# Módulo /legislativo — Plano de implementação em produção

> **Para quem executar:** use superpowers:executing-plans (recomendado, a virada é sequencial e com o Erick presente) ou superpowers:subagent-driven-development. Os passos usam checkbox (`- [ ]`).

**Objetivo:** colocar o módulo `/legislativo` (Entrega 1) em produção no banco novo de São Paulo, trocar todos os consumidores da planilha e liberar a edição para a Ana, com reversão testada até esse momento.

**Arquitetura:** o banco legislativo de produção muda de projeto Supabase (para o projeto novo em sa-east-1, hoje vazio) e, na mesma janela, os consumidores deixam a planilha e passam a ler `gestao`/`contrato`/`api`. Tudo é ensaiado antes na homologação, que já está montada em sa-east-1. A produção atual fica intacta e somente leitura como reversão.

**Stack:** Postgres 17 (Supabase), Python 3.14 (`setup_db.py`, `importar_decisoes.py`, pipelines), GitHub Actions (`pipeline.yml`), n8n, Power BI (PBIP em `BI/`), Next.js na Vercel (repositório `banco-de-contatos-mailing`, branch `legislativo-entrega-1`).

**Spec:** `docs/superpowers/monitoramento-legislativo/prd.md` (§5 ordem da virada, §6 fases, CA01–CA14) e `plano.md` (§4, §5 e "Referência temporal na virada").

> Este documento **não autoriza** nenhuma ação em produção. Cada passo marcado **[PRODUÇÃO]** só roda com o "pode" explícito do Erick naquele momento. Antes de executar, o plano passa pela revisão do Fable.

## Restrições globais

- Ordem da virada (PRD §5): 1 congelar a planilha; 2 importação final com conflitos zerados; 3 fluxo principal do n8n lendo do banco; 4 inclusão lendo do banco; 5 Power BI lendo do banco; 6 liberar o sistema para a Ana. Os passos 1 a 5 têm reversão; depois do 6 só existe rollback da aplicação, que conserva o banco.
- Agenda mantida: carga completa 07h17, pautas 10h e 14h, Power BI 08:30/10:30/14:30 (Brasília). A virada não pode cair numa dessas janelas.
- `data_implantacao` é definida **uma vez**, depois da importação final sem conflitos e antes da Ana editar; nunca no ensaio; preservada em reexecuções:
  `UPDATE gestao.parametro SET valor = clock_timestamp()::text WHERE chave = 'data_implantacao' AND valor IS NULL;`
- `anon` e `authenticated` nunca leem `gestao`, `contrato`, histórico, parecer nem observações; a única exposição é a projeção do painel (colunas fixas). Cadastro aberto do Auth do projeto legislativo desligado.
- Senhas dos papéis `legislativo_app` e `legislativo_n8n` definidas à mão, só em cofre/`src/.env`/secret do ambiente; nunca em arquivo versionado, log ou chat.
- Nenhuma automação lê ou escreve a planilha depois da virada (CA13). A aba "Acompanhamento manual" continua só para auditoria.
- Código, comentários, logs e docs em português. Pipeline: qualquer falha parcial levanta e não avança a janela `incremental`.
- Fluxos de inclusão e e-mail usam o webhook de **produção** do n8n com `X-Webhook-Token`; nunca o de teste.

## Foco da revisão

Cenários que o PRD implica mas nenhuma tarefa de código cobre; cada um tem teste/verificação na tarefa dona.

1. Disparo do Agendador no meio da cópia dos dados (uma carga rodando contra o banco antigo enquanto se copia) → Tarefa 4 pausa o Agendador e espera o job terminar.
2. Cópia incompleta de `bronze`/`silver.tramitacao` (alertas reenviados em massa porque `data_extracao` virou "novo") → Tarefa 3 confere contagens e a Tarefa 4 confere `gold.vw_movimentacoes` vazia.
3. `setup_db` no banco novo apagando grants (DROP CASCADE dos schemas `api`/`api_cache`) → Tarefas 2 e 4 reexecutam o teste de privilégios depois de cada `setup_db`.
4. Pooler/SSL: n8n e Vercel falham por certificado ("self-signed") ou instruções preparadas no modo transação → Tarefa 2 testa as três conexões antes da virada.
5. Link público do Power BI deixar de atualizar ou apontar para o banco antigo depois de trocar URL e chave anon → Tarefa 6 confere "Painel atualizado em" e a conexão de nuvem.

