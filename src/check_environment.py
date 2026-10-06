"""Verificação somente de leitura antes da carga automatizada."""

from db import get_connection

REQUIRED_RELATIONS = (
    "bronze.proposicoes_json",
    "bronze.autores_json",
    "bronze.temas_json",
    "bronze.tramitacoes_json",
    "bronze.eventos_json",
    "bronze.eventos_pauta_json",
    "bronze.controle_execucao",
    "silver.proposicao",
    "silver.proposicoes_proponentes",
    "silver.proposicao_tema",
    "silver.tramitacao",
    "silver.evento",
    "silver.evento_pauta",
    "silver.dim_deputado",
    "silver.dim_orgao",
    "silver.dim_keyword",
    "gold.vw_monitoramento",
    "gold.vw_tramitacoes",
    "gold.vw_proposicoes_sem_keyword",
    "gold.vw_pautas_monitoradas",
    "gold.vw_audiencias_de_interesse",
)


def check_environment():
    with get_connection() as conn:
        with conn.cursor() as cur:
            missing = []
            for relation in REQUIRED_RELATIONS:
                cur.execute("SELECT to_regclass(%s);", (relation,))
                if cur.fetchone()[0] is None:
                    missing.append(relation)
            if missing:
                raise RuntimeError(
                    "Banco não inicializado. Relações ausentes: " + ", ".join(missing)
                    + ". Execute setup_db.py separadamente antes de ativar o pipeline."
                )
            cur.execute("SELECT count(*) FROM silver.dim_keyword WHERE ativo;")
            if cur.fetchone()[0] == 0:
                raise RuntimeError(
                    "Nenhuma keyword ativa. Configure a dimensão antes de ativar o pipeline."
                )
    print("Conexão, schemas e keywords verificados com sucesso.")


if __name__ == "__main__":
    check_environment()
