# PRD — Módulo de Monitoramento Legislativo ABCS

Data: 28/10/2026. Status: requisitos revisados, implementação não iniciada.

Documento complementar ao [plano de implementação](plano.md). Toda versão nova do PRD e do plano passa pelo agente revisor antes de ir ao usuário. O histórico de revisões e decisões está no fim do documento.

**Princípio de produto (Erick, 28/10/2026):** a tela é sempre limpa e ajuda no dia a dia, sem atrapalhar. Entram só as funções necessárias.
- Explicação de regra não fica como texto fixo: vira dica ao passar o mouse ou vai para o guia de uso.
- Aviso só aparece quando há problema.
- Regras de banco e segurança continuam completas, mas não aparecem na tela.
- Antes de acrescentar tela, indicador, aviso ou controle, a pergunta é: a Ana precisa disso no dia a dia?

## 1. Problema e resultado esperado

Ana usa planilha para decisões institucionais e Power BI para consulta. O painel não permite agir. A coleta já funciona e não deve ser reconstruída.

O módulo da Plataforma ABCS permitirá consultar o monitoramento e registrar decisões com login real, substituindo a planilha e o Power BI no uso cotidiano. O banco legislativo será a fonte única das decisões. Manutenção deve ser viável por uma pessoa.

### Usuários e acesso

| Perfil/capacidade | Permissão inicial |
|---|---|
| Equipe com perfil ativo | Consultar módulo e informações internas |
| Ana | Editar decisões e confirmar movimentos apresentados |
| Administrador da plataforma | Conceder capacidades; sem edição política automática |
| Editor do mailing | Sem edição legislativa automática |
| Reconciliação de agrupamentos com impacto em decisões | No MVP, função SQL auditada executada pelo mantenedor, sem capacidade nem tela próprias (RN03) |
| Sem login ou perfil inativo | Sem acesso interno |

Capacidades podem ser concedidas explicitamente a outros usuários sem alterar as permissões do mailing. Hoje só a Ana edita. O administrador pode, no futuro, conceder ou retirar a edição de outras pessoas sem mudar o código.

### Sucesso e limites

- **Entrega 1, que substitui a planilha:** Ana avalia, posiciona, prioriza e inclui proposições no sistema, sem Sheets. As consultas de agenda, audiências e autoria continuam no Power BI, pelo link público "Publicar na Web" inserido no site. Decisão de 28/10/2026: não há licença Pro, os riscos foram aceitos e o painel não mostra dados sensíveis.
- **Entrega 2, que substitui o Power BI:** as seis áreas passam a ser telas nativas e o Power BI é desligado.
- Toda decisão salva fica disponível imediatamente nas telas nativas e tem autoria e histórico. Enquanto o Power BI existir, ele mostra as decisões com o atraso da sua atualização agendada. A página dele diz isso numa frase, e o próprio relatório mostra "Painel atualizado em".
- Migração preserva campos, vazios e conflitos; as automações deixam de depender da planilha na Entrega 1.
- Não podem ser obtidos anonimamente: as tabelas de `gestao`, o histórico de alterações, a autoria das decisões, o parecer e as observações. O que o painel público já mostra (carteira, relevância consolidada, posição e prioridade) continua público por decisão do Erick, por meio de uma projeção com campos fixos (seção 5).
- Sem novos comentários, responsáveis, canais de notificação, app nativo, agente de IA ou infraestrutura de BI nova. O MVP usa o que o Senado já tem em produção (seção 2). Agenda do Senado e inclusão manual do Senado seguem o roteiro próprio e não são requisitos do MVP.

## 2. Estado atual e evidências

Levantamento de 28/10/2026: API Google Sheets, MCP do n8n, código do pipeline e PBIP versionado. O relatório remoto e a configuração ativa de hospedagem não foram auditados. Contagens são um snapshot, não uma meta permanente.

| Fonte | Constatação |
|---|---|
| Proposições | 350 registros: 81 SIM, 268 NÃO, um pendente; 54 acompanhadas |
| Posicionamento ABCS | 81 linhas, todas correspondentes. Em 28/10/2026 a aba passou a ter a coluna `id_proposicao` (preenchida nas 81 linhas): as colunas são `id_proposicao, identificacao, ementa, posicao_abcs, acao, parecer_abcs, prioridade, observacoes`. A migração usa o id primeiro; o Power BI ainda resolve identificação → `chave_projeto` com sufixo de casa e deixa sem ligação (chave negativa) as identificações ambíguas entre casas (`dim_posicionamento_abcs.tmdl`). Posição em 68, ação em 39, parecer em 27, observações em 38 |
| Prioridade | 16 SIM, 12 NÃO, 53 vazios |
| Legado | 151 linhas históricas e backup de posicionamento de 20/10/2026 |
| n8n | Três fluxos legislativos publicados: agendamento, atualização/alertas e inclusão manual |
| PBIP | Início, Carteira, Proposição, Pautas, Audiências e Autores e partidos. Lê o banco pela Data API com a chave `anon` (`fnSupabaseGold`, perfil `api`) e lê a planilha para relevância e posição. `em_painel` usa relevância por id (relação 1:1 com `dim_relevancia`) e encerramento pela situação da versão. Publicado em "Meu workspace", com link "Publicar na Web" também no cabeçalho do README público. Não há licença Pro |
| Senado (código em `main`) | Fases 1 a 4 mescladas em `main` (`017da1a`, `28d9a2a`). O deploy em produção em 28/10/2026 está registrado nas notas do projeto, e não no repositório: o README ainda marca o Senado como pendente e precisa ser atualizado. Conteúdo: `casa` CD/SF, chave do Senado = 1e9 + id nativo, proposições do Senado com keywords sem acento, `dim_senador`, vínculo entre as casas (`silver.proposicao_vinculo`: identificação, "Revisora", MPV e manual), `chave_projeto` por grupo, 9 acompanhadas do Senado e 2 vínculos manuais na seed, carga diária com falha não bloqueante (`incremental_senado`, `reconciliacao_senado`) e `ultima_carga_senado` em `api.vw_ultima_carga`. O n8n já trabalha por grupo, com SIM prevalecendo e a casa no e-mail e na planilha |
| Senado (pendente) | Fase 5, agenda (`executar_pautas_senado` ainda é stub e `eventos_senado` nunca é registrado); fase 6, inclusão manual do Senado no n8n; fase 7, Power BI (segmentação por casa, KPIs por projeto, "Adiada"); fase 8, documentação |

O agendador dispara carga diária às 07h17 e pautas às 10h e 14h, em Brasília. O fluxo principal lê avaliações após receber o webhook da carga. Ele também **escreve** na aba Proposições, acrescentando as novas pendências de avaliação com a coluna `casa`. O intervalo de 15 minutos pertence à inclusão manual, que lê a aba Proposições e grava em `silver.proposicao_acompanhada`. NÃO efetivo suspende alertas inclusive de acompanhadas (regra reafirmada em 28/10/2026), mas não apaga retenção de coleta. Os três fluxos não usam posição ou prioridade para selecionar alertas.

