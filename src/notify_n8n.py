"""Notifica o n8n após a conclusão da carga, sem registrar credenciais."""

import argparse
from datetime import datetime, timezone
import os
from urllib.parse import urlparse

import requests

import config  # noqa: F401 — carrega também o .env para execução local.


def webhook_config():
    url = os.getenv("N8N_WEBHOOK_URL", "").strip()
    token = os.getenv("N8N_WEBHOOK_TOKEN", "").strip()
    if not url or not token:
        raise RuntimeError("Configure N8N_WEBHOOK_URL e N8N_WEBHOOK_TOKEN.")
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or not parsed.path.startswith("/webhook/"):
        raise RuntimeError("N8N_WEBHOOK_URL deve usar HTTPS e o endpoint de produção /webhook/.")
    return url, token


def notify_n8n(mode):
    url, token = webhook_config()
    run_id = os.getenv("GITHUB_RUN_ID")
    repository = os.getenv("GITHUB_REPOSITORY")
    payload = {
        "origem": "github_actions" if run_id else "local",
        "modo": mode,
        "status": "sucesso",
        "concluido_em": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "run_url": f"https://github.com/{repository}/actions/runs/{run_id}" if repository and run_id else None,
    }
    try:
        response = requests.post(
            url, headers={"X-Webhook-Token": token}, json=payload,
            timeout=(10, 60), allow_redirects=False,
        )
    except requests.RequestException:
        raise RuntimeError(
            "Falha de conexão com o webhook n8n. Verifique a execução no n8n antes de repetir a chamada."
        ) from None
    if not 200 <= response.status_code < 300:
        raise RuntimeError(f"Webhook n8n rejeitou a chamada: HTTP {response.status_code}.")
    print(f"Webhook n8n aceitou a chamada: HTTP {response.status_code}; modo={mode}; run_id={run_id or 'local'}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Valida a configuração sem chamar o webhook")
    parser.add_argument("--modo", choices=["completo", "pautas"], default="completo")
    args = parser.parse_args()
    if args.check:
        webhook_config()
        print("Configuração do webhook n8n verificada.")
    else:
        notify_n8n(args.modo)
