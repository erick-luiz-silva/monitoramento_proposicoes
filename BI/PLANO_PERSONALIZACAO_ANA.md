# Plano de personalização do painel legislativo para Ana e equipe

> **Nota (19/10/2026):** este plano foi consolidado com o plano v2 em `~/.claude/plans/abstract-knitting-pine.md`, que é o plano de execução. Resumo e perguntas à Ana em `BRIEFING_PAINEL.md`. As imagens citadas em `plano_ana_evidencias/` não estão nesta pasta.

Data: 19/10/2026  
Status: proposta para discussão, revisada independentemente por GPT-6 Astra; ajustes incorporados.  
Entregável: plano de produto, design e validação. Não representa implementação nem publicação.

## 1. Objetivo e princípio de desenho

O painel deve permitir que Ana e o time respondam rapidamente:

1. O que mudou nas proposições que acompanhamos?
2. O que exige atenção e em qual prazo?
3. Qual é a posição da ABCS e a próxima ação?
4. Quem acompanha cada encaminhamento?

A experiência deve priorizar decisões e leitura comparativa. Ementas integrais, histórico e documentos continuam acessíveis no detalhamento, sem ocupar toda a lista principal.

As propostas de rotina e responsabilidade abaixo são hipóteses de produto a validar com Ana; não são preferências já confirmadas por ela.

## 2. Fontes, alcance e limitações

Foram examinados:

- Projeto solicitado em `\\wsl.localhost\Ubuntu-26.04\home\erick\01-projetos\monitoramento_proposicoes\BI`.
- Definições PBIR das seis páginas, visuais e filtros; modelo TMDL, medidas e relacionamentos.
- README e trechos das regras de acompanhamento e eventos em `sql/schema_gold.sql` do projeto WSL.
- PDF exportado, com seis páginas, fornecido pelo usuário. Origem: `C:\Users\User\AppData\Local\Temp\Power BI Desktop\print-job-350c50c1-a193-4721-aefc-99833c2d2c42\BI_Monitoramento_Proposicoes.pdf`.
- Documentação oficial da Microsoft listada ao final.

A cópia do projeto no Windows é anterior à versão WSL em aspectos importantes. A proposta toma a versão WSL como referência de código e o PDF como evidência visual daquela exportação. Não há confirmação de que o PDF, o PBIP e o relatório publicado correspondam à mesma atualização.

Não foram consultadas linhas do banco em produção nem validado o relatório no Power BI Service. Portanto, diferenças de contagem são pontos de reconciliação, não prova de perda de dados.

O plugin Microsoft Power BI foi instalado após a primeira análise. Sua skill descreve acesso pelo navegador ao serviço, não um MCP de edição do Power BI Desktop. A instalação, por si só, não confirma sessão autenticada, workspace ou versão publicada. Nenhum relatório foi alterado.

## 3. Achados e prioridade de tratamento

| ID | Prioridade | Evidência observada | Risco para o uso | Ação proposta |
|---|---|---|---|---|
| A01 | P0 | PDF mostra 18 monitoradas; README WSL registra 54 acompanhadas em 15/10; filtro global e medidas usam relevância SIM. | Confundir carteira acompanhada com subconjunto avaliado como relevante. | Reconciliar IDs, datas e filtros; definir universos antes de alterar contagens. |
| A02 | P0 | Tabela anuncia últimos 30 dias, mas mostra junho a agosto; definição examinada não contém condição efetiva dessa janela. | Interpretar histórico como novidade. | Aplicar janela explícita e informar referência temporal. |
| A03 | P0 | Visão geral agrega órgão de tramitações separadamente da data; PL 3584/2015 aparece com CAPADR nessa página e CCJC no monitoramento. | Associar órgão e evento de momentos distintos. A diferença entre órgão atual e órgão de um evento histórico, isoladamente, não é erro. | Declarar qual conceito a coluna apresenta: usar órgão atual consolidado ou todos os atributos da mesma última tramitação, com desempate determinístico. |
| A04 | P0 | Medida Data Última Atualização usa MAX da data de movimentação legislativa. | Confundir ausência de novidade com falha de carga, ou mostrar atualização enganosa. | Separar coleta, atualização do modelo e última movimentação. |
| A05 | P0 | Regras de status inferem realização/agendamento pela data e presença de URI de votação. | Exibir cancelado como agendado ou passado como realizado. | Priorizar situação oficial; usar estado desconhecido quando faltar evidência. |
| A06 | P1 | Mapa apresenta erro no PDF; a página já tem barras por UF. | Elemento sem utilidade ocupa grande área. | Retirar o mapa e reorganizar/ampliar os gráficos existentes. Uma matriz adicional só entra se responder a pergunta distinta; evitar duplicar UF. |
| A07 | P1 | Ementas longas, rolagem horizontal e assunto de audiência com participantes na mesma célula. | Poucos itens comparáveis por tela. | Resumos identificados, colunas essenciais e detalhe completo acessível. |
| A08 | P1 | Detalhamento possui cartões de ação, parecer, posição e observação sem rótulos e com cortes. | Interpretar valores sem saber o campo correspondente. | Blocos rotulados com texto legível e acesso integral. |
| A09 | P1 | Posição ABCS mistura categoria e comentário; prioridade usa sim/não. | Filtros fragmentados e classificação inconsistente. | Padronizar categorias e separar observação; preservar valores originais na migração. |

