#!/usr/bin/env bash
# Copia os dados oficiais (silver + bronze.controle_execucao) da produção para a homologação.
# Só LÊ a produção (pg_dump); escreve apenas em DATABASE_URL_HOMOLOGACAO.
# Pré-requisito: setup_db.py já aplicado na homologação. Gold/api derivam da silver (atualizar_api no fim).
# Uso (a partir da raiz do repo): scripts/copiar_dados_oficiais.sh
# Requer docker (não há psql/pg_dump local); usa postgres:17.
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
set -a; . "$RAIZ/src/.env"; set +a

: "${DATABASE_URL:?DATABASE_URL (produção, só leitura) ausente em src/.env}"
: "${DATABASE_URL_HOMOLOGACAO:?DATABASE_URL_HOMOLOGACAO ausente em src/.env}"
if [ "$DATABASE_URL" = "$DATABASE_URL_HOMOLOGACAO" ]; then
    echo "Recusado: o destino é igual à produção." >&2
    exit 1
fi

IMG=postgres:17
DOCKER=(docker run --rm -i --network host -e DATABASE_URL -e DATABASE_URL_HOMOLOGACAO -v "$RAIZ/data:/w" "$IMG")
mkdir -p "$RAIZ/data"
trap 'rm -f "$RAIZ/data/dump_silver.sql" "$RAIZ/data/dump_controle.sql"' EXIT

echo "Dump da produção (somente leitura)..."
# Dois dumps: -t anula -n quando combinados.
"${DOCKER[@]}" sh -c 'pg_dump "$DATABASE_URL" --data-only --no-owner --no-privileges -n silver -f /w/dump_silver.sql'
"${DOCKER[@]}" sh -c 'pg_dump "$DATABASE_URL" --data-only --no-owner --no-privileges -t bronze.controle_execucao -f /w/dump_controle.sql'

echo "Truncando e restaurando na homologação..."
"${DOCKER[@]}" sh -c 'psql "$DATABASE_URL_HOMOLOGACAO" -v ON_ERROR_STOP=1 -q' <<'SQL'
DO $$
DECLARE t text;
BEGIN
    SELECT string_agg(format('%I.%I', schemaname, tablename), ', ') INTO t
    FROM pg_tables WHERE schemaname = 'silver';
    EXECUTE 'TRUNCATE ' || t || ', bronze.controle_execucao RESTART IDENTITY CASCADE';
END
$$;
SQL
"${DOCKER[@]}" sh -c 'psql "$DATABASE_URL_HOMOLOGACAO" -v ON_ERROR_STOP=1 -q -f /w/dump_silver.sql -f /w/dump_controle.sql' >/dev/null

echo "Ajustando sequences..."
"${DOCKER[@]}" sh -c 'psql "$DATABASE_URL_HOMOLOGACAO" -v ON_ERROR_STOP=1 -q' <<'SQL'
DO $$
DECLARE r record;
BEGIN
    FOR r IN
        SELECT n.nspname, c.relname, a.attname, pg_get_serial_sequence(format('%I.%I', n.nspname, c.relname), a.attname) AS seq
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
        WHERE c.relkind = 'r' AND (n.nspname = 'silver' OR (n.nspname = 'bronze' AND c.relname = 'controle_execucao'))
    LOOP
        IF r.seq IS NOT NULL THEN
            EXECUTE format('SELECT setval(%L, coalesce((SELECT max(%I) FROM %I.%I), 0) + 1, false)', r.seq, r.attname, r.nspname, r.relname);
        END IF;
    END LOOP;
END
$$;
SQL

echo "Atualizando api_cache..."
(cd "$RAIZ/src" && DATABASE_URL="$DATABASE_URL_HOMOLOGACAO" "$RAIZ/.venv/bin/python" load_api.py)

echo "Contagens na homologação:"
"${DOCKER[@]}" sh -c 'psql "$DATABASE_URL_HOMOLOGACAO" -tA' <<'SQL'
SELECT 'silver.proposicao: ' || count(*) FROM silver.proposicao
UNION ALL SELECT 'silver.tramitacao: ' || count(*) FROM silver.tramitacao
UNION ALL SELECT 'api_cache.vw_monitoramento: ' || count(*) FROM api_cache.vw_monitoramento
UNION ALL SELECT 'silver.dim_keyword: ' || count(*) FROM silver.dim_keyword;
SQL
