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
    CONSTRAINT ck_decisao_prioridade_exige_sim CHECK (prioridade IS NOT TRUE OR relevancia = 'SIM')
);

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

-- Sem acesso para a Data API.
REVOKE ALL ON SCHEMA gestao FROM PUBLIC, anon, authenticated;
REVOKE ALL ON ALL TABLES IN SCHEMA gestao FROM PUBLIC, anon, authenticated;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA gestao FROM PUBLIC, anon, authenticated;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA gestao FROM PUBLIC, anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA gestao REVOKE ALL ON TABLES FROM PUBLIC, anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA gestao REVOKE ALL ON SEQUENCES FROM PUBLIC, anon, authenticated;
ALTER DEFAULT PRIVILEGES IN SCHEMA gestao REVOKE ALL ON FUNCTIONS FROM PUBLIC, anon, authenticated;