P0 bloqueia a homologação funcional da nova versão. Os P1 da tabela acima compõem o núcleo da primeira versão utilizável, com soluções que usem os campos disponíveis. Campos novos, metadados ainda indisponíveis, estruturação de participantes e personalização avançada são melhorias condicionais; não bloqueiam esse núcleo. P2 corresponde a melhorias posteriores.

## 4. Contrato das informações

### 4.1 Universos de proposições

Definir com o negócio, sem presumir que as categorias sejam mutuamente exclusivas:

| Conceito | Significado proposto | Regra a conferir |
|---|---|---|
| Acompanhadas | Carteira permanente do time, inclusive inclusões manuais e legado. | Usar o indicador de acompanhamento da fonte e reconciliar a importação no modelo. |
| Relevantes | Proposições avaliadas como relevantes para o setor. | Relevância SIM; verificar cobertura de avaliações ausentes. |
| Pendentes de avaliação | Itens elegíveis do radar sem decisão registrada. | Aplicar regra vigente de radar e estado real de avaliação. Não considerar toda ausência de correspondência como pendência. |
| Em tramitação / encerradas | Classificação da situação legislativa. | Mapear códigos com Ana; situação desconhecida permanece explícita. |

Uma acompanhada pode ser relevante e pode estar encerrada. Não somar cartões com sobreposição como se fossem um total. Manter acesso ao histórico mesmo se as encerradas forem excluídas de um indicador operacional.

O filtro global de relevância deve ser revisto depois dessa definição. Não basta removê-lo: as medidas também repetem o filtro e a navegação pode depender dele.

### 4.2 Datas e contagens

- Registrar fuso de apresentação como `America/Sao_Paulo`; conferir como timestamps chegam antes de converter.
- Especificar se “últimos 7/30 dias” significa dias corridos incluindo hoje ou janela móvel de horas. Usar a mesma definição em título, cartão e tabela.
- Diferenciar “proposições com movimentação” de “quantidade de tramitações no período”. Contar eventos no histórico para a segunda pergunta.
- O campo de última movimentação identifica proposições cujo evento mais recente caiu na janela; não substitui o histórico para análises por período arbitrário.
- Excluir datas ausentes e futuras indevidas do indicador de movimentações recentes; informar inconsistências separadamente.
- Contar proposições por ID estável; eventos por ID de evento; itens de pauta por chave própria. Definir o grão antes de deduplicar ou calcular percentuais.
- “Pautas agendadas” precisa indicar se conta itens, proposições ou reuniões. A medida atual conta linhas, apesar de o comentário mencionar proposições.
- Especificar numerador, denominador e período de qualquer taxa de votação. Não apresentar percentual histórico sem contexto como indicador de urgência.
- Diferenciar zero confirmado, ausência de avaliação e informação indisponível. Não substituir todos os valores em branco por zero.

### 4.3 Atualidade dos dados

Exibir separadamente, conforme dados efetivamente disponíveis:

1. Última coleta bem-sucedida na fonte/pipeline.
2. Última atualização bem-sucedida do modelo Power BI.
3. Última movimentação legislativa encontrada.

O calendário atual observado cobre 2025 a 2027, enquanto o projeto mantém histórico anterior. Conferir a amplitude necessária. As relações entre calendário e timestamps também precisam de validação: testar se horários diferentes de meia-noite filtram corretamente e considerar colunas de data próprias para relações.

Correção imediata: renomear a medida existente para “Movimentação mais recente”. Se não houver metadado confiável de coleta ou atualização do modelo, exibir “Não disponível” para esse metadado, sem inferir sucesso ou falha. Implantar a captura adicional como dependência identificada, sem mascarar sua ausência nem bloquear as demais melhorias.

## 5. Arquitetura da experiência

Preservar inicialmente as seis páginas existentes, evitando reconstrução desnecessária. Criar navegação com nomes visíveis: **Início, Carteira, Proposição, Autores e partidos, Pautas, Audiências**. Os nomes finais devem ser reconhecíveis para o time.

### 5.0 Dependências de conteúdo e exportação

O modelo examinado possui ementa e assunto integral, mas não demonstra campos próprios de resumo editorial, título de audiência e participantes estruturados. Na primeira entrega, usar excerto identificado como tal e permitir acesso ao texto integral. Não apresentar corte de texto como síntese validada. Resumo editorial exige origem, regra de produção, responsável e manutenção definidos; estruturação de participantes depende de fonte ou regra de extração validada. Nenhum desses campos será presumido disponível nem gerado automaticamente como requisito deste plano.

