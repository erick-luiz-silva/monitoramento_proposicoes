"""Colunas e medidas das páginas Início, Proposição, Pautas, Audiências e Autores (mockup aprovado em 20/10/2026)."""
import sys
from pathlib import Path

TAB = Path(sys.argv[1]) / "BI_Monitoramento_Proposicoes.SemanticModel" / "definition" / "tables"


def ler(p):
    bruto = p.read_bytes()
    return bruto.decode("utf-8").replace("\r\n", "\n"), b"\r\n" in bruto


def gravar(p, texto, crlf):
    p.write_text(texto, encoding="utf-8", newline="\r\n" if crlf else "\n")


def antes_da_particao(texto, bloco, marca):
    if marca in texto:
        return texto
    i = texto.index("\tpartition ")
    return texto[:i] + bloco + texto[i:]


def substituir(texto, velho, novo):
    if novo in texto:
        return texto
    assert texto.count(velho) == 1, velho[:60]
    return texto.replace(velho, novo)


# --- vw_monitoramento: tipo, apresentação e colunas derivadas para a página de autores ---
p = TAB / "gold vw_monitoramento.tmdl"
s, crlf = ler(p)
s = substituir(s, '{"em_radar", type logical}})', '{"em_radar", type logical}, {"sigla_tipo", type text}, {"data_apresentacao", type datetime}})')
s = antes_da_particao(s, '''	column sigla_tipo
		dataType: string
		lineageTag: 2c8e5a1f-7d3b-4e9a-b6c4-1f0d8e2a5c73
		summarizeBy: none
		sourceColumn: sigla_tipo

		annotation SummarizationSetBy = Automatic

	column data_apresentacao
		dataType: dateTime
		formatString: dd/mm/yyyy
		lineageTag: 9b4d2f7e-3a1c-4e8b-a5d6-7c0e3f9b1a24
		summarizeBy: none
		sourceColumn: data_apresentacao

		annotation SummarizationSetBy = Automatic

	/// Ano de apresentação da proposição (gráfico por ano)
	column ano_apresentacao = YEAR([data_apresentacao])
		dataType: int64
		formatString: 0
		lineageTag: 4f7a1c9e-2d5b-4b8e-9a3c-6e1f8d0b2c57
		summarizeBy: none

		annotation SummarizationSetBy = Automatic

	/// Origem do autor principal: deputado, Senado (projeto de senador) ou Poder Executivo
	column origem_autor =
			SWITCH(
			    TRUE(),
			    [tipo_autor_principal] = "Deputado(a)", "Deputado(a)",
			    CONTAINSSTRING([autor_principal], "Senado"), "Senado",
			    CONTAINSSTRING([tipo_autor_principal], "Executivo"), "Poder Executivo",
			    [tipo_autor_principal]
			)
		dataType: string
		lineageTag: 7e2b9d4a-1f6c-4a3e-8d5b-0c9a7e2f4b61
		summarizeBy: none

		annotation SummarizationSetBy = Automatic

	/// Partido para os gráficos: autor que é órgão (Senado, Executivo) não tem partido
	column partido_exibicao =
			IF(
			    ISBLANK([partido_autor_principal]) || [partido_autor_principal] = "",
			    [origem_autor] & " (sem partido)",
			    [partido_autor_principal]
			)
		dataType: string
		lineageTag: 3a6d0f8c-5e2b-4c7a-9f1d-8b4e2a6c0d95
		summarizeBy: none

		annotation SummarizationSetBy = Automatic

''', "column sigla_tipo")
gravar(p, s, crlf)

# --- pautas: período para o seletor Próximas × Histórico ---
p = TAB / "gold vw_pautas_monitoradas.tmdl"
s, crlf = ler(p)
s = antes_da_particao(s, '''	/// Próximas = reunião agendada (a carga de eventos cobre até D+14); Histórico = o resto
	column periodo = IF([status_alerta] = "Agendado", "Próximas", "Histórico")
		dataType: string
		lineageTag: 6d1b8e3f-4a9c-4e2d-b7a5-2f0c9e6d3b18
		summarizeBy: none

		annotation SummarizationSetBy = Automatic

''', "column periodo")
gravar(p, s, crlf)

# --- audiências: link clicável ---
p = TAB / "gold vw_audiencias_de_interesse.tmdl"
s, crlf = ler(p)
i = s.index("\tcolumn url_registro")
j = s.index("\t\tdataType: string\n", i) + len("\t\tdataType: string\n")
if "dataCategory: WebUrl" not in s[i:i + 300]:
    s = s[:j] + "\t\tdataCategory: WebUrl\n" + s[j:]
gravar(p, s, crlf)

