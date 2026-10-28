"""Bronze do Senado: detalhe de cada processo (/processo/{id}) e mapa dos processos "Revisora".

Append-only como a bronze da Câmara, mas só grava quando o payload muda (hash do JSON
canônico): os detalhes têm de 15 a 300 KB e gravá-los todo dia daria GBs por ano. A
transformação lê só o último snapshot de cada processo (os informes são cumulativos).
"""

import hashlib
import json

import api_client_senado as api
from load_bronze import ConexaoPerdida

_SQL_ULTIMO_HASH = """
    SELECT hash_payload FROM bronze.sf_processo_json
    WHERE id_processo = %s ORDER BY data_extracao DESC, id_bronze DESC LIMIT 1;
"""
_SQL_INSERT = "INSERT INTO bronze.sf_processo_json (id_processo, hash_payload, payload) VALUES (%s, %s, %s);"
_SQL_MAPA = """
    INSERT INTO bronze.sf_mapa_revisora (id_processo, sigla, numero, ano)
    VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING;
"""


def hash_payload(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def carregar_processo(conn, id_processo):
    """Busca o detalhe e grava se mudou. Devolve "ok", "igual" ou "erro: …".

    Erro de API ou de SQL não levanta (quem chama decide se é bloqueante); conexão
    caída levanta ConexaoPerdida, como na bronze da Câmara.
    """
    try:
        payload = api.buscar_processo(id_processo)
    except Exception as exc:
        return f"erro: {exc}"
    novo = hash_payload(payload)
    try:
        with conn.cursor() as cur:
            cur.execute(_SQL_ULTIMO_HASH, (id_processo,))
            ultimo = cur.fetchone()
            if ultimo and ultimo[0] == novo:
                conn.rollback()
                return "igual"
            cur.execute(_SQL_INSERT, (id_processo, novo, json.dumps(payload, ensure_ascii=False)))
        conn.commit()
        return "ok"
    except Exception as exc:
        if conn.closed:
            raise ConexaoPerdida(f"conexão encerrada no processo {id_processo} do Senado: {exc}") from exc
        conn.rollback()
        return f"erro: {exc}"


def gravar_mapa(conn, id_processo, numeros):
    """Números da Câmara (sigla, número, ano) de um processo "Revisora"."""
    with conn.cursor() as cur:
        cur.executemany(_SQL_MAPA, [(id_processo, sigla, numero, ano) for sigla, numero, ano in numeros])
    conn.commit()
