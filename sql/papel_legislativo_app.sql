-- Papel da aplicação /legislativo. Idempotente e SEM senha: cria só o papel (NOLOGIN).
-- LOGIN e senha são definidos à mão em cada ambiente (ALTER ROLE legislativo_app LOGIN PASSWORD '...'),
-- e a senha fica apenas no .env do ambiente. Os grants são decididos em outra etapa.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'legislativo_app') THEN
        CREATE ROLE legislativo_app NOLOGIN;
    END IF;
END
$$;
