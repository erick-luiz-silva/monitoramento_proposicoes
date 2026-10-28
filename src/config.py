import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

# DATABASE_URL (formato padrão de provedores cloud, ex. Supabase/Neon) tem
# prioridade se definida; senão cai nas variáveis discretas (uso local).
_DATABASE_URL = os.getenv("DATABASE_URL")

if _DATABASE_URL:
    DB_CONFIG = {"dsn": _DATABASE_URL}
else:
    DB_CONFIG = {
        "dbname": os.getenv("DB_NAME"),
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
        "host": os.getenv("DB_HOST"),
        "port": os.getenv("DB_PORT"),
    }

API_BASE_URL = "https://dadosabertos.camara.leg.br/api/v2"
SENADO_API_BASE = "https://legis.senado.leg.br/dadosabertos"

# Filtro grosso da extração por tema da Câmara (o fino é por keyword, na gold):
# 64 Agricultura, Pecuária, Pesca e Extrativismo; 48 Meio Ambiente e
# Desenvolvimento Sustentável; 66 Indústria, Comércio e Serviços.
TEMAS = [64, 48, 66]

# Filtro grosso do Senado por classe (os filhos são expandidos em tempo de execução, porque
# o filtro codigoClasse da API não inclui a subárvore): Agropecuária e Abastecimento, Meio
# Ambiente, Indústria/Comércio/Serviços e Saúde > Defesa e Vigilância Sanitária. Todas as
# MPVs entram também (só 32 das 238 desde 2023 estão nessas classes).
CLASSES_SENADO = (33805062, 33809634, 33804850, 33809198)

# Senado no mesmo banco: as chaves do Senado (processo, colegiado, parte de reunião)
# ganham este deslocamento, para id_proposicao continuar um inteiro único em todas as
# camadas, no n8n e no Power BI. Sessões do Plenário do Senado usam faixa própria,
# porque o código de sessão é um espaço de números independente. A coluna `casa`
# ('CD'/'SF') vem ao lado; a bronze do Senado guarda o id nativo.
SENADO_OFFSET = 1_000_000_000
PLENARIO_SENADO_OFFSET = 2_000_000_000

# Carga diária do Senado: janela por última atualização (numdias, limite 30 na API),
# reconciliação por apresentação e prazo global (estourou, vira aviso e a janela não avança).
SENADO_JANELA_DIAS = 14
SENADO_RECONCILIACAO_DIAS = 90
SENADO_PRAZO_MIN = 30


def chave_senado(id_nativo):
    if not 0 <= id_nativo < SENADO_OFFSET:
        raise ValueError(f"id do Senado fora da faixa: {id_nativo}")
    return SENADO_OFFSET + id_nativo


def chave_sessao_plenario(codigo_sessao):
    if not 0 <= codigo_sessao < SENADO_OFFSET:
        raise ValueError(f"código de sessão do Plenário fora da faixa: {codigo_sessao}")
    return PLENARIO_SENADO_OFFSET + codigo_sessao


def eh_camara(id_proposicao):
    return id_proposicao < SENADO_OFFSET


def casa_de(id_proposicao):
    return "CD" if eh_camara(id_proposicao) else "SF"
