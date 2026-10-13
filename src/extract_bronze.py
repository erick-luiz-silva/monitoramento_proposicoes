import argparse
from datetime import date, timedelta

from tqdm import tqdm

import api_client as api
from db import get_connection
from load_bronze import carregar_proposicao_bronze

TEMAS = [64, 48]  # Agricultura, Pecuária, Pesca e Extrativismo / Meio Ambiente e Desenvolvimento Sustentável
DESDE_PADRAO = date(2023, 2, 1)
MAX_DIAS_JANELA = 90  # a API só aceita dataInicio/dataFim com até 3 meses de intervalo


def gerar_janelas(desde, ate, max_dias=MAX_DIAS_JANELA):
    """Divide [desde, ate] em janelas contíguas de até max_dias dias (extremos inclusivos)."""
    janelas = []
    inicio = desde
    while inicio <= ate:
        fim = min(inicio + timedelta(days=max_dias - 1), ate)
        janelas.append((inicio, fim))
        inicio = fim + timedelta(days=1)
    return janelas


def coletar_ids_janelas(janelas):
    ids_vistos = set()
    ids_ordenados = []
    for cod_tema in TEMAS:
        for inicio, fim in janelas:
            print(f"Listando proposições do tema {cod_tema} entre {inicio} e {fim}...")
            proposicoes = api.listar_proposicoes_por_tema(cod_tema, data_inicio=inicio, data_fim=fim)
            print(f"  {len(proposicoes)} proposições encontradas")
            for prop in proposicoes:
                id_prop = prop["id"]
                if id_prop not in ids_vistos:
                    ids_vistos.add(id_prop)
                    ids_ordenados.append(id_prop)
    return ids_ordenados


def carregar_ids_existentes(conn):
    """IDs que já têm as 4 cargas gravadas na bronze.

    Um id com carga parcial (ex.: autores falhou) não entra aqui e é recarregado.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id_proposicao FROM bronze.proposicoes_json
            INTERSECT SELECT id_proposicao FROM bronze.autores_json
            INTERSECT SELECT id_proposicao FROM bronze.temas_json
            INTERSECT SELECT id_proposicao FROM bronze.tramitacoes_json;
            """
        )
        return {linha[0] for linha in cur.fetchall()}


def carregar_ids(ids, pular_existentes=False, limit=None):
    """Grava a bronze das proposições dadas. Levanta erro ao final se algum endpoint falhar.

    Não registra nada em bronze.controle_execucao: essas cargas não avançam a janela incremental.
    """
    if pular_existentes:
        with get_connection() as conn:
            existentes = carregar_ids_existentes(conn)
        ids_novos = [id_prop for id_prop in ids if id_prop not in existentes]
        print(f"{len(ids) - len(ids_novos)} já carregados ignorados; {len(ids_novos)} a carregar")
        ids = ids_novos

    if limit is not None:
        ids = ids[:limit]
        print(f"Modo de teste: limitando a {len(ids)} proposições")

    ok_count = 0
    erro_count = 0

    with get_connection() as conn:
        for id_prop in tqdm(ids, desc="Carga bronze", unit="proposição"):
            resultado = carregar_proposicao_bronze(conn, id_prop)
            for tabela, status in resultado.items():
                if status == "ok":
                    ok_count += 1
                else:
                    erro_count += 1
                    tqdm.write(f"  ! proposição {id_prop} / {tabela}: {status}")

    print(f"\nCarga bronze concluída. Endpoints ok: {ok_count} | Endpoints com erro: {erro_count}")
    if erro_count:
        raise RuntimeError(
            f"Carga bronze incompleta: {erro_count} endpoints com erro. "
            "Rode de novo com --pular-existentes para recarregar só o que falhou."
        )


def executar_carga_bronze(desde=DESDE_PADRAO, ate=None, pular_existentes=False, limit=None):
    ate = ate or date.today()
    janelas = gerar_janelas(desde, ate)
    print(f"{len(janelas)} janelas de até {MAX_DIAS_JANELA} dias entre {desde} e {ate}")
    ids = coletar_ids_janelas(janelas)
    print(f"Total de IDs únicos (temas {TEMAS}): {len(ids)}")
    carregar_ids(ids, pular_existentes=pular_existentes, limit=limit)


def executar_reconciliacao(dias):
    """Recarrega proposições novas dos últimos `dias` dias, sem tocar em controle_execucao.

    Cobre a indexação tardia de tema: proposições que recebem o tema depois da
    margem de 3 dias do incremental e nunca mais aparecem na listagem.
    """
    ate = date.today()
    desde = ate - timedelta(days=dias)
    ids = coletar_ids_janelas(gerar_janelas(desde, ate))
    print(f"Total de IDs únicos nos últimos {dias} dias: {len(ids)}")
    carregar_ids(ids, pular_existentes=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Carga histórica da camada bronze")
    parser.add_argument(
        "--desde",
        type=date.fromisoformat,
        default=DESDE_PADRAO,
        help="Data inicial do backfill, AAAA-MM-DD (padrão: 2023-02-01)",
    )
    parser.add_argument(
        "--pular-existentes",
        action="store_true",
        help="Não recarrega proposições que já têm as 4 cargas na bronze (obrigatório em reexecuções)",
    )
    parser.add_argument(
        "--reconciliar",
        type=int,
        metavar="DIAS",
        default=None,
        help="Modo reconciliação: carrega só proposições novas dos últimos DIAS dias",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limita a quantidade de proposições processadas (uso para teste)",
    )
    args = parser.parse_args()
    if args.reconciliar is not None:
        executar_reconciliacao(args.reconciliar)
    else:
        executar_carga_bronze(desde=args.desde, pular_existentes=args.pular_existentes, limit=args.limit)