---

## Mapa de arquivos e sistemas

| Onde | O que muda | Responsável |
|---|---|---|
| Este repo `main` | merge da branch `legislativo-fundacao` (inclusive os commits de 29/10) | Tarefa 1 |
| Repo `banco-de-contatos-mailing` `main` | merge da `legislativo-entrega-1`; migration de capacidades no banco da plataforma | Tarefas 1 e 5 |
| Supabase de produção novo (sa-east-1, vazio; ref no `src/.env`) | schemas, papéis, dados, schemas expostos `gold, api`, Auth sem cadastro | Tarefas 2–4 |
| GitHub environment `DATABASE_URL` | trocar `DATABASE_URL` (e conferir `N8N_WEBHOOK_URL`/`TOKEN`) | Tarefa 4 |
| n8n `4F6Y2cOHhqNuhdYm`, `23CyodhPlORNJ4xS`, `0sieqPDvsqoZcs31` + novo "Legislativo — inclusão" | credencial Postgres nova, leitura de `gestao`, fim das escritas na planilha | Tarefa 5 |
| Power BI (`BI/`) | parâmetros `SupabaseUrl`/`SupabaseAnonKey`, projeção única, "Painel atualizado em" | Tarefa 6 |
| Vercel (produção) | `LEGISLATIVO_DATABASE_URL`, deploy, página com o painel | Tarefa 7 |

---

### Tarefa 1: Prontidão do código e portões de aprovação

**Arquivos:** nenhum novo. Verificação nos dois repositórios.

**Consome:** branch `legislativo-fundacao` (este repo, HEAD `f6674f5`), branch `legislativo-entrega-1` (app, HEAD `45ec73e`).
**Produz:** `main` dos dois repos com o módulo; tag `legislativo-entrega-1-prod` em cada um.

- [ ] **Passo 1: Portões de decisão (todos precisam estar "sim" antes da Tarefa 4)**
  - Fable revisou este plano. Registrar o resultado no fim deste arquivo.
  - A Ana resolveu todos os conflitos da migração na planilha (a verificação é a Tarefa 3, passo 3).
  - O Erick aprovou o aceite do piloto em homologação (CA11 feito pela Ana sem ajuda).
  - Janela combinada: dia útil fora de 07h–08h, 10h e 14h; Ana e Erick disponíveis.
- [ ] **Passo 2: Testes verdes neste repo**
  Rodar `.venv/bin/python -m compileall -q src tests && .venv/bin/python -m unittest discover -s tests -v`
  Esperado: `OK`, incluindo `test_sql_local` (privilégios) e `test_segredos`.
- [ ] **Passo 3: Testes verdes no app**
  Rodar a bateria do `CLAUDE.md` do app (lint, typecheck, Vitest, pgTAP, build). Esperado: tudo passa; `tests/legislativo/ca11.spec.ts` passa contra a homologação.
- [ ] **Passo 4: Merge e tag**
  PR de `legislativo-fundacao` → `main` neste repo, PR de `legislativo-entrega-1` → `main` no app. Depois do merge: `git tag legislativo-entrega-1-prod && git push --tags` nos dois.
  O workflow `pipeline.yml` na `main` já tem o input `ambiente` com padrão `producao`, então o Agendador (que não informa) continua na produção.

---

### Tarefa 2: Preparar o banco novo de produção (vazio)

**Arquivos:** nenhum. Usa `src/setup_db.py`, `sql/papel_legislativo_app.sql` e `src/check_environment.py`.

**Consome:** projeto de produção novo (sa-east-1); `DATABASE_URL_SP` (admin) no `src/.env`.
**Produz:** schemas aplicados, papéis com login, conexões testadas; ainda sem dados oficiais.

- [ ] **Passo 1: Confirmar o destino antes de qualquer escrita**
  Rodar `docker run --rm postgres:17 psql "$DATABASE_URL_SP" -Atc "select current_database(), inet_server_addr(), (select count(*) from information_schema.schemata where schema_name in ('bronze','silver','gold','api','gestao'))"`
  Esperado: o ref/host é o do projeto de produção novo (sa-east-1, conferir no `src/.env`) e a contagem é `0`. Se houver schemas, parar e perguntar ao Erick.
