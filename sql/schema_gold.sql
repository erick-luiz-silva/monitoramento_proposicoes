CREATE SCHEMA IF NOT EXISTS gold;

-- Keywords são aplicadas exclusivamente aqui na gold (nunca na silver),
-- para permitir adicionar termos sem reprocessar a extração.
-- dim_keyword.termo é um fragmento de regex ancorado por palavra (ver keywords.py) —
-- por isso o match usa ~* (regex case-insensitive), não ILIKE. O match considera
-- tanto a ementa quanto o campo de indexação curado pela própria Câmara
-- (keywords_camara), que às vezes cita o assunto mesmo quando a ementa não o faz.
CREATE OR REPLACE VIEW gold.vw_proposicao_keywords AS
SELECT
    p.id_proposicao,
    string_agg(DISTINCT k.rotulo, ', ' ORDER BY k.rotulo) AS keywords_encontradas
FROM silver.proposicao p
JOIN silver.dim_keyword k
    ON k.ativo
    AND (p.ementa ~* k.termo OR p.keywords_camara ~* k.termo)
    AND (k.termo_requerido IS NULL
         OR p.ementa ~* k.termo_requerido
         OR p.keywords_camara ~* k.termo_requerido)
GROUP BY p.id_proposicao;

-- View principal: uma linha por proposição relevante (com pelo menos 1 keyword).
-- partido/UF do autor principal são os ATUAIS (via silver.dim_deputado), não os da
-- data de apresentação da proposição — só se aplica quando o autor é deputado.
CREATE OR REPLACE VIEW gold.vw_monitoramento AS
SELECT
    p.id_proposicao,
    p.sigla_tipo || ' ' || p.numero || '/' || p.ano AS identificacao,
    p.ementa,
    autor.nome AS autor_principal,
    autor.tipo AS tipo_autor_principal,
    dep.sigla_partido AS partido_autor_principal,
    dep.sigla_uf AS uf_autor_principal,
    p.descricao_situacao AS situacao_atual,
    p.sigla_orgao_atual AS orgao_atual,
    COALESCE(p.descricao_tramitacao, p.despacho) AS ultima_movimentacao,
    p.data_ultima_movimentacao,
    (CURRENT_DATE - p.data_ultima_movimentacao::date) AS dias_sem_movimentacao,
    kw.keywords_encontradas,
    p.link_direto,
    orgao.nome AS nome_orgao_atual
FROM silver.proposicao p
JOIN gold.vw_proposicao_keywords kw ON kw.id_proposicao = p.id_proposicao
LEFT JOIN silver.proposicoes_proponentes autor
    ON autor.id_proposicao = p.id_proposicao AND autor.ordem_assinatura = 1
LEFT JOIN silver.dim_deputado dep
    ON autor.tipo = 'Deputado(a)'
    AND dep.id_deputado = (regexp_replace(autor.uri, '.*/', ''))::int
LEFT JOIN silver.dim_orgao orgao ON orgao.id_orgao = p.id_orgao_atual
ORDER BY p.data_ultima_movimentacao DESC;

-- Histórico completo de tramitações, para drill-down a partir da view principal.
CREATE OR REPLACE VIEW gold.vw_tramitacoes AS
SELECT
    t.id_proposicao,
    p.sigla_tipo || ' ' || p.numero || '/' || p.ano AS identificacao,
    t.sequencia,
    t.data_hora,
    t.sigla_orgao,
    t.descricao_situacao,
    t.descricao_tramitacao,
    t.despacho,
    orgao.nome AS nome_orgao
FROM silver.tramitacao t
JOIN silver.proposicao p ON p.id_proposicao = t.id_proposicao
LEFT JOIN silver.dim_orgao orgao ON orgao.id_orgao = t.id_orgao
ORDER BY t.id_proposicao, t.sequencia;

-- Pautas de comissões/plenário que citam proposições monitoradas — direto (ep.id_proposicao)
-- ou indireto, quando um item processual (ex. requerimento) referencia o PL de fato
-- (ep.id_proposicao_relacionada). Este último é o caminho mais comum (ver achados_eventos.txt).
-- Partido/UF do relator são os ATUAIS via dim_deputado, mesmo princípio do autor principal.
CREATE OR REPLACE VIEW gold.vw_pautas_monitoradas AS
SELECT
    e.id_evento,
    e.data_hora_inicio,
    e.sigla_orgao,
    e.descricao_tipo,
    e.situacao AS situacao_evento,
    ep.topico,
    ep.titulo,
    m.identificacao,
    m.ementa,
    ep.nome_relator,
    dep.sigla_partido AS partido_relator,
    dep.sigla_uf AS uf_relator,
    ep.uri_votacao,
    ep.situacao_item,
    CASE
        WHEN e.data_hora_inicio > now() THEN 'Agendado'
        WHEN ep.uri_votacao IS NOT NULL THEN 'Votado'
        ELSE 'Encerrado sem votação'
    END AS status_alerta,
    e.nome_orgao
FROM silver.evento_pauta ep
JOIN silver.evento e ON e.id_evento = ep.id_evento
JOIN gold.vw_monitoramento m
    ON m.id_proposicao = ep.id_proposicao OR m.id_proposicao = ep.id_proposicao_relacionada
LEFT JOIN silver.dim_deputado dep ON dep.id_deputado = ep.id_deputado_relator
ORDER BY e.data_hora_inicio DESC;

-- Audiências públicas cujo ASSUNTO bate nas keywords. Audiências não têm pauta
-- estruturada nem link confiável com proposição — o cruzamento é feito pelo texto
-- do tema (evento.descricao) contra dim_keyword, mesma regra da gold (termo +
-- termo_requerido). Sinal: "há debate público sobre um tema de interesse".
CREATE OR REPLACE VIEW gold.vw_audiencias_de_interesse AS
SELECT
    e.id_evento,
    e.data_hora_inicio,
    e.sigla_orgao,
    e.nome_orgao,
    e.situacao AS situacao_evento,
    e.descricao AS assunto,
    string_agg(DISTINCT k.rotulo, ', ' ORDER BY k.rotulo) AS keywords_encontradas,
    e.url_registro,
    CASE WHEN e.data_hora_inicio > now() THEN 'Agendada' ELSE 'Realizada' END AS status_alerta
FROM silver.evento e
JOIN silver.dim_keyword k
    ON k.ativo
    AND e.descricao ~* k.termo
    AND (k.termo_requerido IS NULL OR e.descricao ~* k.termo_requerido)
WHERE e.descricao_tipo = 'Audiência Pública'
GROUP BY e.id_evento, e.data_hora_inicio, e.sigla_orgao, e.nome_orgao,
         e.situacao, e.descricao, e.url_registro
ORDER BY e.data_hora_inicio DESC;

-- Auditoria: proposições do tema 64 (Agricultura, Pecuária, Pesca e Extrativismo)
-- que não bateram em nenhuma keyword ativa — usada para descobrir termos faltantes.
CREATE OR REPLACE VIEW gold.vw_proposicoes_sem_keyword AS
SELECT
    p.id_proposicao,
    p.sigla_tipo || ' ' || p.numero || '/' || p.ano AS identificacao,
    p.ementa,
    p.link_direto
FROM silver.proposicao p
JOIN silver.proposicao_tema pt
    ON pt.id_proposicao = p.id_proposicao AND pt.cod_tema = 64
WHERE NOT EXISTS (
    SELECT 1 FROM gold.vw_proposicao_keywords kw WHERE kw.id_proposicao = p.id_proposicao
);