## 3. Requisitos funcionais

### RF01 — Sessão e autorização

Usar o login existente da plataforma. Validar identidade, perfil ativo e capacidade no servidor em toda leitura ou escrita protegida, inclusive histórico. Não confiar em papel ou autor informados pelo navegador.

**Decisão (28/10/2026): autorização no servidor, sem RLS por pessoa no banco legislativo.** O banco legislativo não conhece pessoas. Ele limita o papel técnico da aplicação a funções e leituras delimitadas e grava o ator informado pelo servidor. Risco aceito: um defeito ou comprometimento do servidor permite gravar em nome de qualquer usuário. Os controles são credencial exclusiva da aplicação, funções com validação de domínio e auditoria imutável. As capacidades (ex.: editar decisões) ficam junto aos perfis, no banco da plataforma. A confirmar na fase 1, lendo o código de `banco-de-contatos-mailing`. A perda de acesso de um perfil inativado deve valer no próximo pedido ao servidor, e não só quando a sessão expirar.

### RF02 — Início

**Entrega 1:**
- **Três indicadores**, cada um levando à lista equivalente:
  - urgentes;
  - pendentes de avaliação;
  - projetos monitorados (= carteira ativa).
- **Fila de atenção:** as prioridades urgentes, com o motivo de cada uma. Quando está vazia, uma linha curta.
- **Últimas movimentações em 30 dias** (hoje e os 29 dias anteriores, em Brasília): a mais recente de cada projeto da carteira ativa, até 10 itens, com "ver todas", que abre a Carteira ordenada por data.
- **Fora do Início:** agenda, prioridades e casos a conferir. A agenda está no menu Painéis.
- Regras de contagem (RN08) ficam em dica, não em texto fixo.
- **Entrega 2:** reuniões e audiências agendadas, com o rótulo "até dd/mm". É a mesma janela da urgência por pauta (RF09).

**Fila de avaliação:**
- SIM/NÃO na própria linha, em sequência, com atalhos de teclado (setas, S, N e Enter para abrir o detalhe), lembrados numa dica pequena;
- cada avaliação tem o seu próprio "Desfazer", que é recusado se a decisão mudou depois;
- a fila é calculada pelo estado de avaliação: uma proposição que volta para Pendente no detalhe volta para a fila;
- o detalhe de uma pendência abre antes da decisão, pelo id da proposição. O UUID nasce na primeira decisão (RN03);
- o texto diz "SIM para marcar como relevante", sem confundir relevância com acompanhamento ou com a posição "Acompanhar";
- no perfil de leitura, os botões não aparecem.

### RF03 — Carteira e filas

Busca por identificação ou ementa. Filtros visíveis: prioridade e posição. Situação, órgão, palavra-chave e casa ficam em "Mais filtros", recolhido. Colunas: identificação (com chips de atenção só quando houver), trecho da ementa, posição, órgão, última movimentação, ação e link oficial.

**Abas:** Ativas e Histórico. No Histórico, o motivo (encerrado, marcado NÃO, parado há mais de 12 meses, sem data) aparece na própria linha.

As pendentes ficam na tela Avaliação. Os casos a conferir não ficam na navegação da Ana: são uma lista do mantenedor (rota fora do menu ou consulta SQL), e a Ana vê o aviso dentro do projeto afetado.

**Busca global:** cai em Ativas e indica "Também em: Histórico (n), Avaliação (n)" quando houver.

Explicações de regra ficam em dica nas abas, não em texto fixo.

**Endereço da página:** aba e filtros ficam no endereço, para voltar e recarregar no mesmo recorte.

**Sem tramitação carregada:** a última movimentação aparece como "Sem data", nunca como uma data artificial. Prioridade sem data continua na carteira ativa; não prioritária sem data vai para o histórico.

**Identificação:** é um link de verdade, que abre o projeto pelo teclado e em outra aba.

**Exportação:** baixa um CSV com o mesmo recorte da lista (aba e filtros), sem parecer nem observações.

### RF04 — Detalhe e decisões

Identificar o projeto por UUID e discriminar versões/IDs por casa. Exibir ementa integral, autoria, partido/UF, situação, órgão, keywords, tramitações recentes primeiro, pautas e links oficiais. Permitir editar relevância, posição, prioridade, ação, parecer e observações; histórico informa autor, data e alterações.

Termos fixos: "versões legislativas" são as da Câmara e do Senado; "revisão da decisão" é o número usado no controle de concorrência.

**Concorrência (aprovada no mockup):**
- O salvamento compara a revisão de quando a pessoa abriu com a revisão atual.
- Se forem diferentes, nada é gravado e o botão Salvar fica bloqueado até uma escolha explícita.
- O aviso mostra, por campo: o valor quando a pessoa abriu, o que a outra pessoa salvou e o rascunho. Também diz em quais campos aplicar o rascunho substituiria o que a outra pessoa gravou.
- As opções são duas:
  - "aplicar só as minhas alterações sobre a versão atual", que leva só os campos que a pessoa mudou e toma a versão atual como nova referência;
  - "descartar as minhas".
- Se houver outra mudança depois disso, um novo aviso aparece.

**Rascunho:**
- Erros de salvamento preservam o texto digitado.
- Sair do projeto com alterações não salvas pede confirmação: "continuar editando" ou "descartar e sair".
- Cada projeto tem o seu próprio rascunho.

**RN05:** a transição que a pessoa pretende é resolvida primeiro. Marcar NÃO numa prioridade pergunta "Marcar como NÃO e retirar a prioridade?" e explica o efeito na carteira e nos alertas. Marcar prioridade sem SIM pede a confirmação para marcar SIM. Cancelar não altera nada.

**Perfil de leitura:** vê as decisões como texto, e não como campos desativados.

**O que a tela não mostra:**
- identificador técnico do projeto (a revisão aparece só dentro do aviso de conflito);
- notas fixas de regra;
- chips de palavra-chave no cabeçalho;
- filtro "só as maiores": o ponto colorido na movimentação maior já basta.

**O que só aparece quando precisa:**
- o quadro de pautas, se houver pauta;
- a agenda do Senado ainda não coletada, só em versão do Senado;
- o histórico, recolhido como "Histórico (n)";
- os avisos de conflito e de erro de gravação.

Movimentações maiores anteriores à referência de urgência não entram na lista a confirmar e não ganham anotação.

### RF05 — Pautas (Entrega 2)

Mostrar reuniões agendadas, total de eventos e itens votados/cancelados com unidades explícitas. Filtrar por proposição, comissão, situação e relator. Exibir data/hora, casa, órgão, proposição, relator/partido, status e resultado. Separar próximas de histórico e preservar canceladas/adiadas na consulta histórica.

### RF06 — Audiências (Entrega 2)

