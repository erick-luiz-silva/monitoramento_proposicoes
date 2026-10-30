# Plano — Módulo de Monitoramento Legislativo da Plataforma ABCS

Data: 28/10/2026. Status: fundação implementada na branch `legislativo-fundacao`; importação e urgência em validação na homologação; aplicação pendente.

Revisão: GPT-6 Astra, com ajustes incorporados. Este plano e o [PRD](prd.md) devem passar pelo agente revisor antes de futuras entregas ou revisões ao usuário.

Revisão de 28/10/2026 (tarde), com decisões do Erick:
- duas entregas, a primeira com o Power BI inserido no site pelo link público;
- autorização no servidor;
- piloto em homologação;
- mockup navegável antes da construção;
- estado do Senado conferido na implementação em `main`.

Os detalhes estão no PRD, seções 2, 5, 6 e 7. O mockup foi aprovado em 28/10/2026, e as decisões dele e os esclarecimentos da avaliação do Astra estão no PRD (RF02, RF03, RF04, RF08, RF09, RN03 e RN04). A revisão final do Fable contra o código também foi incorporada:
- grants refeitos pelo `setup_db`;
- DDL em duas partes;
- projeção das inclusões;
- Power BI mantido pelo link público, com projeção de colunas fixas;
- regras únicas entre o Power BI e as telas.

## 1. Objetivo e arquitetura

Substituir a planilha editada por Ana e as consultas do Power BI por edição e dashboards no módulo `/legislativo` da Plataforma ABCS. Preservar o pipeline Python, Supabase legislativo, GitHub Actions e n8n.

Arquitetura escolhida pelo usuário:

- Next.js existente, com o mesmo login, navegação, componentes e deploy da plataforma.
- Dados oficiais nas camadas bronze, silver, gold e caches do banco legislativo atual.
- Decisões humanas persistentes em schema próprio, denominado `gestao` nesta proposta, no banco legislativo.
- Servidor Next.js valida a identidade e a autorização; acessa o banco legislativo por conexão TLS e papel PostgreSQL restrito, com pooler compatível com serverless.
- Credencial nova para a aplicação; Power BI (`anon`), pipeline e n8n mantêm as suas. Nenhuma credencial técnica no navegador.

O Supabase Auth da plataforma não autoriza automaticamente o outro projeto Supabase. A autorização por pessoa ocorre no servidor; o banco legislativo limita as operações disponíveis à credencial técnica. Não apresentar esse desenho como RLS compartilhada entre bancos. **Decidido em 28/10/2026:** não haverá RLS por pessoa no banco legislativo, e o risco foi aceito (PRD RF01). As capacidades ficam junto aos perfis, no banco da plataforma, a confirmar na fase 1.

- Power BI na Entrega 1 pelo link público "Publicar na Web", inserido numa página do site. Decisão do Erick em 28/10/2026: não há licença Pro, os riscos foram aceitos e o painel não mostra dados sensíveis. Na Entrega 2, ele é substituído pelas telas nativas e desligado.

### Alternativas consideradas

| Alternativa | Benefício | Custo ou limitação |
|---|---|---|
| Módulo na plataforma existente — escolhida | Reutiliza login, interface, hospedagem e operação | Compartilha releases com mailing e exige integração segura com o banco legislativo |
| Frontend independente sobre Supabase | Dados e decisões no mesmo ambiente; pouco backend próprio | Outro login, interface e deploy para manter |
| Aplicação com API própria, por exemplo FastAPI | Controle das integrações e familiaridade com Python | Mais serviço, contratos e operação |
| Formulários e tabelas sobre o banco | Substituição rápida da edição da planilha | Customização adicional para substituir os dashboards; possível licença ou servidor |

Não migrar todo o pipeline para compartilhar login nem criar backend independente no MVP.

## 2. Evidências e cobertura do módulo

Fontes consultadas em 28/10/2026:

