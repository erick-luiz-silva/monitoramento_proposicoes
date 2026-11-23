# Entrega 2 do /legislativo (substitui o Power BI) — plano de implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Entregar no app as telas Agenda, Indicadores e Autores e partidos, mais o bloco de agenda na Visão geral, e tirar a aba Painéis. Com isso o Power BI pode ser desligado.

**Architecture:**
- **Monitoramento (`monitoramento_proposicoes`):** ganha só duas views de contrato (`contrato.vw_audiencia`, `contrato.vw_avaliacao`). As demais leituras usam views que já existem (`vw_pauta`, `vw_projeto`, `vw_versao`, `vw_snapshot_carteira`, `vw_inclusao`).
- **App (`banco-de-contatos-mailing`):**
  - Cada tela tem um módulo de filtros puro (`lib/filters/…`), uma DAL guardada (`lib/dados/legislativo/…`), uma página em Server Component e uma rota CSV em `app/api/legislativo/…`.
  - Os gráficos são componentes cliente em `recharts`, no padrão de `components/dashboard/grafico-evolucao.tsx`: os links são montados no servidor e o clique navega.
  - Toda contagem e a lista correspondente saem do mesmo predicado SQL.

**Tech Stack:** PostgreSQL 17 (Supabase), Python 3.14 `unittest` (testes SQL locais), Next 16 (Cache Components, `proxy.ts`), React 19, `postgres` 3.4, zod 4, recharts 3, Vitest, Playwright.