Mostrar total e agendadas, filtro por palavra-chave e tabela com data/hora, casa, órgão, assunto, palavras-chave, status e link oficial. Informar que o matching é temático; não inferir relação com uma proposição.

### RF07 — Autores e partidos (Entrega 2)

Manter gráficos por ano de apresentação, tipo, UF e partido, ranking de autores e filtro de prioridade. Mostrar autores, partidos e UFs distintos disponíveis e quantidade de versões de origem Senado, identificada por `casa = SF`.

O universo é de versões legislativas da carteira filtrada, claramente rotulado; valores ausentes são indicados sem inventar autoria. Contagens distintas de partidos/UFs excluem ausências. Partido e UF são atuais, não históricos da apresentação. Clique em categoria leva à carteira com o filtro correspondente, mostrando a distinção entre versões e projetos.

### RF08 — Inclusão manual

Aceitar identificação ou link oficial validado da Câmara, reutilizando resolução e modo de carga existentes. Não buscar URLs arbitrárias fornecidas pelo usuário. Casa Senado fica explicitamente indisponível para inclusão até sua integração, sem impedir consulta de versões já carregadas.

A fase 6 do roteiro do Senado (inclusão manual do Senado) não deve ser construída no fluxo do n8n que lê a planilha, porque esse fluxo será substituído. Ela entra depois, direto na inclusão do sistema. Até lá, as 9 acompanhadas do Senado da seed e os gêmeos ligados às monitoradas da Câmara já são carregados todo dia.

Persistir solicitação, solicitante, estado e resultado. A solicitação não expira após duas horas; tentativas têm espaçamento controlado e deduplicação, sem repetição contínua ilimitada.

**Ciclo do pedido (esclarecimento da avaliação do Astra):**
1. **Solicitada:** o pedido foi gravado.
2. **Em processamento, etapa "localizando":** o n8n resolve a identificação ou o link para o id da Câmara. É a **resolução**. Um "não encontrado" é falha permanente, sem tentativa automática.
3. **Em processamento, etapa "carregando":** com o id resolvido, uma função de `gestao` grava a acompanhada em `silver.proposicao_acompanhada`, com `origem = 'sistema'`. Isso é a **preparação para a coleta**. Só depois o n8n dispara `modo=inclusao`. Não há dependência circular: a projeção usa o id resolvido, e não o pedido concluído.
4. **Concluída:** os dados estão disponíveis na base de consulta, ou seja, a proposição aparece em `api`.
   - A cada webhook de sucesso, de qualquer modo, o n8n marca como "concluída" todo pedido em "carregando" cujo `id_proposicao` já está em `api.vw_monitoramento`. A regra é idempotente.
   - Isso é necessário porque o sucesso do job não prova que um pedido específico chegou. `pipeline_inclusao.py` carrega todas as acompanhadas ausentes e só falha se nenhuma carregar, e a carga diária também carrega acompanhadas.
   - Pedido em "carregando" há mais de 6 horas vira falha temporária, com nova tentativa. Isso cobre o disparo de `modo=inclusao` que o GitHub cancela na fila quando chega outro disparo (`concurrency` do `pipeline.yml`).
   - O estado do e-mail fica em `gestao.inclusao_manual`. `silver.proposicao_acompanhada.confirmada_em` deixa de ser preenchido para pedidos novos.
5. **Falhou:** guarda o erro e a tentativa. Falha temporária ganha tentativas automáticas espaçadas, com limite; esgotado o limite, fica "falhou" à espera de "Tentar agora".

**E-mail de confirmação:** é um resultado independente, com três estados (aguardando, enviado, falhou com reenvio). Uma falha do e-mail não muda o estado de uma inclusão já concluída. Na tela, o e-mail só aparece quando falhou, com "Reenviar".

**Tela:**
- um campo rotulado "Identificação ou link da Câmara", sem seletor de casa;
- a mensagem de resultado;
- a lista de pedidos com estado e link para o projeto, sem colunas "Quem" e "Tentativas" (as tentativas entram no texto do erro);
- pedidos concluídos há mais de 7 dias ficam recolhidos.

**Identidade e duplicidade:**
- A chave de identidade é a casa mais a identificação resolvida. Link e identificação da mesma proposição dão o mesmo resultado. Número e ano iguais em casas diferentes não são a mesma proposição.
- Um pedido igual a um que falhou retoma o existente, sem criar outro.
- Cada pedido tem no máximo uma execução em andamento e uma conclusão.

**Proposição que já existe:** a resposta mostra o estado atual dela, sem reativar nada sozinha e sem criar projeto duplicado:
- na fila de avaliação: decidir por lá;
- marcada NÃO: para voltar a acompanhar, é preciso mudar a relevância no projeto;
- no histórico ou na carteira ativa: informa onde ela está.

**Inclusão nova:** entra como SIM e acompanhada, mas isso não garante a aba Ativas. Vale o corte de 12 meses, com a exceção da prioridade. A mensagem de conclusão diz onde a proposição ficou.

O campo de uma nova inclusão não é apagado quando a lista de pedidos se atualiza.

### RF09 — Urgência e confirmação

Um projeto prioritário ativo é urgente por movimento elegível não confirmado ou por pauta agendada no intervalo do início de hoje ao início do 15º dia seguinte, exclusivo, em Brasília. Mostrar o motivo ou ambos.

Movimento elegível é só uma **movimentação maior** (decisão do Erick, 28/10/2026). Exemplos: parecer, inclusão em pauta, votação, mudança de relator ou de situação. Movimentos de rotina (recebimento, encaminhamento, publicação) aparecem no histórico, mas não geram urgência nem pedem confirmação. A lista do Apêndice A foi validada pela Ana em 28/10/2026.

Ana confirma somente IDs de movimentos apresentados, com efeito compartilhado e autoria. Nenhuma movimentação vem pré-selecionada. Um botão "Selecionar todas as apresentadas" agiliza, e o botão de confirmar mostra quantas serão confirmadas (aprovado no mockup). Movimento que chega durante a confirmação continua pendente. Abertura da página e envio de e-mail não confirmam leitura. Pauta na janela mantém urgência mesmo após confirmação; cancelamento/reagendamento atualizam o motivo.

Carga inicial/backfill não abre urgência. Estabelecer baseline na migração e ativação da prioridade. A referência de urgência de cada projeto é a mais recente entre a data da migração e a data em que ele virou prioridade. Movimentações maiores anteriores a essa referência não geram urgência e não entram na lista a confirmar. Ocorrências operacionais posteriores exigem identidade estável e data oficial posterior à referência. Correções antigas não reabrem urgência no MVP.

### RF10 — Atualização e falhas

**Com tudo certo:** uma linha só, por exemplo "Dados atualizados hoje às 07:39", com a última coleta diária bem-sucedida.

**Com falha:** um aviso vermelho que diz o que falhou (coleta da Câmara ou do Senado, base de consulta) e qual é o último estado consistente.