- Planilha Google via API (a planilha do monitoramento, ID em GOOGLE_SHEET_MONITORAMENTO_ID), especialmente as abas Proposições e Posicionamento ABCS.
- Workflows publicados do n8n via MCP: Monitoramento de Proposições → Google Sheets (`4F6Y2cOHhqNuhdYm`), Inclusão manual de proposições (`23CyodhPlORNJ4xS`) e Agendador – Monitoramento de Proposições (`0sieqPDvsqoZcs31`).
- Páginas, visuais, medidas e filtros do PBIP versionado em `BI/`. Não houve conferência visual do relatório remoto publicado.
- Código e documentação locais da Plataforma ABCS em `banco-de-contatos-mailing`. A configuração ativa da hospedagem não foi auditada.

Snapshot da planilha: 350 proposições, com 81 SIM, 268 NÃO e uma sem avaliação; 54 acompanhadas. Posicionamento tinha 81 linhas correspondentes, ligadas por `identificacao` com sufixo de casa, porque não há coluna de id: posição em 68, ação em 39, parecer em 27, observações em 38; prioridade com 16 SIM, 12 NÃO e 53 vazios. São referências para conferência, não totais fixos de aceite. Legado de 151 linhas e backup de 20/10/2026 servem à auditoria, sem sobrescrever automaticamente as abas atuais.

Estado do Senado em `main` (commits `017da1a` e `28d9a2a`):
- **Fases 1 a 4, mescladas e implantadas em 28/10/2026** (deploy registrado nas notas do projeto; o README ainda está desatualizado):
  - `casa` e chave do Senado (1e9 + id nativo);
  - proposições do Senado e `dim_senador`;
  - `silver.proposicao_vinculo` com identificação, "Revisora", MPV e manual, e `chave_projeto` por grupo;
  - 9 acompanhadas do Senado na seed;
  - n8n por grupo, com a casa no e-mail e na planilha;
  - `ultima_carga_senado`.
- **Pendente:**
  - fase 5, agenda do Senado (stub);
  - fase 6, inclusão do Senado no n8n: não construir; vai direto para a inclusão do sistema;
  - fase 7, Power BI: na Entrega 1, só o mínimo (projeção única, contagem por `uuid_projeto`, "Adiada"); o resto fica para a Entrega 2;
  - fase 8, documentação.

O fluxo `4F6Y2cOHhqNuhdYm` também escreve as novas pendências na aba Proposições. A virada precisa desligar essas escritas (PRD seção 5).

### Telas e dashboards

| Área | Cobertura |
|---|---|
| Início | Entrega 1: urgentes, pendentes de avaliação e monitorados (carteira ativa); fila de atenção com motivo; até 10 últimas movimentações em 30 dias. Entrega 2: reuniões e audiências agendadas |
| Carteira | Busca por identificação e ementa; filtros por prioridade, posição, situação, órgão, palavra-chave e casa; atenção, identificação, ementa resumida, posição, órgão, última movimentação, ação e link |
| Projeto | Versões por casa, ementa integral, autoria, partido/UF, situação, órgão, tramitações e pautas; edição das decisões e histórico |
| Pautas | Indicadores de reuniões agendadas, eventos e itens votados/cancelados; filtros por proposição, comissão, situação e relator; data, casa, relator, partido, situação e resultado |
| Audiências | Totais e agendadas, filtro por palavra-chave, data, casa, órgão, assunto, situação e link oficial |
| Autores e partidos | Distribuições por ano, tipo, UF e partido; ranking de autores; indicadores de autores, partidos, UFs e origem Senado; filtro de prioridade |

Adicionar fila de avaliação com SIM/NÃO na linha, inclusão manual com estado visível e exportação CSV da carteira. Os casos a conferir são uma lista do mantenedor, fora da navegação da Ana. Uso só em computador. Toda tela segue o princípio de produto do PRD: limpa, só o necessário, explicação em dica e aviso só quando há problema.

Divisão por entrega:
- **Entrega 1, nativo:** Início com três indicadores, Carteira (Ativas e Histórico), Projeto, fila de avaliação e inclusão.
- **Entrega 1, Power BI inserido no site:** Pautas, Audiências e Autores e partidos.
- **Entrega 2:** as três áreas do Power BI e o Início completo passam a ser nativos.

