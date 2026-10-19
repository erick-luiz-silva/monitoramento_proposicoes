from datetime import date, timedelta

from tqdm import tqdm

import api_client as api
from config import TEMAS
from db import get_connection
from extract_bronze import carregar_ids, executar_reconciliacao
from load_bronze import carregar_proposicao_bronze
from load_api import atualizar_api
from load_dim_deputado import carregar_dim_deputado
from load_dim_orgao import carregar_dim_orgao
from load_eventos import executar_carga_eventos
from load_silver import executar_transformacao_silver

JANELA_SEGURANCA_DIAS = 14
RECONCILIACAO_DIAS = 90
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


def carregar_ids_acompanhadas(conn):
    """Ids de silver.proposicao_acompanhada (planilha antiga e inclusões manuais).

    São recarregados todo dia, mesmo fora dos temas e sem tramitação recente,
    para que qualquer movimentação delas chegue ao alerta.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT id_proposicao FROM silver.proposicao_acompanhada ORDER BY id_proposicao;")
        return [linha[0] for linha in cur.fetchall()]


def executar_reconciliacao_diaria(ids_ja_carregados):
    """Roda a reconciliação de 90 dias sem levantar erro.

    Devolve (registro a gravar ou None, ids carregados, descrição do erro ou None).
    """
    print(f"\nReconciliação dos últimos {RECONCILIACAO_DIAS} dias (ausentes da bronze)...")
    try:
        desde, ate, ids, erros = executar_reconciliacao(
            RECONCILIACAO_DIAS, levantar_erro=False, ignorar=ids_ja_carregados
        )
    except Exception as exc:
        print(f"  ! reconciliação falhou: {exc}")
        return None, [], f"reconciliação falhou: {exc}"
    if erros:
        return None, ids, f"reconciliação incompleta: {erros} endpoints com erro"
    return ("reconciliacao", desde, ate, len(ids)), ids, None


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
    """Bronze D-14 + acompanhadas, reconciliação, eventos, silver e dims; depois registra as janelas.

    Falha na D-14, nos eventos, na silver ou nas dims: levanta erro sem registrar nada.
    Falha nas acompanhadas ou na reconciliação: o resto segue e `incremental`/`eventos`
    são registrados (um id com erro crônico não pode travar a janela), `reconciliacao`
    só é registrada se ela completou, e o run levanta erro no fim para o job falhar.
    """
    with get_connection() as conn:
        data_inicio, data_fim = calcular_janela(conn)
        acompanhadas = carregar_ids_acompanhadas(conn)

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

    # Acompanhadas fora da janela: carregadas à parte e sem levantar erro, como a
    # reconciliação — um id ruim (ex.: inclusão manual inválida) não pode travar a janela.
    na_janela = set(ids)
    extras = [id_prop for id_prop in acompanhadas if id_prop not in na_janela]
    print(f"\nRecarregando {len(extras)} proposições acompanhadas fora da janela...")
    try:
        ids_extras, erros_extras = carregar_ids(extras, levantar_erro=False)
        erro_acompanhadas = f"acompanhadas: {erros_extras} endpoints com erro" if erros_extras else None
    except Exception as exc:
        ids_extras, erro_acompanhadas = [], f"acompanhadas falharam: {exc}"

    reconciliacao, ids_reconciliados, erro_reconciliacao = executar_reconciliacao_diaria(ids + ids_extras)

    print("\nCarregando eventos/pautas...")
    hoje = date.today()
    data_inicio_eventos = hoje - timedelta(days=EVENTOS_DIAS_PASSADO)
    data_fim_eventos = hoje + timedelta(days=EVENTOS_DIAS_FUTURO)
    qtd_eventos = executar_carga_eventos(data_inicio_eventos, data_fim_eventos)
    print("\nAtualizando silver...")
    executar_transformacao_silver()

    print("\nAtualizando dim_deputado...")
    carregar_dim_deputado(seletivo=True, ids_proposicao=list(ids) + list(ids_extras) + list(ids_reconciliados))

    print("\nAtualizando dim_orgao...")
    carregar_dim_orgao()

    # Só avança a janela após a conclusão de todas as etapas. Os snapshots
    # já gravados na bronze permanecem disponíveis para a próxima tentativa.
    with get_connection() as conn:
        registrar_execucao(conn, "incremental", data_inicio, data_fim, len(ids))
        registrar_execucao(conn, "eventos", data_inicio_eventos, data_fim_eventos, qtd_eventos)
        if reconciliacao:
            registrar_execucao(conn, *reconciliacao)

    erros = [erro for erro in (erro_acompanhadas, erro_reconciliacao) if erro]

    # Depois das janelas: é derivado (o próximo run recalcula) e não pode travar o
    # incremental, mas roda mesmo quando acompanhadas/reconciliação falharam.
    print("\nAtualizando schema api (Power BI)...")
    try:
        atualizar_api()
    except Exception as exc:
        erros.append(f"atualização do schema api falhou: {exc}")

    if erros:
        raise RuntimeError("; ".join(erros) + " (janela incremental registrada; reconciliação só se completa).")


if __name__ == "__main__":
    executar_carga_incremental()
