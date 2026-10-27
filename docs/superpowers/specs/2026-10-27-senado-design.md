# Senado Federal no monitoramento — estudo e plano de implementação

Data: 27/10/2026. Status: revisado pelo Fable, correções incorporadas. As decisões da seção 8 estão tomadas; a 8.5 foi revista em 27/10/2026.

## 1. Intenção

A responsável pelo acompanhamento (Ana) trata os projetos das duas casas da mesma forma. Hoje o sistema só enxerga a Câmara, e isso deixa dois buracos:

1. **Proposições só do Senado ficam de fora.** São 9 na planilha antiga: MPV 1186/2023, PL 1879/2022, PL 433/2026, PL 4363/2025, PLS 168/2018, PLS 302/2018, PLS 326/2016, PLS 631/2015 e PLS 650/2015. Hoje só são acompanhadas pela planilha manual. O PLC 10/2018 é o PL 5851/2016, que já está acompanhado na Câmara (id 2092191).
2. **Projetos acompanhados somem do radar quando passam para o Senado.**
   - O PL 6028/2019 está "Aguardando Apreciação pelo Senado Federal" na Câmara, onde não se mexe mais. No Senado, ele está "PRONTA PARA A PAUTA NA COMISSÃO" e nenhum e-mail avisa.
   - O caminho inverso também acontece: o PL 1167/2024 e o PL 4262/2025 nasceram no Senado e já estão na Câmara.

**Sucesso:** as proposições do Senado entram no mesmo radar, no mesmo e-mail, na mesma planilha e no mesmo painel, sempre com a casa visível. Um projeto acompanhado continua acompanhado quando muda de casa.

**Não-objetivos:**
- votações nominais e emendas;
- o Congresso Nacional como terceira casa, e as sessões conjuntas do Congresso. **As comissões mistas de MPV (CMMPV) entram** (decisão 8.4);
- histórico do radar. Vale a mesma regra de hoje: entram as acompanhadas e as proposições com keyword apresentadas a partir de 01/09/2026.

**Anti-objetivos (falha mesmo se tecnicamente funcionar):**
- Uma falha do Senado travar a carga, o e-mail ou a planilha da Câmara, que está em produção.
- A avaliação SIM/NÃO ou a posição da ABCS vazar para um projeto diferente da outra casa que tenha o mesmo número.
- O e-mail diário voltar a ter centenas de pendentes. Isso inclui projetos já avaliados reaparecendo quando mudam de casa.
- Mudar a chave da planilha ou do Power BI de um jeito que obrigue a Ana a refazer o que já preencheu.

## 2. A API do Senado (verificado por chamada real em 27/10/2026)

Base: `https://legis.senado.leg.br/dadosabertos`. Usamos a família `/processo`. A família `/materia/*` está depreciada, com sunset em 01/02/2026: ainda responde, mas pode sair do ar sem aviso, então não é usada.

| Necessidade | Endpoint | Observação |
|---|---|---|
| Detalhe | `GET /processo/{id}` | JSON único, de 15 a 300 KB. Traz identificação, ementa, `documento.indexacao` (o equivalente de `keywords`), `autoriaIniciativa`, `classificacoes`, `situacaoAtual` (às vezes nula), `codigoMateria`, `siglaCasaIniciadora`, `identificacaoProcessoInicial`, `outrosNumeros[]` e `autuacoes[]`. Cada autuação tem `informesLegislativos[]` (as tramitações, cada uma com **`id`** próprio; o mesmo id pode se repetir dentro do payload) e `situacoes[]`. |
| Busca por identificação | `GET /processo?sigla=PL&numero=1879&ano=2022` | Achou exatamente 1 resultado para cada uma das 13 proposições do Senado da planilha antiga. **Não acha** um processo pelo número antigo da Câmara (PL 4314/2016, 3729/2004, 3479/2004…), nem com `siglaEnteIdentificador=CD`. |
| Lista | `GET /processo?numdias=N` (N ≤ 30), `dataInicioApresentacao/dataFimApresentacao` (≤ 1 ano), `tramitando=S` | Sem paginação: a resposta vem inteira. `tramitando=S` traz 10.900 processos em 9 MB, com `objetivo` (Iniciadora / Revisora), `autoria` em texto, `ementa`, `dataUltimaAtualizacao` e `codigoMateria`. **Não traz** o número de origem na Câmara. Aceita filtros de `codigoClasse` e de `alteracao`. |
| Tema | `codigoClasse` (árvore) | Agropecuária e Abastecimento 33805062; Meio Ambiente 33809634 mais 11 filhos; Indústria, Comércio e Serviços 33804850 mais filhos; Saúde > Defesa e Vigilância Sanitária 33809198. O filtro **não inclui os filhos**. |
| Relatoria | `GET /processo/relatoria` | Busca por `idProcesso`, `codigoColegiado` ou `dataInicio`/`dataFim`. Traz colegiado, relator, partido, UF e datas de designação e destituição. |
| Senadores | `/senador/lista/atual`, `/senador/{codigo}` | Formato legado (XML convertido em JSON): tudo vem como string, e uma lista de 1 item vira objeto. |
| Agenda das comissões | `GET /comissao/agenda/{AAAAMMDD}/{AAAAMMDD}` (≤ 30 dias) | Formato legado. Cada reunião tem `partes[]` (deliberativa, "Audiência Pública Interativa"…) e `colegiados[]` (podem ser várias comissões). O campo `status` é Agendada, Realizada, Cancelada, Adiada ou Não realizada. Cada item tem `doma.idProcesso` e `siglaResultado`, que inclui Adiado, Retirado de pauta, Vista concedida etc. |
| Agenda do Plenário | `/plenario/agenda/dia/...` e `/plenario/encontro/{codigoSessao}/pauta` | Os itens trazem só `codMateria` (legado). Há sessões do Congresso (`Casa = 'CN'`). |

