# Carteira legislativa — implementação em homologação

Data: 30/10/2026. Status: implementação concluída e enviada à branch de homologação; validação local aprovada. Smoke remoto autenticado e aceite humano pendentes. Revisão Astra do plano e ajustes preservados abaixo.

## Objetivo e referências

Implementar na homologação o mockup aprovado: modo de edição na Carteira e na ficha, diferenças visíveis em cada campo, conclusão/cancelamento explícitos, hierarquia nas linhas, filtros por atenção e preferências visuais persistidas.

- [Contrato funcional e critérios de aceite](2026-10-30-legislativo-edicao-carteira.md).
- [Mockup interativo aprovado](../monitoramento-legislativo/mockup/legislativo-edicao-mockup.html).
- [PRD](../monitoramento-legislativo/prd.md): RF01, RF03, RF04, RN02–RN05 e CA11.
- Aplicação: repositório `banco-de-contatos-mailing`, branch `legislativo-entrega-1`; referência inspecionada `45ec73e`.
- Homologação: Carteira (`/legislativo/carteira`) e a ficha indicada pelo Erick, no alias de Preview da branch `legislativo-entrega-1` (URL fora do repositório público).

Este plano termina com entrega e aceite em homologação. Não inclui merge em `main`, publicação Production, virada de consumidores, migração de decisões, importação da planilha, alterações em n8n/Power BI ou atualização do plano de produção.

## Decisões de implementação

### Edição e diferenças

1. Consulta é o estado inicial. Só usuários com `legislativo_editar` recebem os controles; toda leitura do editor e gravação verifica identidade/autorização no servidor. Projetos a conferir não podem ser editados.
2. **Modo edição** na Carteira habilita **Editar decisões** por projeto. Um formulário se expande sob a linha; apenas um projeto fica aberto por vez. Na ficha, o mesmo editor substitui as decisões em texto após clicar em **Modo edição**.
3. Campos: relevância, posição, prioridade, ação, parecer e observações. Dados oficiais permanecem em leitura; decisões pertencem ao projeto agrupado, não a uma casa isolada.
4. Base é o estado salvo e sua revisão obtidos ao abrir o editor. Diferenças são calculadas contra essa base, nunca por foco ou por histórico de teclas. Cada diferença recebe fundo/borda, etiqueta **Alterado** e **Antes: valor**; resumo mostra quantidade e nomes. A restauração do valor original remove todas as indicações.
5. Normalizar vazio na fronteira do formulário como o `btrim(texto)` SQL existente: string vazia ou composta somente de espaços U+0020 vira `null`; preservar integralmente conteúdo não vazio. Não usar `String.trim()` como equivalente: tabs, quebras de linha e NBSP isolados não são removidos pelo `btrim` padrão. Testar explicitamente esses casos. Relevância pendente e prioridade não informada são `null`; prioridade NÃO é `false`, nunca `null`. Respeitar os limites existentes: ação 20 mil, parecer/observações 50 mil caracteres. Comparação, patch, contador e rascunho usam a mesma normalização.
6. **Concluir edição** grava todas as diferenças numa chamada a `salvarProjeto` → `gestao.salvar_decisao`. Sem diferenças, permanece desabilitado. Durante envio, bloquear controles e novas ações; erro preserva rascunho, destaques e resumo. Somente sucesso confirmado fecha e limpa a edição.
7. **Cancelar** sem diferenças fecha; com diferenças mostra campos e valores a descartar e oferece **Continuar editando** ou **Descartar alterações**. Não gera escrita nem auditoria. Trocar projeto ou sair com diferenças exige escolha equivalente. Bloquear filtros, abas, paginação e ordenação enquanto o editor estiver aberto, com explicação curta; navegação do browser/recarregamento deve preservar rascunho ou acionar a proteção disponível, sem prometer um modal customizado em todos os casos.
8. Preservar confirmações de prioridade/relevância e resolução de concorrência. Depois de mesclar, a versão atual vira a base e os destaques são recalculados; ainda é necessário concluir. Confirmar regra dependente aplica e grava os campos conjuntos na mesma transação. Na retirada de prioridade ao marcar NÃO, enviar também `retirar_prioridade: true`, inclusive se `prioridade: false` já constar no patch. Na ativação, confirmar relevância SIM e prioridade true juntas. Após mescla, reavaliar a confirmação contra a nova base; não reutilizar confirmação baseada numa revisão anterior. Cancelar a confirmação não grava.
9. A confirmação de movimentações continua independente: disponível na ficha fora do modo edição; confirmar um movimento não salva nem apaga rascunho de decisão.

