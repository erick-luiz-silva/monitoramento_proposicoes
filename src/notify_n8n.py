"""Notifica o n8n após a conclusão da carga, sem registrar credenciais."""

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
from urllib.parse import urlparse

import requests

import config  # noqa: F401 — carrega também o .env para execução local.

# Aviso de falha só do Senado: a carga grava, a notificação manda ao n8n (o e-mail sai
# com o aviso no topo). O job não falha por causa do Senado (decisão de 27/10/2026).
ARQUIVO_AVISO = Path(__file__).resolve().parent.parent / "logs" / "aviso_senado.txt"


def limpar_aviso_senado():
    try:
        ARQUIVO_AVISO.unlink(missing_ok=True)
    except OSError as exc:
        print(f"Não foi possível apagar o aviso do Senado: {exc}")


def gravar_aviso_senado(texto):
    """Nunca levanta: um problema ao gravar o aviso não pode derrubar a carga da Câmara."""
    print(f"::warning::{texto}")
    try:
        ARQUIVO_AVISO.parent.mkdir(parents=True, exist_ok=True)
        ARQUIVO_AVISO.write_text(texto, encoding="utf-8")
    except OSError as exc:
        print(f"Não foi possível gravar o aviso do Senado: {exc}")


def ler_aviso_senado():
    try:
        return ARQUIVO_AVISO.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def webhook_config():
    url = os.getenv("N8N_WEBHOOK_URL", "").strip()
    token = os.getenv("N8N_WEBHOOK_TOKEN", "").strip()
    if not url or not token:
        raise RuntimeError("Configure N8N_WEBHOOK_URL e N8N_WEBHOOK_TOKEN.")
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or not parsed.path.startswith("/webhook/"):
        raise RuntimeError("N8N_WEBHOOK_URL deve usar HTTPS e o endpoint de produção /webhook/.")
    return url, token


def notify_n8n(mode, status="sucesso"):
    url, token = webhook_config()
    run_id = os.getenv("GITHUB_RUN_ID")
    repository = os.getenv("GITHUB_REPOSITORY")
    payload = {
        "origem": "github_actions" if run_id else "local",
        "modo": mode,
        "status": status,
        "concluido_em": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "run_url": f"https://github.com/{repository}/actions/runs/{run_id}" if repository and run_id else None,
        "aviso_senado": ler_aviso_senado(),
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
    print(
        f"Webhook n8n aceitou a chamada: HTTP {response.status_code}; modo={mode}; "
        f"status={status}; run_id={run_id or 'local'}."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Valida a configuração sem chamar o webhook")
    parser.add_argument("--modo", choices=["completo", "pautas", "inclusao"], default="completo")
    parser.add_argument(
        "--status",
        choices=["sucesso", "falha"],
        default="sucesso",
        help="falha: avisa o n8n que a carga não terminou (e-mail de aviso, sem dados)",
    )
    args = parser.parse_args()
    if args.check:
        webhook_config()
        print("Configuração do webhook n8n verificada.")
    else:
        notify_n8n(args.modo, args.status)
