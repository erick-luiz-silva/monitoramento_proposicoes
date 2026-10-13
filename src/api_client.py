import time

import requests

from config import API_BASE_URL

REQUEST_TIMEOUT = 15
SLEEP_BETWEEN_CALLS = 0.5
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2  # segundos: 2, 4, 8...


def _get(url, params=None):
    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
            if response.status_code == 200:
                return response.json()
            if response.status_code == 429 or response.status_code >= 500:
                last_error = f"HTTP {response.status_code}"
            else:
                response.raise_for_status()
        except requests.RequestException as exc:
            last_error = str(exc)

        if attempt < MAX_RETRIES:
            time.sleep(RETRY_BACKOFF_BASE * attempt)

    raise RuntimeError(f"Falha ao chamar {url} após {MAX_RETRIES} tentativas: {last_error}")


def listar_proposicoes_por_tema(cod_tema, itens=100, data_inicio=None, data_fim=None):
    """Retorna todas as proposições de um tema, seguindo a paginação via links.

    Sem data_inicio/data_fim, a API devolve só as proposições com tramitação
    nos últimos ~30 dias. Com datas, filtra por proposições com tramitação no
    período (não a data de apresentação), com intervalo máximo de 3 meses
    (HTTP 400 acima disso). Usado na carga incremental para pegar tanto
    proposições novas quanto movimentações em proposições antigas, e no backfill
    por janelas de extract_bronze.py.

    Faz uma pausa entre páginas para não sobrecarregar a API.
    """
    url = f"{API_BASE_URL}/proposicoes"
    params = {"codTema": cod_tema, "itens": itens, "ordenarPor": "id", "ordem": "ASC"}
    if data_inicio is not None:
        params["dataInicio"] = data_inicio.isoformat()
    if data_fim is not None:
        params["dataFim"] = data_fim.isoformat()

    proposicoes = []
    while url:
        data = _get(url, params=params)
        proposicoes.extend(data.get("dados", []))

        links = data.get("links", [])
        url = next((link["href"] for link in links if link["rel"] == "next"), None)
        params = None  # a partir da 2a página, a URL do link já traz os query params

        if url:
            time.sleep(SLEEP_BETWEEN_CALLS)

    return proposicoes


def buscar_detalhes(id_proposicao):
    data = _get(f"{API_BASE_URL}/proposicoes/{id_proposicao}")
    return data.get("dados")


def buscar_autores(id_proposicao):
    data = _get(f"{API_BASE_URL}/proposicoes/{id_proposicao}/autores")
    return data.get("dados")


def buscar_temas(id_proposicao):
    data = _get(f"{API_BASE_URL}/proposicoes/{id_proposicao}/temas")
    return data.get("dados")


def buscar_tramitacoes(id_proposicao):
    data = _get(f"{API_BASE_URL}/proposicoes/{id_proposicao}/tramitacoes")
    return data.get("dados")


def buscar_deputado(id_deputado):
    data = _get(f"{API_BASE_URL}/deputados/{id_deputado}")
    return data.get("dados")


def listar_eventos(ids_orgao, cods_tipo_evento, data_inicio, data_fim, itens=100):
    """Lista eventos de um ou mais órgãos/tipos num período, seguindo a paginação.

    idOrgao e codTipoEvento aceitam múltiplos valores separados por vírgula na
    própria API — uma chamada cobre todas as comissões e tipos deliberativos
    de uma vez, em vez de uma combinação por chamada.
    """
    url = f"{API_BASE_URL}/eventos"
    params = {
        "idOrgao": ",".join(str(i) for i in ids_orgao),
        "codTipoEvento": ",".join(str(i) for i in cods_tipo_evento),
        "dataInicio": data_inicio.isoformat(),
        "dataFim": data_fim.isoformat(),
        "itens": itens,
        "ordenarPor": "id",
        "ordem": "asc",
    }

    eventos = []
    while url:
        data = _get(url, params=params)
        eventos.extend(data.get("dados", []))

        links = data.get("links", [])
        url = next((link["href"] for link in links if link["rel"] == "next"), None)
        params = None

        if url:
            time.sleep(SLEEP_BETWEEN_CALLS)

    return eventos


def buscar_pauta_evento(id_evento):
    data = _get(f"{API_BASE_URL}/eventos/{id_evento}/pauta")
    return data.get("dados")


def listar_orgaos(ids_orgao, itens=100):
    """Busca um ou mais órgãos pelo id (múltiplos valores separados por vírgula
    numa única chamada), seguindo a paginação via links."""
    url = f"{API_BASE_URL}/orgaos"
    params = {"id": ",".join(str(i) for i in ids_orgao), "itens": itens}

    orgaos = []
    while url:
        data = _get(url, params=params)
        orgaos.extend(data.get("dados", []))

        links = data.get("links", [])
        url = next((link["href"] for link in links if link["rel"] == "next"), None)
        params = None

        if url:
            time.sleep(SLEEP_BETWEEN_CALLS)

    return orgaos
