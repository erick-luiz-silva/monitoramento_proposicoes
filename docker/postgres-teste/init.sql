-- Prepara um Postgres limpo (postgres:17) com o que o Supabase já fornece:
-- papéis anon/authenticated/legislativo_app e a extensão unaccent no schema extensions.
-- Usado no Docker local (scripts/postgres_teste.sh) e no job de CI.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN CREATE ROLE anon NOLOGIN; END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN CREATE ROLE authenticated NOLOGIN; END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'legislativo_app') THEN CREATE ROLE legislativo_app NOLOGIN; END IF;
END
$$;
CREATE SCHEMA IF NOT EXISTS extensions;
CREATE EXTENSION IF NOT EXISTS unaccent WITH SCHEMA extensions;
