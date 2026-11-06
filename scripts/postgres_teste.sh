#!/usr/bin/env bash
# Sobe um postgres:17 descartável em Docker para tests/test_sql_local.py.
# Uso: eval "$(scripts/postgres_teste.sh)"   -> exporta TEST_DATABASE_URL
#      scripts/postgres_teste.sh parar       -> remove o contêiner
set -euo pipefail
NOME=postgres-teste-monitoramento
PORTA="${PORTA_POSTGRES_TESTE:-55432}"
RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ "${1:-}" = "parar" ]; then
    docker rm -f "$NOME" >/dev/null 2>&1 || true
    exit 0
fi

docker rm -f "$NOME" >/dev/null 2>&1 || true
docker run -d --name "$NOME" -e POSTGRES_PASSWORD=teste -p "127.0.0.1:${PORTA}:5432" \
    -v "$RAIZ/docker/postgres-teste/init.sql:/docker-entrypoint-initdb.d/init.sql:ro" \
    postgres:17 >/dev/null
# O init.sql roda num servidor temporário só com socket; sondar por TCP garante o servidor definitivo.
PRONTO=0
for _ in $(seq 1 60); do
    if docker exec -e PGPASSWORD=teste "$NOME" psql -h 127.0.0.1 -U postgres -tAc "SELECT 1 FROM pg_namespace WHERE nspname='extensions'" 2>/dev/null | grep -q 1; then
        PRONTO=1
        break
    fi
    sleep 1
done
if [ "$PRONTO" != 1 ]; then
    echo "Postgres de teste não ficou pronto a tempo." >&2
    exit 1
fi
echo "export TEST_DATABASE_URL=postgresql://postgres:teste@127.0.0.1:${PORTA}/postgres"
