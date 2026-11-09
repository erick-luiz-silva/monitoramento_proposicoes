import argparse
from contextlib import ExitStack
from datetime import date, timedelta
import time

import psycopg2
from tqdm import tqdm

import api_client as api
from config import PAUSA_SEGUNDA_PASSAGEM_SEG, TEMAS
from db import get_connection
from load_bronze import (
    STATUS_SUCESSO, ConexaoPerdida, carregar_estado_bronze,
    carregar_proposicao_bronze, houve_erro,
)

DESDE_PADRAO = date(2023, 2, 1)
MAX_DIAS_JANELA = 90  # a API só aceita dataInicio/dataFim com até 3 meses de intervalo
RECONEXAO_ESPERAS = (5, 15, 30, 60, 120)  # segundos antes de cada tentativa de reconectar ao banco
TQDM_MININTERVAL = 30  # segundos entre atualizações da barra; mantém o log do backfill legível


class CargaBronzeIncompleta(RuntimeError):
    """Preserva a contagem final para o chamador informar qual janela falhou."""

    def __init__(self, erro_count):
        self.erro_count = erro_count
        super().__init__(
            f"Carga bronze incompleta: {erro_count} endpoints com erro. "
            "Rode de novo com --pular-existentes para recarregar só o que falhou."
        )


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


def _reconectar(conexao):
    """Abre uma conexão nova em `conexao` (ExitStack), com espera crescente entre tentativas."""
    ultimo_erro = None
    for espera in RECONEXAO_ESPERAS:
        time.sleep(espera)
        try:
            conn = conexao.enter_context(get_connection())
            tqdm.write(f"  reconectado ao banco após {espera}s")
            return conn
        except psycopg2.Error as exc:
            ultimo_erro = exc
            tqdm.write(f"  ! falha ao reconectar ({exc}); nova tentativa")
    raise RuntimeError(
        f"Conexão com o banco perdida e não recuperada após {len(RECONEXAO_ESPERAS)} tentativas "
        f"({ultimo_erro}). Rode de novo com --pular-existentes para continuar de onde parou."
    )


