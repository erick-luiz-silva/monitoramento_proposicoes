"""Senado no mesmo banco da Câmara: chaves, casa e isolamento, sem API nem banco real."""

from datetime import date
import json
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import api_client_senado
import comparar_acompanhamento
import config
import extract_incremental
import extract_senado
import load_bronze_senado
import load_dim_deputado
import load_dim_orgao
import load_dim_senador
import load_silver
import pipeline_inclusao

SQL_DIR = Path(__file__).resolve().parents[1] / "sql"


def ler(nome):
    return (SQL_DIR / nome).read_text(encoding="utf-8")


def sem_comentarios(sql):
    return re.sub(r"--[^\n]*", "", sql)


def gold_view(nome):
    sql = sem_comentarios(ler("schema_gold.sql"))
    return re.search(rf"CREATE OR REPLACE VIEW gold\.{nome} AS(.*?);", sql, re.S).group(1)


def api_view(nome):
    sql = sem_comentarios(ler("schema_api.sql"))
    return re.search(rf"CREATE VIEW api\.{nome} AS(.*?);", sql, re.S).group(1)


class ChaveSenadoTests(unittest.TestCase):
    def test_chaves_e_casa(self):
        self.assertEqual(config.chave_senado(8152618), 1_008_152_618)
        self.assertEqual(config.chave_sessao_plenario(457111), 2_000_457_111)
        self.assertEqual(config.casa_de(2229763), "CD")
        self.assertEqual(config.casa_de(1_008_152_618), "SF")
        self.assertTrue(config.eh_camara(999_999_999))
        self.assertFalse(config.eh_camara(1_000_000_000))

    def test_chave_cabe_em_int_do_postgres(self):
        self.assertLess(config.chave_senado(999_999_999), 2**31 - 1)

    def test_id_nativo_invalido_levanta(self):
        for invalido in (-1, 1_000_000_000):
            with self.assertRaises(ValueError):
                config.chave_senado(invalido)


class SilverSenadoSqlTests(unittest.TestCase):
    def test_colunas_novas_idempotentes(self):
        sql = ler("schema_silver.sql")
        for trecho in ("ADD COLUMN IF NOT EXISTS casa", "ADD COLUMN IF NOT EXISTS id_origem",
                       "ADD COLUMN IF NOT EXISTS data_apresentacao_origem", "ADD COLUMN IF NOT EXISTS eh_relator",
                       "ADD COLUMN IF NOT EXISTS votado", "ck_proposicao_casa",
                       "CREATE TABLE IF NOT EXISTS silver.proposicao_vinculo"):
            self.assertIn(trecho, sql)

    def test_backfill_so_toca_a_camara(self):
        updates = [c for c in sem_comentarios(ler("schema_silver.sql")).split(";") if "UPDATE silver." in c]
        self.assertEqual(len(updates), 4)
        for u in updates:
            self.assertTrue("casa = 'CD'" in u or "< 1000000000" in u, u)
        self.assertTrue(any("votado = (uri_votacao IS NOT NULL)" in u for u in updates))

    def test_camara_grava_origem_relator_e_votado(self):
        bronze = sem_comentarios(ler("transform_bronze_to_silver.sql"))
        self.assertIn("id_origem", bronze)
        self.assertIn("data_apresentacao_origem", bronze)
        self.assertIn("~* '^Designação de Relator'", bronze)
        eventos = sem_comentarios(ler("transform_eventos_to_silver.sql"))
        self.assertIn("(elem->>'uriVotacao') IS NOT NULL", eventos)
        self.assertRegex(eventos, r"DELETE FROM silver\.evento_pauta[\s\S]*?id_evento < 1000000000")