**Pontos operacionais:**
- O limite documentado é 10 requisições por segundo.
- **Aparecem 503 intermitentes** (alguns arquivos de exemplo vieram com 503), então retry com backoff é obrigatório.
- O CDN guarda as respostas por 30 minutos ou mais.
- Neste WSL, a conexão com TLS 1.3 trava e com TLS 1.2 funciona.

**Achados que moldam o desenho:**
- **Ids vão colidir.** Os processos do Senado vão de 2,9 a 9 milhões, e os ids da Câmara já passam de 2,6 milhões e crescem. Reunião, parte de reunião, sessão do Plenário e colegiado são espaços de número independentes.
- **Identificações iguais podem ser projetos iguais ou diferentes.**
  - Um projeto que nasceu em 2019 ou depois mantém o número ao mudar de casa.
  - Um projeto que nasceu antes de 2019 ganha número novo, **qualquer que seja o ano em que chega**. Exemplo: o PL 4314/2016 da Câmara chegou ao Senado em 19/12/2025 como PL 6682/2025.
  - Ao mesmo tempo, "PL 1879/2022" pode existir nas duas casas como projetos diferentes.
  - MPV existe nas duas APIs, com a mesma numeração nacional (EC 32/2001).
- **A MPV no Senado** (MPV 1186/2023, `/processo/8537155`):
  - `siglaCasaIniciadora` e `casaIdentificadora` = `'CN'`;
  - `comissaoMpv` = {codigo 2633, sigla "CMMPV 1186/2023"};
  - `outrosNumeros` só traz a MSG do Executivo, sem número da Câmara.
- **As reuniões de CMMPV não têm itens de pauta.** Nos exemplos, as partes são audiência, trabalho e instalação, e nenhuma é deliberativa. Elas se ligam à MPV por `colegiadoCriador.materiasOriginadoras.idProcesso`, e o colegiado tem `codigoTipoColegiado = '42'`.
- **O vínculo é N:M.** O PL 2159/2021 do Senado lista dois números da Câmara (PL 3729/2004 e PL 2159/2021).
- **O vínculo só sai do detalhe, que existe em lista apenas para os processos "Revisora".** Esses processos (2.064 tramitando, sendo 1.010 PL) trazem em `/processo/{id}` o número da Câmara (`identificacaoProcessoInicial` e `outrosNumeros`).
- **`documento.dataApresentacao` é a data de chegada ao Senado**, não a de origem. Exemplos: PL 6028/2019 → 2021-10-18; PL 4314/2016 → 2025-12-19.
- **A classificação não cobre tudo.** Das 13 proposições da planilha, 11 caem nas classes de agro, meio ambiente ou sanidade. O PL 433/2026 está em Direito Penal e o PL 1167/2024 em Educação.

## 3. Impacto no que existe