# --- medidas ---
p = TAB / "Medidas.tmdl"
s, crlf = ler(p)
medidas = '''
	/// Prioritárias que se movimentaram nos últimos 7 dias ou entram em pauta em até 14 dias
	measure Urgentes = COUNTROWS(FILTER(VALUES('gold vw_monitoramento'[id_proposicao]), [Nível de Atenção] = 3)) + 0
		formatString: 0
		displayFolder: Atenção
		lineageTag: 1a7c4e9b-3d2f-4b8a-9e6c-5f0d2b8a1c34

	/// Prioritárias sem movimentação recente
	measure Prioridades = COUNTROWS(FILTER(VALUES('gold vw_monitoramento'[id_proposicao]), [Nível de Atenção] = 2)) + 0
		formatString: 0
		displayFolder: Atenção
		lineageTag: 8e3a1d6f-2b9c-4e7a-a4d1-6c9e3b0f2a75

	/// Fila de atenção do Início: só urgentes e prioridades (em branco nas demais, que somem da tabela)
	measure 'Fila Nível' = VAR _n = [Nível de Atenção] RETURN IF(_n >= 2, _n)
		formatString: 0
		displayFolder: Início
		lineageTag: 5c2e8a4d-1f7b-4a9e-8c3d-0b6f4e2a9d18

	measure 'Fila Rótulo' = IF(NOT ISBLANK([Fila Nível]), [Atenção Rótulo])
		displayFolder: Início
		lineageTag: 2f9b6d1e-4c8a-4e3b-9d7f-1a5c8e2b4f69

	measure 'Fila Motivo' = IF(NOT ISBLANK([Fila Nível]), [Atenção Motivo])
		displayFolder: Início
		lineageTag: 9d4a2c7e-6b1f-4d8a-b3e5-7c0a4f9d2e83

	/// Data da última movimentação, só nas linhas da fila de atenção (data de verdade, para ordenar)
	measure 'Última Mov.' = IF(NOT ISBLANK([Fila Nível]), MAX('gold vw_monitoramento'[data_ultima_movimentacao]))
		formatString: dd/mm/yyyy
		displayFolder: Início
		lineageTag: 6a1e9c3f-8d2b-4f7a-a5c4-3e9b1d7f0a26

	/// Aviso quando não há reunião agendada (fica " " quando há, para não cobrir a tabela)
	measure 'Aviso Pautas Próximas' =
			IF(
			    [Pautas Próximos 14 Dias] = 0,
			    "Nenhuma reunião com proposições do painel agendada até " & FORMAT([Data Referência] + 14, "dd/mm/yyyy") & ".",
			    " "
			)
		displayFolder: Início
		lineageTag: 3e8c5a2d-7f1b-4b9e-8a6c-2d4f0e8b3c51

	/// Aviso quando ninguém se movimentou nos últimos 30 dias
	measure 'Aviso Movimentações 30 Dias' =
			VAR _ult = CALCULATE(MAX('gold vw_monitoramento'[data_ultima_movimentacao]))
			VAR _id = CALCULATE(
			    FIRSTNONBLANK('gold vw_monitoramento'[identificacao], 1),
			    'gold vw_monitoramento'[data_ultima_movimentacao] = _ult
			)
			RETURN
			    IF(
			        [Movimentaram Últimos 30 Dias] + 0 = 0,
			        "Nenhuma movimentação nos últimos 30 dias. Movimentação mais recente: " & FORMAT(_ult, "dd/mm/yyyy") & " (" & _id & ").",
			        " "
			    )
		displayFolder: Início
		lineageTag: 7b2d9f4e-1c6a-4e8b-9f3d-5a0c7e2b8d46

	/// Resultado do item de pauta, encurtado para a lista
	measure 'Resultado (trecho)' =
			VAR _t = SELECTEDVALUE('gold vw_pautas_monitoradas'[situacao_item])
			RETURN IF(LEN(_t) > 140, LEFT(_t, 137) & "…", _t)
		displayFolder: Pautas
		lineageTag: 4c9e1b7a-2d5f-4a8e-b6c3-9e2a5d1f7b30

	/// Assunto da audiência, encurtado para a lista (texto integral no link da Câmara)
	measure 'Assunto (trecho)' =
			VAR _t = SUBSTITUTE(SELECTEDVALUE('gold vw_audiencias_de_interesse'[assunto]), UNICHAR(10), " ")
			RETURN IF(LEN(_t) > 150, LEFT(_t, 147) & "…", _t)
		displayFolder: Audiências
		lineageTag: 8f1a6c3e-5b2d-4e9a-a7c4-0d3f8b6e1a92

	/// Proposições do painel cujo autor registrado é o Senado Federal (projeto de senador)
	measure 'Origem Senado' = CALCULATE([Total Proposições Monitoradas], 'gold vw_monitoramento'[origem_autor] = "Senado") + 0
		formatString: 0
		displayFolder: Autores e Partidos
		lineageTag: 2b7d4f9a-6e1c-4b3a-8d5e-1f9c6a2e7b04

	/// Página Proposição: campos rotulados
	measure 'Proposição Selecionada' = SELECTEDVALUE('gold vw_monitoramento'[identificacao])
		displayFolder: Proposição
		lineageTag: 5e3b8d1a-9c4f-4a7e-b2d6-8a1e5c9f3b47

	measure 'Atenção da Proposição' = "Atenção: " & [Atenção Rótulo]
		displayFolder: Proposição
		lineageTag: 1d6f3a8c-4e9b-4c2a-9e7d-3b8f1c6a4e25

	measure 'Ementa Integral' = SELECTEDVALUE('gold vw_monitoramento'[ementa])
		displayFolder: Proposição
		lineageTag: 9a2c7e4f-1b8d-4f6a-a3e9-6d1b4f8c2a63

	measure 'Link Câmara' = SELECTEDVALUE('gold vw_monitoramento'[link_direto])
		dataCategory: WebUrl
		displayFolder: Proposição
		lineageTag: 6c8e2a5d-3f1b-4d9a-8b7e-4a2c9e6d1f38

	measure 'Situação atual' = SELECTEDVALUE('gold vw_monitoramento'[situacao_atual], "—")
		displayFolder: Proposição
		lineageTag: 3f1a9d6b-8e2c-4a5f-b9d3-7c4e1a8f6b02

	measure 'Órgão atual' =
			VAR _s = SELECTEDVALUE('gold vw_monitoramento'[orgao_atual])
			VAR _n = SELECTEDVALUE('gold vw_monitoramento'[nome_orgao_atual])
			RETURN IF(ISBLANK(_n), _s, _s & " — " & _n)
		displayFolder: Proposição
		lineageTag: 7d4b1e8a-2c6f-4e9b-a1d5-9e3a6c0f4d71

	measure 'Última movimentação' =
			VAR _d = MAX('gold vw_monitoramento'[data_ultima_movimentacao])
			VAR _dias = SELECTEDVALUE('gold vw_monitoramento'[dias_sem_movimentacao])
			RETURN FORMAT(_d, "dd/mm/yyyy") & " · há " & _dias & " dias"
		displayFolder: Proposição
		lineageTag: 4a8c2f6e-1d9b-4c3e-8f7a-2b5d9e1c6a84

	measure 'Autor principal' =
			VAR _a = SELECTEDVALUE('gold vw_monitoramento'[autor_principal])
			VAR _p = SELECTEDVALUE('gold vw_monitoramento'[partido_autor_principal])
			VAR _u = SELECTEDVALUE('gold vw_monitoramento'[uf_autor_principal])
			RETURN IF(ISBLANK(_p), _a, _a & " (" & _p & "/" & _u & ")")
		displayFolder: Proposição
		lineageTag: 9e6a3c1f-5b8d-4f2a-a9c7-1d4e8b2f6c19

	measure 'Posição ABCS' = COALESCE(SELECTEDVALUE('gold dim_posicionamento_abcs'[posicao_abcs]), "Sem posição registrada")
		displayFolder: Proposição
		lineageTag: 2c5f8a1d-7e3b-4a9c-b6d2-8f1a4c7e3b56

	measure Prioritária = IF(SELECTEDVALUE('gold dim_posicionamento_abcs'[prioridade]) IN {"sim", "alta"}, "Sim", "Não")
		displayFolder: Proposição
		lineageTag: 8b1e4d7a-3c9f-4e6b-a2d8-5c0f3a9e1b72

	measure Parecer = COALESCE(SELECTEDVALUE('gold dim_posicionamento_abcs'[parecer_abcs]), "Sem parecer registrado")
		displayFolder: Proposição
		lineageTag: 5d9a2e6c-1f4b-4d8e-9c3a-7b2e5f1d8a40

	measure Observações = COALESCE(SELECTEDVALUE('gold dim_posicionamento_abcs'[observacoes]), "Sem observações")
		displayFolder: Proposição
		lineageTag: 1f7c4a9e-6d2b-4e1a-b8f5-3a9d6c2e0f17

	measure 'Palavra-chave' = COALESCE(SELECTEDVALUE('gold vw_monitoramento'[keywords_encontradas]), "Incluída manualmente")
		displayFolder: Proposição
		lineageTag: 6e2a9d4f-8b1c-4f7e-a5d3-0c8b2e7a4f95

'''
if "measure Urgentes" not in s:
    s = s.replace("\n\tcolumn Column\n", medidas + "\tcolumn Column\n", 1)

# contagem da Carteira em duas partes: o número vai em negrito num cartão, o texto em outro
contagem = '''
	/// Número da contagem da Carteira (cartão em negrito)
	measure 'Contagem Número' = [Total Proposições Monitoradas] + 0
		formatString: 0
		displayFolder: Carteira
		lineageTag: 3c7e1a9d-5f2b-4d8e-a6c4-9b1d7e3f5a28

	/// Texto ao lado do número, no singular ou plural
	measure 'Contagem Texto' = IF([Contagem Número] = 1, "proposição no painel", "proposições no painel")
		displayFolder: Carteira
		lineageTag: 8f4b2d6a-1e9c-4a7f-b3d5-6c0e8a2f4b91

'''
if "measure 'Contagem Número'" not in s:
    s = s.replace("\n\tcolumn Column\n", contagem + "\tcolumn Column\n", 1)
gravar(p, s, crlf)
print("ok")
