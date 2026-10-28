# Avaliação sistemática do mockup legislativo ABCS

Data: 28/10/2026.

Revisão consolidada pelo Codex, com avaliação independente do GPT-6 Astra, solicitada pelo Erick.

## 1. Escopo, fontes e método

Foram examinadas as versões locais mais recentes, datadas de 28/10/2026, dos seguintes arquivos:

- [PRD](../prd.md).
- [Plano de implementação](../plano.md).
- [Mockup navegável](legislativo-mockup.html).

A análise abrangeu os documentos, todo o código do mockup e a execução isolada de funções JavaScript para verificar casos críticos. A identidade visual foi comparada, em código, com os estilos e componentes da plataforma existente em `banco-de-contatos-mailing`.

**Limitações:** não havia navegador conectado disponível. Aparência renderizada, contraste, comportamento em diferentes resoluções e navegação real por teclado permanecem pendentes. Esta avaliação não equivale a uma auditoria visual concluída nem certifica acessibilidade. As referências a linhas correspondem ao arquivo examinado nesta data e podem mudar em revisões posteriores.

Nenhum arquivo de implementação, PRD ou plano foi alterado durante a avaliação. Este documento registra os achados e as recomendações; não autoriza deploy nem alterações de produção.

## 2. Parecer geral

**O mockup é uma boa base para discussão, mas precisa de correções antes da aprovação.** Os principais problemas estão na segurança das decisões, na preservação da identidade dos projetos e em percursos que aparecem na interface, mas ainda não podem ser concluídos.

As decisões mais recentes tornam a Entrega 1 objetiva: substituir o trabalho da Ana na planilha, mantendo as consultas de pautas, audiências e autoria no Power BI.

| Decisão dos documentos | Situação no mockup |
|---|---|
| Entrega 1 com edição e filas nativas; consultas complementares no Power BI | Parcial: o Início já apresenta pautas nativas |
| Ana como única editora inicial; equipe consulta | Representado pelos dois perfis do simulador |
| Prioridade exige relevância SIM, com confirmação das transições | Há erro na confirmação de NÃO |
| Urgência por movimentação maior ou pauta, com baseline | Parcial: ativar prioridade pode gerar urgência retroativa |
| Decisões preservadas diante de concorrência e mudanças de agrupamento | Há falhas nos dois cenários |
| Inclusão retomável e sem duplicação | Estados existem, mas identidade e retomada precisam melhorar |
| Power BI inserido na página | Há apenas um espaço reservado |
| Uso em computador | Compatível com o foco proposto; celular permanece fora do escopo |

### Escolhas a preservar

- Decisões em campos separados: relevância, posição, prioridade, ação, parecer e observações.
- Prioridade com três estados, preservando ausência de informação.
- Motivos de urgência explícitos.
- Histórico com diferenças entre valores.
- Distinção entre disponibilidade dos dados e envio de e-mail.
- Simuladores de falhas e perfis.
- Confirmação por IDs dos movimentos apresentados, deixando uma ocorrência concorrente pendente.

### Prioridades adotadas

- **P1 — Alta:** corrigir antes de aprovar os fluxos centrais do mockup.
- **P2 — Média:** completar os percursos e reduzir ambiguidade antes da construção.
- **Validação pendente:** exige navegador ou esclarecimento dos documentos.

As prioridades se referem ao aceite do protótipo. Não implicam que os problemas estejam presentes em um sistema de produção.

## 3. Decisões e concorrência