| Camada | O que pressupõe a Câmara |
|---|---|
| Carregadores Python | `carregar_ids_acompanhadas` (`extract_incremental.py`), `pipeline_inclusao.py`, `carregar_ids_existentes` (`extract_bronze.py`, que cruza as 4 bronze da Câmara), `load_dim_orgao.py` (manda ids para `/orgaos` da Câmara), `load_dim_deputado.py` (busca por `tipo = 'Deputado(a)'` e `id_deputado_relator` em `/deputados/{id}`). **Todos mandariam ids do Senado para a API da Câmara.** |
| Orquestração | `executar_carga_incremental` levanta erro e chama `atualizar_api` por dentro. `pipeline_pautas.py` também não isola etapas. No Actions, a notificação ao n8n só sai com sucesso; com falha, sai só `status=falha`, sem e-mail diário nem planilha. |
| silver | `proposicao_acompanhada` (PK `id_proposicao`). `tramitacao` (PK `id_proposicao, sequencia`). Colunas INT em `id_orgao`, `id_orgao_atual` e `id_deputado_relator`. |
| gold | Autor ligado a `dim_deputado` por `regexp_replace(uri)::int`: o Postgres não garante curto-circuito, então um `uri` não numérico derruba a view. `eh_relator` usa a regex `^Designação de Relator`. `status_alerta` usa `uri_votacao`. Audiência pública vem de `descricao_tipo = 'Audiência Pública'`. |
| api | Índices únicos em `id_proposicao` e `id_evento`. Uma linha duplicada faz o `REFRESH CONCURRENTLY` falhar e congela o api inteiro. A regra de status é repetida (há teste de paridade). `vw_ultima_carga` lê só `incremental`/`eventos`. |
| n8n "Monitoramento → Sheets" | Upsert por `id_proposicao`. Listas `sim`/`nao`/`avaliadas` como ids `bigint`. Pendente = `em_radar AND não avaliada`. O texto do link é "Câmara", fixo. "Registrar Envio" confirma acompanhadas por id. |
| n8n "Inclusão manual" | PLS e PLC são rejeitados como "Senado". "PL n/a" é sempre resolvido na Câmara. Duplicatas são detectadas por id. |
| Power BI | `dim_posicionamento_abcs` → `vw_monitoramento` por **`identificacao`, em relação 1:1 bidirecional**: uma identificação repetida derruba o refresh. `dim_relevancia` → `vw_monitoramento` por `id_proposicao` (1:1). Medida "Link Câmara" e textos "Abrir na Câmara ↗" e "Não informada pela Câmara". |

## 4. Decisões técnicas

### 4.1 Chave única com faixas reservadas
- Toda chave do Senado vira um deslocamento fixo somado ao id nativo:
  - **processo**: `1_000_000_000 + id` → `id_proposicao`;
  - **colegiado**: `1_000_000_000 + código` → `id_orgao` (INT; o máximo é 2.147.483.647, então cabe);
  - **parte de reunião de comissão**: `1_000_000_000 + parte.codigo` → `id_evento`;
  - **sessão do Plenário**: `2_000_000_000 + codigoSessao` → `id_evento` (BIGINT).
- Colunas explícitas `casa` ('CD'/'SF') e `id_origem` (id nativo). A transformação da Câmara também grava `id_origem`.
- `CHECK ((casa = 'SF') = (id_proposicao >= 1000000000))` nas tabelas de proposição.
- O deslocamento vale só da silver em diante. A bronze guarda o id nativo, em tabelas próprias. No Python há uma única função de chave (`config.py`); no SQL, constantes nomeadas no topo da transformação do Senado.
- *Por quê:* `id_proposicao` continua sendo um inteiro único. Assim continuam funcionando, sem mudança de tipo: o `::bigint` e o `/^\d+$/` do n8n, o upsert da planilha, as relações do Power BI, a PK das acompanhadas e os índices do `api_cache`. O Fable conferiu os tipos coluna a coluna. Chave texto ou composta foram descartadas.
- **Guarda obrigatória:** todo carregador da Câmara filtra `casa = 'CD'` / `id < 1e9`, e todo carregador do Senado filtra o contrário, com teste. A gold protege os casts (`CASE WHEN uri ~ '/\d+$'`).

