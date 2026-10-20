"""Teste somente de leitura das views gold pela Data API do Supabase.

Configure SUPABASE_URL e SUPABASE_KEY em BI/.env e execute:
    python BI/teste_api.py
    python BI/teste_api.py --view vw_monitoramento --limit 3
"""

import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

import requests
from dotenv import load_dotenv


VIEWS = (
    "vw_proposicao_keywords",
    "vw_monitoramento",
    "vw_tramitacoes",
    "vw_pautas_monitoradas",
    "vw_audiencias_de_interesse",
    "vw_proposicoes_sem_keyword",
)


def diagnostico(status, erro):
    codigo = erro.get("code", "")
    mensagem = str(erro.get("message", ""))
    if codigo == "PGRST106":
        return "Adicione gold em Exposed schemas nas configurações da Data API."
    if codigo == "42501":
        return (
            "A role da chave precisa de USAGE no schema gold e SELECT na view. "
            "Views security_invoker também exigem permissões nas relações de origem."
        )
    if codigo == "PGRST205" or status == 404:
        return "Confira se a view existe em gold e se o cache da API está atualizado."
    if status == 401:
        return "Confira a chave de API e se ela pertence ao projeto da URL."
    if status == 403:
        return "Confira as permissões da role utilizada pela chave/token."
    if codigo == "57014" or "statement timeout" in mensagem.lower():
        return "A consulta excedeu o tempo permitido no banco; revise o custo da view."
    return "Confira message, details e hint retornados pela API."


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--view", choices=VIEWS, help="Consultar apenas esta view")
    parser.add_argument("--limit", type=int, default=3, help="Linhas por view (padrão: 3)")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit deve ser maior que zero")

    env_path = Path(__file__).resolve().with_name(".env")
    load_dotenv(env_path)
    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    key = next(
        (os.getenv(name, "").strip() for name in (
            "SUPABASE_KEY", "SUPABASE_PUBLISHABLE_KEY", "SUPABASE_ANON_KEY",
            "SUPABASE_API_KEY", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SECRET_KEY",
        ) if os.getenv(name, "").strip()),
        "",
    )
    if not url or not key:
        print(f"Configure SUPABASE_URL e SUPABASE_KEY em {env_path} e salve o arquivo.")
        return 1
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        print("SUPABASE_URL deve ser a URL HTTPS do projeto, sem usuário/senha.")
        return 1
    if parts.query or parts.fragment or parts.path not in ("", "/rest/v1"):
        print("SUPABASE_URL deve apontar para o projeto ou para /rest/v1.")
        return 1
    base_url = url if url.endswith("/rest/v1") else f"{url}/rest/v1"
    headers = {"apikey": key, "Accept-Profile": "gold", "Accept": "application/json"}
    token = os.getenv("SUPABASE_ACCESS_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    elif key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {key}"

    falhas = 0
    with requests.Session() as session:
        session.headers.update(headers)
        for view in (args.view,) if args.view else VIEWS:
            print(f"\nConsultando gold.{view} (limite: {args.limit})")
            try:
                response = session.get(
                    f"{base_url}/{view}",
                    params={"select": "*", "limit": args.limit},
                    timeout=(10, 60),
                    allow_redirects=False,
                )
            except requests.Timeout:
                print("FALHA: timeout na chamada HTTP.")
                falhas += 1
                continue
            except requests.RequestException:
                print("FALHA: conexão HTTP. Confira rede, DNS e URL do projeto.")
                falhas += 1
                continue
            try:
                data = response.json()
            except ValueError:
                print(f"FALHA: HTTP {response.status_code}, resposta não é JSON.")
                falhas += 1
                continue
            if not response.ok or not isinstance(data, list):
                erro = data if isinstance(data, dict) else {}
                print(f"FALHA: HTTP {response.status_code}")
                detalhe = json.dumps(erro, ensure_ascii=False, indent=2)
                for segredo in (key, token):
                    if segredo:
                        detalhe = detalhe.replace(segredo, "<oculto>")
                print(detalhe)
                print(diagnostico(response.status_code, erro))
                falhas += 1
                continue
            print(f"OK: HTTP {response.status_code}; {len(data)} linha(s) na amostra.")
            if data:
                print("Colunas: " + ", ".join(data[0]))
                print(json.dumps(data, ensure_ascii=False, indent=2))
            else:
                print("Sem linhas visíveis para esta credencial; confira dados e políticas RLS.")

    print(f"\nTeste concluído: {falhas} falha(s).")
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(main())
