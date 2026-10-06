from pathlib import Path

from db import get_connection

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"

CONTAGENS = [
    ("silver.proposicao", "SELECT count(*) FROM silver.proposicao;"),
    ("silver.proposicoes_proponentes", "SELECT count(*) FROM silver.proposicoes_proponentes;"),
    ("silver.proposicao_tema", "SELECT count(*) FROM silver.proposicao_tema;"),
    ("silver.tramitacao", "SELECT count(*) FROM silver.tramitacao;"),
    ("silver.evento", "SELECT count(*) FROM silver.evento;"),
    ("silver.evento_pauta", "SELECT count(*) FROM silver.evento_pauta;"),
]


def executar_transformacao_silver():
    sql = (SQL_DIR / "transform_bronze_to_silver.sql").read_text(encoding="utf-8")
    sql += "\n" + (SQL_DIR / "transform_eventos_to_silver.sql").read_text(encoding="utf-8")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()

        with conn.cursor() as cur:
            for nome, query in CONTAGENS:
                cur.execute(query)
                print(f"{nome}: {cur.fetchone()[0]} linhas")


def executar_transformacao_eventos():
    """Atualiza somente eventos e pautas, sem reprocessar proposições."""
    sql = (SQL_DIR / "transform_eventos_to_silver.sql").read_text(encoding="utf-8")
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()


if __name__ == "__main__":
    executar_transformacao_silver()
