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
    AND CASE WHEN p.casa = 'SF' THEN
            -- Senado: sem acento dos dois lados (a indexação do Senado às vezes vem sem acento)
            (extensions.unaccent(coalesce(p.ementa, '')) ~* extensions.unaccent(k.termo)
             OR extensions.unaccent(coalesce(p.keywords_camara, '')) ~* extensions.unaccent(k.termo))
            AND (k.termo_requerido IS NULL
                 OR extensions.unaccent(coalesce(p.ementa, '')) ~* extensions.unaccent(k.termo_requerido)
                 OR extensions.unaccent(coalesce(p.keywords_camara, '')) ~* extensions.unaccent(k.termo_requerido))
        ELSE
            (p.ementa ~* k.termo OR p.keywords_camara ~* k.termo)
            AND (k.termo_requerido IS NULL
                 OR p.ementa ~* k.termo_requerido
                 OR p.keywords_camara ~* k.termo_requerido)
        END
GROUP BY p.id_proposicao;

-- Grupo do projeto: as versões do mesmo projeto nas duas casas (silver.proposicao_vinculo,
-- N:M). chave_projeto = menor id do componente conexo do grafo de vínculos, ou o próprio id
-- sem vínculo. O recursivo começa só pelas arestas (barato) e usa UNION (não UNION ALL),
-- o que garante o término mesmo com ciclos; o GROUP BY deixa uma linha por nó.
-- grupo_acompanhado: alguma versão do grupo está em silver.proposicao_acompanhada —
-- acompanhar um projeto vale para as duas casas (decisão de 27/10/2026). Calculado aqui,
-- uma vez por grupo, para vw_monitoramento não precisar de EXISTS por linha.
-- data_origem_grupo: a apresentação mais antiga do grupo (casa iniciadora), para o radar não
-- tratar como novo um projeto antigo mesmo que a versão do Senado venha sem a data de origem.
-- Uma linha por id de silver.proposicao (a PK de proposicao_acompanhada impede duplicar).
CREATE OR REPLACE VIEW gold.vw_grupo_projeto AS
WITH RECURSIVE arestas AS (
    SELECT id_proposicao_cd AS origem, id_proposicao_sf AS destino FROM silver.proposicao_vinculo
    UNION
    SELECT id_proposicao_sf, id_proposicao_cd FROM silver.proposicao_vinculo
),
alcance (no, alcancado) AS (
    SELECT origem, origem FROM arestas
    UNION
    SELECT al.no, ar.destino FROM alcance al JOIN arestas ar ON ar.origem = al.alcancado
),
componentes AS (
    SELECT no, min(alcancado) AS chave FROM alcance GROUP BY no
),
outras_versoes AS (
    SELECT c1.no,
           string_agg(p2.sigla_tipo || ' ' || p2.numero || '/' || p2.ano
                      || CASE p2.casa WHEN 'SF' THEN ' (Senado)' ELSE ' (Câmara)' END,
                      ', ' ORDER BY p2.casa, p2.id_proposicao) AS ids_grupo
    FROM componentes c1
    JOIN componentes c2 ON c2.chave = c1.chave AND c2.no <> c1.no
    JOIN silver.proposicao p2 ON p2.id_proposicao = c2.no
    GROUP BY c1.no
)
SELECT
    p.id_proposicao,
    coalesce(c.chave, p.id_proposicao) AS chave_projeto,
    o.ids_grupo,
    bool_or(a.id_proposicao IS NOT NULL) OVER (PARTITION BY coalesce(c.chave, p.id_proposicao)) AS grupo_acompanhado,
    min(coalesce(p.data_apresentacao_origem, p.data_apresentacao)) OVER (PARTITION BY coalesce(c.chave, p.id_proposicao)) AS data_origem_grupo
FROM silver.proposicao p
LEFT JOIN componentes c ON c.no = p.id_proposicao
LEFT JOIN outras_versoes o ON o.no = p.id_proposicao
LEFT JOIN silver.proposicao_acompanhada a ON a.id_proposicao = p.id_proposicao;