class CamaraIgnoraSenadoTests(unittest.TestCase):
    def test_acompanhadas_filtram_por_casa(self):
        cur = MagicMock(); cur.fetchall.return_value = []
        conn = MagicMock(); conn.cursor.return_value.__enter__.return_value = cur
        extract_incremental.carregar_ids_acompanhadas(conn)
        self.assertIn("id_proposicao < %s", cur.execute.call_args.args[0])
        self.assertEqual(cur.execute.call_args.args[1], (config.SENADO_OFFSET,))
        extract_incremental.carregar_ids_acompanhadas(conn, casa="SF")
        self.assertIn("id_proposicao >= %s", cur.execute.call_args.args[0])

    def test_dims_da_camara_so_pegam_ids_da_camara(self):
        self.assertEqual(load_dim_orgao._SQL_IDS_ORGAO.count("casa = 'CD'"), 3)
        for sql in (load_dim_deputado._SQL_PROPONENTES, load_dim_deputado._SQL_AUTORES_RUN):
            self.assertIn("uri ~ '/[0-9]+$'", sql)
            self.assertIn("id_proposicao < 1000000000", sql)
        self.assertIn("uri ~ '/[0-9]+$'", load_dim_deputado._SQL_IDS_DEPUTADOS)

    def test_guarda_pela_faixa_de_id_mesmo_sem_casa(self):
        # Se uma linha do Senado cair com o DEFAULT 'CD', a faixa de id ainda segura.
        self.assertEqual(load_dim_orgao._SQL_IDS_ORGAO.count("< 1000000000"), 3)
        for sql in (load_dim_deputado._SQL_RELATORES, load_dim_deputado._SQL_IDS_DEPUTADOS):
            self.assertIn("id_evento < 1000000000", sql)

    def test_inclusao_nao_manda_id_do_senado_para_a_camara(self):
        # Mesmo que a lista de acompanhadas traga um id do Senado, a carga da Câmara não o recebe.
        with patch.object(pipeline_inclusao, "get_connection"), patch.object(
            pipeline_inclusao, "carregar_ids_acompanhadas", return_value=[2229763, 1008152618]
        ), patch.object(
            pipeline_inclusao, "carregar_ids_existentes", side_effect=[set(), {2229763}]
        ), patch.object(
            pipeline_inclusao, "carregar_ids", return_value=([2229763], 0)
        ) as carregar, patch.object(pipeline_inclusao, "executar_transformacao_silver"), patch.object(
            pipeline_inclusao, "carregar_dim_deputado"
        ), patch.object(pipeline_inclusao, "carregar_dim_orgao"), patch.object(pipeline_inclusao, "atualizar_api"):
            pipeline_inclusao.executar_pipeline_inclusao()
        self.assertEqual(carregar.call_args.args[0], [2229763])


class GoldSenadoSqlTests(unittest.TestCase):
    def test_monitoramento_colunas_no_fim_e_sem_join_que_multiplica(self):
        v = gold_view("vw_monitoramento")
        select, resto = v.split("FROM silver.proposicao p")
        self.assertTrue(select.rstrip().endswith("ids_vinculados"))
        self.assertLess(select.index("p.data_apresentacao"), select.rindex("casa"))
        self.assertNotIn("proposicao_vinculo", v)
        self.assertNotIn("proposicao_acompanhada", v)          # acompanhamento só via g.grupo_acompanhado
        self.assertEqual(v.count("g.grupo_acompanhado"), 3)    # acompanhada, em_radar, WHERE
        self.assertIn("coalesce(g.data_origem_grupo, p.data_apresentacao) >= DATE '2026-09-01'", v)
        self.assertIn("autor.uri ~ '/[0-9]+$'", v)

    def test_grupo_recursivo_termina_e_tem_uma_linha_por_id(self):
        sql = sem_comentarios(ler("schema_gold.sql"))
        g = gold_view("vw_grupo_projeto")
        self.assertIn("WITH RECURSIVE", g)
        self.assertNotIn("UNION ALL", g)
        self.assertIn("GROUP BY", g)
        self.assertIn("FROM silver.proposicao_vinculo", g)
        self.assertIn("OVER (PARTITION BY", g)                  # grupo_acompanhado calculado uma vez
        # data de origem do projeto = a mais antiga do grupo (defesa se o Senado vier sem a data de origem)
        self.assertIn("min(coalesce(p.data_apresentacao_origem, p.data_apresentacao)) OVER (PARTITION BY", g)
        self.assertLess(sql.index("VIEW gold.vw_grupo_projeto"), sql.index("VIEW gold.vw_monitoramento"))

    def test_relator_e_votado_vem_da_silver(self):
        self.assertIn("t.eh_relator", gold_view("vw_movimentacoes"))
        self.assertNotIn("uri_votacao IS NOT NULL", gold_view("vw_pautas_monitoradas"))
        self.assertIn("ultima_carga_senado", api_view("vw_ultima_carga"))

    def test_colunas_do_cache_existem_na_gold(self):
        # Toda coluna lida por uma MV do api_cache precisa sair da view gold de origem
        # (pego no container: a MV de pautas lia votado, que a gold não expunha).
        api = sem_comentarios(ler("schema_api.sql"))
        for nome, colunas, origem in re.findall(
                r"CREATE MATERIALIZED VIEW api_cache\.(\w+) AS\s+SELECT (.*?)\s+FROM gold\.(\w+)", api, re.S):
            select_gold = gold_view(origem).split("\nFROM ")[0]
            colunas = re.sub(r"row_number\(\) OVER \(.*?\) AS _id,", "", colunas, flags=re.S)
            for coluna in re.split(r",\s*", re.sub(r"\b\w+\.", "", colunas)):
                coluna = coluna.split(" AS ")[-1].strip()
                self.assertRegex(select_gold, rf"(\.|AS |\s){coluna}\s*(,|$)", f"{nome}: {coluna}")


