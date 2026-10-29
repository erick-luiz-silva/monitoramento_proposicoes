-- Contratos do sistema /legislativo (PRD RN03, RN05, RN06, RN07, RF02, RF03, RF08, RF09, RF10).
-- Recriado a cada setup_db.py, DEPOIS de schema_api.sql e de papel_legislativo_app.sql, na
-- mesma transação. Três partes:
--   contrato: views privadas (nunca expostas na Data API) que cruzam api_cache, gestao e
--             silver.proposicao (só cod_situacao, que o cache não tem). É o que a aplicação lê.
--   gestao.*: funções de negócio SECURITY DEFINER, as únicas escritas da aplicação e do n8n.
--             As TABELAS de gestao ficam em schema_gestao.sql e nunca são derrubadas.
--   api.vw_painel_decisoes: a única view de api que lê gestao (painel público, colunas fixas).
-- Relógio: sempre now() AT TIME ZONE 'America/Sao_Paulo' (sessão UTC; horários da Câmara são
-- de Brasília sem fuso).

DROP SCHEMA IF EXISTS contrato CASCADE;
DROP VIEW IF EXISTS api.vw_painel_decisoes;

-- O CASCADE de api_cache/contrato não alcança corpos plpgsql, e CREATE OR REPLACE não troca
-- assinatura nem tipo de retorno (deixaria a versão velha viva, com os grants dela). Toda função
-- de gestao que não é de gatilho pertence a este arquivo: derruba todas, inclusive assinaturas
-- antigas, e recria abaixo. O gatilho do histórico imutável é de schema_gestao.sql e fica.
DO $$
DECLARE
    f regprocedure;
BEGIN
    FOR f IN
        SELECT p.oid::regprocedure
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'gestao' AND p.prorettype <> 'trigger'::regtype
    LOOP
        EXECUTE format('DROP FUNCTION %s', f);
    END LOOP;
END
$$;

CREATE SCHEMA contrato;

-- ---------------------------------------------------------------------------------------------
-- contrato.vw_associacao — associação gravada (gestao.projeto_proposicao) com o alias da
-- reconciliação resolvido: segue projeto.substituido_por até o fim (até 20 saltos; um ciclo
-- deixa a versão sem associação). Uma linha por id_proposicao associado.
--   id_proposicao, uuid_projeto (final), uuid_gravado (o da linha de associação)
-- ---------------------------------------------------------------------------------------------
CREATE VIEW contrato.vw_associacao AS
WITH RECURSIVE cadeia AS (
    SELECT uuid AS uuid_origem, uuid AS uuid_atual, substituido_por, 0 AS saltos
    FROM gestao.projeto
    UNION ALL
    SELECT c.uuid_origem, p.uuid, p.substituido_por, c.saltos + 1
    FROM cadeia c
    JOIN gestao.projeto p ON p.uuid = c.substituido_por
    WHERE c.saltos < 20
)
SELECT pp.id_proposicao, c.uuid_atual AS uuid_projeto, pp.uuid_projeto AS uuid_gravado
FROM gestao.projeto_proposicao pp
JOIN cadeia c ON c.uuid_origem = pp.uuid_projeto AND c.substituido_por IS NULL;

-- ---------------------------------------------------------------------------------------------
-- contrato.vw_versao — uma linha por versão legislativa de api_cache.vw_monitoramento (versões
-- fora do cache, sem keyword e não acompanhadas, não são consideradas).
-- uuid_projeto (RN03.6): a associação direta da versão; sem ela, o UUID único das versões
-- associadas do grupo (chave_projeto); com UUIDs diferentes no grupo, NULL (vai à conferência).
-- chave_agrupamento: a unidade de projeto das telas = uuid_projeto, ou 'k' || chave_projeto
-- quando ainda não há UUID. A chave 'k…' MUDA quando entra um vínculo novo (chave_projeto é o
-- menor id do grupo); só o UUID é estável — links e marcadores usam o UUID ou o id_proposicao.
-- tipo_encerramento: 'arquivada' | 'norma' | 'remessa' | NULL, por gestao.situacao_encerramento
-- (com cod_situacao: compara o código; sem ele: o texto, sem caixa nem acento — Senado).
-- sem_situacao: a versão não tem dado de situação (nem texto nem código).
-- grupo_com_projetos_diferentes / projeto_em_grupos_diferentes: casos da conferência (RN03.6).
-- ---------------------------------------------------------------------------------------------
CREATE VIEW contrato.vw_versao AS
WITH versao AS (
    SELECT m.*, a.uuid_projeto AS uuid_associado, p.cod_situacao
    FROM api_cache.vw_monitoramento m
    LEFT JOIN contrato.vw_associacao a ON a.id_proposicao = m.id_proposicao
    LEFT JOIN silver.proposicao p ON p.id_proposicao = m.id_proposicao
),
grupo AS (
    SELECT chave_projeto,
           count(DISTINCT uuid_associado) AS qtd_uuids,
           min(uuid_associado::text)::uuid AS uuid_unico
    FROM versao
    GROUP BY chave_projeto
),
uuid_em_grupos AS (
    SELECT uuid_associado, count(DISTINCT chave_projeto) AS qtd_grupos
    FROM versao
    WHERE uuid_associado IS NOT NULL
    GROUP BY uuid_associado
),
situacao AS (
    SELECT casa, cod_situacao, lower(extensions.unaccent(texto_situacao)) AS texto, tipo
    FROM gestao.situacao_encerramento
),
resolvida AS (
    SELECT v.*,
           coalesce(v.uuid_associado, CASE WHEN g.qtd_uuids = 1 THEN g.uuid_unico END) AS uuid_resolvido,
           g.qtd_uuids > 1 AS grupo_com_projetos_diferentes,
           coalesce(ug.qtd_grupos > 1, false) AS projeto_em_grupos_diferentes
    FROM versao v
    JOIN grupo g ON g.chave_projeto = v.chave_projeto
    LEFT JOIN uuid_em_grupos ug ON ug.uuid_associado = v.uuid_associado
)
SELECT
    r.id_proposicao,
    r.casa,
    r.chave_projeto,
    r.uuid_resolvido AS uuid_projeto,
    coalesce(r.uuid_resolvido::text, 'k' || r.chave_projeto) AS chave_agrupamento,
    r.uuid_associado IS NOT NULL AS associada,
    r.grupo_com_projetos_diferentes,
    r.projeto_em_grupos_diferentes,
    r.identificacao,
    r.identificacao_casa,
    r.sigla_tipo,
    r.ementa,
    r.autor_principal,
    r.tipo_autor_principal,
    r.partido_autor_principal,
    r.uf_autor_principal,
    r.situacao_atual,
    r.cod_situacao,
    r.orgao_atual,
    r.nome_orgao_atual,
    r.ultima_movimentacao,
    r.data_ultima_movimentacao,
    r.data_apresentacao,
    r.keywords_encontradas,
    r.link_direto,
    r.acompanhada,
    r.em_radar,
    r.ids_vinculados,
    enc.tipo AS tipo_encerramento,
    (r.situacao_atual IS NULL AND r.cod_situacao IS NULL) AS sem_situacao
FROM resolvida r
LEFT JOIN LATERAL (
    SELECT CASE
               WHEN bool_or(s.tipo = 'remessa') THEN 'remessa'
               WHEN bool_or(s.tipo = 'norma') THEN 'norma'
               WHEN bool_or(s.tipo = 'arquivada') THEN 'arquivada'
           END AS tipo
    FROM situacao s
    WHERE s.casa = r.casa
      AND CASE WHEN s.cod_situacao IS NOT NULL THEN s.cod_situacao = r.cod_situacao
               ELSE s.texto = lower(extensions.unaccent(r.situacao_atual)) END
) enc ON true;

-- ---------------------------------------------------------------------------------------------
-- Movimentos maiores oficiais. Não depende de vw_projeto para evitar dependência circular.
-- A confirmação usa a identidade oficial estável, mesmo após reagrupar versões.
-- GREATEST ignora NULL; sem baseline nem prioridade_desde, apos_referencia é false.
CREATE VIEW contrato.vw_movimentacao_maior AS
SELECT v.chave_agrupamento, v.uuid_projeto, t.id_proposicao, t.sequencia, t.data_hora,
       v.identificacao_casa, t.sigla_orgao, t.descricao_tramitacao AS descricao,
       c.id_proposicao IS NOT NULL AS confirmada, c.confirmada_por_nome, c.confirmada_em,
       coalesce(t.data_hora > (greatest(
           (SELECT p.valor::timestamptz FROM gestao.parametro p WHERE p.chave = 'data_implantacao'),
           d.prioridade_desde) AT TIME ZONE 'America/Sao_Paulo'), false) AS apos_referencia