Definir antes do protótipo se o PDF será **briefing**, **conteúdo completo** ou duas saídas distintas. Registrar canal de exportação (Desktop ou Service), páginas, filtros, ordenação, data de referência e contexto da proposição detalhada. Briefing deve declarar que é um recorte. Uma saída completa deve ter IDs e quantidade de registros conferidos contra o universo filtrado. A solução para impressão completa será avaliada conforme a necessidade e os recursos disponíveis; não se promete que o PDF padrão percorra tabelas com rolagem.

### 5.1 Início: briefing de trabalho

Ordem de leitura:

1. Cabeçalho compacto com título, escopo e atualidade.
2. Indicadores de mudanças recentes, pautas próximas, pendências e carteira, conforme contrato validado.
3. Fila de atenção com prioridade, proposição, resumo, mudança e próxima ação.
4. Acesso à carteira completa e ao histórico.

Não presumir urgência só porque um projeto está parado. A fila deve combinar classificação humana e sinais objetivos, explicando o motivo da inclusão. Não atribuir risco automaticamente a uma posição política sem regra aprovada.

Quando nada acontecer na janela, mostrar “Nenhuma movimentação encontrada no período selecionado”, junto à atualidade dos dados; não preencher a lista com registros antigos sob o mesmo título.

### 5.2 Carteira: principal tabela de trabalho

Configuração inicial proposta:

| Ordem | Coluna | Comportamento |
|---|---|---|
| 1 | Prioridade | Texto e ícone; categoria validada. |
| 2 | Proposição | Identificação clara, com acesso ao detalhe. |
| 3 | Resumo / excerto | Uma ou duas linhas; identificar como excerto enquanto não houver resumo validado. |
| 4 | Posição ABCS | Categoria padronizada, distinta da prioridade. |
| 5 | Órgão atual | Sigla na lista e nome completo acessível; inclui comissões, MESA, CCP e PLEN. |
| 6 | Última movimentação | Data simples; informação completa no detalhe. |
| 7 | Próxima ação | Síntese operacional, sem truncar o acesso ao conteúdo integral. |

Autor/partido/UF, dias sem movimentação, parecer, tema, responsável e prazo serão colunas opcionais. Responsável e prazo exigem inclusão na fonte antes de aparecerem como recursos disponíveis.

Ordenação inicial sugerida: prioritárias primeiro, depois movimentação mais recente, com identificação como desempate. Possibilitar ordenação pela Ana. A agenda futura usa ordem crescente de data, não esse padrão.

Filtros iniciais: proposição, tema, prioridade, posição ABCS, situação e órgão. Mostrar os filtros essenciais; filtros adicionais podem usar painel nativo ou painel por indicadores, escolhido e testado no protótipo. Exibir escopo e quantidade de resultados. Definir “Limpar filtros” como restauração dos filtros ao padrão, preservando colunas e ordenação quando tecnicamente validado; oferecer separadamente “Restaurar visão padrão” se necessário. Não prometer dois comportamentos com um único botão ambíguo.

Entrada no detalhe: selecionar uma proposição e acionar botão de drillthrough, com instrução clara quando não houver seleção única. Link oficial é outra ação, rotulada “Abrir na Câmara”. Testar ambos; não presumir que hyperlink na identificação execute drillthrough.

O campo `keywords_encontradas` reúne termos em texto. Para filtrar um tema individual, avaliar uma ponte proposição-tema/keyword, preservando uma linha por proposição na tabela. Não tratar combinações de termos como categorias únicas nem duplicar contagens após expandi-las.

### 5.3 Proposição: detalhe contextual

- Identificação, ementa integral e link oficial.
- Situação e órgão atuais com datas de referência, separados do órgão e da situação de eventos históricos.
- Autor principal com partido/UF segundo a referência temporal garantida pela fonte. A intenção documentada é usar valores atuais, mas a atualidade depende da dimensão e da carga; explicitar essa referência. Não são necessariamente os valores da apresentação, nem prova de mandato atual.
- Posição ABCS, parecer, ação e observações em blocos rotulados.
- Responsável, prazo e estado da ação quando implantados na fonte.
- Histórico de tramitações em ordem decrescente e histórico de pautas com a situação oficial.
- Botão de voltar mantendo a seleção anterior, sem deixar um filtro de exemplo fixo para outras proposições.

O arquivo examinado possui contexto de drillthrough com PL 2788/2025. Testar a entrada a partir de outras proposições e a abertura direta da página; não afirmar que o contexto observado é um defeito sem esse teste.

Ao abrir o detalhe sem contexto, pedir a seleção de uma proposição em vez de apresentar silenciosamente um projeto de exemplo. Os atributos de um evento histórico devem pertencer à mesma linha; não exigir que o órgão desse evento seja igual ao órgão atual.

### 5.4 Autores e partidos

Usar barras ou matriz por autor principal, partido e UF, com filtros de carteira, posição e prioridade. Informar “Autoria principal da carteira selecionada”. Essa cobertura não representa todos os coautores nem uma lista de interlocutores atuais. Autoria numerosa não implica apoio, influência ou alinhamento institucional.

Avaliar incluir relatores somente quando houver fonte adequada e referência temporal. Relator de pauta histórica não equivale necessariamente ao relator atual.

### 5.5 Pautas