Cliques em indicadores e gráficos abrem listas com filtros equivalentes. Cards operacionais contam projetos; análises de autoria e distribuição contam versões legislativas com denominador explícito. Reuniões e itens de pauta têm contagens separadas. O total de prioridades inclui as urgentes.

Audiências são sugestões temáticas, sem vínculo inferido com projeto. Partido e UF são os atuais disponíveis. Não inventar autor ou filiação quando ausentes. A origem Senado deve ser identificada por casa da versão, sem depender de texto genérico de autoria.

## 3. Regras e dados

### Avaliação, carteira e encerramento

- Relevância: pendente, SIM ou NÃO. Posição: Acompanhar, A favor, Contra, A favor com ressalvas ou Em análise, preservando ausência de decisão.
- Preservar prioridade como SIM, NÃO ou não informada. Ação, parecer e observações permanecem separados.
- Elegibilidade: acompanhada (planilha antiga ou incluída), relevante SIM ou prioritária, excluindo NÃO e encerramento efetivo. Prioridade exige SIM nas novas edições.
- Carteira padrão: elegível com última movimentação do grupo nos últimos 12 meses de calendário em Brasília, ou prioridade ativa de qualquer idade.
- Sem data e sem prioridade, consultar pelo histórico. A fila de avaliação conserva a regra de radar, independente desse corte.
- Pautas futuras de elegíveis não desaparecem pelo corte de inatividade. Histórico e retenção de coleta não são limitados a 12 meses.
- Arquivadas ou transformadas em norma vão ao histórico, inclusive prioritárias, somente após encerramento efetivo do projeto.
- Uma versão em tramitação mantém o projeto ativo. Arquivamento por remessa não encerra o projeto. Divergências ou remessa sem destino carregado ficam na lista do mantenedor, independente de idade ou ausência de data, sem prioridade ou urgência automática.

### Urgência e confirmação

Movimentação elegível é só uma movimentação maior, pela lista do Apêndice A do PRD, validada pela Ana em 28/10/2026 e guardada numa tabela de referência editável. Prioritário ativo fica urgente por movimentação elegível não confirmada ou por pauta agendada na janela entre o início de hoje e o início do 15º dia seguinte, exclusivo, em Brasília. O status agendado também é obrigatório.

Ana confirma os IDs dos movimentos efetivamente apresentados; a confirmação é compartilhada e auditada. Nova ocorrência recebida durante a confirmação continua pendente. Confirmar movimentos não elimina urgência causada por pauta. Cancelamento e reagendamento atualizam esse motivo.

Estabelecer baseline na implantação e na ativação de prioridade. Carga inicial e backfill não abrem urgência; cargas operacionais registram novas ocorrências com identidade estável e data oficial posterior à referência. Correções antigas não reabrem urgência no MVP. Não reutilizar o checkpoint do e-mail como confirmação de leitura.

### Identidade e persistência

Entidades mínimas: `projeto`, `projeto_proposicao`, `decisao_projeto`, `inclusao_manual`, `historico_alteracao` e `confirmacao_movimentacao`. A ocorrência de movimentação maior é um contrato (view) sobre `silver.tramitacao`, sem tabela própria (PRD RN09).

UUID estável identifica projeto, URLs, decisões e histórico. Preservar os IDs existentes, casa, IDs de origem e a `chave_projeto` derivada. Igualdade de número entre casas não prova identidade. Mudanças de agrupamento preservam decisões e aliases; não fundir textos nem separar decisões automaticamente. No MVP, a reconciliação que afeta conteúdo é uma função SQL auditada, executada pelo mantenedor, sem capacidade nem tela próprias.

Ciclo de vida do UUID (PRD RN03):
- nasce só com decisão, inclusão ou acompanhamento, criado pela migração ou pela aplicação;
- o pipeline segue dono dos vínculos;
- um contrato aplica a regra única do PRD (RN03, item 6): grupo com UUIDs diferentes vai para a lista do mantenedor;
- uma versão nova de grupo com um só UUID é associada na leitura, pelo contrato, sem gravação do pipeline;
- o caso inverso (versões de um UUID que se separam) também vai para a conferência;
- `projeto_proposicao` não tem FK para a silver;
- rota e link do e-mail aceitam `id_proposicao` para pendentes sem UUID;
- os vínculos manuais da seed são recriados a cada `setup_db`, então a correção é feita na seed;
- no MVP, a reconciliação é uma função SQL auditada, sem tela.