class ClienteSenadoTests(unittest.TestCase):
    ARVORE = [{"codigo": 1, "nome": "Raiz A", "filhos": [
                  {"codigo": 11, "nome": "A1", "filhos": [{"codigo": 111, "nome": "A11", "filhos": []}]},
                  {"codigo": 12, "nome": "A2"}]},
              {"codigo": 2, "nome": "Raiz B", "filhos": [{"codigo": 21, "nome": "B1", "filhos": []}]}]

    def setUp(self):
        self.sleep = patch.object(api_client_senado.time, "sleep").start()
        self.addCleanup(patch.stopall)

    def resposta(self, status, dados=None):
        r = MagicMock(status_code=status)
        r.json.return_value = dados
        return r

    def test_como_lista(self):
        self.assertEqual(api_client_senado.como_lista(None), [])
        self.assertEqual(api_client_senado.como_lista({"a": 1}), [{"a": 1}])
        self.assertEqual(api_client_senado.como_lista([1, 2]), [1, 2])

    def test_expandir_classes_inclui_descendentes_sem_repetir(self):
        with patch.object(api_client_senado, "listar_classes", return_value=self.ARVORE):
            self.assertEqual(api_client_senado.expandir_classes((1, 11)), [1, 11, 111, 12])
            self.assertEqual(api_client_senado.expandir_classes((2,)), [2, 21])

    def test_retry_em_503_ate_dar_certo(self):
        get = patch.object(api_client_senado.SESSAO, "get", side_effect=[
            self.resposta(503), self.resposta(503), self.resposta(200, {"id": 1})]).start()
        self.assertEqual(api_client_senado.buscar_processo(1), {"id": 1})
        self.assertEqual(get.call_count, 3)

    def test_esgotar_tentativas_levanta(self):
        patch.object(api_client_senado.SESSAO, "get", return_value=self.resposta(503)).start()
        with self.assertRaisesRegex(RuntimeError, "HTTP 503"):
            api_client_senado.buscar_processo(1)

    def test_404_levanta_sem_retry(self):
        get = patch.object(api_client_senado.SESSAO, "get", return_value=self.resposta(404)).start()
        with self.assertRaisesRegex(RuntimeError, "HTTP 404"):
            api_client_senado.buscar_processo(1)
        self.assertEqual(get.call_count, 1)

    def test_listar_processos_monta_parametros_e_normaliza_lista(self):
        get = patch.object(api_client_senado.SESSAO, "get", return_value=self.resposta(200, {"id": 5})).start()
        self.assertEqual(api_client_senado.listar_processos(numdias=14, codigo_classe=33805062), [{"id": 5}])
        self.assertEqual(get.call_args.kwargs["params"], {"numdias": 14, "codigoClasse": 33805062})
        api_client_senado.listar_processos(sigla="MPV", data_inicio=date(2025, 1, 1), data_fim=date(2025, 12, 31), tramitando=True)
        self.assertEqual(get.call_args.kwargs["params"], {"sigla": "MPV", "dataInicioApresentacao": "2025-01-01",
                                                          "dataFimApresentacao": "2025-12-31", "tramitando": "S"})

    def test_arvore_real_usa_campo_filhos(self):
        arvore = json.loads((Path(__file__).parent / "fixtures" / "senado" / "classes.json").read_text(encoding="utf-8"))
        with patch.object(api_client_senado, "listar_classes", return_value=arvore):
            filhos = api_client_senado.expandir_classes((33809634,))
        self.assertEqual(filhos[0], 33809634)
        self.assertGreater(len(filhos), 1)