FROM contrato.vw_versao v
JOIN silver.tramitacao t ON t.id_proposicao = v.id_proposicao
LEFT JOIN gestao.decisao_projeto d ON d.uuid_projeto = v.uuid_projeto
LEFT JOIN gestao.confirmacao_movimentacao c
       ON c.id_proposicao = t.id_proposicao AND c.sequencia = t.sequencia
WHERE (v.casa = 'CD' AND EXISTS (
    SELECT 1 FROM gestao.tipo_movimentacao tm
    WHERE tm.casa = 'CD' AND tm.cod_tipo_tramitacao = t.cod_tipo_tramitacao AND tm.maior
)) OR (v.casa = 'SF' AND EXISTS (
    SELECT 1 FROM gestao.regra_movimentacao_senado rm
    WHERE extensions.unaccent(lower(t.descricao_tramitacao)) ~ rm.padrao
));

CREATE VIEW contrato.vw_tipos_sem_classificacao AS
SELECT t.cod_tipo_tramitacao, count(*) AS ocorrencias,
       min(t.descricao_tramitacao) AS exemplo
FROM silver.tramitacao t
JOIN contrato.vw_versao v ON v.id_proposicao = t.id_proposicao
WHERE v.casa = 'CD' AND t.cod_tipo_tramitacao IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM gestao.tipo_movimentacao tm
                  WHERE tm.casa = 'CD' AND tm.cod_tipo_tramitacao = t.cod_tipo_tramitacao)
GROUP BY t.cod_tipo_tramitacao;

-- ---------------------------------------------------------------------------------------------
-- contrato.vw_projeto — uma linha por projeto (chave_agrupamento): decisão, regras da carteira,
-- fila de avaliação, urgência por pauta e aviso de conferência. Regras (PRD RN06, RN07, RF09):
--   encerrado: TODAS as versões do projeto são 'arquivada'/'norma' (remessa não encerra).
--   elegivel: (acompanhada OR relevancia = 'SIM' OR prioridade) AND relevancia <> 'NAO' AND NOT encerrado.
--   em_carteira: elegivel AND (prioridade OR data_ultima_mov_grupo nos últimos 12 meses de
--                calendário, em Brasília OR pauta agendada de hoje em diante — a agenda futura de
--                elegíveis não aplica o corte). Sem data, sem prioridade e sem pauta: histórico ('sem data').
--   motivo_historico: 'encerrado' | 'marcado NÃO' | 'parado há mais de 12 meses' | 'sem data';
--                NULL na carteira, na fila de avaliação e no que nunca foi elegível.
--   pendente_avaliacao: em_radar AND relevancia IS NULL AND NOT acompanhada (é a fila; não entra
--                na carteira). Abrir pelo id_proposicao_recente (o UUID nasce na 1ª decisão).
--   Pauta agendada (RF09, "status agendado obrigatório"): item de pauta cujo evento tem situação
--                informada e que NÃO é 'Cancelada', 'Adiada', nem começa por 'Encerrad' ou 'Realizad'
--                (sem caixa). Valores vistos na Câmara (28/10/2026): Convocada, Encerrada,
--                Encerrada (Final), Encerrada (Termo), Cancelada; NULL não conta como agendada.
--                proxima_pauta_em/_orgao: a primeira pauta agendada com início a partir de hoje
--                00:00 de Brasília (sem limite de data).
--   urgente_pauta: prioridade AND elegivel AND NOT a_conferir AND proxima_pauta_em antes de
--                hoje+15 00:00 (janela [hoje, hoje+15) de Brasília).
--   a_conferir / motivos_conferencia: grupo com projetos diferentes, projeto com versões em grupos
--                diferentes; e, em todo projeto com UUID ou acompanhado (independente de relevância,
--                elegibilidade e corte), remessa sem a versão da outra casa carregada ou mistura de
--                versão encerrada com remessa/sem situação. A conferência não gera prioridade e
--                suspende a urgência automática.
-- id_proposicao_recente: a versão de movimentação mais recente (depois a apresentada por último);
-- os campos de exibição (identificacao, ementa, situacao_atual, órgão...) são dela.
-- revisao: 0 sem decisão gravada (é a revisão esperada na primeira decisão).
-- ---------------------------------------------------------------------------------------------
CREATE VIEW contrato.vw_projeto AS
WITH hoje AS (
    SELECT (now() AT TIME ZONE 'America/Sao_Paulo')::date AS dia
),
versao AS (
    SELECT * FROM contrato.vw_versao
),
pauta_por_versao AS (
    SELECT pm.id_proposicao,
           min(pm.data_hora_inicio) AS proxima_pauta_em,
           (array_agg(pm.sigla_orgao ORDER BY pm.data_hora_inicio, pm.sigla_orgao))[1] AS proxima_pauta_orgao
    FROM api_cache.vw_pautas_monitoradas pm, hoje h
    WHERE pm.situacao_evento IS NOT NULL
      AND pm.situacao_evento NOT IN ('Cancelada', 'Adiada')
      AND pm.situacao_evento !~* '^(encerrad|realizad)'
      AND pm.data_hora_inicio >= h.dia
    GROUP BY pm.id_proposicao
),
palavras AS (
    SELECT v.chave_agrupamento, string_agg(DISTINCT k.rotulo, ', ' ORDER BY k.rotulo) AS keywords_encontradas
    FROM versao v
    CROSS JOIN LATERAL unnest(string_to_array(v.keywords_encontradas, ', ')) AS k (rotulo)
    GROUP BY v.chave_agrupamento
),
agregado AS (
    SELECT
        v.chave_agrupamento,
        min(v.uuid_projeto::text)::uuid AS uuid_projeto,
        (array_agg(v.id_proposicao ORDER BY v.data_ultima_movimentacao DESC NULLS LAST,
                   v.data_apresentacao DESC NULLS LAST, v.id_proposicao DESC))[1] AS id_proposicao_recente,
        array_agg(v.id_proposicao ORDER BY v.casa, v.id_proposicao) AS ids_proposicao,
        array_agg(DISTINCT v.chave_projeto) AS chaves_projeto,
        count(*) AS qtd_versoes,
        string_agg(DISTINCT v.casa, ',' ORDER BY v.casa) AS casas,
        string_agg(v.identificacao_casa, ', ' ORDER BY v.casa, v.id_proposicao) AS identificacoes,
        bool_or(v.acompanhada) AS acompanhada,
        bool_or(v.em_radar) AS em_radar,
        max(v.data_ultima_movimentacao) AS data_ultima_mov_grupo,
        count(*) FILTER (WHERE v.tipo_encerramento IN ('arquivada', 'norma')) AS qtd_encerradas,
        bool_or(v.tipo_encerramento = 'remessa') AS tem_remessa,
        bool_or(v.sem_situacao) AS tem_sem_situacao,
        count(DISTINCT v.casa) AS qtd_casas,
        bool_or(v.grupo_com_projetos_diferentes) AS grupo_com_projetos_diferentes,
        bool_or(v.projeto_em_grupos_diferentes) AS projeto_em_grupos_diferentes,
        min(pv.proxima_pauta_em) AS proxima_pauta_em,
        (array_agg(pv.proxima_pauta_orgao ORDER BY pv.proxima_pauta_em NULLS LAST))[1] AS proxima_pauta_orgao
    FROM versao v
    LEFT JOIN pauta_por_versao pv ON pv.id_proposicao = v.id_proposicao
    GROUP BY v.chave_agrupamento
),
regras AS (
    SELECT
        a.*,
        d.relevancia, d.posicao, d.prioridade, d.acao, d.parecer, d.observacoes,
        coalesce(d.revisao, 0) AS revisao,
        d.prioridade_desde,
        d.atualizado_em AS decisao_atualizada_em,
        d.atualizado_por_nome AS decisao_atualizada_por_nome,
        (a.qtd_encerradas = a.qtd_versoes) AS encerrado,
        (a.acompanhada OR d.relevancia IS NOT DISTINCT FROM 'SIM' OR d.prioridade IS TRUE) AS base_elegivel,
        coalesce(a.data_ultima_mov_grupo >= h.dia - interval '12 months', false) AS movimentou_em_12_meses,
        coalesce(a.proxima_pauta_em < h.dia + 15, false) AS pauta_na_janela,
        (a.uuid_projeto IS NOT NULL OR a.acompanhada) AS sob_gestao
    FROM agregado a
    CROSS JOIN hoje h
    LEFT JOIN gestao.decisao_projeto d ON d.uuid_projeto = a.uuid_projeto
),
elegibilidade AS (
    SELECT
        r.*,
        (r.base_elegivel AND r.relevancia IS DISTINCT FROM 'NAO' AND NOT r.encerrado) AS elegivel
    FROM regras r
),
carteira AS (
    SELECT
        e.*,
        (e.elegivel AND (e.prioridade IS TRUE OR e.movimentou_em_12_meses OR e.proxima_pauta_em IS NOT NULL)) AS em_carteira,
        array_remove(ARRAY[
            CASE WHEN e.grupo_com_projetos_diferentes THEN 'versões do grupo com projetos diferentes' END,
            CASE WHEN e.projeto_em_grupos_diferentes THEN 'projeto com versões em grupos diferentes' END,
            CASE WHEN e.sob_gestao AND e.tem_remessa AND e.qtd_casas = 1
                 THEN 'remessa sem a versão da outra casa carregada' END,
            CASE WHEN e.sob_gestao AND e.qtd_encerradas > 0 AND e.qtd_encerradas < e.qtd_versoes
                      AND (e.tem_remessa OR e.tem_sem_situacao)
                 THEN 'encerramento divergente entre as versões' END
        ], NULL) AS motivos_conferencia
    FROM elegibilidade e
)
SELECT
    c.chave_agrupamento,
    c.uuid_projeto,
    c.id_proposicao_recente,
    c.ids_proposicao,
    c.chaves_projeto,
    c.qtd_versoes,
    c.casas,
    c.identificacoes,
    r.identificacao,
    r.identificacao_casa,
    r.ementa,
    r.situacao_atual,
    r.orgao_atual,
    r.nome_orgao_atual,
    r.ultima_movimentacao,
    c.data_ultima_mov_grupo,
    p.keywords_encontradas,
    r.link_direto,
    c.relevancia,
    c.posicao,
    c.prioridade,
    c.acao,
    c.parecer,
    c.observacoes,
    c.revisao,
    c.prioridade_desde,
    c.decisao_atualizada_em,
    c.decisao_atualizada_por_nome,
    c.acompanhada,
    c.em_radar,
    c.encerrado,
    c.elegivel,
    c.em_carteira,
    CASE
        WHEN c.em_carteira THEN NULL
        WHEN c.encerrado AND (c.base_elegivel OR c.relevancia = 'NAO') THEN 'encerrado'
        WHEN c.relevancia = 'NAO' THEN 'marcado NÃO'
        WHEN NOT c.base_elegivel THEN NULL
        WHEN c.data_ultima_mov_grupo IS NULL THEN 'sem data'
        ELSE 'parado há mais de 12 meses'
    END AS motivo_historico,
    (c.em_radar AND c.relevancia IS NULL AND NOT c.acompanhada) AS pendente_avaliacao,
    (c.elegivel AND c.prioridade IS TRUE AND c.pauta_na_janela AND cardinality(c.motivos_conferencia) = 0) AS urgente_pauta,
    c.proxima_pauta_em,
    c.proxima_pauta_orgao,
    cardinality(c.motivos_conferencia) > 0 AS a_conferir,
    c.motivos_conferencia,
    coalesce(m.pendentes, 0)::int AS movimentacoes_a_confirmar,
    (coalesce(m.pendentes, 0) > 0) AS urgente_movimentacao,
    ((c.elegivel AND c.prioridade IS TRUE AND c.pauta_na_janela AND cardinality(c.motivos_conferencia) = 0)
     OR coalesce(m.pendentes, 0) > 0) AS urgente,
    array_remove(ARRAY[
        CASE WHEN coalesce(m.pendentes, 0) > 0 THEN 'movimentação' END,
        CASE WHEN c.elegivel AND c.prioridade IS TRUE AND c.pauta_na_janela
                  AND cardinality(c.motivos_conferencia) = 0 THEN 'pauta' END
    ], NULL) AS motivos_urgencia
