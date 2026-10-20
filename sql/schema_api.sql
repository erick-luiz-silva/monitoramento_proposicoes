-- Camada lida pelo Power BI via Data API do Supabase (PostgREST, role anon).
-- A anon tem statement_timeout de 3 s e as views gold recalculam o regex de keywords
-- a cada chamada (2–4 s), então o BI lê cópias prontas:
--   api_cache: MATERIALIZED VIEWs sobre a gold, NÃO expostas na API, atualizadas no fim
--              de cada carga por load_api.atualizar_api() (REFRESH ... CONCURRENTLY, que
--              não bloqueia leitura; por isso cada uma tem índice único).
--   api:       views finas sobre o cache, as únicas expostas à anon. Colunas que dependem
--              do relógio (dias_sem_movimentacao, status_alerta) são calculadas aqui, na
--              leitura, para não congelarem no valor do último refresh.
-- Mesmos nomes da gold, para o modelo do Power BI só trocar o schema (Accept-Profile).
-- setup_db.py derruba os dois schemas ANTES de schema_gold.sql (drop_api.sql) e recria
-- tudo aqui: CREATE ... IF NOT EXISTS não aplicaria mudança de definição, e as MVs
-- impediriam alterar as views gold de que dependem. Os GRANTs vêm depois, porque o DROP
-- os apaga.

CREATE SCHEMA api_cache;
CREATE SCHEMA api;

CREATE MATERIALIZED VIEW api_cache.vw_monitoramento AS
SELECT id_proposicao, identificacao, ementa, autor_principal, tipo_autor_principal,
       partido_autor_principal, uf_autor_principal, situacao_atual, orgao_atual,
       nome_orgao_atual, ultima_movimentacao, data_ultima_movimentacao,
       keywords_encontradas, link_direto, acompanhada, em_radar, sigla_tipo, data_apresentacao
FROM gold.vw_monitoramento;
CREATE UNIQUE INDEX ON api_cache.vw_monitoramento (id_proposicao);

CREATE MATERIALIZED VIEW api_cache.vw_proposicao_keywords AS
SELECT id_proposicao, keywords_encontradas
FROM gold.vw_proposicao_keywords;
CREATE UNIQUE INDEX ON api_cache.vw_proposicao_keywords (id_proposicao);

CREATE MATERIALIZED VIEW api_cache.vw_proposicoes_sem_keyword AS
SELECT id_proposicao, identificacao, ementa, link_direto
FROM gold.vw_proposicoes_sem_keyword;
CREATE UNIQUE INDEX ON api_cache.vw_proposicoes_sem_keyword (id_proposicao);

-- Só as tramitações das proposições monitoradas (o relatório só as alcança pela relação
-- com vw_monitoramento): ~207 mil linhas viram alguns milhares. Filtra pelo cache, que
-- load_api atualiza antes deste na mesma transação.
CREATE MATERIALIZED VIEW api_cache.vw_tramitacoes AS
SELECT t.id_proposicao, t.identificacao, t.sequencia, t.data_hora, t.sigla_orgao,
       t.descricao_situacao, t.descricao_tramitacao, t.despacho, t.nome_orgao
FROM gold.vw_tramitacoes t
WHERE t.id_proposicao IN (SELECT id_proposicao FROM api_cache.vw_monitoramento);
CREATE UNIQUE INDEX ON api_cache.vw_tramitacoes (id_proposicao, sequencia);

-- Item de pauta não tem chave estável (silver.evento_pauta é apagada e reinserida):
-- _id posicional, só para o índice único do REFRESH CONCURRENTLY e ordem de paginação.
CREATE MATERIALIZED VIEW api_cache.vw_pautas_monitoradas AS
SELECT row_number() OVER (ORDER BY id_evento, id_proposicao, topico, titulo, nome_relator, situacao_item) AS _id,
       id_evento, data_hora_inicio, sigla_orgao, nome_orgao, descricao_tipo, situacao_evento,
       topico, titulo, identificacao, ementa, nome_relator, partido_relator, uf_relator,
       uri_votacao, situacao_item, id_proposicao, acompanhada, em_radar
FROM gold.vw_pautas_monitoradas;
CREATE UNIQUE INDEX ON api_cache.vw_pautas_monitoradas (_id);

CREATE MATERIALIZED VIEW api_cache.vw_audiencias_de_interesse AS
SELECT id_evento, data_hora_inicio, sigla_orgao, nome_orgao, situacao_evento, assunto,
       keywords_encontradas, url_registro
