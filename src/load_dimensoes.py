import requests

from config import API_BASE_URL
from db import get_connection
from keywords import KEYWORDS


def popular_dim_tema(conn):
    response = requests.get(f"{API_BASE_URL}/referencias/proposicoes/codTema", timeout=15)
    response.raise_for_status()
    temas = response.json()["dados"]

    with conn.cursor() as cur:
        for tema in temas:
            cur.execute(
                """
                INSERT INTO silver.dim_tema (cod_tema, nome)
                VALUES (%s, %s)
                ON CONFLICT (cod_tema) DO UPDATE SET nome = EXCLUDED.nome;
                """,
                (int(tema["cod"]), tema["nome"]),
            )
    conn.commit()
    print(f"dim_tema: {len(temas)} temas carregados")


def popular_dim_keyword(conn):
    with conn.cursor() as cur:
        cur.execute("TRUNCATE silver.dim_keyword RESTART IDENTITY;")
        for rotulo, termo, termo_requerido in KEYWORDS:
            cur.execute(
                """
                INSERT INTO silver.dim_keyword (termo, rotulo, termo_requerido)
                VALUES (%s, %s, %s);
                """,
                (termo, rotulo, termo_requerido),
            )
    conn.commit()
    print(f"dim_keyword: {len(KEYWORDS)} termos carregados (config)")


if __name__ == "__main__":
    with get_connection() as conn:
        popular_dim_tema(conn)
        popular_dim_keyword(conn)