def carregar_ids(
    ids, pular_existentes=False, limit=None, levantar_erro=True, *,
    seletivo=False, ids_autores_gravados=None,
):
    """Grava a bronze das proposições dadas e devolve (ids processados, endpoints com erro).

    Repete os ids com erro uma vez, com carga completa, antes de levantar erro.
    Com seletivo=True, lê o estado anterior uma vez e condiciona autores/temas.
    ids_autores_gravados recebe os ids que gravaram autores em alguma passagem.
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

    resultados = {}
    with ExitStack() as conexao:
        conn = conexao.enter_context(get_connection())
        estado = carregar_estado_bronze(conn, ids) if seletivo else None

        def carregar(id_prop, estado_atual):
            nonlocal conn
            if conn is None:
                # Falha ao reconectar levanta: banco fora do ar derruba a carga na hora,
                # em vez de repetir o backoff inteiro em cada id restante.
                conn = _reconectar(conexao)
            try:
                return carregar_proposicao_bronze(conn, id_prop, estado=estado_atual)
            except (ConexaoPerdida, psycopg2.OperationalError, psycopg2.InterfaceError) as exc:
                tqdm.write(f"  ! conexão perdida na proposição {id_prop}: {exc}")
                conexao.close()
                conn = _reconectar(conexao)
                try:
                    return carregar_proposicao_bronze(conn, id_prop, estado=estado_atual)
                except (ConexaoPerdida, psycopg2.OperationalError, psycopg2.InterfaceError) as exc_retry:
                    conexao.close()
                    conn = None
                    return {"conexao": f"erro: {exc_retry}"}

        autores_gravados = set()

        def registrar_resultado(id_prop, resultado):
            resultados[id_prop] = resultado
            # Acumula já na hora e em qualquer passagem: autores gravados na 1ª continuam
            # valendo para o dim_deputado, mesmo se a 2ª falhar ou a carga levantar depois.
            if (ids_autores_gravados is not None and resultado.get("autores_json") == "ok"
                    and id_prop not in autores_gravados):
                autores_gravados.add(id_prop)
                ids_autores_gravados.append(id_prop)
            for tabela, status in resultado.items():
                if status not in STATUS_SUCESSO:
                    tqdm.write(f"  ! proposição {id_prop} / {tabela}: {status}")

        falhos = []
        for id_prop in tqdm(ids, desc="Carga bronze", unit="proposição", mininterval=TQDM_MININTERVAL):
            resultado = carregar(id_prop, estado)
            registrar_resultado(id_prop, resultado)
            if houve_erro(resultado):
                falhos.append(id_prop)

        if falhos:
            print(f"{len(falhos)} proposições falharam na 1ª passagem; repetindo após "
                  f"{PAUSA_SEGUNDA_PASSAGEM_SEG}s...")
            time.sleep(PAUSA_SEGUNDA_PASSAGEM_SEG)
            recuperados = 0
            for id_prop in falhos:
                resultado = carregar(id_prop, None)
                registrar_resultado(id_prop, resultado)
                recuperados += not houve_erro(resultado)
            print(f"2ª passagem: {recuperados} de {len(falhos)} proposições recuperadas")

    status_finais = [status for resultado in resultados.values() for status in resultado.values()]
    ok_count = status_finais.count("ok")
    pulado_count = status_finais.count("pulado")
    erro_count = sum(status not in STATUS_SUCESSO for status in status_finais)
    print(f"\nCarga bronze concluída. Endpoints ok: {ok_count} | pulado: {pulado_count} | "
          f"Endpoints com erro: {erro_count}")
    if erro_count and levantar_erro:
        raise CargaBronzeIncompleta(erro_count)
    return ids, erro_count


def listar_ids_novos(ids):
    """Imprime e devolve os ids que ainda não têm as 4 cargas na bronze (modo --so-listar)."""
    with get_connection() as conn:
        existentes = carregar_ids_existentes(conn)
    novos = [id_prop for id_prop in ids if id_prop not in existentes]
    print(f"IDs únicos listados: {len(ids)} | já na bronze: {len(ids) - len(novos)} | novos: {len(novos)}")
    return novos


def executar_carga_bronze(desde=DESDE_PADRAO, ate=None, pular_existentes=False, limit=None, so_listar=False):
    ate = ate or date.today()
    janelas = gerar_janelas(desde, ate)
    print(f"{len(janelas)} janelas de até {MAX_DIAS_JANELA} dias entre {desde} e {ate}")
    ids = coletar_ids_janelas(janelas)
    print(f"Total de IDs únicos (temas {TEMAS}): {len(ids)}")
    if so_listar:
        listar_ids_novos(ids)
        return
    carregar_ids(ids, pular_existentes=pular_existentes, limit=limit)


def executar_reconciliacao(dias, levantar_erro=True, ignorar=(), *, ids_autores_gravados=None):
    """Carrega os ids listados nos últimos `dias` dias que ainda não estão na bronze.

    Cobre a indexação tardia de tema: a Câmara atribui o tema de 1 a 2 semanas
    depois da apresentação, quando a proposição já saiu da janela do incremental.
    Não toca em controle_execucao.

    `ignorar`: ids já recarregados neste run (ex.: pela janela do incremental).
    Devolve (desde, ate, ids carregados, endpoints com erro).
    """
    ate = date.today()
    desde = ate - timedelta(days=dias)
    ignorar = set(ignorar)
    ids = [id_prop for id_prop in coletar_ids_janelas(gerar_janelas(desde, ate)) if id_prop not in ignorar]
    with get_connection() as conn:
        existentes = carregar_ids_existentes(conn)
    ausentes = [id_prop for id_prop in ids if id_prop not in existentes]
    print(f"Reconciliação de {dias} dias: {len(ids)} ids listados, {len(ausentes)} ausentes da bronze")
    carregados, erros = carregar_ids(
        ausentes, levantar_erro=levantar_erro, ids_autores_gravados=ids_autores_gravados
    )
    return desde, ate, carregados, erros


def main(argv=None):
    parser = argparse.ArgumentParser(description="Carga histórica da camada bronze")
    parser.add_argument(
        "--desde",
        type=date.fromisoformat,
        default=DESDE_PADRAO,
        help="Data inicial do backfill, AAAA-MM-DD (padrão: 2023-02-01)",
    )
    parser.add_argument(
        "--ate",
        type=date.fromisoformat,
        default=None,
        help="Data final do backfill, AAAA-MM-DD (padrão: hoje)",
    )
    parser.add_argument(
        "--ids",
        type=lambda texto: [int(parte) for parte in texto.split(",") if parte.strip()],
        default=None,
        metavar="ID,ID,...",
        help="Carrega só estas proposições (ignora --desde/--ate)",
    )
    parser.add_argument(
        "--so-listar",
        action="store_true",
        help="Só lista: imprime quantos ids únicos ainda não estão na bronze e sai",
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
        "--pausa",
        type=float,
        default=None,
        metavar="SEG",
        help=f"Pausa entre chamadas à API, em segundos (padrão: {api.SLEEP_BETWEEN_CALLS})",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limita a quantidade de proposições processadas (uso para teste)",
    )
    args = parser.parse_args(argv)
    if args.pausa is not None:
        api.SLEEP_BETWEEN_CALLS = args.pausa  # lido a cada chamada por api_client e load_bronze
    if args.reconciliar is not None:
        executar_reconciliacao(args.reconciliar)
    elif args.ids is not None:
        if args.so_listar:
            listar_ids_novos(args.ids)
        else:
            carregar_ids(args.ids, pular_existentes=args.pular_existentes, limit=args.limit)
    else:
        executar_carga_bronze(
            desde=args.desde,
            ate=args.ate,
            pular_existentes=args.pular_existentes,
            limit=args.limit,
            so_listar=args.so_listar,
        )


if __name__ == "__main__":
    main()
