# Módulo /legislativo — Plano de implementação em produção

> **Para quem executar:** use superpowers:executing-plans (recomendado, a virada é sequencial e com o Erick presente) ou superpowers:subagent-driven-development. Os passos usam checkbox (`- [ ]`).

**Objetivo:** colocar o módulo `/legislativo` (Entrega 1) em produção no banco novo de São Paulo, trocar todos os consumidores da planilha e liberar a edição para a Ana, com reversão testada até esse momento.

**Arquitetura:** o banco legislativo de produção muda de projeto Supabase (para o projeto novo em sa-east-1, hoje vazio) e, na mesma janela, os consumidores deixam a planilha e passam a ler `gestao`/`contrato`/`api`. Tudo é ensaiado antes na homologação, que já está montada em sa-east-1. A produção atual fica intacta e somente leitura como reversão.

**Stack:** Postgres 17 (Supabase), Python 3.14 (`setup_db.py`, `importar_decisoes.py`, pipelines), GitHub Actions (`pipeline.yml`), n8n, Power BI (PBIP em `BI/`), Next.js na Vercel (repositório `banco-de-contatos-mailing`, branch `legislativo-entrega-1`).

**Spec:** `docs/superpowers/monitoramento-legislativo/prd.md` (§5 ordem da virada, §6 fases, CA01–CA14) e `plano.md` (§4, §5 e "Referência temporal na virada").

> Este documento **não autoriza** nenhuma ação em produção. Cada passo marcado **[PRODUÇÃO]** só roda com o "pode" explícito do Erick naquele momento. Antes de executar, a versão corrigida passa por nova revisão do Fable (ver "Registro de revisão").

## Restrições globais

- Ordem da virada (PRD §5): 1 congelar a planilha; 2 importação final com conflitos zerados; 3 fluxo principal do n8n lendo do banco; 4 inclusão lendo do banco; 5 Power BI lendo do banco; 6 liberar o sistema para a Ana. Os passos 1 a 5 têm reversão; depois do 6 só existe rollback da aplicação, que conserva o banco.
- Agenda mantida: carga completa 07h17, pautas 10h e 14h, Power BI 08:30/10:30/14:30 (Brasília). A virada não pode cair numa dessas janelas.
- **Nenhum fluxo de produção fica publicado apontando para o banco antigo depois que o banco novo virou a fonte.** A ordem da Tarefa 4 garante isso: os fluxos do n8n são publicados **antes** de a carga de produção ser apontada para o banco novo.
- `data_implantacao` é definida **uma vez**, depois da importação final sem conflitos e antes da Ana editar; nunca no ensaio; preservada em reexecuções:
  `UPDATE gestao.parametro SET valor = clock_timestamp()::text WHERE chave = 'data_implantacao' AND valor IS NULL;`
- `anon` e `authenticated` nunca leem `gestao`, `contrato`, histórico, parecer nem observações; a única exposição é a projeção do painel (`api.vw_painel_decisoes`, colunas fixas). Cadastro aberto do Auth do projeto legislativo desligado.
- Senhas dos papéis `legislativo_app`, `legislativo_n8n` e `legislativo_n8n_leitura` definidas à mão, só em cofre/`src/.env`/secret do ambiente; nunca em arquivo versionado, log, histórico do shell ou chat.
- **Destino explícito em todo comando de escrita.** `config.py` prioriza `DATABASE_URL` sobre `DB_*` e lê o `src/.env` sem override. Todo comando de escrita roda com `DATABASE_URL="$DATABASE_URL_SP"` (ou a variável do destino da vez) e começa conferindo `current_database()` e o host do destino. Se o host não for o do projeto novo, parar.
- Nenhuma automação lê ou escreve a planilha depois da virada (CA13). A aba "Acompanhamento manual" continua só para auditoria.
- Código, comentários, logs e docs em português. Pipeline: qualquer falha parcial levanta e não avança a janela `incremental`.
- Fluxos de inclusão e e-mail usam o webhook de **produção** do n8n com `X-Webhook-Token`; nunca o de teste.

## Foco da revisão

Cenários que o PRD implica mas nenhuma tarefa de código cobre; cada um tem teste/verificação na tarefa dona.

1. Disparo do Agendador, do gatilho de inclusão ou da planilha no meio da cópia (uma carga contra o banco antigo ou meio copiado) → Tarefa 4 passo 1 desliga tudo e espera `in_progress` **e** `queued` ficarem vazios.
2. Cópia incompleta de `bronze`/`silver.tramitacao` (alertas reenviados em massa porque `data_extracao` virou "novo") → Tarefa 3 confere contagens; Tarefa 4 confere que `gold.vw_movimentacoes` do destino é igual à da origem no instante da cópia.
3. `setup_db` no banco novo apagando grants (DROP CASCADE dos schemas `api`/`api_cache`) → sondagem de privilégios depois de cada `setup_db` (Tarefa 1 passo 2, Tarefa 2 passo 6, Tarefa 4 passo 3).
4. Pooler/SSL: n8n e Vercel falham por certificado ("self-signed") ou instruções preparadas no modo transação → Tarefa 2 testa as três conexões antes da virada.
5. Link público do Power BI deixar de atualizar ou apontar para o banco antigo depois de trocar URL e chave anon → Tarefa 6 confere "Painel atualizado em" e a conexão de nuvem; o refresh agendado fica pausado durante a troca.
6. Deploy automático da Vercel na `main` abrindo `/legislativo` antes da migração e das variáveis → merge do app só na Tarefa 7, depois da migração e das variáveis (ou com a rota desligada por flag).

---

## Mapa de arquivos e sistemas