Referência principal: [edição e salvamento](legislativo-mockup.html#L698). Requisitos relacionados: RF04, RN05 e CA02 do PRD.

### 3.1. [P1] Marcar NÃO em uma prioridade oferece a confirmação errada

Ao mudar a relevância de um projeto prioritário para NÃO, aparece “Marcar SIM e prioridade”. A condição que exige SIM é executada antes da condição de retirada da prioridade.

**Evidência:** comportamento reproduzido executando as funções do mockup. No projeto PL 2417/2024, mudar somente a relevância para NÃO abre a confirmação para voltar a SIM.

**Impacto:** a interface propõe desfazer a intenção da usuária e contraria a transição prevista na RN05.

**Recomendação:** resolver a transição pretendida antes de aplicar a coerência dos campos. A confirmação deve explicar “Marcar como NÃO e retirar a prioridade?”, incluindo o efeito sobre carteira e alertas. Cancelar não deve alterar os dados persistidos.

### 3.2. [P1] O conflito de versão não bloqueia efetivamente a sobrescrita

A versão inicial é guardada em `versaoBase`, mas não é comparada ao salvar. Depois do aviso de concorrência, clicar novamente no botão comum “Salvar decisões” permite gravar sem escolher uma resolução.

**Evidência:** foram reproduzidos dois casos nas funções isoladas:

1. Alteração da versão e de um campo do projeto antes do salvamento: o rascunho é gravado sobre o valor alterado sem conflito efetivo.
2. Primeiro salvamento com concorrência simulada: o aviso aparece; um segundo clique no salvamento comum permite gravar sem resolver explicitamente o conflito.

**Recomendação:** comparar a versão de referência e manter o conflito bloqueante até a decisão explícita. Se houver outra alteração depois da resolução, apresentar um novo aviso.

### 3.3. [P1] “Salvar o meu por cima” precisa mostrar o alcance da substituição

Todos os campos do rascunho são gravados. Isso pode restaurar um valor antigo em um campo que a Ana não pretendia alterar.

**Recomendação:** mostrar as diferenças relevantes e usar a versão atual como referência para a decisão explícita de sobrescrita. Não apresentar o conflito como resolvido somente porque a usuária voltou a clicar em salvar.

### 3.4. [P1] Trocar de projeto pode descartar alterações sem aviso

Existe um único `draft`, substituído ao abrir outro projeto (`vProjeto`, linha 624). Não há proteção para alterações não salvas.

**Recomendação:** oferecer opções claras para continuar editando ou descartar antes da troca que perderia o rascunho. Não é necessário criar um sistema complexo de rascunhos.

**Ressalva da revisão:** foi descartada a hipótese de que apenas confirmar movimentos ou usar o simulador apaga a digitação normal dos campos de decisão. Os handlers de `oninput` já atualizam o rascunho antes do redesenho da tela.

## 4. Urgência, confirmação e encerramento

Referência principal: regras nas linhas 383–399 do [mockup](legislativo-mockup.html). Requisitos relacionados: RF09, RN06, RN07, CA04, CA05 e CA06.

### 4.1. [P1] Ativar prioridade gera urgência por movimento anterior

No exemplo PL 3102/2025 (`p04`), marcar prioridade SIM gera urgência por uma movimentação que já existia. `naoConf` considera todo movimento maior não confirmado, sem baseline de ativação.

**Evidência:** caso reproduzido nas funções isoladas.

**Recomendação:** distinguir movimentos anteriores à prioridade daqueles recebidos depois. Representar o baseline no estado fictício, sem converter o histórico anterior em nova urgência.

### 4.2. [P1] Uma remessa histórica pode impedir o encerramento para sempre

A regra `encerrado` considera que qualquer indicação de remessa impede encerrar o projeto. Mesmo quando todas as versões terminarem, uma remessa antiga pode mantê-lo ativo.

**Evidência:** consequência lógica sob cenário sintético: encerrar todas as versões de `p02`, mantendo o registro de remessa da Câmara, resulta em `encerrado = false`. Esse não é o estado atual exibido pela fixture.

**Recomendação:** distinguir remessa com destino ainda desconhecido de remessa cujo destino já foi carregado e encerrado.

### 4.3. [P2] A confirmação começa com todos os movimentos selecionados

Isso facilita o trabalho, mas aumenta a possibilidade de confirmar itens sem examiná-los.

**Recomendação:** validar com a Ana a preferência entre seleção explícita e uma ação “Selecionar todos os apresentados”. Em ambos os casos, deixar claro o conjunto confirmado e preservar o efeito compartilhado e auditado.

### 4.4. [P2] Faltam cenários essenciais no simulador

Adicionar cenários de:

- Ativação de prioridade com movimentos antigos.
- Cancelamento e reagendamento de pauta.
- Encerramento da versão de destino após remessa.

São situações diretamente relacionadas ao aceite, sem ampliação de escopo.

**Preservar:** confirmar apenas os IDs apresentados e manter pendente um movimento recebido durante a confirmação. A pauta na janela deve continuar causando urgência após a confirmação dos movimentos.

## 5. Avaliação em sequência

Referência principal: fila nas linhas 514–543 do [mockup](legislativo-mockup.html). Requisitos relacionados: RF02, RN03 e CA11.

A avaliação na própria linha atende bem à rotina descrita. As lacunas estão na continuidade e na recuperação.

### 5.1. [P2] Enter não abre o detalhe

O atalho apenas mostra uma mensagem.

**Recomendação:** oferecer um percurso navegável para analisar a pendência antes de decidir, inclusive quando ela ainda não tem UUID. Não criar UUID prematuramente só para tornar o detalhe acessível.

### 5.2. [P2] Voltar a relevância para pendente não devolve o projeto à fila

`S.pendentes` e os projetos são armazenados separadamente, permitindo inconsistência entre a decisão e a fila.

**Recomendação:** manter a fila coerente com o estado efetivo de avaliação, inclusive após edição pelo detalhe.

### 5.3. [P2] “Desfazer” pode afetar a avaliação errada

Os avisos consultam a mesma variável global. Após duas avaliações rápidas, o primeiro aviso pode desfazer a segunda operação.

**Recomendação:** vincular cada desfazer à operação correspondente. A recuperação não deve afetar silenciosamente decisões posteriores.

### 5.4. [P2] Os atalhos precisam respeitar o contexto

**Recomendação:** ignorar combinações com Ctrl/Alt/Meta e conferir que seleção visual, foco e rolagem permaneçam coerentes. O comportamento real depende de validação no navegador.

### 5.5. [P2] O texto confunde relevância e acompanhamento

“SIM para acompanhar” aproxima conceitos que o PRD distingue: relevância, acompanhamento operacional e posição institucional “Acompanhar”.

**Recomendação:** usar “SIM para marcar como relevante” e manter essa terminologia consistente nas demais telas.

## 6. Carteira e conferência

Referência principal: carteira nas linhas 546–616 e conferência nas linhas 809–814 do [mockup](legislativo-mockup.html). Requisitos relacionados: RF03, RN03, RN06, RN07, CA04, CA05 e CA14.

### 6.1. [P2] Filtros ficam somente na memória

O texto promete preservação no endereço, mas a implementação não a realiza.

**Recomendação:** permitir voltar pelo navegador ou recarregar mantendo aba e filtros. O recorte usado na exportação deve corresponder à lista exibida.

### 6.2. [P2] A busca global consulta somente Ativas

Um projeto conhecido pode parecer inexistente por estar encerrado, marcado NÃO ou fora do corte.

**Recomendação:** alcançar esses estados ou indicar claramente o universo pesquisado e oferecer acesso aos demais resultados.

### 6.3. [P2] Histórico reúne situações diferentes sem filtros suficientes

**Recomendação:** acrescentar filtros explícitos para encerrados, marcados NÃO, inativos pelo corte e sem data.

### 6.4. [P2] Ausência de movimentação vira uma data artificial

`ultimaMov` usa a época Unix como valor padrão, posteriormente formatado na tabela e na exportação.

**Recomendação:** representar ausência de data e mostrar “Sem data”. Incluir fixture sem tramitações, inclusive prioritária, para verificar o corte sem inventar datas.

### 6.5. [P2] CSV não é exportado

O botão abre uma prévia, sem baixar o arquivo.

**Recomendação:** permitir download com dados fictícios no próprio mockup. A exportação integra o roteiro de aceite da Ana e pode ser testada sem backend.

### 6.6. [P1] O exemplo de agrupamento já fundiu decisões que afirma preservar

O cenário `p14` reúne duas versões em um único objeto de projeto com decisão SIM/Contra. O texto, porém, diz que o Senado conserva uma decisão própria NÃO.

**Impacto:** o cenário não demonstra a preservação dos dois UUIDs e das duas decisões exigida pela RN03 e pelo CA14.

**Recomendação:** mostrar os dois projetos e suas decisões preservadas, ligados por uma pendência de conferência. Isso cabe na lista existente. Não criar tela de reconciliação: a resolução permanece com o mantenedor por função SQL auditada, conforme o MVP.

## 7. Inclusão manual

Referência principal: inclusão nas linhas 745–806 do [mockup](legislativo-mockup.html). Requisitos relacionados: RF08, RN06 e CA08.

### 7.1. [P2] Duplicidade verificada apenas pelo texto

Falta considerar casa e equivalência entre link oficial e identificação digitada.

**Recomendação:** simular resolução para uma identidade canônica. Link e identificação da mesma proposição devem produzir o mesmo resultado. Igual número/ano em casas diferentes não prova identidade.

### 7.2. [P2] Um pedido falho pode ser recriado

A verificação admite novo pedido quando o anterior falhou. O processamento também não representa proteção suficiente contra execuções concorrentes.

**Recomendação:** privilegiar retomada do pedido existente e garantir uma única conclusão por inclusão, mesmo com repetição da tentativa.

### 7.3. [P2] Projeto existente recebe apenas “já está no monitoramento”

Se estiver marcado NÃO ou fora da carteira, a mensagem não explica adequadamente o resultado da tentativa de inclusão.

**Recomendação:** mostrar o estado atual e oferecer uma decisão coerente com as regras de inclusão, sem reativação silenciosa nem criação de projeto duplicado.

### 7.4. [P2] Atualizações dos pedidos podem apagar o campo em digitação

Os temporizadores redesenham toda a tela enquanto outra solicitação pode estar sendo digitada.

**Recomendação:** preservar o texto da nova solicitação durante atualizações da lista. Preservar também a mensagem de pedido registrado, que atualmente é criada e logo substituída pelo redesenho.

### 7.5. [P2] A tentativa automática prometida não acontece

A mensagem anuncia nova tentativa às 15h40, mas não há agendamento correspondente no mockup.

**Recomendação:** simular a retomada ou identificar essa parte como não simulada. Não apresentar uma ação futura como garantida se ela não ocorre no percurso de teste.

### 7.6. [P2] O estado do e-mail é insuficiente

Existe apenas um indicador enviado/não enviado.

**Recomendação:** representar “aguardando”, “enviado” e “falhou”, mantendo a disponibilidade dos dados como resultado independente. Falha do e-mail não deve parecer falha da inclusão já concluída.

**Preservar:** inclusão inicial restrita à Câmara e indisponibilidade explícita do Senado, sem impedir a consulta às versões do Senado já carregadas.

## 8. Início, Power BI e frescor

Referências principais: Início nas linhas 475–509, Painéis nas linhas 818–824 e frescor nas linhas 441–451 do [mockup](legislativo-mockup.html). Requisitos relacionados: RF02, RF05–RF07, RF10, CA03 e CA10.

### 8.1. [P2] O Início precisa refletir a divisão das entregas

A lista nativa de pautas apresenta problemas independentes:

- Inclui canceladas entre as próximas.
- Usa apenas projetos da carteira ativa, excluindo elegíveis antigos com pauta futura.
- Mostra agenda do Senado enquanto o próprio sistema informa que ela ainda não é coletada.

**Recomendação:** concentrar o Início da Entrega 1 nas decisões e filas, com acesso à agenda no Power BI, conforme os documentos. Se alguma agenda nativa for mantida por decisão posterior, corrigir universo, status e capacidade efetivamente disponível.

A diferença entre 14 e 15 dias também envolve os documentos; não deve ser tratada somente como erro do mockup.

### 8.2. [P2] A página de Painéis não permite aprovar a experiência de consulta

- As abas não executam nenhuma ação.
- O relatório não está incorporado.
- A afirmação “um mockup não consegue incorporar outro site” é incorreta.
- A descrição pode dar a entender que o painel não contém informações de pautas, audiências e autores.

**Recomendação:** incorporar o relatório quando viável ou declarar precisamente o limite da simulação. Distinguir os dados oficiais consultados no painel dos campos de decisão autorizados na projeção pública. Um espaço reservado não equivale ao aceite da experiência de consulta.

O uso do link público foi decidido pelo Erick, com risco aceito. Esta avaliação não recomenda nova licença ou nova infraestrutura de BI.

### 8.3. [P2] Falta separar cache, coleta e refresh do Power BI

O PRD exige atualização do cache separada da coleta. Horário agendado também não prova que o último refresh do Power BI terminou com sucesso.

**Recomendação:** diferenciar:

- Última coleta bem-sucedida por casa/processo.
- Atualização do cache.
- Último refresh efetivamente concluído do Power BI.
- Confirmação de salvamento humano.

Falha deve preservar o último estado consistente e não parecer uma atualização bem-sucedida.

## 9. Interface e acessibilidade

As recomendações abaixo derivam da estrutura do código e precisam de conferência no navegador. Não constituem certificação de conformidade.

### 9.1. [P2] Abrir projeto não deve depender do clique na linha

**Recomendação:** transformar a identificação da tabela em link real, permitindo acesso por teclado e comportamento esperado de abertura em outra aba.

### 9.2. [P2] Completar os diálogos e as abas

**Recomendação:** incluir nome acessível para os diálogos, contenção do foco e retorno do foco ao controle que os abriu. Completar a semântica e a operação das abas por teclado.

### 9.3. [P2] Melhorar a apresentação para perfis de leitura

**Recomendação:** apresentar decisões como conteúdo legível, evitando depender exclusivamente de campos desabilitados. As informações internas continuam consultáveis pela equipe ativa, conforme a permissão definida.

### 9.4. [P2] Distinguir os dois sentidos de “versão”

**Recomendação:** usar “versões legislativas” para Câmara/Senado e “revisão da decisão” para o controle de concorrência.

### 9.5. [P2] Reduzir a interferência dos controles do protótipo

**Recomendação:** permitir recolher os controles de simulação durante o teste normal, evitando disputa com a navegação. O registro de sugestões continua sendo ferramenta do protótipo, sem se tornar requisito do produto.

### 9.6. [P2] Separar classes de estilos com propósitos distintos

O simulador e o marcador SIM usam a classe `.sim`, permitindo interferência entre estilos.

**Recomendação:** dar nomes distintos aos dois componentes e verificar o resultado renderizado.

### 9.7. Validação pendente da identidade visual

Os estilos da plataforma existente usam tipografia Geist e possuem correspondência com o verde do mockup, mas a plataforma utiliza uma base mais neutra.

**Recomendação:** reutilizar seus padrões de botões, tabelas, filtros e navegação, além das cores. Conferir densidade, legibilidade e disposição das ações nas resoluções de computador usadas pela Ana.

**Limite de evidência:** alertas automáticos de contraste sem resolução confiável dos estilos e sem inspeção renderizada não foram tratados como violações confirmadas.

## 10. Esclarecimentos necessários no PRD e no plano

Os pontos abaixo foram destacados na revisão independente do Astra. São lacunas ou ambiguidades de especificação, não defeitos de uma implementação já existente.

| Ponto | Esclarecimento necessário |
|---|---|
| Ciclo da inclusão | PRD e plano dizem projetar pedidos “concluídos” antes de disparar a carga. Distinguir resolução do ID, preparação para coleta e conclusão com dados disponíveis, evitando dependência circular ou sucesso prematuro |
| Projeção pública por versão | Explicitar a chave de ligação de cada versão; um UUID pode representar várias versões. Preservar a lista restrita de campos públicos |
| Migração de relevância | Definir quando SIM > NÃO resolve uma divergência e quando ela exige decisão da Ana |
| Estado de aprovação da projeção | A lista aparece como aprovada e também como pergunta ainda aberta |
| Janelas temporais | Unificar a descrição de 14/15 dias e definir precisamente “últimos sete dias”. O cálculo atual começa sete dias antes à meia-noite e alcança oito datas de calendário até hoje |
| Universo dos indicadores | Definir se “monitorados” significa carteira ativa ou todos os elegíveis |
| Inclusão antiga ou sem data | Explicar que inclusão não garante presença na aba Ativas, preservando o corte e a exceção de prioridade |
| Associação de versões | Distinguir associação automática inequívoca na leitura dos casos encaminhados à conferência |

As decisões resultantes do mockup devem atualizar PRD e plano e passar pelo agente revisor antes da construção, conforme o processo já previsto nesses documentos.

## 11. Ordem recomendada para a próxima revisão

1. **Corrigir decisão e concorrência:** transição para NÃO em prioridade, comparação de versão, resolução explícita e proteção das alterações não salvas.
2. **Ajustar as regras centrais:** baseline, remessa e encerramento, preservação de UUIDs e decisões nos agrupamentos.
3. **Completar as tarefas da Ana:** detalhe da pendência, desfazer correto, retorno à fila, inclusão retomável, filtros no endereço e download do CSV.
4. **Alinhar escopo e estado da informação:** Início da Entrega 1, Power BI incorporado ou limite explícito, agenda do Senado e atualização por etapa.
5. **Esclarecer os contratos documentais:** ciclo da inclusão, chave da projeção, conflitos de migração e fronteiras temporais.
6. **Validar no navegador:** identidade visual, resoluções de computador, teclado, foco, leitura, falhas e recuperação.

### Roteiro de reavaliação

- Avaliar pendências em sequência e abrir uma antes de decidir.
- Desfazer uma avaliação sem afetar outra.
- Mudar posição, ação e prioridade; salvar e conferir histórico.
- Marcar NÃO em prioridade e testar confirmação e cancelamento.
- Simular concorrência e verificar que o salvamento comum não contorna a resolução.
- Trocar de projeto com alterações não salvas.
- Ativar prioridade sem gerar urgência retroativa.
- Confirmar apenas movimentos apresentados; manter uma nova ocorrência pendente.
- Verificar urgência mantida por pauta e atualizada por cancelamento/reagendamento.
- Conferir projetos entre casas, inclusive remessa resolvida e decisões conflitantes preservadas.
- Incluir por identificação e por link, testar duplicidade, falha e retomada.
- Digitar nova inclusão enquanto outro pedido muda de estado.
- Buscar projeto fora de Ativas, preservar filtros ao navegar e exportar o recorte exibido.
- Consultar o Power BI na página e distinguir seu atraso das decisões nativas.
- Repetir os percursos de consulta com perfil de leitura.

## 12. Limites de aceite

O mockup deve comprovar os percursos e os estados da experiência. Ele não comprova autorização no servidor, privilégios SQL, segurança da projeção pública, migração sem perda, persistência após recriação de caches ou desligamento das dependências da planilha.

Essas verificações permanecem nas etapas de implementação, testes e homologação previstas no PRD e no plano. A rodada recomendada mantém o escopo decidido: computador, Power BI público na Entrega 1, reconciliação pelo mantenedor e nenhuma nova infraestrutura ou capacidade não justificada.
