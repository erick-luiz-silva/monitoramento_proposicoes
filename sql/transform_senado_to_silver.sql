-- Transformação bronze -> silver do Senado (docs/superpowers/plans/2026-10-28-senado-fases-3-4.md).
-- Roda dentro da transação de quem chama (load_silver.executar_transformacao_senado), sem
-- commit: a carga confere a unicidade da gold antes de gravar e desfaz tudo se houver duplicata.
-- Só toca linhas do Senado: chave = 1000000000 (config.SENADO_OFFSET) + id nativo, casa 'SF'.
-- Lê só o último snapshot de cada processo (os informes são cumulativos no payload).

-- Último snapshot por processo, sem Substitutivo/Emenda: repetem sigla, número e ano do
-- processo original (ex. "PL 699/2023 (Substitutivo-CD)") e a tramitação segue no original.
DROP TABLE IF EXISTS sf_ultimo;
CREATE TEMP TABLE sf_ultimo ON COMMIT DROP AS
SELECT DISTINCT ON (b.id_processo) b.id_processo, b.payload, b.data_extracao
FROM bronze.sf_processo_json b
ORDER BY b.id_processo, b.data_extracao DESC, b.id_bronze DESC;
DELETE FROM sf_ultimo WHERE coalesce(payload->>'objetivo', '') IN ('Substitutivo', 'Emenda');

