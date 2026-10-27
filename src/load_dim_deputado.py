import time

from tqdm import tqdm

import api_client as api
from db import get_connection

# Só autores da Câmara com uri numérica: os do Senado têm uri NULL e código de outro
# sistema (e o Postgres não garante a ordem do WHERE, então o cast fica protegido).
_SQL_IDS_DEPUTADOS = """
    SELECT DISTINCT (CASE WHEN uri ~ '/[0-9]+$' THEN regexp_replace(uri, '.*/', '') END)::int AS id_deputado
    FROM silver.proposicoes_proponentes
    WHERE tipo = 'Deputado(a)' AND uri ~ '/[0-9]+$' AND id_proposicao < 1000000000
    UNION
    SELECT DISTINCT id_deputado_relator
    FROM silver.evento_pauta
    WHERE id_deputado_relator IS NOT NULL
    ORDER BY 1;
"""

_SQL_PROPONENTES = """
    SELECT DISTINCT (CASE WHEN uri ~ '/[0-9]+$' THEN regexp_replace(uri, '.*/', '') END)::int AS id_deputado
    FROM silver.proposicoes_proponentes
    WHERE tipo = 'Deputado(a)' AND uri ~ '/[0-9]+$' AND id_proposicao < 1000000000
"""

_SQL_RELATORES = """
    SELECT DISTINCT id_deputado_relator AS id_deputado
    FROM silver.evento_pauta
    WHERE id_deputado_relator IS NOT NULL
"""

# Seleção do modo seletivo: ausentes da dim, autores das proposições do run e
# um refresh rolante dos mais antigos (registros com mais de REFRESH_DIAS dias,
# limitados a 1/REFRESH_DIAS da dim por run), que cobre troca de partido de
# quem não teve proposição nova. {candidatos} e {autores_run} são montados abaixo.
_SQL_SELETIVO = """
    WITH candidatos AS ({candidatos}),
    ausentes AS (
        SELECT c.id_deputado FROM candidatos c
        WHERE NOT EXISTS (SELECT 1 FROM silver.dim_deputado d WHERE d.id_deputado = c.id_deputado)
    ),
    defasados AS (
        SELECT d.id_deputado FROM silver.dim_deputado d
        JOIN candidatos c ON c.id_deputado = d.id_deputado
        WHERE d.data_extracao < now() - make_interval(days => %(refresh_dias)s)
        ORDER BY d.data_extracao
        LIMIT (SELECT ceil(count(*)::numeric / %(refresh_dias)s)::int FROM silver.dim_deputado)
    )
    SELECT id_deputado FROM ausentes
    UNION SELECT id_deputado FROM defasados
    {autores_run}
    ORDER BY 1;
"""

_SQL_AUTORES_RUN = """
    UNION
    SELECT (CASE WHEN uri ~ '/[0-9]+$' THEN regexp_replace(uri, '.*/', '') END)::int
    FROM silver.proposicoes_proponentes
    WHERE tipo = 'Deputado(a)' AND uri ~ '/[0-9]+$' AND id_proposicao < 1000000000
      AND id_proposicao = ANY(%(ids)s)
"""

REFRESH_DIAS = 7

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


def _consulta_ids(somente_relatores, seletivo, ids_proposicao):
    """Monta (sql, parâmetros) da lista de deputados a buscar na API."""
    if not seletivo:
        if somente_relatores:
            return _SQL_RELATORES + " ORDER BY 1;", None
        return _SQL_IDS_DEPUTADOS, None
    if somente_relatores:
        candidatos, autores_run = _SQL_RELATORES, ""
    else:
        candidatos, autores_run = _SQL_PROPONENTES + " UNION " + _SQL_RELATORES, _SQL_AUTORES_RUN
    sql = _SQL_SELETIVO.format(candidatos=candidatos, autores_run=autores_run)
    return sql, {"refresh_dias": REFRESH_DIAS, "ids": list(ids_proposicao or [])}


def carregar_dim_deputado(limit=None, somente_relatores=False, seletivo=False, ids_proposicao=None):
    """Atualiza silver.dim_deputado a partir da API.

    Sem `seletivo`, busca todos os proponentes e relatores (ou só relatores).
    Com `seletivo`, busca só os ausentes da dim, os autores de `ids_proposicao`
    (as proposições carregadas no run) e o refresh rolante dos mais antigos.
    Roda depois da silver: a seleção depende dos proponentes já transformados.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            sql, params = _consulta_ids(somente_relatores, seletivo, ids_proposicao)
            cur.execute(sql, params)
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
    parser.add_argument(
        "--seletivo",
        action="store_true",
        help="Só ausentes da dim e refresh rolante dos mais antigos (padrão: todos)",
    )
    args = parser.parse_args()
    carregar_dim_deputado(limit=args.limit, seletivo=args.seletivo)