Separar **Próximas pautas** de **Histórico** por seleção visível. Não ocultar canceladas do histórico.

Tabela principal: data/hora, comissão, proposição, relator informado para o item, posição ABCS, providência, situação oficial e link disponível na fonte.

Priorizar situação oficial do evento e do item. Ausência de URI de votação não prova ausência de apreciação. Se a fonte não permite determinar o resultado, usar “Resultado não identificado” ou estado equivalente validado.

Mostrar o vínculo direto ou indireto com a proposição quando relevante; um requerimento relacionado não deve ser apresentado como votação garantida do projeto principal.

### 5.6 Audiências

Mostrar excerto do assunto com acesso à descrição integral. Separar título, descrição e participantes apenas se a fonte ou a transformação validada sustentar essa estrutura. O título resumido, quando existir, não deve alterar o sentido do tema.

Tabela: data/hora, comissão, assunto resumido, motivo da seleção temática, situação oficial e link. Participantes e descrição extensa ficam no detalhe, acessível também por clique e teclado.

Audiências encontradas por keyword são sugestões temáticas, não pertinência confirmada pela Ana nem vínculos comprovados com projetos. Permitir avaliação de interesse em fase posterior, se o time precisar. Não filtrar essa página pelo relacionamento de proposições sem vínculo confiável.

## 6. Diretrizes de design e acessibilidade

### 6.1 Hierarquia e identidade

- Manter identidade ABCS com uso contido de verde e azul; confirmar cores oficiais antes do tema final.
- Reduzir a altura dos grandes cabeçalhos e rodapés institucionais, destinando espaço à informação e às ações.
- Evitar títulos longos em caixa alta e itálico como padrão de todas as páginas.
- Reservar cor de destaque à seleção e aos estados importantes; usar base neutra nas tabelas.
- Manter espaçamentos, alinhamentos, rótulos, largura de coluna e formato de datas consistentes.
- Não adicionar gráficos sem uma pergunta operacional clara. Evitar repetir no início métricas históricas já disponíveis na página de pautas.

### 6.2 Legibilidade

- Prototipar na resolução real de uso, incluindo notebook de 1366×768 e desktop, se esses forem os equipamentos do time.
- O canvas atual de 1920×1080 pode reduzir bastante os textos quando ajustado à página. Testar alternativas de canvas e tamanho real antes de escolher.
- Como ponto de partida, experimentar corpo de tabela de 11–12 pt e cabeçalhos de 12–14 pt no Power BI; são valores para protótipo, não garantia de legibilidade após escala ou exportação.
- Evitar rolagem horizontal na configuração padrão. Permitir configuração expandida para usuários que escolham mais colunas.
- Usar zebrado discreto e separadores leves quando ajudarem a seguir linhas.
- Ementa integral e observações devem permanecer acessíveis sem depender apenas de tooltip.

### 6.3 Estados e interação

- Cor sempre acompanhada de texto ou ícone compreensível.
- Contraste de texto normal de pelo menos 4,5:1; conferir também foco, rótulos e estados selecionados.
- Ordem de tabulação lógica, texto alternativo nos visuais e botões com nome claro.
- Definir mensagens distintas para ausência de resultados, ausência de avaliação, erro de visual e informação desatualizada.
- “Dias sem movimentação” é idade do evento, não atraso de uma tarefa. Não colorir automaticamente como prazo vencido.
- Nas páginas com visuais cruzados, conferir se clicar em um gráfico filtra ou apenas realça os demais e se o resultado fica evidente.

## 7. Personalização por pessoa

Implementar primeiro escolhas simples e previsíveis:

1. Visões compartilhadas: Prioritárias, Mudanças recentes, Próximas pautas e Sem posicionamento, cada uma com regra explícita.
2. Escolha de colunas por parâmetros de campos, com conjunto pequeno de campos úteis e nomes legíveis.
3. Indicadores pessoais para salvar filtros e preferências, após teste no serviço.
4. Personalização avançada de visuais apenas onde trouxer benefício; não expor todo o modelo técnico ao time.

Parâmetros de campos não devem ser apresentados como editor irrestrito da tabela; validar seleção, ordenação e compatibilidade com o detalhamento. Os campos estáveis de identificação continuam sendo o contexto do drillthrough. Testar o caso de nenhuma seleção: nesse recurso, pode equivaler a todos os campos, reintroduzindo rolagem horizontal. Definir conjunto padrão e controle adequado antes de liberar.

Indicadores pessoais e personalizações visuais não são a mesma coisa que o layout de exportação. A documentação da Microsoft informa que exportações PDF/PowerPoint não capturam visuais personalizados. Definir uma configuração padrão de exportação e testar seu resultado.

## 8. Fonte de manutenção e processo do time

O modelo já lê posicionamento institucional de uma planilha Google. Aproveitar essa rotina antes de introduzir um novo sistema de edição.