### 4.2 Bronze separada, silver compartilhada
- **bronze**: `sf_processo_json`, `sf_relatoria_json`, `sf_agenda_comissao_json` (uma linha por reunião) e `sf_plenario_pauta_json` (uma linha por sessão). Todas append-only, mas **só gravam quando o payload mudou** (hash ou `dataUltimaAtualizacao` igual à da última linha). Sem isso, de 4 a 7 GB por ano. A transformação lê só o último snapshot por id; os informes são cumulativos no payload.
- **silver**: as mesmas tabelas, com colunas novas no fim. `sql/transform_senado_to_silver.sql` faz o mapeamento:
  - `proposicao`: `casa`, `id_origem`, `codigo_materia`, `casa_iniciadora` e `data_apresentacao_origem` (ver 4.6). `casa` é **sempre `'SF'`** para o que vem da API do Senado, porque indica a API de origem. `'CN'` (MPV) só vai para `casa_iniciadora`, e a CHECK de `casa` continua valendo. `descricao_situacao` = situação mais recente entre as autuações, porque `situacaoAtual` pode vir nula. A indexação vai para a coluna de keywords (renomear `keywords_camara` → `indexacao` fica a critério de quem implementa).
  - `tramitacao`: `sequencia` = `informe.id`, com `ON CONFLICT DO NOTHING` (nunca `DO UPDATE`, porque há id repetido). Ganha a coluna nova `eh_relator`, calculada na silver para as duas casas. No Senado, **a regra é a regex** sobre `informe.descricao` (fase 0: 96,5% de cobertura, nenhum falso positivo encontrado). A relatoria (`dataDesignacao` + colegiado) só identifica o relator (código, partido, UF). Casar só por dia e colegiado daria 21% de falsos positivos. Na Câmara, a regex atual.
  - `proposicoes_proponentes` (de `autoriaIniciativa`): `uri = NULL`. Os tipos ficam distintos dos da Câmara ('Senador(a)', 'Deputado(a) – via Senado', 'Câmara dos Deputados'…), para `load_dim_deputado` e a gold nunca os confundirem.
  - `proposicao_tema`: vem de `classificacoes` (código de 8 dígitos, que não colide com os temas da Câmara).
  - `evento_pauta`: o relator do Senado vai para colunas próprias (`codigo_parlamentar_relator`, partido e UF do momento), **nunca** para `id_deputado_relator`. Ganha a coluna `votado boolean`, normalizada para as duas casas (Câmara: `uri_votacao IS NOT NULL`; Senado: `siglaResultado` numa lista de resultados de votação, levantada na fase 0).
- **`silver.dim_senador`**: código, nome, partido e UF atuais. Na gold, autor e relator buscam em `dim_deputado` ou `dim_senador` conforme o tipo. Para deputado autor de projeto que veio da Câmara, o partido sai do registro vinculado da Câmara, quando houver.

### 4.3 Extração e janela (`extract_senado.py`)
1. **Candidatos do dia**: `numdias` com `codigoClasse` para cada código da subárvore configurada (`CLASSES_SENADO` em `config.py`; os filhos saem de `/processo/classes`). **Sem o filtro `alteracao`**: a fase 0 mostrou que ele perderia eventos. Mais **todas** as MPVs (`numdias` com `sigla=MPV`): só 32 das 238 desde 2023 estão nas classes.
2. **Acompanhadas do Senado** (`id >= 1e9`): recarregadas todo dia. Erro por id não trava a janela, como na Câmara.
3. **Gêmeos de proposições monitoradas** (4.4): recarregados todo dia.
4. **Reconciliação** de 90 dias por apresentação e classe, para os ausentes.
5. Para cada id, `GET /processo/{id}`. A relatoria vem por janela (`/processo/relatoria?dataInicio&dataFim`) mais o id das acompanhadas, evitando uma chamada por processo.
- **Janela**: `numdias = min(30, dias desde o último sucesso + 14)`. Se o buraco passar de 16 dias, recarregar todos os ids do Senado presentes na gold.
- **`tipo_carga`**: `incremental_senado`, `eventos_senado`, `reconciliacao_senado`.
- **Carga inicial**: classes e MPVs × anos desde 2023-02-01, mais `tramitando=S` filtrado pelas mesmas classes, mais as acompanhadas, mais o mapa de vínculo (4.4).
- **Cliente HTTP próprio**: retry com backoff em 429/5xx, ≤ 5 req/s, segue redirects e tolera objeto no lugar de lista. Usa TLS 1.2 se o runner também travar.