FROM gold.vw_audiencias_de_interesse;
CREATE UNIQUE INDEX ON api_cache.vw_audiencias_de_interesse (id_evento);

-- Views expostas. Rodam com os privilégios do dono, então a anon só precisa de SELECT
-- nelas, nunca no api_cache. As regras de relógio repetem as da gold — mantenha iguais.
-- A sessão do banco é UTC e os horários da Câmara são de Brasília sem fuso: o relógio
-- é sempre now() AT TIME ZONE 'America/Sao_Paulo', senão uma pauta vira "encerrada"
-- 3 h antes de começar.
CREATE VIEW api.vw_monitoramento AS
SELECT id_proposicao, identificacao, ementa, autor_principal, tipo_autor_principal,
       partido_autor_principal, uf_autor_principal, situacao_atual, orgao_atual,
       nome_orgao_atual, ultima_movimentacao, data_ultima_movimentacao,
       ((now() AT TIME ZONE 'America/Sao_Paulo')::date - data_ultima_movimentacao::date) AS dias_sem_movimentacao,
       keywords_encontradas, link_direto, acompanhada, em_radar, sigla_tipo, data_apresentacao
FROM api_cache.vw_monitoramento;

CREATE VIEW api.vw_proposicao_keywords AS
SELECT id_proposicao, keywords_encontradas FROM api_cache.vw_proposicao_keywords;

CREATE VIEW api.vw_proposicoes_sem_keyword AS
SELECT id_proposicao, identificacao, ementa, link_direto FROM api_cache.vw_proposicoes_sem_keyword;

CREATE VIEW api.vw_tramitacoes AS
SELECT id_proposicao, identificacao, sequencia, data_hora, sigla_orgao, descricao_situacao,
       descricao_tramitacao, despacho, nome_orgao
FROM api_cache.vw_tramitacoes;

CREATE VIEW api.vw_pautas_monitoradas AS
SELECT _id, id_evento, data_hora_inicio, sigla_orgao, nome_orgao, descricao_tipo, situacao_evento,
       topico, titulo, identificacao, ementa, nome_relator, partido_relator, uf_relator,
       uri_votacao, situacao_item,
       CASE
           WHEN situacao_evento = 'Cancelada' THEN 'Cancelada'
           WHEN data_hora_inicio > (now() AT TIME ZONE 'America/Sao_Paulo') THEN 'Agendado'
           WHEN uri_votacao IS NOT NULL THEN 'Votado'
           ELSE 'Encerrado sem votação'
       END AS status_alerta,
       id_proposicao, acompanhada, em_radar
FROM api_cache.vw_pautas_monitoradas;

CREATE VIEW api.vw_audiencias_de_interesse AS
SELECT id_evento, data_hora_inicio, sigla_orgao, nome_orgao, situacao_evento, assunto,
       keywords_encontradas, url_registro,
       CASE
           WHEN situacao_evento = 'Cancelada' THEN 'Cancelada'
           WHEN data_hora_inicio > (now() AT TIME ZONE 'America/Sao_Paulo') THEN 'Agendada'
           ELSE 'Realizada'
       END AS status_alerta
FROM api_cache.vw_audiencias_de_interesse;

-- "Dados atualizados em" do relatório: a última carga que terminou bem, não a hora do
-- refresh do Power BI (que roda mesmo se o pipeline falhar). Sem cache: lê
-- controle_execucao direto, poucas linhas. executado_em é gravado em UTC (sessão UTC).
-- data_referencia é o "hoje" de Brasília no momento da leitura, para o relatório não
-- usar TODAY() (UTC no Service).
CREATE VIEW api.vw_ultima_carga AS
SELECT
    (max(executado_em) FILTER (WHERE tipo_carga = 'incremental')
        AT TIME ZONE 'UTC') AT TIME ZONE 'America/Sao_Paulo' AS ultima_carga_diaria,
    (max(executado_em) FILTER (WHERE tipo_carga = 'eventos')
        AT TIME ZONE 'UTC') AT TIME ZONE 'America/Sao_Paulo' AS ultima_carga_pautas,
    (now() AT TIME ZONE 'America/Sao_Paulo')::date AS data_referencia
FROM bronze.controle_execucao;

REVOKE ALL ON SCHEMA api_cache FROM PUBLIC;
GRANT USAGE ON SCHEMA api TO anon;
GRANT SELECT ON ALL TABLES IN SCHEMA api TO anon;

-- O Supabase já recarrega o cache do PostgREST em DDL; o NOTIFY garante (sai no commit).
NOTIFY pgrst, 'reload schema';
