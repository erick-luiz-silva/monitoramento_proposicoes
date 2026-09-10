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

A infraestrutura é local (sem dependência de nuvem): o volume de dados é pequeno, o consumidor é um time interno, e a decisão prioriza iteração rápida sobre complexidade operacional. Uma eventual migração para infraestrutura compartilhada não exige alterar a lógica de negócio, apenas o destino da conexão.

## Stack

| Camada | Tecnologia |
|---|---|
| Extração e transformação | Python (`requests`, `pandas`) |
| Armazenamento | PostgreSQL |
| Orquestração local | Task Scheduler / cron |
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
- [ ] Agendamento automático da carga incremental (Task Scheduler / cron)
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

python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt

# copie src/.env.example para src/.env e preencha as credenciais do seu Postgres
cp src/.env.example src/.env

cd src
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

## Autor

**Erick Silva** — Analista de BI, ABCS
