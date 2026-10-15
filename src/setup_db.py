from pathlib import Path

from db import get_connection

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"


def apply_sql_file(cursor, filename):
    sql = (SQL_DIR / filename).read_text(encoding="utf-8")
    cursor.execute(sql)


if __name__ == "__main__":
    with get_connection() as conn:
        with conn.cursor() as cur:
            apply_sql_file(cur, "schema_bronze.sql")
            apply_sql_file(cur, "schema_silver.sql")
            apply_sql_file(cur, "seed_acompanhadas.sql")
            apply_sql_file(cur, "schema_gold.sql")
        conn.commit()
    print("Schemas bronze, silver e gold (e seed das acompanhadas) aplicados com sucesso.")