### Hierarquia, filtros e preferências

- Linhas urgentes: vermelho suave e motivo visível. Prioridades: âmbar. Sem nenhuma decisão: azul. Precedência da cor: urgente → sem decisões → prioridade → neutra. Etiquetas permanecem ao desligar destaques.
- Coluna **Decisões ABCS** mostra a posição com etiqueta, **Sem posição** quando há outros registros, ou **Sem decisões ABCS** quando todos os seis campos estão ausentes. NÃO e `false` são decisões válidas; ação/parecer/observações preenchidos também contam. Ausência de posição sozinha não significa ausência de decisão.
- A cor, os filtros e a ordem refletem somente dados salvos. Rascunho não muda a posição da linha. Não mover pendências da Avaliação para a Carteira para preencher a demonstração.
- Filtros rápidos: Todas, Urgentes, Prioridades e Sem decisões ABCS. São recortes sobre a aba, busca e filtros atuais; urgentes entram também em Prioridades. Os números não são somáveis.
- Usar parâmetros de URL `foco=todas|urgentes|prioridades|sem_decisoes` e `ordem=atencao|movimentacao|identificacao`. Ausência de foco equivale a todas. Preservar `ordem=identificacao` já existente e links `urgente=sim` do Início. Foco explícito válido sempre vence `urgente=sim`: na canonicalização, remover `urgente` se houver `foco` válido, inclusive `foco=todas`. Valor de foco inválido não vence o legado; aplicar o fallback de validação e canonicalizar a URL. Somente na ausência de foco interpretar `urgente=sim` como foco Urgentes e refletir essa seleção. Clicar num filtro rápido remove o parâmetro legado para não manter uma interseção invisível. Lista, contagens e CSV usam o mesmo resultado canônico; testar URLs contendo ambos.
- Ordenação padrão **Atenção primeiro**: urgentes → sem decisões → prioridades → demais, depois última movimentação DESC NULLS LAST e chave estável. **Última movimentação** usa só data e desempate estável: remover o `p.urgente DESC` incondicional atual nesse modo. Identificação continua como alternativa compatível.
- Contagens rápidas: aba + busca + filtros comuns, ignorando apenas `foco` (e sua representação legada). Total paginável e totais de abas: incluir o foco selecionado. CSV: mesmo predicado e ordem da lista, sem LIMIT/OFFSET; continuar sem parecer e observações. Calcular tudo antes da paginação no servidor.
- **Personalizar**: três opções de destaque, ordem e restaurar padrão. Persistir preferências visuais sem dados internos em chave versionada por ambiente e usuário. Armazenamento inválido/bloqueado usa padrão. A URL explícita vence a preferência de ordem; sem ordem explícita, resolver a preferência e refletir na URL antes de consultar o recorte definitivo. CSV e paginação recebem a mesma ordem resolvida. Evitar diferenças de hidratação: estado inicial determinístico e resolução da preferência antes de apresentar a lista como definitiva.
- Mudanças no menu Personalizar não modificam decisões nem urgência. Preferências não sincronizam entre usuários/navegadores. Rascunho usa sessão, namespace por ambiente/usuário/projeto; não migrar automaticamente chaves antigas sem autoria para o novo namespace.

## Arquitetura e mapa de arquivos

Não há migração de banco prevista. Reutilizar `contrato.vw_projeto` e a escrita transacional existente; alterações de SQL são consultas parametrizadas na camada de dados da aplicação. Se faltar contrato, registrar a lacuna e revisar o plano antes de propor migração remota.

