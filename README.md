# Monitoramento de Proposições Legislativas — Suinocultura

Pipeline de dados que automatiza o acompanhamento de proposições legislativas relevantes para a suinocultura, extraindo e organizando informações da API de Dados Abertos da Câmara dos Deputados.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-14+-4169E1?logo=postgresql&logoColor=white)
![Status](https://img.shields.io/badge/status-em%20desenvolvimento-yellow)

---

## Sobre o projeto

O time político da ABCS acompanha manualmente as proposições legislativas que impactam o setor de suinocultura: abre o portal da Câmara, busca por número, lê a ementa, identifica autor e comissão, anota a última movimentação. É um processo repetitivo que consome tempo de profissionais cuja competência é análise política, não coleta de dados.

Este projeto automatiza essa coleta: extrai as proposições relevantes diretamente da API pública da Câmara, armazena o histórico em um banco estruturado e entrega os dados prontos para consumo em dashboard ou planilha — liberando o time para focar em análise e articulação.

## O problema

Sem esse pipeline, cada uma dessas perguntas exige navegação manual repetida:

- Quais proposições relacionadas à suinocultura estão tramitando?
- Quem é o autor, de qual partido e estado?
- Em qual comissão a proposição está agora?
- Quando foi a última movimentação?
- Surgiram proposições novas que ainda não estavam no radar?

Não há histórico consolidado, alertas ou visão comparativa — só o portal, uma proposição de cada vez.

## Como funciona

A extração usa duas camadas de filtro: um filtro amplo por tema legislativo (reduz o universo de ~27.000 proposições para as classificadas em Agricultura/Pecuária e Meio Ambiente), e um filtro fino por palavra-chave mantido como configuração — novos termos podem ser adicionados sem reprocessar a extração.

O filtro fino roda contra a ementa **e** contra o campo de indexação temática que a própria Câmara mantém por proposição — a ementa sozinha se mostrou insuficiente (ex.: uma proposição sobre bem-estar de suínos pode ter ementa genérica como "Institui o Código Federal de Bem-Estar Animal", sem citar o termo, mas a Câmara já indexa isso). O matching usa regex ancorada por início de palavra em vez de busca por substring simples, para cobrir variações de gênero/número (suíno/suína/suínos) sem gerar falso positivo por coincidência textual (ex.: um radical mal ancorado para "aves" bateria em "grave"; para "ração" bateria em "tração").

Termos genéricos podem ter um **termo requerido** (`dim_keyword.termo_requerido`): um 2º regex que também precisa bater para a keyword contar. É o que separa, por exemplo, "bem-estar animal" no contexto de produção (abate, granja, cadeia produtiva) de "bem-estar animal" de pet — vocabulário quase idêntico que keyword simples não distingue. Com esse ajuste, o conjunto automático (~147 proposições) ficou próximo do que a consultora valida manualmente (~139).

Os dados passam por três camadas, seguindo o padrão medallion:

```
API Câmara dos Deputados
        │
        ▼
 Scripts Python (extração e carga)
        │
        ▼
   PostgreSQL
    ├── bronze  → JSON bruto da API, append-only (auditoria e reprocessamento)
    ├── silver  → dados normalizados em tabelas relacionais
    └── gold    → views analíticas prontas para consumo (keywords aplicadas aqui)
        │
        ▼
  Power BI / planilha exportada
```

O projeto nasceu com infraestrutura local (volume pequeno, consumidor interno, iteração rápida) e migrou para um Postgres gerenciado na nuvem (Supabase) sem alterar nenhuma lógica de negócio — só o destino da conexão (`DATABASE_URL`), exatamente como esse desenho já previa desde o início.

## Stack

| Camada | Tecnologia |
|---|---|
| Extração e transformação | Python (`requests`, `pandas`) |
| Armazenamento | PostgreSQL (Supabase) |
| Orquestração | GitHub Actions (agendamento diário e execução manual) |
| Visualização | Power BI Desktop ou export CSV |

## Fonte de dados

[API de Dados Abertos da Câmara dos Deputados](https://dadosabertos.camara.leg.br/swagger/api.html) — pública, gratuita, mantida pela própria Câmara. O pipeline consome os endpoints de listagem, detalhes, autores, temas e tramitações de cada proposição.

## Status do projeto

- [x] Extração e carga da camada **bronze** (proposições, autores, temas e tramitações) — ~1.530 proposições únicas
- [x] Modelagem da camada **silver** (normalização relacional + tabelas de referência)
- [x] Views analíticas da camada **gold** com matching de palavras-chave — ~280 proposições relevantes identificadas
- [x] Enriquecimento do autor principal com partido/UF **atuais** (dimensão de deputados)
- [x] Carga incremental (bronze → silver → dim_deputado em um único script)
- [x] Pautas de comissões e plenário (`gold.vw_pautas_monitoradas`) — alerta de proposições monitoradas agendadas para votação
- [x] Audiências públicas (`gold.vw_audiencias_de_interesse`) — debates públicos cujo tema bate nas keywords
- [ ] Dashboard Power BI (em desenvolvimento)
- [x] Agendamento no GitHub Actions: carga completa às 07h17 e pautas às 10h e 14h (São Paulo), usando o environment `DATABASE_URL`
- [ ] **Filtro de arquivamento para indicadores** — excluir dos KPIs proposições arquivadas ou correlatas a arquivamento (situações 914/920/923/930/931/940, possivelmente também 950/1120/1222/1292). A definição do bucket será fechada com a área de negócio. Requer também tratar o `cod_situacao` nulo em ~55 proposições (a API vem devolvendo `statusProposicao` com `descricaoSituacao` vazio em extrações recentes, e a silver, ao pegar a última extração, às vezes descarta um valor bom anterior).

O partido/UF exibidos são os atuais do deputado (dimensão separada, atualizável), não os da data em que a proposição foi apresentada — decisão deliberada, já que o uso real é o time político saber com quem falar hoje.

A carga incremental (`extract_incremental.py`) busca proposições com tramitação nos últimos 3 dias (pega tanto proposições novas quanto movimentação em proposições antigas) e registra cada execução em `bronze.controle_execucao`. A janela do próximo run nunca começa depois de "3 dias antes da última execução bem-sucedida" — se a máquina ficar dias sem rodar o job, a janela seguinte se alarga sozinha para cobrir o período perdido, sem depender de alguém notar a falha.

A mesma execução também atualiza os eventos das comissões (CAPADR, CCJC, CMADS e PLEN — as únicas confirmadas com eventos deliberativos ativos; não existe hoje uma comissão específica de bem-estar animal em atividade) numa janela rolante de D-7 a D+14:

- **Eventos deliberativos** (sessões e reuniões de votação): o cruzamento com as proposições monitoradas geralmente ocorre de forma indireta — um item de pauta (ex. um requerimento) referencia o PL de fato como "proposição relacionada", caminho bem mais comum que o item citar o PL diretamente.
- **Audiências públicas**: não têm pauta estruturada nem link confiável com proposição. O cruzamento é feito por keyword no texto do tema da audiência (`evento.descricao`) — o sinal é "há debate público sobre um assunto de interesse, em tal data, com tais expositores".

**Próximas fases:** alertas automáticos e dados do Senado Federal.

## Rodando localmente

```bash
git clone https://github.com/erickluizsilva/monitoramento_proposicoes
cd monitoramento_proposicoes

python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.lock

# copie src/.env.example para src/.env e preencha as credenciais do seu Postgres
cp src/.env.example src/.env

cd src
# no .env, use DATABASE_URL (Supabase/Neon/etc.) ou as variáveis DB_* discretas — ver .env.example
python setup_db.py             # cria os schemas e tabelas
python extract_bronze.py       # roda a carga histórica (bronze)
python load_dimensoes.py       # popula tabelas de referência (temas e keywords)
python load_silver.py          # transforma bronze em tabelas relacionais (silver)
python load_dim_deputado.py    # enriquece autores deputados com partido/UF atuais
python load_dim_orgao.py       # nomes dos órgãos (comissões, plenário) por trás das siglas

# carga histórica de eventos/pautas (uma vez; ajuste as datas em load_eventos.py):
python -c "from datetime import date; from load_eventos import executar_carga_eventos; executar_carga_eventos(date(2023,1,1), date.today())"

# no dia a dia, roda só isso (bronze incremental + eventos + silver + dimensões, tudo em um):
python pipeline.py
```

## Execução no GitHub Actions

O workflow `.github/workflows/pipeline.yml` executa a carga incremental em um
runner Ubuntu hospedado pelo GitHub. A máquina local pode ficar desligada: os
dados e o controle de execução ficam no PostgreSQL na nuvem, e cada execução
instala seu próprio ambiente Python. Não é necessário instalar um MCP ou plugin
no runner.

### Configuração inicial

1. No Supabase, abra **Connect** e copie a conexão **Session pooler**, na porta
   `5432`. Essa opção permite conexão por IPv4. Preencha a senha do banco e
   codifique os caracteres especiais da senha para uso em uma URL. Não use a
   chave da API do Supabase como senha.
2. No repositório do GitHub, abra **Settings → Environments → DATABASE_URL**.
   Em **Environment secrets**, crie o secret **`DATABASE_URL`** com a URL completa.
   O job usa `environment: DATABASE_URL`; se mudar o nome do environment,
   atualize esse campo em `.github/workflows/pipeline.yml`:

   ```text
   postgresql://postgres.PROJECT_REF:SENHA_CODIFICADA@POOLER_HOST:5432/postgres?sslmode=require
   ```

   Substitua os campos pelo que aparece em **Connect**. Não adicione aspas ao
   valor e não versione o arquivo `src/.env`. O workflow exige SSL e define um
   timeout de conexão de 15 segundos.
3. Confirme que esse banco já contém os schemas Bronze, Silver e Gold e keywords
   ativas. Para um banco novo, execute a preparação e a carga histórica descritas
   acima separadamente. O workflow diário não cria tabelas, não reinicializa
   keywords e não executa a carga histórica.
4. Publique o código e os workflows na **branch padrão** do repositório. Em
   **Actions**, habilite os workflows se o GitHub solicitar. A configuração do
   repositório deve permitir `actions/checkout` e `actions/setup-python`.
5. Em **Actions → Pipeline diário e pautas → Run workflow**, escolha a branch padrão
   e o modo `completo` ou `pautas`. Execute a primeira carga manualmente.
   A etapa de verificação confere a conexão,
   a existência das tabelas/views necessárias e a presença de keywords ativas.
   Confirme a conclusão e as contagens Gold no log da execução.

Referência da conexão: [documentação do Supabase](https://supabase.com/docs/guides/database/connecting-to-postgres).
Se o projeto tiver restrições de rede, o runner também precisa conseguir acessar
o endpoint escolhido.

### Agendamento e acompanhamento

- A **carga completa incremental** executa todos os dias às **07h17 de São Paulo**
  (cron `17 10 * * *` em UTC). Inclui proposições, eventos/pautas, Silver e dimensões.
- As **pautas e audiências** recebem atualizações adicionais todos os dias às
  **10h e 14h de São Paulo** (cron `0 13,17 * * *` em UTC), por
  `src/pipeline_pautas.py`. Esse modo atualiza Bronze de eventos/pautas, Silver de
  eventos/pautas, relatores e órgãos; não extrai proposições nem avança sua janela.
- O processo Python usa `TZ=America/Sao_Paulo` para calcular as janelas de datas.
  Altere os crons em `pipeline.yml` para ajustar os horários.
- O workflow permite execução manual e serializa as execuções desse pipeline,
  sem cancelar uma carga em andamento. O limite de duração é de 120 minutos.
- O environment precisa permitir a branch padrão. Se tiver revisão obrigatória,
  os jobs aguardarão aprovação antes de acessar o secret; para execução autônoma,
  configure regras compatíveis com esse uso.
  [Referência de environments](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments).
- Os logs ficam em **Actions → execução → job pipeline**. Ative as notificações
  de falha do GitHub Actions nas configurações da sua conta.
- Falhas parciais em proposições, eventos ou deputados fazem o job falhar. A
  janela incremental só avança após Bronze, eventos, Silver e dimensões
  concluírem. Os endpoints já gravados permanecem na Bronze; a próxima execução
  tenta novamente a janela, podendo acrescentar novos snapshots.
- O controle de concorrência do Actions não impede execução simultânea pela sua
  máquina. Ao ativar o agendamento remoto, desative o agendamento local existente.
- O GitHub pode atrasar ou descartar disparos agendados sob alta carga. Em
  repositórios públicos, o agendamento é desativado após 60 dias sem atividade.
  Verifique periodicamente a última execução e reative o workflow se necessário.
  [Referência de agendamento](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).
- Esse job atualiza o banco; a atualização do Power BI deve ser configurada
  separadamente no Power BI Service ou executada no Desktop.

### Arquivos locais do Power BI

O diretório `BI/`, arquivos `.pbix`, `.pbit`, `.abf` e configurações locais de
projetos PBIP ficam no `.gitignore`. Eles podem conter dados embutidos, caches e
metadados de conexão. O PBIX anteriormente versionado foi retirado do índice;
a cópia local é preservada. Isso não remove o arquivo dos commits históricos.
Não inclua esses artefatos ao publicar alterações do pipeline.

### Notificação ao n8n

Após cada carga bem-sucedida (completa ou pautas), o Actions executa
`src/notify_n8n.py`: envia um POST ao webhook de produção com o header
`X-Webhook-Token`. Cadastre `N8N_WEBHOOK_URL` e `N8N_WEBHOOK_TOKEN` como secrets
no mesmo environment `DATABASE_URL`. O webhook do agendador local estava no
arquivo `.bat`, que não é executado pelo runner Linux; a chamada agora é uma
etapa explícita do Actions.

O payload inclui `origem=github_actions`, `modo`, `run_id`, `run_url` e a data
da notificação para identificar a execução no n8n. A etapa só aceita HTTP 2xx;
erros HTTP ou de conexão fazem o job falhar. O POST não é repetido automaticamente,
pois o n8n pode ter recebido a chamada mesmo se a resposta sofrer timeout.
O aceite HTTP confirma a entrega ao webhook; confirme também o resultado do
workflow e da atualização da planilha nas **Executions** do n8n.

Para testar a integração ou repetir apenas a notificação depois de uma falha,
abra **Run workflow**, escolha o modo desejado e marque
**somente_notificar_n8n**. Essa opção usa os dados já existentes no banco.
Se precisar repetir uma chamada, confira antes se houve execução correspondente
no n8n pelo `run_id`.

### Ambiente reproduzível e testes

O Python do runner é definido em `.python-version` (3.14). `requirements.txt`
mantém a lista de dependências diretas; `requirements.lock` fixa as versões
diretas e transitivas validadas. Instale o lock para reproduzir esse ambiente.
Ao atualizar dependências, use um ambiente virtual novo com essa versão de Python,
instale `requirements.txt`, gere novamente o lock com `python -m pip freeze >
requirements.lock` e rode os testes antes de publicar.

O workflow `.github/workflows/tests.yml` roda em pull requests e pushes na
`main`, sem secrets e sem acessar banco/API reais. Para executar localmente,
na raiz do projeto e com o ambiente virtual ativo:

```bash
python -m compileall -q src tests
python -m unittest discover -s tests -v
```

## Autor

**Erick Silva** — Analista de BI, ABCS
