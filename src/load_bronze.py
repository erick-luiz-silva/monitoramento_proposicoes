import json
import time

import api_client as api
from db import get_connection

SLEEP_BETWEEN_PROPOSICOES = 0.5

_INSERT_SQL = {
    "proposicoes_json": """
        INSERT INTO bronze.proposicoes_json (id_proposicao, payload)
        VALUES (%s, %s);
    """,
    "autores_json": """
        INSERT INTO bronze.autores_json (id_proposicao, payload)
        VALUES (%s, %s);
    """,
    "temas_json": """
        INSERT INTO bronze.temas_json (id_proposicao, payload)
        VALUES (%s, %s);
    """,
    "tramitacoes_json": """
        INSERT INTO bronze.tramitacoes_json (id_proposicao, payload)
        VALUES (%s, %s);
    """,
}


def _insert_payload(cursor, tabela, id_proposicao, payload):
    cursor.execute(_INSERT_SQL[tabela], (id_proposicao, json.dumps(payload, ensure_ascii=False)))


def carregar_proposicao_bronze(conn, id_proposicao):
    """Busca os 4 endpoints de uma proposição e grava cada resposta na bronze.

    Cada chamada é isolada: se um endpoint falhar, os demais ainda são
    tentados e gravados (bronze é append-only, sem meia-entrada bloqueando o resto).
    """
    endpoints = {
        "proposicoes_json": api.buscar_detalhes,
        "autores_json": api.buscar_autores,
        "temas_json": api.buscar_temas,
        "tramitacoes_json": api.buscar_tramitacoes,
    }

    resultados = {}
    with conn.cursor() as cur:
        for tabela, fetch_fn in endpoints.items():
            try:
                payload = fetch_fn(id_proposicao)
                _insert_payload(cur, tabela, id_proposicao, payload)
                conn.commit()
                resultados[tabela] = "ok"
            except Exception as exc:
                conn.rollback()
                resultados[tabela] = f"erro: {exc}"
            time.sleep(api.SLEEP_BETWEEN_CALLS)
    return resultados


if __name__ == "__main__":
    ids_teste = [497409, 502669]

    with get_connection() as conn:
        for id_proposicao in ids_teste:
            print(f"Carregando proposição {id_proposicao}...")
            resultado = carregar_proposicao_bronze(conn, id_proposicao)
            for tabela, status in resultado.items():
                print(f"  {tabela}: {status}")
            time.sleep(SLEEP_BETWEEN_PROPOSICOES)

    print("Teste de carga concluído.")