Na migração, SIM vence no grupo; sem SIM, NÃO vence; sem avaliação, pendente. Prioridades incompatíveis, posições ou textos divergentes exigem revisão. Nas novas edições, tornar prioritária implica SIM com confirmação explícita quando necessário; marcar NÃO em uma prioridade exige confirmar sua retirada. Gravação e auditoria na mesma transação, com versão para evitar sobrescrita concorrente.

## 4. Segurança e integração

Toda equipe ativa consulta. Ana recebe edição e confirmação iniciais e, por ora, é a única editora. O administrador pode conceder ou retirar a edição no futuro, sem mudar o código. A concorrência fica no mínimo: número de versão e aviso. Administradores concedem acesso, mas não ganham edição legislativa automaticamente; editor do mailing também não. Validar perfil ativo e capacidade em cada operação.

Proteger as decisões. A `anon` só lê a projeção do painel público, com colunas fixas (relevância, posição, prioridade e `em_carteira`), e nunca `gestao`, parecer, observações ou histórico. Corrigir grants atuais e futuros no SQL fonte, inclusive em `gold`, para que `setup_db.py` não restaure exposição.

Com o link público mantido, o Power BI continua usando a `anon`, e não há revogação. Regras:
1. a projeção do painel em `api` tem colunas fixas e testadas: sem ação, parecer, observações, histórico nem autoria das decisões;
2. `gestao` e os contratos nunca ficam expostos pela Data API nem recebem grant de `anon`/`authenticated`;
3. o cadastro aberto do Auth do projeto legislativo fica desligado;
4. os grants do papel da aplicação ficam no SQL que recria os objetos.

DDL em duas partes:
- tabelas de `gestao` antes do `drop_api.sql`, evoluídas por `ADD COLUMN IF NOT EXISTS`;
- contratos (num schema não exposto) e projeção do painel (em `api`, colunas fixas) depois de `schema_api.sql`, recriados a cada `setup_db`.

Os testes verificam dependências nos dois sentidos e os grants depois de cada `setup_db`.

`gestao` fica fora de `api`/`api_cache` e de dependências removíveis pelo `DROP ... CASCADE` atual. Cargas não sobrescrevem decisões, textos ou confirmações humanas; podem registrar ocorrências técnicas, processar pedidos e manter associações pelos contratos definidos.

- Manter carga diária às 07h17 e pautas às 10h e 14h em Brasília.
- Substituir consultas à planilha pelas decisões do banco e contratos SQL privados de elegibilidade, carteira, pendências e urgência.
- Preservar e-mails e seus checkpoints após sucesso ou ausência de itens; NÃO continua suspendendo alertas de acompanhadas, sem eliminar retenção de coleta. Não restringir e-mails apenas às prioridades nem importar o corte visual.
- `proposicao_acompanhada` permanece projeção ou retenção operacional, sem segunda edição humana concorrente. O pipeline continua lendo dela para carregar e reter as acompanhadas. Depois da virada, uma função de `gestao` grava a acompanhada com `origem = 'sistema'` assim que o n8n resolve o id da Câmara. A partir daí, o n8n dispara o `modo=inclusao`, e o pedido só passa para "concluída" quando a proposição aparece em `api` (PRD RF08). A seed segue só como retenção (`ON CONFLICT DO NOTHING`).
- Virada dos consumidores na ordem do PRD, seção 5. Depois dela, nenhum fluxo lê ou escreve a planilha. Os passos 1 a 5 têm reversão testada em homologação, válida só até a Ana começar a editar no sistema.
- Os e-mails de alerta levam link para o projeto no sistema e mostram "Adiada".
- Inclusão começa pela Câmara, reutilizando resolução e modo de carga existentes. Pedidos não expiram após duas horas; tentativas são espaçadas, deduplicadas e retomáveis. Inclusão no Senado não é prometida sem integração própria.
- Decisões aparecem imediatamente; cache fica restrito aos dados oficiais. Mostrar separadamente carga por processo/casa e atualização do cache; falhas não podem parecer atualizações bem-sucedidas.

