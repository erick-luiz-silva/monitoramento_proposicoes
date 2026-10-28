# Senado Federal — fases 3 e 4 (proposições e vínculo entre casas) — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** carregar as proposições do Senado (classes de agro, meio ambiente, indústria e sanidade, todas as MPVs, as acompanhadas e os gêmeos de proposições monitoradas da Câmara) e ligar as versões do mesmo projeto nas duas casas.

**Architecture:**
- **Carga:** `extract_senado.executar_carga_senado()` substitui o stub da fase 1. Ela roda depois da Câmara, e qualquer falha vira aviso.
- **Bronze:** guarda o detalhe de cada processo (`/processo/{id}`) só quando o payload muda.
- **Silver:** `sql/transform_senado_to_silver.sql` grava nas mesmas tabelas da Câmara, com chave `1e9 + id` e `casa = 'SF'`, e preenche `silver.proposicao_vinculo` a partir dos números da Câmara no payload, do mapa dos processos "Revisora" e da regra de MPV.
- **Gold:** muda pouco (keywords sem acento no Senado e autor do Senado ou do grupo). O grupo, o radar e a posição já funcionam desde a fase 1.

**Tech Stack:** Python 3.14 (`requests`, `psycopg2`), PostgreSQL 17/Supabase (`unaccent`), GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-27-senado-design.md`, seções 2, 4.2 a 4.6 e 8. Contexto e decisões: `docs/superpowers/plans/2026-10-27-senado.md`, que traz a fase 0, a fase 1 e as "Pendências da revisão final da fase 1". Os números e os vocabulários da fase 0 estão em `data/senado_fase0/RESULTADOS*.md` (local, gitignored).

**Validação:** o Fable revisou este plano em 28/10/2026, com veredito "aprovado com ajustes". Os ajustes obrigatórios E1 a E8 e as lacunas estão incorporados abaixo, marcados com **[Fable]**.

**Estado em 28/10/2026:** as fases 1 e 2 estão em produção.
- **Fase 1:** o banco tem `casa`, `id_origem`, `data_apresentacao_origem`, `eh_relator`, `votado`, `proposicao_vinculo` e `vw_grupo_projeto`, com `data_origem_grupo` e `grupo_acompanhado`. O orquestrador transforma uma falha do Senado em aviso. O Power BI liga a posição por `chave_projeto`.
- **Fase 2:** o n8n trabalha por grupo e mostra a casa no e-mail e na planilha.

## Global Constraints

- **Plano principal:** valem as Global Constraints de `docs/superpowers/plans/2026-10-27-senado.md`: idioma, testes mockados, deslocamentos (`config.SENADO_OFFSET`), colunas novas no fim, paridade gold × api, "o Senado nunca derruba a Câmara", repositório público e deploy com `setup_db` antes do merge.
- **Casa:** toda linha que vem da API do Senado tem `casa = 'SF'`. `'CN'` só aparece em `casa_iniciadora` e em `dim_orgao.casa`, para as comissões mistas.
- **Escopo da transformação do Senado:** só escreve linhas com id `>= 1e9`, nunca toca linhas da Câmara.
- **Unicidade:** antes do commit da transformação, a carga confere a unicidade de `gold.vw_monitoramento` nos ids do Senado. Se houver duplicata, faz rollback da transformação e levanta erro, que vira aviso. A silver fica como estava, e o `REFRESH` do api não quebra.
- **API do Senado:**
  - no máximo 5 req/s;
  - retry com backoff em 429/5xx;
  - timeout de conexão de 15 s e de leitura de 120 s;
  - segue redirects;
  - força TLS 1.2 só quando `SENADO_TLS12=1`, uso local no WSL. O runner do Actions não precisa (0.1).
- **Prazo global da carga do Senado:** `SENADO_PRAZO_MIN = 30`. Estourou, levanta erro, que vira aviso, e as janelas do Senado não avançam.
- **Fora do escopo:** relatorias (`/processo/relatoria`). `eh_relator` é a regex da 0.4 sobre a descrição do informe, e o relator da pauta vem da agenda na fase 5. MPV não é filtrada.

## Review Focus

1. **Processo do Senado com `situacaoAtual` nula** (PLS 631/2015, PLC 10/2018) **e situações com o mesmo `inicio`** (87 de 1.182 payloads): a situação é determinística. **[Fable]** Os 1.182 payloads têm uma autuação só; o caso de várias autuações é coberto por uma fixture sintética (Tarefa 3.3).
2. **Informe com o mesmo `id` repetido no payload** (PL 1879/2022 tem um id 7×): entra uma linha só em `tramitacao`, sem erro de PK (Tarefa 3.3).
3. **Gêmeo com número diferente**, como PL 4314/2016 ↔ PL 6682/2025, ou PL 6882/2017 ↔ PL 395/2019 (ano no Senado ≥ 2019): o mapa liga pelo detalhe, nunca pela identificação da lista, e a carga diária traz o gêmeo (Tarefas 4.1 e 4.2). **[Fable E1]**
6. **Proposição nova da Câmara (radar) que chega ao Senado:** continua no radar, porque a data de origem vem da versão da Câmara ligada (Tarefa 4.1). **[Fable E2]**
4. **Acompanhada do Senado com erro crônico na API** (id inválido): não trava a janela `incremental_senado`, vira aviso e não derruba a Câmara (Tarefa 3.6).
5. **Duplicata gerada pela transformação do Senado:** é desfeita antes do commit, e o api da Câmara continua atualizando (Tarefa 3.6).

---

## Fase 3 — Proposições do Senado

Branch `feat/senado-fase3-4`, a partir da `main`.

### Tarefa 3.1: Cliente da API do Senado

**Files:**
- Create: `src/api_client_senado.py`
- Test: `tests/test_senado.py` (classe `ClienteSenadoTests`)
- Modify: `src/config.py`, que recebe `SENADO_API_BASE = "https://legis.senado.leg.br/dadosabertos"` e `CLASSES_SENADO = (33805062, 33809634, 33804850, 33809198)` (Agropecuária, Meio Ambiente, Indústria/Comércio/Serviços e Defesa Sanitária; os filhos, no campo `filhos`, são expandidos em tempo de execução). **[Fable E5]**

**Interfaces — Produces:**
- `como_lista(x) -> list`: `None` vira `[]`, um dict vira `[dict]` e uma lista volta como está.
- `listar_classes() -> list[dict]`
- `expandir_classes(raizes: tuple[int, ...]) -> list[int]`: as raízes mais todos os descendentes, sem repetição e em ordem.
- `listar_processos(numdias=None, codigo_classe=None, sigla=None, data_inicio=None, data_fim=None, tramitando=None) -> list[dict]`
- `buscar_processo(id_processo: int) -> dict`
- ~~`buscar_processo_por_identificacao`~~: **removida [Fable lacuna 3]**. Os gêmeos vêm do mapa (detalhe) e dos vínculos. A busca por identificação também é ambígua: há 5 pares com a mesma sigla, número e ano ("PL 699/2023" e o substitutivo).

As chamadas passam por `_get(caminho, params)`. Ele usa uma `requests.Session` com o header `Accept: application/json`, controla o ritmo (≤ 5 req/s, intervalo mínimo de 0,2 s entre chamadas), faz retry em 429/5xx (até 4 tentativas, espera de 2, 4 e 8 s) e levanta `RuntimeError` com a URL ao esgotar.

- [ ] **Passo 1: testes que falham**, com `requests.Session.get` mockado:
  - `como_lista` com os três formatos;
  - `expandir_classes` sobre uma árvore fixa de 3 níveis;
  - retry: o mock devolve 503, 503 e 200, e o resultado é o JSON, com 3 chamadas;
  - esgotar as tentativas levanta `RuntimeError`;
  - um 404 em `buscar_processo` levanta sem retry;
  - `expandir_classes` lê o campo `filhos`, conferido contra `data/senado_fase0/raw02/classes.json`.
- [ ] **Passo 2:** rodar. Esperado: FAIL.
- [ ] **Passo 3:** implementar. A árvore de `/processo/classes` traz `codigo`, `nome` e `filhos`.
- [ ] **Passo 4:** rodar a suíte. Esperado: PASS.
- [ ] **Passo 5:** commit `Cliente da API de Dados Abertos do Senado`.

### Tarefa 3.2: Bronze do Senado e mapa dos "Revisora"

**Files:**
- Modify: `sql/schema_bronze.sql`
- Create: `src/load_bronze_senado.py`
- Test: `tests/test_senado.py`

**Interfaces — Produces:**
- `bronze.sf_processo_json`: colunas `id_bronze BIGSERIAL PK`, `id_processo BIGINT NOT NULL` (nativo), `hash_payload TEXT NOT NULL`, `payload JSONB NOT NULL`, `data_extracao TIMESTAMP NOT NULL DEFAULT now()`, com índice em `(id_processo, data_extracao DESC)`.
- `bronze.sf_mapa_revisora`: colunas `id_processo BIGINT NOT NULL`, `sigla VARCHAR(20)`, `numero INT`, `ano INT` e `data_extracao TIMESTAMP NOT NULL DEFAULT now()`, com PK `(id_processo, sigla, numero, ano)`. São os números da Câmara de cada processo "Revisora".
- `load_bronze_senado.carregar_processo(conn, id_processo: int) -> str`: devolve `"ok"`, `"igual"` ou `"erro: …"`.
  - Calcula o `sha256` do JSON canônico (`sort_keys`) e só insere se for diferente do último hash daquele id.
  - Isola cada chamada como o `load_bronze` da Câmara: se der erro, faz rollback e devolve o erro.
  - Se a conexão cair, levanta `ConexaoPerdida`, reaproveitada de `load_bronze`.
- `load_bronze_senado.gravar_mapa(conn, id_processo: int, numeros: list[tuple[str, int, int]]) -> None`: upsert com `ON CONFLICT DO NOTHING`.

- [ ] **Passo 1: testes que falham.**
  - Com a conexão falsa (`FakeConnection` do `test_pipeline`, ou um mock):
    - o mesmo payload duas vezes gera 1 INSERT, e a segunda chamada devolve `"igual"`;
    - um payload diferente gera um novo INSERT;
    - um erro de API devolve `"erro: …"` e faz rollback.
  - Teste de texto no `schema_bronze.sql`: as duas tabelas, com `IF NOT EXISTS`.
- [ ] **Passo 2:** rodar. Esperado: FAIL.
- [ ] **Passo 3:** implementar.
- [ ] **Passo 4:** rodar a suíte. Esperado: PASS.
- [ ] **Passo 5:** commit `Bronze do Senado só quando o payload muda`.

### Tarefa 3.3: Silver do Senado (transformação)

**Files:**
- Modify: `sql/schema_silver.sql`. Acrescenta:
  - `ALTER TABLE silver.proposicoes_proponentes ADD COLUMN IF NOT EXISTS codigo_parlamentar_senado INT`;
  - `ADD COLUMN IF NOT EXISTS partido_autor_epoca VARCHAR(20)` e `uf_autor_epoca VARCHAR(5)`, com o partido e a UF do payload, para servir de reserva;
  - a tabela `silver.dim_senador` (`codigo INT PK`, `nome VARCHAR(255)`, `sigla_partido VARCHAR(20)`, `sigla_uf VARCHAR(5)`, `em_exercicio BOOLEAN`, `data_extracao TIMESTAMP`). **Os tipos têm de ser exatamente esses**, porque o `coalesce` com `dim_deputado` não pode mudar o tipo da coluna da view **[Fable E7]**;
  - `CREATE SCHEMA IF NOT EXISTS extensions; CREATE EXTENSION IF NOT EXISTS unaccent WITH SCHEMA extensions` **[Fable E7]**.
- Modify: `src/check_environment.py`. `REQUIRED_RELATIONS` passa a incluir `bronze.sf_processo_json`, `bronze.sf_mapa_revisora` e `silver.dim_senador`, e a verificação confere `to_regprocedure('extensions.unaccent(text)')`. **[Fable E7]**
- Create: `sql/transform_senado_to_silver.sql`
- Modify: `src/load_silver.py`, que recebe `executar_transformacao_senado(cur) -> None`. Ela executa o arquivo **no cursor recebido**, sem commit; quem chama decide.
- Test: `tests/test_senado.py`. Fixtures em `tests/fixtures/senado/`: payloads reais reduzidos da fase 0 (dados públicos) de PL 6028/2019 (8152618), PLS 631/2015 (2916834, `situacaoAtual` nula), PL 1879/2022 (8283772, informe repetido), MPV 1186/2023 (8537155, CN) e PL 6682/2025 (8981388, pré-2019 da Câmara).

**Regras da transformação** (sempre o último snapshot de cada `id_processo`; `k = 1000000000 + id_processo`):

- **Fora da silver [Fable lacuna 4, decisão minha]:** processos com `objetivo` 'Substitutivo' ou 'Emenda' (ex.: "PL 699/2023 (Substitutivo-CD)"). Eles repetem a sigla, o número e o ano do original e apareceriam como duas linhas iguais. A tramitação deles segue no processo original.
- **Casts:** só depois de conferir com a regex `^\S+ \d+/\d{4}$`. Existe "MPV 2163-41/2001". **[Fable E5]**

- **`silver.proposicao`** (upsert):
  - `id_proposicao = k`, `casa = 'SF'`, `id_origem = id_processo`, `codigo_materia`;
  - `sigla_tipo = payload.sigla`, `descricao_tipo = payload.descricaoSigla`, `numero = payload.numero::int` (sem zeros à esquerda), `ano`;
  - `ementa = conteudo.ementa`, `data_apresentacao = documento.dataApresentacao`;
  - `data_apresentacao_origem`:
    - `casa_iniciadora = 'SF'` ou nula: `documento.dataApresentacao`;
    - `'CN'`: `dataInicioEfetivo` (edição da MPV);
    - `'CD'`: **a `data_apresentacao` da versão da Câmara ligada.** É preenchida pelo UPDATE no fim da Tarefa 4.1, depois dos vínculos. Sem vínculo, fica 1º de janeiro do ano de `identificacaoProcessoInicial` **[Fable E2]**;
  - `casa_iniciadora = siglaCasaIniciadora`;
  - `descricao_situacao`: `situacaoAtual` quando preenchida (98% dos casos). Sem ela, a situação de todas as `autuacoes[].situacoes[]` ordenada por `inicio DESC, (fim IS NULL) DESC, ordinalidade DESC`, com `WITH ORDINALITY`. Esse desempate bateu 1.162/1.162 na fase 0 **[Fable E3]**;
  - `sigla_orgao_atual` e `id_orgao_atual = 1e9 + colegiado.codigo`, da mesma situação. Se o colegiado vier `{}`, usar `autuacoes[].codigoColegiadoControleAtual` / `siglaColegiadoControleAtual` **[Fable E4]**;
  - `descricao_tramitacao`, `despacho` (nulo) e `data_ultima_movimentacao`: do informe ordenado por `data DESC, id DESC` **[Fable E3]**;
  - `link_direto = 'https://www25.senado.leg.br/web/atividade/materias/-/materia/' || codigoMateria`;
  - `keywords_camara = documento.indexacao`.
- **`silver.proposicoes_proponentes`:**
  - origem: `autoriaIniciativa[]`, ou `documento.autoria[]` se a primeira estiver vazia;
  - `ordem_assinatura` = posição no array, `uri = NULL`, `nome = autor`, `codigo_parlamentar_senado = codigoParlamentar`;
  - `tipo` pelo `siglaTipo` (valores reais da fase 0) **[Fable E5]**:
    - SENADOR → 'Senador(a)';
    - DEPUTADO → 'Deputado(a) – via Senado' (2 vêm sem `codigoParlamentar`);
    - CAMARA → 'Câmara dos Deputados';
    - PRESIDENTE_REPUBLICA → 'Poder Executivo';
    - COMISSAO_SENADO → 'Comissão do Senado';
    - COMISSAO_CAMARA → 'Comissão da Câmara';
    - COMISSAO_CONGRESSO → 'Comissão Mista';
    - outro → o próprio `siglaTipo`.
  - `partido_autor_epoca = siglaPartido`, `uf_autor_epoca = uf` (o campo `siglaUf` vem nulo).
- **`silver.proposicao_tema`:** de `classificacoes[]`, com `cod_tema = codigo` e `tema = descricaoHierarquia`.
- **`silver.tramitacao`:**
  - `jsonb_array_elements` de todas as `autuacoes[].informesLegislativos[]`;
  - `sequencia = informe.id`, `data_hora = informe.data`, `sigla_orgao = colegiado.sigla`, `id_orgao = 1e9 + colegiado.codigo`, `descricao_tramitacao = descricao`, `casa = 'SF'`;
  - `eh_relator = descricao ~* <regex da 0.4 em POSIX, com \m no lugar de \b>`;
  - `data_extracao = now()`. É a "primeira vez vista", que define o que entra como movimentação nova no e-mail.
  - `ON CONFLICT DO NOTHING`. Ids repetidos no payload têm conteúdo igual.
- **`silver.dim_orgao`** (upsert) **[Fable E4]**:
  - colegiados dos informes e das situações, só os que têm `colegiado ? 'codigo'` (há 2.618 colegiados `{}` na população);
  - um por código, com `DISTINCT ON (codigo)` pelo informe mais recente;
  - `id_orgao = 1e9 + codigo`, `sigla` e `nome`;
  - `casa`: 'CN' quando `colegiado.casa = 'CN'`; senão 'SF'. A Mesa da Câmara (`casa 'CD'`) vista do Senado fica 'SF', porque é um id do Senado.
- **Guarda [Fable E6]:**
  - `proposicao` e `tramitacao` gravam `casa = 'SF'`;
  - todo comando sobre `proposicao`, `proposicoes_proponentes`, `proposicao_tema`, `tramitacao` e `dim_orgao` só toca id `>= 1e9`;
  - `proposicao_vinculo` tem `id_proposicao_sf >= 1e9`, garantido pela CHECK.

- [ ] **Passo 1: testes de texto que falham.**
  - O arquivo existe.
  - Os INSERTs de `silver.proposicao` e `silver.tramitacao` gravam `'SF'`.
  - Não há `DELETE` sem filtro de faixa ou de origem.
  - A tramitação usa `ON CONFLICT (id_proposicao, sequencia) DO NOTHING`.
  - O `objetivo` exclui Substitutivo e Emenda.
  - `dim_orgao` filtra `colegiado ? 'codigo'` e usa `DISTINCT ON`.
  - `load_silver.executar_transformacao_senado` executa o arquivo no cursor recebido sem chamar `commit`.
- [ ] **Passo 2:** rodar. Esperado: FAIL.
- [ ] **Passo 3:** implementar.
- [ ] **Passo 4: validação no container** `pg-senado-teste`: schema da `main` + este schema, e as 5 fixtures inseridas em `bronze.sf_processo_json`. Rodar a transformação duas vezes (idempotente) e conferir:
  - PLS 631/2015: situação não nula;
  - fixture sintética com 2 autuações e situações empatadas no `inicio`: a situação escolhida é a esperada;
  - fixture com colegiado `{}`: a transformação não falha;
  - PL 1879/2022: sem erro de PK e uma linha por id de informe;
  - MPV 1186/2023: `casa = 'SF'` e `casa_iniciadora = 'CN'`;
  - PL 6682/2025: `data_apresentacao_origem = 2016-01-01`;
  - `dim_orgao` com a CRA (1001307, 'SF');
  - CHECK de casa sem violação.
- [ ] **Passo 5:** commit `Transformação do Senado para a silver`.

### Tarefa 3.4: Gold do Senado (keywords sem acento e autor)

**Files:**
- Modify: `sql/schema_gold.sql`, `src/comparar_acompanhamento.py`
- Test: `tests/test_senado.py`, `tests/test_comparar_acompanhamento.py`

**Mudanças:**
- **`gold.vw_proposicao_keywords`:** para `p.casa = 'SF'`, o match usa `extensions.unaccent(...)` dos dois lados (texto e termo, no `termo` e no `termo_requerido`). Para a Câmara, a regra atual, sem mudança. Uma forma é um `CASE WHEN p.casa = 'SF' THEN extensions.unaccent(coalesce(p.ementa,'')) ~* extensions.unaccent(k.termo) … ELSE <atual> END`.
- **`gold.vw_monitoramento`, autor:**
  - `LEFT JOIN silver.dim_senador sen ON autor.tipo = 'Senador(a)' AND sen.codigo = autor.codigo_parlamentar_senado`;
  - `partido_autor_principal = coalesce(dep.sigla_partido, sen.sigla_partido, dep_grupo.sigla_partido, autor.partido_autor_epoca)` e o mesmo para a UF;
  - `dep_grupo`: o autor deputado da versão da Câmara do grupo (`g.chave_projeto < 1e9`, ordem 1, cast protegido). Ele só entra quando `p.casa = 'SF'` e o autor é 'Deputado(a) – via Senado'. É um único join pela chave, então não multiplica linhas.
- **`comparar_acompanhamento.rotulos_do_silver`:** a mesma regra por casa, via `CASE` no SQL dela.
- **`rotulos_de`:** ganha o parâmetro `casa="CD"`.

- [ ] **Passo 1: testes que falham.**
  - Texto da view: `extensions.unaccent` presente, só no ramo `casa = 'SF'`.
  - `dim_senador` no join do autor.
  - Teste de unicidade de linhas mantido (`test_monitoramento_colunas_no_fim_e_sem_join_que_multiplica`).
  - `rotulos_de` com `casa="SF"` gera SQL com `unaccent`.
- [ ] **Passo 2:** rodar. Esperado: FAIL.
- [ ] **Passo 3:** implementar.
- [ ] **Passo 4:** container:
  - a indexação "AGROINDUSTRIA" casa com a keyword de agroindústria só na linha SF;
  - uma linha da Câmara com o mesmo texto sem acento continua sem casar;
  - refresh das 6 MVs e unicidade OK.
- [ ] **Passo 5:** commit `Gold do Senado: keywords sem acento e autor`.

### Tarefa 3.5: Dimensão de senadores

**Files:**
- Create: `src/load_dim_senador.py`
- Test: `tests/test_senado.py`

**Interfaces — Produces:** `carregar_dim_senador() -> int`.
- Lê `/senador/lista/atual` (81 senadores, formato legado; usar `como_lista`).
- Busca `/senador/{codigo}` para cada `codigo_parlamentar_senado` de autores 'Senador(a)' ausentes da dim (ex-senadores).
- Faz upsert.
- **404 ou falha de um código não levanta [Fable E8]:** o código fica fora da dim, e a gold cai para `partido_autor_epoca`/`uf_autor_epoca`. Só falha da lista atual levanta.
- **Antes de codificar:** capturar uma fixture real de `/senador/lista/atual` e de um `/senador/{codigo}` (formato legado, não conferido na fase 0). **[Fable lacuna 9]**

- [ ] **Passo 1:** testes com a API mockada: atual com lista e com objeto único; ausente buscado; um 404 num código não levanta e grava os outros.
- [ ] **Passo 2:** rodar. Esperado: FAIL.
- [ ] **Passo 3:** implementar.
- [ ] **Passo 4:** rodar a suíte. Esperado: PASS.
- [ ] **Passo 5:** commit `Dimensão de senadores`.

### Tarefa 3.6: Carga diária do Senado

**Files:**
- Modify: `src/extract_senado.py`. Troca os stubs, mantendo os nomes. `executar_pautas_senado` continua stub até a fase 5.
- Modify: `src/config.py` (`SENADO_PRAZO_MIN = 30`, `SENADO_JANELA_DIAS = 14`, `SENADO_RECONCILIACAO_DIAS = 90`)
- Modify: `.github/workflows/pipeline.yml`, só se faltar variável. Não deve precisar.
- Test: `tests/test_senado.py` (classe `CargaSenadoTests`, espelhando `IncrementalTests`)

**Interfaces — Produces:**
- `calcular_numdias(conn, hoje: date) -> tuple[int, bool]`:
  - devolve `numdias = min(30, dias desde o último incremental_senado + 14)`, ou 30 se não houver;
  - `recarga_total = dias desde o último > 16`.
- `coletar_candidatos(numdias: int) -> list[int]`: as classes expandidas mais `sigla=MPV`, todas com `numdias`. Ids nativos, sem repetição.
- `ids_gemeos(conn) -> list[int]`: Tarefa 4.2.
- `executar_carga_senado() -> None`, nesta ordem:
  1. Calcula a janela.
  2. Coleta os candidatos. Erro de qualquer candidato é **bloqueante** para a janela `incremental_senado`.
  3. Atualiza o mapa dos "Revisora" (4.1) e junta as acompanhadas do Senado (`carregar_ids_acompanhadas(conn, casa="SF")` − 1e9) e os gêmeos (4.2, depois do mapa). Tudo **não bloqueante**.
  4. Se houver recarga total, soma todos os ids SF da gold.
  5. Reconciliação de 90 dias por apresentação: classes mais MPV, só os ausentes da bronze. É **não bloqueante**; registra `reconciliacao_senado` se completar.
  6. Carrega a bronze de todos, conferindo o prazo global a cada id: estourou, levanta `TimeoutError`.
  7. **Transformação numa transação** **[Fable E9]**:
     - `SET LOCAL lock_timeout = '30s'` e `SET LOCAL statement_timeout = '10min'`;
     - `executar_transformacao_senado(cur)`;
     - depois, a constante nova `SQL_DUPLICADAS_SENADO`: `GROUP BY id HAVING count(*) > 1` com `id >= 1e9`, sem `LIMIT`.
     - Se houver duplicata ou erro, `conn.rollback()` explícito e levanta. Senão, commit.
  8. `carregar_dim_senador()`.
  9. Registra `incremental_senado` se não houve erro bloqueante, e `reconciliacao_senado` se a reconciliação completou.
  10. **Erros não bloqueantes não viram "Senado não atualizado" [Fable E8]:**
      - a carga levanta `SenadoComPendencias(RuntimeError)`;
      - o orquestrador, em `extract_incremental`, grava o aviso como **"Senado atualizado com pendências: …"**, e só falhas bloqueantes (exceções de outro tipo) como "Senado não atualizado: …";
      - no n8n, o aviso continua aparecendo no topo do e-mail do modo completo. O texto deixa claro que os dados do Senado chegaram.
- CLI: `python extract_senado.py --bootstrap [--desde 2023-02-01] [--pausa 0.2]`. Não registra janela. Nesta ordem:
  1. classes por ano de apresentação (cada chamada cobre ≤ 1 ano), mais `tramitando=S` filtrado pelas classes, mais todas as MPVs desde a data;
  2. acompanhadas;
  3. mapa completo (4.1);
  4. **gêmeos (4.2)** **[Fable E10]**;
  5. transformação, com a mesma verificação de unicidade e o mesmo rollback;
  6. **`carregar_dim_senador()`** **[Fable lacuna 10]**.

- [ ] **Passo 1: testes que falham** (API e banco mockados):
  - sucesso registra `incremental_senado` e `reconciliacao_senado` depois da transformação;
  - erro num candidato não registra `incremental_senado` e levanta;
  - erro numa acompanhada ou num gêmeo registra `incremental_senado` e levanta `SenadoComPendencias` no fim. O orquestrador grava "Senado atualizado com pendências" (Review Focus 4);
  - prazo estourado (relógio mockado) levanta `TimeoutError` sem registrar;
  - duplicata no `SQL_DUPLICADAS` faz rollback da transformação e levanta, sem commit (Review Focus 5);
  - `calcular_numdias` com 1 dia, 20 dias e sem histórico devolve, respectivamente, (15, False), (30, True) e (30, False).
- [ ] **Passo 2:** rodar. Esperado: FAIL.
- [ ] **Passo 3:** implementar.
- [ ] **Passo 4:** rodar a suíte. Esperado: PASS. Os testes do orquestrador da fase 1 continuam verdes.
- [ ] **Passo 5:** commit `Carga diária do Senado`.

### Tarefa 3.7: Seeds

**Files:** Modify: `sql/seed_acompanhadas.sql`

- **Acompanhadas do Senado** (`planilha_antiga`, `id = 1000000000 + nativo`): 8283772 PL 1879/2022, 8992504 PL 433/2026, 8900340 PL 4363/2025, 7376720 PLS 168/2018, 7403160 PLS 302/2018, 2913579 PLS 326/2016, 2916834 PLS 631/2015, 2916662 PLS 650/2015 e 8537155 MPV 1186/2023.
- **Vínculos manuais** (`silver.proposicao_vinculo`, origem `'manual'`): (2092191, 1007364805), que é PL 5851/2016 ↔ PLC 10/2018, e (2344901, 1007403160), que é PL 3047/2022 ↔ PLS 302/2018. `ON CONFLICT DO NOTHING`.
- O seed roda antes de existir a silver do Senado. O vínculo não tem FK, e a `vw_grupo_projeto` parte da silver, então isso não quebra nada.

- [ ] **Passo 1:** teste de texto: 9 ids `>= 1000000000` e 2 vínculos manuais, com `ON CONFLICT DO NOTHING`.
- [ ] **Passo 2:** rodar. Esperado: FAIL.
- [ ] **Passo 3:** implementar.
- [ ] **Passo 4:** rodar a suíte. Esperado: PASS.
- [ ] **Passo 5:** commit `Acompanhadas do Senado e vínculos manuais no seed`.

---

## Fase 4 — Vínculo entre as casas

### Tarefa 4.1: Vínculos na transformação e mapa dos "Revisora"

**Files:** Modify: `sql/transform_senado_to_silver.sql`, `src/extract_senado.py`. Test: `tests/test_senado.py`.

**Vínculos** (no fim da transformação, `INSERT … ON CONFLICT DO NOTHING`, só para processos do Senado presentes na silver):
- **`'identificacao'`:** números da Câmara em `identificacaoProcessoInicial` (quando `siglaCasaIniciadora = 'CD'`) e em todos os `outrosNumeros[casaIdentificadora='CD']`, qualquer que seja a casa iniciadora.
  - Normalização: sigla, `ltrim(numero,'0')::int` e ano.
  - Casamento com `silver.proposicao` (`casa='CD'`) por sigla, número e ano.
- **`'revisora'`:** `bronze.sf_mapa_revisora` casado da mesma forma com a Câmara, para processos do Senado na silver.
- **`'mpv'`:** Senado `sigla='MPV'` com Câmara `sigla_tipo='MPV'`, mesmo número e ano, ano ≥ 2002, e `abs(dataInicioEfetivo do Senado − data_apresentacao da Câmara) ≤ 7 dias`.

**Mapa** (`extract_senado.atualizar_mapa_revisora(conn, completo: bool) -> int`) **[Fable E1]**:
- **Fonte:**
  - na carga inicial, `GET /processo?tramitando=S` (lista inteira);
  - na carga diária, `GET /processo?numdias=<janela>` sem classe (spec 4.4).
  - Nos dois casos, filtra `objetivo == 'Revisora'`.
- **Sempre o detalhe:** para todo id novo, busca `/processo/{id}` e grava só `identificacaoProcessoInicial` (se `siglaCasaIniciadora = 'CD'`) e `outrosNumeros[casaIdentificadora='CD']`. **Nunca** usa a `identificacao` da lista: 238 dos ~2.000 processos de 2019 em diante têm número diferente do da Câmara.
- Ids que já estão no mapa não são buscados de novo.
- Na carga inicial são ~2.065 detalhes (cerca de 7 min a 5 req/s); por dia, uma dúzia.
- Roda na carga diária como etapa **não bloqueante**, dentro do prazo global.

**Recriação dos vínculos [Fable E1]:** a transformação apaga e regrava os vínculos que não são manuais dos processos do Senado presentes na silver (`DELETE … WHERE origem <> 'manual' AND id_proposicao_sf IN (…)`, seguido de INSERT). Assim um vínculo errado não fica para sempre.

**Data de origem pela versão da Câmara [Fable E2]:** depois dos vínculos, um UPDATE nas linhas do Senado (id ≥ 1e9) com `casa_iniciadora = 'CD'`:
- `data_apresentacao_origem = coalesce((data_apresentacao da versão CD ligada mais antiga), make_date(ano de identificacaoProcessoInicial, 1, 1))`.

- [ ] **Passo 1: testes que falham.**
  - Texto: as três origens no SQL, a guarda de ano ≥ 2002 e os 7 dias na MPV.
  - `atualizar_mapa_revisora` com a lista mockada:
    - **todo id novo chama o detalhe**, inclusive um de 2019 com número diferente ("PL 395/2019" → grava "PL 6882/2017");
    - um id já mapeado não gera chamada.
  - Texto: o `DELETE` de vínculos filtra `origem <> 'manual'`; existe o UPDATE de `data_apresentacao_origem` pela versão CD.
- [ ] **Passo 2:** rodar. Esperado: FAIL.
- [ ] **Passo 3:** implementar.
- [ ] **Passo 4: container**, com as fixtures e a silver da Câmara do container:
  - inserir as versões da Câmara do PL 6028/2019 e da MPV 1186/2023;
  - inserir no mapa o PL 6682/2025 → PL 4314/2016, com a Câmara correspondente.

  Esperado:
  - 3 vínculos com as origens certas, `vw_grupo_projeto` com uma linha por id e o mesmo `chave_projeto` em cada par;
  - a versão do Senado do PL 6682/2025 com `data_apresentacao_origem` = data real do PL 4314/2016;
  - **regressão do radar:** uma proposição fictícia da Câmara apresentada em 15/09/2026, com keyword, ligada a uma versão fictícia do Senado, continua `em_radar` nas duas.
- [ ] **Passo 5:** commit `Vínculo entre as casas`.

### Tarefa 4.2: Gêmeos dos monitorados da Câmara na carga diária

**Files:** Modify: `src/extract_senado.py`. Test: `tests/test_senado.py`.

**Interfaces — Produces:** `ids_gemeos(conn) -> list[int]` (nativos), a união de:
- **(a)** processos de `bronze.sf_mapa_revisora` cujo número da Câmara casa com uma proposição da Câmara em `gold.vw_monitoramento`;
- **(b)** processos já ligados por vínculo a uma proposição da Câmara em `gold.vw_monitoramento`, para manter os gêmeos atualizados;
- **(c)** os vínculos manuais.

Os ids entram como não bloqueantes, na etapa 3 da 3.6.

- [ ] **Passo 1:** teste com o cursor mockado: as três origens sem repetição, convertidas para o id nativo.
- [ ] **Passo 2:** rodar. Esperado: FAIL.
- [ ] **Passo 3:** implementar.
- [ ] **Passo 4:** rodar a suíte. Esperado: PASS.
- [ ] **Passo 5:** commit `Gêmeos dos monitorados entram na carga do Senado`.

---

## Revisão e deploy (fases 3 e 4 juntas)

### Tarefa R: Revisão final da branch
- Pacote de revisão e revisor independente (Fable), com o Review Focus deste plano e o do plano principal.
- Fix pass com RED → GREEN, como na fase 1.

### Tarefa D: Deploy em produção (cada passo autorizado pelo Erick)
0. **Pré-condição [Fable lacuna 1] — dispensada pelo Erick em 28/10/2026.** Nenhum contexto de texto separa as SIM das NÃO de "produtor rural":
   - os temas coincidem (crédito rural, recuperação judicial, leite);
   - o melhor contexto mantém 11/11 SIM com precisão de 8%, e o mais restrito perde 3 SIM;
   - apagar a keyword tiraria 10 das 11 SIM do monitoramento;
   - o efeito no painel é nulo, porque `em_painel` usa só acompanhadas e SIM, e no radar é de cerca de 1 por mês.

   A pergunta sobre manter "produtor rural" no radar vai para a Ana.
1. Anotar o "antes": as mesmas contagens da 1.8 (banco e DAX), mais o tempo da `gold.vw_monitoramento` e **o `em_radar` de cada linha da Câmara** (id e valor), para comparar depois.
   - **[revisão final, I1] Pré-condição:** publicar no n8n o aviso que diferencia "Senado atualizado com pendências" de "não atualizado" antes de reativar o Agendador.
   - Rodar o `setup_db` primeiro dentro de `BEGIN … ROLLBACK`, para confirmar a permissão de `CREATE EXTENSION` no schema `extensions`.
   - Conferir onde a extensão está: `SELECT extnamespace::regnamespace FROM pg_extension WHERE extname = 'unaccent'`. Se estiver fora de `extensions`, ajustar antes do `setup_db`. **[Fable E7]**
2. Desativar o Agendador do n8n.
3. `setup_db` com o código da branch (extensão `unaccent`, tabelas, seed) e `ANALYZE`.
4. **Carga inicial pelo WSL:** `SENADO_TLS12=1 python extract_senado.py --bootstrap`. Estimativa: ~1.200 processos mais o mapa (~2.000 itens de lista e ~280 detalhes), cerca de 15 a 25 min. Conferir:
   - as 9 acompanhadas do Senado em `api.vw_monitoramento` com `casa='SF'`;
   - PL 6028/2019 Câmara (2229763) e Senado (1008152618) com o mesmo `chave_projeto`, as duas acompanhadas;
   - MPV 1376/2026 com as duas versões no mesmo grupo;
   - nenhuma duplicata na gold;
   - pendentes do e-mail (`em_radar and not acompanhada`, menos as marcadas) dentro do previsto na 0.2;
   - **[revisão final, I2]** listar as linhas da Câmara cujo `em_radar` mudou em relação ao "antes" e confirmar que todas são projetos que nasceram no Senado. Para esses, a data de origem passa a ser a do Senado, como diz o spec. Avisar a Ana se houver algum;
   - **[revisão final, M10]** conferir à mão os processos do Senado ligados a mais de uma proposição da Câmara (`SELECT id_proposicao_sf, count(DISTINCT id_proposicao_cd) FROM silver.proposicao_vinculo GROUP BY 1 HAVING count(*) > 1`). Nenhum grupo pode juntar projetos diferentes;
   - linhas que a consulta "Consultar Proposições" do n8n devolve com `casa='SF'` (estimativa: 12 a 15);
   - movimentações do Senado em `gold.vw_movimentacoes`, que vão para o primeiro e-mail. Elas entram como novas na carga inicial (informes dos últimos 30 dias das acompanhadas e dos grupos com SIM). **Decisão minha:** mostrar uma vez e avisar a Ana na mensagem;
   - linhas do Senado por keyword.
   - **Reversão**, se a carga inicial falhar depois do `setup_db`: as linhas do Senado são removíveis por faixa (`DELETE … WHERE id >= 1e9` nas tabelas da silver, nesta ordem: filhos, depois proposição; mais `proposicao_vinculo` de origem ≠ manual) e o código antigo ignora essas linhas.
5. Refresh das MVs do api (`load_api.atualizar_api()`) e tempo da gold: no máximo +1 s em relação ao passo 1.
6. Merge, `setup_db` de novo a partir da `main` e reativação do Agendador.
7. Verificação: a carga das 07h17 do dia seguinte tem de terminar verde, sem aviso do Senado, com o tempo do Senado registrado e com o e-mail e a planilha recebendo linhas do Senado com `casa = "Senado"`.
8. Power BI: refresh no Service e conferência dos DAX.
   - **Efeito transitório esperado:** até a fase 7, os KPIs contam versões (as do Senado entram como linhas novas).
   - A posição da ABCS precisa continuar ligada: as 7 identificações que existem nas duas casas são o mesmo projeto e casam pelo grupo, e as linhas com chave positiva têm de ficar iguais ao "antes".

**Mensagem à Ana** (depois do passo 7, rascunho aprovado pelo Erick):
- as proposições do Senado começaram a entrar, incluindo as 9 que estavam só na planilha antiga;
- o primeiro e-mail traz as movimentações recentes delas no Senado;
- a planilha ganha linhas com casa "Senado";
- o painel conta as duas versões até o ajuste final.

## Revisão final das fases 3 e 4 (Fable, 28/10/2026): mínimos adiados

- Na versão do Senado de um projeto da Câmara de 2026 que ficou fora dos temas da Câmara (sem vínculo), a data de reserva de 1º de janeiro deixa o projeto fora do radar. Só acontece em 2026.
- O órgão atual pode não ser o da autuação da situação quando há várias autuações e colegiado `{}`.
- O informe mais recente é ordenado sem `NULLS LAST` (todo informe real tem data).
- Com erro de processo da janela, as pendências não entram no texto do aviso.
- A opção `--pausa` do bootstrap não foi implementada; o ritmo fixo de 0,2 s do cliente atende.
- `DROP TABLE IF EXISTS sf_ultimo` sem `pg_temp.`.
- O CLAUDE.md será atualizado na fase 8.
