from contextlib import contextmanager

import psycopg2

from config import DB_CONFIG


@contextmanager
def get_connection():
    # keepalives: evita que o pooler derrube conexões longas (ex.: backfill de horas).
    conn = psycopg2.connect(**DB_CONFIG, keepalives=1, keepalives_idle=30, keepalives_interval=10, keepalives_count=5)
    try:
        yield conn
    finally:
        conn.close()
