from pathlib import Path

from db import get_connection

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def apply_sql_file(cursor, filename):
    sql = (SQL_DIR / filename).read_text(encoding="utf-8")
    cursor.execute(sql)


def aplicar_schemas(cur):
    """Aplica todos os schemas e a seed, em ordem (idempotente). Usada pelo setup e pelos testes de SQL."""
    apply_sql_file(cur, "schema_bronze.sql")
    apply_sql_file(cur, "schema_silver.sql")
    apply_sql_file(cur, "seed_acompanhadas.sql")
    # gestao guarda decisões humanas: nunca é derrubado, só evolui com ADD COLUMN IF NOT EXISTS.
    apply_sql_file(cur, "schema_gestao.sql")
    # api_cache depende da gold: derrubado antes e recriado depois (ver schema_api.sql).
    apply_sql_file(cur, "drop_api.sql")
    apply_sql_file(cur, "schema_gold.sql")
    apply_sql_file(cur, "schema_api.sql")


if __name__ == "__main__":
    with get_connection() as conn:
        with conn.cursor() as cur:
            aplicar_schemas(cur)
        conn.commit()
    print("Schemas bronze, silver, gestao, gold e api (e seed das acompanhadas) aplicados com sucesso.")