| Arquivo na aplicação | Mudança |
|---|---|
| `lib/schemas/legislativo.ts`, `lib/legislativo/conflito.ts` | Normalização compartilhada, rótulos e comparação dos seis campos; manter domínio existente |
| Novo `lib/legislativo/carteira.ts` | Tipos/seleção de cor, rótulos e preferências; regras operacionais continuam no contrato SQL |
| `lib/filters/legislativo.ts` | Foco, nova ordem, compatibilidade de links e serialização canônica |
| `lib/dados/legislativo/carteira.ts` | Predicado compartilhado, flag `sem_decisoes`, contagens, ordenação e paginação no servidor |
| `lib/dados/legislativo/tipos.ts` | Separar DTO da linha do snapshot completo do editor |
| `lib/dados/legislativo/projeto.ts` | Consulta enxuta do snapshot de decisão atual, identidade canônica e revisão |
| `lib/dados/legislativo/escritas.ts` | Tipar retorno específico de `salvarDecisao` com os seis campos canônicos já retornados pelo SQL, UUID, revisão, indicador de alteração e auditoria |
| `app/(app)/legislativo/actions.ts` | Carregar snapshot autorizado; repassar retorno canônico atômico no sucesso e consultar a versão atual somente no conflito |
| Novo `app/(app)/legislativo/_components/editor-decisao.tsx` | Editor compartilhado, diferenças, rascunho e estados; interfaces por callbacks para Carteira/ficha |
| Novos componentes de consulta/diferenças/preferências em `_components/` | Valores, destaque por campo, confirmação de descarte e menu Personalizar |
| `carteira/page.tsx`, `carteira/tabela.tsx` | Permissão, filtros rápidos, expansão, cores e contexto de edição |
| `projeto/[id]/page.tsx`, `projeto/[id]/editor.tsx` | Consulta inicial e integração do editor extraído; remover duplicação |
| `app/api/legislativo/carteira/route.ts` | Consumir filtro/ordem canônicos existentes na mesma camada de dados |
| Testes Vitest e `tests/legislativo/ca11.spec.ts` | Regressões de domínio, consultas e jornada de edição |

A tabela genérica `components/dados/tabela-dados.tsx` ainda não permite cor de linha/expansão. Acrescentar pontos opcionais `classeLinha` e `renderizarExpansao`, com defaults que preservem seus outros consumidores. Expansão desktop usa uma segunda linha, célula com colspan correto e sem elementos inválidos no tbody; renderização estreita usa bloco abaixo do item. Montar apenas uma instância do editor, mesmo quando a tabela e os cartões coexistirem no DOM. IDs, campos, rascunhos e chamadas não podem se duplicar. Não copiar a tabela inteira nem alterar o comportamento do mailing.

A listagem não precisa receber parecer/observações para decidir o destaque: selecionar colunas explícitas e calcular `sem_decisoes` no servidor com uma única expressão SQL reutilizada em seleção, filtro, contagens e ORDER BY. Exemplo semântico: relevância/posição/prioridade nulas e textos nulos ou vazios segundo normalização do banco. Definir DTO da lista com o mínimo já usado pela tela/CSV; snapshot completo somente ao abrir editor autorizado. Nenhuma nova exposição na projeção pública `api`.

## Execução sequencial

### Tarefa 1 — Preparar baseline e conferir destino

- [ ] Ler `AGENTS.md`, `CLAUDE.md`, decisões e runbook do repo da aplicação. Consultar documentação Next instalada antes de escrever código de sessão/cache/ações.
- [ ] Conferir HEAD e alterações locais; trabalhar em checkout/worktree isolado baseado na ponta atual de `legislativo-entrega-1`. A referência `45ec73e` é contexto, não instrução para reset. Não misturar alterações locais de outros trabalhos.
- [ ] Registrar commit e deployment imutável do preview atual para reversão. Verificar que o alias informado pertence à branch de homologação.
- [ ] Conferir, sem imprimir valores secretos, o vínculo Preview das variáveis: Auth/capacidades da plataforma em homologação e `LEGISLATIVO_DATABASE_URL` no banco legislativo de homologação. São dois projetos diferentes. Referência documental do legislativo: projeto de homologação em sa-east-1 (ref no `src/.env`); confirmar no ambiente real antes de qualquer escrita. Não confundir com banco da plataforma nem copiar variáveis Production.
- [ ] Registrar a proteção de acesso do preview e duas contas de teste (editor/leitor). Não criar ou alterar capacidade em produção.
- [ ] Executar baseline de lint, typecheck e Vitest; registrar falhas anteriores separadamente. Confirmar harness sintético CA11 e porta/variáveis locais necessárias.

