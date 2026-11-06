# Runbook da virada — cópia de bronze/silver e importação das decisões

Ensaio de 30/10/2026 (Tarefa 3 do [plano de produção](../plans/2026-10-30-legislativo-producao.md)). Só comandos e números; nenhum segredo, nenhum dado de proposição.

**Onde foi ensaiado (decisão do Erick, 30/10/2026):** a cópia foi ensaiada no próprio banco novo de produção (ref `pwyupgfyholqquuhmlgm`), que ainda não tem consumidor e é apagado e recopiado na janela (Tarefa 4, passo 2). A importação foi ensaiada num Postgres 17 local limpo, com o mesmo dump. A homologação (piloto da Ana) não foi tocada.

## Variáveis (do `src/.env`, nunca impressas)

- `DATABASE_URL`: produção atual (us-west-2). Vem com a porta 6543 (pooler em modo transação). Para `pg_dump` e contagens use a **5432** (Session pooler): `SRC=$(.venv/bin/python -c "import os;print(os.environ['DATABASE_URL'].replace(':6543/',':5432/'))")`.
- `DATABASE_URL_SP`: admin do banco novo (Session pooler 5432). Guarda antes de toda escrita:
  `.venv/bin/python -c "import os,sys;from urllib.parse import urlsplit;sys.exit(0 if urlsplit(os.environ['DATABASE_URL_SP']).username=='postgres.pwyupgfyholqquuhmlgm' else 1)" || exit 1`
- Carregar com `set -a; . src/.env; set +a`. Cliente: `docker run --rm postgres:17 psql ...` (sem psql local). `S` = pasta temporária fora do repositório (o dump tem dados reais).

## Sequência (Tarefa 4, passos 2 e 3)

| # | Ação | Comando | Ensaio |
|---|---|---|---|
| 1 | Paridade de colunas `bronze`/`silver` (tabelas base) origem × destino | `information_schema.columns` nos dois, `comm -23` (só na origem quebra o `COPY`) | 164 × 164, nenhuma diferença |
| 2 | Contagens de referência da origem | `psql "$SRC" -f $S/contagens.sql` (abaixo) | ver tabela de contagens |
| 3 | Dump | `docker run --rm -v $S/dump:/dump postgres:17 pg_dump "$SRC" --data-only --schema=bronze --schema=silver --no-owner --no-privileges -f /dump/bronze_silver.sql` | 3 min 04 s; 445 MB; 23 `COPY`; 10 `setval` |
| 4 | Lista do `TRUNCATE` gerada no destino | `select 'TRUNCATE ' \|\| string_agg(format('%I.%I', table_schema, table_name), ', ') \|\| ' CASCADE;' from information_schema.tables where table_schema in ('bronze','silver') and table_type='BASE TABLE'` > `$S/truncate.sql` | 23 tabelas |
| 5 | `TRUNCATE` + restore na mesma transação | `docker run --rm -v $S:/s postgres:17 psql "$DATABASE_URL_SP" -X -q -v ON_ERROR_STOP=1 --single-transaction -f /s/truncate.sql -f /s/dump/bronze_silver.sql` | 45 s; sem erro |
| 6 | Remover o vínculo PL 3047/2022 × PLS 302/2018 | `delete from silver.proposicao_vinculo where id_proposicao_cd = 2344901 and id_proposicao_sf = 1007403160 and origem = 'manual'` e conferir `count(*) = 0` | `DELETE 1`, restam 0 |
| 7 | `dim_keyword` × `src/keywords.py` | comparar `(rotulo, termo, termo_requerido)` ativos com `KEYWORDS` | iguais (22); `load_dimensoes.py` **não** rodado |
| 8 | `setup_db.py` depois do restore | de `src/`: `DATABASE_URL="$DATABASE_URL_SP" python setup_db.py` | 10 s |
| 9 | Sondagem | `psql "$DATABASE_URL_SP" -At -F ' \| ' -f sql/sondagem_privilegios.sql`, contar linhas que não terminam em `t` | 139 linhas, 0 divergência |
| 10 | Contagens do destino × origem | mesmo `contagens.sql`, comparar **ordenado** (`sort`) | iguais, exceto o vínculo removido (abaixo) |
| 11 | Relatório do importador | de `src/`: `python importar_decisoes.py` | 0 conflito |
| 12 | Importação | `python importar_decisoes.py --aplicar`, depois `--aplicar` de novo | ver "Importação" |

