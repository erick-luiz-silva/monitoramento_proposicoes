"""Cliente da API de Dados Abertos do Senado (família /processo; ver o estudo do Senado).

Ritmo de no máximo 5 req/s e retry com espera crescente em 429/5xx (a API devolve 503
intermitente). Endpoints legados (senador, agenda) devolvem lista de 1 item como objeto:
use como_lista. TLS 1.2 forçado só com SENADO_TLS12=1 (o TLS 1.3 trava no WSL local;
no runner do Actions não precisa).
"""

import os
import ssl
import time

import requests
from requests.adapters import HTTPAdapter

from config import SENADO_API_BASE

TIMEOUT = (15, 120)
INTERVALO_MIN = 0.2  # segundos entre chamadas (≤ 5 req/s)
ESPERAS = (2, 4, 8)  # entre tentativas; MAX_TENTATIVAS = len(ESPERAS) + 1
MAX_TENTATIVAS = len(ESPERAS) + 1


class _AdaptadorTls12(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        contexto = ssl.create_default_context()
        contexto.maximum_version = ssl.TLSVersion.TLSv1_2
        kwargs["ssl_context"] = contexto
        return super().init_poolmanager(*args, **kwargs)


SESSAO = requests.Session()
SESSAO.headers.update({"Accept": "application/json"})
if os.getenv("SENADO_TLS12") == "1":
    SESSAO.mount("https://", _AdaptadorTls12())

_ultima_chamada = 0.0


def _respeitar_ritmo():
    global _ultima_chamada
    espera = INTERVALO_MIN - (time.monotonic() - _ultima_chamada)
    if espera > 0:
        time.sleep(espera)
    _ultima_chamada = time.monotonic()


def _get(caminho, params=None):
    url = f"{SENADO_API_BASE}{caminho}"
    erro = None
    for tentativa in range(MAX_TENTATIVAS):
        _respeitar_ritmo()
        try:
            resposta = SESSAO.get(url, params=params, timeout=TIMEOUT)
        except requests.RequestException as exc:
            erro = str(exc)
        else:
            if resposta.status_code == 200:
                return resposta.json()
            if resposta.status_code != 429 and resposta.status_code < 500:
                raise RuntimeError(f"HTTP {resposta.status_code} em {url}")
            erro = f"HTTP {resposta.status_code}"
        if tentativa < len(ESPERAS):
            time.sleep(ESPERAS[tentativa])
    raise RuntimeError(f"Falha ao chamar {url} após {MAX_TENTATIVAS} tentativas: {erro}")


def como_lista(valor):
    if valor is None:
        return []
    return valor if isinstance(valor, list) else [valor]


def listar_classes():
    return como_lista(_get("/processo/classes"))


def expandir_classes(raizes):
    """Códigos das raízes e de todos os descendentes, na ordem da árvore, sem repetir.

    O filtro codigoClasse da API não inclui os filhos, então cada código é consultado.
    """
    codigos = []

    def visitar(no, dentro):
        dentro = dentro or no.get("codigo") in raizes
        if dentro and no.get("codigo") not in codigos:
            codigos.append(no["codigo"])
        for filho in como_lista(no.get("filhos")):
            visitar(filho, dentro)

    for no in listar_classes():
        visitar(no, False)
    return codigos


def listar_processos(numdias=None, codigo_classe=None, sigla=None, data_inicio=None, data_fim=None, tramitando=None):
    """Lista de processos (sem paginação: a resposta vem inteira)."""
    params = {}
    if numdias is not None:
        params["numdias"] = numdias
    if codigo_classe is not None:
        params["codigoClasse"] = codigo_classe
    if sigla is not None:
        params["sigla"] = sigla
    if data_inicio is not None:
        params["dataInicioApresentacao"] = data_inicio.isoformat()
    if data_fim is not None:
        params["dataFimApresentacao"] = data_fim.isoformat()
    if tramitando:
        params["tramitando"] = "S"
    return como_lista(_get("/processo", params))


def buscar_processo(id_processo):
    return _get(f"/processo/{id_processo}")