FROM carteira c
JOIN versao r ON r.id_proposicao = c.id_proposicao_recente
LEFT JOIN palavras p ON p.chave_agrupamento = c.chave_agrupamento
LEFT JOIN LATERAL (
    SELECT count(*) AS pendentes FROM contrato.vw_movimentacao_maior mm
    WHERE c.prioridade IS TRUE AND c.elegivel AND cardinality(c.motivos_conferencia) = 0
      AND mm.chave_agrupamento = c.chave_agrupamento AND mm.apos_referencia AND NOT mm.confirmada
) m ON true;

-- ---------------------------------------------------------------------------------------------
-- contrato.vw_conferencia — lista do mantenedor: uma linha por (projeto, motivo). Dois UUIDs
-- de um mesmo grupo aparecem como dois projetos lado a lado (ordene por chaves_projeto), cada
-- um com a sua decisão; nada é fundido nem descartado.
-- ---------------------------------------------------------------------------------------------
CREATE VIEW contrato.vw_conferencia AS
SELECT
    p.chave_agrupamento,
    p.uuid_projeto,
    m.motivo,
    p.chaves_projeto,
    p.ids_proposicao,
    p.identificacoes,
    p.relevancia,
    p.posicao,
    p.prioridade,
    p.revisao,
    p.em_carteira
FROM contrato.vw_projeto p
CROSS JOIN LATERAL unnest(p.motivos_conferencia) AS m (motivo);

-- ---------------------------------------------------------------------------------------------
-- contrato.vw_tramitacao — tramitações das versões monitoradas (api_cache.vw_tramitacoes), com a
-- unidade de projeto. Filtre por chave_agrupamento ou uuid_projeto e ordene por data_hora DESC.
-- ---------------------------------------------------------------------------------------------
CREATE VIEW contrato.vw_tramitacao AS
SELECT
    v.chave_agrupamento,
    v.uuid_projeto,
    t.id_proposicao,
    v.identificacao_casa,
    t.casa,
    t.sequencia,
    t.data_hora,
    t.sigla_orgao,
    t.nome_orgao,
    t.descricao_situacao,
    t.descricao_tramitacao,
    t.despacho
FROM api_cache.vw_tramitacoes t
JOIN contrato.vw_versao v ON v.id_proposicao = t.id_proposicao;

-- ---------------------------------------------------------------------------------------------
-- contrato.vw_pauta — itens de pauta das versões monitoradas, com a unidade de projeto e o
-- status_alerta na leitura (mesma regra de api.vw_pautas_monitoradas: Cancelada/Adiada primeiro,
-- depois o relógio de Brasília).
-- ---------------------------------------------------------------------------------------------
CREATE VIEW contrato.vw_pauta AS
SELECT
    v.chave_agrupamento,
    v.uuid_projeto,
    pm.id_proposicao,
    pm.identificacao,
    pm.id_evento,
    pm.data_hora_inicio,
    pm.casa,
    pm.sigla_orgao,
    pm.nome_orgao,
    pm.descricao_tipo,
    pm.situacao_evento,
    pm.topico,
    pm.titulo,
    pm.nome_relator,
    pm.partido_relator,
    pm.uf_relator,
    pm.situacao_item,
    pm.votado,
    CASE
        WHEN pm.situacao_evento = 'Cancelada' THEN 'Cancelada'
        WHEN pm.situacao_evento = 'Adiada' THEN 'Adiada'
        WHEN pm.data_hora_inicio > (now() AT TIME ZONE 'America/Sao_Paulo') THEN 'Agendado'
        WHEN pm.votado THEN 'Votado'
        ELSE 'Encerrado sem votação'
    END AS status_alerta
FROM api_cache.vw_pautas_monitoradas pm
JOIN contrato.vw_versao v ON v.id_proposicao = pm.id_proposicao;