- [ ] **Passo 2: Aplicar os schemas** **[PRODUÇÃO]**
  De `src/`, com `DATABASE_URL="$DATABASE_URL_SP"`: `python setup_db.py`
  Esperado: "Schemas bronze, silver, gestao, gold, api e contrato … aplicados com sucesso."
- [ ] **Passo 3: Dimensões** **[PRODUÇÃO]**
  `python load_dimensoes.py` (carrega `dim_tema`/`dim_keyword` e atualiza o `api`).
- [ ] **Passo 4: Papéis com login, à mão**
  `ALTER ROLE legislativo_app LOGIN PASSWORD '…'` e idem `legislativo_n8n`, com senhas novas e distintas das da homologação. Guardar no `src/.env` (`LEGISLATIVO_APP_DATABASE_URL`, `LEGISLATIVO_N8N_DATABASE_URL`) e no cofre.
- [ ] **Passo 5: Supabase: Data API e Auth**
  Painel do projeto: schemas expostos = `gold, api` (nunca `gestao`/`contrato`); cadastro aberto do Auth **desligado**; TLS exigido; backup diário ligado e, se o plano permitir, PITR.
- [ ] **Passo 6: Testar as três conexões e o ambiente**
  - Admin: `python check_environment.py` com `DATABASE_URL="$DATABASE_URL_SP"`. Esperado: schemas presentes e (ainda) keywords não vazias.
  - `legislativo_app`: `select 1` e uma chamada a uma função de `gestao` permitida; `insert` direto em tabela de `gestao` deve falhar.
  - `legislativo_n8n`: `gestao.reivindicar_inclusao` permitida; leitura de `silver.proposicao_acompanhada` conforme o papel.
  - Anônimo (chave anon do projeto novo): `GET /rest/v1/…` com `Accept-Profile: gestao` deve dar erro de schema; `Accept-Profile: api` lê só views esperadas.
  Esperado: tudo conforme o PRD §5; anotar o modo do pooler (sessão ou transação) usado em cada conexão.

---

### Tarefa 3: Ensaio da migração de dados na homologação

**Arquivos:** criar `docs/superpowers/monitoramento-legislativo/runbook-virada.md` só com comandos e números do ensaio (sem dados reais, sem segredos).

**Consome:** homologação (sa-east-1; ref no `src/.env`), cópia da `silver` já feita em 29/10.
**Produz:** roteiro com tempos medidos e contagens de referência para a Tarefa 4.

- [ ] **Passo 1: Medir o banco de origem**
  `select schemaname, pg_size_pretty(sum(pg_total_relation_size(relid))) from pg_stat_user_tables group by 1` na produção atual (somente leitura). Decidir com base no tamanho: copiar `bronze` + `silver` (+ `bronze.controle_execucao`) por `pg_dump --data-only`, ou recarregar o bronze pelo `extract_bronze.py` (mais lento, mas sem copiar). **Padrão recomendado: copiar**, porque `silver.tramitacao` acumula histórico de todas as linhas do bronze e `data_extracao` (primeira vez vista) alimenta `gold.vw_movimentacoes`.
- [ ] **Passo 2: Ensaiar o ciclo completo numa cópia limpa da homologação**
  Esvaziar um banco de teste (ou usar o de homologação após `drop schema … cascade`), rodar: `setup_db` → restore dos dados → `load_dimensoes` → `importar_decisoes.py` (ensaio) → pipeline `completo` na homologação. Anotar o tempo de cada etapa.
- [ ] **Passo 3: Contagens de referência**
  Gravar, para origem e destino: linhas por tabela do `bronze` e `silver`, `max(data_extracao)` de `silver.tramitacao`, e `count(*)` de `api.vw_monitoramento`. Esperado: iguais entre origem e destino; `gold.vw_movimentacoes` do destino **vazia** logo após a cópia (nada "novo" para alertar).
- [ ] **Passo 4: Ensaiar a reversão dos passos 1 a 5**
  Na homologação: voltar `DATABASE_URL`/credenciais do n8n e do Power BI para a fonte anterior e confirmar que o fluxo antigo roda. Registrar no runbook o tempo e os cliques.
