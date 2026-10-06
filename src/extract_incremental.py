from datetime import date, timedelta

from tqdm import tqdm

import api_client as api
from db import get_connection
from load_bronze import carregar_proposicao_bronze
from load_dim_deputado import carregar_dim_deputado
from load_dim_orgao import carregar_dim_orgao
from load_eventos import executar_carga_eventos
from load_silver import executar_transformacao_silver

TEMAS = [64, 48]
JANELA_SEGURANCA_DIAS = 3
EVENTOS_DIAS_PASSADO = 7
EVENTOS_DIAS_FUTURO = 14


def calcular_janela(conn):
    """Define [data_inicio, data_fim] da carga incremental.

    data_inicio = min(hoje - 3, data_fim do último run bem-sucedido - 3).
    Se rodou no dia anterior, equivale a D-3 fixo. Se ficou N dias sem rodar
    (máquina desligada, falha), a janela se alarga sozinha para cobrir o
    período inteiro perdido, sem depender de intervenção manual.
    """
    hoje = date.today()
    limite_padrao = hoje - timedelta(days=JANELA_SEGURANCA_DIAS)

    with conn.cursor() as cur:
        cur.execute(
            "SELECT max(data_fim_janela) FROM bronze.controle_execucao WHERE tipo_carga = 'incremental';"
        )
        ultima_data_fim = cur.fetchone()[0]

    if ultima_data_fim is None:
        data_inicio = limite_padrao
    else:
        data_inicio = min(limite_padrao, ultima_data_fim - timedelta(days=JANELA_SEGURANCA_DIAS))

    return data_inicio, hoje


def coletar_ids_unicos(data_inicio, data_fim):
    ids_vistos = set()
    ids_ordenados = []
    for cod_tema in TEMAS:
        print(f"Listando proposições do tema {cod_tema} entre {data_inicio} e {data_fim}...")
        proposicoes = api.listar_proposicoes_por_tema(cod_tema, data_inicio=data_inicio, data_fim=data_fim)
        print(f"  {len(proposicoes)} proposições encontradas no tema {cod_tema}")
        for prop in proposicoes:
            id_prop = prop["id"]
            if id_prop not in ids_vistos:
                ids_vistos.add(id_prop)
                ids_ordenados.append(id_prop)
    return ids_ordenados


def registrar_execucao(conn, tipo_carga, data_inicio, data_fim, qtd):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO bronze.controle_execucao (tipo_carga, data_inicio_janela, data_fim_janela, qtd_proposicoes)
            VALUES (%s, %s, %s, %s);
            """,
            (tipo_carga, data_inicio, data_fim, qtd),
        )
    conn.commit()


def executar_carga_incremental():
    with get_connection() as conn:
        data_inicio, data_fim = calcular_janela(conn)

    ids = coletar_ids_unicos(data_inicio, data_fim)
    print(f"Total de IDs únicos na janela: {len(ids)}")

    ok_count = 0
    erro_count = 0
    with get_connection() as conn:
        for id_prop in tqdm(ids, desc="Carga incremental", unit="proposição"):
            resultado = carregar_proposicao_bronze(conn, id_prop)
            for tabela, status in resultado.items():
                if status == "ok":
                    ok_count += 1
                else:
                    erro_count += 1
                    tqdm.write(f"  ! proposição {id_prop} / {tabela}: {status}")

    print(f"\nCarga incremental (bronze) concluída. Endpoints ok: {ok_count} | com erro: {erro_count}")
    if erro_count:
        raise RuntimeError(f"Carga incremental incompleta: {erro_count} endpoints com erro.")

    print("\nCarregando eventos/pautas...")
    hoje = date.today()
    data_inicio_eventos = hoje - timedelta(days=EVENTOS_DIAS_PASSADO)
    data_fim_eventos = hoje + timedelta(days=EVENTOS_DIAS_FUTURO)
    qtd_eventos = executar_carga_eventos(data_inicio_eventos, data_fim_eventos)
    print("\nAtualizando silver...")
    executar_transformacao_silver()

    print("\nAtualizando dim_deputado...")
    carregar_dim_deputado()

    print("\nAtualizando dim_orgao...")
    carregar_dim_orgao()

    # Só avança a janela após a conclusão de todas as etapas. Os snapshots
    # já gravados na bronze permanecem disponíveis para a próxima tentativa.
    with get_connection() as conn:
        registrar_execucao(conn, "incremental", data_inicio, data_fim, len(ids))
        registrar_execucao(conn, "eventos", data_inicio_eventos, data_fim_eventos, qtd_eventos)


if __name__ == "__main__":
    executar_carga_incremental()