**Saída:** baseline, destino e comando de testes registrados; sem mudança em banco remoto.

### Tarefa 2 — Formalizar dados de lista e consultas

- [ ] Definir DTO mínimo da lista e snapshot completo do editor, mantendo UUID canônico, ID de proposição, agrupamento e revisão.
- [ ] Implementar foco/ordem na URL e compatibilidade com links existentes. Toda mudança de filtro ou ordem volta à página 1.
- [ ] Construir base de filtros comuns, foco e expressão `sem_decisoes` uma única vez na camada server-only. Consulta de linhas, contagem filtrada, contagens rápidas e exportação reutilizam essas peças.
- [ ] Aplicar ordenação SQL antes de LIMIT/OFFSET com desempate estável; não ordenar/filtrar só os registros recebidos pelo componente cliente.
- [ ] Testar categorias, contagens, ordenação em pelo menos duas páginas e paridade CSV. A UI recebe flag de ausência; não recebe textos internos só para classificar a linha.

**Saída:** consultas e testes locais aprovados, sem migração.

### Tarefa 3 — Extrair o editor e estabilizar a base

- [ ] Extrair o formulário existente preservando confirmações, conflitos e validações; reutilizar `alteracoesDecisao`, `mesclarDecisao` e schema.
- [ ] Implementar leitura autorizada e enxuta ao abrir edição. Enquanto carrega, mostrar status; falha permite tentar novamente sem abrir formulário vazio. Abandonar respostas de abertura antigas ao trocar projeto.
- [ ] Modelar estados: consulta, carregando, editando sem diferenças, editando com diferenças, enviando, erro e conflito. Derivar diferenças da comparação normalizada, sem manter uma segunda lista manual de campos sujos.
- [ ] Usar diretamente o retorno atômico que `gestao.salvar_decisao` já fornece (`sql/schema_contratos.sql:721–735`): seis campos canônicos, UUID, revisão, `alterado`, `criado`, diferenças e histórico. Tipar esse resultado em `escritas.ts` e repassá-lo em `salvarProjeto`; não estabelecer releitura pós-commit como base nem usar os dados enviados como se fossem o valor persistido. Consultar estado atual apenas ao abrir ou resolver conflito; a próxima abertura relê o servidor.
- [ ] Usar retorno canônico para resolver UUID criado na primeira decisão e limpar rascunhos nos identificadores antigo/canônico; preservar navegação por alias existente.

**Saída:** editor único com base e revisão corretas, utilizável nas duas telas.

### Tarefa 4 — Implementar diferenças, descarte e proteção de saída

- [ ] Destacar somente campos diferentes: etiqueta, valor anterior integral consultável, resumo por nomes/quantidade e mensagens acessíveis. Textos longos não podem estourar a largura.
- [ ] Implementar Concluir edição/Cancelar, confirmação de descarte, retorno ao original, falha preservando dados, bloqueio durante envio e foco após fechar/restaurar.
- [ ] Manter rascunho por usuário/projeto/ambiente na sessão. Ao reabrir com rascunho, informar a restauração; comparar a revisão salva com a atual e passar pelo fluxo de conflito quando divergente. Limpar no sucesso e descarte; usuário diferente não restaura conteúdo anterior.
- [ ] Proteger links internos, mudança de projeto, voltar/avançar, recarregar e fechar. Quando não for possível interceptar a navegação do browser, o rascunho deve ser recuperável; testar o comportamento real, sem depender só de interceptação de cliques em `<a>`.
- [ ] Recalcular diferenças depois de resolução de conflito e de confirmação de relevância/prioridade. Não reaproveitar revisão antiga silenciosamente.

**Saída:** nenhuma perda silenciosa nem gravação no cancelamento.

