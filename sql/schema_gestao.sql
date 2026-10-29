-- Schema gestao: decisões humanas persistentes do sistema /legislativo (PRD RN02, RN03, RN09).
-- NUNCA é derrubado: só CREATE ... IF NOT EXISTS e, na evolução, ALTER TABLE ... ADD COLUMN IF NOT EXISTS.
-- O pipeline não lê nem grava aqui. Views de contrato e funções de negócio vêm em outra etapa.
-- Sem acesso para anon/authenticated (Data API do Supabase); o acesso da aplicação é concedido depois.

CREATE SCHEMA IF NOT EXISTS gestao;

-- Identidade estável da unidade de decisão. Nasce só com decisão, inclusão ou acompanhamento.
CREATE TABLE IF NOT EXISTS gestao.projeto (
    uuid              UUID PRIMARY KEY,
    criado_em         TIMESTAMPTZ NOT NULL DEFAULT now(),
    criado_por_id     UUID,
    -- alias da reconciliação: projeto antigo aponta para o que o substituiu
    substituido_por   UUID REFERENCES gestao.projeto (uuid)
);

-- Associação às versões legislativas. Sem FK para silver.proposicao (RN03.7: ids do Senado
-- são apagados e regravados pela transformação, e as seeds admitem id ausente).
CREATE TABLE IF NOT EXISTS gestao.projeto_proposicao (
    id_proposicao   BIGINT PRIMARY KEY,
    uuid_projeto    UUID NOT NULL REFERENCES gestao.projeto (uuid),
    origem          TEXT NOT NULL CHECK (origem IN ('migracao', 'aplicacao', 'reconciliacao')),
    criado_em       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_projeto_proposicao_uuid ON gestao.projeto_proposicao (uuid_projeto);

-- Campos humanos. NULL = não informado (relevância NULL = pendente; prioridade NULL não vira false).
CREATE TABLE IF NOT EXISTS gestao.decisao_projeto (
    uuid_projeto         UUID PRIMARY KEY REFERENCES gestao.projeto (uuid),
    relevancia           TEXT CHECK (relevancia IN ('SIM', 'NAO')),
    posicao              TEXT CHECK (posicao IN ('Acompanhar', 'A favor', 'Contra', 'A favor com ressalvas', 'Em análise')),
    prioridade           BOOLEAN,
    acao                 TEXT,
    parecer              TEXT,
    observacoes          TEXT,
    revisao              INT NOT NULL DEFAULT 1,
    prioridade_desde     TIMESTAMPTZ,
    atualizado_em        TIMESTAMPTZ NOT NULL DEFAULT now(),
    atualizado_por_id    UUID,
    atualizado_por_nome  TEXT,
    CONSTRAINT ck_decisao_prioridade_exige_sim CHECK (prioridade IS NOT TRUE OR relevancia IS NOT DISTINCT FROM 'SIM')
);
-- CREATE TABLE IF NOT EXISTS não altera tabela existente: recria a constraint (idempotente) para
-- que prioridade=true com relevância NULL (pendente) também seja barrada.
ALTER TABLE gestao.decisao_projeto DROP CONSTRAINT IF EXISTS ck_decisao_prioridade_exige_sim;
ALTER TABLE gestao.decisao_projeto ADD CONSTRAINT ck_decisao_prioridade_exige_sim
    CHECK (prioridade IS NOT TRUE OR relevancia IS NOT DISTINCT FROM 'SIM');

-- Auditoria imutável.
CREATE TABLE IF NOT EXISTS gestao.historico_alteracao (
    id            BIGSERIAL PRIMARY KEY,
    uuid_projeto  UUID NOT NULL REFERENCES gestao.projeto (uuid),
    operacao      TEXT NOT NULL,
    diferencas    JSONB,
    origem        TEXT NOT NULL CHECK (origem IN ('aplicacao', 'migracao', 'reconciliacao')),
    ator_id       UUID,
    ator_nome     TEXT,
    em            TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_historico_alteracao_projeto ON gestao.historico_alteracao (uuid_projeto, em);
-- Revisão da decisão resultante da alteração: desfazer_avaliacao só desfaz se ela ainda é a atual.
ALTER TABLE gestao.historico_alteracao ADD COLUMN IF NOT EXISTS revisao INT;

CREATE OR REPLACE FUNCTION gestao.bloquear_alteracao_historico() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'gestao.historico_alteracao é imutável (% bloqueado)', TG_OP;
END
$$;

DROP TRIGGER IF EXISTS trg_historico_imutavel ON gestao.historico_alteracao;
CREATE TRIGGER trg_historico_imutavel
    BEFORE UPDATE OR DELETE ON gestao.historico_alteracao
    FOR EACH ROW EXECUTE FUNCTION gestao.bloquear_alteracao_historico();

DROP TRIGGER IF EXISTS trg_historico_sem_truncate ON gestao.historico_alteracao;
CREATE TRIGGER trg_historico_sem_truncate
    BEFORE TRUNCATE ON gestao.historico_alteracao
    FOR EACH STATEMENT EXECUTE FUNCTION gestao.bloquear_alteracao_historico();

-- Pedidos de inclusão manual de proposição (fila persistente consumida pelo n8n).
CREATE TABLE IF NOT EXISTS gestao.inclusao_manual (
    id                    BIGSERIAL PRIMARY KEY,
    entrada               TEXT NOT NULL,
    chave_entrada         TEXT NOT NULL UNIQUE,   -- entrada normalizada (sem acento, caixa, espaços)
    casa                  TEXT NOT NULL DEFAULT 'CD' CHECK (casa = 'CD'),
    id_proposicao         BIGINT UNIQUE,
    estado                TEXT NOT NULL DEFAULT 'solicitada'
                          CHECK (estado IN ('solicitada', 'localizando', 'carregando', 'concluida', 'falhou')),
    etapa                 TEXT,
    tentativas            INT NOT NULL DEFAULT 0,
    proxima_tentativa_em  TIMESTAMPTZ,
    erro                  TEXT,
    email_estado          TEXT,
    solicitante_id        UUID,
    solicitante_nome      TEXT,
    criado_em             TIMESTAMPTZ NOT NULL DEFAULT now(),
    atualizado_em         TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Proposição já monitorada quando o pedido foi resolvido (concluído sem reativar nada, RF08) e
-- quem retomou o pedido por último ("Tentar agora" ou novo pedido igual a um que falhou, RF01).
ALTER TABLE gestao.inclusao_manual ADD COLUMN IF NOT EXISTS ja_monitorada BOOLEAN;
ALTER TABLE gestao.inclusao_manual ADD COLUMN IF NOT EXISTS retomado_por_id UUID;
ALTER TABLE gestao.inclusao_manual ADD COLUMN IF NOT EXISTS retomado_por_nome TEXT;
ALTER TABLE gestao.inclusao_manual ADD COLUMN IF NOT EXISTS retomado_em TIMESTAMPTZ;

-- Referência editável pelo mantenedor: situações que encerram a tramitação (RN07).
-- Câmara casa por cod_situacao; Senado casa por texto (a silver grava cod_situacao NULL).
CREATE TABLE IF NOT EXISTS gestao.situacao_encerramento (
    casa            TEXT NOT NULL CHECK (casa IN ('CD', 'SF')),
    cod_situacao    INT,
    texto_situacao  TEXT,
    tipo            TEXT NOT NULL CHECK (tipo IN ('arquivada', 'norma', 'remessa')),
    CONSTRAINT ck_situacao_encerramento_chave CHECK (cod_situacao IS NOT NULL OR texto_situacao IS NOT NULL)
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_situacao_encerramento
    ON gestao.situacao_encerramento (casa, COALESCE(cod_situacao, -1), COALESCE(texto_situacao, ''));

-- Valores iniciais, conferidos nas monitoradas em 28/10/2026. Conservador: só situações
-- inequívocas; as ambíguas (ex.: 931 "Aguardando Remessa ao Arquivo", "Perdeu a Eficácia",
-- "Retirado pelo(a) Autor(a)", "Sem eficácia", "Revogada", "Prejudicada") deixam o projeto
-- ativo até o mantenedor decidir. ON CONFLICT DO NOTHING preserva o que o mantenedor editar.
INSERT INTO gestao.situacao_encerramento (casa, cod_situacao, texto_situacao, tipo) VALUES
    ('CD', 923,  'Arquivada',                          'arquivada'),
    ('CD', 1140, 'Transformado em Norma Jurídica',     'norma'),
    ('CD', 926,  'Aguardando Apreciação pelo Senado Federal', 'remessa'),
    ('SF', NULL, 'ARQUIVADA AO FINAL DA LEGISLATURA',  'arquivada'),
    ('SF', NULL, 'TRANSFORMADA EM NORMA JURÍDICA',     'norma'),
    ('SF', NULL, 'REMETIDA À CÂMARA DOS DEPUTADOS',    'remessa')
ON CONFLICT DO NOTHING;

-- Classificação editável: código novo é rotina até o mantenedor classificá-lo (Apêndice A).
CREATE TABLE IF NOT EXISTS gestao.tipo_movimentacao (
    casa TEXT NOT NULL CHECK (casa = 'CD'),
    cod_tipo_tramitacao TEXT NOT NULL,
    descricao TEXT NOT NULL,
    maior BOOLEAN NOT NULL,
    PRIMARY KEY (casa, cod_tipo_tramitacao)
);

CREATE TABLE IF NOT EXISTS gestao.regra_movimentacao_senado (
    id SERIAL PRIMARY KEY,
    padrao TEXT NOT NULL UNIQUE,
    descricao TEXT NOT NULL
);

-- Sem FK para silver: recargas oficiais nunca apagam confirmação humana (RN09).
CREATE TABLE IF NOT EXISTS gestao.confirmacao_movimentacao (
    id_proposicao BIGINT NOT NULL,
    sequencia INT NOT NULL,
    uuid_projeto UUID NOT NULL REFERENCES gestao.projeto (uuid),
    confirmada_por_id UUID NOT NULL,
    confirmada_por_nome TEXT NOT NULL,
    confirmada_em TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id_proposicao, sequencia)
);

CREATE TABLE IF NOT EXISTS gestao.parametro (
    chave TEXT PRIMARY KEY,
    valor TEXT
);
INSERT INTO gestao.parametro (chave, valor) VALUES ('data_implantacao', NULL) ON CONFLICT DO NOTHING;

-- Validação da Ana em 28/10/2026: 110, 195 e 330 são maiores; 1244 permanece rotina.
INSERT INTO gestao.tipo_movimentacao (casa, cod_tipo_tramitacao, descricao, maior)
SELECT 'CD', codigo, descricao, maior
FROM (VALUES
    ('Relatoria', true, ARRAY['320','327','328','1255','1250']),
    ('Parecer', true, ARRAY['322','330','336','335','339','420','431','1040']),
    ('Discussão e votação', true, ARRAY['250','220','222','242','227','221','234','219','1243','231','1231','245','1239','1233','223','1232','1008']),
    ('Resultado', true, ARRAY['240','1235','239','1236','1237','1242','198','1240','1518']),
    ('Urgência e requerimentos', true, ARRAY['196','195','192']),
    ('Mudança de caminho', true, ARRAY['110','603','171','106','129','104','120','121','122','128']),
    ('Fim ou retomada', true, ARRAY['502','640','620','200','1241','251','1012','1013']),
    ('Recebimento', false, ARRAY['500','501','506','507']),
    ('Publicação', false, ARRAY['604','605','611','1050']),
    ('Prazos', false, ARRAY['350','352','600']),
    ('Notificações', false, ARRAY['1002','1005','203','504','505']),
    ('Apresentação', false, ARRAY['100','300','194']),
    ('Requerimentos de rotina', false, ARRAY['260','263','362','1262','1263','1264']),
    ('Documentos e respostas', false, ARRAY['190','138','162','1055','1056']),
    ('Encaminhamento e devolução', false, ARRAY['180','113','170','602']),
    ('Outras rotinas', false, ARRAY['1023','1245','1244','1010','1516','1051','1042','5'])
) AS grupos(descricao, maior, codigos)
CROSS JOIN LATERAL unnest(codigos) AS c(codigo)
ON CONFLICT DO NOTHING;

INSERT INTO gestao.regra_movimentacao_senado (padrao, descricao) VALUES
    ('parecer|relator', 'Parecer e relatoria'),
    ('aprov|rejei|votacao', 'Aprovação, rejeição e votação'),
    ('pauta', 'Pauta'),
    ('(remess|remet|encaminh).*(camara|sancao)', 'Remessa à Câmara ou à sanção'),
    ('arquiv', 'Arquivamento'),
    ('sancao|veto|norma juridica', 'Sanção, veto e norma jurídica'),
    ('sancion|vetad', 'Sanção e veto nas flexões sancionada, sancionado e vetado'),
    ('urgencia', 'Urgência'),
    ('prejudic|prejuiz|retirad', 'Prejuízo ou retirada')
ON CONFLICT DO NOTHING;

-- Sem acesso para a Data API. Os ALTER DEFAULT PRIVILEGES
-- valem para objetos criados pelo papel que aplica o setup; o REVOKE em massa cobre o restante.
REVOKE ALL ON SCHEMA gestao FROM PUBLIC, anon, authenticated;
REVOKE ALL ON ALL TABLES IN SCHEMA gestao FROM PUBLIC, anon, authenticated;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA gestao FROM PUBLIC, anon, authenticated;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA gestao FROM PUBLIC, anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA gestao REVOKE ALL ON TABLES FROM PUBLIC, anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA gestao REVOKE ALL ON SEQUENCES FROM PUBLIC, anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA gestao REVOKE ALL ON FUNCTIONS FROM PUBLIC, anon, authenticated;