- [ ] **Passo 5: Commit do runbook**
  `git add docs/superpowers/monitoramento-legislativo/runbook-virada.md && git commit -m "Runbook da virada com tempos e contagens do ensaio"` (com a linha `Co-Authored-By` da conversa).

---

### Tarefa 4: Janela da virada — banco e pipeline **[PRODUÇÃO]**

**Arquivos:** nenhum. Segue o runbook da Tarefa 3.

**Consome:** portões da Tarefa 1; banco preparado (Tarefa 2); contagens de referência (Tarefa 3).
**Produz:** banco novo com os dados oficiais, decisões importadas, `data_implantacao` gravada e o pipeline completo rodando nele.

- [ ] **Passo 1: Pausar o que escreve**
  - n8n: despublicar o Agendador `0sieqPDvsqoZcs31` (anotar o id da versão para restaurar).
  - GitHub: esperar `gh run list --workflow pipeline.yml --status in_progress` vazio.
  - Planilha: aplicar a proteção de edição (**passo 1 da ordem da virada**) e avisar a Ana.
- [ ] **Passo 2: Cópia final dos dados oficiais**
  `pg_dump --data-only` de `bronze`, `silver` (e `controle_execucao`) da produção atual → restore no banco novo, como ensaiado. Reexecutar `python load_dimensoes.py` e `python load_dim_deputado.py` só se o ensaio mostrou necessidade.
  Conferir as contagens da Tarefa 3, passo 3. **Divergência = parar.**
- [ ] **Passo 3: Reaplicar schemas e privilégios**
  `python setup_db.py` (de novo, depois do restore) e repetir o teste de privilégios da Tarefa 2, passo 6. Esperado: sem exposição de `gestao`/`contrato` depois do `setup_db`.
- [ ] **Passo 4: Importação final com conflitos zerados (passo 2 da ordem)**
  `python importar_decisoes.py` (ensaio): relatório sem conflitos abertos. Só então `python importar_decisoes.py --aplicar` (o script recusa se houver conflito). Rodar de novo `--aplicar`: não deve gravar nada (idempotência).
- [ ] **Passo 5: Referência de urgência**
  Executar o `UPDATE gestao.parametro … data_implantacao` das restrições globais; depois `select valor from gestao.parametro where chave='data_implantacao'` e anotar o instante.
- [ ] **Passo 6: Apontar o GitHub para o banco novo**
  No environment `DATABASE_URL`: trocar o secret `DATABASE_URL` pela URL do pooler novo (Session pooler, porta 5432, `sslmode=require`). Guardar a URL antiga fora do repositório, para reversão.
- [ ] **Passo 7: Carga completa de verificação**
  `gh workflow run pipeline.yml -f modo=completo -f ambiente=producao`, acompanhar até o fim.
  Esperado: job verde; `bronze.controle_execucao` com `incremental`, `eventos` e `reconciliacao`; `api.vw_ultima_carga` com data de hoje; `gold.vw_movimentacoes` só com o que veio depois da cópia.
  Como o webhook do n8n de produção ainda aponta o fluxo antigo (Tarefa 5), este passo pode gerar um e-mail legítimo de atualização; avisar a equipe antes.

---

### Tarefa 5: n8n — passos 3 e 4 da ordem da virada **[PRODUÇÃO]**

**Arquivos:** nenhum no repo. Mudanças no n8n, validadas com `validate_workflow` e conferidas com `get_workflow_details` (o objeto `connections`) depois de cada alteração.

**Consome:** `legislativo_n8n` (Tarefa 2); workflow de homologação `JFY5o63SlUExlH6t` como modelo.
**Produz:** fluxos em produção lendo `gestao` e sem tocar a planilha.

- [ ] **Passo 1: Credencial Postgres nova**
  Criar a credencial do banco novo, papel `legislativo_n8n`, com **Ignore SSL Issues** (o pooler do Supabase dá "self-signed certificate in certificate chain"). Para o fluxo que ainda precisa de leitura ampla, usar a credencial com o papel mínimo que o fluxo exige; nunca o admin.
