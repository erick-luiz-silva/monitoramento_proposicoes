-- Transformação bronze -> silver via jsonb_array_elements/extração de campos.
-- proposicao, proposicoes_proponentes e proposicao_tema refletem o estado mais
-- recente (última linha de bronze por id_proposicao) e usam upsert.
-- tramitacao é histórica: acumula de todas as linhas de bronze, nunca sobrescreve
-- uma sequência já vista (idempotente entre execuções).

-- 1) silver.proposicao (depende de nada; demais tabelas têm FK para ela)
WITH ultimo_bronze AS (
    SELECT DISTINCT ON (id_proposicao) id_proposicao, payload, data_extracao
    FROM bronze.proposicoes_json
    ORDER BY id_proposicao, data_extracao DESC
)
INSERT INTO silver.proposicao (
    id_proposicao, sigla_tipo, descricao_tipo, numero, ano, ementa,
    data_apresentacao, sigla_orgao_atual, id_orgao_atual, descricao_situacao, descricao_tramitacao,
    despacho, data_ultima_movimentacao, cod_situacao, link_direto, keywords_camara, data_extracao
)
SELECT
    b.id_proposicao,
    b.payload->>'siglaTipo',
    b.payload->>'descricaoTipo',
    (b.payload->>'numero')::int,
    (b.payload->>'ano')::int,
    b.payload->>'ementa',
    (b.payload->>'dataApresentacao')::timestamp,
    b.payload#>>'{statusProposicao,siglaOrgao}',
    (regexp_replace(b.payload#>>'{statusProposicao,uriOrgao}', '.*/', ''))::int,
    b.payload#>>'{statusProposicao,descricaoSituacao}',
    b.payload#>>'{statusProposicao,descricaoTramitacao}',
    b.payload#>>'{statusProposicao,despacho}',
    (b.payload#>>'{statusProposicao,dataHora}')::timestamp,
    (b.payload#>>'{statusProposicao,codSituacao}')::int,
    'https://www.camara.leg.br/proposicoesWeb/fichadetramitacao?idProposicao=' || b.id_proposicao,
    b.payload->>'keywords',
    b.data_extracao
FROM ultimo_bronze b
ON CONFLICT (id_proposicao) DO UPDATE SET
    sigla_tipo = EXCLUDED.sigla_tipo,
    descricao_tipo = EXCLUDED.descricao_tipo,
    numero = EXCLUDED.numero,
    ano = EXCLUDED.ano,
    ementa = EXCLUDED.ementa,
    data_apresentacao = EXCLUDED.data_apresentacao,
    sigla_orgao_atual = EXCLUDED.sigla_orgao_atual,
    id_orgao_atual = EXCLUDED.id_orgao_atual,
    descricao_situacao = EXCLUDED.descricao_situacao,
    descricao_tramitacao = EXCLUDED.descricao_tramitacao,
    despacho = EXCLUDED.despacho,
    keywords_camara = EXCLUDED.keywords_camara,
    data_ultima_movimentacao = EXCLUDED.data_ultima_movimentacao,
    cod_situacao = EXCLUDED.cod_situacao,
    link_direto = EXCLUDED.link_direto,
    data_extracao = EXCLUDED.data_extracao;

-- 2) silver.proposicoes_proponentes
WITH ultimo_bronze AS (
    SELECT DISTINCT ON (id_proposicao) id_proposicao, payload, data_extracao
    FROM bronze.autores_json
    ORDER BY id_proposicao, data_extracao DESC
)
INSERT INTO silver.proposicoes_proponentes (
    id_proposicao, ordem_assinatura, uri, nome, tipo, cod_tipo, proponente, data_extracao
)
SELECT
    b.id_proposicao,
    (elem->>'ordemAssinatura')::int,
    elem->>'uri',
    elem->>'nome',
    elem->>'tipo',
    (elem->>'codTipo')::int,
    (elem->>'proponente')::int,
    b.data_extracao
FROM ultimo_bronze b, jsonb_array_elements(b.payload) elem
ON CONFLICT (id_proposicao, ordem_assinatura) DO UPDATE SET
    uri = EXCLUDED.uri,
    nome = EXCLUDED.nome,
    tipo = EXCLUDED.tipo,
    cod_tipo = EXCLUDED.cod_tipo,
    proponente = EXCLUDED.proponente,
    data_extracao = EXCLUDED.data_extracao;

-- 3) silver.proposicao_tema
WITH ultimo_bronze AS (
    SELECT DISTINCT ON (id_proposicao) id_proposicao, payload, data_extracao
    FROM bronze.temas_json
    ORDER BY id_proposicao, data_extracao DESC
)
INSERT INTO silver.proposicao_tema (id_proposicao, cod_tema, tema, relevancia, data_extracao)
SELECT
    b.id_proposicao,
    (elem->>'codTema')::int,
    elem->>'tema',
    (elem->>'relevancia')::int,
    b.data_extracao
FROM ultimo_bronze b, jsonb_array_elements(b.payload) elem
ON CONFLICT (id_proposicao, cod_tema) DO UPDATE SET
    tema = EXCLUDED.tema,
    relevancia = EXCLUDED.relevancia,
    data_extracao = EXCLUDED.data_extracao;

-- 4) silver.tramitacao (histórica: acumula de todas as linhas de bronze já vistas)
INSERT INTO silver.tramitacao (
    id_proposicao, sequencia, data_hora, sigla_orgao, uri_orgao, id_orgao, cod_situacao,
    descricao_situacao, descricao_tramitacao, despacho, url, cod_tipo_tramitacao, data_extracao
)
SELECT
    b.id_proposicao,
    (elem->>'sequencia')::int,
    (elem->>'dataHora')::timestamp,
    elem->>'siglaOrgao',
    elem->>'uriOrgao',
    (regexp_replace(elem->>'uriOrgao', '.*/', ''))::int,
    (elem->>'codSituacao')::int,
    elem->>'descricaoSituacao',
    elem->>'descricaoTramitacao',
    elem->>'despacho',
    elem->>'url',
    elem->>'codTipoTramitacao',
    b.data_extracao
FROM bronze.tramitacoes_json b, jsonb_array_elements(b.payload) elem
ON CONFLICT (id_proposicao, sequencia) DO NOTHING;
