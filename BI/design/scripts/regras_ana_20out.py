"""Regras da Ana (áudio de 20/10/2026) no modelo e no relatório.

- Painel = acompanhadas + marcadas SIM, sem as marcadas NÃO e sem arquivadas/transformadas em norma
  (coluna calculada em_painel; mesma regra do e-mail diário). Substitui o filtro "relevância = SIM".
- Atenção: Urgente = prioritária que se movimentou nos últimos 7 dias (ou entra em pauta em
  até 14 dias, decisão do Erick); Prioridade = prioritária parada; Acompanhamento = as demais.
"""
import json, re, sys
from pathlib import Path


def ler(p):
    bruto = p.read_bytes()
    return bruto.decode("utf-8").replace("\r\n", "\n"), b"\r\n" in bruto


def gravar(p, texto, crlf):
    p.write_text(texto, encoding="utf-8", newline="\r\n" if crlf else "\n")

BI = Path(sys.argv[1])  # .../BI
SM = BI / "BI_Monitoramento_Proposicoes.SemanticModel" / "definition" / "tables"
REP = BI / "BI_Monitoramento_Proposicoes.Report" / "definition"

# --- coluna calculada em_painel ---
p = SM / "gold vw_monitoramento.tmdl"
s, crlf = ler(p)
if "column em_painel" not in s:
    coluna = '''	/// Entra no painel: acompanhada ou marcada SIM na aba "Proposições", sem as marcadas NÃO e sem as encerradas
	/// (arquivada ou transformada em norma). Mesma regra do e-mail diário; decidido com a Ana em 20/10/2026
	column em_painel =
			VAR _relevancia = UPPER(TRIM(LOOKUPVALUE('gold dim_relevancia'[relevancia], 'gold dim_relevancia'[id_proposicao], [id_proposicao])))
			VAR _encerrada = [situacao_atual] IN {"Arquivada", "Transformado em Norma Jurídica"}
			RETURN ([acompanhada] || _relevancia = "SIM") && NOT (_relevancia IN {"NÃO", "NAO"}) && NOT _encerrada
		dataType: boolean
		lineageTag: 5d9a2c7e-1f4b-4e8a-b3d6-9c0e7a2f4b18
		summarizeBy: none

		annotation SummarizationSetBy = Automatic

'''
    i = s.index("\tpartition ")
    s = s[:i] + coluna + s[i:]
    gravar(p, s, crlf)

# --- medidas: filtro do universo e níveis de atenção ---
p = SM / "Medidas.tmdl"
s, crlf = ler(p)
s = s.replace("'gold dim_relevancia'[relevancia] = \"SIM\"", "'gold vw_monitoramento'[em_painel] = TRUE()")
# o filtro global sai de dim_relevancia: as contagens "independentes do painel" passam a remover em_painel
s = s.replace("REMOVEFILTERS('gold dim_relevancia')", "REMOVEFILTERS('gold vw_monitoramento'[em_painel])")
s = s.replace("/// Total de proposições avaliadas como relevantes ao setor pelo time político (dim_relevancia = SIM)",
              "/// Proposições do painel: acompanhadas + marcadas SIM, sem NÃO e sem encerradas (coluna em_painel)")


def trocar_medida(texto, nome, nova):
    ini = texto.index(f"\tmeasure '{nome}' =")
    ini = texto.rindex("\n\n", 0, ini) + 2  # inclui o comentário ///
    fim = texto.index("\n\n", texto.index("lineageTag:", ini)) + 2
    return texto[:ini] + nova + texto[fim:]


