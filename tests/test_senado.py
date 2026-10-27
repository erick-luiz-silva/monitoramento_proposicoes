"""Senado no mesmo banco da Câmara: chaves, casa e isolamento, sem API nem banco real."""

from pathlib import Path
import re
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import config
import extract_incremental
import load_dim_deputado
import load_dim_orgao
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


if __name__ == "__main__":
    unittest.main()