**Spec:**
- Mockup aprovado em 19/11/2026: `docs/superpowers/monitoramento-legislativo/mockup/legislativo-entrega2-mockup.html` (https://claude.ai/artifact/NwiB2yZ8ZTEZMowY1yDphC).
- Plano pós-veredito: `docs/superpowers/plans/2026-11-06-legislativo-pos-veredito.md`, Fase 6, itens 2 e 3 e adendo de 19/11.
- PRD: `docs/superpowers/monitoramento-legislativo/prd.md` (§1, RF02, RN08, §6).

## Global Constraints

- **Interface:** 100% pt-BR, limpa, só o necessário (memória "simplicidade"). As regras de contagem ficam num `<details>` "Como os números são contados", fechado.
- **Rótulos das abas, nesta ordem:** "Visão geral", "Avaliação", "Carteira", "Agenda", "Indicadores", "Autores e partidos", "Inclusão". "Painéis" sai.
- **Acesso:**
  - As rotas novas (`/legislativo/agenda`, `/legislativo/indicadores`, `/legislativo/autores` e `/api/legislativo/{agenda,indicadores,autores}`) exigem acesso completo: `obterLeitorLegislativo()` na DAL e na rota, e 404 pelo proxy, que já cobre qualquer subrota.
  - A Visão geral continua aberta a todo perfil ativo. Sem acesso completo, o bloco de agenda aparece sem link interno, sem "ver agenda" e sem chip de prioridade.
- **Projeto:** número → ficha (`caminhoProjeto`), e ↗ por versão → `link_direto` em nova aba, via `IdentificacaoProposicao`, como nas outras telas.
- **Datas:** o "hoje" é sempre o de Brasília, lido do banco: `(now() AT TIME ZONE 'America/Sao_Paulo')::date`. Formato de exibição `DD/MM/YYYY` (ou `DD/MM` em eixos).
- **Lançamento da plataforma:** `LANCAMENTO_LEGISLATIVO = "2026-11-06"`.
- **Pré-lançamento:**
  - Relevância vinda da planilha (`operacao = 'importacao_planilha'`, `origem = 'migracao'`) conta como avaliada, sem data, com o rótulo "Pré-lançamento".
  - Entra só no período "Desde o início" e na linha própria da tabela mês a mês.
  - Reavaliação na plataforma prevalece, com a data dela.
- **Sem coluna de autor da avaliação.** Só a Ana avalia.
- **Relevância:** `NAO` no banco é exibida como "NÃO".
- **CSV:** usar `celula()`/o mesmo escape de `lib/legislativo/csv.ts`, que neutraliza fórmula. Headers: `text/csv; charset=utf-8`, `attachment`, `Cache-Control: private, no-store`.
- **Next 16:** antes de escrever código Next, ler `node_modules/next/dist/docs/`. Tudo que lê sessão ou `searchParams` fica dentro de `<Suspense>`. Rodar `npm run typecheck` depois de criar rotas (rotas tipadas).
- **Fixtures e prints:** nenhum dado real.
- **Commits:** com `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Produção:** nada vai para produção sem "pode" explícito do Erick no momento. Merge do monitoramento + `setup_db.py` antes do merge do app.
- **Isolamento:** cada repositório trabalha numa branch em `.worktrees/<branch>`, partindo de `origin/main` (monitoramento `c74cda2`, app `2dd8aac`). Os checkouts principais têm mudanças do usuário e ficam intocados.

## Review Focus

1. **Item de pauta repetido:** a mesma linha da pauta é ligada ao item literal e ao relacionado (`schema_gold.sql:200`). Um projeto deve aparecer uma vez por reunião, e cartão e lista contam `(id_evento, chave_agrupamento)` distintos. Teste na Task 2.
2. **Avaliação desfeita, ou mudada depois no mesmo período:** a desfeita não conta, e de duas avaliações vale a última. Testes nas Tasks 1 e 4.
3. **Período sem foto diária:** fim de semana ou período inteiro antes de 06/11. O cartão de monitorados mostra "—" com "sem contagem diária no período", sem quebrar nem mostrar 0. Teste na Task 4.
4. **Datas inválidas na URL** (`de` > `ate`, data futura, texto): caem no padrão sem erro 500. Teste na Task 4.
5. **Autor/partido com acento ou espaço no link para a Carteira** (ex.: "REPUBLICANOS", "Dep. João Vasconcelos"): ida e volta pela URL sem perda, e a Carteira mostra o filtro ativo com como removê-lo. Teste na Task 6.

---

## Repositório `monitoramento_proposicoes` (branch `entrega2-contratos`)

### Task 1: Views `contrato.vw_audiencia` e `contrato.vw_avaliacao`

**Files:**
- Modify: `sql/schema_contratos.sql` (logo depois de `contrato.vw_pauta`, linha ~474; as views entram antes dos GRANTs do fim do arquivo, então o `GRANT SELECT ON ALL TABLES IN SCHEMA contrato TO legislativo_app` já as cobre)
- Modify: `CLAUDE.md` (seção Architecture: uma linha sobre as duas views, junto do parágrafo da foto diária)
- Test: `tests/test_sql_local.py` (classe nova `IndicadoresContratoTests(_ComDados)`)

**Interfaces:**
- Produces:
  - `contrato.vw_audiencia(id_evento, data_hora_inicio timestamp, sigla_orgao, nome_orgao, assunto, keywords_encontradas text, url_registro, casa, status text)`.
    - `status` ∈ `'Agendada' | 'Realizada' | 'Adiada' | 'Cancelada'`, com a mesma regra de `api.vw_audiencias_de_interesse.status_alerta`.
    - Origem: `api_cache.vw_audiencias_de_interesse`.
  - `contrato.vw_avaliacao(id bigint, uuid_projeto uuid, relevancia text, dia date, pre_lancamento boolean)`. Uma linha por evento que deixou a relevância em `'SIM'` ou `'NAO'`:
    - `gestao.historico_alteracao` com `diferencas ? 'relevancia'` e `diferencas->'relevancia'->>'para' IN ('SIM','NAO')`;
    - exclui `operacao = 'desfazer_avaliacao'`;
    - exclui todo `'avaliar'` desfeito, isto é, quando existe `desfazer_avaliacao` do mesmo `uuid_projeto` com `revisao = avaliar.revisao + 1`;
    - `uuid_projeto` resolvido por `coalesce(p.substituido_por, h.uuid_projeto)` (um nível);
    - `pre_lancamento = (origem = 'migracao')`;
    - `dia` = `(em AT TIME ZONE 'America/Sao_Paulo')::date` quando não é pré-lançamento, senão `NULL`.

- [ ] **Step 1: Escrever os testes que falham** em `IndicadoresContratoTests`, usando `self.chamar`, `self.decidir` e o ATOR de `FuncoesGestaoTests`:
  - `test_audiencia_status_igual_ao_da_api`: insira em `silver.evento` uma audiência futura, uma passada, uma `'Adiada'` e uma `'Cancelada'` com descrição que casa uma keyword da fixture; `self.atualizar_cache()`; `SELECT id_evento, status FROM contrato.vw_audiencia ORDER BY 1` igual a `SELECT id_evento, status_alerta … FROM api.vw_audiencias_de_interesse ORDER BY 1`, e os quatro status presentes.
  - `test_avaliacao_registra_sim_e_nao_com_dia_de_brasilia`:
    - `gestao.avaliar` com SIM em 900021, depois `salvar_decisao` mudando para NAO;
    - a view tem 2 linhas do projeto, `relevancia` `['SIM','NAO']`, `dia` = data de Brasília de `now()` e `pre_lancamento` false;
    - com `SET LOCAL TIME ZONE 'UTC'`, o resultado é o mesmo.
  - `test_avaliacao_desfeita_nao_conta`: `avaliar` SIM e depois `desfazer_avaliacao(historico_id)`. A view não tem linha desse projeto.
  - `test_relevancia_da_planilha_e_pre_lancamento_sem_dia`: insira em `gestao.historico_alteracao` (como faz `importar_decisoes.py`) `operacao 'importacao_planilha'`, `origem 'migracao'`, `diferencas {"relevancia":{"de":null,"para":"NAO"}}`. A linha sai com `pre_lancamento` true, `dia` NULL e `relevancia` 'NAO'.
  - `test_mudanca_sem_relevancia_e_relevancia_para_nulo_nao_entram`: `salvar_decisao` só com `posicao`, e um evento com `para` null. Nenhum dos dois entra.
  - `test_projeto_substituido_aparece_pelo_novo_uuid`: um projeto A com evento e `UPDATE gestao.projeto SET substituido_por = B` (como dono, no setUp do teste). A linha sai com `uuid_projeto = B`.
  - `test_app_le_e_anon_nao_le`: `has_table_privilege('legislativo_app', 'contrato.vw_avaliacao', 'SELECT')` e o mesmo para `vw_audiencia` são true; para `anon` e `authenticated`, false.

- [ ] **Step 2: Rodar e ver falhar**

  Run: `eval "$(scripts/postgres_teste.sh)" && .venv/bin/python -m unittest tests.test_sql_local.IndicadoresContratoTests -v`
  Expected: FAIL (`relation "contrato.vw_avaliacao" does not exist`).

- [ ] **Step 3: Criar as duas views em `sql/schema_contratos.sql`**, com comentário de cabeçalho no estilo das vizinhas. Na `vw_avaliacao`, o "desfeito" é um `NOT EXISTS`; não usar janela.

- [ ] **Step 4: Rodar e ver passar, mais a suíte inteira**

  Run: `.venv/bin/python -m unittest tests.test_sql_local -v && .venv/bin/python -m unittest discover -s tests`
  Expected: tudo OK, 0 pulados na classe nova.

- [ ] **Step 5: Commit**

```bash
git add sql/schema_contratos.sql tests/test_sql_local.py CLAUDE.md
git commit -m "Contratos da Entrega 2: vw_audiencia e vw_avaliacao (pré-lançamento sem data)"
```

---

## Repositório `banco-de-contatos-mailing` (branch `legislativo-entrega-2`)

**Pré-requisito dos testes de integração:** o banco descartável de `docs/legislativo-testes-locais.md`, montado com `MONITORAMENTO_SQL` apontando para o `sql/` do worktree da Task 1. A fixture `tests/fixtures/gestao/carteira_paginacao.sql` ganha, nesta branch, os dados sintéticos de que cada Task precisa:
- audiências;
- pautas passadas e futuras, incluindo uma linha repetida item/relacionado;
- eventos de histórico (`avaliar`, `desfazer_avaliacao`, `importacao_planilha`);
- fotos em `gestao.snapshot_carteira` em dois dias;
- uma inclusão concluída.

Os testes de integração ficam ao lado da DAL, no padrão de `lib/dados/legislativo/carteira.test.ts`, e pulam sem `LEGISLATIVO_TEST_DATABASE_URL`. O portão de cada Task é **0 pulados**.

### Task 2: Agenda — filtros e DAL

**Files:**
- Create: `lib/filters/agenda.ts`, `lib/filters/agenda.test.ts`
- Create: `lib/dados/legislativo/agenda.ts`, `lib/dados/legislativo/agenda.test.ts` (integração)
- Modify: `lib/dados/legislativo/tipos.ts` (tipos abaixo)
- Modify: `tests/fixtures/gestao/carteira_paginacao.sql` (audiências e pautas)

**Interfaces:**
- Produces (`lib/filters/agenda.ts`):
  - `filtrosAgendaSchema` com:
    - `quando: "proximos"|"historico"` (padrão `"proximos"`);
    - `tipo: "tudo"|"pauta"|"audiencia"` (padrão `"tudo"`);
    - `orgao: string` (máx. 30);
    - `prioridade: ""|"sim"`;
    - `q: string` (máx. 200);
    - `recorte: ""|"prioridades"|"audiencias"|"votado"|"sem_votacao"|"adiado_cancelado"`.
  - `lerFiltrosAgenda(params: ParamsLegislativo): FiltrosAgenda` (inválido → padrão do campo, como `lerFiltrosLegislativo`), `paramsAgenda(f): URLSearchParams` e `hrefAgenda(parcial?: Partial<FiltrosAgenda>): string`.
- Produces (`tipos.ts`):
  - `type StatusPauta = "Agendado"|"Votado"|"Adiada"|"Cancelada"|"Encerrado sem votação"`;
  - `type StatusAudiencia = "Agendada"|"Realizada"|"Adiada"|"Cancelada"`;
  - `ItemAgenda` (união discriminada por `tipo`):
    - campos comuns: `id_evento: string; data: string /*YYYY-MM-DD*/; hora: string /*HH24:MI*/; sigla_orgao: string`;
    - pauta: `{tipo:"pauta"; status: StatusPauta; chave_agrupamento; uuid_projeto: string|null; versoes: IdentificacaoVersao[]; ementa; posicao: string|null; prioridade: boolean|null; nome_relator: string|null; partido_relator; uf_relator; resultado: string|null}`;
    - audiência: `{tipo:"audiencia"; status: StatusAudiencia; assunto: string; keywords: string[]; url_registro: string|null}`.
  - `ResumoAgenda = {quando:"proximos"; itens:number; reunioes:number; prioridades:number; audiencias:number} | {quando:"historico"; votados:number; sem_votacao:number; adiados_cancelados:number; audiencias_realizadas:number}` e `SemanaAgenda = {inicio: string; votados: number; nao_votados: number}`.
- Produces (`lib/dados/legislativo/agenda.ts`):
  - `listarAgenda(f: FiltrosAgenda, exportar?: boolean): Promise<{ itens: ItemAgenda[]; resumo: ResumoAgenda; semanas: SemanaAgenda[] | null; orgaos: string[] }>`. Guardada por `obterLeitorLegislativo()`.
  - `proximosAgenda(limite: number, completo: boolean): Promise<ItemAgenda[]>`. Guardada só por `obterUsuarioAtual()`. Com `completo = false`, devolve `prioridade: null` e `posicao: null`.

**Regras (dentro da SQL da DAL):**
- **Janelas:**
  - próximos = `data_hora_inicio > agora_brasilia AND data_hora_inicio::date <= hoje + 14`;
  - histórico = `data_hora_inicio::date BETWEEN hoje - 90 AND hoje AND data_hora_inicio <= agora_brasilia`.
- **Pautas:** de `contrato.vw_pauta`, deduplicadas por `(id_evento, chave_agrupamento)`, com `JOIN contrato.vw_projeto` para ementa, posição e prioridade. `resultado = situacao_item`.
- **Audiências:** de `contrato.vw_audiencia`, com `keywords = string_to_array(keywords_encontradas, ', ')`.
- **Contagens do resumo:**
  - `itens` = pautas `Agendado` da janela;
  - `reunioes` = `id_evento` distintos dessas pautas;
  - `prioridades` = as que têm `prioridade IS TRUE`;
  - `audiencias` = audiências `Agendada`;
  - no histórico: `votados` = `Votado`, `sem_votacao` = `Encerrado sem votação`, `adiados_cancelados` = `Adiada` ou `Cancelada`, `audiencias_realizadas` = `Realizada`.
- **Recortes:** cada `recorte` filtra a lista pelo mesmo predicado do número correspondente. O resumo ignora `recorte` e `q`, mas respeita `tipo`, `orgao` e `prioridade`.
- **Semanas:** só no histórico, as 13 semanas que terminam hoje. Semana = 7 dias encerrados no dia `hoje - 7k`, igual ao mockup. Votado vs. não votado sobre as pautas.
- **Ordem:** próximos por data crescente; histórico por data decrescente.

- [ ] **Step 1: Testes puros que falham** em `lib/filters/agenda.test.ts`:
  - `"ignora valores inválidos preservando os válidos"`: `lerFiltrosAgenda({quando:"ontem", tipo:"pauta", orgao:"CAPADR", recorte:"x"})` → `{quando:"proximos", tipo:"pauta", orgao:"CAPADR", recorte:""}`.
  - `"serializa e relê sem perda"`: ida e volta de `{quando:"historico", tipo:"audiencia", prioridade:"sim", q:"peste suína"}`.
  - `"hrefAgenda omite padrões"`: `hrefAgenda()` → `"/legislativo/agenda"` e `hrefAgenda({quando:"historico"})` → `"/legislativo/agenda?quando=historico"`.
- [ ] **Step 2: Testes de integração que falham** em `agenda.test.ts`:
  - `"número = lista em cada recorte"`: para cada recorte, `resumo[campo] === itens.length` (próximos e histórico).
  - `"linha repetida item/relacionado aparece uma vez"`: o projeto da fixture com duas linhas na mesma reunião gera 1 item.
  - `"audiência adiada fica fora de audiencias agendadas e aparece na lista"`.
  - `"semanas somam o total de pautas do histórico"`: `sum(votados + nao_votados)` = pautas do histórico em 91 dias.
  - `"proximosAgenda sem acesso completo não expõe prioridade nem posição"`.
- [ ] **Step 3: Rodar e ver falhar.** Run: `npx vitest run lib/filters/agenda.test.ts lib/dados/legislativo/agenda.test.ts`. Expected: FAIL (módulos inexistentes).
- [ ] **Step 4: Implementar** `lib/filters/agenda.ts` (padrão de `lib/filters/legislativo.ts`) e `lib/dados/legislativo/agenda.ts`. Montar `versoes` com `adicionarIdentificacoesVersoes`/`SemGuarda`, como faz a Visão geral.
- [ ] **Step 5: Rodar e ver passar.** Mesmo comando com `LEGISLATIVO_TEST_DATABASE_URL`. Expected: PASS, 0 pulados.
- [ ] **Step 6: Commit** `git commit -m "Agenda: filtros e DAL (pautas + audiências, número = lista)"`

### Task 3: Agenda — página, gráfico, CSV e bloco da Visão geral

**Files:**
- Create: `app/(app)/legislativo/agenda/page.tsx`
- Create: `app/(app)/legislativo/agenda/lista.tsx` (Server Component: dias agrupados)
- Create: `app/(app)/legislativo/_components/grafico-colunas.tsx` (cliente, recharts, reutilizado nas Tasks 5 e 7)
- Create: `app/api/legislativo/agenda/route.ts`, `lib/legislativo/csv-agenda.ts`, `lib/legislativo/csv-agenda.test.ts`
- Modify: `lib/dados/legislativo/visao-geral.ts` (campo `agenda: ItemAgenda[]`, com `proximosAgenda(6, completo)`) e `app/(app)/legislativo/page.tsx` (bloco "Agenda até DD/MM")

**Interfaces:**
- Consumes: `listarAgenda`, `proximosAgenda`, `hrefAgenda` (Task 2).
- Produces:
  - `GraficoColunas({ pontos: {rotulo: string; a: number; b?: number; dica: string; href?: string}[]; rotuloA: string; rotuloB?: string; aria: string })`. A série `a` usa `var(--primary)` e a `b`, empilhada acima, `var(--chart-1)`. Legenda quando há `b`. O clique navega para `href`.
  - `gerarCsvAgenda(itens: ItemAgenda[]): string`, com as colunas `Data;Hora;Órgão;Tipo;Projeto ou assunto;Relator;Situação;Resultado`.

**Tela (igual ao mockup):**
- Título "Agenda" e subtítulo de cobertura "Reuniões com projetos monitorados na pauta e audiências públicas de interesse. Cobertura: CAPADR, CCJC, CMADS e Plenário da Câmara."
- Alternância "Próximos 14 dias" / "Histórico (90 dias)". Os cartões do resumo são links `hrefAgenda({...f, recorte})`, e o cartão ativo fica marcado.
- Filtros num `<form method="get">`: tipo, órgão (`orgaos` da DAL), "Só prioridades da ABCS", busca.
- "Exportar CSV" → `/api/legislativo/agenda?{params}`.
- Lista agrupada por dia, com o cabeçalho "qua, 19/11/2026".
  - Pauta: hora e órgão; identificação com ↗; chips de prioridade e posição; ementa; "Relator: Nome (PARTIDO-UF)" ou "sem relator designado"; resultado; chips "Pauta" e situação.
  - Audiência: assunto com ↗ para `url_registro`; chips das palavras-chave; chips "Audiência" e situação.
- Gráfico "Itens de pauta por semana e resultado", só no histórico e acima da lista.
- Vazio: "Nada neste recorte. Limpe os filtros para ver tudo."
- Visão geral: painel "Agenda até DD/MM" com até 6 itens (dia, hora, projeto ou "Audiência pública", órgão) e o link "ver agenda" só com acesso completo. Vazio: "Nada agendado nos próximos 14 dias."

- [ ] **Step 1: Teste que falha** em `csv-agenda.test.ts`, `"gera cabeçalho e neutraliza fórmula"`: um item de audiência com assunto `"=HYPERLINK(...)"` sai como `"'=HYPERLINK(...)"`, e o cabeçalho é exatamente o da Interface.
- [ ] **Step 2: Teste que falha** em `lib/legislativo/csv-route.test.ts` (já existe; seguir o padrão), `"rota da agenda nega sem acesso completo e responde CSV com no-store"`.
- [ ] **Step 3: Rodar e ver falhar.** `npx vitest run lib/legislativo/csv-agenda.test.ts lib/legislativo/csv-route.test.ts` → FAIL.
- [ ] **Step 4: Implementar** página, lista, gráfico, rota CSV e o bloco da Visão geral.
- [ ] **Step 5: Rodar.** `npm run typecheck && npm run lint && npx vitest run` → PASS. Abrir `npm run dev` contra o banco descartável e conferir a tela com o mockup, em claro e escuro, a 1280 px e a 400 px.
- [ ] **Step 6: Commit** `git commit -m "Agenda: tela, gráfico semanal, CSV e bloco na Visão geral"`

### Task 4: Indicadores — período e DAL

**Files:**
- Create: `lib/filters/indicadores.ts`, `lib/filters/indicadores.test.ts`
- Create: `lib/dados/legislativo/indicadores.ts`, `lib/dados/legislativo/indicadores.test.ts` (integração)
- Modify: `tests/fixtures/gestao/carteira_paginacao.sql` (eventos de avaliação, fotos em 2 dias, inclusão concluída)

**Interfaces:**
- Produces (`lib/filters/indicadores.ts`):
  - `LANCAMENTO_LEGISLATIVO = "2026-11-06"`.
  - `filtrosIndicadoresSchema` com:
    - `periodo: "mes"|"anterior"|"90"|"ano"|"tudo"|"datas"` (padrão `"mes"`);
    - `de`, `ate`: `YYYY-MM-DD` ou `""`;
    - `k: "mon"|"ava"|"inc"` (padrão `"mon"`);
    - `r: ""|"carteira"|"entraram"|"sairam"|"todos"|"SIM"|"NAO"|"pre"`.
  - `lerFiltrosIndicadores(params)`, `hrefIndicadores(parcial?)`.
  - `resolverPeriodo(f: FiltrosIndicadores, hoje: string): { de: string; ate: string; comPre: boolean }`:
    - `mes` → dia 1 do mês de `hoje` até `hoje`;
    - `anterior` → o mês anterior inteiro;
    - `90` → `hoje-89` até `hoje`;
    - `ano` → 01/01 até `hoje`;
    - `tudo` → `LANCAMENTO_LEGISLATIVO` até `hoje`, com `comPre` true;
    - `datas` → `de`/`ate` válidos, com `ate` limitado a `hoje`; data ausente, inválida ou `de > ate` → cai em `mes`.
  - `comPre` é true só em `tudo`.
- Produces (`lib/dados/legislativo/indicadores.ts`):
  - `obterIndicadores(f: FiltrosIndicadores, exportar?: boolean): Promise<Indicadores>`, guardada por `obterLeitorLegislativo()`, com:
```ts
type Indicadores = {
  hoje: string; periodo: { de: string; ate: string; comPre: boolean };
  monitorados: { dia: string; total: number; entraram: number; sairam: number } | null; // null = sem foto no período
  avaliados: { total: number; sim: number; nao: number; pre: number };
  incluidos: number;
  serieDiaria: { dia: string; monitorados: number }[];          // dias com foto no período
  avaliadosPorMes: { mes: string /*YYYY-MM*/; sim: number; nao: number }[]; // do mês do lançamento ao de hoje; só plataforma
  preLancamento: { total: number; sim: number; nao: number; reavaliados: number };
  meses: { mes: string; monitorados: number | null; entraram: number | null; sairam: number | null;
           avaliados: number; sim: number; nao: number; incluidos: number }[]; // mais recente primeiro
  lista: LinhaIndicador[];  // do cartão k e do recorte r
};
type LinhaIndicador = { chave_agrupamento: string | null; versoes: IdentificacaoVersao[]; ementa: string | null;
  casa: string | null; dia: string | null; relevancia: "SIM" | "NAO" | null; motivo: string | null; pre_lancamento: boolean };
```

**Regras (SQL da DAL):**
- **Avaliados do período:**
  - `DISTINCT ON (uuid_projeto)` sobre `contrato.vw_avaliacao` onde `(NOT pre_lancamento AND dia BETWEEN de AND ate) OR (comPre AND pre_lancamento)`;
  - `ORDER BY uuid_projeto, pre_lancamento, dia DESC, id DESC` (a plataforma vence o pré-lançamento; vale a mais recente);
  - `pre` = quantas linhas finais têm `pre_lancamento`.
- **`preLancamento`:**
  - os projetos cuja avaliação efetiva desde o início é de pré-lançamento;
  - `reavaliados` = projetos com evento de pré-lançamento e também algum evento da plataforma até `hoje`.
- **Identificação:** `LEFT JOIN contrato.vw_projeto` por `uuid_projeto`. Projeto fora do monitoramento entra na conta, com `versoes` vazias e ementa "Projeto fora do monitoramento".
- **Monitorados:**
  - `f0`/`f1` = menor/maior `dia` de `contrato.vw_snapshot_carteira` entre `de` e `ate`, e `total` = `em_carteira` em `f1`;
  - `entraram` = chaves `em_carteira` em `f1` que não estavam `em_carteira` em `f0` (ausente conta como fora). `sairam` é o inverso;
  - motivo da saída = `motivo_historico` em `f1`, ou "saiu do monitoramento" se a chave sumiu. Motivo da entrada = "inclusão manual" se há inclusão concluída no período para uma versão do projeto, senão "monitoramento automático";
  - sem foto no período, `monitorados = null`;
  - chave = `chave_agrupamento`.
- **Incluídos:** `contrato.vw_inclusao` com `estado = 'concluida'` e `(atualizado_em AT TIME ZONE 'America/Sao_Paulo')::date BETWEEN de AND ate`. Concluída não muda mais de estado (`inclusao_ja_concluida`).
- **`meses`:** a mesma conta aplicada a cada mês, do mês do lançamento ao de hoje, com o mês corrente até `hoje`. `monitorados` é `null` quando o mês não tem foto.
- **Uma só fonte:** o cartão e o recorte da lista saem da mesma CTE, e `exportar` só remove o limite (lista sem paginação no CSV; na tela, até 500 linhas com o aviso "mostrando 500 de N; exporte o CSV para ver todas").

- [ ] **Step 1: Testes puros que falham** em `lib/filters/indicadores.test.ts`, com `hoje = "2026-11-19"`:
  - `mes` → `{de:"2026-11-01", ate:"2026-11-19", comPre:false}`;
  - `anterior` → `{de:"2026-10-01", ate:"2026-10-31", comPre:false}`;
  - `90` → `de "2026-08-22"`;
  - `ano` → `de "2026-01-01"`;
  - `tudo` → `{de:"2026-11-06", ate:"2026-11-19", comPre:true}`;
  - `datas` com `de "2026-11-10"`, `ate "2026-12-31"` → `ate "2026-11-19"`;
  - `datas` com `de > ate`, com `"abc"` ou vazio → igual a `mes`;
  - `anterior` com `hoje = "2026-01-15"` → `{de:"2025-12-01", ate:"2025-12-31"}`.
- [ ] **Step 2: Testes de integração que falham** em `indicadores.test.ts`:
  - `"número = lista"`: para cada `k`/`r`, o número do cartão e do recorte é igual a `lista.length`.
  - `"pré-lançamento só em Desde o início"`: o projeto com `importacao_planilha` entra com `periodo:"tudo"` (`pre_lancamento` true, `dia` null) e fica fora de `periodo:"mes"`.
  - `"reavaliação na plataforma prevalece"`: o projeto da planilha com `avaliar` posterior aparece uma vez, com a data e a relevância da plataforma, e conta em `preLancamento.reavaliados`.
  - `"avaliação desfeita não conta"`.
  - `"sem foto no período, monitorados é null"`: com `periodo:"datas"` em outubro de 2026.
  - `"entraram e saíram comparam a primeira e a última foto"`: fixture com fotos em dois dias, uma chave entrando e outra saindo com `motivo_historico 'marcado NÃO'`.
  - `"inclusão concluída no período conta; pendente não"`.
- [ ] **Step 3: Rodar e ver falhar.** `npx vitest run lib/filters/indicadores.test.ts lib/dados/legislativo/indicadores.test.ts` → FAIL.
- [ ] **Step 4: Implementar.** O `hoje` vem do banco numa consulta só, e a DAL chama `resolverPeriodo` com ele.
- [ ] **Step 5: Rodar e ver passar** (com `LEGISLATIVO_TEST_DATABASE_URL`, 0 pulados).
- [ ] **Step 6: Commit** `git commit -m "Indicadores: período, DAL e regra de pré-lançamento"`

### Task 5: Indicadores — página, gráficos e CSV

**Files:**
- Create: `app/(app)/legislativo/indicadores/page.tsx`
- Create: `app/(app)/legislativo/_components/grafico-linha.tsx` (cliente, recharts)
- Create: `app/api/legislativo/indicadores/route.ts`, `lib/legislativo/csv-indicadores.ts`, `lib/legislativo/csv-indicadores.test.ts`

**Interfaces:**
- Consumes: `obterIndicadores`, `hrefIndicadores`, `GraficoColunas` (Task 3).
- Produces:
  - `GraficoLinha({ pontos: {dia: string; valor: number}[]; aria: string; rotuloValor: string })`: área suave em `var(--primary)`, último ponto destacado com o valor e dica "DD/MM/YYYY · N monitorados".
  - `gerarCsvIndicadores(k, linhas: LinhaIndicador[]): string`, com colunas por `k`:
    - `mon` → `Projeto;Casa;Data;Motivo`;
    - `ava` → `Projeto;Avaliação;Em` (`Em` = `DD/MM/YYYY` ou `pré-lançamento`; `NAO` → `NÃO`);
    - `inc` → `Projeto;Concluído em;Pedido por`.

**Tela (igual ao mockup):**
- Seletor de período: "Este mês", "Mês passado", "Últimos 90 dias", "Este ano", "Desde o início" e "Escolher datas" (dois `<input type="date">` num `<form method="get">`). A faixa de texto do período fica abaixo.
- Três cartões-link:
  - "Monitorados hoje" / "Monitorados em DD/MM", com "+N entraram −M saíram". Sem foto: "—" e "sem contagem diária no período";
  - "Avaliados no período", com "N SIM · M NÃO" e "· P pré-lançamento" quando `P > 0`;
  - "Incluídos no período".
- Dois gráficos:
  - "Monitorados por dia" (`serieDiaria`);
  - "Avaliados por mês" (`GraficoColunas` SIM/NÃO). Cada coluna é link para `periodo=datas` daquele mês com `k=ava`.
  - Abaixo, a linha "Pré-lançamento (planilha, sem data): N avaliados (x SIM · y NÃO). Outros R foram reavaliados na plataforma e contam pela data nova." O número é link para `periodo=tudo&k=ava&r=pre`.
- Lista com recortes em pílulas e "Exportar CSV". Sem coluna "Por" nas avaliações.
- `<details>` "Ver a tabela mês a mês", com a linha final "Pré-lançamento (planilha, sem data)". Todo número é link.
- `<details>` "Como os números são contados", com o texto do mockup e a data de lançamento real (06/11/2026).

- [ ] **Step 1: Teste que falha** em `csv-indicadores.test.ts`, `"avaliações: NAO vira NÃO e pré-lançamento sem data"`: linha `{relevancia:"NAO", pre_lancamento:true, dia:null}` → `"…";"NÃO";"pré-lançamento"`.
- [ ] **Step 2: Teste que falha** em `csv-route.test.ts`, `"rota de indicadores nega sem acesso completo e responde CSV com no-store"`.
- [ ] **Step 3: Rodar e ver falhar**, implementar e rodar `npm run typecheck && npm run lint && npx vitest run` → PASS. Conferir no navegador com o mockup (claro, escuro, 400 px), inclusive período sem foto e "Desde o início".
- [ ] **Step 4: Commit** `git commit -m "Indicadores: tela, gráficos, tabela mês a mês e CSV"`

### Task 6: Carteira — filtros por autor, partido, UF, ano e tipo

**Files:**
- Modify: `lib/filters/legislativo.ts` (schema)
- Modify: `lib/dados/legislativo/carteira.ts:28-33` (o `EXISTS` sobre `vw_versao`)
- Modify: `app/(app)/legislativo/carteira/page.tsx` (linha "Filtrado por: …" com remoção por filtro)
- Test: `lib/legislativo/regras.test.ts` (filtros) e `lib/dados/legislativo/carteira.test.ts` (integração)

**Interfaces:**
- Produces: `FiltrosLegislativo` ganha `autor: string` (máx. 200), `partido: string` (máx. 30), `uf: string` (`/^[A-Z]{2}$/` ou `""`), `ano: number | ""` (inteiro 1900–2100) e `tipo: string` (máx. 10). `hrefCarteira` aceita essas chaves. O predicado entra no `EXISTS`:
  - `v.autor_principal = autor`;
  - `v.partido_autor_principal = partido`;
  - `v.uf_autor_principal = uf`;
  - `extract(year FROM v.data_apresentacao) = ano`;
  - `v.sigla_tipo = tipo`.

- [ ] **Step 1: Testes que falham:**
  - em `regras.test.ts`, `"filtros de autoria: ida e volta com acento e espaço"`: `hrefCarteira({autor:"Dep. João Vasconcelos", partido:"REPUBLICANOS", uf:"PR", ano:2025, tipo:"PLP"})` relido por `lerFiltrosLegislativo` devolve os mesmos valores; `uf:"pr1"` → `""`; `ano:"x"` → `""`.
  - em `carteira.test.ts` (integração), `"filtro por partido vale para alguma versão do projeto"`: na fixture, um projeto com versões de partidos diferentes aparece filtrando por qualquer um dos dois.
- [ ] **Step 2: Rodar e ver falhar**, implementar e rodar `npx vitest run lib/legislativo/regras.test.ts lib/dados/legislativo/carteira.test.ts` → PASS, 0 pulados.
- [ ] **Step 3: Commit** `git commit -m "Carteira: filtros por autor, partido, UF, ano e tipo"`

### Task 7: Autores e partidos — DAL, tela e CSV

**Files:**
- Create: `lib/dados/legislativo/autores.ts`, `lib/dados/legislativo/autores.test.ts` (integração)
- Create: `app/(app)/legislativo/autores/page.tsx`, `app/(app)/legislativo/_components/barras-horizontais.tsx` (Server Component em HTML/CSS, sem recharts)
- Create: `app/api/legislativo/autores/route.ts`, `lib/legislativo/csv-autores.ts`, `lib/legislativo/csv-autores.test.ts`

**Interfaces:**
- Consumes: `hrefCarteira` com os filtros da Task 6, `GraficoColunas` (Task 3).
- Produces:
  - `obterAutores(soPrioridades: boolean): Promise<{ versoes: number; projetos: number; autores: number; partidos: number; ufs: number; doSenado: number; porPartido: Contagem[]; porUf: Contagem[]; porAno: Contagem[]; porTipo: Contagem[]; topAutores: { autor: string; partido: string|null; uf: string|null; versoes: number; prioritarias: number }[] }>`, com `type Contagem = { rotulo: string; n: number }`.
  - `BarrasHorizontais({ itens: Contagem[]; topo?: number; hrefDe: (rotulo: string) => string | null })`: as `topo` maiores e uma barra "Outros" sem link.

**Regras:**
- **Universo:** versões de `contrato.vw_versao` cujo projeto (`vw_projeto`, pela `chave_agrupamento`) está `em_carteira`, mais `prioridade IS TRUE` quando `soPrioridades`.
- **Unidades:** conta versões (RN08), e `projetos` = chaves distintas, para o subtítulo "N versões de M projetos".
- **Totais:** `doSenado` = versões com `casa = 'SF'`. `NULL` em partido, UF ou ano vira "Não informado", sem link.
- **Ordem e cortes:** partido e UF com `topo = 8`; tipo sem corte; ano em colunas de 2019 ao ano corrente, com zeros. `topAutores`: 10 maiores por versões, empate por nome.
- **Links para a Carteira:** `hrefCarteira({partido})`, `({uf})`, `({ano})`, `({tipo})`, `({autor})`, com `prioridade:"sim"` quando `soPrioridades`.
- **Tela:**
  - Alternância "Toda a carteira" / "Só prioridades" (`?recorte=prio`); totais em linha; grade 2×2 (partido, UF, ano, tipo); tabela "Autores com mais projetos" (Autor, Partido-UF, Versões, Prioritárias) e "Exportar CSV".
  - `<details>` com as regras do mockup: conta versões; partido e UF são os atuais do parlamentar; cada barra abre a Carteira filtrada.

- [ ] **Step 1: Testes que falham:**
  - integração `"totais batem com as barras"`: `sum(porPartido.n) = sum(porUf.n) = sum(porTipo.n) = versoes`;
  - integração `"só prioridades restringe o universo"`;
  - integração `"projeto com duas versões conta duas versões e um projeto"`;
  - puro `csv-autores.test.ts`, `"cabeçalho e escape"` (`Autor;Partido;UF;Versões;Prioritárias`);
  - `csv-route.test.ts`, `"rota de autores nega sem acesso completo"`.
- [ ] **Step 2: Rodar e ver falhar**, implementar e rodar `npm run typecheck && npm run lint && npx vitest run` → PASS. Conferir com o mockup.
- [ ] **Step 3: Commit** `git commit -m "Autores e partidos: DAL, barras, tabela e CSV"`

### Task 8: Abas novas, Painéis fora e CA11

**Files:**
- Modify: `app/(app)/legislativo/layout.tsx` (`ABAS` na ordem das Global Constraints)
- Delete: `app/(app)/legislativo/paineis/page.tsx`
- Modify: `.env.example` (remover `LEGISLATIVO_POWERBI_URL`), `README.md`/`docs/deploy.md` onde citarem a variável
- Modify: `lib/legislativo/layout.test.ts`
- Modify: `tests/legislativo/ca11.spec.ts`
- Modify: `next.config.ts` (redirect permanente `/legislativo/paineis` → `/legislativo/indicadores`)

- [ ] **Step 1: Atualizar os testes para falhar:**
  - em `layout.test.ts`, a lista de abas esperada passa a ser `["/legislativo","Visão geral"], ["/legislativo/avaliacao","Avaliação"], ["/legislativo/carteira","Carteira"], ["/legislativo/agenda","Agenda"], ["/legislativo/indicadores","Indicadores"], ["/legislativo/autores","Autores e partidos"], ["/legislativo/inclusao","Inclusão"]`;
  - o `it.each` de aba ativa troca `paineis` pelas três rotas novas;
  - o teste "só Visão geral sem acesso completo" passa a negar também `Agenda|Indicadores|Autores`.
- [ ] **Step 2: Rodar e ver falhar.** `npx vitest run lib/legislativo/layout.test.ts` → FAIL.
- [ ] **Step 3: Implementar** layout, remoção da página, redirect e limpeza da variável. `grep -rn "paineis\|POWERBI" app lib components tests docs .env.example` não deve achar nada além do redirect.
- [ ] **Step 4: CA11:**
  - em `rotasRestritas`, trocar `"/legislativo/paineis"` por `"/legislativo/agenda"`, `"/legislativo/indicadores"` e `"/legislativo/autores"`;
  - acrescentar as três rotas CSV ao bloco que já nega CSV/RSC/prefetch;
  - acrescentar `"editor vê as sete abas na ordem"`.
- [ ] **Step 5: Rodar** `npm run typecheck && npm run lint && npx vitest run && npm run build`. Com o banco e o Auth locais de `docs/legislativo-testes-locais.md`, rodar `npx playwright test --config=playwright.legislativo.config.ts`. Expected: tudo PASS.
- [ ] **Step 6: Commit** `git commit -m "Legislativo: abas Agenda, Indicadores e Autores; Painéis sai"`

---

### Task 9: Documentação, homologação e virada (lead; passos de produção só com "pode")

**Files:**
- Modify (monitoramento): `docs/superpowers/monitoramento-legislativo/prd.md` (§1 e §6: Entrega 2 entregue; RF02: bloco de agenda; RF07: Autores e partidos volta como tela nativa, revendo o D4 de 06/11; RN08: pré-lançamento) e `docs/superpowers/plans/2026-11-06-legislativo-pos-veredito.md` (registro de execução)
- Modify (app): `docs/decisoes.md` (adendo ao ADR-029: Entrega 2 e fim da aba Painéis) e `CLAUDE.md` (uma linha em Arquitetura sobre as rotas novas)

- [ ] **Step 1:** Abrir os PRs:
  - monitoramento: `entrega2-contratos` + documentação;
  - app: `legislativo-entrega-2`.
  
  Revisão final pelo alethe (Fable + Codex) nos dois e aplicação dos ajustes.
- [ ] **Step 2: Homologação** (`oqtorngrfejygrxjfgkv`): `setup_db.py` + `load_api.py` pela branch, prévia do app apontando para ela e conferência das três telas com o Erick. Conferir que `contrato.vw_avaliacao` tem pré-lançamento igual ao número de projetos com relevância importada.
- [ ] **Step 3 [PRODUÇÃO, com "pode"]:** merge do PR do monitoramento, depois `setup_db.py` + `load_api.py` no banco novo (`pwyupgfyholqquuhmlgm`). Conferir as contagens da Task 1 contra a API.
- [ ] **Step 4 [PRODUÇÃO, com "pode"]:**
  - merge do PR do app, que dispara o deploy;
  - sincronizar o espelho pessoal (memória "deploy via espelho");
  - remover `LEGISLATIVO_POWERBI_URL` da Vercel.
- [ ] **Step 5: Aceite da Ana (CA11 da Entrega 2).** Mensagem sem jargão (memória "comunicação com o negócio"). Antes, um e-mail de teste só para abcsdata@.
- [ ] **Step 6 [PRODUÇÃO, só depois do aceite e com "pode"]:**
  - desligar o "Publicar na Web" do relatório;
  - desligar a agenda de atualização do modelo no workspace DIN;
  - tirar o link do README;
  - avaliar com o Erick a revogação do `anon` sobre `api` (PRD fase 6).
  
  Registrar no plano e na memória.