### 4.4 Vínculo entre as casas
- `silver.proposicao_vinculo (id_proposicao_cd, id_proposicao_sf)`, com **PK nos dois campos (N:M)**.
- Calculada a partir do detalhe dos processos do Senado: `identificacaoProcessoInicial` e todos os `outrosNumeros[casaIdentificadora = 'CD']`, **qualquer que seja a casa iniciadora**, casados com `silver.proposicao` da Câmara por sigla/número/ano, sem zeros à esquerda. Exemplo: o PL 1167/2024 e o PL 4262/2025 nasceram no Senado e trazem o próprio número CD em `outrosNumeros`.
- **Vínculos manuais** (origem `'manual'`, num seed): pares que a API não liga. Da planilha antiga: PLC 10/2018 ↔ PL 5851/2016 e PLS 302/2018 ↔ PL 3047/2022. O mapa dos "Revisora" só cobre o que tramita no Senado.
- **Como encontrar o gêmeo no Senado** de um projeto monitorado da Câmara:
  - Pós-2019: busca direta por `sigla/numero/ano`.
  - Pré-2019: um mapa mantido a partir dos processos "Revisora". A carga inicial lê o detalhe de todos os ~2 mil processos tramitando (~1 mil são PL), uma vez só. Depois, a cada dia, só os novos "Revisora" que aparecem no `numdias`. O detalhe é o mesmo que já vai para a bronze, então não há custo extra para os que estão nas classes.
  - O caminho inverso (do Senado para a Câmara) usa o mesmo número pós-2019 e, antes disso, o `outrosNumeros`.
- **Na gold, nada de join direto com o vínculo** (multiplicaria linhas e derrubaria o índice único). O padrão é agregar:
  - `chave_projeto`: o menor id do grupo, que é sempre o da Câmara quando existe. É a chave canônica do "mesmo projeto".
  - `ids_vinculados`: texto, para exibição.
- **Teste de unicidade** de `id_proposicao` em `vw_monitoramento`.
- **MPV** (decisão 8.5): vem do Senado, e a versão da Câmara entra no mesmo grupo pelo vínculo `'mpv'`.
  - Regra do vínculo: identificação idêntica (`sigla_tipo = 'MPV'`), ano ≥ 2002, número sem zeros à esquerda e **`dataInicioEfetivo` do detalhe do Senado** a no máximo 7 dias da data de apresentação na Câmara. A `dataApresentacao` da lista é a data de leitura no Senado e falhou num caso (MPV 1339/2026, 119 dias). Fase 0: 98/98 MPVs casam 1:1.
  - O Senado **não cria processo PLV**: o projeto de conversão fica dentro do processo da MPV (`deliberacao.siglaTipo = APROVADO_PLV`). O PLV da Câmara é uma proposição própria e não entra no grupo nesta fase.

### 4.5 Agenda e audiências
- **Comissões**:
  - Uma chamada `/comissao/agenda/{D-7}/{D+14}`.
  - Filtro por **qualquer** colegiado da reunião (`colegiados[]`), dentro de `COMISSOES_SENADO`.
  - **Uma linha de `silver.evento` por parte da reunião.** As partes deliberativas vão para `evento_pauta` com `id_proposicao = 1e9 + doma.idProcesso`.
  - **Comissões mistas de MPV**: entram as reuniões com algum colegiado de tipo 42 (CMMPV) cuja `colegiadoCriador.materiasOriginadoras.idProcesso` esteja na silver do Senado.
    - Fase 0: 14 de 44 reuniões de CMMPV têm uma parte deliberativa cujo item é a própria MPV (`doma.idProcesso` = `materiasOriginadoras.idProcesso`). Nessas, vale o item real. Nas que não têm item (audiência, instalação, trabalho), grava-se **uma linha sintética** em `evento_pauta` com `id_proposicao = 1e9 + idProcesso`, na primeira parte. Fica no máximo uma linha por (reunião, MPV).
    - O relator de CMMPV pode ser deputado (`casaRelator = CD`): a dimensão de relatores não pode supor que todo relator é senador.
    - A audiência da CMMPV também fica ligada à MPV por essa linha, porque a finalidade não casa com keywords.
    - Os colegiados CMMPV vão para `dim_orgao` com `casa = 'CN'`.
  - As partes com `descricaoTipo` LIKE 'Audiência Pública%' viram `descricao_tipo = 'Audiência Pública'` e `descricao = finalidade`. O match por keyword continua igual.
- **Situação do evento**: mapeada pelo campo `status` da reunião, nunca por `situacao`, que junta Cancelada, Adiada e Não realizada.
  - Realizada e "Continua em …" → 'Realizada'.
  - Cancelada e Não realizada → 'Cancelada'.
  - Adiada → 'Adiada', um rótulo novo (decisão minha, ver 7).
  - Qualquer outro valor → 'Agendada', com registro em log.
  - As regras de `status_alerta` ganham o caso 'Adiada', idêntico na gold e no api.
