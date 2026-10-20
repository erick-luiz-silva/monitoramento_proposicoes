# Briefing — Painel de Monitoramento Legislativo (ABCS)

Data: 19/10/2026 · Plano de execução: `~/.claude/plans/abstract-knitting-pine.md` (consolida `PLANO_PERSONALIZACAO_ANA.md` e o plano v2).

## 1. Contexto e problema
O time político da ABCS (Ana) acompanha proposições da Câmara que afetam a suinocultura. O painel é a fonte única, mas hoje não mostra o que exige atenção: nenhuma tabela tem cor, os números mudam conforme a tela (19 × 54) e alguns rótulos e datas enganam (tabela "últimos 30 dias" sem janela, "última atualização" que é a última movimentação, reuniões canceladas como "encerradas").

## 2. Usuários e uso
- Principal: Ana e o time político (fonte de informação do dia a dia). Toda a ABCS pode consultar.
- Equipamento: principalmente notebook (layout pensado para 1366 × 768). Versão para celular fica para uma etapa futura.

## 3. Decisões apoiadas → perguntas → indicadores
| Decisão | Pergunta | Indicador / visual |
|---|---|---|
| Onde agir esta semana | O que exige atenção e por quê? | Fila ordenada por Nível de Atenção, com motivo |
| Preparar presença em comissão | Quais proposições entram em pauta nos próximos 14 dias? | Pautas agendadas (reuniões distintas), proposições em pauta |
| Atualizar a posição da ABCS | Qual a posição e a próxima ação de cada uma? | Carteira com posição, ação e observações rotuladas |
| Confiar no painel | Os dados estão em dia? | Dados atualizados em · última movimentação |

## 4. Regras de negócio (contrato)
- **Universos** (não somar entre si): Acompanhadas = 54 (planilha antiga + inclusões) · Radar = 59 (acompanhadas + novas desde 01/09/2026) · Relevantes = marcadas SIM na planilha (19) · Pendentes = radar sem avaliação. **Visão padrão do painel: só as relevantes (SIM)** — decidido em 19/10/2026; o número principal é sempre o de relevantes.
- **Filtro global "relevância = SIM"**: fica. Consequência: acompanhadas não marcadas SIM não aparecem no painel (continuam nos e-mails). Para entrar, precisam ser marcadas SIM na aba "Proposições".
- **Janelas**: "últimos N dias" = dias corridos incluindo hoje, no horário de Brasília. Título, cartão e tabela usam a mesma janela. Sem itens na janela: "Nenhuma movimentação no período", nunca registros antigos.
- **Grão**: proposições por id; pautas agendadas = reuniões distintas (id_evento); proposições em pauta = id_proposicao distintos.
- **Status de pauta/audiência**: situação oficial primeiro (Cancelada), depois data (Agendado/Agendada), depois votação (Votado), senão Encerrado sem votação / Realizada.
- **Atualidade**: "Dados atualizados em" = última carga diária com sucesso; "Movimentação mais recente" = último andamento legislativo. São coisas diferentes.
- **Nível de Atenção v1**: prioridade definida pela ABCS + pauta/audiência nos próximos 14 dias; arquivadas e transformadas em norma em cinza. "Dias parada" não é atraso e não vira vermelho sozinho. Critérios finais — ⚠️ PENDENTE (perguntas 1–3).
- **Premissas**: a planilha "Posicionamento ABCS" é mantida à mão pelo time; dias sem movimentação são calculados na última atualização (08:30, 10:30, 14:30), não no momento da leitura.

## 5. Fora do escopo (v1)
Parâmetros de campo, indicadores pessoais, responsável/prazo da ação, PDF completo, filtro por tema individual, layout de celular — entram só se a Ana pedir.

## 6. Telas
1. **Início** — fila de atenção com motivo; KPIs com janela explícita; datas de atualidade.
2. **Carteira** — Atenção | Proposição | Excerto | Posição ABCS | Órgão atual | Última movimentação | Próxima ação; ordenada por atenção; filtros numa linha; "Ver detalhes" e "Abrir na Câmara".
3. **Proposição** (detalhe) — ementa integral, blocos rotulados, linha do tempo, pautas.
4. **Autores e partidos** — sem mapa; autoria principal da carteira selecionada.
5. **Pautas** — próximas × histórico; status oficial.
6. **Audiências** — "sugeridas por tema"; excerto + texto integral.

## 7. Preferências visuais
Identidade ABCS (verdes #00533a / #09814a / #53af33, azul do logo, texto #14231b, Segoe UI). Cores de atenção separadas do verde da marca, sempre com ícone e texto. Tabelas com destaque por prioridade (pedido da Ana). **Semáforo padrão** (vermelho / laranja / amarelo) para atenção, separado do verde da marca — decidido em 19/10/2026. Proposta de tons em `design/` e no mockup.

## 8. Critérios de aceite
- Contagens iguais entre telas para o mesmo universo; batem com o banco.
- Nenhuma informação só por cor; contraste ≥ 4,5:1.
- Detalhe acessível a partir de qualquer linha, com volta à lista.
- Ana encontra, sem ajuda, o que entra em pauta na semana e a posição da ABCS em cada caso.

## 9. Pendências — perguntas para a Ana
Ver mensagem abaixo; respostas destravam a Fase 3 (Nível de Atenção) e as cores.

> Ana, estamos preparando a nova versão do painel de proposições, com cores que destacam o que precisa de atenção. Para acertar os critérios, gostaríamos de confirmar alguns pontos:
>
> 1. **O que torna uma proposição urgente para você?** R: Urgência para mim é quando é um tema extremamente importante com todas as demais características! Já a prioridade são os temas mais importantes para a ABCS
> 2. **Níveis de prioridade:** R: Acho que não precisa ter níveis de prioridade,  pode ser assim "PL é de interesse? Sim/não, Dos que são SIM e vão ser acompanhados quais desses são PRIORIDADE
> 3. **Proposições arquivadas ou que já viraram lei** R: Sair da lista
> 4. **Contagem principal:** R: apenas as releventes para a suinocultura, entao o numero correto sera sempre os relevantes.
> 5. **Cores:** R: pode ser o padrão; toda a abcs conseguira ver, mas para ela e o time dela sempre servira como fonte de informacao
> 6. **Como você costuma abrir o painel:** R: principalmente no notebook, mas no futuro quero fazer a versao mobile tambem. 

## 10. Regras confirmadas em 20/10/2026 (áudio da Ana + decisão do Erick)
- **Quem aparece no painel:** acompanhadas (a "planilha principal", ~54) + marcadas SIM na aba "Proposições"; saem as marcadas NÃO e as arquivadas/transformadas em norma. Mesma regra do e-mail diário. Substitui o item 4 da seção 9 (com só SIM, 51 das 54 acompanhadas sumiam, inclusive a do rótulo).
- **Prioridade:** sim/não, sem níveis. Fica na aba "Posicionamento ABCS". Hoje só 6 estão marcadas, todas novas: a Ana precisa marcar as prioritárias entre as antigas (ex.: a do rótulo, PL 767/2011 ou PL 3479/2004).
- **Urgente (vermelho):** prioritária que se movimentou nos últimos 7 dias corridos, ou que entra em pauta em até 14 dias.
- **Prioridade (laranja):** prioritária sem movimentação recente ("é prioridade, mas não é urgente").
- **Acompanhamento (sem cor):** todas as demais.
- **Arquivadas e transformadas em norma:** saem da lista.
