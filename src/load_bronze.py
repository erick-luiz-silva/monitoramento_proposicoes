import json
import time

import api_client as api
from db import get_connection

SLEEP_BETWEEN_PROPOSICOES = 0.5
STATUS_SUCESSO = ("ok", "pulado")


class ConexaoPerdida(Exception):
    """A conexão com o banco caiu no meio da carga; quem chamou decide se reconecta."""

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


def houve_erro(resultado) -> bool:
    return any(status not in STATUS_SUCESSO for status in resultado.values())


def carregar_estado_bronze(conn, ids) -> dict[int, tuple[dict, bool]]:
    """Lê detalhes anteriores e a necessidade de atualizar autores/temas em lote."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT ids.id_proposicao, detalhes.payload,
                   coalesce(autores.ultima IS NULL OR temas.ultima IS NULL
                   OR least(autores.ultima, temas.ultima) < now() - interval '7 days'
                   OR least(autores.ultima, temas.ultima) < versao.primeira, true)
            FROM unnest(%s::int[]) AS ids(id_proposicao)
            JOIN LATERAL (
                SELECT payload FROM bronze.proposicoes_json
                WHERE id_proposicao = ids.id_proposicao
                ORDER BY data_extracao DESC, id_bronze DESC LIMIT 1
            ) detalhes ON true
            CROSS JOIN LATERAL (
                -- Início da sequência atual de detalhes iguais (depois do último payload
                -- diferente): em A→B→A, autores/temas gravados durante B não valem para o
                -- A de volta.
                -- A ordem é a do id_bronze (sequência de inserção), que desempata timestamps.
                SELECT min(p.data_extracao) AS primeira FROM bronze.proposicoes_json p
                WHERE p.id_proposicao = ids.id_proposicao AND p.payload = detalhes.payload
                  AND p.id_bronze > coalesce((
                      SELECT max(d.id_bronze) FROM bronze.proposicoes_json d
                      WHERE d.id_proposicao = ids.id_proposicao AND d.payload <> detalhes.payload
                  ), 0)
            ) versao
            CROSS JOIN LATERAL (
                SELECT max(data_extracao) AS ultima FROM bronze.autores_json
                WHERE id_proposicao = ids.id_proposicao
            ) autores
            CROSS JOIN LATERAL (
                SELECT max(data_extracao) AS ultima FROM bronze.temas_json
                WHERE id_proposicao = ids.id_proposicao
            ) temas;
            """,
            (list(ids),),
        )
        return {id_prop: (payload, precisa) for id_prop, payload, precisa in cur.fetchall()}


def carregar_proposicao_bronze(conn, id_proposicao, estado=None):
    """Grava detalhes e tramitações sempre; autores/temas conforme o estado anterior.

    Sem estado, busca os quatro endpoints, como na carga histórica e na reconciliação.

    Cada chamada é isolada: se um endpoint falhar, os demais ainda são
    tentados e gravados (bronze é append-only, sem meia-entrada bloqueando o resto).
    Se a própria conexão cair, levanta ConexaoPerdida — não adianta tentar os
    demais endpoints nem dar rollback numa conexão fechada.
    """
    endpoints = {
        "proposicoes_json": api.buscar_detalhes,
        "autores_json": api.buscar_autores,
        "temas_json": api.buscar_temas,
        "tramitacoes_json": api.buscar_tramitacoes,
    }

    resultados = {}
    precisa_autores_temas = estado is None or id_proposicao not in estado
    if not precisa_autores_temas:
        detalhes_anteriores, precisa_autores_temas = estado[id_proposicao]
    with conn.cursor() as cur:
        for tabela, fetch_fn in endpoints.items():
            if tabela in ("autores_json", "temas_json") and not precisa_autores_temas:
                resultados[tabela] = "pulado"
                continue
            try:
                payload = fetch_fn(id_proposicao)
                if tabela == "proposicoes_json" and not precisa_autores_temas:
                    precisa_autores_temas = payload != detalhes_anteriores
                _insert_payload(cur, tabela, id_proposicao, payload)
                conn.commit()
                resultados[tabela] = "ok"
            except Exception as exc:
                if conn.closed:
                    raise ConexaoPerdida(f"conexão encerrada na proposição {id_proposicao}: {exc}") from exc
                conn.rollback()
                resultados[tabela] = f"erro: {exc}"
                if tabela == "proposicoes_json":
                    precisa_autores_temas = True
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