**Fontes:** `api.vw_ultima_carga` tem `ultima_carga_diaria`, `ultima_carga_pautas`, `ultima_carga_senado` e `ultima_carga_pautas_senado`. A atualização da base de consulta (`api_cache`) é conferida à parte. A agenda do Senado ainda não coletada só aparece no projeto de uma versão do Senado.

**Power BI:** o site não mostra a hora nem a falha de atualização do Power BI. Sem licença Pro e com o relatório em "Meu workspace", o site não consegue ler o histórico de atualizações, e o "Publicar na Web" ainda tem cache próprio. A hora aparece dentro do relatório, como "Painel atualizado em", calculada na própria atualização (cuidado com o UTC do Service, como já se faz com `data_referencia`).

O salvamento das decisões tem confirmação própria, e abrir a página não atualiza dados.

## 4. Regras de negócio e dados

### RN01 — Fonte única

Decisões ficam em `gestao`, fora dos caches. Cargas e backfill não sobrescrevem decisões, textos ou confirmações humanas. Processamento técnico (n8n) só atualiza solicitações de inclusão. Ocorrências elegíveis e associações são calculadas por contratos (views), sem gravação técnica. Não haverá sincronização bidirecional permanente com planilha.

### RN02 — Campos e domínios

- Relevância: pendente, SIM, NÃO.
- Posição: Acompanhar, A favor, Contra, A favor com ressalvas, Em análise; vazio significa ausência de posição.
- Prioridade: SIM, NÃO ou não informada, sem converter ausência em NÃO.
- Ação, parecer e observações: campos textuais separados; preservar conteúdo na migração.
- Acompanhamento na carteira não é sinônimo da posição institucional Acompanhar.

### RN03 — Projeto e versões

UUID persistente identifica a unidade de decisão. Associação mantém os IDs legislativos existentes, `casa` e IDs de origem; conservar `chave_projeto` como agrupamento derivado, não identidade permanente.

Ciclo de vida do UUID:
1. **Criação:** o UUID nasce só quando há decisão, inclusão ou acompanhamento. Quem cria é a migração ou uma função da aplicação, nunca o pipeline. Ele não é criado para as ~15 mil proposições da bronze.
2. **Vínculos novos:** o pipeline continua dono de `silver.proposicao_vinculo` e da `chave_projeto`. O pipeline não chama `gestao`. Os casos de associação são detectados por contrato SQL, conforme a regra única do item 6.
3. **Até a reconciliação:** cada UUID mantém sua decisão.
4. **Reconciliação no MVP:** é feita por função SQL auditada, executada pelo mantenedor. Não há tela de reconciliação nem capacidade própria até haver volume que a justifique (hoje, 6 das 54 acompanhadas têm gêmeo).
5. **Caso inverso:** um UUID com versões que caíram em grupos diferentes também vai para a conferência. Isso acontece quando a transformação do Senado apaga e regrava os vínculos não manuais (`transform_senado_to_silver.sql`). Acontece também quando a versão da Câmara ainda não está na silver, e a do Senado fica por um tempo com `chave_projeto` própria.
6. **Regra única de associação**, calculada na leitura pelos contratos, sem gravação e por isso sem auditoria própria. Só a migração, a aplicação e a reconciliação do mantenedor gravam em `projeto_proposicao`.
   - Ela é **inequívoca** só quando a versão nova cai num grupo em que todas as versões já associadas apontam para **um único** UUID.
   - Vão para a conferência, sem associação automática:
     - grupo com versões de UUIDs diferentes;
     - versão já associada a um UUID que agora está num grupo diferente das outras versões desse UUID (inclui a versão que ficou sozinha num grupo novo).
   - Na lista do mantenedor, o caso de dois UUIDs com decisões diferentes aparece como dois projetos lado a lado, cada um com a sua decisão.
7. **Sem chave estrangeira:** `projeto_proposicao` não tem FK para `silver.proposicao`, porque a reversão do Senado apaga ids ≥ 1e9 e as seeds já admitem id ausente.
8. **Pendente sem UUID:** a rota do sistema e o link do e-mail aceitam `id_proposicao`. O UUID é resolvido pelo grupo ou criado na primeira decisão.
9. **Seed recria vínculos:** os vínculos manuais e as acompanhadas `planilha_antiga` da seed são recriados a cada `setup_db.py`. Para corrigi-los, é preciso editar a seed.

Relevância e posição valem para as versões do projeto nas duas casas. Igual número/ano em casas distintas não prova vínculo. Fusões/separações exigem reconciliação pelo mantenedor quando afetarem decisões; preservar histórico e o UUID antigo como alias. Não fundir textos nem separar decisões automaticamente após desaparecimento de vínculo.

### RN04 — Migração

Consolidar relevância por grupo: SIM prevalece; sem SIM, NÃO prevalece; sem avaliação, pendente. Prioridade incompatível ou divergência de posicionamento/textos vira conflito para resolução antes da virada, sem descarte silencioso.

Quando a regra resolve sozinha e quando ela vai para a Ana (esclarecimento):
- **Resolve sozinha:**
  - Divergência só de relevância entre as versões de um mesmo grupo, já ligadas por `chave_projeto` na data da importação. SIM prevalece, como o n8n já faz desde a fase 2 do Senado e por decisão do Erick de 27/10/2026. A importação registra no histórico que a relevância foi consolidada pela regra.
- **Vai para a Ana:**
  - divergência de posição, prioridade, ação, parecer ou observações entre versões do grupo;
  - prioridade SIM com relevância NÃO no resultado;
  - identificação ambígua entre casas na aba Posicionamento.

Usar as abas atuais como fonte; legado/backup são evidência de conferência. Ensaiar importação idempotente, verificar totais por campo e preservar vazios. Snapshots privados e conteúdo político não entram no repositório público.

A migração liga cada linha da aba Posicionamento pelo `id_proposicao` quando preenchido (validado no banco); um id que discorda da identificação vira conflito. Sem id, usa a `identificacao` pela regra do Power BI, com sufixo de casa, e toda identificação ambígua entre casas vira conflito. Linhas da aba Proposições cujo id não está no monitoramento atual não são conflito: a decisão é importada e a linha vai para uma lista do mantenedor.

Conflitos são casos em que a planilha diz coisas diferentes para o mesmo projeto. Exemplos: versões com relevância ou posição diferentes, prioridade SIM em proposição NÃO, textos divergentes para o mesmo projeto. São resolvidos na planilha, antes do congelamento, a partir de uma lista preparada pelo mantenedor. A Ana decide cada caso (decisão do Erick, 28/10/2026). A importação final, no congelamento, repete a detecção de conflitos, porque a planilha continua sendo editada depois do ensaio. Com um conflito em aberto, a virada não acontece. A seed atual já inclui 9 acompanhadas do Senado (ids ≥ 1e9) e 2 vínculos manuais, e a importação agrupa pelas versões das duas casas.

### RN05 — Edição coerente

