"""Filtro do git que mantém acessos fora do repositório público.

O modelo do Power BI guarda nos .tmdl a URL e a chave anon do Supabase (parâmetros
SupabaseUrl/SupabaseAnonKey) e o link da planilha "Proposições". No commit (clean) eles
viram marcadores; no checkout (smudge) voltam com os valores dos .env locais, para o
Desktop continuar abrindo o modelo. Sem os .env, os marcadores ficam e é preciso preencher
os parâmetros no Desktop.

Configuração única por clone (a partir da raiz do repositório):
    git config filter.segredos-pbi.clean "python3 BI/filtro_segredos.py clean"
    git config filter.segredos-pbi.smudge "python3 BI/filtro_segredos.py smudge"
    git config filter.segredos-pbi.required true

Lê o arquivo na entrada padrão e escreve na saída padrão (só biblioteca padrão: roda com
qualquer python3, sem o .venv).
"""

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

MARCADOR_URL = b"https://SEU-PROJETO.supabase.co"
MARCADOR_CHAVE = b"COLE-A-CHAVE-ANON"
MARCADOR_PLANILHA = b"ID-DA-PLANILHA"

RE_URL = re.compile(rb'(expression SupabaseUrl = ")[^"]*(")')
RE_CHAVE = re.compile(rb'(expression SupabaseAnonKey = ")[^"]*(")')
RE_PLANILHA = re.compile(rb"(docs\.google\.com/spreadsheets/d/)[A-Za-z0-9_-]+")


def ler_env(caminho):
    valores = {}
    if caminho.exists():
        for linha in caminho.read_text(encoding="utf-8").splitlines():
            nome, sep, valor = linha.strip().partition("=")
            if sep and not nome.startswith("#"):
                valores[nome.strip()] = valor.strip().strip('"').strip("'")
    return valores


def limpar(conteudo):
    conteudo = RE_URL.sub(rb"\g<1>" + MARCADOR_URL + rb"\g<2>", conteudo)
    conteudo = RE_CHAVE.sub(rb"\g<1>" + MARCADOR_CHAVE + rb"\g<2>", conteudo)
    return RE_PLANILHA.sub(rb"\g<1>" + MARCADOR_PLANILHA, conteudo)


def restaurar(conteudo):
    env = {**ler_env(RAIZ / "src" / ".env"), **ler_env(RAIZ / "BI" / ".env")}
    url = re.sub(r"/rest/v1/?$", "", env.get("SUPABASE_URL", ""))
    trocas = (
        (MARCADOR_URL, url),
        (MARCADOR_CHAVE, env.get("SUPABASE_KEY", "")),
        (MARCADOR_PLANILHA, env.get("GOOGLE_SHEET_MONITORAMENTO_ID", "")),
    )
    for marcador, valor in trocas:
        if valor:
            conteudo = conteudo.replace(marcador, valor.encode("utf-8"))
    return conteudo


if __name__ == "__main__":
    modo = sys.argv[1] if len(sys.argv) > 1 else ""
    if modo not in ("clean", "smudge"):
        sys.exit("uso: filtro_segredos.py clean|smudge")
    entrada = sys.stdin.buffer.read()
    sys.stdout.buffer.write(limpar(entrada) if modo == "clean" else restaurar(entrada))