| Onde | O que muda | Responsável |
|---|---|---|
| Este repo (`legislativo-fundacao` → `main`) | pré-requisitos de código (papel de leitura do n8n, sondagem de privilégios, `.env.example`, PBIP) e merge | Tarefa 1 |
| Repo `banco-de-contatos-mailing` | merge da `legislativo-entrega-1` na `main` (só na Tarefa 7); migration de capacidades no banco da plataforma | Tarefa 7 |
| Supabase de produção novo (sa-east-1, vazio; ref no `src/.env`) | schemas, papéis, dados, schemas expostos `gold, api`, Auth sem cadastro | Tarefas 2–4 |
| GitHub environment `DATABASE_URL` | trocar `DATABASE_URL` (e conferir `N8N_WEBHOOK_URL`/`TOKEN`) | Tarefa 4 |
| n8n `4F6Y2cOHhqNuhdYm`, `23CyodhPlORNJ4xS`, `0sieqPDvsqoZcs31` + novo "Legislativo — inclusão" | credenciais novas, leitura de `gestao`, fim das escritas na planilha | Tarefas 5 (preparo) e 4 (publicação) |
| Power BI (`BI/`) e serviço | parâmetros `SupabaseUrl`/`SupabaseAnonKey` no modelo **e** nas configurações do conjunto de dados publicado; projeção `api.vw_painel_decisoes`; "Painel atualizado em" | Tarefa 6 |
| Vercel (produção) | `LEGISLATIVO_DATABASE_URL`, URL/token do webhook, deploy, página com o painel | Tarefa 7 |

---

### Tarefa 1: Prontidão do código e portões de aprovação

**Arquivos:** `sql/papel_legislativo_app.sql` (só o `CREATE ROLE`), `sql/schema_contratos.sql` (grants e função do papel de leitura), `tests/test_sql_local.py`, `src/.env.example`, `sql/sondagem_privilegios.sql` (novo), modelo do PBIP em `BI/` (se as mudanças do modelo ainda não estiverem na branch).

**Consome:** branch `legislativo-fundacao` (este repo, HEAD `68913eb`), branch `legislativo-entrega-1` (app, HEAD `45ec73e`).
**Produz:** código de prontidão testado e PRs prontos, **sem merge na `main`** (o merge deste repo e a tag acontecem dentro da janela, Tarefa 4 passo 4; o do app, na Tarefa 7).

> **Por que o merge deste repo não vem antes da janela:** o Agendador dispara o workflow na `main`. Depois do merge, a `main` traz um `check_environment.py` que exige `api.vw_painel_decisoes`, `gestao.decisao_projeto` e `contrato.vw_projeto`, que o banco antigo não tem. Toda carga (07h17/10h/14h) falharia até a troca do secret, e a reversão deixaria a `main` nova apontando para o banco antigo.

- [ ] **Passo 1: Portões de decisão (todos precisam estar "sim" antes da Tarefa 4)**
  - Fable revisou a versão corrigida deste plano (ver "Registro de revisão"): sem bloqueante em aberto.
  - A Ana resolveu todos os conflitos da migração **na planilha** (decisão do Erick, 30/10/2026), e a importação final não tem conflito aberto (verificação: Tarefa 4, passo 4). Ensaio de 30/10 contra a homologação: 4 casos (3 divergências de posição entre Câmara e Senado e 1 proposição ausente na cópia de 29/10).
  - O Erick aprovou o aceite do piloto em homologação (CA11 feito pela Ana sem ajuda).
  - Janela combinada: dia útil fora de 07h–08h, 10h e 14h; Ana e Erick disponíveis.
  - Ensaio da Tarefa 3 concluído: contagens batendo com a origem e reversão ensaiada (runbook commitado).
  - Rascunhos da Tarefa 5 validados em homologação com `legislativo_n8n_leitura` (execução de teste; nenhuma chamada ao Google Sheets). Este é o portão do B2: sem ele, o `4F6…` novo não é publicado.
  - Token Google conferido (passo 5 desta tarefa) e relatório de `importar_decisoes.py` **sem `--aplicar`** sem conflito aberto, rodado antes da janela (I4: conflito descoberto depois do merge na `main` obrigaria a reverter o merge). O relatório se repete no passo 4 da Tarefa 4.
- [ ] **Passo 2: Papel de leitura do fluxo principal do n8n (fecha B3)**
  Inventariar, com `get_workflow_details` do `4F6Y2cOHhqNuhdYm`, cada leitura e escrita que o fluxo faz no banco (hoje ele lê a planilha; a versão de produção nova vai ler `gestao`/`contrato`). Com esse inventário, criar o papel `legislativo_n8n_leitura` com **somente** o que a lista exige:
  - `CREATE ROLE` em `sql/papel_legislativo_app.sql` (esse arquivo roda antes de `schema_contratos.sql` e só cria papéis).
  - Grants e função no fim de `sql/schema_contratos.sql`, junto dos grants do `legislativo_n8n` (~linhas 1321–1330), porque `drop_api.sql` e o `schema_gold` apagam grants a cada `setup_db`. Se o fluxo precisar de `gold.vw_movimentacoes` ou de `api_cache`, os grants são reaplicados depois do `schema_api`.
  - `SELECT` só nas views/funções de `contrato`/`gestao` necessárias; nunca por tabela inteira nem em histórico, parecer ou observações.
  - Checkpoint `alerta_movimentacoes`: `GRANT` não filtra por valor (`bronze.controle_execucao.tipo_carga` é `VARCHAR(30)` sem CHECK, `schema_bronze.sql:72`), então a escrita vai por uma função `SECURITY DEFINER` com `search_path` fixo e `EXECUTE` só para `legislativo_n8n_leitura`. Não habilitar RLS em tabela que as cargas usam.
    - A função é criada **antes** do bloco de `OWNER` (`schema_contratos.sql` ~linha 1276), no schema `gestao`, para entrar no loop que passa o dono a `gestao_dono`.
    - O dono `gestao_dono` precisa de três grants, além do `INSERT` em `bronze.controle_execucao`: `USAGE` no schema `bronze` e `USAGE` na sequência `bronze.controle_execucao_id_execucao_seq`. Sem eles o `INSERT` falha em runtime. Atualizar o comentário do arquivo (hoje diz "nada de bronze", `schema_contratos.sql:1261-1275`).
    - Assinatura: `gestao.registrar_alerta_movimentacoes(p_modo text, p_qtd int, p_instante timestamp)`. `executado_em` = `p_instante` em **UTC** (convenção das marcas internas: `data_extracao` e `executado_em` usam o `now()` de uma sessão UTC; ver `api.vw_ultima_carga`). O n8n lê `SELECT localtimestamp` **antes** das consultas do e-mail e o envia; a função rejeita instante nulo ou no futuro. Janela `data_inicio/fim` = dia de Brasília. Só o modo `completo` avança a marca. (Revisão do Fable, B1: a versão anterior deste plano mandava usar o `localtimestamp` lido na gravação; isso perdia tramitação carregada durante o envio, e gravar em Brasília deslocava a marca 3 horas.)
    - Leituras concedidas (inventário de 30/10 do `4F6Y2cOHhqNuhdYm`, B2): views gold do e-mail (`vw_grupo_projeto`, `vw_monitoramento`, `vw_pautas_monitoradas`, `vw_movimentacoes`, `vw_audiencias_de_interesse`), `silver.evento`, `silver.proposicao_acompanhada` (UPDATE só de `confirmada_em`) e `bronze.alerta_pauta` (SELECT, INSERT, DELETE). `gestao`/`contrato` ficam para a Tarefa 5, quando o rascunho do fluxo novo existir. `bronze.controle_execucao` só pela função.
    - Testes: a função grava o checkpoint; `legislativo_n8n_leitura` não consegue `INSERT` direto em `bronze.controle_execucao`.
  - Testes em `tests/test_sql_local.py`: o papel `legislativo_n8n` continua só executando as funções de inclusão (teste existente `test_legislativo_n8n_executa_so_o_fluxo_de_inclusao`, sem mudança). Acrescentar testes para `legislativo_n8n_leitura`: lê o que o fluxo precisa, não lê `gestao`/`contrato` por tabela, só consegue gravar o checkpoint pela função.
  - Esperado: `unittest` com esses testes rodando (sem pular) e `OK`.
