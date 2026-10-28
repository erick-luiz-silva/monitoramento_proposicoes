"""Compara a aba "Acompanhamento manual" da planilha do time com o banco. Só leitura.

Lê a planilha pela Sheets API, resolve cada proposição na Câmara e classifica:
  A  no gold (gold.vw_monitoramento)
  B  no silver, sem keyword
  C1 fora do banco, dentro dos temas da carga (config.TEMAS)
  C2 fora dos temas da carga
  NC não encontrada na Câmara (ex.: Senado)

Também mostra a precisão por keyword a partir da coluna "relevancia" da aba "Proposições".

Uso (de src/; o id da planilha vai em GOOGLE_SHEET_MONITORAMENTO_ID):
    python comparar_acompanhamento.py
    python comparar_acompanhamento.py --keywords-candidatas   # testa keywords.KEYWORDS em memória

Saída: ../data/comparacao_acompanhamento.csv (ignorada pelo git).
"""

import argparse
import csv
import os
import re
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

from google.auth.transport.requests import AuthorizedSession

import api_client as api
from config import API_BASE_URL, TEMAS  # também carrega o .env
from db import get_connection
from google_auth import get_credentials
from keywords import KEYWORDS

SAIDA = Path(__file__).resolve().parents[1] / "data" / "comparacao_acompanhamento.csv"
SLEEP_ENTRE_CHAMADAS = 0.3
_IDENTIFICADOR = re.compile(r"\b(PLP|PLS|PLC|PDL|PL|RIC|MP|PEC)\s*(\d+)\s*(?:/|de)\s*(\d{4})", re.I)


def ler_aba(sessao, sheet_id, aba):
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/{quote(aba)}"
    resposta = sessao.get(url, timeout=30)
    resposta.raise_for_status()
    linhas = resposta.json().get("values", [])
    if not linhas:
        return []
    cabecalho = linhas[0]
    # A Sheets API omite células vazias no fim de cada linha; completa para alinhar as colunas.
    return [dict(zip(cabecalho, linha + [""] * (len(cabecalho) - len(linha)))) for linha in linhas[1:]]


def identificadores(texto):
    return {f"{m[1].upper()} {int(m[2])}/{m[3]}" for m in _IDENTIFICADOR.finditer(texto or "")}


def manual_por_identificador(linhas):
    manual = defaultdict(lambda: defaultdict(set))
    for linha in linhas:
        for ident in identificadores(linha.get("Nº do Projeto")):
            entrada = manual[ident]
            entrada["casa"].add(linha.get("Casa", "").strip())
            entrada["anos"].add(linha.get("Ano", "")[:4])
            entrada["rotulo"].add(linha.get("Rótulo", "").replace("\n", " ").strip())
            entrada["posicao"].add(linha.get("Posição", "").replace("\n", " ").strip()[:60])
    return manual


def resolver_na_camara(ident):
    """Devolve (id, detalhes, temas) ou None se a proposição não existe na Câmara."""
    sigla, resto = ident.split(" ")
    numero, ano = resto.split("/")
    dados = api._get(f"{API_BASE_URL}/proposicoes", params={"siglaTipo": sigla, "numero": numero, "ano": ano})
    if not dados.get("dados"):
        return None
    id_camara = dados["dados"][0]["id"]
    detalhes = api.buscar_detalhes(id_camara) or {}
    temas = [t["codTema"] for t in (api.buscar_temas(id_camara) or [])]
    return id_camara, detalhes, temas


def _fonte_keywords(candidatas):
    """Retorna (FROM, params, cláusula de ativo) para simular as keywords em SQL."""
    if candidatas:
        valores = ", ".join(["(%s, %s, %s)"] * len(KEYWORDS))
        params = [parte for kw in KEYWORDS for parte in kw]
        return f"(VALUES {valores}) AS k(rotulo, termo, termo_requerido)", params, "TRUE"
    return "silver.dim_keyword k", [], "k.ativo"


def rotulos_de(cur, ementa, keywords_camara, candidatas):
    """Replica gold.vw_proposicao_keywords para uma única proposição."""
    origem, params, ativo = _fonte_keywords(candidatas)
    cur.execute(
        f"""
        SELECT string_agg(DISTINCT k.rotulo, ', ' ORDER BY k.rotulo)
        FROM {origem}
        WHERE {ativo}
          AND (%s ~* k.termo OR %s ~* k.termo)
          AND (k.termo_requerido IS NULL OR %s ~* k.termo_requerido OR %s ~* k.termo_requerido);
        """,
        params + [ementa, keywords_camara, ementa, keywords_camara],
    )
    return cur.fetchone()[0] or ""