- [ ] **Passo 2: Fluxo principal `4F6Y2cOHhqNuhdYm` (passo 3 da ordem)**
  Salvar o id da versão atual (reversão). Trocar a leitura de relevância da planilha pelos contratos de `gestao`; remover a escrita das novas pendências na aba Proposições; e-mail com link para o projeto no sistema e status "Adiada". Publicar.
  Esperado: execução de teste com o webhook de produção; e-mail só com itens após o checkpoint; nenhuma chamada ao node do Google Sheets na execução.
- [ ] **Passo 3: Inclusão manual `23CyodhPlORNJ4xS` e o novo fluxo (passo 4)**
  Desativar o gatilho da planilha (15 min). Publicar o "Legislativo — inclusão" de produção (cópia do de homologação): webhook vindo do app, cron de 15 min, `gestao.reivindicar_inclusao` → Câmara → `registrar_inclusao_resolvida`/`falhar_inclusao` → `modo=inclusao` (`ambiente=producao`) → `concluir_inclusoes`.
  Anotar a URL do webhook de produção e o token (para a Tarefa 7).
- [ ] **Passo 4: Religar o Agendador**
  Republicar `0sieqPDvsqoZcs31` (sem mudança de conteúdo: 07:17 `completo`, 10h/14h `pautas`).
- [ ] **Passo 5: Conferir CA13**
  `search_workflow_executions` das últimas execuções: nenhum node de Google Sheets executado nos fluxos 4F6… e 23Cy….

---

### Tarefa 6: Power BI — passo 5 da ordem **[PRODUÇÃO]**

**Arquivos:** `BI/BI_Monitoramento_Proposicoes.SemanticModel/` (modelo lê a projeção única em `api`; contagem por `uuid_projeto`; "Adiada"; "Painel atualizado em"). Respeitar o filtro `segredos-pbi`: URL e chave nunca entram no repositório.

**Consome:** URL e anon key do projeto novo (em `BI/.env`).
**Produz:** relatório publicado lendo o banco novo; link público inalterado.

- [ ] **Passo 1: Atualizar os parâmetros localmente**
  Em `BI/.env`: `SupabaseUrl` e `SupabaseAnonKey` do projeto novo. Fechar o Desktop antes de editar por arquivos (regra do projeto) e não rodar `gerar_paginas.py`.
- [ ] **Passo 2: Verificação no Desktop**
  Atualizar o modelo; conferir que a carteira, a contagem de projetos (por `uuid_projeto`) e `em_carteira` batem com a Carteira do sistema (CA03). Conferir "Painel atualizado em" em horário de Brasília.
- [ ] **Passo 3: Publicar sobre o mesmo relatório**
  Republicar no mesmo workspace/relatório, para manter o link de "Publicar na Web" do README. Se o Service pedir nova credencial: conexão de nuvem `con_supabase_monitoramento` (Web, Anonymous) apontando para a URL nova.
- [ ] **Passo 4: Atualização agendada**
  Forçar uma atualização e confirmar sucesso; conferir 08:30/10:30/14:30. Abrir o link público em janela anônima: dados novos e hora do painel de hoje.
- [ ] **Passo 5: Conferir CA12**
  Com a chave anon nova, listar as colunas da projeção do painel: só as aprovadas (relevância, posição, prioridade, `em_carteira`, ids). Nada de ação, parecer, observações ou histórico.

---

### Tarefa 7: Aplicação — passo 6 da ordem e liberação para a Ana **[PRODUÇÃO]**

**Arquivos:** nenhum no repo do app além do que já está na branch. Configuração na Vercel e no banco da plataforma.

**Consome:** `legislativo_app` (Tarefa 2); URL/token do webhook do n8n (Tarefa 5); migration de capacidades do legislativo.
**Produz:** `/legislativo` em produção, Ana como única editora.

- [ ] **Passo 1: Verificar antes de aplicar**
  No banco de produção **da plataforma** (não o legislativo): ver se a migration de capacidades do legislativo já foi aplicada (`supabase migration list` contra o projeto de produção). Se não: aplicar **[PRODUÇÃO]** e rodar o pgTAP correspondente. Conferir que o primeiro admin existe.
- [ ] **Passo 2: Variáveis da Vercel (ambiente Production)**
  `LEGISLATIVO_DATABASE_URL` = URL do pooler com `legislativo_app`; URL e token do webhook de produção do n8n (nomes iguais aos da Preview). Nunca copiar o token da homologação.
