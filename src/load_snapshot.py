"""Foto diária da carteira, gravada só depois do refresh do modo completo."""

from db import get_connection


def gravar_snapshot_carteira():
    """Substitui a foto de hoje em uma transação própria, sem tocar nas janelas da carga."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT gestao.gravar_snapshot_carteira();")
        conn.commit()
    print("Foto diária da carteira gravada.")
