"""Carga do Senado Federal (docs/superpowers/plans/2026-10-28-senado-fases-3-4.md).

Roda depois da Câmara, isolada dela: qualquer exceção daqui vira aviso no e-mail e nunca
derruba a carga da Câmara (o orquestrador em extract_incremental/pipeline_pautas trata).
Erro em processo da janela é bloqueante (não avança incremental_senado) e vira "Senado não
atualizado"; erro em acompanhada, gêmeo, mapa, reconciliação ou senador não trava a janela e
vira SenadoComPendencias ("Senado atualizado com pendências").
"""

import argparse
import time
from datetime import date, timedelta

import api_client_senado as api
from config import (
    CLASSES_SENADO,
    SENADO_JANELA_DIAS,
    SENADO_OFFSET,
    SENADO_PRAZO_MIN,
    SENADO_RECONCILIACAO_DIAS,
)
from db import get_connection
from load_bronze_senado import carregar_processo, gravar_mapa
from load_dim_senador import carregar_dim_senador
from load_silver import executar_transformacao_senado

# Unicidade das linhas do Senado na gold, conferida antes do commit da transformação: uma
# duplicata faria o REFRESH CONCURRENTLY do api falhar e congelaria também a Câmara.
SQL_DUPLICADAS_SENADO = """
    SELECT id_proposicao FROM gold.vw_monitoramento
    WHERE id_proposicao >= 1000000000 GROUP BY 1 HAVING count(*) > 1;
"""
_SQL_ULTIMA_JANELA = "SELECT max(data_fim_janela) FROM bronze.controle_execucao WHERE tipo_carga = 'incremental_senado';"
_SQL_REGISTRAR = """
    INSERT INTO bronze.controle_execucao (tipo_carga, data_inicio_janela, data_fim_janela, qtd_proposicoes)
    VALUES (%s, %s, %s, %s);
"""
_SQL_SF_DA_GOLD = "SELECT id_proposicao - 1000000000 FROM gold.vw_monitoramento WHERE id_proposicao >= 1000000000;"


class SenadoComPendencias(RuntimeError):
    """O Senado foi atualizado, mas algo não bloqueante falhou (vira aviso, não "não atualizado")."""


def registrar_execucao(conn, tipo_carga, data_inicio, data_fim, qtd):
    with conn.cursor() as cur:
        cur.execute(_SQL_REGISTRAR, (tipo_carga, data_inicio, data_fim, qtd))
    conn.commit()


def calcular_numdias(conn, hoje):
    """(numdias, recarga_total). numdias = dias desde o último sucesso + 14, até 30 (limite
    da API). Com mais de 16 dias de buraco, recarrega tudo o que o Senado tem na gold."""
    with conn.cursor() as cur:
        cur.execute(_SQL_ULTIMA_JANELA)
        ultimo = cur.fetchone()[0]
    if ultimo is None:
        return 30, False
    dias = (hoje - ultimo).days
    return min(30, dias + SENADO_JANELA_DIAS), dias > 16


def _ids(processos):
    return [int(p["id"]) for p in processos if p.get("id") is not None]


def _sem_repetir(ids):
    return list(dict.fromkeys(ids))


def coletar_candidatos(numdias):
    """Processos atualizados na janela: classes (com os filhos) e todas as MPVs."""
    ids = []
    for classe in api.expandir_classes(CLASSES_SENADO):
        ids += _ids(api.listar_processos(numdias=numdias, codigo_classe=classe))
    ids += _ids(api.listar_processos(numdias=numdias, sigla="MPV"))
    return _sem_repetir(ids)


def carregar_acompanhadas_sf(conn):
    from extract_incremental import carregar_ids_acompanhadas  # import tardio: extract_incremental importa este módulo

    return [id_prop - SENADO_OFFSET for id_prop in carregar_ids_acompanhadas(conn, casa="SF")]


def ids_reconciliacao(conn, hoje):
    """Apresentados nos últimos 90 dias (classes e MPVs) ainda ausentes da bronze: a classe
    pode ser atribuída depois da apresentação."""
    desde = hoje - timedelta(days=SENADO_RECONCILIACAO_DIAS)
    ids = []
    for classe in api.expandir_classes(CLASSES_SENADO):
        ids += _ids(api.listar_processos(codigo_classe=classe, data_inicio=desde, data_fim=hoje))
    ids += _ids(api.listar_processos(sigla="MPV", data_inicio=desde, data_fim=hoje))
    ids = _sem_repetir(ids)
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT id_processo FROM bronze.sf_processo_json WHERE id_processo = ANY(%s);", (ids,))
        existentes = {linha[0] for linha in cur.fetchall()}
    return [i for i in ids if i not in existentes]


