-- Transformação de eventos e pautas bronze -> silver.
-- Compartilhada entre a carga diária e as atualizações intradiárias.

-- 5) silver.evento (o item de listagem já tem tudo; sem chamada a /eventos/{id})
WITH ultimo_bronze AS (
    SELECT DISTINCT ON (id_evento) id_evento, payload, data_extracao
    FROM bronze.eventos_json
    ORDER BY id_evento, data_extracao DESC
)
INSERT INTO silver.evento (
    id_evento, data_hora_inicio, data_hora_fim, descricao_tipo, situacao, descricao,
    id_orgao, sigla_orgao, nome_orgao, local_nome, url_registro, data_extracao
)
SELECT
    b.id_evento,
    (b.payload->>'dataHoraInicio')::timestamp,
    (b.payload->>'dataHoraFim')::timestamp,
    b.payload->>'descricaoTipo',
    b.payload->>'situacao',
    b.payload->>'descricao',
    (b.payload#>>'{orgaos,0,id}')::int,
    b.payload#>>'{orgaos,0,sigla}',
    b.payload#>>'{orgaos,0,nome}',
    b.payload#>>'{localCamara,nome}',
    b.payload->>'urlRegistro',
    b.data_extracao
FROM ultimo_bronze b
ON CONFLICT (id_evento) DO UPDATE SET
    data_hora_inicio = EXCLUDED.data_hora_inicio,
    data_hora_fim = EXCLUDED.data_hora_fim,
    descricao_tipo = EXCLUDED.descricao_tipo,
    situacao = EXCLUDED.situacao,
    descricao = EXCLUDED.descricao,
    id_orgao = EXCLUDED.id_orgao,
    sigla_orgao = EXCLUDED.sigla_orgao,
    nome_orgao = EXCLUDED.nome_orgao,
    local_nome = EXCLUDED.local_nome,
    url_registro = EXCLUDED.url_registro,
    data_extracao = EXCLUDED.data_extracao;

-- 6) silver.evento_pauta: sem chave natural confiável dentro do evento (ver
-- schema_silver.sql), então substitui a pauta inteira de cada evento presente
-- neste lote de bronze, a partir do snapshot mais recente. 'id' de
-- proposicao_/proposicaoRelacionada_/relator vêm como número ou string
-- dependendo do item na API — #>>'{...}' sempre retorna texto, então o cast
-- funciona nos dois casos.
DELETE FROM silver.evento_pauta
WHERE id_evento IN (SELECT DISTINCT id_evento FROM bronze.eventos_pauta_json);

WITH ultimo_bronze AS (
    SELECT DISTINCT ON (id_evento) id_evento, payload, data_extracao
    FROM bronze.eventos_pauta_json
    ORDER BY id_evento, data_extracao DESC
)
INSERT INTO silver.evento_pauta (
    id_evento, ordem, topico, regime, titulo, id_proposicao, id_proposicao_relacionada,
    id_deputado_relator, nome_relator, uri_votacao, situacao_item, data_extracao
)
SELECT
    b.id_evento,
    (elem->>'ordem')::int,
    elem->>'topico',
    elem->>'regime',
    elem->>'titulo',
    (elem#>>'{proposicao_,id}')::bigint,
    (elem#>>'{proposicaoRelacionada_,id}')::bigint,
    (regexp_replace(elem#>>'{relator,uri}', '.*/', ''))::int,
    elem#>>'{relator,nome}',
    elem->>'uriVotacao',
    elem->>'situacaoItem',
    b.data_extracao
FROM ultimo_bronze b, jsonb_array_elements(b.payload) elem;