Nas novas operações, marcar prioridade exige SIM na mesma transação, com confirmação explícita quando necessário. Marcar NÃO em uma prioridade exige confirmar a retirada da prioridade. Desistir da confirmação não altera os dados. Atualização, versão e auditoria são atômicas.

### RN06 — Elegibilidade e corte

Elegível: acompanhada (planilha antiga ou incluída), relevante SIM ou prioridade SIM, excluindo relevância NÃO e encerramento efetivo. Carteira ativa: elegível e com última movimentação máxima do grupo nos últimos 12 meses de calendário em Brasília, ou prioridade ativa independentemente de idade.

Uma inclusão pelo sistema marca o projeto como SIM e acompanhado, como faz hoje a inclusão pela planilha. Sem data, não prioritárias ficam no histórico. A fila de avaliação mantém a regra de radar independente. Agenda futura de elegíveis não aplica o corte de inatividade. Corte não remove histórico nem suspende retenção de coleta. Encerramentos a conferir ficam na lista do mantenedor, independente desses filtros, sem prioridade/urgência automática.

### RN07 — Encerramento entre casas

As versões conhecidas são as do grupo em `silver.proposicao_vinculo`, já em produção. Encerramento efetivo requer todas as versões conhecidas efetivamente encerradas, sem indicação de continuidade por remessa. Qualquer versão em tramitação mantém o projeto ativo. Arquivamento por remessa não encerra o projeto. Divergências ou destino ainda não carregado geram conferência, sem ocultação silenciosa. Projetos efetivamente arquivados ou transformados em norma vão somente ao histórico, inclusive prioritários.

### RN08 — Unidades dos indicadores

Cards operacionais contam projetos distintos por UUID. Prioridades inclui urgentes; fila não duplica o projeto. Análises de autoria/distribuição contam versões legislativas com denominador explícito. Reuniões são eventos distintos; itens de pauta têm unidade própria. Lista e gráfico compartilham filtros e explicam quando várias versões representam um projeto.

### RN09 — Persistência mínima

| Entidade | Responsabilidade |
|---|---|
| `projeto` | Identidade estável; o alias da reconciliação é uma coluna (`substituido_por`) até haver volume |
| `projeto_proposicao` | Associação às versões existentes |
| `decisao_projeto` | Campos humanos, versão, autoria e datas |
| `inclusao_manual` | Pedido, solicitante, estado, tentativas, resultado e erro |
| `historico_alteracao` | Operação, diferenças, origem, ator e data |
| `confirmacao_movimentacao` | Tramitações confirmadas, pela chave estável `(id_proposicao, sequencia)` de `silver.tramitacao`, com autora e data |

A ocorrência elegível não é tabela: é um contrato (view) sobre `silver.tramitacao`, com tipo maior (Apêndice A), data posterior à referência de urgência e prioridade ativa. Assim nenhum processo técnico precisa gravar ocorrências.

Identificar ator por emissor de identidade e UUID validado pelo servidor; não criar FK para o Auth do outro banco. Novos instantes de gestão usam `timestamptz`; timestamps legados são interpretados conforme a origem e o horário de Brasília, sem descartar offsets implicitamente.

## 5. Integrações e requisitos não funcionais

### Integrações

- Manter pipeline Python e disparos GitHub Actions pelo n8n, com agenda atual.
- Publicar contratos SQL privados para elegibilidade, carteira, pendências e urgência. Aplicação e automações usam as regras pertinentes.
- E-mails conservam relevância, precedência SIM no grupo e checkpoints após sucesso ou ausência de itens; não herdam corte visual nem exigência de prioridade.
- Confirmação de inclusão por e-mail é diferente de confirmação de movimento visto.
- `proposicao_acompanhada` passa a ser só projeção/retenção operacional, sem segunda fonte humana editável. Ela continua sendo o que o pipeline lê para carregar e recarregar acompanhadas (`pipeline_inclusao.py`, `extract_incremental.py`) e o que mantém na gold as linhas sem keyword (`grupo_acompanhado`). Por isso, depois da virada, uma função de `gestao`, chamada pelo n8n assim que o id da Câmara é resolvido e antes de disparar `modo=inclusao`, grava a acompanhada com `origem = 'sistema'` (RF08). O n8n deixa de gravar `origem = 'inclusao_manual'` direto. `setup_db.py` continua aplicando `seed_acompanhadas.sql` só como retenção de coleta (`ON CONFLICT DO NOTHING`), sem efeito sobre decisões.
- Cliente não dispara GitHub nem executa SQL arbitrário. n8n consulta solicitações persistentes e reutiliza resolução/carga existentes.
- Os e-mails de alerta trazem link direto para o projeto no sistema e passam a mostrar o status "Adiada" (pendência da fase 1 do Senado).

**Consumidores da planilha e ordem da virada (Entrega 1).** Os passos 1 a 5 têm reversão registrada no plano, válida só até o passo 6. Depois que a Ana edita no sistema, voltar o n8n para a planilha usaria dados velhos, e só resta o rollback da aplicação, que mantém o banco.

| Consumidor | Lê da planilha | Escreve na planilha | Depois da virada |
|---|---|---|---|
| n8n Monitoramento → Google Sheets (`4F6Y2cOHhqNuhdYm`) | Relevância (por grupo) | Novas pendências na aba Proposições, com `casa` | Lê `gestao` pelos contratos e deixa de escrever |
| n8n Inclusão manual (`23CyodhPlORNJ4xS`) | Linhas novas da aba Proposições, a cada 15 min | Estado da inclusão | Lê `gestao.inclusao_manual`; o gatilho da planilha é desativado |
| n8n Agendador (`0sieqPDvsqoZcs31`) | — | — | Sem mudança |
| Power BI | Relevância e posição (abas Proposições e Posicionamento ABCS) | — | Lê a projeção do painel público (colunas fixas) |

Ordem:
1. congelar a planilha (proteção de edição);
2. importação final com conflitos zerados;
3. publicar o fluxo principal lendo do banco;
4. publicar a inclusão lendo do banco;
5. publicar o Power BI lendo do banco;
6. liberar o sistema para a Ana.

**Power BI público (Entrega 1).** O relatório continua publicado pelo "Publicar na Web", e o código de inserção é colocado numa página do site da plataforma.
- Decisão do Erick, 28/10/2026: não há licença Pro, os riscos foram aceitos e o painel não mostra dados sensíveis.
- Consequência registrada: quem tiver o endereço vê o painel sem login. Estar dentro do site não protege o conteúdo, e o link continua no README e no histórico git.
- Por isso, o painel só recebe campos que podem ser públicos (projeção abaixo).
- O relatório continua em "Meu workspace". Nenhuma mudança de licença ou de capacidade é necessária.

