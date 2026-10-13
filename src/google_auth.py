"""Autenticação OAuth 2.0 com a conta Google (Sheets/Drive).

Uso local (uma vez, abre o consentimento no navegador e grava o token):
    python google_auth.py

Depois, em outros scripts:
    from google_auth import get_credentials
    creds = get_credentials()

O token (com refresh token) fica em src/token_google.json, que está no
.gitignore. Em ambiente sem navegador (ex. GitHub Actions), defina
GOOGLE_TOKEN_JSON com o conteúdo desse arquivo.
"""

import argparse
import json
import os
from pathlib import Path
from urllib.parse import parse_qs
import wsgiref.simple_server
import wsgiref.util

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

import config  # noqa: F401 — carrega também o .env para execução local.

TOKEN_PATH = Path(__file__).resolve().parent / "token_google.json"
SCOPES_PADRAO = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]


def scopes():
    valor = os.getenv("GOOGLE_SCOPES", "").strip()
    return valor.split() if valor else SCOPES_PADRAO


def client_config():
    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        raise RuntimeError("Configure GOOGLE_CLIENT_ID e GOOGLE_CLIENT_SECRET.")
    return {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }


def _carregar_token():
    token_env = os.getenv("GOOGLE_TOKEN_JSON", "").strip()
    if token_env:
        return Credentials.from_authorized_user_info(json.loads(token_env), scopes())
    if TOKEN_PATH.exists():
        return Credentials.from_authorized_user_file(str(TOKEN_PATH), scopes())
    return None


def _salvar_token(creds):
    if os.getenv("GOOGLE_TOKEN_JSON", "").strip():
        return  # Token vem do ambiente; não grava em disco.
    TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    TOKEN_PATH.chmod(0o600)


class _HandlerSilencioso(wsgiref.simple_server.WSGIRequestHandler):
    def log_message(self, *args):
        pass


def autorizar(porta):
    """Executa o fluxo de consentimento no navegador e grava o token.

    Não usa InstalledAppFlow.run_local_server porque ele desiste na primeira
    conexão recebida; navegadores (sobretudo via WSL) abrem pré-conexões vazias
    ou pedem /favicon.ico antes do redirecionamento com o código.
    """
    flow = InstalledAppFlow.from_client_config(client_config(), scopes())
    flow.redirect_uri = f"http://localhost:{porta}/"
    auth_url, state = flow.authorization_url(access_type="offline", prompt="consent")

    recebido = {}

    def app(environ, start_response):
        query = parse_qs(environ.get("QUERY_STRING", ""))
        if query.get("state", [None])[0] != state:
            corpo = "Link de autorização antigo; use a URL mais recente exibida no terminal."
        elif "code" in query or "error" in query:
            recebido["uri"] = wsgiref.util.request_uri(environ)
            recebido["erro"] = query.get("error", [None])[0]
            corpo = "Autorização concluída. Pode fechar esta aba." if "code" in query else "Autorização negada."
        else:
            corpo = "Aguardando autorização do Google."
        start_response("200 OK", [("Content-Type", "text/plain; charset=utf-8")])
        return [corpo.encode("utf-8")]

    servidor = wsgiref.simple_server.make_server("localhost", porta, app, handler_class=_HandlerSilencioso)
    try:
        print(f"Abra esta URL no navegador para autorizar:\n{auth_url}", flush=True)
        while "uri" not in recebido:
            servidor.handle_request()
    finally:
        servidor.server_close()

    if recebido["erro"]:
        raise RuntimeError(f"Google recusou a autorização: {recebido['erro']}.")
    # oauthlib exige https na URL de retorno, mesmo sendo localhost.
    flow.fetch_token(authorization_response=recebido["uri"].replace("http://", "https://", 1))
    creds = flow.credentials
    _salvar_token(creds)
    return creds


def get_credentials():
    """Retorna credenciais válidas, renovando o access token se necessário."""
    creds = _carregar_token()
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _salvar_token(creds)
        return creds
    raise RuntimeError("Sem token Google válido. Execute: python google_auth.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="Valida o token salvo sem abrir o navegador")
    parser.add_argument("--porta", type=int, default=int(os.getenv("GOOGLE_OAUTH_PORT", "8080")))
    args = parser.parse_args()
    if args.check:
        creds = get_credentials()
    else:
        creds = autorizar(args.porta)
    print(f"Token Google válido; escopos: {' '.join(creds.scopes or scopes())}.")
