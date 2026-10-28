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
import config
import extract_incremental
import load_bronze_senado
import load_dim_deputado
import load_dim_orgao
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


if __name__ == "__main__":
    unittest.main()