class BronzeSenadoTests(unittest.TestCase):
    def conexao(self, ultimo_hash=None):
        cur = MagicMock()
        cur.fetchone.return_value = (ultimo_hash,) if ultimo_hash else None
        conn = MagicMock(closed=0)
        conn.cursor.return_value.__enter__.return_value = cur
        return conn, cur

    def inserts(self, cur):
        return [c for c in cur.execute.call_args_list if "INSERT INTO bronze.sf_processo_json" in c.args[0]]

    def test_grava_so_quando_o_payload_muda(self):
        payload = {"id": 8152618, "b": 2, "a": 1}
        with patch.object(load_bronze_senado.api, "buscar_processo", return_value=payload):
            conn, cur = self.conexao()
            self.assertEqual(load_bronze_senado.carregar_processo(conn, 8152618), "ok")
            self.assertEqual(len(self.inserts(cur)), 1)
            conn.commit.assert_called()
            mesmo_hash = self.inserts(cur)[0].args[1][1]
            conn, cur = self.conexao(ultimo_hash=mesmo_hash)
            self.assertEqual(load_bronze_senado.carregar_processo(conn, 8152618), "igual")
            self.assertEqual(self.inserts(cur), [])
        # a ordem das chaves não muda o hash
        self.assertEqual(load_bronze_senado.hash_payload({"a": 1, "b": 2}), load_bronze_senado.hash_payload({"b": 2, "a": 1}))

    def test_erro_de_api_devolve_erro_sem_gravar(self):
        with patch.object(load_bronze_senado.api, "buscar_processo", side_effect=RuntimeError("HTTP 503")):
            conn, cur = self.conexao()
            self.assertEqual(load_bronze_senado.carregar_processo(conn, 1), "erro: HTTP 503")
        self.assertEqual(self.inserts(cur), [])

    def test_erro_sql_faz_rollback(self):
        with patch.object(load_bronze_senado.api, "buscar_processo", return_value={"id": 1}):
            conn, cur = self.conexao()
            cur.execute.side_effect = [None, RuntimeError("falha no insert")]
            self.assertTrue(load_bronze_senado.carregar_processo(conn, 1).startswith("erro: falha"))
        conn.rollback.assert_called()

    def test_mapa_ignora_repetidos(self):
        conn, cur = self.conexao()
        load_bronze_senado.gravar_mapa(conn, 8981388, [("PL", 4314, 2016)])
        sql = cur.executemany.call_args.args[0]
        self.assertIn("INSERT INTO bronze.sf_mapa_revisora", sql)
        self.assertIn("ON CONFLICT DO NOTHING", sql)
        self.assertEqual(cur.executemany.call_args.args[1], [(8981388, "PL", 4314, 2016)])

    def test_tabelas_da_bronze(self):
        sql = ler("schema_bronze.sql")
        self.assertIn("CREATE TABLE IF NOT EXISTS bronze.sf_processo_json", sql)
        self.assertIn("hash_payload", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS bronze.sf_mapa_revisora", sql)


class TransformacaoSenadoSqlTests(unittest.TestCase):
    def comandos(self):
        sql = sem_comentarios(ler("transform_senado_to_silver.sql"))
        return [c.strip() for c in sql.split(";") if c.strip()]

    def test_proposicao_e_tramitacao_gravam_sf(self):
        cmds = self.comandos()
        for tabela in ("silver.proposicao (", "silver.tramitacao ("):
            insert = next(c for c in cmds if c.startswith(("INSERT INTO " + tabela, "WITH")) and ("INSERT INTO " + tabela) in c)
            self.assertIn("'SF'", insert, tabela)
        tram = next(c for c in cmds if "INSERT INTO silver.tramitacao" in c)
        self.assertIn("ON CONFLICT (id_proposicao, sequencia) DO NOTHING", tram)

    def test_deletes_so_na_faixa_do_senado(self):
        for c in self.comandos():
            if c.upper().startswith("DELETE FROM SILVER."):
                self.assertTrue("1000000000" in c or "origem <> 'manual'" in c, c)

    def test_exclui_substitutivo_e_emenda_e_colegiado_vazio(self):
        sql = sem_comentarios(ler("transform_senado_to_silver.sql"))
        self.assertIn("'Substitutivo'", sql)
        self.assertIn("'Emenda'", sql)
        self.assertIn("? 'codigo'", sql)
        self.assertIn("DISTINCT ON (codigo)", sql)

    def test_situacao_deterministica(self):
        sql = sem_comentarios(ler("transform_senado_to_silver.sql"))
        self.assertIn("WITH ORDINALITY", sql)
        self.assertIn("situacaoAtual", sql)

    def test_transformacao_no_cursor_sem_commit(self):
        cur = MagicMock()
        load_silver.executar_transformacao_senado(cur)
        self.assertIn("silver.proposicao", cur.execute.call_args.args[0])
        self.assertFalse(hasattr(cur, "commit") and cur.commit.called)


class GoldSenadoFase3Tests(unittest.TestCase):
    def test_keywords_sem_acento_so_no_senado(self):
        v = gold_view("vw_proposicao_keywords")
        self.assertIn("CASE WHEN p.casa = 'SF' THEN", v)
        self.assertIn("extensions.unaccent(", v)
        # o ramo da Câmara continua sem unaccent
        camara = v.split("ELSE", 1)[1]
        self.assertNotIn("unaccent", camara.split("END", 1)[0])

    def test_autor_do_senado_e_do_grupo(self):
        v = gold_view("vw_monitoramento")
        self.assertIn("LEFT JOIN silver.dim_senador sen", v)
        self.assertIn("sen.codigo = autor.codigo_parlamentar_senado", v)
        self.assertIn("autor.partido_autor_epoca", v)
        self.assertIn("dep_grupo", v)

    def test_comparador_espelha_a_regra_por_casa(self):
        cur = MagicMock(); cur.fetchall.return_value = []
        comparar_acompanhamento.rotulos_do_silver(cur, False)
        sql = cur.execute.call_args.args[0]
        self.assertIn("CASE WHEN p.casa = 'SF' THEN", sql)
        self.assertIn("extensions.unaccent(", sql)


class DimSenadorTests(unittest.TestCase):
    FIX = Path(__file__).parent / "fixtures" / "senado"

    def setUp(self):
        self.lista = json.loads((self.FIX / "senador_lista_atual.json").read_text(encoding="utf-8"))
        self.um = json.loads((self.FIX / "senador_3366.json").read_text(encoding="utf-8"))
        self.cur = MagicMock()
        conn = MagicMock(); conn.__enter__.return_value = conn
        conn.cursor.return_value.__enter__.return_value = self.cur
        self.conn = conn
        patch.object(load_dim_senador, "get_connection", return_value=conn).start()
        self.addCleanup(patch.stopall)

    def gravados(self):
        return [c.args[1][0] for c in self.cur.execute.call_args_list if "INSERT INTO silver.dim_senador" in c.args[0]]

    def test_carrega_atuais_e_ausentes(self):
        self.cur.fetchall.return_value = [(3366,)]
        def get(caminho, params=None):
            return self.lista if caminho == "/senador/lista/atual" else self.um
        patch.object(load_dim_senador.api, "_get", side_effect=get).start()
        n = load_dim_senador.carregar_dim_senador()
        self.assertEqual(n, 6)
        self.assertIn(3366, self.gravados())
        self.conn.commit.assert_called()

    def test_lista_com_um_so_parlamentar_vem_como_objeto(self):
        unico = {"ListaParlamentarEmExercicio": {"Parlamentares": {"Parlamentar":
                 self.lista["ListaParlamentarEmExercicio"]["Parlamentares"]["Parlamentar"][0]}}}
        self.cur.fetchall.return_value = []
        patch.object(load_dim_senador.api, "_get", return_value=unico).start()
        self.assertEqual(load_dim_senador.carregar_dim_senador(), 1)

    def test_404_num_ex_senador_nao_levanta(self):
        self.cur.fetchall.return_value = [(1,), (3366,)]
        def get(caminho, params=None):
            if caminho == "/senador/lista/atual":
                return self.lista
            if caminho == "/senador/1":
                raise RuntimeError("HTTP 404")
            return self.um
        patch.object(load_dim_senador.api, "_get", side_effect=get).start()
        load_dim_senador.carregar_dim_senador()          # não levanta
        self.assertIn(3366, self.gravados())
        self.assertNotIn(1, self.gravados())


class CargaSenadoTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.conn = MagicMock()
        self.cur = self.conn.cursor.return_value.__enter__.return_value
        self.cur.fetchall.return_value = []            # sem duplicatas
        p = lambda nome, **kw: patch.object(extract_senado, nome, **kw).start()
        self.addCleanup(patch.stopall)
        p("get_connection", return_value=self.conn)
        self.conn.__enter__.return_value = self.conn
        p("calcular_numdias", return_value=(15, False))
        self.acompanhadas = p("carregar_acompanhadas_sf", return_value=[2916834])
        self.candidatos = p("coletar_candidatos", return_value=[8152618, 8283772])
        self.mapa = p("atualizar_mapa_revisora", return_value=0)
        self.gemeos = p("ids_gemeos", return_value=[7364805])
        self.recon = p("ids_reconciliacao", return_value=[9000001])
        self.carregar = p("carregar_processo", side_effect=lambda conn, i: self.events.append(("bronze", i)) or "ok")
        self.transformar = p("executar_transformacao_senado", side_effect=lambda cur: self.events.append("silver"))
        self.dim = p("carregar_dim_senador", side_effect=lambda: self.events.append("dim") or 81)
        self.registrar = p("registrar_execucao", side_effect=lambda conn, tipo, *a: self.events.append(("janela", tipo)))

    def janelas(self):
        return [e[1] for e in self.events if isinstance(e, tuple) and e[0] == "janela"]

    def test_sucesso_registra_janelas_depois_da_transformacao(self):
        extract_senado.executar_carga_senado()
        self.assertEqual(self.janelas(), ["incremental_senado", "reconciliacao_senado"])
        self.assertLess(self.events.index("silver"), self.events.index(("janela", "incremental_senado")))
        carregados = [e[1] for e in self.events if isinstance(e, tuple) and e[0] == "bronze"]
        self.assertEqual(sorted(carregados), [2916834, 7364805, 8152618, 8283772, 9000001])
        self.conn.commit.assert_called()

    def test_erro_num_candidato_nao_registra_incremental_e_levanta(self):
        self.carregar.side_effect = lambda conn, i: "erro: HTTP 503" if i == 8152618 else "ok"
        with self.assertRaises(RuntimeError) as ctx:
            extract_senado.executar_carga_senado()
        self.assertNotIsInstance(ctx.exception, extract_senado.SenadoComPendencias)
        self.assertNotIn("incremental_senado", self.janelas())

    def test_erro_em_acompanhada_ou_gemeo_registra_e_vira_pendencia(self):
        self.carregar.side_effect = lambda conn, i: "erro: HTTP 404" if i in (2916834, 7364805) else "ok"
        with self.assertRaises(extract_senado.SenadoComPendencias):
            extract_senado.executar_carga_senado()
        self.assertIn("incremental_senado", self.janelas())

    def test_mapa_falhando_vira_pendencia(self):
        self.mapa.side_effect = RuntimeError("HTTP 503")
        with self.assertRaises(extract_senado.SenadoComPendencias):
            extract_senado.executar_carga_senado()
        self.assertIn("incremental_senado", self.janelas())

    def test_prazo_estourado_levanta_sem_registrar(self):
        relogio = iter([0.0] + [10_000.0] * 50)
        patch.object(extract_senado.time, "monotonic", side_effect=lambda: next(relogio)).start()
        with self.assertRaises(TimeoutError):
            extract_senado.executar_carga_senado()
        self.assertEqual(self.janelas(), [])
        self.transformar.assert_not_called()

    def test_duplicata_desfaz_a_transformacao(self):
        self.cur.fetchall.return_value = [(1008152618,)]
        with self.assertRaisesRegex(RuntimeError, "duplicad"):
            extract_senado.executar_carga_senado()
        self.conn.rollback.assert_called()
        self.assertEqual(self.janelas(), [])

    def test_calcular_numdias(self):
        patch.stopall()
        cur = MagicMock(); conn = MagicMock(); conn.cursor.return_value.__enter__.return_value = cur
        hoje = date(2026, 10, 28)
        for ultimo, esperado in ((date(2026, 10, 27), (15, False)), (date(2026, 10, 8), (30, True)), (None, (30, False))):
            cur.fetchone.return_value = (ultimo,)
            self.assertEqual(extract_senado.calcular_numdias(conn, hoje), esperado)


class OrquestradorPendenciasTests(unittest.TestCase):
    def test_pendencia_tem_aviso_proprio(self):
        with patch.object(extract_incremental, "limpar_aviso_senado"), patch.object(
            extract_incremental, "executar_carga_camara", return_value=[]), patch.object(
            extract_incremental, "executar_carga_senado",
            side_effect=extract_senado.SenadoComPendencias("acompanhadas: 1 com erro")), patch.object(
            extract_incremental, "atualizar_api"), patch.object(extract_incremental, "gravar_aviso_senado") as aviso:
            extract_incremental.executar_carga_incremental()
        self.assertTrue(aviso.call_args.args[0].startswith("Senado atualizado com pendências: "))


class SeedSenadoTests(unittest.TestCase):
    def test_acompanhadas_do_senado_e_vinculos_manuais(self):
        seed = sem_comentarios(ler("seed_acompanhadas.sql"))
        ids = [int(i) for i in re.findall(r"\((\d{10}), 'planilha_antiga'", seed)]
        self.assertEqual(sorted(ids), sorted(config.SENADO_OFFSET + i for i in (
            8283772, 8992504, 8900340, 7376720, 7403160, 2913579, 2916834, 2916662, 8537155)))
        self.assertIn("INSERT INTO silver.proposicao_vinculo", seed)
        self.assertIn("(2092191, 1007364805, 'manual')", seed)
        self.assertIn("(2344901, 1007403160, 'manual')", seed)
        self.assertEqual(seed.count("ON CONFLICT"), 3)


class VinculoSenadoTests(unittest.TestCase):
    def test_sql_das_tres_origens_e_data_pela_camara(self):
        sql = sem_comentarios(ler("transform_senado_to_silver.sql"))
        for origem in ("'identificacao'", "'revisora'", "'mpv'"):
            self.assertIn(origem, sql)
        self.assertRegex(sql, r"DELETE FROM silver\.proposicao_vinculo\s+WHERE origem <> 'manual'")
        self.assertIn(">= 2002", sql)
        self.assertIn("<= 7", sql)
        self.assertIn("dataInicioEfetivo", sql)
        self.assertRegex(sql, r"UPDATE silver\.proposicao[\s\S]*data_apresentacao_origem[\s\S]*proposicao_vinculo")

    def test_numeros_da_camara_vem_do_detalhe(self):
        detalhe = json.loads((Path(__file__).parent / "fixtures" / "senado" / "8981388.json").read_text(encoding="utf-8"))
        self.assertIn(("PL", 4314, 2016), extract_senado.numeros_camara(detalhe))
        self.assertEqual(extract_senado.numeros_camara({"siglaCasaIniciadora": "SF", "outrosNumeros": []}), [])
        self.assertEqual(extract_senado.numeros_camara({"siglaCasaIniciadora": "CD",
                                                        "identificacaoProcessoInicial": "MPV 2163-41/2001"}), [])

    def test_mapa_sempre_busca_o_detalhe_dos_novos(self):
        lista = [{"id": 1, "identificacao": "PL 395/2019", "objetivo": "Revisora"},
                 {"id": 2, "identificacao": "PL 10/2020", "objetivo": "Revisora"},
                 {"id": 3, "identificacao": "PL 5/2020", "objetivo": "Iniciadora"}]
        detalhe = {"siglaCasaIniciadora": "CD", "identificacaoProcessoInicial": "PL 6882/2017", "outrosNumeros": []}
        cur = MagicMock(); cur.fetchall.return_value = [(2,)]          # o 2 já está no mapa
        conn = MagicMock(); conn.cursor.return_value.__enter__.return_value = cur
        with patch.object(extract_senado.api, "listar_processos", return_value=lista) as listar, patch.object(
                extract_senado.api, "buscar_processo", return_value=detalhe) as buscar, patch.object(
                extract_senado, "gravar_mapa") as gravar:
            self.assertEqual(extract_senado.atualizar_mapa_revisora(conn, completo=False, numdias=14), 1)
        listar.assert_called_once_with(numdias=14)
        buscar.assert_called_once_with(1)                              # nunca usa o número da lista
        gravar.assert_called_once_with(conn, 1, [("PL", 6882, 2017)])

    def test_mapa_completo_usa_tramitando(self):
        with patch.object(extract_senado.api, "listar_processos", return_value=[]) as listar:
            cur = MagicMock(); cur.fetchall.return_value = []
            conn = MagicMock(); conn.cursor.return_value.__enter__.return_value = cur
            extract_senado.atualizar_mapa_revisora(conn, completo=True)
        listar.assert_called_once_with(tramitando=True)


if __name__ == "__main__":
    unittest.main()
