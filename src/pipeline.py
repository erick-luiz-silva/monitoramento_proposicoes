import logging
import sys
import time
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "pipeline.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("pipeline")

from db import get_connection  # noqa: E402
from extract_incremental import executar_carga_incremental  # noqa: E402

GOLD_CONTAGENS = [
    ("api.vw_monitoramento", "SELECT count(*) FROM api.vw_monitoramento;"),
    ("api.vw_tramitacoes", "SELECT count(*) FROM api.vw_tramitacoes;"),
    ("api.vw_proposicoes_sem_keyword", "SELECT count(*) FROM api.vw_proposicoes_sem_keyword;"),
]


def resumo_gold():
    """Gold é só views — não há carga aqui. Conta o schema api (cópia materializada da
    gold, já atualizada pela carga), que é o que o Power BI lê e sai barato."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            for nome, query in GOLD_CONTAGENS:
                cur.execute(query)
                logger.info("%s: %s linhas", nome, cur.fetchone()[0])


def main():
    inicio = time.monotonic()
    logger.info("=== Pipeline diário iniciado (bronze incremental -> silver -> dim_deputado -> gold/api) ===")
    try:
        executar_carga_incremental()
        resumo_gold()
    except Exception:
        logger.exception("Pipeline falhou")
        sys.exit(1)

    duracao = time.monotonic() - inicio
    logger.info("=== Pipeline concluído com sucesso em %.1fs ===", duracao)


if __name__ == "__main__":
    main()