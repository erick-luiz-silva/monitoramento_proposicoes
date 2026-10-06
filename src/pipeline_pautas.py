"""Atualização intradiária de eventos e pautas usados pela Gold."""

from datetime import date, timedelta

from db import get_connection
from extract_incremental import (
    EVENTOS_DIAS_PASSADO,
    EVENTOS_DIAS_FUTURO,
    registrar_execucao,
)
from load_dim_deputado import carregar_dim_deputado
from load_dim_orgao import carregar_dim_orgao
from load_eventos import executar_carga_eventos
from load_silver import executar_transformacao_eventos


def executar_pipeline_pautas():
    hoje = date.today()
    inicio = hoje - timedelta(days=EVENTOS_DIAS_PASSADO)
    fim = hoje + timedelta(days=EVENTOS_DIAS_FUTURO)
    qtd = executar_carga_eventos(inicio, fim)
    executar_transformacao_eventos()
    carregar_dim_deputado(somente_relatores=True)
    carregar_dim_orgao()
    # O controle das proposições fica reservado à carga completa diária.
    with get_connection() as conn:
        registrar_execucao(conn, "eventos", inicio, fim, qtd)
    print(f"Atualização de pautas concluída: {qtd} eventos entre {inicio} e {fim}.")


if __name__ == "__main__":
    executar_pipeline_pautas()