O modelo muda só o mínimo, porque será descartado na Entrega 2. Ele passa a ler, pela `anon` como hoje, uma projeção única em `api`. A projeção tem uma linha por versão legislativa e é chaveada por `id_proposicao` (a versão), com `uuid_projeto` para agrupar as versões de um projeto. Versão sem UUID (sem decisão) tem `uuid_projeto` nulo e é contada pela `chave_projeto`. A projeção lê só `api_cache`, nunca `gold`: a `anon` tem `statement_timeout` de 3 s e as views gold levam de 2 a 4 s. A parte que depende do relógio (corte de 12 meses) é calculada na view, como já se faz com `status_alerta`. A lista fechada de campos foi aprovada com o mockup em 28/10/2026 e é travada por teste:
- `id_proposicao` e `casa`;
- `uuid_projeto`;
- relevância, posição e prioridade já consolidadas, sem ação, parecer, observações, histórico nem autoria das decisões;
- `em_carteira`, calculado pelo mesmo contrato SQL das telas.

O DAX deixa de recalcular regras e conta projetos por `uuid_projeto`, e o status "Adiada" passa a aparecer. O relatório ganha "Painel atualizado em" (RF10). Na página do site, o painel inserido e uma frase só: "Decisões salvas aparecem aqui na próxima atualização do painel." As abas são as do próprio relatório. A segmentação por casa só entra se for trivial. O restante da fase 7 do Senado é absorvido pela Entrega 2.

### Segurança

Servidor valida pessoa e capacidade; banco legislativo aplica privilégios da credencial técnica. Testar ambas as fronteiras. Papel da aplicação tem SELECT delimitado e EXECUTE necessário, sem DDL ou escrita geral. Funções privilegiadas usam proprietário restrito, nomes qualificados, `search_path` fixo e execução revogada de papéis não autorizados.

Usar TLS e pooler compatível; credenciais técnicas ficam no servidor. A aplicação recebe credencial nova e própria. O Power BI continua com a `anon`, e pipeline e n8n mantêm as suas. Nenhuma chave administrativa geral é usada para contornar o login. Não versionar segredos, dados reais ou snapshots privados nem registrá-los em logs.

Anon não acessa `gestao`, o histórico, a autoria das decisões, o parecer nem as observações. A única exposição deliberada é a projeção do painel público, com campos fixos. Corrigir grants e privilégios futuros no SQL fonte, inclusive `gold`, e verificar novamente após `setup_db.py`.

Situação atual:
- `schema_api.sql` concede USAGE e SELECT em `api` à `anon` a cada `setup_db.py`, porque o schema é recriado.
- Na `gold`, o SELECT de `anon` e `authenticated` vem do padrão do Supabase.
- A chave `anon` não está no repositório (filtro `segredos-pbi`).
- O Power BI usa a `anon`.

Com o link público mantido, não há troca de credencial do Power BI nem revogação da `anon`. Continuam valendo:
1. A projeção do painel fica em `api` e recebe o SELECT da `anon` pelo GRANT que já existe. Um teste fixa a lista de colunas, para que nenhum campo interno entre por engano.
2. Tabelas de `gestao` e contratos ficam em schemas que nunca são expostos pela Data API e não recebem grant de `anon`/`authenticated`. Isso vale inclusive depois de cada `setup_db.py`.
3. O cadastro aberto do Auth do projeto legislativo fica desligado. Sem isso, qualquer pessoa obtém o papel `authenticated` com a chave pública.
4. Os grants do papel da aplicação sobre objetos recriados ficam no SQL que os recria, porque o DROP CASCADE os apaga a cada `setup_db`.

`gestao` fica fora de `api`/`api_cache` e de dependências destrutivas do DROP CASCADE desses schemas.

A DDL fica neste repositório, sem dados, em duas partes:
- **Tabelas de `gestao`:** aplicadas por `setup_db.py` antes de `drop_api.sql`, sem DROP. Evoluem com `ALTER … ADD COLUMN IF NOT EXISTS`, porque `CREATE TABLE IF NOT EXISTS` não aplica mudança.
- **Contratos:** cruzam `gestao` com `api_cache` (de preferência; `gold` só onde o tempo de resposta permitir). Ficam num arquivo aplicado depois de `schema_api.sql` e recriado a cada `setup_db`, num schema próprio que nunca é exposto à `anon` nem incluído nos schemas da Data API.
- **Projeção do painel público:** é a única view de `api` que lê `gestao`. É recriada no mesmo arquivo e tem colunas fixas.

Testes no estilo de `tests/test_segredos.py`, nos dois sentidos:
- nada em `api`/`api_cache`/`gold` lê `gestao`, exceto a projeção do painel, cujas colunas são conferidas;
- nada que dependa de `api_cache`/`gold` fica fora do arquivo recriado;
- os grants esperados existem depois de cada `setup_db`. Os scripts de importação leem a planilha pela API e não versionam snapshot.

### Operação e experiência

Reutilizar stack, componentes, CI e hospedagem da plataforma; evitar serviço novo para manutenção individual. Aplicação é web hospedada consultando o banco, sem promessa de execução offline ou banco local no dispositivo.

A hospedagem ativa e o modo do pooler (sessão ou transação) são verificados na fase 1, antes de definir os contratos, porque o modo transação muda o comportamento de instruções preparadas e de `SET`.

Uso só em computador (decisão de 28/10/2026). Celular fica fora do escopo. Paginar consultas e não carregar toda a Silver no navegador. Erros oferecem recuperação e preservam edição. Mudanças são aditivas e isoladas do mailing. Não fixar SLA numérico sem medição; validar os fluxos reais no piloto.

## 6. Implantação, validação e aceite

### Fases

1. **Fundação:**
   - projeto de homologação com cópia dos dados oficiais (públicos);
   - conexão restrita da aplicação;
   - projeção do painel público com campos aprovados pelo Erick e cadastro aberto do Auth desligado (seção 5);
   - `gestao` e contratos;
   - importação ensaiada;
   - lista de conflitos entregue para resolução na planilha;
   - verificação da hospedagem e do pooler;
   - localização das capacidades no banco da plataforma.
2. **Mockup navegável, antes de qualquer código da aplicação.** Concluído: aprovado pelo Erick em 28/10/2026, na versão 2, depois da avaliação do Astra. Escopo:
   - protótipo interativo com dados fictícios, sem banco nem login real;
   - o Erick testa as funcionalidades da Entrega 1 e sugere mudanças:
     - fila de avaliação com SIM/NÃO na linha;
     - Carteira com filtros e exportação;
     - Projeto com edição, conflito de versão, confirmação de prioridade/NÃO e histórico;
     - inclusão com estados;
     - urgência e confirmação de movimentos;
     - frescor e falha;
     - página do site com o Power BI público inserido;
   - itera até o Erick aprovar; depois, se ele quiser, mostra à Ana;
   - as decisões do mockup atualizam PRD e plano antes da construção;
   - o mockup segue a identidade visual da plataforma e fica fora do repositório público se trouxer qualquer conteúdo real;
   - depois da aprovação, passou pela simplificação do princípio de produto (28/10/2026);
   - faixa de protótipo, "Simular cenários" e botão "Sugestão" são ferramentas do mockup, e não do produto.
