# Edição de decisões diretamente na Carteira

Status: contrato funcional com mockup aprovado e [plano de implementação em homologação revisado pelo Astra](2026-10-30-legislativo-carteira-homologacao.md). Implantação em produção é etapa posterior.

## Objetivo

Permitir que a pessoa edite as decisões da ABCS sem sair da Carteira, distinguindo cada campo alterado dos demais e sabendo exatamente o que será salvo ou descartado. A ficha do projeto reutiliza o mesmo fluxo.

## Mockup para validar o comportamento

Arquivo: [legislativo-edicao-mockup.html](../monitoramento-legislativo/mockup/legislativo-edicao-mockup.html).

Derivado do mockup aprovado `legislativo-mockup.html`, preservado sem alterações. Abre na Carteira; dados e gravações são fictícios, mantidos apenas na página. Recarregar restaura os dados. Não acessa o banco nem a homologação.

Roteiro: ativar **Modo edição**, escolher **Editar decisões**, alterar posição e ação, conferir destaques e valores anteriores, então escolher **Concluir edição** ou **Cancelar**. O simulador herdado permite testar erro, concorrência e perfil de leitura.

## Contrato da experiência

- Consulta é o estado inicial. A capacidade `legislativo_editar` habilita o modo de edição; a autorização também é verificada no servidor a cada gravação.
- Na Carteira, a edição se expande sob a proposição, mostrando identificação e ementa. Apenas um projeto fica em edição por vez.
- Campos editáveis: relevância, posição, prioridade, ação, parecer e observações. Dados das fontes oficiais permanecem em leitura. A decisão é compartilhada pelas versões legislativas do projeto.
- Um campo é alterado quando seu valor difere da base carregada ao abrir o editor, seguindo a normalização do domínio. Foco, clique ou digitação seguida de retorno ao valor original não contam como alteração.
- Cada campo alterado recebe fundo e borda destacados, etiqueta textual **Alterado** e valor **Antes**. O valor novo permanece no próprio controle. A informação não depende somente de cor.
- Abaixo do formulário, mostrar a quantidade e os nomes dos campos alterados. Para textos longos, permitir consultar o valor anterior integral, com quebra de linha e rolagem.
- Ao restaurar o valor original, retirar destaque, etiqueta e valor anterior; atualizar a lista e a contagem imediatamente.
- **Concluir edição** fica desabilitado sem diferenças e enquanto houver conflito não resolvido. A ação salva todos os campos alterados daquele projeto numa única transação. Não há salvamento automático por campo.
- Ao concluir com sucesso, fechar o formulário, limpar o rascunho e os destaques, atualizar a linha, os totais e o histórico e informar o sucesso. A próxima edição parte dos valores e da revisão retornados pelo servidor.
- **Cancelar** sem alterações fecha o formulário. Com alterações, mostrar quais campos e valores serão descartados e oferecer **Continuar editando** ou **Descartar alterações**. Descartar não escreve no banco nem cria histórico e remove o rascunho.
- Mudar de projeto ou sair da tela com alterações exige a mesma decisão explícita. Durante a edição, o mockup bloqueia filtros e abas para evitar ocultar o formulário; a implementação deve preservar o recorte e explicar o bloqueio.
- Falha de gravação preserva valores, destaques e resumo para nova tentativa. Durante o envio, desabilitar campos e ações para evitar envios duplicados e alterações posteriores ao conteúdo enviado.
- Se o projeto deixar o recorte após salvar, informar o resultado antes de remover a linha. Preservar busca, filtros e página, ajustando a paginação se a página atual ficar vazia.
- Na ficha, decisões aparecem como texto até clicar em **Modo edição**. Leitores não recebem controles de edição; casos a conferir permanecem bloqueados.

## Hierarquia visual e personalização da Carteira

Ajuste solicitado após a primeira avaliação do mockup: destacar as linhas mais importantes e as proposições sem decisões da ABCS.

- Urgentes recebem fundo vermelho suave na linha inteira, etiqueta **Urgente** e motivo visível (movimentações pendentes e/ou pauta). Prioridades recebem fundo âmbar. Projetos sem nenhuma decisão recebem fundo azul e etiqueta **Sem decisões ABCS**. Demais linhas mantêm fundo neutro.
- A posição institucional aparece como etiqueta na coluna **Decisões ABCS**, com tratamento próprio para A favor, Contra, A favor com ressalvas, Em análise e Acompanhar. Esses estados são independentes da importância da linha.
- **Sem decisões ABCS** significa ausência de decisão em todos os seis campos: relevância sem SIM/NÃO, posição vazia, prioridade não informada e ação, parecer e observações vazios. NÃO e prioridade NÃO são decisões explícitas; texto preenchido também é decisão. Não inferir ausência somente pela falta de posição ou pela revisão.
- **Sem posição** é outro estado: já existe algum registro de decisão, mas a posição institucional não foi definida. Campos opcionais vazios não transformam uma decisão existente em pendência obrigatória.
- A classificação usa apenas o estado salvo; rascunhos não mudam cor, filtro ou ordenação da linha até a conclusão. Após salvar, recalcular o estado e os totais.
- Cor de linha segue precedência: urgente, sem decisões, prioridade, neutra. Etiquetas continuam visíveis ao desativar cores; nenhuma regra operacional ou urgência é alterada pela preferência visual.
- Filtros rápidos: **Todas**, **Urgentes**, **Prioridades**, **Sem decisões ABCS**. Contagens respeitam a aba, busca e demais filtros, antes de aplicar o filtro rápido. Urgentes também estão incluídas na contagem de prioridades: os filtros não são grupos exclusivos. Exportação respeita o mesmo recorte.
- **Personalizar** permite ligar/desligar os três destaques e escolher ordenação. Padrão: **Atenção primeiro** (urgentes, sem decisões, prioridades, demais), com última movimentação como desempate. Alternativa: **Última movimentação**. A ordenação é independente da ativação das cores.
- Preferências ficam neste navegador, persistidas sem dados de decisão, com **Restaurar padrão** e fallback quando o armazenamento estiver indisponível. A implementação deve isolar preferências por usuário em navegadores compartilhados. Enquanto houver editor aberto, controles que mudam o recorte/ordem ficam bloqueados para não ocultar o rascunho.
- Preservar abas Ativas/Histórico e fila Avaliação: destaques não transferem projetos entre universos. O mockup acrescenta um exemplo fictício de projeto acompanhado, fora do radar e sem decisão, para demonstrar o estado na Carteira.