| Campo | Proposta | Condição |
|---|---|---|
| Posição ABCS | Categorias como A favor, A favor com ressalvas, Contra, Acompanhar e Em avaliação. | Vocabulário a aprovar com Ana; não reclassificar automaticamente textos ambíguos. |
| Prioridade | Manter sim/não na primeira entrega ou migrar para Alta/Média/Baixa mediante critérios claros. | Não converter sim para Alta sem decisão do negócio. |
| Ação | Encaminhamento concreto e separado do parecer. | Preservar texto original na migração. |
| Parecer | Análise institucional e eventual referência documental. | Texto completo no detalhe. |
| Responsável | Pessoa ou equipe responsável pela providência. | Novo campo com responsável por manutenção. |
| Prazo | Data de uma ação do time. | Não confundir com data de pauta ou prazo legislativo. |
| Situação da ação | A fazer, Em andamento, Concluída, se fizer sentido para a rotina. | Novo campo e critérios de fechamento. |
| Atualizado por/em | Rastreabilidade da avaliação humana. | Depende do mecanismo de edição e auditoria disponível. |

O relatório não oferece gravação de volta na planilha apenas por exibir esses campos. Se houver necessidade de editar, usar link para a fonte autorizada ou desenhar integração específica em etapa posterior.

## 9. Revisão técnica para sustentar o design

- Reconciliar os filtros globais, de página, de visual e das medidas com os universos definidos.
- Normalizar a chave de proposição: o modelo observado tem ID numérico em monitoramento e ID textual em posicionamento; não trocar relações sem limpar dados e validar unicidade.
- Revisar relacionamentos 1:1 bidirecionais e caminhos inativos com dados reais. Não substituir tudo por um modelo estrela sem evidência da necessidade.
- Verificar propagação de filtros entre carteira, posicionamento, pautas e tramitações; impedir que uma seleção elimine registros sem avaliação indevidamente.
- Conferir calendário, datas sem horário, amplitude histórica e papéis temporais distintos. A relação de data das pautas está inativa; medidas por data devem usar o papel correto.
- Testar paginação e completude da importação antes de explicar uma contagem menor como regra de negócio.
- Confirmar a regra e a frequência de recálculo de dias sem movimentação. Em modo importação, o valor não se atualiza sozinho com a passagem do tempo.
- Não expor IDs técnicos e campos de suporte como somas nas escolhas do usuário.

## 10. Sequência de implementação e aceite

| Etapa | Entrega | Dependência | Critério de aceite |
|---|---|---|---|
| 1 — Reconciliação | Contrato de carteira, grãos, datas, status, atualidade e finalidade do PDF. | Definições atuais e acesso autorizado às fontes. | Explicar por IDs a diferença de universos; conferir amostra com os mesmos filtros e data; escolher briefing ou saída completa. |
| 2 — Protótipo | Início, Carteira, Proposição e amostra da saída de exportação escolhida. | Etapa 1 e linguagem validada com Ana. | Ana encontra mudança, posição e ação; exportação representa o recorte ou conteúdo completo declarado. |
| 3 — Versão funcional | Ajustes de tabelas, navegação, filtros e detalhe. | Protótipo escolhido. | Sem cortes impeditivos; navegação mantém contexto; contagens e linhas concordam no mesmo universo. |
| 4 — Agenda e audiências | Próximos eventos, histórico e conteúdo resumido. | Regras de situação e vínculo corretas. | Cancelamentos e casos desconhecidos não são apresentados como realização/votação confirmada. |
| 5 — Homologação do núcleo | Registro de testes e feedback da Ana. | Etapas 1 a 4. | Nenhum P0 aberto; evidências preservadas; diferenças aceitas documentadas. Não depende de novos campos nem da personalização avançada. |
| 6 — Melhorias opcionais | Escolha de colunas, visões pessoais e novos campos operacionais escolhidos pelo time. | Núcleo homologado; fonte, serviço e permissões disponíveis para cada recurso. | Homologação por melhoria; preferências podem ser salvas/restauradas; estado sem seleção e retorno ao padrão são claros. |

Não estimar esforço em dias antes de confirmar o estado do modelo publicado, as fontes disponíveis e a necessidade de migração da planilha.

## 11. Cenários mínimos de validação

### Funcionais e de dados

- Mesma proposição e campos de mesmo significado iguais entre início, carteira e detalhe; diferenças entre órgão atual e órgão de evento histórico devem ser explicadas e rotuladas, não eliminadas artificialmente.
- Reconciliar acompanhadas, relevantes e pendentes por ID; registrar sobreposições e exclusões.
- Janela recente nas fronteiras do período, data ausente, data futura indevida e mudança de dia no fuso escolhido.
- Data do calendário filtrando registros com horário; período histórico anterior a 2025 e pautas futuras.
- Carteira sem posição preenchida, sem prioridade e sem correspondência na planilha institucional.
- Proposição com múltiplas keywords, múltiplas tramitações e múltiplos itens de pauta sem multiplicar KPIs indevidamente.
- Evento cancelado, adiado, encerrado, futuro e de resultado desconhecido.
- Vínculo indireto entre item de pauta e proposição explicitado corretamente.
- Drillthrough com pelo menos três proposições diferentes e retorno à lista preservando o contexto esperado.
- Última coleta, atualização do modelo e última movimentação com definições distintas.

