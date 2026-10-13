# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Data pipeline that monitors Brazilian Chamber of Deputies (Câmara dos Deputados) bills relevant to pig farming (suinocultura) for ABCS. Pulls from the public API (`https://dadosabertos.camara.leg.br/api/v2`), stores in PostgreSQL (Supabase in production) using a bronze/silver/gold medallion layout, consumed by Power BI and an n8n workflow. Code, comments, logs and docs are in Portuguese — keep it that way.

## Commands

Python version is pinned in `.python-version` (3.14); install from the lock file. Locally the deps live in `.venv/` — use `.venv/bin/python` (the system `python3` lacks them, so test discovery fails with an import error). Scripts are run from inside `src/` (they import siblings as top-level modules, e.g. `from db import get_connection`).

```bash
pip install -r requirements.lock

# Tests (no DB/API access — everything is mocked; same as CI in .github/workflows/tests.yml)
python -m compileall -q src tests
python -m unittest discover -s tests -v

# Single test
python -m unittest tests.test_pipeline.IncrementalTests.test_partial_bronze_failure_does_not_advance_window -v

# Pipeline (from src/, requires src/.env with DATABASE_URL or DB_* vars — see src/.env.example)
python setup_db.py          # applies sql/schema_bronze.sql, schema_silver.sql, schema_gold.sql (idempotent)
python load_dimensoes.py    # reloads silver.dim_tema and silver.dim_keyword (from keywords.py)
python pipeline.py          # daily full incremental run
python pipeline_pautas.py   # intraday events/agendas-only refresh

# One-time bootstrap of an empty database (after setup_db.py + load_dimensoes.py):
python extract_bronze.py    # historical bronze load for all TEMAS, desde 2023-02-01 em janelas de 90 dias (--desde, --pular-existentes, --reconciliar N)
python load_silver.py && python load_dim_deputado.py && python load_dim_orgao.py
python -c "from datetime import date; from load_eventos import executar_carga_eventos; executar_carga_eventos(date(2023,1,1), date.today())"
```

`src/executar.bat` is a legacy local Windows scheduler (gitignored, superseded by GitHub Actions) — don't extend it.

When updating dependencies: fresh venv with the pinned Python, install `requirements.txt`, regenerate with `python -m pip freeze > requirements.lock`, run tests.

## Architecture

**Layers**
- `bronze` — raw API JSON, append-only snapshots (`bronze.proposicoes_json` etc.) plus `bronze.controle_execucao`, which records each successful run's date window.
- `silver` — relational tables built entirely in SQL (`sql/transform_bronze_to_silver.sql`, `sql/transform_eventos_to_silver.sql`) executed by `load_silver.py`. Proposition tables take the latest bronze row per id and upsert; `silver.tramitacao` is historical and accumulates across all bronze rows. Dimension tables (`dim_deputado`, `dim_orgao`, `dim_tema`, `dim_keyword`) are loaded by their own Python scripts.
- `gold` — **views only** (`sql/schema_gold.sql`), no load step. Changing gold means editing the SQL and re-running `setup_db.py`.

**Keyword matching is a gold-only concern.** `src/keywords.py` defines `(rotulo, termo, termo_requerido)` tuples of POSIX regex fragments; `load_dimensoes.py` truncates and reloads them into `silver.dim_keyword`; `gold.vw_proposicao_keywords` matches with `~*` against both `ementa` and `keywords_camara` (the Câmara's own indexing field). Terms use `\m` word-start anchors to avoid substring false positives (e.g. "ave" in "grave"), and `termo_requerido` is a second regex that must also match to disambiguate generic terms (e.g. production vs. pet "bem-estar animal"). Adding a keyword = edit `keywords.py` + run `load_dimensoes.py`; no re-extraction needed.

**Extraction filter**: coarse filter by API theme codes (`TEMAS = [64, 48]` in `extract_incremental.py`), fine filter by keywords in gold.

**Daily flow** (`pipeline.py` → `extract_incremental.executar_carga_incremental`):
1. Compute window: `min(today-3, last successful data_fim - 3)` → today, so missed runs widen the next window automatically.
2. List ids per theme, load each into bronze (`load_bronze.carregar_proposicao_bronze` — details, authors, themes, tramitações per endpoint).
3. Load events/agendas for committees in a D-7..D+14 window (`load_eventos.py`).
4. Silver transform, then `dim_deputado` and `dim_orgao`.
5. Only then register both windows in `bronze.controle_execucao`.

**Failure semantics are deliberate and covered by tests**: any partial failure (a bronze endpoint, an event pauta, a deputado) must raise so the job fails, must roll back the aborted transaction so other rows still persist, and must *not* advance the incremental window. `pipeline_pautas.py` refreshes only events/pautas/relatores/órgãos and registers only an `eventos` window — it must never advance the `incremental` window. Preserve these invariants when touching loaders.

**Automation**: `.github/workflows/pipeline.yml` has no `schedule` (GitHub's cron delayed runs by hours or dropped them). Scheduling lives in n8n: workflow "Agendador – Monitoramento de Proposições" calls the GitHub `workflow_dispatch` API at 07:17 São Paulo with `modo=completo` and at 10h/14h with `modo=pautas`; the job picks the pipeline from `inputs.modo`. Change times in n8n, not in the YAML. Runs with `TZ=America/Sao_Paulo` (window dates depend on it). Before the load it runs `notify_n8n.py --check` and `check_environment.py` (verifies schemas and non-empty keywords). After success, `notify_n8n.py` POSTs to the n8n production webhook with `X-Webhook-Token` — it rejects test webhooks/plain HTTP and intentionally does not retry. The n8n webhook (workflow "Monitoramento de Proposições → Google Sheets") responds immediately, so HTTP 200 only means "received" — failures inside n8n (e.g. its own Postgres credential) show up only in n8n executions, not in Actions. Secrets (`DATABASE_URL`, `N8N_WEBHOOK_URL`, `N8N_WEBHOOK_TOKEN`) live in the GitHub environment named `DATABASE_URL`.

## Notes

- `BI/`, `*.pbix`, `*.pbit`, `*.abf` and PBIP local settings are gitignored (may contain embedded data) — never commit them.
- Partido/UF shown for authors are the deputy's *current* ones (from `dim_deputado`), by design.
- Open item: filtering archived propositions out of KPIs (situação codes 914/920/923/930/931/940, possibly others) and ~55 propositions with null `cod_situacao` — see README "Status do projeto".
