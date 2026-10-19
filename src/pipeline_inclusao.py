"""Carga sob demanda das proposições incluídas manualmente pela planilha.

Disparado pelo n8n (modo=inclusao) depois que uma linha nova da aba "Proposições"
é resolvida e gravada em silver.proposicao_acompanhada. Carrega na bronze só as
acompanhadas ainda ausentes, atualiza a silver e as dimensões. Não registra nada
em controle_execucao: a janela incremental continua sendo da carga diária.
"""

from db import get_connection
from extract_bronze import carregar_ids, carregar_ids_existentes
from extract_incremental import carregar_ids_acompanhadas
from load_api import atualizar_api
from load_dim_deputado import carregar_dim_deputado
from load_dim_orgao import carregar_dim_orgao
from load_silver import executar_transformacao_silver


def executar_pipeline_inclusao():
    with get_connection() as conn:
        acompanhadas = carregar_ids_acompanhadas(conn)
        existentes = carregar_ids_existentes(conn)
    ausentes = [id_prop for id_prop in acompanhadas if id_prop not in existentes]
    print(f"{len(acompanhadas)} proposições acompanhadas; {len(ausentes)} ainda fora da bronze")

    # Sem levantar erro por id: um id inválido (que continuaria ausente) não pode
    # bloquear as inclusões seguintes. Só falha se nenhuma das ausentes chegou à bronze
    # (conferido no banco, o que também cobre queda de conexão no meio da carga).
    carregados, erros = carregar_ids(ausentes, levantar_erro=False)
    if ausentes:
        with get_connection() as conn:
            existentes = carregar_ids_existentes(conn)
        if not any(id_prop in existentes for id_prop in ausentes):
            raise RuntimeError("Nenhuma proposição incluída pôde ser carregada.")
    executar_transformacao_silver()
    carregar_dim_deputado(seletivo=True, ids_proposicao=carregados)
    carregar_dim_orgao()
    atualizar_api()
    print(f"Inclusão concluída: {len(carregados)} proposições processadas, {erros} endpoints com erro.")


if __name__ == "__main__":
    executar_pipeline_inclusao()
