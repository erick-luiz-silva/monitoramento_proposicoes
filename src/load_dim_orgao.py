import api_client as api
from db import get_connection

# Só órgãos da Câmara: os colegiados do Senado têm id deslocado e vêm de outra API. A faixa
# de id também é conferida, caso uma linha do Senado tenha ficado com o DEFAULT 'CD'.
_SQL_IDS_ORGAO = """
    SELECT id_orgao_atual FROM silver.proposicao WHERE id_orgao_atual IS NOT NULL AND casa = 'CD' AND id_orgao_atual < 1000000000
    UNION
    SELECT id_orgao FROM silver.tramitacao WHERE id_orgao IS NOT NULL AND casa = 'CD' AND id_orgao < 1000000000
    UNION
    SELECT id_orgao FROM silver.evento WHERE id_orgao IS NOT NULL AND casa = 'CD' AND id_orgao < 1000000000;
"""

_SQL_UPSERT = """
    INSERT INTO silver.dim_orgao (id_orgao, sigla, nome, apelido, cod_tipo_orgao, tipo_orgao, data_extracao)
    VALUES (%s, %s, %s, %s, %s, %s, now())
    ON CONFLICT (id_orgao) DO UPDATE SET
        sigla = EXCLUDED.sigla,
        nome = EXCLUDED.nome,
        apelido = EXCLUDED.apelido,
        cod_tipo_orgao = EXCLUDED.cod_tipo_orgao,
        tipo_orgao = EXCLUDED.tipo_orgao,
        data_extracao = EXCLUDED.data_extracao;
"""


def carregar_dim_orgao():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(_SQL_IDS_ORGAO)
            ids = [row[0] for row in cur.fetchall()]

        print(f"{len(ids)} órgãos distintos a processar")
        if not ids:
            return

        orgaos = api.listar_orgaos(ids)

        with conn.cursor() as cur:
            for o in orgaos:
                cur.execute(
                    _SQL_UPSERT,
                    (o["id"], o.get("sigla"), o.get("nome"), o.get("apelido"), o.get("codTipoOrgao"), o.get("tipoOrgao")),
                )
        conn.commit()
        print(f"dim_orgao: {len(orgaos)} órgãos carregados")


if __name__ == "__main__":
    carregar_dim_orgao()
