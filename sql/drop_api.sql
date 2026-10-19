-- Aplicado por setup_db.py ANTES de schema_gold.sql: as materialized views do api_cache
-- dependem das views gold e impediriam alterá-las. schema_api.sql recria tudo depois.
DROP SCHEMA IF EXISTS api CASCADE;
DROP SCHEMA IF EXISTS api_cache CASCADE;
