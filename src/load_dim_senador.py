"""Dimensão de senadores: partido/UF atuais, como dim_deputado faz para a Câmara.

Endpoints legados do Senado (XML convertido em JSON: tudo string, lista de 1 item vem como
objeto). Lê a lista em exercício e busca um a um os autores ausentes (ex-senadores). Falha
num código não levanta: a gold cai para o partido/UF da época (proposicoes_proponentes).
"""

import api_client_senado as api
from api_client_senado import como_lista
from db import get_connection

_SQL_AUSENTES = """
    SELECT DISTINCT p.codigo_parlamentar_senado
    FROM silver.proposicoes_proponentes p
    WHERE p.tipo = 'Senador(a)' AND p.codigo_parlamentar_senado IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM silver.dim_senador d WHERE d.codigo = p.codigo_parlamentar_senado)
    ORDER BY 1;
"""
_SQL_UPSERT = """
    INSERT INTO silver.dim_senador (codigo, nome, sigla_partido, sigla_uf, em_exercicio, data_extracao)
    VALUES (%s, %s, %s, %s, %s, now())
    ON CONFLICT (codigo) DO UPDATE SET
        nome = EXCLUDED.nome,
        sigla_partido = EXCLUDED.sigla_partido,
        sigla_uf = EXCLUDED.sigla_uf,
        em_exercicio = EXCLUDED.em_exercicio,
        data_extracao = EXCLUDED.data_extracao;
"""


def _identificacao(parlamentar):
    i = parlamentar.get("IdentificacaoParlamentar") or {}
    return int(i["CodigoParlamentar"]), i.get("NomeParlamentar"), i.get("SiglaPartidoParlamentar"), i.get("UfParlamentar")


def listar_em_exercicio():
    dados = api._get("/senador/lista/atual")
    parlamentares = dados["ListaParlamentarEmExercicio"]["Parlamentares"]["Parlamentar"]
    return [_identificacao(p) for p in como_lista(parlamentares)]


def buscar_senador(codigo):
    return _identificacao(api._get(f"/senador/{codigo}")["DetalheParlamentar"]["Parlamentar"])


def carregar_dim_senador():
    """Devolve quantos senadores foram gravados. Só a falha da lista em exercício levanta."""
    atuais = listar_em_exercicio()
    gravados = 0
    with get_connection() as conn:
        with conn.cursor() as cur:
            for codigo, nome, partido, uf in atuais:
                cur.execute(_SQL_UPSERT, (codigo, nome, partido, uf, True))
                gravados += 1
            em_exercicio = {codigo for codigo, *_ in atuais}
            cur.execute(_SQL_AUSENTES)
            for (codigo,) in cur.fetchall():
                if codigo in em_exercicio:
                    continue
                try:
                    _, nome, partido, uf = buscar_senador(codigo)
                except Exception as exc:
                    print(f"  ! senador {codigo} sem dados ({exc}); fica o partido/UF da época")
                    continue
                cur.execute(_SQL_UPSERT, (codigo, nome, partido, uf, False))
                gravados += 1
        conn.commit()
    print(f"dim_senador: {gravados} senadores gravados")
    return gravados
