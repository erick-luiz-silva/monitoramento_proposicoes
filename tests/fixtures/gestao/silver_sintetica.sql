-- Silver sintética mínima para os testes dos contratos (tests/test_sql_local.py). Dados fictícios:
-- ids da Câmara 900001+ e do Senado 1990000001+ (fora da seed). Datas relativas ao "agora" de
-- Brasília, como os contratos. Uma keyword ('suínos') faz cada proposição entrar no cache.
INSERT INTO silver.dim_keyword (termo, rotulo) VALUES ('\msuín', 'suínos');

INSERT INTO silver.proposicao
    (id_proposicao, casa, sigla_tipo, numero, ano, ementa, data_apresentacao,
     descricao_situacao, cod_situacao, sigla_orgao_atual, data_ultima_movimentacao)
SELECT x.id, x.casa, 'PL', x.numero, 2020, 'Dispõe sobre a criação de suínos ' || x.numero,
       coalesce(x.apresentacao, TIMESTAMP '2020-03-01'), x.situacao, x.cod, 'CAPADR', x.mov
FROM (SELECT now() AT TIME ZONE 'America/Sao_Paulo' AS agora) h
CROSS JOIN LATERAL (VALUES
    -- corte e elegibilidade
    (900001, 'CD', 1, 'Aguardando Parecer', 1000, h.agora - interval '2 years', NULL::timestamp),  -- prioridade antiga
    (900002, 'CD', 2, 'Aguardando Parecer', 1000, h.agora - interval '2 years', NULL),             -- SIM parado
    (900003, 'CD', 3, 'Aguardando Parecer', 1000, NULL, NULL),                                     -- SIM sem data
    (900004, 'CD', 4, 'Aguardando Parecer', 1000, h.agora - interval '10 days', NULL),             -- NÃO
    -- encerramento (RN07)
    (900005, 'CD', 5, 'Arquivada', 923, h.agora - interval '10 days', NULL),                       -- arquivada + ...
    (1990000005, 'SF', 5, 'EM TRAMITAÇÃO', NULL, h.agora - interval '5 days', NULL),               -- ... versão ativa
    (900006, 'CD', 6, 'Arquivada', 923, h.agora - interval '10 days', NULL),                       -- encerrada
    (1990000016, 'SF', 16, 'Transformada em Norma Juridica', NULL, h.agora - interval '10 days', NULL), -- texto sem acento
    (900007, 'CD', 7, 'Aguardando Apreciação pelo Senado Federal', 926, h.agora - interval '10 days', NULL), -- remessa sem destino
    (900008, 'CD', 8, 'Arquivada', 923, h.agora - interval '10 days', NULL),                       -- encerrada + ...
    (1990000008, 'SF', 8, NULL, NULL, h.agora - interval '10 days', NULL),                         -- ... sem situação
    -- urgência por pauta
    (900009, 'CD', 9, 'Aguardando Parecer', 1000, h.agora - interval '10 days', NULL),
    -- associação e conferência (RN03.6)
    (900011, 'CD', 11, 'Aguardando Parecer', 1000, h.agora - interval '10 days', NULL),
    (1990000011, 'SF', 11, 'EM TRAMITAÇÃO', NULL, h.agora - interval '10 days', NULL),
    (900012, 'CD', 12, 'Aguardando Parecer', 1000, h.agora - interval '10 days', NULL),
    (1990000012, 'SF', 12, 'EM TRAMITAÇÃO', NULL, h.agora - interval '10 days', NULL),
    (900013, 'CD', 13, 'Aguardando Parecer', 1000, h.agora - interval '10 days', NULL),
    (1990000013, 'SF', 13, 'EM TRAMITAÇÃO', NULL, h.agora - interval '10 days', NULL),
    (900014, 'CD', 14, 'Aguardando Parecer', 1000, h.agora - interval '10 days', NULL),
    -- funções (sem decisão)
    (900021, 'CD', 21, 'Aguardando Parecer', 1000, h.agora - interval '10 days', NULL),
    (1990000021, 'SF', 21, 'EM TRAMITAÇÃO', NULL, h.agora - interval '3 days', NULL),
    -- fila de avaliação: radar (apresentada depois de 2026-09-01)
    (900031, 'CD', 31, 'Aguardando Parecer', 1000, h.agora - interval '3 days', h.agora - interval '5 days'),
    (900032, 'CD', 32, 'Aguardando Parecer', 1000, h.agora - interval '3 days', h.agora - interval '5 days'),  -- acompanhada
    (900033, 'CD', 33, 'Aguardando Parecer', 1000, h.agora - interval '3 days', NULL)              -- antiga, fora do radar
) AS x (id, casa, numero, situacao, cod, mov, apresentacao);

INSERT INTO silver.proposicao_vinculo (id_proposicao_cd, id_proposicao_sf, origem) VALUES
    (900005, 1990000005, 'manual'),
    (900008, 1990000008, 'manual'),
    (900011, 1990000011, 'manual'),
    (900012, 1990000012, 'manual'),
    (900021, 1990000021, 'manual');

INSERT INTO silver.proposicao_acompanhada (id_proposicao, origem) VALUES (900032, 'inclusao_manual');

-- Reunião daqui a 3 dias às 10:00 com o PL 9 na pauta (pelo item relacionado, o caminho comum).
INSERT INTO silver.evento (id_evento, data_hora_inicio, descricao_tipo, situacao, sigla_orgao, nome_orgao)
SELECT 9100001, (now() AT TIME ZONE 'America/Sao_Paulo')::date + 3 + time '10:00',
       'Reunião Deliberativa', 'Convocada', 'CAPADR', 'Comissão de Agricultura';
INSERT INTO silver.evento_pauta (id_evento, ordem, titulo, id_proposicao, id_proposicao_relacionada, votado)
VALUES (9100001, 1, 'Parecer do relator', 990001, 900009, false);
