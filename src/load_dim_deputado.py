import time

from tqdm import tqdm

import api_client as api
from db import get_connection

_SQL_IDS_DEPUTADOS = """
    SELECT DISTINCT (regexp_replace(uri, '.*/', ''))::int AS id_deputado
    FROM silver.proposicoes_proponentes
    WHERE tipo = 'Deputado(a)'
    UNION
    SELECT DISTINCT id_deputado_relator
    FROM silver.evento_pauta
    WHERE id_deputado_relator IS NOT NULL
    ORDER BY 1;
"""

_SQL_UPSERT = """
    INSERT INTO silver.dim_deputado (id_deputado, nome, sigla_partido, sigla_uf, situacao, data_extracao)
    VALUES (%s, %s, %s, %s, %s, now())
    ON CONFLICT (id_deputado) DO UPDATE SET
        nome = EXCLUDED.nome,
        sigla_partido = EXCLUDED.sigla_partido,
        sigla_uf = EXCLUDED.sigla_uf,
        situacao = EXCLUDED.situacao,
        data_extracao = EXCLUDED.data_extracao;
"""


def carregar_dim_deputado(limit=None, somente_relatores=False):
    with get_connection() as conn:
        with conn.cursor() as cur:
            if somente_relatores:
                cur.execute(
                    "SELECT DISTINCT id_deputado_relator FROM silver.evento_pauta "
                    "WHERE id_deputado_relator IS NOT NULL ORDER BY 1;"
                )
            else:
                cur.execute(_SQL_IDS_DEPUTADOS)
            ids = [row[0] for row in cur.fetchall()]

        if limit is not None:
            ids = ids[:limit]

        print(f"{len(ids)} deputados distintos a processar")

        ok, erro = 0, 0
        with conn.cursor() as cur:
            for id_deputado in tqdm(ids, desc="dim_deputado", unit="deputado"):
                try:
                    dep = api.buscar_deputado(id_deputado)
                    status = dep.get("ultimoStatus", {})
                    cur.execute(
                        _SQL_UPSERT,
                        (
                            id_deputado,
                            status.get("nome"),
                            status.get("siglaPartido"),
                            status.get("siglaUf"),
                            status.get("situacao"),
                        ),
                    )
                    conn.commit()
                    ok += 1
                except Exception as exc:
                    conn.rollback()
                    erro += 1
                    tqdm.write(f"  ! deputado {id_deputado}: {exc}")
                time.sleep(api.SLEEP_BETWEEN_CALLS)

        print(f"dim_deputado: {ok} ok, {erro} com erro")
        if erro:
            raise RuntimeError(f"Carga de deputados incompleta: {erro} deputados com erro.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Carga da dimensão de deputados (partido/UF atuais)")
    parser.add_argument("--limit", type=int, default=None, help="Limita a quantidade de deputados (teste)")
    args = parser.parse_args()
    carregar_dim_deputado(limit=args.limit)