`contagens.sql` (gerado do `information_schema`, para não esquecer tabela):

```sql
\pset format unaligned
\pset tuples_only on
\pset fieldsep ' | '
select string_agg(format('select %L as tabela, count(*) as n from %I.%I', table_schema||'.'||table_name, table_schema, table_name), ' union all ' order by table_schema, table_name) as sql
from information_schema.tables where table_schema in ('bronze','silver') and table_type='BASE TABLE' \gset
:sql ;
select 'max(tramitacao.data_extracao)', max(data_extracao)::text from silver.tramitacao;
select 'api.vw_monitoramento', count(*)::text from api.vw_monitoramento;
select 'gold.vw_movimentacoes', count(*)::text from gold.vw_movimentacoes;
select 'ultimo controle_execucao', max(executado_em)::text from bronze.controle_execucao;
select 'vinculo 2344901x1007403160', count(*)::text from silver.proposicao_vinculo where id_proposicao_cd = 2344901 and id_proposicao_sf = 1007403160;
```

## Contagens do ensaio (origem às 21:14 UTC de 30/10/2026)

| Tabela / medida | Origem | Destino |
|---|---:|---:|
| bronze.alerta_pauta | 0 | 0 |
| bronze.autores_json | 23266 | 23266 |
| bronze.controle_execucao | 186 | 186 |
| bronze.eventos_json | 1262 | 1262 |
| bronze.eventos_pauta_json | 1262 | 1262 |
| bronze.proposicoes_json | 23268 | 23268 |
| bronze.sf_mapa_revisora | 2322 | 2322 |
| bronze.sf_processo_json | 1389 | 1389 |
| bronze.temas_json | 23266 | 23266 |
| bronze.tramitacoes_json | 23263 | 23263 |
| silver.dim_deputado | 1116 | 1116 |
| silver.dim_keyword | 22 | 22 |
| silver.dim_orgao | 248 | 248 |
| silver.dim_senador | 134 | 134 |
| silver.dim_tema | 32 | 32 |
| silver.evento | 1062 | 1062 |
| silver.evento_pauta | 20617 | 20617 |
| silver.proposicao | 16736 | 16736 |
| silver.proposicao_acompanhada | 63 | 63 |
| silver.proposicao_tema | 38590 | 38590 |
| silver.proposicao_vinculo | 269 | **268** (vínculo removido, passo 6) |
| silver.proposicoes_proponentes | 23158 | 23158 |
| silver.tramitacao | 224689 | 224689 |
| max(tramitacao.data_extracao) | 2026-10-30 19:00:58 | igual |
| api.vw_monitoramento | 515 | 515 |
| gold.vw_movimentacoes | 0 | 0 |
| vínculo 2344901 × 1007403160 | 1 | **0** |

A origem tem ~373 MB com índices (bronze 142 MB, silver 231 MB); Postgres 17.6.

## Importação (Postgres local limpo, mesmo dump, passos 5–8 repetidos)

| | Relatório | 1º `--aplicar` | 2º `--aplicar` |
|---|---:|---:|---:|
| Conflitos | 0 | 0 | 0 |
| Projetos | 360 a criar | 360 criados | 0 |
| Associações | 372 a criar | 372 | 0 |
| Decisões | 360 a inserir | 360 gravadas | 360 iguais, nada a gravar |
| Fora do monitoramento (importadas) | 46 | 46 | 46 |

Planilha lida: 372 linhas em Proposições (78 SIM, 294 NÃO), 78 no Posicionamento. Depois do `--aplicar`: `data_implantacao` NULL; `api.vw_painel_decisoes` com 515 linhas. Na janela (Tarefa 4, passo 4), o "Gravado" deve bater com estes números, salvo mudança na planilha depois de 30/10 (explicar a diferença antes de aplicar).

## Carga completa no banco novo (ensaio, 30/10/2026, noite)

Rodada localmente (`TZ=America/Sao_Paulo`, de `src/`: `check_environment.py` e `pipeline.py`, sem `notify_n8n`), contra o banco novo depois da cópia. Na janela, a carga de verificação é a do GitHub Actions (Tarefa 4, passo 8).

