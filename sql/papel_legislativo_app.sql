-- Papéis do sistema /legislativo. Idempotente e SEM senha: cria só os papéis (NOLOGIN).
-- legislativo_app: papel da aplicação. LOGIN e senha são definidos à mão em cada ambiente
--   (ALTER ROLE legislativo_app LOGIN PASSWORD '...'), e a senha fica apenas no .env do ambiente.
-- gestao_dono: dono restrito das funções SECURITY DEFINER de gestao (PRD §5). Nunca loga; os
--   privilégios dele são concedidos em schema_contratos.sql. O papel que aplica o setup precisa
--   ser membro dele para trocar o dono das funções e derrubá-las no próximo setup (no Supabase,
--   postgres tem CREATEROLE mas não é superusuário; quem cria o papel tem ADMIN e pode se incluir).
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'legislativo_app') THEN
        CREATE ROLE legislativo_app NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'gestao_dono') THEN
        CREATE ROLE gestao_dono NOLOGIN NOINHERIT;
    END IF;
    -- No Postgres 16+, quem cria o papel com CREATEROLE recebe só ADMIN (sem SET): ALTER ... OWNER
    -- TO gestao_dono exige poder fazer SET ROLE nele.
    IF NOT pg_has_role(current_user, 'gestao_dono', 'SET') THEN
        EXECUTE format('GRANT gestao_dono TO %I WITH SET TRUE', current_user);
    END IF;
END
$$;