Verificação em Chromium: destaques de cada categoria, filtro sem decisões, remoção desse filtro após gravar a primeira decisão, persistência das preferências, restauração do padrão e troca de ordenação. Aparência conferida nos temas claro e escuro; fluxo de edição, restauração ao valor original, falha e conflito foi reexecutado.

## Regras existentes a preservar

- Reutilizar `salvarProjeto`, o schema de decisão e `gestao.salvar_decisao`; não criar uma segunda via de gravação.
- Prioridade mantém SIM, NÃO e não informada. Relevância mantém SIM, NÃO e pendente; posição vazia significa ausência de decisão.
- Tornar prioritário sem relevância SIM exige confirmar a mudança conjunta. Marcar NÃO num projeto prioritário exige confirmar a retirada da prioridade. Cancelar essas confirmações não grava nada.
- Efeitos conjuntos confirmados entram no salvamento e no histórico, inclusive campos dependentes alterados pela regra.
- Enviar somente diferenças; validar domínios e limites no servidor. Ator vem da sessão, nunca do cliente.
- Revisão divergente impede a gravação. Mostrar base, versão atual e rascunho; exigir escolha explícita para reaplicar as próprias alterações ou descartá-las. Depois da escolha, recalcular os destaques contra a nova base.
- Decisão, revisão e auditoria são atômicas. Manter permissões, isolamento dos dados internos e proteção contra sobrescrita por cargas.

## Sequência de implementação após validar o mockup

1. Extrair `projeto/[id]/editor.tsx` em componente compartilhado, separando consulta, edição e apresentação das diferenças. Reutilizar `CAMPOS_DECISAO`, rótulos e funções de comparação.
2. Adicionar estados de consulta, edição sem diferenças, edição com diferenças, envio, falha e conflito. Implementar cancelamento, limpeza/restauração de rascunho e sincronização da base após sucesso.
3. Implementar hierarquia visual, preferências e filtros rápidos conforme a seção acima. Integrar o modo de edição em `carteira/page.tsx` e `carteira/tabela.tsx`. Carregar decisão completa e revisão atual ao abrir o editor, com autorização no servidor. Não ampliar CSV nem expor parecer e observações ao painel público.
4. Reutilizar o editor na ficha em `projeto/[id]/page.tsx`, com entrada explícita por botão. Manter confirmação de movimentações independente da edição de decisões.
5. Revalidar dados e recortes após o salvamento, atualizar histórico e tratar saída do projeto do filtro atual.
6. Atualizar testes de componentes e roteiro Playwright CA11. Rodar lint, typecheck, testes e build conforme as instruções do repositório da aplicação. Homologar com a Ana antes de detalhar a implantação.

Não há migração de banco prevista: confirmar a suficiência dos contratos existentes durante a implementação. O código da aplicação fica no repositório `banco-de-contatos-mailing`, branch `legislativo-entrega-1`.

## Critérios de aceite

- Categorias de atenção e ausência de decisão aparecem em consulta, com etiquetas mesmo quando cores são desativadas; preferências não alteram decisões.
- Filtros rápidos, ordenação e exportação usam o mesmo recorte, preservando a separação entre Carteira e Avaliação.
- Alterar qualquer um dos seis campos destaca somente os campos diferentes da base e atualiza a contagem e os nomes.
- Restaurar um campo ao original remove sua indicação; restaurar todos desabilita Concluir edição.
- Valores anteriores, novos, vazios e textos longos ficam compreensíveis, inclusive por teclado e sem depender de cor.
- Concluir grava somente diferenças e uma auditoria coerente; reabrir não mostra alterações pendentes antigas.
- Cancelar informa o descarte, preserva o banco e limpa o rascunho. Continuar editando preserva tudo.
- Falha preserva o preenchimento e os destaques; conflito não sobrescreve silenciosamente.
- Confirmações de prioridade/relevância preservam as regras existentes; destaque e resumo acompanham a base atual depois de uma mescla.
- Perfil de leitura e permissão revogada não conseguem gravar; projeto a conferir permanece bloqueado.
- Mudança de aba, filtro, projeto e navegação não perde rascunho silenciosamente.
- Gravação atualiza o recorte sem perder filtros; confirmação de movimentações continua funcionando fora do modo de edição.

## Verificação do protótipo

Sintaxe JavaScript conferida e fluxo executado em Chromium com Playwright: abrir editor na Carteira, destacar dois campos, continuar editando após cancelar, concluir, reabrir com valores salvos, descartar mudanças, editar pela ficha, restaurar o valor original, desabilitar conclusão sem diferenças, preservar rascunho em falha e recalcular destaques após conflito. Captura visual revisada em desktop. Esta verificação não substitui os testes da aplicação nem executa alterações reais.