- **Votado nas comissões**: `siglaResultado` em `RESULTADOS_VOTADO`, com os 13 valores de `data/senado_fase0/RESULTADOS_04.md`. "Prejudicado" e "Sem deliberação" não contam. Falso negativo conhecido: a MPV 1304/2025 foi aprovada na comissão (reunião 14185), mas veio com "Sem deliberação". O caso foi aceito; se ficar frequente, usar como reserva a regex `descricaoResultado ~* 'aprovad[oa].*relat'`. Um teste lista os valores conhecidos, e um valor novo cai na reserva `apreciado = 'true'`.
- **Relator na pauta das comissões**: `item.doma.relatorias.relator.parlamentar` (código, partido, UF), ou `relatorAdhoc` quando existir.
- **Plenário**: `/plenario/agenda/dia` por dia da janela, mais `/plenario/encontro/{codigoSessao}/pauta`.
  - A pauta traz `materiaLegislativa.idProcesso`, que é o id do `/processo` (fase 0: 25/25). Esse é o vínculo. `materiaLegislativa.codigo` é o documento, não o processo, e `codigo_materia` fica só como reserva.
  - Entram só sessões com `Casa = 'SF'` e `TipoSessao` deliberativa. Sessões do Congresso ficam fora (decisão 8.4).
  - Situação da sessão: Encerrada → Realizada; Cancelada e Sessão não realizada → Cancelada.
  - Votado: o item principal (`indItemPrincipal = 'S'`) tem `txtDecisao ~* '^\s*(aprovad|rejeitad|requerimentos?\s+(aprovad|rejeitad))'`.
- **"Votado"**: a regra passa a ler `evento_pauta.votado`, levado ao `api_cache`, igual na gold e no api.
- `pipeline_pautas.py` também atualiza a agenda do Senado e registra só `eventos_senado`.

### 4.6 Gold, api e keywords
- **`vw_proposicao_keywords`**: o match usa ementa e indexação. A indexação do Senado vem às vezes sem acento ("AGROINDUSTRIA"). Nas linhas do Senado, o match usa `unaccent` dos dois lados; na fase 0, isso subiu os casamentos de 49 para 55. A Câmara continua como está, para não mudar resultados em produção; estender à Câmara depende de medir antes com o comparador.
- **Precisão antes do radar**: 85% dos casamentos do Senado vêm de "produtor rural", keyword já marcada como de baixa precisão. Refinar essa keyword antes de a fase 3 entrar em produção.
- **`vw_monitoramento`**: colunas novas **no fim**: `casa`, `chave_projeto`, `ids_vinculados`, `identificacao_casa` (ex. "PL 2159/2021 (Senado)"). Mais:
  - `link_direto` do Senado = `https://www25.senado.leg.br/web/atividade/materias/-/materia/{codigoMateria}`.
  - Autor, partido e UF conforme 4.2.
- **`acompanhada`**: verdadeira se a própria proposição **ou alguma do seu grupo** (`chave_projeto`) estiver em `proposicao_acompanhada` (se 8.1 for aprovado).
- **`em_radar`**: usa `data_apresentacao_origem` = a data de apresentação na casa iniciadora (da Câmara pelo vínculo; sem vínculo, 1º de janeiro do ano de `identificacaoProcessoInicial`; com `casa_iniciadora = 'CN'` (MPV), a própria data do Senado, porque a edição é a mesma nas duas casas). Assim, projeto velho que chega ao Senado não parece novo (8.6).
- **`vw_pautas_monitoradas`, `vw_audiencias_de_interesse`, `vw_tramitacoes`, `vw_movimentacoes`**: coluna `casa` no fim. `eh_relator` passa a vir da silver.
- **`api`**: repete as colunas. `vw_ultima_carga` ganha `ultima_carga_senado` e `ultima_carga_pautas_senado` no fim.

### 4.7 Planilha, e-mail e Power BI
- **Aba "Proposições"**: uma linha por proposição de cada casa (o id continua único). Coluna nova `casa`, escrita pelo n8n.
- **Avaliação SIM/NÃO entre casas** (se 8.1 for aprovado):
  - o n8n expande **as três listas** (`sim`, `nao`, `avaliadas`) pelo grupo (`chave_projeto`), via uma view `gold.vw_grupo_projeto`;
  - o gêmeo de um projeto avaliado herda a avaliação e não vira pendente;
  - se houver divergência, prevalece o que 8.1 decidir.
  - A coluna `relevancia` do gêmeo na planilha **não** é preenchida automaticamente. A herança acontece só nas consultas.
