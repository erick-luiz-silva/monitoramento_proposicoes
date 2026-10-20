# Pedido ao time de design — fundo do painel "Monitoramento Legislativo"

## Contexto
Painel em Power BI usado pelo time político da ABCS para acompanhar projetos de lei na Câmara. É uma ferramenta de trabalho diário: a prioridade é ler tabelas com muitas linhas e achar rápido o que exige atenção. Hoje usamos o mesmo fundo dos painéis "ABCS Data Insights" (faixa degradê verde no topo e rodapé azul→verde com redes sociais), que ocupa espaço e compete com a informação.

## O que precisamos
**Um único fundo para todas as páginas** (o título de cada página, os filtros e a data de atualização são colocados por cima, no próprio Power BI).

## Formato de entrega
- Proporção **16:9**. Arquivo **PNG de 2560 × 1440 px** (serve para as telas de 1280 × 720 e 1920 × 1080 sem perder nitidez), com **no máximo 300 KB**.
- Arquivo-fonte editável (Figma, Illustrator ou SVG), para ajustes futuros.

## Estrutura
1. **Cabeçalho**: no máximo **7% da altura** (cerca de 100 px no arquivo de 2560 × 1440; hoje ocupa 9%).
   - Logo à esquerda (ABCS Data Insights ou ABCS, a critério de vocês), pequeno.
   - **Cor sólida** em verde escuro ABCS (#00533A) na área à direita do logo, **sem degradê** onde ficará texto: ali entram, em branco, o título da página, os botões de navegação entre páginas e a frase "Dados atualizados em…". O texto precisa de contraste alto (branco sobre #00533A funciona).
   - Deixar livres cerca de **70% da largura** do cabeçalho à direita do logo, sem elementos gráficos.
2. **Área de conteúdo**: fundo liso, branco ou quase branco (ex.: #F7F8F7). **Sem caixas, molduras, sombras ou divisórias desenhadas**: os quadros dos gráficos e tabelas são feitos no Power BI, e o layout vai mudar com o tempo.
3. **Rodapé**: **sem redes sociais**. No máximo uma linha fina de 3–4 px nas cores da marca, ou nenhum rodapé. A fonte dos dados ("Câmara dos Deputados — Dados Abertos") será texto no Power BI.

## Cores
- Usar só a família da marca: verde escuro #00533A, verde #09814A, verde claro #53AF33, texto #14231B. O azul do logo pode aparecer apenas no próprio logo.
- **Não usar vermelho, laranja nem amarelo** em nenhum elemento decorativo: essas cores estão reservadas para indicar urgência nas tabelas.
- Detalhes decorativos (grafismos, ícones) só no cabeçalho e discretos; nada atrás das tabelas.

## Tipografia
Se houver texto fixo no fundo (idealmente nenhum além do logo), usar Segoe UI, que é a fonte disponível no Power BI on-line.

## Para validar antes de fechar
- Ver o fundo com uma tabela densa por cima em um notebook comum (1366 × 768): a tabela deve continuar sendo o elemento mais forte da tela.
- Conferir que o texto branco do cabeçalho fica legível em todo o trecho reservado.