### Design e uso

- Busca por número de proposição, filtro de prioridade, limpeza de filtros e acesso à fonte oficial.
- Ementa, parecer e observação muito longos; audiência com lista extensa de participantes.
- Nenhum resultado e falha/desatualização de dados com mensagens diferentes.
- Uso por teclado e compreensão dos estados sem depender da cor.
- Registrar equipamento, resolução, escala e modo de exibição usados no teste; percorrer por teclado filtro → seleção da linha → detalhe → voltar, verificando foco e nome acessível dos controles.
- Verificar leitura integral de um texto longo e medir contraste das combinações efetivamente usadas. Acessibilidade do relatório não certifica automaticamente a do PDF.
- Testar personalização com nenhum campo opcional selecionado, restauração de filtros e restauração da visão completa como comportamentos distintos.
- Leitura no notebook real e no PDF; os testes de PDF não substituem os testes de interação no serviço.
- Se o PDF precisa representar toda a carteira, prever saída específica: uma tabela com rolagem na tela não garante que todas as linhas apareçam na exportação.
- Medir tarefas como localizar a próxima pauta prioritária e identificar posição/ação de um projeto. Registrar referência inicial e comparar após o ajuste, sem inventar metas de desempenho já aprovadas.

## 12. Perguntas para discussão com Ana

1. A abertura deve destacar toda a carteira ou apenas o trabalho da semana?
2. Quais são as regras para acompanhar, avaliar relevância e encerrar acompanhamento?
3. Prioridade sim/não é suficiente? Quem define e revisa a classificação?
4. Qual informação decide a próxima ação: pauta, relatoria, posição institucional, prazo ou outra?
5. Responsável e prazo fazem parte da rotina que o time quer manter?
6. O PDF é briefing resumido ou precisa conter todas as linhas e textos?
7. Quais equipamentos, formas de acesso e necessidades de leitura devem orientar o layout?

Essas perguntas orientam a homologação; não impedem corrigir rótulos, cortes e inconsistências já demonstradas.

## 13. Skills, plugins e revisão independente

- **PDF:** empregado na extração e inspeção visual das seis páginas na análise anterior.
- **Microsoft Power BI:** skill consultada para distinguir arquivos locais, relatório no serviço, autenticação e limites de publicação; não houve sessão ao vivo nesta etapa de documentação.
- **Visualize:** consultada para avaliar se um protótipo em conversa seria necessário; o entregável pedido é Markdown, portanto não se criou um artefato interativo adicional.
- **Plugin Management:** empregado para descobrir recursos de design. Figma, Canva e MagicPath estavam disponíveis, mas não instalados na consulta. Não foram usados para produzir este plano.
- **Product Design:** instalado posteriormente. Foram consultadas as skills index, audit e user-context, o framework de auditoria e suas regras de comunicação. O preflight não encontrou contexto salvo. Aplicou-se o framework como revisão estática ao PDF explicitamente fornecido, novamente renderizado e inspecionado nesta etapa. O complemento da seção 16 não equivale a auditoria de navegação ao vivo. Nenhum protótipo, canvas ou publicação foi criado.
- Ferramentas de imagem, apresentações e criação de sites não são necessárias para este arquivo de planejamento. Instalar todas não melhora, por si, a qualidade ou viabilidade do painel.
- **Revisão independente:** realizada por segundo agente com modelo GPT-6 Astra, esforço alto, conforme solicitação do usuário. Parecer e ajustes registrados na seção 15.

## 14. Referências oficiais