- **Inclusão manual**: coluna `casa` com lista suspensa; vazio = Câmara. PLS/PLC/PRS/PDS são reconhecidos como Senado. No Senado, a busca é por `sigla/numero/ano`. A mensagem de erro diz em que casa procurou. **Só é liberada depois da fase 2.**
- **E-mail**:
  - "Proposição" mostra `identificacao_casa`;
  - o link tem o nome da casa;
  - os pendentes e as movimentações são deduplicados por `chave_projeto`: uma linha por projeto, com as outras versões em `ids_vinculados`. A mesma MPV nova chega às duas casas no mesmo dia;
  - "Novo relator" vale nas duas casas;
  - se o Senado falhou e a Câmara não, o e-mail sai com um aviso no topo (4.8).
- **Power BI**:
  - **Já na fase 1**, a relação de posicionamento deixa de ser 1:1 por `identificacao`. Passa a N:1 por uma chave que é única na dimensão. A forma depende de 8.2.
  - Segmentação "Casa".
  - "Link" com rótulo da casa.
  - Textos genéricos.
  - `dim_senador` no mapa e nos partidos.
  - Visuais novos com mockup aprovado antes.

### 4.8 Falhas: o Senado nunca derruba a Câmara
- Falha parcial do Senado: levanta erro, faz rollback da transação abortada e não registra as janelas do Senado.
- **Orquestrador novo em `pipeline.py` e `pipeline_pautas.py`**:
  - roda a Câmara: bronze, silver e registro das janelas, sem `atualizar_api` nem o `raise` final, que saem de `executar_carga_incremental`;
  - roda o Senado;
  - roda `atualizar_api`;
  - junta os erros.
  - Se a Câmara falhou, o comportamento é o de hoje. **Se só o Senado falhou**, o job termina com sucesso e notifica o n8n com `status=ok` e `aviso_senado=<motivo>`. O e-mail diário e a planilha saem com o aviso. O Actions registra a falha como *annotation*, sem derrubar o job.
- Testes cobrem:
  - falha do Senado não avança as janelas do Senado nem bloqueia as da Câmara;
  - o aviso chega ao n8n;
  - falha da Câmara segue derrubando o job.
- **Ordem de deploy de cada fase**: `setup_db.py` em produção antes do merge, porque `check_environment.py` passa a exigir as tabelas novas.

## 5. Plano por fases

Cada fase é um PR com testes mockados. A produção é atualizada só após o merge, com `setup_db` antes.

**Fase 0 — Verificações (scripts no scratchpad, nada no repositório)**
1. TLS do runner do Actions com `legis.senado.leg.br` (passo `curl` temporário em workflow manual).
2. Volume: total por classe e filhos desde 2023, mais os tramitando, mais `numdias=14` somado (tempo do job e tamanho da bronze). Espaço atual do Supabase.
3. Cobertura: keywords atuais sobre ementa e indexação dos candidatos. Quantos entrariam no radar e quantos se tornariam pendentes no e-mail.
4. Vínculo pré-2019: montar o mapa dos "Revisora" e conferir as acompanhadas antigas do seed (PL 3479/2004, 5194/2005, 215/2007, 6559/2013…). Quantas estão no Senado?
5. Vocabulário de `siglaResultado` (várias semanas) e dos resultados do Plenário: a lista de "votado".
6. Regra `eh_relator`: informe × `relatoria.dataDesignacao` nos 13 processos da planilha.
7. Estabilidade de `informe.id` entre duas leituras. Formato da pauta do Plenário em sessão deliberativa.
8. Quantas identificações colidiriam: MPVs e gêmeos entre os monitorados da Câmara. O cruzamento das MPVs pela regra `'mpv'` e o PLV.

**Fase 1 — Casa e chave, sem dados do Senado (deploy sem mudança visível)**
- Funções de chave e constantes.
- Colunas `casa`, `id_origem`, `codigo_materia`, `data_apresentacao_origem`, `eh_relator` e `votado` na silver, preenchidas para a Câmara.
- CHECKs.
- Filtros de casa em todos os carregadores da Câmara.
- Casts protegidos na gold.
- `proposicao_vinculo` vazia.
- Colunas novas no fim da gold e do api; `status_alerta` lê `votado`.
- Teste de paridade e de unicidade.
- Orquestrador com isolamento por casa (o Senado ainda é um no-op).
- **Power BI: relação de posicionamento N:1** (publicar).