-- View principal: uma linha por proposição com pelo menos 1 keyword OU acompanhada
-- (silver.proposicao_acompanhada: planilha antiga e inclusões manuais, mesmo sem keyword).
-- partido/UF do autor principal são os ATUAIS (via silver.dim_deputado), não os da
-- data de apresentação da proposição — só se aplica quando o autor é deputado.
-- em_radar: o que entra para avaliação/alerta. Acompanhadas sempre; as demais só se
-- apresentadas a partir de 2026-09-01 (início da produção), contando a data na casa
-- iniciadora (projeto antigo da Câmara que chega ao Senado não é novo).
-- Acompanhada = alguma versão do grupo do projeto (as duas casas) está acompanhada. Decisão da responsável:
-- trazer o que surgir daqui para frente, sem o histórico; setembro (e não a data da
-- mudança) recupera as que a Câmara demorou a classificar por tema.
-- Colunas novas só no FIM: CREATE OR REPLACE VIEW não aceita reordenar/renomear, e
-- vw_pautas_monitoradas depende desta view.
CREATE OR REPLACE VIEW gold.vw_monitoramento AS
SELECT
    p.id_proposicao,
    p.sigla_tipo || ' ' || p.numero || '/' || p.ano AS identificacao,
    p.ementa,
    autor.nome AS autor_principal,
    autor.tipo AS tipo_autor_principal,
    -- Partido/UF atuais: deputado (Câmara), senador (Senado) ou, para a versão do Senado de um
    -- projeto da Câmara, o deputado autor da versão da Câmara do grupo; por último, o da época.
    coalesce(dep.sigla_partido, sen.sigla_partido, dep_grupo.sigla_partido, autor.partido_autor_epoca) AS partido_autor_principal,
    coalesce(dep.sigla_uf, sen.sigla_uf, dep_grupo.sigla_uf, autor.uf_autor_epoca) AS uf_autor_principal,
    p.descricao_situacao AS situacao_atual,
    p.sigla_orgao_atual AS orgao_atual,
    COALESCE(p.descricao_tramitacao, p.despacho) AS ultima_movimentacao,
    p.data_ultima_movimentacao,
    ((now() AT TIME ZONE 'America/Sao_Paulo')::date - p.data_ultima_movimentacao::date) AS dias_sem_movimentacao,
    kw.keywords_encontradas,
    p.link_direto,
    orgao.nome AS nome_orgao_atual,
    g.grupo_acompanhado AS acompanhada,
    (g.grupo_acompanhado
     OR (kw.id_proposicao IS NOT NULL
         AND coalesce(coalesce(g.data_origem_grupo, p.data_apresentacao) >= DATE '2026-09-01', false))) AS em_radar,
    p.sigla_tipo,
    p.data_apresentacao,
    p.casa,
    g.chave_projeto,
    p.sigla_tipo || ' ' || p.numero || '/' || p.ano
        || CASE p.casa WHEN 'SF' THEN ' (Senado)' ELSE ' (Câmara)' END AS identificacao_casa,
    g.ids_grupo AS ids_vinculados
FROM silver.proposicao p
JOIN gold.vw_grupo_projeto g ON g.id_proposicao = p.id_proposicao
LEFT JOIN gold.vw_proposicao_keywords kw ON kw.id_proposicao = p.id_proposicao
LEFT JOIN silver.proposicoes_proponentes autor
    ON autor.id_proposicao = p.id_proposicao AND autor.ordem_assinatura = 1
-- Cast protegido: o Postgres não garante a ordem das condições, e autores do Senado têm uri nula.
LEFT JOIN silver.dim_deputado dep
    ON autor.tipo = 'Deputado(a)'
    AND autor.uri ~ '/[0-9]+$'
    AND dep.id_deputado = (CASE WHEN autor.uri ~ '/[0-9]+$' THEN regexp_replace(autor.uri, '.*/', '') END)::int
LEFT JOIN silver.dim_senador sen
    ON autor.tipo = 'Senador(a)' AND sen.codigo = autor.codigo_parlamentar_senado
-- Uma linha só: o autor de ordem 1 da proposição-chave do grupo (a versão da Câmara, quando existe).
LEFT JOIN silver.proposicoes_proponentes autor_cd
    ON p.casa = 'SF' AND autor.tipo = 'Deputado(a) – via Senado'
    AND g.chave_projeto < 1000000000
    AND autor_cd.id_proposicao = g.chave_projeto AND autor_cd.ordem_assinatura = 1
LEFT JOIN silver.dim_deputado dep_grupo
    ON autor_cd.tipo = 'Deputado(a)'
    AND autor_cd.uri ~ '/[0-9]+$'
    AND dep_grupo.id_deputado = (CASE WHEN autor_cd.uri ~ '/[0-9]+$' THEN regexp_replace(autor_cd.uri, '.*/', '') END)::int
LEFT JOIN silver.dim_orgao orgao ON orgao.id_orgao = p.id_orgao_atual
WHERE kw.id_proposicao IS NOT NULL OR g.grupo_acompanhado
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
    orgao.nome AS nome_orgao,
    t.casa
