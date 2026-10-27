CREATE SCHEMA IF NOT EXISTS silver;

-- Dados normalizados da proposição em si. Nenhuma regra de negócio aplicada.
CREATE TABLE IF NOT EXISTS silver.proposicao (
    id_proposicao           BIGINT PRIMARY KEY,
    sigla_tipo              VARCHAR(20),
    descricao_tipo          VARCHAR(255),
    numero                  INT,
    ano                     INT,
    ementa                  TEXT,
    data_apresentacao       TIMESTAMP,
    sigla_orgao_atual       VARCHAR(20),
    id_orgao_atual          INT,
    descricao_situacao      VARCHAR(255),
    descricao_tramitacao    TEXT,
    despacho                TEXT,
    data_ultima_movimentacao TIMESTAMP,
    cod_situacao            INT,
    link_direto             TEXT,
    keywords_camara         TEXT,
    data_extracao           TIMESTAMP
);

-- Relação 1:N proposição -> proponentes. Nem todo proponente é deputado
-- (pode ser órgão do Executivo, comissão etc.) — ver achados_1.txt.
-- Não há partido/UF disponíveis neste endpoint da API.
CREATE TABLE IF NOT EXISTS silver.proposicoes_proponentes (
    id_proposicao    BIGINT NOT NULL REFERENCES silver.proposicao (id_proposicao),
    ordem_assinatura INT NOT NULL,
    uri              TEXT,
    nome             VARCHAR(255),
    tipo             VARCHAR(100),
    cod_tipo         INT,
    proponente       INT,
    data_extracao    TIMESTAMP,
    PRIMARY KEY (id_proposicao, ordem_assinatura)
);

-- Relação N:N proposição -> temas legislativos da Câmara.
CREATE TABLE IF NOT EXISTS silver.proposicao_tema (
    id_proposicao BIGINT NOT NULL REFERENCES silver.proposicao (id_proposicao),
    cod_tema      INT NOT NULL,
    tema          VARCHAR(255),
    relevancia    INT,
    data_extracao TIMESTAMP,
    PRIMARY KEY (id_proposicao, cod_tema)
);

-- Histórico de movimentações. Estrutural: nunca é sobrescrito, só cresce.
CREATE TABLE IF NOT EXISTS silver.tramitacao (
    id_proposicao         BIGINT NOT NULL REFERENCES silver.proposicao (id_proposicao),
    sequencia             INT NOT NULL,
    data_hora             TIMESTAMP,
    sigla_orgao           VARCHAR(20),
    uri_orgao             TEXT,
    id_orgao              INT,
    cod_situacao          INT,
    descricao_situacao    VARCHAR(255),
    descricao_tramitacao  TEXT,
    despacho              TEXT,
    url                   TEXT,
    cod_tipo_tramitacao   VARCHAR(20),
    data_extracao         TIMESTAMP,
    PRIMARY KEY (id_proposicao, sequencia)
);

-- Tabela de referência: temas legislativos da Câmara.
-- A API só retorna 'cod' e 'nome' preenchidos (sigla/descricao vêm sempre vazios).
CREATE TABLE IF NOT EXISTS silver.dim_tema (
    cod_tema INT PRIMARY KEY,
    nome     VARCHAR(255)
);

-- Dimensão de órgãos (comissões, plenário etc.), populada só com os IDs
-- referenciados em silver.proposicao/tramitacao/evento (não a base inteira de
-- órgãos da Câmara, que inclui milhares de comissões especiais extintas).
CREATE TABLE IF NOT EXISTS silver.dim_orgao (
    id_orgao       INT PRIMARY KEY,
    sigla          VARCHAR(20),
    nome           TEXT,
    apelido        TEXT,
    cod_tipo_orgao INT,
    tipo_orgao     VARCHAR(100),
    data_extracao  TIMESTAMP
);

-- Dimensão de deputados: partido/UF ATUAIS (ultimoStatus da API /deputados/{id}),
-- não o partido na data em que a proposição foi apresentada. Para deputados fora
-- de mandato, "atual" é o último status que a Câmara registrou, não necessariamente
-- a filiação partidária civil dele hoje. Upsert — sempre reflete o dado mais recente
-- coletado, sem histórico de mudanças de partido (para isso, ver /deputados/{id}/historico).
CREATE TABLE IF NOT EXISTS silver.dim_deputado (
    id_deputado   INT PRIMARY KEY,
    nome          VARCHAR(255),
    sigla_partido VARCHAR(20),
    sigla_uf      VARCHAR(5),
    situacao      VARCHAR(50),
    data_extracao TIMESTAMP
);

