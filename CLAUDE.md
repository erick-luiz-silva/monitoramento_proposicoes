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
python setup_db.py          # applies sql/schema_bronze.sql, schema_silver.sql, seed_acompanhadas.sql, drop_api.sql, schema_gold.sql, schema_api.sql (idempotent)
python load_dimensoes.py    # reloads silver.dim_tema and silver.dim_keyword (from keywords.py), then refreshes api
python load_api.py          # refreshes the api_cache materialized views (all pipelines already do it at the end)
python pipeline.py          # daily full incremental run
python pipeline_pautas.py   # intraday events/agendas-only refresh
python pipeline_inclusao.py # loads acompanhadas still missing from bronze + silver + dims (modo=inclusao)

# One-time bootstrap of an empty database (after setup_db.py + load_dimensoes.py):
python extract_bronze.py    # historical bronze load for all TEMAS, desde 2023-02-01 em janelas de 90 dias (--desde, --ate, --ids 1,2,3, --so-listar, --pular-existentes, --reconciliar N, --pausa SEG); reconecta automaticamente se o banco derrubar a conexão
python load_silver.py && python load_dim_deputado.py && python load_dim_orgao.py
python -c "from datetime import date; from load_eventos import executar_carga_eventos; executar_carga_eventos(date(2023,1,1), date.today())"
```

Read-only audit tooling (local only, not part of the pipeline): `python google_auth.py` does the one-time Google OAuth consent and writes `src/token_google.json` (gitignored; `GOOGLE_TOKEN_JSON` env var in headless environments). Then `python comparar_acompanhamento.py [--keywords-candidatas]` compares the sheet (`GOOGLE_SHEET_MONITORAMENTO_ID`) with the DB, classifying each proposition A/B/C1/C2/NC and showing per-keyword precision from the "relevancia" column. Use it to try out new keywords before changing `keywords.py`. Its output goes to `data/` (gitignored).

`src/executar.bat` is a legacy local Windows scheduler (gitignored, superseded by GitHub Actions) — don't extend it.

When updating dependencies: fresh venv with the pinned Python, install `requirements.txt`, regenerate with `python -m pip freeze > requirements.lock`, run tests.

## Architecture

**Layers**
- `bronze` — raw API JSON, append-only snapshots (`bronze.proposicoes_json` etc.) plus `bronze.controle_execucao`, which records each successful run's date window.
- `silver` — relational tables built entirely in SQL (`sql/transform_bronze_to_silver.sql`, `sql/transform_eventos_to_silver.sql`) executed by `load_silver.py`. Proposition tables take the latest bronze row per id and upsert; `silver.tramitacao` is historical and accumulates across all bronze rows. Dimension tables (`dim_deputado`, `dim_orgao`, `dim_tema`, `dim_keyword`) are loaded by their own Python scripts.
- `gold` — **views only** (`sql/schema_gold.sql`), no load step. Changing gold means editing the SQL and re-running `setup_db.py`.
- `api` — what Power BI reads through the Supabase Data API (`sql/schema_api.sql`). The `anon` role has a 3 s `statement_timeout` and the gold views recompute the keyword regex on every call (2–4 s), so `api_cache` (not exposed) holds MATERIALIZED VIEWs of the six gold views the model uses (tramitações filtered to monitored propositions: ~8k rows instead of ~207k), and `api` exposes thin views over them that compute the clock-dependent columns (`dias_sem_movimentacao`, `status_alerta`) at read time — keep those rules identical to gold (a test compares them). The DB session is UTC and Câmara timestamps are naive Brasília time, so the clock is always `now() AT TIME ZONE 'America/Sao_Paulo'`; `status_alerta` checks the official `situacao = 'Cancelada'` before the date. `api.vw_ultima_carga` (not cached) gives the report its "data atualizada em" (last successful `incremental`/`eventos` run, in Brasília time) and a Brasília `data_referencia`, since `TODAY()` in the Service is UTC. `load_api.atualizar_api()` refreshes them CONCURRENTLY in one transaction at the end of every pipeline and of `load_dimensoes.py`; it is derived, so in the daily run it runs *after* the windows are registered and a failure only makes the job fail at the end. `setup_db.py` drops both schemas before `schema_gold.sql` (the MVs depend on gold) and recreates them with grants after. Exposed schemas in Supabase: `gold, api`. If the pipeline fails, Power BI keeps showing the last refreshed snapshot.

**Keyword matching is a gold-only concern.** `src/keywords.py` defines `(rotulo, termo, termo_requerido)` tuples of POSIX regex fragments; `load_dimensoes.py` truncates and reloads them into `silver.dim_keyword`; `gold.vw_proposicao_keywords` matches with `~*` against both `ementa` and `keywords_camara` (the Câmara's own indexing field). Terms use `\m` word-start anchors to avoid substring false positives (e.g. "ave" in "grave"), and `termo_requerido` is a second regex that must also match to disambiguate generic terms (e.g. production vs. pet "bem-estar animal"). Adding a keyword = edit `keywords.py` + run `load_dimensoes.py` (which also refreshes `api`); no re-extraction needed.

**Extraction filter**: coarse filter by API theme codes (`TEMAS = [64, 48, 66]`, defined only in `src/config.py`), fine filter by keywords in gold.

**Daily flow** (`pipeline.py` → `extract_incremental.executar_carga_incremental`):
1. Compute window: `min(today-14, last successful data_fim - 14)` → today, so missed runs widen the next window automatically.
2. List ids per theme, add every id in `silver.proposicao_acompanhada` (so tracked ones refresh daily even off-theme or idle), load each into bronze (`load_bronze.carregar_proposicao_bronze` — details, authors, themes, tramitações per endpoint).
3. Reconciliation (`extract_bronze.executar_reconciliacao`): list the last 90 days and load ids missing from bronze. This is the main path for *new* propositions: the Câmara assigns the theme 1–2 weeks after presentation. (Empty `keywords` is structural by type — RIC/INC never get them — so it is *not* a reload criterion; a previous attempt reloaded ~3k ids/day and blew the job timeout.)
4. Load events/agendas for committees (CAPADR, CCJC, CMADS, PLEN) in a D-7..D+14 window (`load_eventos.py`). In gold, `vw_pautas_monitoradas` links agenda items to monitored propositions, mostly indirectly through the item's "proposição relacionada". `vw_audiencias_de_interesse` matches public hearings by keyword on `evento.descricao`, because hearings have no structured link to a proposition.
5. Silver transform, then `dim_deputado` (selective: missing from the dim, authors of ids loaded in this run, plus a rolling refresh of rows >7 days old capped at 1/7 of the dim) and `dim_orgao`.
6. Only then register `incremental` and `eventos` in `bronze.controle_execucao`, plus `reconciliacao` if the reconciliation was complete.

**Tracked propositions and radar** (decided by the business owner, Oct 2026):
- `silver.proposicao_acompanhada` = always-tracked propositions: `planilha_antiga` (one-time snapshot of the old "Acompanhamento manual" tab, `sql/seed_acompanhadas.sql`) and `inclusao_manual` (inserted by the n8n "Inclusão manual de proposições" workflow when the owner adds a row with only `identificacao` to the "Proposições" tab; it then dispatches `modo=inclusao`). The old tab is audit-only: no automation reads or writes it.
- `gold.vw_monitoramento` = keyword matches ∪ tracked; `acompanhada` and `em_radar` columns appended at the end (`em_radar` = tracked OR keyword match presented since 2026-09-01 — "from now on", no history). Pending-evaluation e-mails use `em_radar` and go out only in `modo=completo` (once a day); each scheduled pauta is e-mailed at most once per Brasília day (`bronze.alerta_pauta`, written by n8n after sending), so `pautas` runs alert only new or rescheduled ones; relevância SIM/NÃO lives in the sheet (Power BI reads it there) and is passed to n8n queries as parameters, never stored in the DB.
- `gold.vw_movimentacoes` = not-yet-alerted tramitações (`silver.tramitacao.data_extracao` = first seen) after the latest `alerta_movimentacoes` row in `controle_execucao`, which n8n writes only after the e-mail is sent.

**Failure semantics are deliberate and covered by tests**: any partial failure (a bronze endpoint, an event pauta, a deputado) must raise so the job fails, must roll back the aborted transaction so other rows still persist, and must *not* advance the incremental window. **Deliberate exception:** a reconciliation failure does not block the `incremental`/`eventos` windows (a chronically failing id would otherwise stay "missing" for 90 days and freeze the window) — it skips the `reconciliacao` row and raises at the end so the job still fails. `pipeline_pautas.py` refreshes only events/pautas/relatores/órgãos and registers only an `eventos` window — it must never advance the `incremental` window. Preserve these invariants when touching loaders.

**Automation**: `.github/workflows/pipeline.yml` has no `schedule` (GitHub's cron delayed runs by hours or dropped them). Scheduling lives in n8n: workflow "Agendador – Monitoramento de Proposições" calls the GitHub `workflow_dispatch` API at 07:17 São Paulo with `modo=completo` and at 10h/14h with `modo=pautas`; the job picks the pipeline from `inputs.modo`. Change times in n8n, not in the YAML. Runs with `TZ=America/Sao_Paulo` (window dates depend on it). Before the load it runs `notify_n8n.py --check` and `check_environment.py` (verifies schemas and non-empty keywords). Modes: `completo`, `pautas`, `inclusao`. After success, `notify_n8n.py` POSTs to the n8n production webhook with `X-Webhook-Token` — it rejects test webhooks/plain HTTP and intentionally does not retry. On failure, an `if: failure()` step posts `status=falha` so n8n can e-mail that the run failed. The n8n webhook (workflow "Monitoramento de Proposições → Google Sheets") responds immediately, so HTTP 200 only means "received" — failures inside n8n (e.g. its own Postgres credential) show up only in n8n executions, not in Actions. Secrets (`DATABASE_URL`, `N8N_WEBHOOK_URL`, `N8N_WEBHOOK_TOKEN`) live in the GitHub environment named `DATABASE_URL`. Input `ambiente` (`producao` default, `homologacao`) picks the environment: `homologacao` has its own three secrets (homologation DB and the homologation n8n webhook), and `concurrency` is grouped per ambiente so a homologation dispatch never replaces a pending production one. Dispatches that omit `ambiente` (Agendador, planilha workflow) stay on production. `/legislativo` inclusion requests are processed by the n8n workflow "Legislativo — inclusão" (webhook from the app + 15-min cron): `gestao.reivindicar_inclusao` → Câmara lookup → `registrar_inclusao_resolvida`/`falhar_inclusao` → `modo=inclusao` → `concluir_inclusoes`, using the restricted role `legislativo_n8n`.

## Notes

- The PBIP project in `BI/` is versioned in a **public** repo. `BI/.env`, `*.pbix`, `*.pbit`, `*.abf` (incl. `.pbi/cache.abf`) and PBIP local settings stay gitignored — never commit them. The Supabase URL/anon key and the sheet link in the `.tmdl` files are replaced by placeholders on commit by the `segredos-pbi` git filter (`.gitattributes` → `BI/filtro_segredos.py`; local `git config` per clone, see README) and restored on checkout from the `.env` files; `tests/test_segredos.py` fails if a key or sheet link reaches the index. Never put an access value anywhere else in the repo. The `anon` role is read-only (SELECT on `api` and `gold`; write grants revoked in `schema_api.sql`).
- Public report ("Publicar na Web") link is in the README header.
- Partido/UF shown for authors are the deputy's *current* ones (from `dim_deputado`), by design.
- Open item: filtering archived propositions out of KPIs (situação codes 914/920/923/930/931/940, possibly others) and ~55 propositions with null `cod_situacao` — see README "Status do projeto".