FROM silver.tramitacao t
JOIN silver.proposicao p ON p.id_proposicao = t.id_proposicao
LEFT JOIN silver.dim_orgao orgao ON orgao.id_orgao = t.id_orgao
ORDER BY t.id_proposicao, t.sequencia;

-- Pautas de comissões/plenário que citam proposições monitoradas — direto (ep.id_proposicao)
-- ou indireto, quando um item processual (ex. requerimento) referencia o PL de fato
-- (ep.id_proposicao_relacionada). Este último é o caminho mais comum (ver achados_eventos.txt).
-- Partido/UF do relator são os ATUAIS via dim_deputado, mesmo princípio do autor principal.
-- status_alerta: a situação oficial do evento vem primeiro (reunião cancelada ou adiada
-- não é "agendada" nem "encerrada sem votação"); depois a data, no relógio de Brasília (a
-- sessão é UTC e data_hora_inicio vem sem fuso). Mesma regra nas audiências e no api.
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
        WHEN e.situacao = 'Cancelada' THEN 'Cancelada'
        WHEN e.situacao = 'Adiada' THEN 'Adiada'
        WHEN e.data_hora_inicio > (now() AT TIME ZONE 'America/Sao_Paulo') THEN 'Agendado'
        WHEN ep.votado THEN 'Votado'
        ELSE 'Encerrado sem votação'
    END AS status_alerta,
    e.nome_orgao,
    m.id_proposicao,
    m.acompanhada,
    m.em_radar,
    ep.votado,
    e.casa,
    m.chave_projeto
FROM silver.evento_pauta ep
JOIN silver.evento e ON e.id_evento = ep.id_evento
JOIN gold.vw_monitoramento m
    ON m.id_proposicao = ep.id_proposicao OR m.id_proposicao = ep.id_proposicao_relacionada
LEFT JOIN silver.dim_deputado dep ON dep.id_deputado = ep.id_deputado_relator
ORDER BY e.data_hora_inicio DESC;

-- Tramitações ainda não alertadas das proposições da vw_monitoramento, para a seção
-- "Movimentações" do e-mail (o n8n filtra acompanhadas/SIM e exclui as marcadas NÃO).
-- data_extracao em silver.tramitacao é a da 1ª vez que a tramitação foi vista (insert
-- com ON CONFLICT DO NOTHING), então pega também as indexadas com atraso, sem repetir.
-- A marca 'alerta_movimentacoes' em controle_execucao é gravada pelo n8n só depois que
-- o e-mail sai (com o instante capturado ANTES da consulta): run ou e-mail que falhe
-- não faz perder alerta. O instante deve vir do próprio banco (SELECT localtimestamp),
-- nunca do relógio do n8n: as colunas são TIMESTAMP sem fuso e um ISO com -03:00 teria
-- o offset descartado, deixando a marca 3 h atrás (alertas repetidos). O limite de 30 dias evita despejar o histórico de proposições
-- recém-carregadas.
CREATE OR REPLACE VIEW gold.vw_movimentacoes AS
SELECT
    t.id_proposicao,
    m.identificacao,
    m.acompanhada,
    t.data_hora,
    t.sigla_orgao,
    t.descricao_tramitacao,
    t.despacho,
    coalesce(t.eh_relator, false) AS eh_relator,
    t.data_extracao,
    t.casa,
    m.chave_projeto
FROM silver.tramitacao t
JOIN gold.vw_monitoramento m ON m.id_proposicao = t.id_proposicao
WHERE t.data_extracao > coalesce(
        (SELECT max(executado_em) FROM bronze.controle_execucao WHERE tipo_carga = 'alerta_movimentacoes'),
        now() - interval '1 day')
  AND t.data_hora >= current_date - 30
ORDER BY t.data_hora DESC;

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
    CASE
        WHEN e.situacao = 'Cancelada' THEN 'Cancelada'
        WHEN e.situacao = 'Adiada' THEN 'Adiada'
        WHEN e.data_hora_inicio > (now() AT TIME ZONE 'America/Sao_Paulo') THEN 'Agendada'
        ELSE 'Realizada'
    END AS status_alerta,
    e.casa
FROM silver.evento e
JOIN silver.dim_keyword k
    ON k.ativo
    AND e.descricao ~* k.termo
    AND (k.termo_requerido IS NULL OR e.descricao ~* k.termo_requerido)
WHERE e.descricao_tipo = 'Audiência Pública'
GROUP BY e.id_evento, e.data_hora_inicio, e.sigla_orgao, e.nome_orgao,
         e.situacao, e.descricao, e.url_registro, e.casa
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