### Tarefa 5 — Integrar Carteira e ficha

- [ ] Levar permissão do servidor à Carteira e implementar Modo edição/Editar decisões, expansão única e carregamento do snapshot atual.
- [ ] Adicionar pontos opcionais à tabela genérica, verificar HTML válido, foco, colspan e regressão dos outros consumidores. Tela estreita não monta outro editor simultaneamente.
- [ ] Bloquear controles de recorte/paginação enquanto editor aberto; manter identificação/ementa visíveis. Trocar projeto com diferenças passa pelo descarte explícito.
- [ ] Após salvar, revalidar o layout legislativo como hoje, fechar editor e atualizar linha/totais/histórico. Preservar filtros e ordem; se a linha sair do recorte, informar o fato em mensagem persistente à atualização. Se página ficar vazia, ajustar para a última página válida.
- [ ] Na ficha, texto no estado inicial, botão Modo edição e mesmo editor; confirmar movimentos continua funcional com ou sem edição aberta e não confirma/salva decisões implicitamente.

**Saída:** fluxo aprovado reproduzido nas duas telas.

### Tarefa 6 — Aplicar destaques e personalização

- [ ] Aplicar classes/tokens para urgência, prioridade, ausência de decisão e posição institucional; respeitar tema claro/escuro e hover. Não depender somente de cor.
- [ ] Implementar filtros rápidos com totais globais do recorte e estados de seleção acessíveis. Foco escolhido fica na URL e na exportação.
- [ ] Implementar Personalizar, restauração, isolamento por usuário e fallback de armazenamento. Manter a ordem resolvida coerente entre lista, paginação, URL e CSV, inclusive após reload.
- [ ] Verificar visualmente em desktop 1366 e 1600 px, zoom 200% e largura estreita para detectar perda de conteúdo. Verificar contraste dos elementos novos, foco e rolagem; não transportar os avisos de texto pequeno/contraste do HTML de demonstração para a implementação.

**Saída:** aparência do mockup com comportamento real consistente.

### Tarefa 7 — Validação automatizada e evidências

No checkout da aplicação, executar os scripts existentes: `npm run lint`, `npm run typecheck`, `npm run test`, `npm run build`. Rodar `npm run db:test` no Supabase local e atualizar CA11 em PostgreSQL legislativo sintético local; a suíte CA11 existente rejeita banco remoto e não deve ser apontada à homologação. Preparar massa via rotinas de teste já existentes, nunca resetar banco remoto.

- [ ] Vitest: normalização/triestado/diferenças (incluindo U+0020, tabs, quebras e NBSP), retorno canônico, mescla, classificação da ausência de decisão, regras visuais, foco/ordem, preferências válidas/inválidas e compatibilidade da URL.
- [ ] Testes da camada de dados: mesma seleção para linhas/totais/CSV; primeira/segunda página; empates; prioridade antiga/sem data; texto só com espaços; `false` como decisão; filtros por casa/órgão preservados; sem textos privados no DTO da lista.
- [ ] CA11 ampliado: consulta inicial, abrir editor, alterar seis campos, voltar ao original, concluir/reabrir, cancelar/continuar/descartar, erros, concorrência e mescla, confirmação e cancelamento das duas direções de prioridade/relevância (incluindo `retirar_prioridade: true`, mescla e nova confirmação), controle de acesso e revogação, confirmação de movimentos independente, saída/restauração de rascunho e ajuste de recorte/página.
- [ ] Leitor: sem controles; chamada direta de leitura do editor/gravação sem capacidade recusada. Editor: snapshots não ficam em cache compartilhado nem logs com conteúdo interno.
- [ ] Regressões da tabela genérica no mailing, exportação sem parecer/observações, UI claro/escuro e teclado; capturas usam dados sintéticos.

**Saída:** comandos, resultados, SHA e capturas registrados no relatório da entrega. Falha nova impede publicação do preview de aceite.

### Tarefa 8 — Publicar somente o preview de homologação

