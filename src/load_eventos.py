import json
import time

import api_client as api
from db import get_connection

COMISSOES = {"CAPADR": 2001, "CCJC": 2003, "CMADS": 6174, "PLEN": 180}
# 110/112/125/204/210 = eventos deliberativos (têm pauta, cruzam por proposição).
# 120 = Audiência Pública (não tem pauta; cruza por keyword no assunto — ver
# gold.vw_audiencias_de_interesse).
TIPOS_EVENTO = [110, 112, 120, 125, 204, 210]


def carregar_evento_bronze(conn, evento_payload):
    """Grava o item de listagem do evento (já tem tudo que silver.evento precisa —
    não é necessário chamar /eventos/{id} separadamente) e a pauta associada.
    Audiências públicas retornam pauta vazia — gravada mesmo assim, sem efeito."""
    id_evento = evento_payload["id"]
    resultado = {}

    with conn.cursor() as cur:
        try:
            cur.execute(
                "INSERT INTO bronze.eventos_json (id_evento, payload) VALUES (%s, %s);",
                (id_evento, json.dumps(evento_payload, ensure_ascii=False)),
            )
            conn.commit()
            resultado["evento"] = "ok"
        except Exception as exc:
            conn.rollback()
            resultado["evento"] = f"erro: {exc}"

        time.sleep(api.SLEEP_BETWEEN_CALLS)

        try:
            pauta = api.buscar_pauta_evento(id_evento)
            cur.execute(
                "INSERT INTO bronze.eventos_pauta_json (id_evento, payload) VALUES (%s, %s);",
                (id_evento, json.dumps(pauta, ensure_ascii=False)),
            )
            conn.commit()
            resultado["pauta"] = "ok"
        except Exception as exc:
            conn.rollback()
            resultado["pauta"] = f"erro: {exc}"

    return resultado


def executar_carga_eventos(data_inicio, data_fim, limit=None):
    eventos = api.listar_eventos(COMISSOES.values(), TIPOS_EVENTO, data_inicio, data_fim)
    print(f"{len(eventos)} eventos encontrados entre {data_inicio} e {data_fim}")

    if limit is not None:
        eventos = eventos[:limit]

    ok, erro = 0, 0
    with get_connection() as conn:
        for evento in eventos:
            resultado = carregar_evento_bronze(conn, evento)
            for parte, status in resultado.items():
                if status == "ok":
                    ok += 1
                else:
                    erro += 1
                    print(f"  ! evento {evento['id']} / {parte}: {status}")

    print(f"Carga de eventos concluída. ok: {ok} | erro: {erro}")
    if erro:
        raise RuntimeError(f"Carga de eventos incompleta: {erro} endpoints com erro.")
    return len(eventos)


if __name__ == "__main__":
    import argparse
    from datetime import date, timedelta

    parser = argparse.ArgumentParser(description="Carga de eventos/pautas (teste manual)")
    parser.add_argument("--dias-passado", type=int, default=7)
    parser.add_argument("--dias-futuro", type=int, default=14)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    hoje = date.today()
    executar_carga_eventos(
        hoje - timedelta(days=args.dias_passado),
        hoje + timedelta(days=args.dias_futuro),
        limit=args.limit,
    )
