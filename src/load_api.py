"""Atualiza as cópias materializadas lidas pelo Power BI e pelo /legislativo (sql/schema_api.sql).

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

# Sinal de frescor do cache (RF10, contrato.vw_frescor e api.vw_ultima_carga): gravado na
# mesma transação dos REFRESH, então só existe se o cache inteiro foi atualizado. As colunas
# de janela são NOT NULL: recebem o "hoje" de Brasília.
SQL_REGISTRAR = """
INSERT INTO bronze.controle_execucao (tipo_carga, data_inicio_janela, data_fim_janela, qtd_proposicoes)
SELECT 'atualizacao_api', h.dia, h.dia, (SELECT count(*) FROM api_cache.vw_monitoramento)
FROM (SELECT (now() AT TIME ZONE 'America/Sao_Paulo')::date AS dia) h;
"""


def atualizar_cache(cur):
    """REFRESH de todas as materializadas + registro 'atualizacao_api', no cursor/transação dado."""
    # CONCURRENTLY não bloqueia a leitura da Data API durante o refresh.
    for nome in MATERIALIZADAS:
        cur.execute(f"REFRESH MATERIALIZED VIEW CONCURRENTLY api_cache.{nome};")
    cur.execute(SQL_REGISTRAR)


def atualizar_api():
    # Uma transação só: o BI nunca vê monitoramento novo com tramitações velhas.
    with get_connection() as conn:
        with conn.cursor() as cur:
            atualizar_cache(cur)
        conn.commit()
    print(f"Schema api atualizado: {len(MATERIALIZADAS)} materialized views.")


if __name__ == "__main__":
    atualizar_api()