3. **Entrega 1, construção:**
   - edição, histórico, fila de avaliação com SIM/NÃO na linha, Carteira, Projeto e inclusão;
   - urgência e frescor;
   - Power BI público inserido no site, lendo a projeção do painel (mínimo da seção 5);
   - n8n adaptado em homologação: leitura de `gestao`, projeção das inclusões e "Adiada" no e-mail.
4. **Entrega 1, piloto e virada:**
   - O piloto roda só em homologação, com os dados oficiais e uma importação ensaiada das decisões. Nada do que for feito ali vai para produção.
   - A planilha segue oficial até o congelamento.
   - Após o aceite: congelar, fazer a importação final com conflitos zerados, conferir e trocar os consumidores na ordem da seção 5.
   - O aceite da Entrega 1 exige que a planilha deixe de ser usada e de ser lida ou escrita por automações.
5. **Entrega 1, estabilização:**
   - ciclo diário e de pautas;
   - cenários controlados de concorrência, cancelamento, duplicidade e falha com retomada;
   - o rollback da aplicação conserva as decisões no banco, sem reativar a planilha.
6. **Entrega 2:**
   - Pautas, Audiências, Autores e partidos e o Início completo como telas nativas;
   - depois do aceite, desligar o Power BI e sua credencial.

Este documento não autoriza deploy ou alteração de produção por si só.

### Critérios de aceitação

| ID | Verificação |
|---|---|
| CA01 | Anônimo não lê internos; leitor e editor do mailing não gravam; admin sem concessão não edita decisões; inativo perde acesso |
| CA02 | Edição aparece imediatamente, gera auditoria atômica e conflito de versão impede sobrescrita silenciosa |
| CA03 | (Entrega 2) Seis áreas cobrem as consultas do PBIP; diferenças de corte, urgência e denominadores são explícitas e filtros coerentes. (Entrega 1) O Power BI conta projetos por `uuid_projeto` e usa `em_carteira` da projeção, e os totais batem com a Carteira nativa após a atualização do painel |
| CA04 | Prioridade antiga permanece ativa; projeto antigo com movimento recente reaparece; histórico completo permanece acessível |
| CA05 | Versão arquivada não esconde versão ativa; remessa/divergência aparece na lista do mantenedor e no aviso do projeto, mesmo sem data ou fora do corte |
| CA06 | Pauta mantém urgência após confirmação; cancelamento/reagendamento atualizam motivo; movimento concorrente não é confirmado; baseline/backfill não criam urgências indevidas |
| CA07 | Migração conserva contagens de referência conferidas, conteúdo, vazios, conflitos e IDs; repetição não duplica |
| CA08 | Inclusão duplicada é segura; erro e retomada são visíveis; solicitação continua recuperável após duas horas; um PL sem keyword incluído pelo sistema chega a `proposicao_acompanhada`, é carregado e permanece na gold |
| CA09 | Backfill e recriação de caches preservam decisões, confirmações e restrições de acesso |
| CA10 | Com tudo certo, uma linha de atualização; com falha, o aviso diz o que falhou e o último estado bom; falha não apresenta atualização falsa |
| CA11 | (Entrega 1) Em homologação e sem ajuda, a Ana: avalia em sequência as pendências da fila; muda uma posição, uma ação e uma prioridade; inclui um PL; confirma um movimento; e exporta a carteira, tudo sem Sheets. (Entrega 2) Consulta agenda, audiências e autoria sem Power BI |
| CA12 | A projeção do painel só expõe as colunas aprovadas; `anon` e `authenticated` não leem `gestao`, contratos, histórico, parecer nem observações, inclusive depois de um novo `setup_db.py`; o painel público continua atualizando |
| CA13 | Depois da virada, nenhum fluxo do n8n lê ou escreve a planilha, e o Power BI não a lê; os passos 1 a 5 da virada têm reversão testada em homologação |
| CA14 | Um vínculo novo entre versões com UUIDs diferentes, ou um UUID cujas versões se separaram, aparece na lista do mantenedor, e nenhuma decisão é fundida ou perdida |

Testes: unittest e fixtures para regressões do pipeline; testes SQL de contratos e privilégios no harness Postgres local já usado na fase Senado; Vitest para regras/aplicação; Playwright só para o roteiro do CA11. Testes automatizados dispensam APIs e credenciais reais e usam dados sintéticos. A homologação do piloto usa dados oficiais públicos e uma importação privada das decisões, que nunca vai para o repositório. Não copiar decisões reais para fixtures públicas. Os testes de privilégio rodam depois de cada `setup_db.py`, em homologação e na produção.

## 7. Riscos e premissas

| Risco | Controle |
|---|---|
| Manutenção por uma pessoa | Reuso da plataforma e ausência de serviço novo |
| Releases afetarem mailing | Módulo isolado, mudanças aditivas e regressão de fluxos compartilhados |
| Duas fontes humanas | Congelamento/delta/virada explícitos, sem sync bidirecional |
| Agrupamentos mutáveis | UUID persistente, alias e reconciliação pelo mantenedor |
| Coleta/cache falharem | Frescor por etapa e retomada sem sobrescrever decisões |
| Baixa adoção | Piloto com tarefas de Ana e cobertura dos fluxos atuais |
| Escopo crescer | Princípio de produto: só o necessário na tela; seis áreas existentes e edição mínima |
| Link público do painel | Risco aceito pelo Erick (28/10/2026); projeção com colunas fixas e testadas |

Premissas:
- dados do levantamento podem mudar;
- o Senado tem as fases 1 a 4 mescladas e implantadas em 28/10/2026, conforme as notas do projeto, e as fases 5 (agenda) e 6 (inclusão) ainda não existem;
- PBIP é evidência versionada, não prova do estado atual no Service;
- campos humanos permanecem separados;
- não há requisito de experiência pública ou offline.

Se essas premissas mudarem, atualizar plano e PRD e submetê-los ao agente revisor. Na virada, atualizar CLAUDE.md, README e AGENTS.md, que hoje dizem que a relevância vive na planilha e nunca no banco.

A lista de movimentações maiores do Apêndice A foi validada pela Ana em 28/10/2026.

Decididas em 28/10/2026:
- duas entregas;
- autorização no servidor;
- piloto em homologação;
- mockup antes da construção;
- Power BI pelo link público inserido no site, sem licença Pro, com riscos aceitos;
- a Ana decide os conflitos da migração;
- só computador;
- confirmação por movimento, limitada às movimentações maiores;
- por ora só a Ana edita, com papéis concedidos pelo administrador no futuro e controle de concorrência por revisão da decisão, com aviso bloqueante;
- mockup aprovado (versão 2), com a projeção pública limitada a relevância, posição, prioridade e `em_carteira`;
- simplificação da tela pelo princípio de produto (revisão do Fable).