- [ ] Revisar diff e criar commits focados em português. Se usado ramo auxiliar, integrar somente na branch `legislativo-entrega-1` após checks; verificar avanço remoto antes do push e resolver divergências preservando trabalho alheio.
- [ ] Conferir os destinos de push: o origin da aplicação tem dois destinos documentados. Publicar a branch de homologação segundo a configuração existente, verificando o resultado nos destinos; não fazer push de `main` nem usar force push.
- [ ] Aguardar o deployment Preview e registrar SHA, URL imutável e resultado do build. Confirmar que o alias da homologação aponta para esse SHA; não usar deploy Production nem promover preview.
- [ ] Conferir novamente credenciais de Preview e proteção de acesso. Smoke autenticado: Carteira, ficha indicada, Personalizar e CSV. Credenciais e textos internos não entram no relatório.
- [ ] Exercitar gravações manuais só em projetos de teste identificados na homologação, após registrar valores anteriores e revisão. Não importar a massa fictícia do mockup para o banco remoto. Se for necessário restaurar os testes, usar nova edição auditada e revisão atual, nunca UPDATE direto ou restauração integral do banco.

**Saída:** preview correto publicado e smoke concluído; produção preservada.

### Tarefa 9 — Aceite em homologação e encerramento

- [ ] Ana/Erick identificam visualmente uma urgente, uma prioridade e um projeto sem decisão, entendendo a diferença para Sem posição. Se algum cenário não existir no banco remoto, registrar a ausência e usar a evidência sintética local, sem fabricar estado em um projeto real.
- [ ] Ativar edição, alterar posição/ação/prioridade, identificar campos e valores anteriores, cancelar e depois concluir uma edição de teste. Conferir autor/data/diferenças no histórico.
- [ ] Personalizar cores, recarregar, mudar ordem e filtrar uma categoria; conferir contagem e CSV. Verificar perfil leitor e restauração de rascunho.
- [ ] Registrar aprovado/ajustes por critério, URL e SHA. Capturas de dados internos de homologação ficam em local privado, nunca no repositório público.
- [ ] Atualizar o contrato funcional com decisões de implementação aceitas. A implantação em produção permanece uma etapa posterior, fora deste plano.

## Matriz de aceite resumida

| Caso | Resultado obrigatório |
|---|---|
| Campo alterado/restaurado | Marca/limpa destaque, Antes e resumo imediatamente |
| Cancelar | Escolha explícita; sem gravação; descarte limpa somente o rascunho daquele projeto/usuário |
| Concluir | Um patch, revisão validada, auditoria coerente, base canônica e atualização do recorte |
| Erro ou conflito | Rascunho intacto; sem sobrescrita silenciosa; nova comparação após escolha |
| Prioridade/relevância | Confirmações existentes e gravação atômica preservadas |
| Permissão removida | Próximo pedido ao servidor recusa gravação, mesmo com editor aberto |
| Atenção e ausência | Mesmas regras no servidor para cor, filtro, contagem e ordenação; rascunho não reordena |
| CSV/paginação | Recorte global coerente; ordem estável; textos privados ausentes do CSV |
| Preferências/rascunhos | Isolados por usuário/ambiente; sem duplicação do editor nem vazamento entre contas |
| Voltar/recarregar | Proteção ou recuperação explícita, sem perda silenciosa |
| Publicação | Apenas Preview da branch de homologação; SHA e destino verificados |

## Reversão em homologação

Se o smoke apresentar regressão, voltar o alias de Preview para o deployment imutável registrado na Tarefa 1, sem promover nada para Production. Registrar SHA/URL antes/depois e verificar acesso. Se o provedor não permitir reatribuição do alias nesse fluxo, publicar um novo commit de reversão dos commits desta entrega na própria branch de homologação, preservando commits alheios. O código anterior usa os mesmos schemas e funções; decisões já salvas e auditoria permanecem. Preferências versionadas novas podem ser ignoradas pelo código antigo; não apagar dados de decisão nem restaurar o banco. Registrar limitações de rascunhos novos ao retornar à interface anterior.

## Revisão Astra