def rotulos_do_silver(cur, candidatas):
    """Simula as keywords sobre todo o silver. Retorna {id_proposicao: rotulos}."""
    origem, params, ativo = _fonte_keywords(candidatas)
    cur.execute(
        f"""
        SELECT p.id_proposicao, string_agg(DISTINCT k.rotulo, ', ' ORDER BY k.rotulo)
        FROM silver.proposicao p
        JOIN {origem}
          ON {ativo}
         -- mesma regra da gold.vw_proposicao_keywords: sem acento nas linhas do Senado
         AND CASE WHEN p.casa = 'SF' THEN
                 (extensions.unaccent(coalesce(p.ementa, '')) ~* extensions.unaccent(k.termo)
                  OR extensions.unaccent(coalesce(p.keywords_camara, '')) ~* extensions.unaccent(k.termo))
                 AND (k.termo_requerido IS NULL
                      OR extensions.unaccent(coalesce(p.ementa, '')) ~* extensions.unaccent(k.termo_requerido)
                      OR extensions.unaccent(coalesce(p.keywords_camara, '')) ~* extensions.unaccent(k.termo_requerido))
             ELSE
                 (p.ementa ~* k.termo OR p.keywords_camara ~* k.termo)
                 AND (k.termo_requerido IS NULL OR p.ementa ~* k.termo_requerido OR p.keywords_camara ~* k.termo_requerido)
             END
        GROUP BY p.id_proposicao;
        """,
        params,
    )
    return {linha[0]: linha[1] for linha in cur.fetchall()}


def precisao_por_keyword(linhas_proposicoes, rotulos_por_id=None):
    """Conta SIM/NÃO por keyword. Sem rotulos_por_id, usa a coluna keywords_encontradas da planilha."""
    contagem = defaultdict(lambda: {"SIM": 0, "NÃO": 0})
    for linha in linhas_proposicoes:
        relevancia = linha.get("relevancia", "").strip().upper()
        if relevancia not in ("SIM", "NÃO", "NAO"):
            continue
        relevancia = "NÃO" if relevancia == "NAO" else relevancia
        if rotulos_por_id is None:
            rotulos = linha.get("keywords_encontradas", "")
        else:
            rotulos = rotulos_por_id.get(int(linha["id_proposicao"]), "")
        for rotulo in filter(None, (r.strip() for r in rotulos.split(","))):
            contagem[rotulo][relevancia] += 1
    return contagem


def classificar(id_camara, temas, gold_ids, silver_ids):
    if id_camara in gold_ids:
        return "A_NO_GOLD"
    if id_camara in silver_ids:
        return "B_SILVER_SEM_KEYWORD"
    if set(temas) & set(TEMAS):
        return "C1_FORA_BANCO_DENTRO_TEMAS"
    return "C2_FORA_TEMAS"