-- ---------------------------------------------------------------------------------------------
-- contrato.vw_frescor — uma linha: últimas cargas bem-sucedidas (horário de Brasília) e falhas
-- (RF10). executado_em é gravado em UTC (sessão UTC).
--   falha_diaria / falha_senado: sem 'incremental' / 'incremental_senado' hoje depois das 09:00
--       de Brasília (antes das 09:00, sem nenhuma desde ontem).
--   falha_api: a última atualização do api_cache ('atualizacao_api', gravada por load_api) é
--       anterior à última carga diária — as telas e o painel mostram dados velhos.
-- ---------------------------------------------------------------------------------------------
-- Leituras privadas da aplicação: tabelas de gestão continuam sem SELECT direto.
CREATE VIEW contrato.vw_historico AS
SELECT id, uuid_projeto, operacao, diferencas, origem, ator_id, ator_nome, em, revisao
FROM gestao.historico_alteracao;

CREATE VIEW contrato.vw_inclusao AS
SELECT id, entrada, chave_entrada, casa, id_proposicao, estado, etapa, tentativas,
       proxima_tentativa_em, erro, email_estado, solicitante_id, solicitante_nome,
       criado_em, atualizado_em, ja_monitorada
FROM gestao.inclusao_manual;

CREATE VIEW contrato.vw_frescor AS
WITH carga AS (
    SELECT
        (max(executado_em) FILTER (WHERE tipo_carga = 'incremental')
            AT TIME ZONE 'UTC') AT TIME ZONE 'America/Sao_Paulo' AS ultima_carga_diaria,
        (max(executado_em) FILTER (WHERE tipo_carga = 'eventos')
            AT TIME ZONE 'UTC') AT TIME ZONE 'America/Sao_Paulo' AS ultima_carga_pautas,
        (max(executado_em) FILTER (WHERE tipo_carga = 'incremental_senado')
            AT TIME ZONE 'UTC') AT TIME ZONE 'America/Sao_Paulo' AS ultima_carga_senado,
        (max(executado_em) FILTER (WHERE tipo_carga = 'atualizacao_api')
            AT TIME ZONE 'UTC') AT TIME ZONE 'America/Sao_Paulo' AS ultima_atualizacao_api
    FROM bronze.controle_execucao
),
relogio AS (
    SELECT now() AT TIME ZONE 'America/Sao_Paulo' AS agora
),
esperado AS (
    -- data mínima da última carga diária: hoje a partir das 09:00, ontem antes disso
    SELECT r.agora, r.agora::date - CASE WHEN r.agora::time >= time '09:00' THEN 0 ELSE 1 END AS dia_minimo
    FROM relogio r
)
SELECT
    c.ultima_carga_diaria,
    c.ultima_carga_pautas,
    c.ultima_carga_senado,
    c.ultima_atualizacao_api,
    e.agora::date AS data_referencia,
    (c.ultima_carga_diaria IS NULL OR c.ultima_carga_diaria::date < e.dia_minimo) AS falha_diaria,
    (c.ultima_carga_senado IS NULL OR c.ultima_carga_senado::date < e.dia_minimo) AS falha_senado,
    (c.ultima_carga_diaria IS NOT NULL
     AND (c.ultima_atualizacao_api IS NULL OR c.ultima_atualizacao_api < c.ultima_carga_diaria)) AS falha_api
FROM carga c CROSS JOIN esperado e;

-- =============================================================================================
-- Funções de negócio (gestao). Todas SECURITY DEFINER com search_path fixo e nomes qualificados;
-- o ator (id e nome) é informado pelo servidor da aplicação, que já validou a pessoa (RF01).
-- Erros de domínio: SQLSTATE P0001 com MESSAGE fixa (a aplicação decide pela mensagem):
--   ator_obrigatorio, campos_invalidos, campo_invalido, relevancia_invalida, posicao_invalida,
--   prioridade_invalida, texto_invalido, projeto_nao_informado, projeto_nao_encontrado,
--   proposicao_nao_encontrada, projeto_a_conferir, conflito_revisao, prioridade_exige_sim,
--   confirmar_retirada_prioridade, desfazer_recusado, entrada_invalida, inclusao_nao_encontrada,
--   id_proposicao_invalido, estado_invalido, inclusao_duplicada, inclusao_ja_concluida.
-- =============================================================================================

