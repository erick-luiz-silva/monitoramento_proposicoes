-- Camada bronze: append-only. Cada extração grava uma NOVA linha (nunca
-- update/delete), preservando o histórico de payloads como a API os retornou.
-- A chave primária é um id_bronze surrogate; id_proposicao é indexado, não único.

CREATE SCHEMA IF NOT EXISTS bronze;

CREATE TABLE IF NOT EXISTS bronze.proposicoes_json (
    id_bronze       BIGSERIAL PRIMARY KEY,
    id_proposicao   BIGINT NOT NULL,
    payload         JSONB NOT NULL,
    data_extracao   TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_bronze_proposicoes_json_id_proposicao
    ON bronze.proposicoes_json (id_proposicao);

CREATE TABLE IF NOT EXISTS bronze.autores_json (
    id_bronze       BIGSERIAL PRIMARY KEY,
    id_proposicao   BIGINT NOT NULL,
    payload         JSONB NOT NULL,
    data_extracao   TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_bronze_autores_json_id_proposicao
    ON bronze.autores_json (id_proposicao);

CREATE TABLE IF NOT EXISTS bronze.temas_json (
    id_bronze       BIGSERIAL PRIMARY KEY,
    id_proposicao   BIGINT NOT NULL,
    payload         JSONB NOT NULL,
    data_extracao   TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_bronze_temas_json_id_proposicao
    ON bronze.temas_json (id_proposicao);

CREATE TABLE IF NOT EXISTS bronze.tramitacoes_json (
    id_bronze       BIGSERIAL PRIMARY KEY,
    id_proposicao   BIGINT NOT NULL,
    payload         JSONB NOT NULL,
    data_extracao   TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_bronze_tramitacoes_json_id_proposicao
    ON bronze.tramitacoes_json (id_proposicao);

CREATE TABLE IF NOT EXISTS bronze.eventos_json (
    id_bronze       BIGSERIAL PRIMARY KEY,
    id_evento       BIGINT NOT NULL,
    payload         JSONB NOT NULL,
    data_extracao   TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_bronze_eventos_json_id_evento
    ON bronze.eventos_json (id_evento);

CREATE TABLE IF NOT EXISTS bronze.eventos_pauta_json (
    id_bronze       BIGSERIAL PRIMARY KEY,
    id_evento       BIGINT NOT NULL,
    payload         JSONB NOT NULL,
    data_extracao   TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_bronze_eventos_pauta_json_id_evento
    ON bronze.eventos_pauta_json (id_evento);

-- Controle de execução da carga incremental. Guarda a janela [data_inicio_janela,
-- data_fim_janela] de cada run bem-sucedido. O próximo run calcula seu dataInicio
-- como min(hoje - 3, data_fim_janela do último run - 3): se rodou ontem, é
-- equivalente a D-3 fixo; se ficou N dias sem rodar, a janela se alarga sozinha
-- para cobrir o buraco inteiro, sem depender de alguém notar a falha.
-- tipo_carga distingue 'incremental' (proposições) de 'eventos'; qtd_proposicoes
-- é reaproveitado genericamente como "quantidade de itens processados" em ambos.
CREATE TABLE IF NOT EXISTS bronze.controle_execucao (
    id_execucao        BIGSERIAL PRIMARY KEY,
    tipo_carga         VARCHAR(30) NOT NULL,
    data_inicio_janela DATE NOT NULL,
    data_fim_janela    DATE NOT NULL,
    qtd_proposicoes    INT,
    executado_em       TIMESTAMP NOT NULL DEFAULT now()
);

-- Pautas já avisadas por e-mail, por dia de Brasília. O n8n ("Monitoramento de Proposições →
-- Google Sheets") só manda a pauta que ainda não está aqui no dia e grava depois do envio:
-- cada pauta sai uma vez por dia e as rodadas de pautas (10h/14h) avisam só as novas.
-- data_hora_inicio entra na chave para reavisar pauta remarcada. Duas execuções do n8n quase
-- simultâneas podem repetir uma pauta (risco aceito). Linhas com mais de 30 dias são apagadas
-- pelo próprio n8n.
CREATE TABLE IF NOT EXISTS bronze.alerta_pauta (
    dia              DATE NOT NULL,
    id_evento        BIGINT NOT NULL,
    id_proposicao    BIGINT NOT NULL,
    data_hora_inicio TIMESTAMP NOT NULL,
    avisado_em       TIMESTAMP NOT NULL DEFAULT (now() AT TIME ZONE 'America/Sao_Paulo'),
    PRIMARY KEY (dia, id_evento, id_proposicao, data_hora_inicio)
);

-- Senado (docs/superpowers/plans/2026-10-28-senado-fases-3-4.md). id_processo é o id nativo
-- da API do Senado; a chave deslocada (1e9 + id) só existe da silver em diante.
-- Só grava quando o payload muda (hash_payload): os detalhes são grandes e cumulativos.
CREATE TABLE IF NOT EXISTS bronze.sf_processo_json (
    id_bronze     BIGSERIAL PRIMARY KEY,
    id_processo   BIGINT NOT NULL,
    hash_payload  TEXT NOT NULL,
    payload       JSONB NOT NULL,
    data_extracao TIMESTAMP NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_bronze_sf_processo_json_id
    ON bronze.sf_processo_json (id_processo, data_extracao DESC);

-- Números da Câmara de cada processo "Revisora" do Senado (vindo da Câmara), lidos sempre do
-- detalhe (identificacaoProcessoInicial e outrosNumeros[CD]): o número no Senado pode ser
-- outro mesmo de 2019 em diante (o ano no Senado é o da chegada). Liga gêmeos que mudaram
-- de número. Sem o payload: o processo só entra na bronze se for gêmeo de um monitorado.
CREATE TABLE IF NOT EXISTS bronze.sf_mapa_revisora (
    id_processo   BIGINT NOT NULL,
    sigla         VARCHAR(20) NOT NULL,
    numero        INT NOT NULL,
    ano           INT NOT NULL,
    data_extracao TIMESTAMP NOT NULL DEFAULT now(),
    PRIMARY KEY (id_processo, sigla, numero, ano)
);