**Fase 2 — Planilha e e-mail preparados (n8n)**
- Coluna `casa` na aba "Proposições".
- E-mail com casa, link com nome da casa e aviso de falha parcial.
- Expansão das listas pelo grupo (se aprovado).
- Validar o workflow antes de publicar.
- A inclusão manual do Senado fica fora.

**Fase 3 — Proposições do Senado**
- Cliente HTTP, `extract_senado.py`, bronze `sf_*`, `transform_senado_to_silver.sql` e `dim_senador`.
- Janelas próprias.
- Seed das 9 acompanhadas só do Senado (ids da seção 2 mais o deslocamento).
- Carga inicial.
- `check_environment.py` cobre o Senado.

**Fase 4 — Vínculo e propagação**
- Mapa dos "Revisora" e `proposicao_vinculo`.
- Gêmeos na carga diária.
- `chave_projeto`, `acompanhada` propagada e `data_apresentacao_origem`.
- Autor via Câmara.

**Fase 5 — Agenda do Senado**
- Comissões por parte, Plenário por `codMateria`, audiências por `finalidade`, CMMPV das MPVs monitoradas (tipo 42, `materiasOriginadoras`).
- `votado` e situação normalizada.
- `pipeline_pautas.py`.

**Fase 6 — Inclusão manual do Senado (n8n)**

**Fase 7 — Power BI**
- Colunas, segmentação "Casa", textos genéricos.
- `dim_senador` no mapa e nos partidos.
- Comissões do Senado nas pautas.
- Mockup antes; publicação no Service.

**Fase 8 — Comunicação**
- Mensagem curta à Ana: o que muda no e-mail, na planilha e no painel.
- README ("Status do projeto") e CLAUDE.md (arquitetura com Senado).

## 6. Riscos

- **A API muda (`/processo` e endpoints legados).** A bronze guarda o JSON cru, e o cliente do Senado isola o formato.
- **Respostas grandes (5–9 MB).** A rotina diária usa `numdias` com classe; `tramitando=S` só na carga inicial e na manutenção do mapa.
- **O job fica mais longo.** Estimativa de 5 a 15 minutos a mais, a confirmar na fase 0. O timeout é de 120 minutos.
- **Classes que deixam projetos de fora.** Ficam cobertos pela inclusão manual e pela propagação do vínculo. Avaliar na fase 0 um filtro grosso extra por termo de indexação (`termo=suino`).
- **Convenção de deslocamento esquecida em código novo.** Mitigação: uma função única, CHECKs e testes.

## 7. Decisões que tomei (conferir)

- Deslocamento de 1e9 (e 2e9 para sessões do Plenário) em vez de chave composta.
- Bronze só quando muda.
- Uma linha de evento por parte da reunião.
- O rótulo "Adiada" é próprio.
- `eh_relator` e `votado` calculados na silver.
- Falha só do Senado não falha o job e vira aviso no e-mail. Essa decisão o Erick pode vetar: ver 8.3.

## 8. Decisões de negócio (Erick, 27/10/2026)

1. **Projeto que muda de casa é um projeto só.** Acompanhamento e SIM/NÃO valem para as duas versões (grupo `chave_projeto`). Se as avaliações divergirem, prevalece SIM.
2. **A posição da ABCS vale para o projeto nas duas casas.** A aba Posicionamento continua por identificação, e o painel liga a posição ao grupo do projeto. Para um projeto só do Senado, a Ana digita a identificação do Senado (ex. "PLS 650/2015").
3. **Falha só do Senado:** o e-mail diário e a planilha saem com um aviso no topo. O job não falha por causa do Senado.
4. **Comissões do Senado na agenda:** CRA, CMA, CCJ, CAE, Plenário do Senado e as **comissões mistas das MPVs monitoradas**. Sessões do Congresso ficam fora.
5. **MPV é acompanhada pelo Senado**, e a versão da Câmara fica ligada no mesmo grupo. As pautas do Plenário da Câmara continuam alertando. Esta decisão substitui a anterior ("MPV pela Câmara"), também de 27/10/2026.
6. **Radar:** projeto antigo da Câmara que chega ao Senado não entra como novo. Isso não foi perguntado; vale a recomendação do estudo (`data_apresentacao_origem`). Se for importante, já é acompanhado, e o acompanhamento passa junto.

## 9. Deixado para quem implementar

- Nomes de tabelas e colunas, dentro do padrão.
- Ritmo de chamadas e estrutura dos testes.
- Onde expandir a árvore de classes.
- Renomear `keywords_camara`.
- Texto das mensagens do n8n.