-- Eventos de comissões/plenário (pautas). Upsert por id_evento — reflete o
-- estado mais recente (situação pode mudar de "Convocada" pra "Encerrada", etc).
CREATE TABLE IF NOT EXISTS silver.evento (
    id_evento        BIGINT PRIMARY KEY,
    data_hora_inicio TIMESTAMP,
    data_hora_fim    TIMESTAMP,
    descricao_tipo   VARCHAR(255),
    situacao         VARCHAR(100),
    descricao        TEXT,
    id_orgao         INT,
    sigla_orgao      VARCHAR(20),
    nome_orgao       TEXT,
    local_nome       TEXT,
    url_registro     TEXT,
    data_extracao    TIMESTAMP
);

-- Itens de pauta de um evento. 'id_proposicao' é o item literal da pauta (pode
-- ser um documento processual, ex. parecer do relator); 'id_proposicao_relacionada'
-- é o PL de fato a que o item se refere — normalmente o caminho de match útil
-- (ver achados_eventos.txt). id_deputado_relator resolve partido/UF ATUAIS via
-- silver.dim_deputado na gold, mesmo princípio usado pro autor principal.
-- Chave substituta: 'ordem' NÃO é única dentro de um evento — repete quando um
-- item passa por múltiplas votações (preliminar/mérito/redação final), variando
-- só o uri_votacao (que pode até vir nulo). A transformação substitui a pauta
-- inteira do evento a cada execução, não faz upsert linha a linha.
CREATE TABLE IF NOT EXISTS silver.evento_pauta (
    id_evento_pauta           BIGSERIAL PRIMARY KEY,
    id_evento                 BIGINT NOT NULL REFERENCES silver.evento (id_evento),
    ordem                     INT,
    topico                    VARCHAR(100),
    regime                    VARCHAR(100),
    titulo                    TEXT,
    id_proposicao             BIGINT,
    id_proposicao_relacionada BIGINT,
    id_deputado_relator       INT,
    nome_relator              VARCHAR(255),
    uri_votacao               TEXT,
    situacao_item             TEXT,
    data_extracao             TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_evento_pauta_id_evento ON silver.evento_pauta (id_evento);
CREATE INDEX IF NOT EXISTS ix_evento_pauta_id_proposicao ON silver.evento_pauta (id_proposicao);
CREATE INDEX IF NOT EXISTS ix_evento_pauta_id_proposicao_relacionada ON silver.evento_pauta (id_proposicao_relacionada);

-- Tabela de configuração: palavras-chave usadas no matching da gold.
-- 'termo' é o fragmento de regex usado no match (ver src/keywords.py);
-- 'rotulo' é o texto legível exibido nos resultados (ex.: "suínos");
-- 'termo_requerido' (opcional) é um 2º regex que TAMBÉM precisa bater para o
-- termo contar — usado para desambiguar termos genéricos (ex.: "integração" só
-- conta em contexto agro; "bem-estar animal" só em contexto de produção).
CREATE TABLE IF NOT EXISTS silver.dim_keyword (
    id_keyword     SERIAL PRIMARY KEY,
    termo          VARCHAR(100) UNIQUE NOT NULL,
    rotulo         VARCHAR(100) NOT NULL,
    termo_requerido VARCHAR(400),
    ativo          BOOLEAN NOT NULL DEFAULT true
);

-- Proposições acompanhadas sempre, mesmo paradas, fora dos temas ou sem keyword:
-- recarregadas todo dia pelo incremental e sempre presentes em gold.vw_monitoramento.
-- origem 'planilha_antiga': fotografia única da aba "Acompanhamento manual"
-- (sql/seed_acompanhadas.sql); a planilha antiga não é lida por nenhuma automação.
-- origem 'inclusao_manual': gravada pelo n8n quando a responsável inclui uma
-- proposição pela aba "Proposições" (só INSERT ... ON CONFLICT DO NOTHING);
-- confirmada_em é preenchido pelo n8n depois do e-mail de confirmação.
CREATE TABLE IF NOT EXISTS silver.proposicao_acompanhada (
    id_proposicao BIGINT PRIMARY KEY,
    origem        VARCHAR(30) NOT NULL,
    observacao    TEXT,
    incluida_em   TIMESTAMP NOT NULL DEFAULT now(),
    confirmada_em TIMESTAMP
);

-- Senado no mesmo banco (docs/superpowers/specs/2026-10-27-senado-design.md, §4.1–4.2).
-- As chaves do Senado são 1_000_000_000 + id nativo (config.SENADO_OFFSET), então uma
-- proposição com id >= 1e9 é sempre do Senado. 'casa' é a API de origem ('CD'/'SF');
-- 'CN' (MPV, comissões mistas) só vale em proposicao.casa_iniciadora e dim_orgao.casa.
-- ADD COLUMN ... NOT NULL DEFAULT preenche as linhas que já existem (todas da Câmara).
ALTER TABLE silver.proposicao ADD COLUMN IF NOT EXISTS casa VARCHAR(2) NOT NULL DEFAULT 'CD';
ALTER TABLE silver.proposicao ADD COLUMN IF NOT EXISTS id_origem BIGINT;
ALTER TABLE silver.proposicao ADD COLUMN IF NOT EXISTS codigo_materia INT;
ALTER TABLE silver.proposicao ADD COLUMN IF NOT EXISTS casa_iniciadora VARCHAR(2);
-- Data de apresentação na casa iniciadora: no Senado, a data de apresentação é a da
-- chegada (projeto antigo da Câmara pareceria novo no radar).
ALTER TABLE silver.proposicao ADD COLUMN IF NOT EXISTS data_apresentacao_origem TIMESTAMP;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_proposicao_casa') THEN
        ALTER TABLE silver.proposicao
            ADD CONSTRAINT ck_proposicao_casa CHECK ((casa = 'SF') = (id_proposicao >= 1000000000));
    END IF;
END $$;

ALTER TABLE silver.tramitacao ADD COLUMN IF NOT EXISTS casa VARCHAR(2) NOT NULL DEFAULT 'CD';
-- "Novo relator" calculado na silver (cada casa escreve a designação de um jeito).
ALTER TABLE silver.tramitacao ADD COLUMN IF NOT EXISTS eh_relator BOOLEAN;
ALTER TABLE silver.evento ADD COLUMN IF NOT EXISTS casa VARCHAR(2) NOT NULL DEFAULT 'CD';
-- votado normalizado (Câmara: uri_votacao; Senado: resultado do item). Relator do Senado
-- em colunas próprias, nunca em id_deputado_relator (código de outro sistema).
ALTER TABLE silver.evento_pauta ADD COLUMN IF NOT EXISTS votado BOOLEAN;
ALTER TABLE silver.evento_pauta ADD COLUMN IF NOT EXISTS codigo_parlamentar_relator INT;
ALTER TABLE silver.evento_pauta ADD COLUMN IF NOT EXISTS partido_relator VARCHAR(20);
ALTER TABLE silver.evento_pauta ADD COLUMN IF NOT EXISTS uf_relator VARCHAR(5);
ALTER TABLE silver.dim_orgao ADD COLUMN IF NOT EXISTS casa VARCHAR(2) NOT NULL DEFAULT 'CD';

-- Versões do mesmo projeto nas duas casas (N:M: um processo do Senado pode citar dois
-- números da Câmara). Só é lida agregada, em gold.vw_grupo_projeto — um JOIN direto
-- multiplicaria linhas. origem: 'revisora', 'identificacao', 'mpv', 'manual'.
CREATE TABLE IF NOT EXISTS silver.proposicao_vinculo (
    id_proposicao_cd BIGINT NOT NULL CHECK (id_proposicao_cd < 1000000000),
    id_proposicao_sf BIGINT NOT NULL CHECK (id_proposicao_sf >= 1000000000),
    origem           VARCHAR(30) NOT NULL,
    data_extracao    TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (id_proposicao_cd, id_proposicao_sf)
);
CREATE INDEX IF NOT EXISTS ix_proposicao_vinculo_sf ON silver.proposicao_vinculo (id_proposicao_sf);

-- Preenchimento das colunas novas nas linhas da Câmara que já existiam. Idempotente
-- (só nulos) e restrito à Câmara: roda a cada setup_db e nunca toca linhas do Senado.
UPDATE silver.proposicao SET id_origem = id_proposicao WHERE id_origem IS NULL AND casa = 'CD';
UPDATE silver.proposicao SET data_apresentacao_origem = data_apresentacao
 WHERE data_apresentacao_origem IS NULL AND casa = 'CD';
UPDATE silver.tramitacao SET eh_relator = coalesce(descricao_tramitacao, '') ~* '^Designação de Relator'
 WHERE eh_relator IS NULL AND id_proposicao < 1000000000;
UPDATE silver.evento_pauta SET votado = (uri_votacao IS NOT NULL)
 WHERE votado IS NULL AND id_evento < 1000000000;
