"""Senado no mesmo banco da Câmara: chaves, casa e isolamento, sem API nem banco real."""

from pathlib import Path
import re
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import config

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


if __name__ == "__main__":
    unittest.main()
