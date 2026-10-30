-- Papéis do sistema /legislativo. Idempotente e SEM senha: cria só os papéis (NOLOGIN).
-- legislativo_app: papel da aplicação. LOGIN e senha são definidos à mão em cada ambiente
--   (ALTER ROLE legislativo_app LOGIN PASSWORD '...'), e a senha fica apenas no .env do ambiente.
-- legislativo_n8n_leitura: papel do fluxo principal do n8n (e-mail diário; leituras e checkpoint, ver schema_contratos.sql).
-- legislativo_n8n: papel do n8n no fluxo de inclusão (RF08). Mesmo esquema: LOGIN e senha à mão,
--   e a senha fica só na credencial Postgres do n8n.
-- gestao_dono: dono restrito das funções SECURITY DEFINER de gestao (PRD §5). Nunca loga; os
--   privilégios dele são concedidos em schema_contratos.sql. O papel que aplica o setup precisa
--   ser membro dele para trocar o dono das funções e derrubá-las no próximo setup (no Supabase,
--   postgres tem CREATEROLE mas não é superusuário; quem cria o papel tem ADMIN e pode se incluir).
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'legislativo_app') THEN
        CREATE ROLE legislativo_app NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'legislativo_n8n') THEN
        CREATE ROLE legislativo_n8n NOLOGIN;
    END IF;
    -- legislativo_n8n_leitura: fluxo principal do n8n (e-mail diário, checkpoint de movimentações).
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'legislativo_n8n_leitura') THEN
        CREATE ROLE legislativo_n8n_leitura NOLOGIN;
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