Limites do protótipo que não mudam o requisito:
- **CSV:** o ambiente do artifact bloqueia downloads, então o CSV aparece num quadro. No sistema, o arquivo é baixado.
- **Power BI:** o ambiente bloqueia a incorporação de outros sites, então o Power BI é só descrito. No sistema, o painel aparece inserido na página.
- **Filtros:** o endereço não aceita parâmetros, então os filtros ficam guardados no navegador. No sistema, eles ficam no endereço da página.

## Apêndice A — Movimentações maiores (validado pela Ana em 28/10/2026)

Uma movimentação maior é uma mudança que exige reação do time político: quem relata, o que o relator concluiu, se entrou em votação, qual foi o resultado e se o caminho do projeto mudou.

As movimentações de rotina continuam no histórico e no e-mail diário, mas não deixam uma prioridade urgente e não pedem confirmação.

A base são os tipos de tramitação da Câmara (`silver.tramitacao.cod_tipo_tramitacao`) das proposições monitoradas, levantados em 28/10/2026. Nos últimos 12 meses, a lista abaixo cobre 482 de 1.302 movimentações da Câmara (37%).

**Câmara — maiores**

| Grupo | Tipos (código) |
|---|---|
| Relatoria | Designação de Relator(a) (320), do Vencedor (327), Parcial (328); Saída de Relator(a), com ou sem parecer (1255, 1250) |
| Parecer | Parecer do(a) Relator(a) (322), Leitura e publicação do Parecer (330), Aprovação do Parecer (336), Rejeição do Parecer (335), Rejeição do Relatório Prévio (339), Pedido de Vista (420), Voto em Separado (431), Ratificação de Parecer (1040) |
| Discussão e votação | Retirada de Pauta (250), Discussão (220, 222, 242), Encerramento de Discussão (227), Adiamento de Discussão/Votação (221, 234), Encaminhamento da Votação (219, 1243), Votação (231, 1231), Verificação de Votação (245, 1239), Destaques (1233), Obstrução (223, 1232), Não Deliberado (1008) |
| Resultado | Aprovação (240, 1235), Aprovação da Redação Final (239), Rejeição (1236), Manutenção do texto (1237), Não Acolhimento (1242), Prejudicado/Prejudicialidade (198, 1240), Aprovação no Senado Federal (1518) |
| Urgência e requerimentos | Aprovação de Urgência (196), Aprovação de Requerimento (195), Apresentação de Recurso (192) |
| Mudança de caminho | Distribuição (110), Novo despacho (603), Devolução à Mesa para Novo Despacho (171), Apensação/Despacho de Apensação (106, 129), Desapensação (104), Criação/Constituição/Instalação de Comissão Temporária (120, 121, 122), Remessa ao Senado Federal (128) |
| Fim ou retomada | Arquivamento (502), Desarquivamento (640), Perda de eficácia (620), Retirada pelo Autor(a) (200, 1241), Transformação em Norma Jurídica (251), Norma com Veto Parcial (1012), Vetado Totalmente (1013) |

**Câmara — rotina** (no histórico, sem urgência):
- Recebimento (500, 501, 506, 507);
- Publicação (604, 605, 611, 1050);
- Abertura, prorrogação e encerramento de prazo (350, 352, 600);
- Notificações (1002, 1005, 203, 504, 505);
- Apresentação de Proposição (100, 300) e de Requerimento (194);
- Rejeição, retirada ou prejuízo de requerimento (260, 263, 362, 1262, 1263, 1264);
- Expedição de documento, remessa a ministério e respostas (190, 138, 162, 1055, 1056);
- Encaminhamento (180), Envio para a redação final (113), Devolução ao(à) Relator(a) (170) e Devolução de Vista (602);
- Despacho (1023), Acessórios (1245), Encerramentos (1244), Devolução à CCP (1010), Leitura do ofício de MPV (1516), Encerramento de Comissão Temporária (1051), Conferência de Assinaturas (1042) e Não Informado (5).

Validação da Ana em 28/10/2026: Distribuição (110), Aprovação de Requerimento (195) e Leitura e publicação do Parecer (330) são maiores. A leitura do parecer pode ocorrer meses depois de sua apresentação. Distribuição foi descrita como menos urgente que relatoria; um nível separado fica como possível ajuste futuro. Encerramentos (1244), não submetido à Ana, permanece rotina por decisão do mantenedor.

**Senado.** O Senado não tem código de tipo: a movimentação é um texto livre (`descricao_tramitacao`). A regra aprovada pela Ana em 28/10/2026 trata como maior o texto que mencione:
- parecer, relator ou relatoria;
- aprovação, rejeição ou votação;
- pauta;
- remessa ou encaminhamento à Câmara ou à sanção;
- arquivamento;
- sanção, veto ou norma jurídica;
- urgência;
- prejuízo ou retirada.

Nos últimos 12 meses, essa regra pega 98 de 250 movimentações do Senado (39%). A implementação confere exemplos reais na homologação, como foi feito com `eh_relator` na fase Senado.

**Regras gerais:**
- uma tramitação nova de tipo maior numa prioridade ativa abre urgência até ser confirmada;
- várias movimentações maiores no mesmo dia aparecem juntas, e a Ana confirma as que viu;
- os tipos novos que a Câmara criar entram como rotina até alguém classificá-los, e aparecem numa consulta SQL de "tipos sem classificação" para o mantenedor revisar, sem tela;
- a classificação fica numa tabela de referência editável pelo mantenedor, e não no código.

## Histórico de revisões

Primeira versão revisada pelo GPT-6 Astra, com as seis correções incorporadas.

Revisão de 28/10/2026 (tarde), com decisões do Erick:
- duas entregas, a primeira com o Power BI inserido no site;
- autorização no servidor;
- piloto em homologação;
- estado do Senado atualizado pela implementação em `main` (commit `28d9a2a`);
- Power BI continua pelo link público "Publicar na Web", inserido no site da plataforma, até a Entrega 2 (seção 5).

Revisão final do Fable contra o código (28/10/2026) e respostas do Erick incorporadas:
- não há licença Pro: o link público continua, com riscos aceitos pelo Erick, porque o painel não mostra dados sensíveis;
- a Ana decide os conflitos da migração;
- lista proposta de movimentações maiores no Apêndice A;
- só computador;
- confirmação das movimentações maiores;
- por ora só a Ana edita, com papéis editáveis no futuro.

Mockup aprovado pelo Erick em 28/10/2026 (versão 2, `mockup/legislativo-mockup.html`), depois da avaliação do Astra (`mockup/avaliacao_mockup_asta.md`). As decisões de tela e os esclarecimentos da seção 10 da avaliação estão incorporados neste documento, principalmente no RF02, RF03, RF04, RF08, RF09, RN03, RN04 e na seção 6.

Simplificação de 28/10/2026 (revisão do Fable, aprovada pelo Erick): menos indicadores, abas, colunas e notas na tela; "A conferir" sai da navegação da Ana; a ocorrência de movimentação maior vira view e só a confirmação fica em tabela; o horário de atualização do Power BI fica dentro do próprio relatório.
