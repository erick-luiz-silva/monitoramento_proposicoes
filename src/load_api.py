"""Atualiza as cópias materializadas lidas pelo Power BI (sql/schema_api.sql).

Chamado no fim de cada carga (completa, pautas, inclusão) e de load_dimensoes.py.
É derivado e idempotente: se falhar, nada se perde e o próximo run recalcula — por isso
a carga incremental o chama depois de registrar as janelas, e só soma o erro no fim.
"""

from db import get_connection

# Ordem importa: vw_tramitacoes filtra por api_cache.vw_monitoramento, que precisa
# estar atualizada antes, na mesma transação.
MATERIALIZADAS = (
    "vw_proposicao_keywords",
    "vw_monitoramento",
    "vw_proposicoes_sem_keyword",
    "vw_tramitacoes",
    "vw_pautas_monitoradas",
    "vw_audiencias_de_interesse",
)


def atualizar_api():
    # Uma transação só: o BI nunca vê monitoramento novo com tramitações velhas.
    # CONCURRENTLY não bloqueia a leitura da Data API durante o refresh.
    with get_connection() as conn:
        with conn.cursor() as cur:
            for nome in MATERIALIZADAS:
                cur.execute(f"REFRESH MATERIALIZED VIEW CONCURRENTLY api_cache.{nome};")
        conn.commit()
    print(f"Schema api atualizado: {len(MATERIALIZADAS)} materialized views.")


if __name__ == "__main__":
    atualizar_api()