- [ ] **Passo 3: Sondagem de privilégios para o banco de produção (fecha I1)**
  Criar `sql/sondagem_privilegios.sql`: um `SELECT` que devolve uma linha por verificação, com o resultado esperado na própria linha. Cobre `has_schema_privilege`/`has_table_privilege`/`has_function_privilege` para `anon`, `authenticated` e `PUBLIC` em `gestao`, `contrato` e `api_cache` (todos `false`), e a lista de colunas de `api.vw_painel_decisoes` (igual à lista aprovada no CA12). Rodar contra a homologação antes de liberar. Esperado: zero linha divergente.
  O teste local `test_sql_local` não serve como prova em produção: pula sem `TEST_DATABASE_URL` e recusa hosts que não sejam localhost. Por isso a sondagem é o checkpoint.
- [ ] **Passo 4: `.env.example` (fecha I2)**
  Documentar `DATABASE_URL_SP` (admin do banco novo de produção), `LEGISLATIVO_APP_DATABASE_URL` e `LEGISLATIVO_N8N_DATABASE_URL`, `LEGISLATIVO_N8N_LEITURA_DATABASE_URL`, sem valores.
- [ ] **Passo 5: Pré-requisitos do importador (fecha I3)**
  `importar_decisoes.py` precisa de `GOOGLE_SHEET_MONITORAMENTO_ID` e de credencial Google válida (`src/token_google.json` ou `GOOGLE_TOKEN_JSON`). Conferir que o token lê a planilha (leitura é suficiente para o ensaio; a planilha fica protegida na virada, então a conferência precisa ser feita antes do passo 1 da Tarefa 4).
- [ ] **Passo 6: Modelo do Power BI (fecha I10)**
  Confirmar, no PBIP da branch, se o modelo já lê `api.vw_painel_decisoes`, conta projetos por `uuid_projeto`, trata "Adiada" e exibe "Painel atualizado em" em Brasília. Se não, o ajuste entra aqui (commit no PBIP, sem URL nem chave) e é validado na Tarefa 6, passo 2.
- [ ] **Passo 7: Testes verdes neste repo**
  `.venv/bin/python -m compileall -q src tests && .venv/bin/python -m unittest discover -s tests -v`
  Esperado: `OK` com **0 skipped** em `test_sql_local` e `test_segredos`. Se algum estiver pulado, a causa é registrada e resolvida antes de seguir (o `OK` sozinho não prova privilégio).
- [ ] **Passo 8: Testes verdes no app**
  Rodar a bateria do `CLAUDE.md` do app (lint, typecheck, Vitest, pgTAP, build). Esperado: tudo passa; `tests/legislativo/ca11.spec.ts` passa contra a homologação.