-- 1) silver.proposicao
-- Situação: situacaoAtual quando vem (98%); senão a situação mais recente entre todas as
-- autuações, com desempate determinístico (inicio, aberta primeiro, posição no payload).
-- Órgão atual: colegiado dessa situação; se vier {}, o colegiado de controle da autuação.
-- Última movimentação: informe mais recente (data, depois id).
WITH sit AS (
    SELECT DISTINCT ON (u.id_processo) u.id_processo, s.value AS situacao
    FROM sf_ultimo u
    CROSS JOIN LATERAL jsonb_array_elements(coalesce(u.payload->'autuacoes', '[]')) WITH ORDINALITY a(value, oa)
    CROSS JOIN LATERAL jsonb_array_elements(coalesce(a.value->'situacoes', '[]')) WITH ORDINALITY s(value, os)
    ORDER BY u.id_processo, (s.value->>'inicio') DESC NULLS LAST, (s.value->>'fim') IS NULL DESC, a.oa DESC, s.os DESC
),
aut AS (
    SELECT DISTINCT ON (u.id_processo) u.id_processo, a.value AS autuacao
    FROM sf_ultimo u
    CROSS JOIN LATERAL jsonb_array_elements(coalesce(u.payload->'autuacoes', '[]')) WITH ORDINALITY a(value, oa)
    ORDER BY u.id_processo, a.oa DESC
),
inf AS (
    SELECT DISTINCT ON (u.id_processo) u.id_processo, i.value AS informe
    FROM sf_ultimo u
    CROSS JOIN LATERAL jsonb_array_elements(coalesce(u.payload->'autuacoes', '[]')) a(value)
    CROSS JOIN LATERAL jsonb_array_elements(coalesce(a.value->'informesLegislativos', '[]')) i(value)
    ORDER BY u.id_processo, (i.value->>'data') DESC, (i.value->>'id')::bigint DESC
)
INSERT INTO silver.proposicao (
    id_proposicao, sigla_tipo, descricao_tipo, numero, ano, ementa,
    data_apresentacao, sigla_orgao_atual, id_orgao_atual, descricao_situacao, descricao_tramitacao,
    despacho, data_ultima_movimentacao, cod_situacao, link_direto, keywords_camara, data_extracao,
    casa, id_origem, codigo_materia, casa_iniciadora, data_apresentacao_origem
)
SELECT
    1000000000 + u.id_processo,
    u.payload->>'sigla',
    left(u.payload->>'descricaoSigla', 255),
    CASE WHEN u.payload->>'numero' ~ '^[0-9]+$' THEN (u.payload->>'numero')::int END,
    (u.payload->>'ano')::int,
    u.payload#>>'{conteudo,ementa}',
    (u.payload#>>'{documento,dataApresentacao}')::timestamp,
    left(coalesce(sit.situacao#>>'{colegiado,sigla}', aut.autuacao->>'siglaColegiadoControleAtual'), 20),
    1000000000 + coalesce((sit.situacao#>>'{colegiado,codigo}')::int, (aut.autuacao->>'codigoColegiadoControleAtual')::int),
    left(coalesce(u.payload->>'situacaoAtual', sit.situacao->>'descricao'), 255),
    inf.informe->>'descricao',
    NULL,
    (inf.informe->>'data')::timestamp,
    NULL,
    'https://www25.senado.leg.br/web/atividade/materias/-/materia/' || (u.payload->>'codigoMateria'),
    u.payload#>>'{documento,indexacao}',
    u.data_extracao,
    'SF',
    u.id_processo,
    (u.payload->>'codigoMateria')::int,
    u.payload->>'siglaCasaIniciadora',
    -- Data na casa iniciadora. Vindo da Câmara ('CD'), a data real é posta pelo vínculo no fim
    -- deste arquivo; aqui fica 1º de janeiro do ano de origem como reserva.
    CASE coalesce(u.payload->>'siglaCasaIniciadora', 'SF')
        WHEN 'CN' THEN (u.payload->>'dataInicioEfetivo')::timestamp
        WHEN 'CD' THEN CASE WHEN u.payload->>'identificacaoProcessoInicial' ~ '^\S+ [0-9]+/[0-9]{4}$'
                            THEN make_date(substring(u.payload->>'identificacaoProcessoInicial' from '([0-9]{4})$')::int, 1, 1) END
        ELSE (u.payload#>>'{documento,dataApresentacao}')::timestamp
    END
FROM sf_ultimo u
LEFT JOIN sit ON sit.id_processo = u.id_processo
LEFT JOIN aut ON aut.id_processo = u.id_processo
LEFT JOIN inf ON inf.id_processo = u.id_processo
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
    data_ultima_movimentacao = EXCLUDED.data_ultima_movimentacao,
    link_direto = EXCLUDED.link_direto,
    keywords_camara = EXCLUDED.keywords_camara,
    data_extracao = EXCLUDED.data_extracao,
    codigo_materia = EXCLUDED.codigo_materia,
    casa_iniciadora = EXCLUDED.casa_iniciadora,
    data_apresentacao_origem = EXCLUDED.data_apresentacao_origem;

-- 2) silver.proposicoes_proponentes: autoria de iniciativa (ou do documento, se vazia).
-- uri nula e tipos próprios: load_dim_deputado e a gold nunca confundem com deputados da Câmara.
DELETE FROM silver.proposicoes_proponentes
WHERE id_proposicao IN (SELECT 1000000000 + id_processo FROM sf_ultimo);

INSERT INTO silver.proposicoes_proponentes (
    id_proposicao, ordem_assinatura, uri, nome, tipo, cod_tipo, proponente, data_extracao,
    codigo_parlamentar_senado, partido_autor_epoca, uf_autor_epoca
)
SELECT
    1000000000 + u.id_processo,
    au.ordem::int,
    NULL,
    left(au.v->>'autor', 255),
    CASE au.v->>'siglaTipo'
        WHEN 'SENADOR' THEN 'Senador(a)'
        WHEN 'DEPUTADO' THEN 'Deputado(a) – via Senado'
        WHEN 'CAMARA' THEN 'Câmara dos Deputados'
        WHEN 'PRESIDENTE_REPUBLICA' THEN 'Poder Executivo'
        WHEN 'COMISSAO_SENADO' THEN 'Comissão do Senado'
        WHEN 'COMISSAO_CAMARA' THEN 'Comissão da Câmara'
        WHEN 'COMISSAO_CONGRESSO' THEN 'Comissão Mista'
        ELSE au.v->>'siglaTipo'
    END,
    NULL,
    1,
    u.data_extracao,
    (au.v->>'codigoParlamentar')::int,
    left(au.v->>'siglaPartido', 20),
    left(au.v->>'uf', 5)
FROM sf_ultimo u
CROSS JOIN LATERAL jsonb_array_elements(
    CASE WHEN jsonb_array_length(coalesce(u.payload->'autoriaIniciativa', '[]')) > 0
         THEN u.payload->'autoriaIniciativa'
         ELSE coalesce(u.payload#>'{documento,autoria}', '[]') END
) WITH ORDINALITY au(v, ordem);

-- 3) silver.proposicao_tema: classificações do Senado (código de 8 dígitos, sem colisão
-- com os temas da Câmara).
DELETE FROM silver.proposicao_tema
WHERE id_proposicao IN (SELECT 1000000000 + id_processo FROM sf_ultimo);

INSERT INTO silver.proposicao_tema (id_proposicao, cod_tema, tema, relevancia, data_extracao)
SELECT DISTINCT ON (1000000000 + u.id_processo, (c.value->>'codigo')::int)
    1000000000 + u.id_processo,
    (c.value->>'codigo')::int,
    left(c.value->>'descricaoHierarquia', 255),
    NULL,
    u.data_extracao
FROM sf_ultimo u
CROSS JOIN LATERAL jsonb_array_elements(coalesce(u.payload->'classificacoes', '[]')) c(value)
WHERE c.value ? 'codigo';

-- 4) silver.tramitacao: informes legislativos. sequencia = id do informe (estável; ids
-- repetidos no payload têm conteúdo idêntico, por isso DO NOTHING). data_extracao = primeira
-- vez vista: define o que entra como movimentação nova no e-mail.
-- "Novo relator": regex validada na fase 0 (96,5% de cobertura, sem falso positivo).
INSERT INTO silver.tramitacao (
    id_proposicao, sequencia, data_hora, sigla_orgao, uri_orgao, id_orgao, cod_situacao,
    descricao_situacao, descricao_tramitacao, despacho, url, cod_tipo_tramitacao, data_extracao,
    casa, eh_relator
)
SELECT
    1000000000 + u.id_processo,
    (i.value->>'id')::int,
    (i.value->>'data')::timestamp,
    left(i.value#>>'{colegiado,sigla}', 20),
    NULL,
    1000000000 + (i.value#>>'{colegiado,codigo}')::int,
    NULL,
    NULL,
    i.value->>'descricao',
    NULL,
    NULL,
    NULL,
    now(),
    'SF',
    coalesce(i.value->>'descricao', '') ~* (
        '^(re)?distribu[ií]d[oa]\s+(ao|à)\s+senador'
        '|designa\s+(como\s+)?(o\s+|a\s+)?(relator|relatora|senador|senadora)\M'
        '|designad[oa]s?\s+(["“”]?ad hoc["“”]?\s+)?(o\s+|a\s+)?(relator|relatora|senador|senadora)\M'
        '|avocad[oa]\s+a\s+relatoria')
FROM sf_ultimo u
CROSS JOIN LATERAL jsonb_array_elements(coalesce(u.payload->'autuacoes', '[]')) a(value)
CROSS JOIN LATERAL jsonb_array_elements(coalesce(a.value->'informesLegislativos', '[]')) i(value)
WHERE i.value ? 'id'
ON CONFLICT (id_proposicao, sequencia) DO NOTHING;

-- 5) silver.dim_orgao: colegiados do Senado com código (há muitos colegiado {}), um por
-- código pelo registro mais recente. casa 'CN' para os do Congresso (comissões mistas).
INSERT INTO silver.dim_orgao (id_orgao, sigla, nome, apelido, cod_tipo_orgao, tipo_orgao, data_extracao, casa)
SELECT DISTINCT ON (codigo)
    1000000000 + codigo, left(sigla, 20), nome, NULL, NULL, NULL, now(),
    CASE WHEN casa = 'CN' THEN 'CN' ELSE 'SF' END
FROM (
    SELECT (i.value#>>'{colegiado,codigo}')::int AS codigo, i.value#>>'{colegiado,sigla}' AS sigla,
           i.value#>>'{colegiado,nome}' AS nome, i.value#>>'{colegiado,casa}' AS casa, i.value->>'data' AS quando
    FROM sf_ultimo u
    CROSS JOIN LATERAL jsonb_array_elements(coalesce(u.payload->'autuacoes', '[]')) a(value)
    CROSS JOIN LATERAL jsonb_array_elements(coalesce(a.value->'informesLegislativos', '[]')) i(value)
    WHERE i.value->'colegiado' ? 'codigo'
    UNION ALL
    SELECT (s.value#>>'{colegiado,codigo}')::int, s.value#>>'{colegiado,sigla}',
           s.value#>>'{colegiado,nome}', s.value#>>'{colegiado,casa}', s.value->>'inicio'
    FROM sf_ultimo u
    CROSS JOIN LATERAL jsonb_array_elements(coalesce(u.payload->'autuacoes', '[]')) a(value)
    CROSS JOIN LATERAL jsonb_array_elements(coalesce(a.value->'situacoes', '[]')) s(value)
    WHERE s.value->'colegiado' ? 'codigo'
    UNION ALL
    SELECT (a.value->>'codigoColegiadoControleAtual')::int, a.value->>'siglaColegiadoControleAtual',
           a.value->>'nomeColegiadoControleAtual', a.value->>'casaColegiadoControleAtual', NULL
    FROM sf_ultimo u
    CROSS JOIN LATERAL jsonb_array_elements(coalesce(u.payload->'autuacoes', '[]')) a(value)
    WHERE a.value ? 'codigoColegiadoControleAtual'
) col
WHERE codigo IS NOT NULL
ORDER BY codigo, quando DESC NULLS LAST
ON CONFLICT (id_orgao) DO UPDATE SET
    sigla = EXCLUDED.sigla,
    nome = EXCLUDED.nome,
    casa = EXCLUDED.casa,
    data_extracao = EXCLUDED.data_extracao;