- [Formatação condicional em tabelas e matrizes](https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-conditional-table-formatting)
- [Links em tabelas e matrizes](https://learn.microsoft.com/en-us/power-bi/create-reports/power-bi-hyperlinks-in-tables)
- [Drillthrough](https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-drillthrough)
- [Parâmetros de campos](https://learn.microsoft.com/en-us/power-bi/create-reports/power-bi-field-parameters)
- [Personalização de visuais e limitações de exportação](https://learn.microsoft.com/en-us/power-bi/create-reports/power-bi-personalize-visuals)
- [Indicadores pessoais](https://learn.microsoft.com/en-us/power-bi/explore-reports/end-user-bookmarks)
- [Design de relatórios acessíveis](https://learn.microsoft.com/en-us/power-bi/create-reports/desktop-accessibility-creating-reports)
- [Exportação de relatórios para PDF](https://learn.microsoft.com/en-us/power-bi/collaborate-share/end-user-pdf)

### Localizadores das evidências no projeto WSL

Caminhos relativos à pasta BI informada na seção 2:

| Evidência | Arquivo / campo |
|---|---|
| Filtro global de relevância | `BI_Monitoramento_Proposicoes.Report/definition/report.json`, `filterConfig`. |
| Tabela inicial, título e agregações independentes | `BI_Monitoramento_Proposicoes.Report/definition/pages/144a96dc6239db74d11a/visuals/8cf83186af14d6369fe6/visual.json`. |
| Colunas e ordenação da carteira | `BI_Monitoramento_Proposicoes.Report/definition/pages/2f1b62b82156458deeae/visuals/fdcb8e8cdd7463edd434/visual.json`. |
| Medidas e definição de atualização | `BI_Monitoramento_Proposicoes.SemanticModel/definition/tables/Medidas.tmdl`. |
| Calendário | `BI_Monitoramento_Proposicoes.SemanticModel/definition/tables/gold_vw_dim_calendario.tmdl`. |
| Tipos de chave e fonte de posicionamento | `BI_Monitoramento_Proposicoes.SemanticModel/definition/tables/gold dim_posicionamento_abcs.tmdl`. |
| Propagação de filtros e relações inativas | `BI_Monitoramento_Proposicoes.SemanticModel/definition/relationships.tmdl`. |

O PDF está em pasta temporária do Power BI e pode ser removido pelo sistema. Preservar uma cópia autorizada da exportação usada na homologação, com data e filtros, se for necessário manter evidência durável.

## 15. Registro de revisão

Revisão independente concluída em 19/10/2026 por GPT-6 Astra, com esforço alto. O revisor examinou o plano, as seis imagens e os artefatos PBIR/TMDL copiados do WSL. Não consultou banco ou Service e não revalidou o README WSL nem as regras SQL, que não estavam na cópia fornecida a ele.

**Parecer recebido:** aprovado como base de discussão, com ajustes antes de virar especificação de implementação. A revisão não constitui homologação dos dados ou do relatório publicado.

Ajustes incorporados após o parecer:

1. Distinguir órgão atual de órgão da última tramitação; igualdade só é exigida para conceitos equivalentes.
2. Declarar dependências dos resumos e da estruturação de participantes; primeira entrega pode usar excerto identificado.
3. Antecipar a decisão e a validação da saída PDF para reconciliação e protótipo.
4. Separar homologação do núcleo de melhorias opcionais e tratar metadados indisponíveis explicitamente.
5. Especificar seleção e botão de drillthrough, abertura sem contexto, restauração de filtros e caso sem seleção em parâmetros de campos.
6. Manter nome Autores e partidos e explicitar cobertura de autoria principal e referência temporal da fonte.
7. Remover mapa sem duplicar o gráfico de UF existente.
8. Tornar testes de acessibilidade reproduzíveis em equipamento e percurso registrados.

**Estado final do documento:** revisado para debate e planejamento. Implementação, reconciliação em produção e homologação com Ana permanecem trabalhos futuros explicitamente previstos.

## 16. Complemento de Product Design: revisão visual por tela

### Escopo e limite da evidência

Objetivo: revisar hierarquia, clareza, densidade, orientação e riscos visíveis de acessibilidade no material exportado da experiência existente.

As seis páginas do PDF fornecido foram novamente renderizadas a PNG e inspecionadas em 19/10/2026. As imagens abaixo são renderizações dessa exportação, não capturas do relatório publicado nem prova de comportamento interativo. A ordem é a ordem das páginas do PDF, não uma jornada de navegação observada.

O fluxo desejado para validação futura é **localizar novidade → identificar prioridade e posição → abrir proposição → consultar evidência → decidir encaminhamento → voltar à carteira**. Cliques, foco, teclado, seleção, indicadores, estado vazio e atualização precisam ser capturados e testados no relatório real antes de se declarar auditado esse fluxo.

Os efeitos no trabalho descritos abaixo são riscos inferidos da apresentação visual, ainda não observados em teste com Ana.

### 1. Painel de controle — precisa de ajuste de hierarquia e orientação

![Tela 1 — Painel de controle do PDF](plano_ana_evidencias/tela-1.png)

- **Pontos fortes:** identidade institucional reconhecível; indicadores e lista estão agrupados; há busca por identificação visível.
- **Evidência visual:** seis indicadores pequenos; botão Detalhes aparece acinzentado e distante do registro; rótulos técnicos; grande área institucional e baixo aproveitamento da largura útil na exportação.
- **Efeito no trabalho:** o primeiro olhar não deixa clara a próxima ação nem o significado de valores como `--`. O aspecto do botão não comprova que esteja desabilitado no serviço.
- **Proposta:** organizar indicadores pelo briefing de trabalho, aproximar a ação de detalhe da seleção e explicar o estado sem seleção. Substituir rótulos técnicos e reduzir decoração para melhorar o tamanho percebido da informação.
- **Risco de acessibilidade:** textos pequenos e cinza podem dificultar leitura; medir contraste e escala real antes de concluir conformidade.

### 2. Monitoramento — conteúdo útil, comparação entre linhas prejudicada

![Tela 2 — Carteira de monitoramento do PDF](plano_ana_evidencias/tela-2.png)

- **Pontos fortes:** posição, prioridade e ação já aparecem junto à informação legislativa; filtros relevantes estão próximos da tabela.
- **Evidência visual:** linhas de alturas muito diferentes, grande volume de texto integral, prioridade/ação à direita e rolagem horizontal.
- **Efeito no trabalho:** comparar prioridades exige percorrer uma tabela extensa; a ementa domina a leitura antes da providência.
- **Proposta:** aplicar a configuração compacta da seção 5.2; trazer prioridade para o início; usar excerto com leitura integral disponível no detalhe; manter uma configuração padrão sem rolagem horizontal.
- **Risco de acessibilidade:** a ampliação necessária para ler pode aumentar o deslocamento horizontal; validar com escala e equipamento reais, sem depender de hover para recuperar texto.

### 3. Detalhamento — estrutura aproveitável, significado de campos comprometido

![Tela 3 — Detalhamento de proposição do PDF](plano_ana_evidencias/tela-3.png)

- **Pontos fortes:** identificação destacada; informações de autor, posicionamento, tramitações e pautas agrupadas em uma página.
- **Evidência visual:** ementa truncada; valores como “sim - enviado”, “Contra” e “em conjunt...” aparecem em cartões sem rótulos individuais.
- **Efeito no trabalho:** o leitor precisa deduzir qual informação é ação, parecer ou observação; a ementa completa não fica disponível nessa saída.
- **Proposta:** substituir cartões de texto livre por blocos rotulados; deixar posição resumida em destaque e textos longos em área própria. Garantir acesso integral no serviço e representação adequada na saída PDF escolhida.
- **Risco de acessibilidade:** hierarquia visual não garante nome acessível; testar leitura por tecnologia assistiva e ordem de foco no relatório real.

### 4. Autores e partidos — comparações legíveis, mapa sem função

![Tela 4 — Autores e partidos do PDF](plano_ana_evidencias/tela-4.png)

- **Pontos fortes:** barras usam base comparável e valores; a autoria principal pode ser localizada por nome.
- **Evidência visual:** o mapa está substituído por mensagem de erro; o gráfico por UF já existe; os títulos repetem nomes técnicos de medidas e campos.
- **Efeito no trabalho:** área grande é consumida por erro; uma segunda comparação por UF seria redundante sem pergunta distinta.
- **Proposta:** retirar o mapa, ampliar os gráficos existentes e simplificar títulos. Explicitar a cobertura de autor principal e o universo selecionado.
- **Risco de acessibilidade:** nomes de autores e partidos longos exigem largura suficiente; não usar cores de partido como único código de identificação.

### 5. Pautas e eventos — histórico visível, agenda operacional pouco destacada

![Tela 5 — Pautas e eventos do PDF](plano_ana_evidencias/tela-5.png)

- **Pontos fortes:** relator e situação do item ajudam a entender o evento; há comparação por órgão e status.
- **Evidência visual:** gráficos históricos ocupam boa parte da página; a tabela inferior mostra poucos itens e descrições longas; o cartão de agendadas exibe `--`, sem explicação visível do significado.
- **Efeito no trabalho:** é difícil distinguir rapidamente se não há agenda futura, se há filtro restritivo ou se falta atualização.
- **Proposta:** destacar agenda próxima com janela e atualidade explícitas; alternar agenda/histórico; reduzir texto do resultado na lista e preservar acesso integral. A semântica dos estados continua condicionada à correção A05.
- **Risco de acessibilidade:** não usar apenas cor para diferenciar agendado, cancelado e resultado desconhecido; cada estado precisa de rótulo textual.

### 6. Audiências — leitura do conteúdo extensa demais para uma lista

![Tela 6 — Audiências públicas do PDF](plano_ana_evidencias/tela-6.png)

- **Pontos fortes:** motivo temático da seleção está exposto; data e órgão acompanham o assunto.
- **Evidência visual:** uma audiência com participantes ocupa quase toda a altura da tabela; o título “keyword match” exige conhecimento da implementação.
- **Efeito no trabalho:** comparar datas e assuntos de várias audiências fica prejudicado; o leitor pode confundir seleção automática com interesse confirmado.
- **Proposta:** renomear para “Audiências sugeridas por tema”; usar excerto do assunto e detalhe integral. Só separar participantes em campos se houver fonte/regra validada, sem prometer extração segura a partir do texto mostrado.
- **Risco de acessibilidade:** conteúdo longo deve ter acesso por clique e teclado; tooltip não é substituto para esse acesso, e o PDF exige decisão específica sobre inclusão integral.

### Decisão de design recomendada

Após a reconciliação dos dados prevista na etapa 1, começar o protótipo pelo par **Carteira + Proposição**, pois concentra comparação e interpretação. Ajustar o Início para orientar a rotina e as páginas de agenda para antecipar ações. A intenção não é uniformizar todas as telas: listas devem ser compactas, e o detalhe deve permitir leitura completa.

As seis renderizações estão em `BI/plano_ana_evidencias/`, ao lado deste documento. Para discutir o plano com outro agente ou em outra máquina, manter o Markdown e essa pasta juntos. O arquivo continua compreensível sem as imagens, mas elas preservam a rastreabilidade visual dos achados.

Este complemento passou por nova revisão do GPT-6 Astra em 19/10/2026. Parecer: aprovado como complemento de revisão estática, com duas correções incorporadas: qualificar os efeitos no trabalho como riscos inferidos e descrever `--` sem presumir seu significado. O revisor confirmou coerência dos achados com as seis imagens, sem homologar o fluxo ao vivo.
