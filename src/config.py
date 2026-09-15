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