## 5. Entrega, riscos e aceite

1. **Fundação:**
   - homologação com dados oficiais copiados;
   - acesso restrito da aplicação;
   - projeção do painel público com colunas aprovadas pelo Erick e cadastro aberto do Auth desligado;
   - tabelas e contratos de `gestao`;
   - ensaio da migração e lista de conflitos;
   - hospedagem e pooler;
   - capacidades na plataforma;
   - lista de movimentações maiores validada pela Ana em 28/10/2026 (PRD, Apêndice A);
   - conflitos da migração decididos pela Ana na planilha.
2. **Mockup navegável (concluído em 28/10/2026, versão 2 aprovada):**
   - protótipo com dados fictícios cobrindo as tarefas da Entrega 1 (PRD seção 6, item 2);
   - o Erick testa e sugere mudanças, e o ciclo se repete até a aprovação;
   - o resultado atualiza PRD e plano antes de qualquer código da aplicação.
3. **Entrega 1, construção:**
   - edição, fila, Carteira, Projeto, inclusão, histórico, urgência e frescor;
   - Power BI público inserido no site, lendo a projeção do painel (contagem por `uuid_projeto`, `em_carteira` do contrato, "Adiada");
   - n8n adaptado em homologação (leitura de `gestao`, projeção das inclusões, "Adiada" no e-mail).
4. **Entrega 1, piloto e virada:**
   - piloto só em homologação; nada volta para produção;
   - planilha oficial até o congelamento;
   - importação final com conflitos zerados;
   - troca dos consumidores na ordem definida;
   - aceite quando a planilha deixa de ser usada e de ser lida ou escrita por automações.
5. **Entrega 1, estabilização:**
   - ciclos diário e de pautas;
   - concorrência, cancelamento, duplicidade e falha com retomada;
   - rollback da aplicação mantém o banco como fonte única.
6. **Entrega 2:** telas nativas de Pautas, Audiências, Autores e partidos e o Início completo; depois do aceite, desligar o Power BI e a credencial dele.

Riscos principais: manutenção individual (reusar stack e evitar serviço novo), regressão no mailing (módulo isolado e mudanças aditivas), fontes concorrentes (virada explícita), agrupamentos mutáveis (UUID e reconciliação auditada), frescor (sinais por etapa) e adoção (piloto com Ana).

Aceite (detalhado no PRD, CA01–CA14): anonimato sem internos (fora a projeção deliberada do painel); permissões independentes do mailing; edição imediata auditada e sem sobrescrita; contagens consistentes entre gráficos e listas; prioridades antigas visíveis; encerramento entre casas correto; urgência independente do envio de e-mail; inclusão idempotente e retomável; migração sem perda; decisões e permissões preservadas após backfill e recriação dos caches.

Usar unittest/fixtures para Python, testes SQL de contratos e privilégios no harness Postgres local, Vitest para a aplicação e Playwright só para o roteiro do CA11. Testes automatizados dispensam APIs e credenciais reais e usam dados sintéticos. A homologação do piloto usa dados oficiais públicos e uma importação privada das decisões. Uso só em computador. Não criar comentários, responsáveis, aplicativo nativo, notificações complexas, agente de IA ou novo serviço de BI neste MVP.

### Referência temporal na virada

No congelamento da planilha, depois da importação final sem conflitos e antes de habilitar a edição da Ana, o mantenedor define a referência uma única vez no banco de destino:

```sql
UPDATE gestao.parametro
SET valor = clock_timestamp()::text
WHERE chave = 'data_implantacao' AND valor IS NULL;
```

Conferir o valor gravado e preservá-lo nas reexecuções, backfills e novos `setup_db`. Não preencher automaticamente no ensaio. A urgência compara a data oficial com a referência mais recente entre esse instante e `prioridade_desde`.