| Etapa | Resultado | Tempo |
|---|---|---|
| Listagem D-14 (temas 64, 48, 66) | 558 ids | < 1 min |
| Bronze incremental | 2232 endpoints, 0 erro (1ª tentativa: 1 erro de DNS local, job falhou sem avançar janela, como previsto) | ~37 min (~3,5–4 s por proposição) |
| Acompanhadas fora da janela | 53 ids, 212 endpoints, 0 erro | 3 min 38 s |
| Reconciliação de 90 dias | 710 ids listados, 0 ausente | ~1 min |
| Eventos/pautas (D-7..D+14) | 7 eventos, 14 cargas ok | < 1 min |
| Silver | contagens iguais à cópia (nenhuma tramitação nova desde a cópia) | < 1 min |
| `dim_deputado` | 333 a processar; API da Câmara com HTTP 504/timeout em `/deputados` (34 falhas em 220) → interrompido, o job falharia sem avançar janela | > 38 min, inconclusivo |
| `dim_orgao` (rodado à parte) | 86 órgãos | 4 s |
| Senado (rodado à parte) | API do Senado sem resposta em 60 s (`/processo/classes`) → falhou | inconclusivo |
| `atualizar_api` (rodado à parte) | 6 materialized views | 9 s |

Nenhuma janela (`incremental`, `eventos`, `reconciliacao`) foi registrada nas tentativas que falharam. Pendente: repetir `dim_deputado` e Senado no banco novo com as APIs normais.

**Para a janela:** medir a API antes de começar (`curl -m 60 -w '%{http_code} %{time_total}'` em `/api/v2/deputados/<id>` da Câmara e em `/dadosabertos/processo/classes` do Senado). Com 504 ou timeout, não começar: a carga de verificação do passo 8 falharia e a reversão ficaria no caminho.

## Reversão (ensaio de 06/11/2026, sem Power BI)

Vale até a carga de verificação (B8); depois dela corrige-se para frente.

**n8n — colisão de webhook** (dois fluxos descartáveis no caminho `teste-virada-colisao`, criados, testados e arquivados pelo MCP; o caminho de produção não foi tocado):

| Passo | Resultado | Tempo |
|---|---|---|
| Publicar A; `POST` no caminho | execução em A | — |
| Publicar B com A ativo | **recusado**: `There is a conflict with one of the webhooks.` (nada muda; A segue ativo) | imediato |
| Despublicar A, publicar B; `POST` | execução em B | ~10 s |
| Despublicar B, `restore_workflow_version` de A, `publish_workflow` com o `versionId`; `POST` | execução em A | ~20 s |

Consequência para a janela: no B6, **despublicar o `4F6…` antes** de publicar o `DyzR…` (senão a publicação falha). Na reversão, **despublicar o `DyzR…` antes** de republicar o `4F6…`. Conferir pelo `search_workflow_executions` qual fluxo recebeu a primeira chamada real. Anotar o `versionId` ativo de cada fluxo no B1 para o `publish_workflow(versionId)` da volta.

**GitHub — revert do merge** (worktree descartável, sem push):

```bash
git merge --no-ff origin/legislativo-fundacao          # o merge do PR #13 (na janela: pelo gh pr merge 13 --merge)
git revert --no-edit -m 1 <sha-do-merge>               # sem -q (não é aceito)
git diff origin/main-anterior HEAD | wc -l             # ensaio: 0 linha (volta exata)
git push origin main
git tag -d legislativo-entrega-1-prod && git push origin :refs/tags/legislativo-entrega-1-prod
```

Num worktree fora do clone principal, o filtro `segredos-pbi` não encontra `BI/filtro_segredos.py`; no clone principal ele funciona normalmente.

**Secret `DATABASE_URL`:** a troca é manual pelo Erick (Settings → Environments → `DATABASE_URL`); a URL antiga fica guardada fora do repositório para a volta. Tempo medido no ensaio pelo Erick no environment `homologacao`: _a preencher_.

**E-mails de teste:** todo e-mail disparado em teste ou na carga de verificação vai só para abcsdata@abcsagro.com.br (decisão do Erick, 06/11). No B6 o `DyzR…` é publicado com destinatários = Erick; os destinatários da Ana entram no B9, depois do B8 verde.