def imprimir_precisao(contagem):
    print("\nPrecisão por keyword (SIM / NÃO):")
    for rotulo, c in sorted(contagem.items(), key=lambda kv: (-kv[1]["NÃO"], kv[0])):
        print(f"  {rotulo:<35} {c['SIM']:>4} / {c['NÃO']:<4}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--keywords-candidatas",
        action="store_true",
        help="Simula keywords.KEYWORDS em memória (CTE VALUES), sem alterar silver.dim_keyword",
    )
    args = parser.parse_args()

    sheet_id = os.getenv("GOOGLE_SHEET_MONITORAMENTO_ID", "").strip()
    if not sheet_id:
        raise RuntimeError("Configure GOOGLE_SHEET_MONITORAMENTO_ID (id da planilha de monitoramento).")

    sessao = AuthorizedSession(get_credentials())
    proposicoes_planilha = ler_aba(sessao, sheet_id, "Proposições")
    manual = manual_por_identificador(ler_aba(sessao, sheet_id, "Acompanhamento manual"))
    print(f"Planilha: {len(proposicoes_planilha)} proposições em 'Proposições'; "
          f"{len(manual)} identificadores únicos em 'Acompanhamento manual'.")

    with get_connection() as conn:
        conn.set_session(readonly=True)
        cur = conn.cursor()
        cur.execute("SELECT id_proposicao FROM gold.vw_monitoramento")
        gold_ids = {linha[0] for linha in cur.fetchall()}
        cur.execute("SELECT id_proposicao FROM silver.proposicao")
        silver_ids = {linha[0] for linha in cur.fetchall()}

        linhas_csv = []
        for ident, dados in sorted(manual.items()):
            base = {
                "identificacao": ident,
                "casa": "/".join(sorted(filter(None, dados["casa"]))),
                "anos": ",".join(sorted(filter(None, dados["anos"]))),
                "rotulo": " ; ".join(sorted(filter(None, dados["rotulo"]))),
                "posicao": " ; ".join(sorted(filter(None, dados["posicao"]))),
            }
            try:
                resolvido = resolver_na_camara(ident)
            except RuntimeError as exc:
                print(f"  ! {ident}: {exc}")
                linhas_csv.append({**base, "grupo": "ERRO_API"})
                continue
            time.sleep(SLEEP_ENTRE_CHAMADAS)

            if resolvido is None:
                linhas_csv.append({**base, "grupo": "NC_NAO_ENCONTRADA"})
                continue
            id_camara, detalhes, temas = resolvido
            st = detalhes.get("statusProposicao") or {}
            grupo = classificar(id_camara, temas, gold_ids, silver_ids)
            kw = rotulos_de(cur, detalhes.get("ementa", ""), detalhes.get("keywords") or "",
                            args.keywords_candidatas)
            linhas_csv.append({
                **base,
                "id": id_camara,
                "grupo": grupo,
                "temas": ",".join(str(t) for t in temas),
                "situacao": st.get("descricaoSituacao", ""),
                "kw_sim": kw,
            })

        rotulos_silver = rotulos_do_silver(cur, args.keywords_candidatas)

    modo = "candidatas (keywords.py)" if args.keywords_candidatas else "atuais (silver.dim_keyword)"
    print(f"\nModo de keywords: {modo}")

    print("\nCobertura (identificadores do acompanhamento manual):")
    totais = defaultdict(int)
    for linha in linhas_csv:
        totais[linha["grupo"]] += 1
    for grupo in ["A_NO_GOLD", "B_SILVER_SEM_KEYWORD", "C1_FORA_BANCO_DENTRO_TEMAS", "C2_FORA_TEMAS",
                  "NC_NAO_ENCONTRADA", "ERRO_API"]:
        print(f"  {grupo:<30} {totais[grupo]:>4}")
    c1_casariam = sum(1 for l in linhas_csv if l["grupo"] == "C1_FORA_BANCO_DENTRO_TEMAS" and l["kw_sim"])
    print(f"  (C1 que já casariam com as keywords: {c1_casariam})")

    print(f"\nGold simulado: {len(rotulos_silver)} proposições com ao menos 1 keyword "
          f"(de {len(silver_ids)} no silver).")

    precisao = precisao_por_keyword(
        proposicoes_planilha, rotulos_silver if args.keywords_candidatas else None
    )
    sim = sum(1 for l in proposicoes_planilha if l.get("relevancia", "").strip().upper() == "SIM")
    nao = sum(1 for l in proposicoes_planilha if l.get("relevancia", "").strip().upper() in ("NÃO", "NAO"))
    print(f"Relevância na planilha: {sim} SIM / {nao} NÃO")
    if args.keywords_candidatas:
        ids_sim = {int(l["id_proposicao"]) for l in proposicoes_planilha
                   if l.get("relevancia", "").strip().upper() == "SIM"}
        mantidos = ids_sim & set(rotulos_silver)
        perdidos = sorted(ids_sim - set(rotulos_silver))
        print(f"SIM mantidos com as keywords candidatas: {len(mantidos)} de {len(ids_sim)}")
        print(f"SIM perdidos: {perdidos or 'nenhum'}")
    imprimir_precisao(precisao)

    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    campos = ["identificacao", "id", "casa", "anos", "rotulo", "posicao", "grupo", "temas", "situacao", "kw_sim"]
    with SAIDA.open("w", newline="", encoding="utf-8") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=campos, extrasaction="ignore")
        escritor.writeheader()
        escritor.writerows(linhas_csv)
    print(f"\nDetalhe gravado em {SAIDA}")


if __name__ == "__main__":
    main()
