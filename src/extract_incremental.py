from datetime import date, timedelta

from tqdm import tqdm

import api_client as api
from config import TEMAS
from db import get_connection
from extract_bronze import executar_reconciliacao
from load_bronze import carregar_proposicao_bronze
from load_dim_deputado import carregar_dim_deputado
from load_dim_orgao import carregar_dim_orgao
from load_eventos import executar_carga_eventos
from load_silver import executar_transformacao_silver

JANELA_SEGURANCA_DIAS = 14
RECONCILIACAO_DIAS = 90
RECONCILIACAO_LONGA_DIAS = 365
RECONCILIACAO_LONGA_INTERVALO_DIAS = 7
EVENTOS_DIAS_PASSADO = 7
EVENTOS_DIAS_FUTURO = 14


def calcular_janela(conn):
    """Define [data_inicio, data_fim] da carga incremental.

    data_inicio = min(hoje - 14, data_fim do último run bem-sucedido - 14).
    Se rodou no dia anterior, equivale a D-14 fixo. Se ficou N dias sem rodar
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


def reconciliacao_longa_pendente(conn):
    """A de 365 dias roda quando a última bem-sucedida tem 7 dias ou mais (ou nunca rodou).

    Por idade, não por dia da semana: se um run falhar, o seguinte compensa.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT max(data_fim_janela) FROM bronze.controle_execucao WHERE tipo_carga = 'reconciliacao_365';"
        )
        ultima = cur.fetchone()[0]
    return ultima is None or ultima <= date.today() - timedelta(days=RECONCILIACAO_LONGA_INTERVALO_DIAS)


def executar_reconciliacoes(longa, ids_ja_carregados):
    """Roda a reconciliação (365 dias se `longa`, senão 90) sem levantar erro.

    Devolve (tipos de carga a registrar, ids carregados, descrição do erro ou None).
    A de 365 cobre a de 90, então quando roda registra as duas.
    """
    dias = RECONCILIACAO_LONGA_DIAS if longa else RECONCILIACAO_DIAS
    print(f"\nReconciliação dos últimos {dias} dias (ausentes da bronze e sem keywords)...")
    try:
        desde, ate, ids, erros = executar_reconciliacao(
            dias, levantar_erro=False, ignorar=ids_ja_carregados
        )
    except Exception as exc:
        print(f"  ! reconciliação falhou: {exc}")
        return [], [], f"reconciliação de {dias} dias falhou: {exc}"
    if erros:
        return [], ids, f"reconciliação de {dias} dias incompleta: {erros} endpoints com erro"
    tipos = ["reconciliacao", "reconciliacao_365"] if longa else ["reconciliacao"]
    return [(tipo, desde, ate, len(ids)) for tipo in tipos], ids, None


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
    """Bronze D-14, reconciliação, eventos, silver e dims; depois registra as janelas.

    Falha na D-14, nos eventos, na silver ou nas dims: levanta erro sem registrar nada.
    Falha na reconciliação: o resto segue e `incremental`/`eventos` são registrados
    (um id com erro crônico não pode travar a janela), mas `reconciliacao` não é,
    e o run levanta erro no fim para o job aparecer como falho.
    """
    with get_connection() as conn:
        data_inicio, data_fim = calcular_janela(conn)
        longa = reconciliacao_longa_pendente(conn)

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

    reconciliacoes, ids_reconciliados, erro_reconciliacao = executar_reconciliacoes(longa, ids)

    print("\nCarregando eventos/pautas...")
    hoje = date.today()
    data_inicio_eventos = hoje - timedelta(days=EVENTOS_DIAS_PASSADO)
    data_fim_eventos = hoje + timedelta(days=EVENTOS_DIAS_FUTURO)
    qtd_eventos = executar_carga_eventos(data_inicio_eventos, data_fim_eventos)
    print("\nAtualizando silver...")
    executar_transformacao_silver()

    print("\nAtualizando dim_deputado...")
    carregar_dim_deputado(seletivo=True, ids_proposicao=list(ids) + list(ids_reconciliados))

    print("\nAtualizando dim_orgao...")
    carregar_dim_orgao()

    # Só avança a janela após a conclusão de todas as etapas. Os snapshots
    # já gravados na bronze permanecem disponíveis para a próxima tentativa.
    with get_connection() as conn:
        registrar_execucao(conn, "incremental", data_inicio, data_fim, len(ids))
        registrar_execucao(conn, "eventos", data_inicio_eventos, data_fim_eventos, qtd_eventos)
        for tipo, desde, ate, qtd in reconciliacoes:
            registrar_execucao(conn, tipo, desde, ate, qtd)

    if erro_reconciliacao:
        raise RuntimeError(erro_reconciliacao.capitalize() + "; janela incremental registrada, reconciliação não.")


if __name__ == "__main__":
    executar_carga_incremental()