Solicitação: revisar este plano contra o contrato funcional, mockup e código `legislativo-entrega-1`, com foco em lacunas executáveis, autorização, concorrência, normalização, filtros/contagens/CSV, isolamento de rascunhos, tabela compartilhada e publicação exclusiva de homologação. A revisão não executa implementação nem deploy.

Resultado: revisão somente leitura concluída pelo **Astra (`gpt-6-astra`)**, comparando este plano, contrato, mockup, aplicação na branch `legislativo-entrega-1` e SQL. Parecer: plano pronto para execução após os quatro ajustes abaixo; sem necessidade identificada de migração nem de mudança em produção.

| Prioridade | Achado | Correção incorporada |
|---|---|---|
| P1 | Releitura pós-commit não representa necessariamente a gravação e pode falhar depois de salvar | Tarefa 3 e mapa de arquivos agora exigem retorno tipado dos seis campos canônicos, UUID/revisão/auditoria já devolvidos atomicamente por `gestao.salvar_decisao`; releitura apenas para abertura/conflito e atualização de lista |
| P2 | `.trim()` do mockup diverge do `btrim` SQL | Regra de normalização especifica somente U+0020, preserva conteúdo não vazio e pede fixtures para tabs, quebras e NBSP; implementar a mesma semântica na flag de ausência |
| P2 | URL com `foco` e `urgente=sim` podia manter interseção invisível | Foco explícito válido vence; canonicalização remove legado; testes cobrem lista, contagens e CSV |
| P2 | Confirmação RN05 precisava explicitar marcador e nova avaliação após mescla | `retirar_prioridade: true` obrigatório ao confirmar retirada, mesmo com `prioridade: false`; testes de confirmar/cancelar nas duas direções e reavaliação contra nova base |

Todos os quatro achados foram incorporados nesta versão. A revisão não executou testes da aplicação, alterações remotas ou publicação. O executor ainda deve cumprir os checks e registrar evidências de cada tarefa; a revisão do plano não é aceite do código futuro.


## Registro de execução — layout implementado em 30/10/2026

- Aplicação: checkout isolado, branch `legislativo-entrega-1`, base `45ec73e`.
- Commits enviados aos dois destinos Git configurados: `f9d3baf` (implementação, testes e capturas) e `75de287` (canonicalização de foco inválido e registro de validação).
- Entregues: editor compartilhado Carteira/ficha com consulta inicial, diferenças por campo, conclusão/cancelamento, rascunhos isolados, resolução de conflito e confirmações; linhas de atenção, cinco posições institucionais, filtros/ordem/CSV no servidor e preferências visuais.
- A expansão conserva a mesma instância em todas as larguras; testes incluem resize durante envio com armazenamento bloqueado, navegação durante gravação e permissão revogada.
- Validação: format, lint e tipos passaram; 327 testes unitários; 7 testes SQL reais de recorte/paginação/CSV; 190 pgTAP; 11 CA11 na bateria completa e mais 1 regressão de URL executada isoladamente. Cobertura: 96,35% de linhas.
- Build de produção aprovado com `npm run build -- --webpack`. O Turbopack encontrou restrição de porta interna no ambiente; configuração e dependências não foram alteradas.
- Capturas sintéticas e relatório versionados na aplicação: `docs/legislativo-layout-homologacao.md` e `docs/legislativo-layout-evidencias/`. Verificadas larguras 1366, 1600 e 390 px, claro/escuro e viewport equivalente a zoom 200%; sem overflow horizontal em 390 px.
- Supabase de teste isolado `layout-legislativo`, portas 55321/55322; nenhuma escrita em banco remoto, migração ou mudança em produção.
- Vercel publicou o Preview principal e a proteção por Vercel Authentication foi confirmada. Alias de acesso: Preview da branch `legislativo-entrega-1` (URL fora do repositório público).
- **Pendente:** smoke autenticado remoto (a sessão disponível não possui autenticação Vercel), conferência remota das variáveis de Preview e aceite visual/funcional da Ana/Erick. Esses itens não foram marcados como concluídos por testes locais. Produção e liberação à Ana continuam fora desta entrega.

Deployment final confirmado pelo status Vercel do SHA `75de2873916828514ac88b05e65efc36c1f92f06`: **success / Deployment has completed**.