- [ ] **Passo 3: Deploy do `main` do app** e verificação do pooler
  Abrir `/legislativo` com um usuário admin sem capacidade: leitura sim, edição não (CA01). Conferir nos logs da Vercel ausência de erro de instrução preparada.
- [ ] **Passo 4: Conceder a capacidade de editor à Ana**
  Pela administração de usuários. Esta é a **linha de não retorno**: a partir daqui, reverter o n8n para a planilha usaria dados velhos.
- [ ] **Passo 5: Roteiro CA11 com a Ana em produção**
  Ela avalia pendências, muda uma posição, uma ação e uma prioridade, inclui um PL, confirma um movimento e exporta a carteira. O PL de teste deve ser uma proposição real de interesse (a inclusão persiste e dispara e-mail); combinar qual antes.
  Esperado: pedido vai a "Concluída" em poucos minutos; a proposição aparece em `api.vw_monitoramento`; o e-mail de confirmação chega.
- [ ] **Passo 6: Painel do site**
  Página com o Power BI inserido e a frase "Decisões salvas aparecem aqui na próxima atualização do painel."

---

### Tarefa 8: Reversão (referência; só até a Tarefa 7, passo 4)

- [ ] **Antes da linha de não retorno:** trocar o secret `DATABASE_URL` do GitHub de volta para a URL antiga; no n8n, restaurar as versões salvas (`restore_workflow_version`) dos dois fluxos e reativar o gatilho da planilha; no Power BI, voltar `SupabaseUrl`/chave e republicar; remover a proteção da planilha. O banco antigo não foi alterado (somente leitura na cópia), então nada é perdido.
- [ ] **Depois da linha de não retorno:** só rollback da aplicação (redeploy do commit anterior na Vercel). O banco novo permanece fonte única; nada reativa a planilha.

---

### Tarefa 9: Estabilização e encerramento

**Arquivos:** `README.md` (status), `CLAUDE.md` (remover menções à planilha como fonte; documentar o banco novo), `docs/superpowers/monitoramento-legislativo/plano.md` (marcar a Entrega 1 como em produção).

- [ ] **Passo 1: D+1 a D+3**
  Conferir diariamente: carga das 07h17 verde; pautas 10h/14h; `api.vw_ultima_carga`; e-mails sem duplicar; fila de inclusões sem pedido preso em "carregando" por mais de 60 min.
- [ ] **Passo 2: Cenários controlados (PRD §6 fase 5)**
  Conflito de versão (duas abas editando o mesmo projeto), pedido duplicado, falha de carga com retomada, cancelamento. Esperado: nenhuma sobrescrita silenciosa; falha visível, sem "atualização falsa" (CA10).
- [ ] **Passo 3: Teste de privilégios depois de uma carga real** (CA09/CA12): decisões e confirmações intactas após o `setup_db`/cache do dia seguinte.
- [ ] **Passo 4: Descomissionar (D+14, só com pedido do Erick)**
  Pausar e depois excluir o projeto Supabase antigo de produção e a homologação antiga; remover secrets antigos.
- [ ] **Passo 5: Documentação e commit**
  Atualizar os docs acima e a nota de memória do projeto; commit `docs: Entrega 1 do legislativo em produção`.

---

## Autoavaliação

- **Cobertura do PRD:** ordem da virada (Tarefas 4–7), baseline (T4/5), CA01/02/07/08/09/10/11/12/13 cobertos; CA03 na T6; CA04–06 e CA14 já cobertos por testes automatizados e não precisam de verificação extra em produção além da T9 passo 3. Entrega 2 está fora de escopo.
- **Não verificado ao escrever (conferir na Tarefa 1/2):** onde roda hoje o banco antigo de produção e o tamanho do bronze; se a migration de capacidades já foi aplicada no banco da plataforma em produção; os nomes exatos das variáveis de ambiente na Vercel; o estado atual dos fluxos de produção do n8n e se o plano do Supabase novo inclui backup/PITR. O plano trata cada um como passo de verificação, não como fato.
- **Decisão que o Erick precisa confirmar:** copiar `bronze` e `silver` (recomendado) em vez de recarregar o bronze (Tarefa 3, passo 1).

## Registro de revisão

- [ ] Revisão do Fable: pendente.