-- ---------------------------------------------------------------------------------------------
-- gestao.gravar_decisao — núcleo interno de salvar_decisao/avaliar/desfazer_avaliacao e da
-- inclusão (NÃO é executável pela aplicação). Resolve o projeto por p_uuid (seguindo o alias)
-- ou pelo grupo de p_id_proposicao (sob pg_advisory_xact_lock do grupo, para duas primeiras
-- decisões simultâneas não criarem dois UUIDs), confere a revisão, aplica RN05, grava a decisão
-- e o histórico na mesma transação. Sem mudança efetiva não grava nada (alterado = false).
-- ---------------------------------------------------------------------------------------------
CREATE FUNCTION gestao.gravar_decisao(
    p_uuid uuid,
    p_id_proposicao bigint,
    p_revisao_esperada int,
    p_campos jsonb,
    p_ator_id uuid,
    p_ator_nome text,
    p_operacao text
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
    c_campos CONSTANT text[] := ARRAY['relevancia', 'posicao', 'prioridade', 'acao', 'parecer', 'observacoes'];
    v_uuid uuid;
    v_proximo uuid;
    v_chave bigint;
    v_qtd_uuids int;
    v_atual gestao.decisao_projeto%ROWTYPE;
    v_novo gestao.decisao_projeto%ROWTYPE;
    v_revisao int := 0;
    v_retirar boolean := false;
    v_campo text;
    v_tipo text;
    v_texto text;
    v_dif jsonb := '{}'::jsonb;
    v_hist bigint;
    v_criou boolean := false;
BEGIN
    IF p_ator_id IS NULL OR coalesce(btrim(p_ator_nome), '') = '' THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'ator_obrigatorio';
    END IF;
    IF p_campos IS NULL OR jsonb_typeof(p_campos) <> 'object' THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'campos_invalidos';
    END IF;
    SELECT k INTO v_campo
    FROM jsonb_object_keys(p_campos) AS k
    WHERE k <> ALL (c_campos || 'retirar_prioridade'::text)
    LIMIT 1;
    IF v_campo IS NOT NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'campo_invalido', DETAIL = v_campo;
    END IF;

    -- 1. Projeto, sob trava.
    IF p_uuid IS NOT NULL THEN
        v_uuid := p_uuid;
        FOR i IN 1..20 LOOP
            SELECT substituido_por INTO v_proximo FROM gestao.projeto WHERE uuid = v_uuid;
            IF NOT FOUND THEN
                RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'projeto_nao_encontrado';
            END IF;
            EXIT WHEN v_proximo IS NULL;
            v_uuid := v_proximo;
        END LOOP;
        IF v_proximo IS NOT NULL THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'projeto_nao_encontrado', DETAIL = 'cadeia de substituição sem fim';
        END IF;
    ELSE
        IF p_id_proposicao IS NULL THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'projeto_nao_informado';
        END IF;
        SELECT chave_projeto INTO v_chave FROM api_cache.vw_monitoramento WHERE id_proposicao = p_id_proposicao;
        IF NOT FOUND THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'proposicao_nao_encontrada';
        END IF;
        PERFORM pg_advisory_xact_lock(hashtextextended('gestao.grupo:' || v_chave, 0));
        -- Regra única (RN03.6): associação direta; sem ela, o UUID único do grupo.
        SELECT count(DISTINCT a.uuid_projeto), min(a.uuid_projeto::text)::uuid
        INTO v_qtd_uuids, v_uuid
        FROM api_cache.vw_monitoramento m
        JOIN contrato.vw_associacao a ON a.id_proposicao = m.id_proposicao
        WHERE m.chave_projeto = v_chave;
        IF v_qtd_uuids > 1 THEN
            v_uuid := (SELECT uuid_projeto FROM contrato.vw_associacao WHERE id_proposicao = p_id_proposicao);
            IF v_uuid IS NULL THEN
                RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'projeto_a_conferir',
                    DETAIL = 'versões do grupo associadas a projetos diferentes';
            END IF;
            -- grupo em conferência: decide pela própria versão, sem associar as outras a um lado
            v_chave := NULL;
        END IF;
    END IF;
    IF v_uuid IS NOT NULL THEN
        PERFORM pg_advisory_xact_lock(hashtextextended('gestao.projeto:' || v_uuid::text, 0));
        SELECT * INTO v_atual FROM gestao.decisao_projeto WHERE uuid_projeto = v_uuid FOR UPDATE;
        IF FOUND THEN
            v_revisao := v_atual.revisao;
        END IF;
    END IF;

    -- 2. Concorrência: a revisão de quando a pessoa abriu precisa ser a atual (0 = sem decisão).
    IF p_revisao_esperada IS DISTINCT FROM v_revisao THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'conflito_revisao',
            DETAIL = format('revisao_atual=%s', v_revisao);
    END IF;

    -- 3. Campos: chave ausente = não muda; null = limpa (relevância null volta a pendente).
    v_novo := v_atual;
    IF p_campos ? 'relevancia' THEN
        v_tipo := jsonb_typeof(p_campos -> 'relevancia');
        IF v_tipo NOT IN ('string', 'null') OR (v_tipo = 'string' AND (p_campos ->> 'relevancia') NOT IN ('SIM', 'NAO')) THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'relevancia_invalida';
        END IF;
        v_novo.relevancia := p_campos ->> 'relevancia';
    END IF;
    IF p_campos ? 'posicao' THEN
        v_tipo := jsonb_typeof(p_campos -> 'posicao');
        IF v_tipo NOT IN ('string', 'null') OR (v_tipo = 'string' AND (p_campos ->> 'posicao')
                NOT IN ('Acompanhar', 'A favor', 'Contra', 'A favor com ressalvas', 'Em análise')) THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'posicao_invalida';
        END IF;
        v_novo.posicao := p_campos ->> 'posicao';
    END IF;
    IF p_campos ? 'prioridade' THEN
        v_tipo := jsonb_typeof(p_campos -> 'prioridade');
        IF v_tipo NOT IN ('boolean', 'null') THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'prioridade_invalida';
        END IF;
        v_novo.prioridade := CASE WHEN v_tipo = 'boolean' THEN (p_campos ->> 'prioridade')::boolean END;
    END IF;
    IF p_campos ? 'retirar_prioridade' THEN
        IF jsonb_typeof(p_campos -> 'retirar_prioridade') <> 'boolean' THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'campos_invalidos', DETAIL = 'retirar_prioridade';
        END IF;
        v_retirar := (p_campos ->> 'retirar_prioridade')::boolean;
    END IF;
    FOREACH v_campo IN ARRAY ARRAY['acao', 'parecer', 'observacoes'] LOOP
        IF p_campos ? v_campo THEN
            v_tipo := jsonb_typeof(p_campos -> v_campo);
            IF v_tipo NOT IN ('string', 'null') THEN
                RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'texto_invalido', DETAIL = v_campo;
            END IF;
            -- texto só com espaços = vazio; o conteúdo em si é preservado como veio
            v_texto := p_campos ->> v_campo;
            IF btrim(v_texto) = '' THEN
                v_texto := NULL;
            END IF;
            CASE v_campo
                WHEN 'acao' THEN v_novo.acao := v_texto;
                WHEN 'parecer' THEN v_novo.parecer := v_texto;
                ELSE v_novo.observacoes := v_texto;
            END CASE;
        END IF;
    END LOOP;

    -- 4. RN05: NÃO numa prioridade só com a retirada confirmada; prioridade só com SIM.
    IF v_atual.prioridade IS TRUE AND v_novo.relevancia = 'NAO' THEN
        IF NOT v_retirar THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'confirmar_retirada_prioridade';
        END IF;
        v_novo.prioridade := false;
    END IF;
    IF v_novo.prioridade IS TRUE AND v_novo.relevancia IS DISTINCT FROM 'SIM' THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'prioridade_exige_sim';
    END IF;

    -- 5. Diferenças {campo: {"de": x, "para": y}} só do que mudou.
    -- (sem decisão gravada, v_atual inteiro é NULL: o coalesce iguala ausente e null)
    FOREACH v_campo IN ARRAY c_campos LOOP
        IF coalesce(to_jsonb(v_atual) -> v_campo, 'null'::jsonb)
           IS DISTINCT FROM coalesce(to_jsonb(v_novo) -> v_campo, 'null'::jsonb) THEN
            v_dif := v_dif || jsonb_build_object(v_campo, jsonb_build_object(
                'de', to_jsonb(v_atual) -> v_campo, 'para', to_jsonb(v_novo) -> v_campo));
        END IF;
    END LOOP;

    IF v_dif <> '{}'::jsonb THEN
        -- O UUID nasce na primeira decisão e já associa todas as versões do grupo.
        IF v_uuid IS NULL THEN
            v_uuid := gen_random_uuid();
            INSERT INTO gestao.projeto (uuid, criado_por_id) VALUES (v_uuid, p_ator_id);
            v_criou := true;
        END IF;
        IF v_chave IS NOT NULL THEN
            INSERT INTO gestao.projeto_proposicao (id_proposicao, uuid_projeto, origem)
            SELECT m.id_proposicao, v_uuid, 'aplicacao'
            FROM api_cache.vw_monitoramento m
            WHERE m.chave_projeto = v_chave
            ON CONFLICT (id_proposicao) DO NOTHING;
        END IF;

        v_novo.prioridade_desde := CASE
            WHEN v_novo.prioridade IS TRUE AND v_atual.prioridade IS NOT TRUE THEN now()
            WHEN v_novo.prioridade IS TRUE THEN v_atual.prioridade_desde
        END;
        INSERT INTO gestao.decisao_projeto AS d (
            uuid_projeto, relevancia, posicao, prioridade, acao, parecer, observacoes, revisao,
            prioridade_desde, atualizado_em, atualizado_por_id, atualizado_por_nome)
        VALUES (
            v_uuid, v_novo.relevancia, v_novo.posicao, v_novo.prioridade, v_novo.acao, v_novo.parecer,
            v_novo.observacoes, v_revisao + 1, v_novo.prioridade_desde, now(), p_ator_id, p_ator_nome)
        ON CONFLICT (uuid_projeto) DO UPDATE SET
            relevancia = EXCLUDED.relevancia,
            posicao = EXCLUDED.posicao,
            prioridade = EXCLUDED.prioridade,
            acao = EXCLUDED.acao,
            parecer = EXCLUDED.parecer,
            observacoes = EXCLUDED.observacoes,
            revisao = EXCLUDED.revisao,
            prioridade_desde = EXCLUDED.prioridade_desde,
            atualizado_em = EXCLUDED.atualizado_em,
            atualizado_por_id = EXCLUDED.atualizado_por_id,
            atualizado_por_nome = EXCLUDED.atualizado_por_nome;

        INSERT INTO gestao.historico_alteracao (uuid_projeto, operacao, diferencas, origem, ator_id, ator_nome, revisao)
        VALUES (v_uuid, p_operacao, v_dif, 'aplicacao', p_ator_id, p_ator_nome, v_revisao + 1)
        RETURNING id INTO v_hist;
        v_revisao := v_revisao + 1;
    END IF;

    RETURN jsonb_build_object(
        'uuid_projeto', v_uuid,
        'revisao', v_revisao,
        'relevancia', v_novo.relevancia,
        'posicao', v_novo.posicao,
        'prioridade', v_novo.prioridade,
        'acao', v_novo.acao,
        'parecer', v_novo.parecer,
        'observacoes', v_novo.observacoes,
        'alterado', v_dif <> '{}'::jsonb,
        'criado', v_criou,
        'historico_id', v_hist,
        'diferencas', v_dif);
END
$$;

-- ---------------------------------------------------------------------------------------------
-- gestao.salvar_decisao — salva a decisão de um projeto (tela Projeto, RF04).
--   p_uuid: o projeto; NULL na primeira decisão, quando o projeto é aberto por p_id_proposicao.
--   p_revisao_esperada: a revisão de quando a pessoa abriu (0 sem decisão). Divergente:
--       P0001 'conflito_revisao' (DETAIL 'revisao_atual=N') e nada é gravado.
--   p_campos: subconjunto de {relevancia, posicao, prioridade, acao, parecer, observacoes};
--       chave ausente não muda, null limpa. 'retirar_prioridade': true confirma NÃO numa prioridade.
-- Retorna jsonb {uuid_projeto, revisao, relevancia, posicao, prioridade, acao, parecer,
--   observacoes, alterado, criado, historico_id, diferencas}.
-- ---------------------------------------------------------------------------------------------
CREATE FUNCTION gestao.salvar_decisao(
    p_uuid uuid,
    p_id_proposicao bigint,
    p_revisao_esperada int,
    p_campos jsonb,
    p_ator_id uuid,
    p_ator_nome text
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
    RETURN gestao.gravar_decisao(p_uuid, p_id_proposicao, p_revisao_esperada, p_campos,
                                 p_ator_id, p_ator_nome, 'salvar_decisao');
END
$$;

-- ---------------------------------------------------------------------------------------------
-- gestao.avaliar — SIM/NÃO na fila de avaliação (RF02), pelo id da versão aberta.
-- Mesmo retorno de salvar_decisao; o historico_id devolvido é o que desfazer_avaliacao recebe.
-- ---------------------------------------------------------------------------------------------
CREATE FUNCTION gestao.avaliar(
    p_id_proposicao bigint,
    p_relevancia text,
    p_revisao_esperada int,
    p_ator_id uuid,
    p_ator_nome text
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
    IF p_relevancia IS NULL OR p_relevancia NOT IN ('SIM', 'NAO') THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'relevancia_invalida';
    END IF;
    RETURN gestao.gravar_decisao(NULL, p_id_proposicao, p_revisao_esperada,
                                 jsonb_build_object('relevancia', p_relevancia),
                                 p_ator_id, p_ator_nome, 'avaliar');
END
$$;

-- ---------------------------------------------------------------------------------------------
-- gestao.desfazer_avaliacao — "Desfazer" de uma avaliação da fila: devolve a relevância ao valor
-- anterior. Recusa (P0001 'desfazer_recusado') se o histórico não é de 'avaliar', se o projeto
-- foi substituído ou se a decisão mudou depois (a revisão atual não é a gravada pela avaliação).
-- Mesmo retorno de salvar_decisao.
-- ---------------------------------------------------------------------------------------------
CREATE FUNCTION gestao.desfazer_avaliacao(
    p_historico_id bigint,
    p_ator_id uuid,
    p_ator_nome text
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
    v_hist gestao.historico_alteracao%ROWTYPE;
    v_revisao int;
BEGIN
    SELECT * INTO v_hist FROM gestao.historico_alteracao WHERE id = p_historico_id;
    IF NOT FOUND OR v_hist.operacao <> 'avaliar' OR NOT (v_hist.diferencas ? 'relevancia') THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'desfazer_recusado', DETAIL = 'não é uma avaliação';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended('gestao.projeto:' || v_hist.uuid_projeto::text, 0));
    IF EXISTS (SELECT 1 FROM gestao.projeto WHERE uuid = v_hist.uuid_projeto AND substituido_por IS NOT NULL) THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'desfazer_recusado', DETAIL = 'projeto substituído';
    END IF;
    SELECT revisao INTO v_revisao FROM gestao.decisao_projeto WHERE uuid_projeto = v_hist.uuid_projeto FOR UPDATE;
    IF v_revisao IS DISTINCT FROM v_hist.revisao THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'desfazer_recusado', DETAIL = 'a decisão mudou depois da avaliação';
    END IF;
    RETURN gestao.gravar_decisao(v_hist.uuid_projeto, NULL, v_revisao,
                                 jsonb_build_object('relevancia', v_hist.diferencas -> 'relevancia' -> 'de'),
                                 p_ator_id, p_ator_nome, 'desfazer_avaliacao');
END
$$;

-- ---------------------------------------------------------------------------------------------
-- gestao.solicitar_inclusao — grava um pedido de inclusão (RF08). p_chave_entrada é a entrada
-- normalizada pela aplicação (casa + identificação). Deduplica pela chave: pedido em 'falhou' é
-- retomado (volta a 'solicitada', sem criar outro); em outro estado, devolve o existente.
-- Não decide nada sobre a proposição: onde ela está é lido em contrato.vw_projeto/vw_versao.
-- Retorna jsonb {id, estado, existente, retomado, id_proposicao}.
-- ---------------------------------------------------------------------------------------------
CREATE FUNCTION gestao.solicitar_inclusao(
    p_entrada text,
    p_chave_entrada text,
    p_ator_id uuid,
    p_ator_nome text
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
    v_id bigint;
    v_pedido gestao.inclusao_manual%ROWTYPE;
BEGIN
    IF p_ator_id IS NULL OR coalesce(btrim(p_ator_nome), '') = '' THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'ator_obrigatorio';
    END IF;
    IF coalesce(btrim(p_entrada), '') = '' OR coalesce(btrim(p_chave_entrada), '') = '' THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'entrada_invalida';
    END IF;

    INSERT INTO gestao.inclusao_manual (entrada, chave_entrada, solicitante_id, solicitante_nome)
    VALUES (p_entrada, p_chave_entrada, p_ator_id, p_ator_nome)
    ON CONFLICT (chave_entrada) DO NOTHING
    RETURNING id INTO v_id;
    IF v_id IS NOT NULL THEN
        RETURN jsonb_build_object('id', v_id, 'estado', 'solicitada', 'existente', false,
                                  'retomado', false, 'id_proposicao', NULL);
    END IF;

    SELECT * INTO v_pedido FROM gestao.inclusao_manual WHERE chave_entrada = p_chave_entrada FOR UPDATE;
    IF v_pedido.estado = 'falhou' THEN
        UPDATE gestao.inclusao_manual
        SET estado = 'solicitada', etapa = NULL, tentativas = 0, proxima_tentativa_em = NULL,
            erro = NULL, atualizado_em = now(),
            retomado_por_id = p_ator_id, retomado_por_nome = p_ator_nome, retomado_em = now()
        WHERE id = v_pedido.id;
        RETURN jsonb_build_object('id', v_pedido.id, 'estado', 'solicitada', 'existente', true,
                                  'retomado', true, 'id_proposicao', v_pedido.id_proposicao);
    END IF;
    RETURN jsonb_build_object('id', v_pedido.id, 'estado', v_pedido.estado, 'existente', true,
                              'retomado', false, 'id_proposicao', v_pedido.id_proposicao);
END
$$;

-- ---------------------------------------------------------------------------------------------
-- gestao.tentar_inclusao_agora — botão "Tentar agora" (RF08): pedido em 'falhou', ou esperando
-- nova tentativa automática, volta a 'solicitada' já elegível, com as tentativas zeradas. Em
-- outro estado não muda nada. Quem retomou fica em retomado_por_id/_nome/_em (RF01).
-- Retorna jsonb {id, estado, alterado}.
-- ---------------------------------------------------------------------------------------------
CREATE FUNCTION gestao.tentar_inclusao_agora(
    p_id bigint,
    p_ator_id uuid,
    p_ator_nome text
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
    v_pedido gestao.inclusao_manual%ROWTYPE;
BEGIN
    IF p_ator_id IS NULL OR coalesce(btrim(p_ator_nome), '') = '' THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'ator_obrigatorio';
    END IF;
    SELECT * INTO v_pedido FROM gestao.inclusao_manual WHERE id = p_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'inclusao_nao_encontrada';
    END IF;
    IF v_pedido.estado = 'falhou' OR (v_pedido.estado = 'solicitada' AND v_pedido.proxima_tentativa_em > now()) THEN
        UPDATE gestao.inclusao_manual
        SET estado = 'solicitada', etapa = NULL, tentativas = 0, proxima_tentativa_em = NULL,
            erro = NULL, atualizado_em = now(),
            retomado_por_id = p_ator_id, retomado_por_nome = p_ator_nome, retomado_em = now()
        WHERE id = p_id;
        RETURN jsonb_build_object('id', p_id, 'estado', 'solicitada', 'alterado', true);
    END IF;
    RETURN jsonb_build_object('id', p_id, 'estado', v_pedido.estado, 'alterado', false);
END
$$;

-- ---------------------------------------------------------------------------------------------
-- Funções do n8n (escritas e testadas aqui; o grant ao papel do n8n vem no passo do n8n).
-- A aplicação NÃO as executa.
-- ---------------------------------------------------------------------------------------------

-- gestao.falhar_inclusao — registra falha do pedido. Temporária: nova tentativa automática
-- espaçada (15, 30, 60, 120 min) até 5 tentativas; depois, ou se permanente (ex.: "não
-- encontrado"), fica em 'falhou' à espera de "Tentar agora". Pedido concluído não volta atrás.
-- Retorna jsonb {id, estado, tentativas, proxima_tentativa_em}.
CREATE FUNCTION gestao.falhar_inclusao(
    p_id bigint,
    p_erro text,
    p_temporaria boolean
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
    v_pedido gestao.inclusao_manual%ROWTYPE;
    v_tentativas int;
    v_proxima timestamptz;
    v_estado text;
BEGIN
    SELECT * INTO v_pedido FROM gestao.inclusao_manual WHERE id = p_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'inclusao_nao_encontrada';
    END IF;
    IF v_pedido.estado = 'concluida' THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'inclusao_ja_concluida';
    END IF;
    v_tentativas := v_pedido.tentativas + 1;
    IF coalesce(p_temporaria, false) AND v_tentativas < 5 THEN
        v_estado := 'solicitada';
        v_proxima := now() + interval '15 minutes' * power(2, v_tentativas - 1);
    ELSE
        v_estado := 'falhou';
        v_proxima := NULL;
    END IF;
    UPDATE gestao.inclusao_manual
    SET estado = v_estado, tentativas = v_tentativas, proxima_tentativa_em = v_proxima,
        erro = p_erro, atualizado_em = now()
    WHERE id = p_id;
    RETURN jsonb_build_object('id', p_id, 'estado', v_estado, 'tentativas', v_tentativas,
                              'proxima_tentativa_em', v_proxima);
END
$$;

-- gestao.registrar_inclusao_resolvida — o n8n resolveu o id da Câmara: o pedido passa a
-- 'carregando' e a proposição entra em silver.proposicao_acompanhada com origem 'sistema'
-- (retenção de coleta; ON CONFLICT DO NOTHING). Depois disso o n8n dispara modo=inclusao.
-- Proposição JÁ monitorada (no api_cache ou já associada em gestao) não é reativada (RF08): o
-- pedido conclui na hora com ja_monitorada = true, sem gravar acompanhada nem relevância; a
-- aplicação mostra onde ela está (fila, NÃO, histórico ou carteira).
-- Idempotente para o mesmo id. Outro pedido com o mesmo id: P0001 'inclusao_duplicada'
-- (DETAIL = id do outro pedido). Retorna jsonb {id, estado, id_proposicao, ja_monitorada, ja_acompanhada}.
CREATE FUNCTION gestao.registrar_inclusao_resolvida(
    p_id bigint,
    p_id_proposicao bigint
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
    v_pedido gestao.inclusao_manual%ROWTYPE;
    v_outro bigint;
    v_inseridas int;
BEGIN
    -- Só Câmara nesta entrega (RF08): ids do Senado são >= 1e9.
    IF p_id_proposicao IS NULL OR p_id_proposicao <= 0 OR p_id_proposicao >= 1000000000 THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'id_proposicao_invalido';
    END IF;
    SELECT * INTO v_pedido FROM gestao.inclusao_manual WHERE id = p_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'inclusao_nao_encontrada';
    END IF;
    IF v_pedido.estado IN ('carregando', 'concluida') AND v_pedido.id_proposicao = p_id_proposicao THEN
        RETURN jsonb_build_object('id', p_id, 'estado', v_pedido.estado, 'id_proposicao', p_id_proposicao,
                                  'ja_monitorada', coalesce(v_pedido.ja_monitorada, false),
                                  'ja_acompanhada', EXISTS (SELECT 1 FROM silver.proposicao_acompanhada
                                                            WHERE id_proposicao = p_id_proposicao));
    END IF;
    IF v_pedido.estado NOT IN ('solicitada', 'localizando') THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'estado_invalido', DETAIL = v_pedido.estado;
    END IF;
    SELECT id INTO v_outro FROM gestao.inclusao_manual WHERE id_proposicao = p_id_proposicao AND id <> p_id;
    IF v_outro IS NOT NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'inclusao_duplicada', DETAIL = v_outro::text;
    END IF;

    IF EXISTS (SELECT 1 FROM api_cache.vw_monitoramento WHERE id_proposicao = p_id_proposicao)
       OR EXISTS (SELECT 1 FROM gestao.projeto_proposicao WHERE id_proposicao = p_id_proposicao) THEN
        UPDATE gestao.inclusao_manual
        SET id_proposicao = p_id_proposicao, estado = 'concluida', ja_monitorada = true, etapa = NULL,
            proxima_tentativa_em = NULL, erro = NULL, atualizado_em = now()
        WHERE id = p_id;
        RETURN jsonb_build_object('id', p_id, 'estado', 'concluida', 'id_proposicao', p_id_proposicao,
                                  'ja_monitorada', true,
                                  'ja_acompanhada', EXISTS (SELECT 1 FROM silver.proposicao_acompanhada
                                                            WHERE id_proposicao = p_id_proposicao));
    END IF;

    UPDATE gestao.inclusao_manual
    SET id_proposicao = p_id_proposicao, estado = 'carregando', ja_monitorada = false, etapa = NULL,
        proxima_tentativa_em = NULL, erro = NULL, atualizado_em = now()
    WHERE id = p_id;
    INSERT INTO silver.proposicao_acompanhada (id_proposicao, origem, observacao)
    VALUES (p_id_proposicao, 'sistema', format('Inclusão pelo sistema (pedido %s)', p_id))
    ON CONFLICT (id_proposicao) DO NOTHING;
    GET DIAGNOSTICS v_inseridas = ROW_COUNT;
    RETURN jsonb_build_object('id', p_id, 'estado', 'carregando', 'id_proposicao', p_id_proposicao,
                              'ja_monitorada', false, 'ja_acompanhada', v_inseridas = 0);
END
$$;

-- gestao.concluir_inclusoes — chamada pelo n8n a cada webhook de sucesso (idempotente):
-- 1. todo pedido em 'carregando' cujo id já está no api_cache passa a 'concluida' e, se o
--    projeto ainda não tem relevância, recebe SIM em nome de quem pediu (RN06: inclusão entra
--    como SIM e acompanhada; uma relevância já decidida, inclusive NÃO, nunca é sobrescrita).
--    Só pedidos de proposição nova: a já monitorada concluiu no registro, sem SIM (RF08);
-- 2. pedido em 'carregando' há mais de 6 h vira falha temporária (disparo cancelado na fila).
-- Retorna jsonb {concluidas, marcadas_sim, expiradas}.
CREATE FUNCTION gestao.concluir_inclusoes() RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
    v_pedido record;
    v_revisao int;
    v_relevancia text;
    v_concluidas int := 0;
    v_sim int := 0;
    v_expiradas int := 0;
BEGIN
    FOR v_pedido IN
        UPDATE gestao.inclusao_manual i
        SET estado = 'concluida', etapa = NULL, erro = NULL, proxima_tentativa_em = NULL, atualizado_em = now()
        WHERE i.estado = 'carregando'
          AND i.ja_monitorada IS NOT TRUE
          AND EXISTS (SELECT 1 FROM api_cache.vw_monitoramento m WHERE m.id_proposicao = i.id_proposicao)
        RETURNING i.id, i.id_proposicao, i.solicitante_id, i.solicitante_nome
    LOOP
        v_concluidas := v_concluidas + 1;
        SELECT coalesce(d.revisao, 0), d.relevancia INTO v_revisao, v_relevancia
        FROM contrato.vw_versao v
        LEFT JOIN gestao.decisao_projeto d ON d.uuid_projeto = v.uuid_projeto
        WHERE v.id_proposicao = v_pedido.id_proposicao;
        IF v_relevancia IS NULL AND v_pedido.solicitante_id IS NOT NULL THEN
            BEGIN
                PERFORM gestao.gravar_decisao(NULL, v_pedido.id_proposicao, v_revisao, '{"relevancia": "SIM"}'::jsonb,
                                              v_pedido.solicitante_id, coalesce(v_pedido.solicitante_nome, 'inclusão'),
                                              'inclusao');
                v_sim := v_sim + 1;
            EXCEPTION WHEN SQLSTATE 'P0001' THEN
                -- projeto a conferir ou decisão concorrente: a conclusão vale; a relevância fica com a pessoa
                RAISE NOTICE 'Pedido %: relevância SIM não aplicada (%).', v_pedido.id, SQLERRM;
            END;
        END IF;
    END LOOP;

    FOR v_pedido IN
        SELECT id FROM gestao.inclusao_manual
        WHERE estado = 'carregando' AND atualizado_em < now() - interval '6 hours'
    LOOP
        PERFORM gestao.falhar_inclusao(v_pedido.id, 'Carga não concluída em 6 horas', true);
        v_expiradas := v_expiradas + 1;
    END LOOP;

    RETURN jsonb_build_object('concluidas', v_concluidas, 'marcadas_sim', v_sim, 'expiradas', v_expiradas);
END
$$;

-- =============================================================================================
-- Confirma apenas IDs efetivamente apresentados pela tela. Não toca no checkpoint do e-mail.
CREATE FUNCTION gestao.confirmar_movimentacoes(
    p_uuid uuid, p_itens jsonb, p_ator_id uuid, p_ator_nome text
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
    v_confirmadas jsonb;
    v_quantidade int;
    v_proximo uuid;
BEGIN
    IF p_ator_id IS NULL OR coalesce(btrim(p_ator_nome), '') = '' THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'ator_obrigatorio';
    END IF;
    IF p_itens IS NULL OR jsonb_typeof(p_itens) <> 'array' THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'campos_invalidos';
    END IF;
    IF p_uuid IS NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'projeto_nao_informado';
    END IF;
    -- A tela pode ter sido aberta antes de uma reconciliação. Resolve o mesmo alias
    -- aceito por gravar_decisao, sem confirmar movimentos de outro projeto.
    FOR i IN 1..20 LOOP
        SELECT substituido_por INTO v_proximo FROM gestao.projeto WHERE uuid = p_uuid;
        IF NOT FOUND THEN
            RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'projeto_nao_encontrado';
        END IF;
        EXIT WHEN v_proximo IS NULL;
        p_uuid := v_proximo;
    END LOOP;
    IF v_proximo IS NOT NULL THEN
        RAISE EXCEPTION USING ERRCODE = 'P0001', MESSAGE = 'projeto_nao_encontrado';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtextextended('gestao.projeto:' || p_uuid::text, 0));
    -- Só prioridade ativa pede confirmação. A conferência suspende urgência e confirmação.
    WITH inseridas AS (
        INSERT INTO gestao.confirmacao_movimentacao
            (id_proposicao, sequencia, uuid_projeto, confirmada_por_id, confirmada_por_nome)
        SELECT DISTINCT m.id_proposicao, m.sequencia, p_uuid, p_ator_id, p_ator_nome
        FROM contrato.vw_movimentacao_maior m
        JOIN contrato.vw_projeto p ON p.chave_agrupamento = m.chave_agrupamento
        WHERE m.uuid_projeto = p_uuid AND m.apos_referencia AND NOT m.confirmada
          AND p.prioridade IS TRUE AND p.elegivel AND NOT p.a_conferir
          AND EXISTS (
              SELECT 1 FROM jsonb_array_elements(p_itens) AS i(item)
              WHERE i.item->>'id_proposicao' = m.id_proposicao::text
                AND i.item->>'sequencia' = m.sequencia::text)
        ON CONFLICT DO NOTHING
        RETURNING id_proposicao, sequencia
    )
    SELECT coalesce(jsonb_agg(jsonb_build_object('id_proposicao', id_proposicao, 'sequencia', sequencia)), '[]'::jsonb),
           count(*)::int INTO v_confirmadas, v_quantidade FROM inseridas;
    IF v_quantidade > 0 THEN
        INSERT INTO gestao.historico_alteracao (uuid_projeto, operacao, diferencas, origem, ator_id, ator_nome)
        VALUES (p_uuid, 'confirmar_movimentacoes', jsonb_build_object('itens', v_confirmadas),
                'aplicacao', p_ator_id, p_ator_nome);
    END IF;
    RETURN jsonb_build_object('confirmadas', v_quantidade,
                              'ignoradas', jsonb_array_length(p_itens) - v_quantidade);
END
$$;

-- =============================================================================================
-- Projeção do painel público (Power BI pela anon, PRD seção 5). A ÚNICA view de api que lê
-- gestao: uma linha por versão de api_cache.vw_monitoramento, colunas fixas e travadas por teste
-- (sem ação, parecer, observações, histórico nem autoria). Versão sem UUID: uuid_projeto NULL
-- (o BI conta pela chave_projeto de api.vw_monitoramento). em_carteira vem de contrato.vw_projeto,
-- calculado na leitura (corte de 12 meses). Lê só api_cache/gestao, nunca gold (timeout de 3 s).
-- =============================================================================================
CREATE VIEW api.vw_painel_decisoes AS
SELECT
    v.id_proposicao,
    v.casa,
    v.uuid_projeto,
    p.relevancia,
    p.posicao,
    p.prioridade,
    p.em_carteira
FROM contrato.vw_versao v
JOIN contrato.vw_projeto p ON p.chave_agrupamento = v.chave_agrupamento;

-- =============================================================================================
-- Dono restrito das funções (PRD §5): gestao_dono (NOLOGIN, papel_legislativo_app.sql) só tem o
-- que as funções usam — nada de DDL, nada de bronze/gold/api, nada de silver além da acompanhada.
-- SECURITY DEFINER passa a rodar com esses privilégios, não com os do papel do setup.
-- =============================================================================================
GRANT USAGE ON SCHEMA gestao, contrato, api_cache, silver TO gestao_dono;
GRANT SELECT, INSERT ON gestao.projeto, gestao.projeto_proposicao, gestao.historico_alteracao TO gestao_dono;
GRANT SELECT, INSERT, UPDATE ON gestao.decisao_projeto, gestao.inclusao_manual TO gestao_dono;
GRANT SELECT, INSERT ON gestao.confirmacao_movimentacao TO gestao_dono;
GRANT SELECT ON gestao.tipo_movimentacao, gestao.regra_movimentacao_senado, gestao.parametro TO gestao_dono;
GRANT SELECT ON contrato.vw_projeto, contrato.vw_movimentacao_maior TO gestao_dono;
GRANT USAGE ON SEQUENCE gestao.historico_alteracao_id_seq, gestao.inclusao_manual_id_seq TO gestao_dono;
GRANT SELECT, INSERT ON silver.proposicao_acompanhada TO gestao_dono;
GRANT SELECT ON api_cache.vw_monitoramento, contrato.vw_associacao, contrato.vw_versao TO gestao_dono;
-- ALTER ... OWNER exige CREATE no schema para o novo dono: concedido só durante a troca.
GRANT CREATE ON SCHEMA gestao TO gestao_dono;
DO $$
DECLARE
    f regprocedure;
BEGIN
    FOR f IN
        SELECT p.oid::regprocedure
        FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'gestao' AND p.prorettype <> 'trigger'::regtype
    LOOP
        EXECUTE format('ALTER FUNCTION %s OWNER TO gestao_dono', f);
    END LOOP;
END
$$;
REVOKE CREATE ON SCHEMA gestao FROM gestao_dono;

-- =============================================================================================
-- Grants (refeitos a cada setup_db: o DROP derruba os de contrato e das funções).
-- =============================================================================================
-- O GRANT amplo de schema_api.sql rodou antes desta view existir.
GRANT SELECT ON api.vw_painel_decisoes TO anon;

-- Função nova nasce executável por PUBLIC: revoga tudo e concede só o necessário. O REVOKE em
-- massa é o que vale (todas as funções de gestao são criadas acima, nesta mesma transação); o
-- ALTER DEFAULT PRIVILEGES por schema não remove o padrão global de PUBLIC (o Postgres só
-- SOMA privilégios por schema), fica como registro da intenção.
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA gestao FROM PUBLIC, anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA gestao REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
REVOKE ALL ON SCHEMA contrato FROM PUBLIC, anon, authenticated;
REVOKE ALL ON ALL TABLES IN SCHEMA contrato FROM PUBLIC, anon, authenticated;

-- Papel da aplicação: lê os contratos e executa só as funções da aplicação (nunca as do n8n
-- nem gravar_decisao); nada em gestao (tabelas), silver ou api_cache direto.
GRANT USAGE ON SCHEMA contrato, gestao TO legislativo_app;
GRANT SELECT ON ALL TABLES IN SCHEMA contrato TO legislativo_app;
GRANT EXECUTE ON FUNCTION
    gestao.salvar_decisao(uuid, bigint, int, jsonb, uuid, text),
    gestao.avaliar(bigint, text, int, uuid, text),
    gestao.desfazer_avaliacao(bigint, uuid, text),
    gestao.solicitar_inclusao(text, text, uuid, text),
    gestao.tentar_inclusao_agora(bigint, uuid, text),
    gestao.confirmar_movimentacoes(uuid, jsonb, uuid, text)
TO legislativo_app;

NOTIFY pgrst, 'reload schema';