- [ ] **Passo 9: Preparar o PR deste repo (sem mergear)**
  Integrar `95cb7a6` (#12, que está na `main` e não na branch) na `legislativo-fundacao`, rodar de novo os testes do passo 7 e abrir o PR. O merge e a tag acontecem na Tarefa 4, passo 4.

---

### Tarefa 2: Preparar o banco novo de produção (vazio)

**Arquivos:** nenhum. Usa `src/setup_db.py`, `sql/papel_legislativo_app.sql` e `src/check_environment.py`.

**Consome:** projeto de produção novo (sa-east-1); `DATABASE_URL_SP` (admin) no `src/.env`.
**Produz:** schemas aplicados, papéis com login, conexões testadas; ainda sem dados oficiais.

- [ ] **Passo 1: Confirmar o destino antes de qualquer escrita**
  Anotar o ref do projeto novo (do `src/.env`). Rodar `docker run --rm postgres:17 psql "$DATABASE_URL_SP" -Atc "select current_database(), current_user, (select count(*) from information_schema.schemata where schema_name in ('bronze','silver','gold','api','gestao'))"` e conferir que o ref novo aparece no usuário (`postgres.<ref>`; no Session pooler o host é só `aws-…pooler.supabase.com` e não identifica o projeto). A contagem é `0`. Se houver schemas, parar e perguntar ao Erick.
- [ ] **Passo 2: Aplicar os schemas** **[PRODUÇÃO]**
  De `src/`, com `DATABASE_URL="$DATABASE_URL_SP"`: `python setup_db.py`
  Esperado: "Schemas bronze, silver, gestao, gold, api e contrato … aplicados com sucesso."
- [ ] **Passo 3: Dimensões** **[PRODUÇÃO]**
  `python load_dimensoes.py` (carrega `dim_tema`/`dim_keyword` e atualiza o `api`).
- [ ] **Passo 4: Papéis com login, à mão (M1/M2)** **[PRODUÇÃO]**
  Os três papéis nascem `NOLOGIN` (`sql/papel_legislativo_app.sql`). No `psql` interativo: `ALTER ROLE <papel> LOGIN;` (sem senha; I3 do Fable: sem isso as três conexões falham no passo 6) e depois `\password <papel>` para `legislativo_app`, `legislativo_n8n` e `legislativo_n8n_leitura`, com senhas novas e distintas das da homologação (nunca `ALTER ROLE … PASSWORD '…'` em linha de comando ou histórico). No pooler do Supabase o usuário é `papel.<ref>`; anotar esse formato. Guardar as URLs no `src/.env` e no cofre.
- [ ] **Passo 5: Supabase: Data API e Auth (M3)** **[PRODUÇÃO]**
  Painel do projeto: schemas expostos = `gold, api` (nunca `gestao`/`contrato`); cadastro aberto do Auth **desligado**; TLS exigido; backup diário ligado e, se o plano permitir, PITR. Guardar captura de tela dessas três configurações como evidência.
- [ ] **Passo 6: Testar as conexões, o ambiente e os privilégios**
  - Admin: `python check_environment.py` com `DATABASE_URL="$DATABASE_URL_SP"`. Esperado: schemas presentes e keywords não vazias.
  - Sondagem: `sql/sondagem_privilegios.sql` rodada no banco novo. Esperado: zero divergência.
  - `legislativo_app`: `select 1` e uma chamada a uma função de `gestao` permitida; `insert` direto em tabela de `gestao` deve falhar.
  - `legislativo_n8n`: `gestao.reivindicar_inclusao` permitida; nenhuma leitura direta de `gestao`/`contrato`.
  - `legislativo_n8n_leitura`: as leituras do inventário da Tarefa 1, passo 2, funcionam; `gestao` por tabela falha.
  - Anônimo (chave anon do projeto novo): `GET /rest/v1/…` com `Accept-Profile: gestao` ou `contrato` deve dar erro de schema; `Accept-Profile: api` lê só a projeção esperada.
  Esperado: tudo conforme o PRD §5; anotar o modo do pooler (sessão ou transação) usado em cada conexão.

---

### Tarefa 3: Ensaio da migração de dados na homologação

**Arquivos:** criar `docs/superpowers/monitoramento-legislativo/runbook-virada.md` só com comandos e números do ensaio (sem dados reais, sem segredos).

**Consome:** homologação (sa-east-1; ref no `src/.env`); branch com os passos 2 a 4 da Tarefa 1 prontos (o `setup_db` do passo 1 aplica o papel e os grants novos).
**Produz:** runbook com tempos medidos, o comando exato de restore ensaiado e contagens de referência para a Tarefa 4.

- [ ] **Passo 1: Medir o banco de origem**
  `select schemaname, pg_size_pretty(sum(pg_total_relation_size(relid))) from pg_stat_user_tables group by 1` na produção atual (somente leitura; aviso ao Erick de que é leitura). **Padrão: copiar** `bronze` + `silver` + `bronze.controle_execucao`, porque `silver.tramitacao` acumula histórico e `data_extracao` alimenta `gold.vw_movimentacoes`. Recarregar pelo `extract_bronze.py` fica só como alternativa se o dump não couber.
- [ ] **Passo 2: Regra de restore (fecha B4) e ensaio**
  Ordem fixa, ensaiada na homologação numa cópia limpa:
  1. `setup_db.py` no destino (aplica a seed de `proposicao_acompanhada`).
  2. Antes do dump, conferir a paridade de tabelas e colunas de `bronze`/`silver` entre origem e destino (`information_schema.columns`). Coluna ou tabela que existe na origem e não no destino faz o `COPY` falhar; coluna a mais no destino fica com o default (ex.: `id_origem`, `data_apresentacao_origem` ficam NULL e o `setup_db` do passo 3 da Tarefa 4 faz o backfill, `schema_silver.sql:221`; por isso o setup roda **depois** do restore).
  3. `TRUNCATE ... CASCADE` das tabelas de `bronze` e `silver` listadas por nome (gerar o comando a partir de `information_schema`, para não esquecer nem sobrar tabela nova só no destino, como as do Senado, que ficam vazias sem erro). Seguro: `gestao` só referencia `gestao.projeto` e não há FK de `gold`/`api`/`gestao` para `silver`. A seed é descartada porque a origem já tem `planilha_antiga` e `inclusao_manual`; o dump é superconjunto dela.
  4. `pg_dump --data-only --schema=bronze --schema=silver` (inclui `controle_execucao` no `bronze` e os `setval` das sequências; conferir no ensaio) e restore com `psql -v ON_ERROR_STOP=1 --single-transaction`, **`TRUNCATE` e restore na mesma transação**, em conexão direta ou Session pooler (nunca pooler em modo transação). Sem superusuário no Supabase não há `--disable-triggers`; as FKs de `silver` são internas ao `silver` (`schema_silver.sql:28,41,51,129`) e o `pg_dump` ordena por dependência. Se uma FK falhar, o restore para e não é retentado com o erro escondido.
  5. Comparar `silver.dim_keyword` do destino com `src/keywords.py`; se divergir (o banco antigo pode estar defasado), rodar `load_dimensoes.py` (idempotente, não depende de extração). Se não divergir, não rodar.
  6. **Vínculo manual PL 3047/2022 × PLS 302/2018 (decisão da Ana, 30/10/2026: projetos diferentes).** A seed deixou de criar esse vínculo, mas a origem da cópia ainda o tem em `silver.proposicao_vinculo` (`id_proposicao_cd = 2344901`, `id_proposicao_sf = 1007403160`, `origem = 'manual'`). Depois do restore, **remover** essa linha com `DELETE ... WHERE` exato e conferir `count(*) = 0` antes de seguir. Sem isso, a cópia traz o vínculo de volta e o caso reaparece. **Homologação:** a separação em `gestao` já foi feita em 30/10 (versão do Senado movida para projeto próprio, origem `reconciliacao`, histórico registrado). **Produção não precisa dessa reconciliação:** a gestão nasce vazia e o `--aplicar` cria os dois projetos a partir da planilha, desde que o vínculo tenha sido removido.
  7. `importar_decisoes.py` (ensaio) → `importar_decisoes.py --aplicar` → `--aplicar` de novo, que não pode gravar nada (idempotência). Conferir que o relatório de "Gravado" bate com os números da importação de homologação (CA07).
  7. Pipeline `completo` na homologação. Anotar o tempo de cada etapa.
- [ ] **Passo 3: Contagens de referência**
  Gravar, para origem e destino, no instante da cópia: linhas por tabela de `bronze` e `silver`, `max(data_extracao)` de `silver.tramitacao`, `count(*)` de `api.vw_monitoramento`, e **`count(*)` de `gold.vw_movimentacoes` da origem**. Esperado: origem e destino iguais em todas as contagens. A `vw_movimentacoes` do destino deve ser igual à da origem naquele instante (o que a origem ainda não tinha alertado), não "vazia" (correção de I9).
- [ ] **Passo 4: Ensaiar a reversão**
  Na homologação: voltar `DATABASE_URL`/credenciais do n8n e do Power BI para a fonte anterior, reativar o gatilho da planilha em teste e confirmar que o fluxo antigo roda. Registrar no runbook o tempo e os cliques.
- [ ] **Passo 5: Commit do runbook**
  `git add docs/superpowers/monitoramento-legislativo/runbook-virada.md && git commit -m "Runbook da virada com tempos e contagens do ensaio"` (com a linha `Co-Authored-By` da conversa).

---

### Tarefa 4: Janela da virada — banco e pipeline **[PRODUÇÃO]**

**Arquivos:** nenhum. Segue o runbook da Tarefa 3. Os fluxos do n8n já estão **preparados como rascunho** (Tarefa 5, passos 1–3) e só são publicados no passo 6.

**Marcação:** o marcador **[PRODUÇÃO]** do título vale para **todos** os passos desta tarefa, inclusive os que não têm o marcador próprio (1, 2, 3, 4, 5, 7 e 8 escrevem em produção).

**Consome:** portões da Tarefa 1; banco preparado (Tarefa 2); contagens e comandos ensaiados (Tarefa 3); rascunhos do n8n (Tarefa 5).
**Produz:** banco novo com os dados oficiais, decisões importadas, `data_implantacao` gravada, fluxos publicados lendo o banco novo e o pipeline completo rodando nele.

- [ ] **Passo 1: Pausar tudo que escreve (fecha B2 e I6)**
  - n8n: despublicar o Agendador `0sieqPDvsqoZcs31`; despublicar o gatilho de 15 min do `23CyodhPlORNJ4xS` e o gatilho da planilha do fluxo de planilha (anotar o id de cada versão para restaurar). Execuções do n8n já em andamento não são interrompidas: conferir `search_workflow_executions` com status `running` e esperar zerar.
  - Power BI: pausar a atualização agendada do conjunto de dados no Service (08:30/10:30/14:30), para não rodar com parâmetros pela metade.
  - GitHub: esperar até não haver run do `pipeline.yml` em `in_progress`, `queued` ou `pending` (`gh run list --workflow pipeline.yml --limit 50 --json status --jq '[.[] | select(.status != "completed")] | length'` deve dar `0`), e conferir que nenhum outro workflow dispara `pipeline.yml` (inclusive o da planilha). **Medir de novo imediatamente antes do passo 2** (a cópia).
  - Planilha: aplicar a proteção de edição (**passo 1 da ordem da virada**) e avisar a Ana.
- [ ] **Passo 2: Cópia final dos dados oficiais**
  Seguir a Tarefa 3, passo 2, exatamente como ensaiado. Conferir as contagens e `count(*)` de `gold.vw_movimentacoes` contra a origem no mesmo instante da cópia (Tarefa 3, passo 3). **Divergência = parar.**
- [ ] **Passo 3: Schemas, privilégios e teste HTTP (fecha I1/M3)**
  `python setup_db.py` no destino (de novo, depois do restore), com destino conferido. Depois: `sql/sondagem_privilegios.sql` (zero divergência) e o teste HTTP anônimo da Tarefa 2, passo 6. Esperado: sem exposição de `gestao`/`contrato`. **Divergência = parar.**
- [ ] **Passo 3b: Merge deste repo e tag [PRODUÇÃO]**
  Só aqui, com o Agendador pausado e o banco novo já com os objetos que o `check_environment.py` da `main` exige: merge do PR de `legislativo-fundacao` → `main` e `git tag legislativo-entrega-1-prod && git push origin legislativo-entrega-1-prod` (sem `--tags`). Confirmar na `main` que `pipeline.yml` tem `ambiente` com padrão `producao`, para o Agendador (que não informa) continuar na produção. A reversão deste merge está na Tarefa 8.
- [ ] **Passo 4: Importação final com conflitos zerados (passo 2 da ordem)**
  Este relatório repete o portão da Tarefa 1 (passo 1): se houver conflito aqui, a virada para antes do passo 3b e a `main` não é tocada. `python importar_decisoes.py` (relatório): sem conflito aberto. Conferir que o relatório de "Gravado" bate com o ensaio da homologação (CA07). Só então `python importar_decisoes.py --aplicar` (o script recusa se houver conflito). Rodar de novo `--aplicar`: não deve gravar nada.
- [ ] **Passo 5: Referência de urgência (fecha CA06)**
  Conferir o host do destino e então executar o `UPDATE gestao.parametro … data_implantacao` das restrições globais. Depois `select valor from gestao.parametro where chave='data_implantacao'` e anotar o instante. Conferir que a lista de urgências/pendências de confirmação está coerente (sem urgência criada pela importação).
- [ ] **Passo 6: Publicar os fluxos do n8n que leem o banco novo (passos 3 e 4 da ordem) [PRODUÇÃO]**
  Publicar **só webhooks**, sem nenhum cron nem gatilho de planilha: o fluxo principal `4F6…` (Tarefa 5, passo 2) e o webhook do "Legislativo — inclusão" (Tarefa 5, passo 3), com as credenciais novas. Os crons de 15 min ficam despublicados até o passo 9: um cron publicado agora leria o banco novo e despacharia `modo=inclusao` que carrega no banco antigo, porque o secret ainda não virou. Verificar `get_workflow_details` (`connections`) depois de publicar.
  Esperado: nenhum node do Google Sheets ativo nesses fluxos.
- [ ] **Passo 7: Apontar o GitHub para o banco novo [PRODUÇÃO]**
  Só depois do passo 6: no environment `DATABASE_URL`, trocar o secret `DATABASE_URL` pela URL do pooler novo (Session pooler, porta 5432, `sslmode=require`). Guardar a URL antiga fora do repositório, para reversão. Assim, qualquer notificação feita pelo pipeline cai nos fluxos já migrados (fecha B1).
- [ ] **Passo 8: Carga completa de verificação [PRODUÇÃO]**
  `gh workflow run pipeline.yml -f modo=completo -f ambiente=producao`, acompanhar até o fim. Avisar a equipe antes: esta carga pode mandar e-mail legítimo de pendências.
  Esperado: job verde; `bronze.controle_execucao` com `incremental`, `eventos`, `reconciliacao` e o `alerta_movimentacoes` copiado; `api.vw_ultima_carga` com data de hoje; `gold.vw_movimentacoes` igual à da origem no instante da cópia mais o que veio depois.
  Divergência ou falha = reverter o secret do passo 7 (Tarefa 8).
- [ ] **Passo 9: Religar o Agendador e o gatilho de inclusão [PRODUÇÃO]**
  Só depois do passo 8 verde: republicar `0sieqPDvsqoZcs31` (07:17 `completo`, 10h/14h `pautas`) e ligar o **único** cron de inclusão (o do "Legislativo — inclusão"; o `23Cy…` antigo fica arquivado, nunca republicado). Antes das 10h, se possível. O gatilho de planilha do fluxo que dispara o GitHub **continua desligado**; a decisão sobre ele é da Tarefa 5, passo 4. Religar a atualização agendada do Power BI na Tarefa 6.
  Alarme de religação: registrar na Tarefa 9, passo 1, a conferência de que o Agendador está ativo no dia seguinte. Se a virada abortar, o Agendador desligado não pode passar despercebido.

---

### Tarefa 5: n8n — preparo dos fluxos (sem publicar) e CA13

**Arquivos:** nenhum no repo. Mudanças no n8n, validadas com `validate_workflow` e conferidas com `get_workflow_details` (o objeto `connections`) depois de cada alteração. **Os rascunhos ficam fora de produção até a Tarefa 4, passo 6.**

**Consome:** papéis `legislativo_n8n` e `legislativo_n8n_leitura` (Tarefas 1 e 2); workflow de homologação `JFY5o63SlUExlH6t` como modelo.
**Produz:** rascunhos prontos para publicar, inventário completo de Google Sheets e lista de credenciais.

- [ ] **Passo 1: Credenciais Postgres novas**
  Criar duas credenciais no n8n: `legislativo_n8n_leitura` (fluxo principal) e `legislativo_n8n` (inclusão), ambas com **Ignore SSL Issues** (o pooler do Supabase dá "self-signed certificate in certificate chain"). Nunca o admin.
- [ ] **Passo 2: Rascunho do fluxo principal `4F6Y2cOHhqNuhdYm` (passo 3 da ordem)**
  Salvar o id da versão atual (reversão). Trocar a leitura de relevância da planilha pelos contratos de `gestao`/`contrato` com `legislativo_n8n_leitura`; remover a escrita das novas pendências na aba Proposições; gravar o checkpoint `alerta_movimentacoes` em `bronze.controle_execucao` pelo papel que o Passo 2 da Tarefa 1 definiu; e-mail com link para o projeto no sistema e status "Adiada". **Não publicar.**
  Esperado (no rascunho, com a credencial nova apontando para homologação): execução de teste com webhook de teste; nenhuma chamada ao node do Google Sheets.
- [ ] **Passo 3: Rascunho da inclusão `23CyodhPlORNJ4xS` e do novo "Legislativo — inclusão" (passo 4 da ordem)**
  Há **um único** fluxo de inclusão em produção: o novo "Legislativo — inclusão"; o `23Cy…` antigo é arquivado na Tarefa 4, passo 9 (não coexistem). O novo fluxo é cópia do de homologação: webhook vindo do app, cron de 15 min, `gestao.reivindicar_inclusao` → Câmara → `registrar_inclusao_resolvida`/`falhar_inclusao` → `modo=inclusao` (`ambiente=producao`) → `concluir_inclusoes`, com `legislativo_n8n`. **Não publicar.** Anotar a URL do webhook de produção e o token (para a Tarefa 7).
- [ ] **Passo 4: Inventário de CA13 (fecha I8)**
  `search_workflows` e `search_workflow_executions` para listar **todos** os workflows com node do Google Sheets (incluindo o da planilha que dispara o GitHub e o Agendador). Para cada um: manter, desligar ou remover, com decisão do Erick. Confirmar que o PBIP não tem mais fonte da planilha (placeholders do link nos `.tmdl` continuam sendo a única referência).
- [ ] **Passo 5: Conferir CA13 depois da publicação (Tarefa 4, passo 6)**
  `search_workflow_executions` das execuções posteriores: nenhum node de Google Sheets executado nos fluxos `4F6…` e `23Cy…`.

---

### Tarefa 6: Power BI — passo 5 da ordem **[PRODUÇÃO]**

**Arquivos:** `BI/BI_Monitoramento_Proposicoes.SemanticModel/` (modelo lê a projeção única `api.vw_painel_decisoes`; contagem por `uuid_projeto`; "Adiada"; "Painel atualizado em"). Respeitar o filtro `segredos-pbi`: URL e chave nunca entram no repositório.

**Consome:** URL e anon key do projeto novo (em `BI/.env`); refresh agendado pausado (Tarefa 4, passo 1).
**Produz:** relatório publicado lendo o banco novo; link público inalterado.

- [ ] **Passo 1: Atualizar os parâmetros localmente**
  Em `BI/.env`: `SupabaseUrl` e `SupabaseAnonKey` do projeto novo. Fechar o Desktop antes de editar por arquivos (regra do projeto) e não rodar `gerar_paginas.py`.
- [ ] **Passo 2: Verificação no Desktop**
  Atualizar o modelo; conferir que a carteira, a contagem de projetos (por `uuid_projeto`) e `em_carteira` batem com a Carteira do sistema (CA03). Conferir "Painel atualizado em" em horário de Brasília.
- [ ] **Passo 3: Publicar sobre o mesmo relatório [PRODUÇÃO]**
  Republicar no mesmo workspace/relatório, para manter o link de "Publicar na Web" do README. Se o Service pedir nova credencial: conexão de nuvem `con_supabase_monitoramento` (Web, Anonymous) apontando para a URL nova.
- [ ] **Passo 4: Parâmetros no Service (I10)**
  Nas configurações do conjunto de dados publicado, atualizar `SupabaseUrl`/`SupabaseAnonKey` (o Service guarda os próprios parâmetros, não só o `.env`). Conferir que a conexão de nuvem aponta para a URL nova.
- [ ] **Passo 5: Atualização agendada**
  Forçar uma atualização e confirmar sucesso; religar o agendamento 08:30/10:30/14:30 (Tarefa 4, passo 9 dá o sinal). Abrir o link público em janela anônima: dados novos e hora do painel de hoje.
- [ ] **Passo 6: Conferir CA12**
  Com a chave anon nova, listar as colunas de `api.vw_painel_decisoes`: só as aprovadas (relevância, posição, prioridade, `em_carteira`, ids). Nada de ação, parecer, observações ou histórico. Bater com a lista da sondagem da Tarefa 1, passo 3.

---

### Tarefa 7: Aplicação — passo 6 da ordem e liberação para a Ana **[PRODUÇÃO]**

**Arquivos:** nenhum no repo do app além do que já está na branch. Configuração na Vercel e no banco da plataforma.

**Consome:** `legislativo_app` (Tarefa 2); URL/token do webhook do n8n de produção (Tarefa 5, passo 3); migration de capacidades do legislativo.
**Produz:** `/legislativo` em produção, Ana como única editora.

- [ ] **Passo 1: Confirmar o comportamento de deploy da Vercel (fecha I4)**
  Verificar na Vercel se o branch de produção é `main` e se o merge dispara deploy de produção automático. Se disparar, o merge do app em `main` só acontece depois dos passos 2 e 3; se não disparar, o merge pode ser feito no passo 3.
- [ ] **Passo 2: Migration de capacidades (antes do primeiro deploy de produção) [PRODUÇÃO]**
  No banco de produção **da plataforma** (não o legislativo): `supabase migration list` contra o projeto de produção. Se a migration de capacidades do legislativo ainda não estiver aplicada, aplicar e rodar o pgTAP correspondente. Conferir que o primeiro admin existe.
- [ ] **Passo 3: Variáveis da Vercel (ambiente Production)**
  `LEGISLATIVO_DATABASE_URL` = URL do pooler com `legislativo_app`; URL e token do webhook de produção do n8n (nomes iguais aos da Preview). Nunca copiar o token da homologação. Conferir os nomes exatos na Vercel antes de criar.
- [ ] **Passo 4: Merge do app e tag [PRODUÇÃO]**
  PR de `legislativo-entrega-1` → `main` no app, e `git tag legislativo-entrega-1-prod && git push origin legislativo-entrega-1-prod` no app. Deploy de produção.
  Verificação: abrir `/legislativo` com um usuário admin sem capacidade: leitura sim, edição não (CA01). Conferir nos logs da Vercel ausência de erro de instrução preparada no pooler. Conferir também leitor e usuário inativo (CA01).
- [ ] **Passo 5: Checkpoint go/no-go antes da linha de não retorno**
  Antes do passo 6: CA02, CA06, CA12 e CA13 verificados; reversão ainda possível; Ana avisada. Se algo falhar, reverter pela Tarefa 8.
- [ ] **Passo 6: Conceder a capacidade de editor à Ana [PRODUÇÃO]**
  Pela administração de usuários. Esta é a **linha de não retorno**: a partir daqui, reverter o n8n para a planilha usaria dados velhos.
- [ ] **Passo 7: Roteiro CA11 com a Ana em produção**
  Ela avalia pendências, muda uma posição, uma ação e uma prioridade, inclui um PL, confirma um movimento e exporta a carteira. Avisar antes que as mudanças são reais: geram urgência e e-mail reais e a inclusão persiste. O PL de teste é uma proposição real de interesse, combinada antes com a Ana e com o Erick.
  Esperado: pedido vai a "Concluída" em poucos minutos; a proposição aparece em `api.vw_painel_decisoes`; o e-mail de confirmação chega.
- [ ] **Passo 8: Painel do site**
  Página com o Power BI inserido e a frase "Decisões salvas aparecem aqui na próxima atualização do painel."

---

### Tarefa 8: Reversão (só até a Tarefa 7, passo 6; depois, só rollback da aplicação)

**Dono da decisão de reverter:** o Erick. **Critério:** qualquer divergência na Tarefa 4 (passos 2, 3, 4, 8), falha de carga em produção após o passo 8, ou falha de CA02/CA06/CA12/CA13 no checkpoint da Tarefa 7, passo 5. **[PRODUÇÃO]**

- [ ] **Até a Tarefa 7, passo 6:**
  1. GitHub: voltar o secret `DATABASE_URL` para a URL antiga (Tarefa 4, passo 7) **e reverter o merge na `main`** (revert do merge, ou disparar o workflow com `--ref` da versão antiga): a `main` nova exige objetos que o banco antigo não tem e a carga falharia no `check_environment`. Se a tag `legislativo-entrega-1-prod` tiver sido criada, apagar local e remoto: `git tag -d legislativo-entrega-1-prod && git push origin :refs/tags/legislativo-entrega-1-prod`.
  2. n8n, nesta ordem: despublicar o "Legislativo — inclusão" de produção (dois fluxos não podem reivindicar pedidos ao mesmo tempo); restaurar as versões salvas (`restore_workflow_version`) dos fluxos `4F6…` e `23Cy…` e do Agendador. **Restaurar uma versão não publica**: depois, **republicar explicitamente** o Agendador `0sieqPDvsqoZcs31`, o `23Cy…` (com o gatilho de 15 min) e o gatilho da planilha do fluxo que dispara o GitHub, se existia. Conferir que estão ativos no dia seguinte, antes da carga das 07h17.
  3. Power BI: voltar `SupabaseUrl`/chave no modelo e no Service; republicar; religar o refresh.
  4. Planilha: remover a proteção de edição.
  5. Conferir o banco antigo. **Limite:** a reversão é segura só até a carga do passo 8 da Tarefa 4: a partir dela o `4F6…` novo grava notificações e o checkpoint `alerta_movimentacoes` no banco novo, e esses dados precisam ser reconciliados antes de voltar (decisão do Erick). Avisar a Ana antes do passo 8.
- [ ] **Depois da linha de não retorno (Tarefa 7, passo 6):** só rollback da aplicação (redeploy do commit anterior na Vercel). O banco novo permanece fonte única; nada reativa a planilha.
- [ ] **Migration de capacidades (Tarefa 7, passo 2):** não é desfeita; é aditiva e a aplicação anterior a ignora.

---

### Tarefa 9: Estabilização e encerramento

**Arquivos:** `README.md` (status), `CLAUDE.md` (remover menções à planilha como fonte; documentar o banco novo), `docs/superpowers/monitoramento-legislativo/plano.md` (marcar a Entrega 1 como em produção).

- [ ] **Passo 1: D+0 (religação) e D+1 a D+3**
  - D+0: conferir que o Agendador e o gatilho de inclusão estão ativos e que a próxima execução (10h ou 14h) saiu.
  - D+1 a D+3: carga das 07h17 verde; pautas 10h/14h; `api.vw_ultima_carga`; e-mails sem duplicar; fila de inclusões sem pedido preso em "carregando" por mais de 2 horas (alinhado a CA08).
- [ ] **Passo 2: Cenários controlados (PRD §6 fase 5)**
  Conflito de versão (duas abas editando o mesmo projeto), pedido duplicado, falha de carga com retomada, cancelamento. Esperado: nenhuma sobrescrita silenciosa; falha visível, sem "atualização falsa" (CA10).
- [ ] **Passo 3: Sondagem de privilégios depois de uma carga real** (CA09/CA12): rodar `sql/sondagem_privilegios.sql` depois do `setup_db`/cache do dia seguinte, com o admin (`DATABASE_URL="$DATABASE_URL_SP"`, host conferido pelo ref, como na Tarefa 2, passo 1); decisões e confirmações intactas.
- [ ] **Passo 4: Descomissionar [PRODUÇÃO] (D+30 no mínimo, só com pedido do Erick)**
  Pausar (não excluir) o projeto Supabase antigo de produção e a homologação antiga; manter o backup por mais tempo; remover secrets antigos. A exclusão só depois de um mês sem reversão.
- [ ] **Passo 5: Documentação e commit**
  Atualizar os docs acima e a nota de memória do projeto; commit `docs: Entrega 1 do legislativo em produção`.

---

## Autoavaliação

- **Cobertura do PRD:** ordem da virada (Tarefas 4–7), baseline (T3/T4), CA01/02/06/07/08/09/10/11/12/13 cobertos com verificação em produção (T7 passo 4, T4 passo 5, T4 passo 4, T9 passo 2, T9 passo 3, T7 passo 7, T6 passo 6, T5 passo 4). CA03 na T6; CA04, CA05 e CA14 cobertos por testes automatizados (T1 passo 7, com 0 skipped) e não têm verificação própria em produção.
- **Não verificado ao escrever (conferir na execução):** tamanho do bronze na origem (T3, passo 1); se a migration de capacidades já foi aplicada no banco da plataforma (T7, passo 2); os nomes exatos das variáveis na Vercel (T7, passo 3); o estado atual dos fluxos do n8n e o inventário de `get_workflow_details` do `4F6…` (T1, passo 2); se o plano do Supabase novo inclui backup/PITR (T2, passo 5); se o merge do app dispara deploy (T7, passo 1). O plano trata cada um como verificação, não como fato.
- **Decisão confirmada pelo Erick (30/10/2026):** copiar `bronze` e `silver` (T3, passo 1), em vez de recarregar o bronze.
- **Decisões que o Erick ainda precisa confirmar:** destino dos workflows de Google Sheets que não são do legislativo (T5, passo 4); limite de reversão depois da primeira execução de produção (T8).

## Registro de revisão

- [x] Revisão do Fable da versão original (30/10/2026, somente leitura): **aprovado com ajustes**. Bloqueantes: B1 (ordem n8n × carga de produção), B2 (gatilhos ativos durante a cópia; espera sem `queued`), B3 (papel do n8n insuficiente), B4 (restore com colisão com a seed e as dimensões). Importantes e menores atendidos nesta versão: destino por comando, sondagem de privilégios, Google, deploy da Vercel, HEAD, tags, reversão, CA06/CA13/`origem`, `vw_movimentacoes` (criterio igual à origem), Power BI, senhas, limiares.
- [x] Segunda revisão do Fable (30/10/2026): **reprovado** por N1 (merge na `main` antes da janela quebra a carga e a reversão). Os 4 bloqueantes originais foram resolvidos no desenho. Corrigido: merge e tag movidos para a Tarefa 4 passo 3b e reversão do merge na Tarefa 8; webhooks no passo 6 e crons só no passo 9, com fluxo único de inclusão; grants do papel de leitura em `schema_contratos.sql` e checkpoint por função `SECURITY DEFINER`; restore com `ON_ERROR_STOP`, `--single-transaction`, paridade de colunas e comparação de `dim_keyword`; ref do projeto conferido pelo usuário do pooler; `--limit 50` e medição repetida da fila; limite da reversão no passo 8.
- [x] Terceira revisão do Fable (30/10/2026): **aprovado com ajustes**, sem bloqueante. Correções aplicadas: (I-1) checkpoint com grants de `gestao_dono` em `bronze` e na sequência, função antes do bloco de OWNER, `NOT NULL` da janela, `localtimestamp` do banco; (I-2) republicação explícita do Agendador, do `23Cy…` e do gatilho da planilha na reversão; (M-1) dependência da Tarefa 1 na Tarefa 2; (M-2) gatilho da planilha segue desligado na Tarefa 4 passo 9; (M-3) apagar a tag no remoto; (M-4) marcador [PRODUÇÃO] vale para toda a Tarefa 4; (M-5) numeração da Tarefa 3; (M-6) URL do admin na sondagem da Tarefa 9.
- [x] Onde a Ana resolve os conflitos: **na planilha** (decisão do Erick, 30/10/2026), como já previam o PRD e o `importar_decisoes.py`.
- [x] Quarta revisão do Fable (30/10/2026): **reprovado** com B1 (checkpoint em Brasília, 3 h de atraso; o código estava errado, o plano certo), B2 (papel de leitura sem os grants do fluxo) e I1 a I5. Corrigidos no código (commit `d365761`, PR #13): checkpoint em UTC com instante lido antes das consultas, grants de leitura do inventário. Corrigidos no plano nesta rodada: I3 (`ALTER ROLE … LOGIN`), I4 (relatório do importador como portão antes do merge), I5 (portões do ensaio, dos rascunhos da Tarefa 5 e do token Google), B2 (portão de homologação com o papel de leitura). Pendente: nova revisão do Fable sobre esta versão. M1 (INSERT herdado por `gestao_dono` em `controle_execucao`) e M3 (isenção da sondagem por nome) registrados, sem mudança nesta rodada.
- [ ] Portão dos conflitos: pendente da Ana zerar a lista. Este registro não autoriza nenhum passo [PRODUÇÃO].
