-- Sondagem de privilégios do sistema /legislativo. Só leitura (nenhum DDL, nenhum DML).
-- Uma linha por verificação, com o resultado esperado na própria linha. Divergência = ok false.
-- Esperado: nenhuma linha com ok = false. Rodar depois de cada setup_db no banco de produção e
-- de homologação, com o admin (DATABASE_URL conferida antes: current_database() e o ref do projeto).
--   psql "$DATABASE_URL" -f sql/sondagem_privilegios.sql
-- Cobre: anon, authenticated e PUBLIC sem acesso a gestao, contrato e api_cache (schema, tabela e
-- função); a única relação exposta é api.vw_painel_decisoes, com as colunas aprovadas (CA12).

WITH papeis(papel) AS (VALUES ('anon'), ('authenticated')),
esquemas(nome) AS (VALUES ('gestao'), ('contrato'), ('api_cache')),
checagens AS (
    -- schema: sem USAGE para anon/authenticated/PUBLIC
    SELECT 'schema ' || p.papel || ': USAGE em ' || e.nome AS verificacao,
           'false' AS esperado,
           has_schema_privilege(p.papel, e.nome, 'USAGE')::text AS obtido
    FROM papeis p CROSS JOIN esquemas e
    UNION ALL
    SELECT 'schema PUBLIC: USAGE em ' || e.nome,
           'false',
           EXISTS (SELECT 1 FROM pg_namespace n, aclexplode(n.nspacl) a
                   WHERE n.nspname = e.nome AND a.grantee = 0 AND a.privilege_type = 'USAGE')::text
    FROM esquemas e
    UNION ALL
    -- tabelas e views de gestao, contrato e api_cache: nenhum SELECT para anon/authenticated
    SELECT 'tabela ' || c.relname_completo || ': SELECT para ' || p.papel,
           'false',
           has_table_privilege(p.papel, c.oid, 'SELECT')::text
    FROM papeis p
    CROSS JOIN (SELECT c.oid, n.nspname || '.' || c.relname AS relname_completo
                FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname IN ('gestao', 'contrato', 'api_cache') AND c.relkind IN ('r', 'v', 'm', 'p')) c
    UNION ALL
    SELECT 'tabela ' || n.nspname || '.' || c.relname || ': SELECT para PUBLIC',
           'false',
           EXISTS (SELECT 1 FROM aclexplode(c.relacl) a WHERE a.grantee = 0 AND a.privilege_type = 'SELECT')::text
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname IN ('gestao', 'contrato', 'api_cache') AND c.relkind IN ('r', 'v', 'm', 'p')
    UNION ALL
    -- funções de gestao (não gatilho): nenhum EXECUTE para anon/authenticated/PUBLIC
    SELECT 'função ' || p.oid::regprocedure::text || ': EXECUTE para ' || r.papel,
           'false',
           has_function_privilege(r.papel, p.oid, 'EXECUTE')::text
    FROM pg_proc p
    CROSS JOIN papeis r
    WHERE p.pronamespace = 'gestao'::regnamespace AND p.prorettype <> 'trigger'::regtype
    UNION ALL
    SELECT 'função ' || p.oid::regprocedure::text || ': EXECUTE para PUBLIC',
           'false',
           (p.proacl IS NULL OR EXISTS (SELECT 1 FROM aclexplode(p.proacl) a WHERE a.grantee = 0 AND a.privilege_type = 'EXECUTE'))::text
    FROM pg_proc p
    WHERE p.pronamespace = 'gestao'::regnamespace AND p.prorettype <> 'trigger'::regtype
    UNION ALL
    -- a projeção do painel é legível pela anon, com as colunas aprovadas (CA12) e nada além delas
    SELECT 'api.vw_painel_decisoes: SELECT para anon',
           'true',
           has_table_privilege('anon', 'api.vw_painel_decisoes', 'SELECT')::text
    UNION ALL
    SELECT 'api.vw_painel_decisoes: colunas',
           'id_proposicao,casa,uuid_projeto,relevancia,posicao,prioridade,em_carteira',
           coalesce((SELECT string_agg(column_name::text, ',' ORDER BY ordinal_position)
                     FROM information_schema.columns
                     WHERE table_schema = 'api' AND table_name = 'vw_painel_decisoes'), '(ausente)')
    UNION ALL
    -- o dono das funções de gestao é o restrito, e ele não loga nem vira superusuário
    SELECT 'funções de gestao: dono',
           'gestao_dono',
           coalesce((SELECT string_agg(DISTINCT pg_get_userbyid(p.proowner), ',')
                     FROM pg_proc p
                     WHERE p.pronamespace = 'gestao'::regnamespace AND p.prorettype <> 'trigger'::regtype), '(nenhuma)')
    UNION ALL
    SELECT 'gestao_dono: sem login, superusuário ou CREATEROLE',
           'false',
           coalesce((SELECT (rolcanlogin OR rolsuper OR rolcreaterole)::text FROM pg_roles WHERE rolname = 'gestao_dono'), 'ausente')
)
SELECT verificacao, esperado, obtido, obtido = esperado AS ok
FROM checagens
ORDER BY ok, verificacao;
