"""Verificação somente de leitura antes da carga automatizada."""

from config import SENADO_OFFSET
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
    "silver.proposicao_acompanhada",
    "silver.proposicao_vinculo",
    "gold.vw_grupo_projeto",
    "gold.vw_monitoramento",
    "gold.vw_tramitacoes",
    "gold.vw_proposicoes_sem_keyword",
    "gold.vw_pautas_monitoradas",
    "gold.vw_audiencias_de_interesse",
    "gold.vw_movimentacoes",
    "api.vw_monitoramento",
    "api.vw_proposicao_keywords",
    "api.vw_proposicoes_sem_keyword",
    "api.vw_tramitacoes",
    "api.vw_pautas_monitoradas",
    "api.vw_audiencias_de_interesse",
)

# Uma linha por id_proposicao na gold: duplicata faria o REFRESH CONCURRENTLY falhar e
# congelaria o api inteiro. Consulta a gold (o cache tem índice único e nunca teria
# duplicata); custa 2–4 s com o papel do pipeline, sem o timeout da anon.
# ORDER BY: ids da Câmara (menores) vêm primeiro, então duplicatas do Senado não escondem uma da Câmara.
SQL_DUPLICADAS = "SELECT id_proposicao FROM gold.vw_monitoramento GROUP BY 1 HAVING count(*) > 1 ORDER BY 1 LIMIT 5"


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
            cur.execute(SQL_DUPLICADAS)
            duplicadas = [linha[0] for linha in cur.fetchall()]
            da_camara = [id_prop for id_prop in duplicadas if id_prop < SENADO_OFFSET]
            if da_camara:
                raise RuntimeError(
                    "ids duplicados em gold.vw_monitoramento: " + ", ".join(map(str, da_camara))
                )
            if duplicadas:
                # Só do Senado: não bloqueia a carga da Câmara aqui, mas o REFRESH CONCURRENTLY do
                # api ainda falharia no fim. A carga do Senado (fase 3) garante a unicidade antes do refresh.
                print("::warning::ids do Senado duplicados na gold: " + ", ".join(map(str, duplicadas)))
    print("Conexão, schemas e keywords verificados com sucesso.")


if __name__ == "__main__":
    check_environment()