def atualizar_mapa_revisora(conn, completo, numdias=None):
    """Mapa dos processos "Revisora" (números da Câmara). Ver Tarefa 4.1."""
    return 0


def ids_gemeos(conn):
    """Processos do Senado gêmeos de proposições monitoradas da Câmara. Ver Tarefa 4.2."""
    return []


def _carregar(conn, ids, prazo_fim):
    """Carrega a bronze de cada id. Devolve a lista de (id, erro). Prazo estourado levanta."""
    erros = []
    for id_processo in ids:
        if time.monotonic() > prazo_fim:
            raise TimeoutError(f"carga do Senado passou de {SENADO_PRAZO_MIN} min")
        resultado = carregar_processo(conn, id_processo)
        if resultado.startswith("erro"):
            erros.append((id_processo, resultado))
    return erros


def transformar_com_unicidade():
    """Transforma a silver do Senado numa transação e só faz commit se a gold continuar com
    uma linha por id do Senado. Duplicata ou erro: desfaz tudo e levanta."""
    with get_connection() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute("SET LOCAL lock_timeout = '30s';")
                cur.execute("SET LOCAL statement_timeout = '10min';")
                executar_transformacao_senado(cur)
                cur.execute(SQL_DUPLICADAS_SENADO)
                duplicadas = [linha[0] for linha in cur.fetchall()]
            if duplicadas:
                raise RuntimeError(
                    "ids do Senado duplicados na gold, transformação desfeita: " + ", ".join(map(str, duplicadas[:5]))
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def executar_carga_senado():
    inicio = time.monotonic()
    prazo_fim = inicio + SENADO_PRAZO_MIN * 60
    hoje = date.today()
    pendencias = []

    with get_connection() as conn:
        numdias, recarga_total = calcular_numdias(conn, hoje)
        acompanhadas = carregar_acompanhadas_sf(conn)
    candidatos = coletar_candidatos(numdias)  # erro aqui é bloqueante: levanta
    print(f"Senado: {len(candidatos)} processos na janela de {numdias} dias, {len(acompanhadas)} acompanhadas")

    extras = list(acompanhadas)
    try:
        with get_connection() as conn:
            atualizar_mapa_revisora(conn, completo=False, numdias=numdias)
            extras += ids_gemeos(conn)
    except Exception as exc:
        pendencias.append(f"mapa/gêmeos: {exc}")
    if recarga_total:
        with get_connection() as conn, conn.cursor() as cur:
            cur.execute(_SQL_SF_DA_GOLD)
            extras += [linha[0] for linha in cur.fetchall()]
    try:
        with get_connection() as conn:
            reconciliacao = ids_reconciliacao(conn, hoje)
        reconciliacao_ok = True
    except Exception as exc:
        reconciliacao, reconciliacao_ok = [], False
        pendencias.append(f"reconciliação: {exc}")

    na_janela = set(candidatos)
    extras = [i for i in _sem_repetir(extras) if i not in na_janela]
    reconciliacao = [i for i in reconciliacao if i not in na_janela and i not in set(extras)]
    with get_connection() as conn:
        erros_janela = _carregar(conn, candidatos, prazo_fim)
        erros_extras = _carregar(conn, extras, prazo_fim)
        erros_reconciliacao = _carregar(conn, reconciliacao, prazo_fim)
    if erros_extras:
        pendencias.append(f"{len(erros_extras)} acompanhadas/gêmeos com erro (ex.: {erros_extras[0][0]}: {erros_extras[0][1]})")
    if erros_reconciliacao:
        reconciliacao_ok = False
        pendencias.append(f"{len(erros_reconciliacao)} processos da reconciliação com erro")

    transformar_com_unicidade()
    try:
        carregar_dim_senador()
    except Exception as exc:
        pendencias.append(f"senadores: {exc}")

    with get_connection() as conn:
        if not erros_janela:
            registrar_execucao(conn, "incremental_senado", hoje - timedelta(days=numdias), hoje, len(candidatos))
        if reconciliacao_ok:
            registrar_execucao(conn, "reconciliacao_senado", hoje - timedelta(days=SENADO_RECONCILIACAO_DIAS), hoje,
                               len(reconciliacao))
    print(f"Senado concluído em {time.monotonic() - inicio:.0f} s")

    if erros_janela:
        raise RuntimeError(f"{len(erros_janela)} processos da janela com erro (ex.: {erros_janela[0][0]}: {erros_janela[0][1]})")
    if pendencias:
        raise SenadoComPendencias("; ".join(pendencias))


def executar_pautas_senado():
    print("Senado: carga de pautas ainda não habilitada.")