s = trocar_medida(s, "Nível de Atenção", '''	/// Nível de atenção (regra da Ana, 20/10/2026): 3 = Urgente, prioritária que se movimentou nos últimos 7 dias
	/// (mesma régua de 'Movimentaram Últimos 7 Dias') ou entra em pauta em até 14 dias (decisão do Erick); 2 = Prioridade, prioritária parada; 1 = Acompanhamento; 0 = encerrada.
	/// Parada não é atraso: sem prioridade, nunca ganha cor. Em branco fora do contexto de uma proposição
	measure 'Nível de Atenção' =
			VAR _id = SELECTEDVALUE('gold vw_monitoramento'[id_proposicao])
			VAR _situacao = SELECTEDVALUE('gold vw_monitoramento'[situacao_atual])
			VAR _prioritaria = SELECTEDVALUE('gold dim_posicionamento_abcs'[prioridade]) IN {"sim", "alta"}
			VAR _dias = SELECTEDVALUE('gold vw_monitoramento'[dias_sem_movimentacao])
			VAR _movimentou = NOT ISBLANK(_dias) && _dias <= 7
			VAR _pauta = [Pautas Próximos 14 Dias] > 0
			RETURN
			    IF(
			        ISBLANK(_id),
			        BLANK(),
			        SWITCH(
			            TRUE(),
			            _situacao IN {"Arquivada", "Transformado em Norma Jurídica"}, 0,
			            _prioritaria && (_movimentou || _pauta), 3,
			            _prioritaria, 2,
			            1
			        )
			    )
		formatString: 0
		displayFolder: Atenção
		lineageTag: 8d2b5f9a-4e1c-4b7d-a6e3-9c0f2b8d5a16

''')
s = trocar_medida(s, "Atenção Rótulo", '''	/// Rótulo do nível de atenção, para acompanhar a cor (cor nunca sozinha)
	measure 'Atenção Rótulo' =
			SWITCH(
			    [Nível de Atenção],
			    3, "Urgente",
			    2, "Prioridade",
			    1, "Acompanhamento",
			    0, "Encerrada"
			)
		displayFolder: Atenção
		lineageTag: 3b7e1d9c-6a4f-4e2b-9f8a-2d5c0b7e1a43

''')
s = trocar_medida(s, "Atenção Motivo", '''	/// Por que a proposição está nesse nível
	measure 'Atenção Motivo' =
			VAR _nivel = [Nível de Atenção]
			VAR _dias = SELECTEDVALUE('gold vw_monitoramento'[dias_sem_movimentacao])
			VAR _movimentou = NOT ISBLANK(_dias) && _dias <= 7
			VAR _pauta = [Pautas Próximos 14 Dias] > 0
			RETURN
			    SWITCH(
			        TRUE(),
			        ISBLANK(_nivel), BLANK(),
			        _nivel = 0, "Arquivada ou transformada em norma",
			        _nivel = 3 && _movimentou && _pauta, "Prioritária: movimentou nos últimos 7 dias e está em pauta",
			        _nivel = 3 && _movimentou, "Prioritária: movimentou nos últimos 7 dias",
			        _nivel = 3, "Prioritária: em pauta nos próximos 14 dias",
			        _nivel = 2, "Prioritária, sem movimentação recente",
			        "Acompanhamento"
			    )
		displayFolder: Atenção
		lineageTag: 5a9c3e1f-8b2d-4f6a-b7e4-0c3d9a1f6b58

''')
s = s.replace(" proposição relevante\"", " proposição no painel\"").replace(" proposições relevantes\"", " proposições no painel\"")
gravar(p, s, crlf)

# --- filtro global do relatório: em_painel = verdadeiro ---
p = REP / "report.json"
rep = json.loads(p.read_text(encoding="utf-8"))
rep["filterConfig"]["filters"] = [{
    "name": "filtroEmPainel",
    "field": {"Column": {"Expression": {"SourceRef": {"Entity": "gold vw_monitoramento"}}, "Property": "em_painel"}},
    "type": "Categorical",
    "filter": {
        "Version": 2,
        "From": [{"Name": "m", "Entity": "gold vw_monitoramento", "Type": 0}],
        "Where": [{"Condition": {"In": {
            "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "m"}}, "Property": "em_painel"}}],
            "Values": [[{"Literal": {"Value": "true"}}]],
        }}}],
    },
    "howCreated": "User",
    "isHiddenInViewMode": True,
}]
p.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
print("ok")
