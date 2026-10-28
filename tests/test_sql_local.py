"""Testes de SQL contra um Postgres real e descartável (sem credenciais reais).

Pulam sem TEST_DATABASE_URL. Localmente: eval "$(scripts/postgres_teste.sh)". Em CI, service postgres:17.
Cada teste recebe um banco limpo (schemas derrubados) com setup_db.aplicar_schemas aplicado.
"""

import os
import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

SCHEMAS = ("api", "api_cache", "gold", "silver", "bronze", "gestao", "contrato")


def _validar_destino():
    """Os testes derrubam schemas: só rodam em banco local e nunca em produção/homologação."""
    from urllib.parse import urlsplit

    host = urlsplit(TEST_DATABASE_URL).hostname
    if host not in ("localhost", "127.0.0.1"):
        raise RuntimeError("TEST_DATABASE_URL precisa apontar para localhost/127.0.0.1.")
    for nome in ("DATABASE_URL", "DATABASE_URL_HOMOLOGACAO"):
        if os.getenv(nome) and os.getenv(nome) == TEST_DATABASE_URL:
            raise RuntimeError(f"TEST_DATABASE_URL não pode ser igual a {nome}.")


def conectar():
    _validar_destino()
    import psycopg2

    return psycopg2.connect(TEST_DATABASE_URL)


def criar_banco_limpo(cur):
    """Derruba os schemas do projeto e reaplica tudo. Ponto de extensão para as próximas camadas."""
    for esquema in SCHEMAS:
        cur.execute(f"DROP SCHEMA IF EXISTS {esquema} CASCADE;")
    from setup_db import aplicar_schemas

    aplicar_schemas(cur)


@unittest.skipUnless(TEST_DATABASE_URL, "TEST_DATABASE_URL não definida")
class BancoLimpoTests(unittest.TestCase):
    def setUp(self):
        self.conn = conectar()
        self.cur = self.conn.cursor()
        criar_banco_limpo(self.cur)
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_schemas_existem(self):
        self.cur.execute("SELECT nspname FROM pg_namespace WHERE nspname = ANY(%s)", (["bronze", "silver", "gold", "api", "api_cache"],))
        self.assertEqual({l[0] for l in self.cur.fetchall()}, {"bronze", "silver", "gold", "api", "api_cache"})

    def test_aplicar_schemas_e_idempotente(self):
        from setup_db import aplicar_schemas

        aplicar_schemas(self.cur)
        self.conn.commit()

    def test_unaccent_disponivel(self):
        self.cur.execute("SELECT extensions.unaccent('suínos')")
        self.assertEqual(self.cur.fetchone()[0], "suinos")


if __name__ == "__main__":
    unittest.main()
