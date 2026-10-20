"""Gera as 6 páginas do relatório em 1920×1080 (Full HD), no padrão do mockup aprovado em 20/10/2026.

Uso: python gerar_paginas.py <pasta BI> <pasta de backup>
Os visuais antigos de cada página vão uma única vez para o backup; o cabeçalho (cabecalho*) é
mantido e redimensionado por gerar_cabecalho.py, que deve rodar depois deste.
"""
import json, shutil, sys
from pathlib import Path

BI = Path(sys.argv[1])
BACKUP = Path(sys.argv[2])
DEF = BI / "BI_Monitoramento_Proposicoes.Report" / "definition"
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.12.0/schema.json"
W, H = 1920, 1080

INICIO, CARTEIRA, PROPOSICAO = "144a96dc6239db74d11a", "2f1b62b82156458deeae", "b65619ca9073f1dd488a"
AUTORES, PAUTAS, AUDIENCIAS = "0e004dfd0732f57f2943", "a0b7e00206a8b0176a8a", "0fb3418f7d50e4d08b27"
NAV = [(INICIO, "Início", 110), (CARTEIRA, "Carteira", 120), (PAUTAS, "Pautas", 110), (AUDIENCIAS, "Audiências", 140), (AUTORES, "Autores e partidos", 200)]

MON, POS, PAU, AUD, MED = "gold vw_monitoramento", "gold dim_posicionamento_abcs", "gold vw_pautas_monitoradas", "gold vw_audiencias_de_interesse", "Medidas"
VERDE, TINTA, TINTA2, LINHA = "#00533A", "#14231B", "#4A5A51", "#E3E8E5"


# ---------- peças ----------
def lit(v):
    return {"expr": {"Literal": {"Value": v}}}


def txt(v):
    return lit("'" + v.replace("'", "''") + "'")


def cor(hexa):
    return {"solid": {"color": lit(f"'{hexa}'")}}


def col(ent, prop):
    return {"Column": {"Expression": {"SourceRef": {"Entity": ent}}, "Property": prop}}


def med(prop):
    return {"Measure": {"Expression": {"SourceRef": {"Entity": MED}}, "Property": prop}}


def ref(field):
    k = next(iter(field))
    return f'{field[k]["Expression"]["SourceRef"]["Entity"]}.{field[k]["Property"]}'


def proj(field, nome=None, ativo=False):
    p = {"field": field, "queryRef": ref(field), "nativeQueryRef": field[next(iter(field))]["Property"]}
    if nome is not None:
        p["displayName"] = nome
    if ativo:
        p["active"] = True
    return p


def caixa(titulo=None, fundo=True):
    o = {
        "background": [{"properties": {"show": lit("true" if fundo else "false"), "color": cor("#FFFFFF"), "transparency": lit("0D")}}],
        "border": [{"properties": {"show": lit("false")}}],
        "dropShadow": [{"properties": {"show": lit("false")}}],
        "visualHeader": [{"properties": {"show": lit("false")}}],
        "title": [{"properties": {"show": lit("false")}}],
        "subTitle": [{"properties": {"show": lit("false")}}],
    }
    if titulo:
        o["title"] = [{"properties": {"show": lit("true"), "text": txt(titulo), "fontSize": lit("14D"), "bold": lit("true"), "fontColor": cor(TINTA)}}]
    return o


def visual(nome, x, y, w, h, z, corpo, tab=None):
    return {"$schema": SCHEMA, "name": nome,
            "position": {"x": x, "y": y, "z": z, "height": h, "width": w, "tabOrder": tab if tab is not None else z},
            "visual": {**corpo, "drillFilterOtherVisuals": True}}


def textbox(nome, x, y, w, h, z, runs, fundo=False):
    return visual(nome, x, y, w, h, z, {
        "visualType": "textbox",
        "objects": {"general": [{"properties": {"paragraphs": [{"textRuns": runs}]}}]},
        "visualContainerObjects": caixa(fundo=fundo)})


def run(texto, tam=12, cor_=TINTA2, negrito=False):
    st = {"fontFamily": "Segoe UI", "fontSize": f"{tam}pt", "color": cor_}
    if negrito:
        st["fontWeight"] = "bold"
    return {"value": texto, "textStyle": st}


def card(nome, x, y, w, h, z, medida, cor_texto=TINTA, tam=12, fundo=False, cor_medida=None, negrito=False):
    labels = {"color": cor(cor_texto), "fontSize": lit(f"{tam}D"), "fontFamily": lit("'Segoe UI Bold'" if negrito else "'Segoe UI'")}
    if cor_medida:
        labels["color"] = {"solid": {"color": {"expr": med(cor_medida)}}}
    return visual(nome, x, y, w, h, z, {
        "visualType": "card",
        "query": {"queryState": {"Values": {"projections": [proj(med(medida))]}}},
        "objects": {"labels": [{"properties": labels}],
                    "categoryLabels": [{"properties": {"show": lit("false")}}],
                    "wordWrap": [{"properties": {"show": lit("true")}}]},
        "visualContainerObjects": caixa(fundo=fundo)})


def campo(nome, x, y, w, h, z, medida, rotulo):
    """Valor com rótulo embaixo e quebra de linha (o multiRowCard corta textos longos)."""
    return visual(nome, x, y, w, h, z, {
        "visualType": "card",
        "query": {"queryState": {"Values": {"projections": [proj(med(medida), rotulo)]}}},
        "objects": {"labels": [{"properties": {"color": cor(TINTA), "fontSize": lit("13D"), "fontFamily": lit("'Segoe UI'")}}],
                    "categoryLabels": [{"properties": {"show": lit("true"), "color": cor(TINTA2), "fontSize": lit("10D")}}],
                    "wordWrap": [{"properties": {"show": lit("true")}}]},
        "visualContainerObjects": caixa(fundo=False)})


def kpis(nome, x, y, w, h, z, itens):
    """Cartões de indicador (cardVisual com várias medidas, como os do relatório original)."""
    return visual(nome, x, y, w, h, z, {
        "visualType": "cardVisual",
        "query": {"queryState": {"Data": {"projections": [proj(med(m), rotulo) for m, rotulo in itens]}}},
        "visualContainerObjects": caixa(fundo=False)})


def multirow(nome, x, y, w, h, z, medidas, titulo):
    return visual(nome, x, y, w, h, z, {
        "visualType": "multiRowCard",
        "query": {"queryState": {"Values": {"projections": [proj(med(m)) for m in medidas]}}},
        "objects": {"card": [{"properties": {"cardPadding": lit("12D"), "barShow": lit("false")}}],
                    "dataLabels": [{"properties": {"fontSize": lit("13D"), "color": cor(TINTA)}}],
                    "categoryLabels": [{"properties": {"fontSize": lit("10D"), "color": cor(TINTA2)}}]},
        "visualContainerObjects": caixa(titulo)})


def slicer(nome, x, y, w, h, z, field, titulo, modo="Dropdown"):
    obj = {"data": [{"properties": {"mode": lit(f"'{modo}'")}}],
           "header": [{"properties": {"show": lit("true"), "text": txt(titulo), "fontColor": cor(TINTA2), "textSize": lit("11D")}}],
           "items": [{"properties": {"textSize": lit("12D")}}]}
    if modo == "Basic":
        obj["general"] = [{"properties": {"orientation": lit("1D")}}]
        obj["selection"] = [{"properties": {"singleSelect": lit("true")}}]
    return visual(nome, x, y, w, h, z, {
        "visualType": "slicer",
        "query": {"queryState": {"Values": {"projections": [proj(field, ativo=True)]}}},
        "objects": obj,
        "visualContainerObjects": {"background": [{"properties": {"show": lit("false")}}],
                                   "border": [{"properties": {"show": lit("false")}}],
                                   "title": [{"properties": {"show": lit("false")}}]}})


def barras(nome, x, y, w, h, z, categoria, medida, titulo, tipo="clusteredBarChart", ordenar_categoria=False):
    sort = {"field": categoria, "direction": "Ascending"} if ordenar_categoria else {"field": med(medida), "direction": "Descending"}
    return visual(nome, x, y, w, h, z, {
        "visualType": tipo,
        "query": {"queryState": {"Category": {"projections": [proj(categoria, ativo=True)]},
                                 "Y": {"projections": [proj(med(medida), "Proposições")]}},
                  "sortDefinition": {"sort": [sort], "isDefaultSort": True}},
        "objects": {"valueAxis": [{"properties": {"show": lit("false"), "showAxisTitle": lit("false")}}],
                    "categoryAxis": [{"properties": {"showAxisTitle": lit("false"), "fontSize": lit("11D")}}],
                    "labels": [{"properties": {"show": lit("true"), "fontSize": lit("11D")}}],
                    "dataPoint": [{"properties": {"fill": cor("#09814A")}}]},
        "visualContainerObjects": caixa(titulo)})


def tabela(nome, x, y, w, h, z, colunas, ordem, titulo=None, atencao=False, filtros=None, url_icone=True):
    """colunas: [(field, nome, largura)]; atencao=True pinta a linha pelo nível (1ª coluna = faixa, 2ª = rótulo)."""
    projs = [proj(f, n) for f, n, _ in colunas]
    refs = [p["queryRef"] for p in projs]
    todas = {"data": [{"dataViewWildcard": {"matchingOption": 1}}]}
    values = [{"properties": {"urlIcon": lit("true" if url_icone else "false"), "wordWrap": lit("true"), "fontSize": lit("12D")}}]
    if atencao:
        for r in refs:
            values.append({"properties": {"backColor": {"solid": {"color": {"expr": med("Atenção Cor Fundo")}}}}, "selector": {**todas, "metadata": r}})
        values.append({"properties": {"backColor": {"solid": {"color": {"expr": med("Atenção Cor")}}}, "fontColor": {"solid": {"color": {"expr": med("Atenção Cor")}}}}, "selector": {**todas, "metadata": refs[0]}})
        values.append({"properties": {"fontColor": {"solid": {"color": {"expr": med("Atenção Cor Texto")}}}}, "selector": {**todas, "metadata": refs[1]}})
    corpo = {
        "visualType": "tableEx",
        "query": {"queryState": {"Values": {"projections": projs}}, "sortDefinition": {"sort": ordem}},
        "objects": {
            "columnHeaders": [{"properties": {"wordWrap": lit("true"), "fontSize": lit("12D"), "fontColor": cor(TINTA), "backColor": cor("#F2F5F3")}}],
            "values": values,
            "grid": [{"properties": {"gridVertical": lit("false"), "gridHorizontal": lit("true"), "gridHorizontalColor": cor(LINHA), "rowPadding": lit("5D")}}],
            "total": [{"properties": {"totals": lit("false")}}],
            "columnWidth": [{"properties": {"value": lit(f"{w_}D")}, "selector": {"metadata": r}} for r, (_, _, w_) in zip(refs, colunas)],
        },
        "visualContainerObjects": caixa(titulo)}
    v = visual(nome, x, y, w, h, z, corpo)
    if filtros:
        v["filterConfig"] = {"filters": filtros}
    return v


def filtro_igual(nome, ent, prop, valor):
    return {"name": nome, "field": col(ent, prop), "type": "Categorical",
            "filter": {"Version": 2, "From": [{"Name": "t", "Entity": ent, "Type": 0}],
                       "Where": [{"Condition": {"In": {"Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": prop}}],
                                                       "Values": [[{"Literal": {"Value": valor}}]]}}}]},
            "howCreated": "User"}


def filtro_ate(nome, ent, prop, limite):
    return {"name": nome, "field": col(ent, prop), "type": "Advanced",
            "filter": {"Version": 2, "From": [{"Name": "t", "Entity": ent, "Type": 0}],
                       "Where": [{"Condition": {"Comparison": {"ComparisonKind": 4,
                                                               "Left": {"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": prop}},
                                                               "Right": {"Literal": {"Value": f"{limite}L"}}}}}]},
            "howCreated": "User"}


def botao(nome, x, y, w, h, z, texto, link, fundo, cor_texto, tam=12, negrito=False):
    return visual(nome, x, y, w, h, z, {
        "visualType": "actionButton",
        "objects": {
            "icon": [{"properties": {"shapeType": lit("'blank'")}, "selector": {"id": "default"}}],
            "text": [{"properties": {"show": lit("true")}},
                     {"properties": {"text": txt(texto), "fontSize": lit(f"{tam}D"), "fontColor": cor(cor_texto), "bold": lit("true" if negrito else "false")}, "selector": {"id": "default"}}],
            "fill": [{"properties": {"show": lit("true" if fundo else "false"), "fillColor": cor(fundo or "#FFFFFF"), "transparency": lit("0D")}, "selector": {"id": "default"}}],
            "outline": [{"properties": {"show": lit("false")}, "selector": {"id": "default"}}],
        },
        "visualContainerObjects": {"visualLink": [{"properties": link}],
                                   "visualHeader": [{"properties": {"show": lit("false")}}]}})


def navegacao(pagina):
    vs, x = [], 560
    for i, (pid, rotulo, w) in enumerate(NAV):
        ativa = pid == pagina
        vs.append(botao(f"nav{i + 1}", x, 18, w, 40, 1500 + i, rotulo,
                        {"show": lit("true"), "type": lit("'PageNavigation'"), "navigationSection": txt(pid)},
                        "#FFFFFF" if ativa else "#0B6B4B", VERDE if ativa else "#FFFFFF", 13, ativa))
        x += w + 8
    return vs


def cabecalho(pagina, titulo, fonte="Dados Atualizados Em", nav=True):
    vs = [textbox("v00Titulo", 240, 12, 320, 52, 1400, [run(titulo, 20, "#FFFFFF", True)]),
          card("v00Atualizacao", 1480, 10, 420, 56, 1410, fonte, "#FFFFFF", 12)]
    return vs + (navegacao(pagina) if nav else [])


# ---------- páginas ----------
def carteira():
    filtros_linha = [
        ("v04FiltroPrioridade", 325, 180, col(POS, "prioridade"), "Prioritária"),
        ("v05FiltroPosicao", 520, 255, col(POS, "posicao_abcs"), "Posição ABCS"),
        ("v06FiltroSituacao", 790, 285, col(MON, "situacao_atual"), "Situação"),
        ("v07FiltroOrgao", 1090, 180, col(MON, "orgao_atual"), "Órgão atual"),
        ("v08FiltroTema", 1285, 285, col(MON, "keywords_encontradas"), "Palavra-chave"),
    ]
    busca = json.loads(json.dumps(BUSCA))
    busca.pop("parentGroupName", None)
    busca.pop("filterConfig", None)
    busca["name"] = "v03Busca"
    busca["position"] = {"x": 30, "y": 100, "z": 2000, "height": 80, "width": 280, "tabOrder": 2000}
    busca["visual"].setdefault("visualContainerObjects", {})["title"] = [{"properties": {"show": lit("true"), "text": txt("Buscar proposição"), "fontSize": lit("11D"), "fontColor": cor(TINTA2)}}]
    vs = cabecalho(CARTEIRA, "Carteira") + [busca]
    vs += [slicer(n, x, 100, w, 80, 2100 + i, f, t) for i, (n, x, w, f, t) in enumerate(filtros_linha)]
    # o cartão clássico centraliza o texto: caixas justas deixam número e texto lado a lado
    vs.append(card("v09ContagemNumero", 1600, 118, 60, 56, 2600, "Contagem Número", TINTA, 16, negrito=True))
    vs.append(card("v09ContagemTexto", 1652, 118, 230, 56, 2610, "Contagem Texto", TINTA, 14))
    leg = [run("Legenda:   ", 11)]
    for hexa, t in [("#D92D20", "Urgente — prioritária que se movimentou nos últimos 7 dias ou entra em pauta em até 14 dias"),
                    ("#E8590C", "Prioridade — marcada como prioritária pela ABCS"), ("#D0D5DD", "Acompanhamento")]:
        leg += [{"value": "▌", "textStyle": {"fontSize": "14pt", "color": hexa}}, run(f" {t}        ", 11)]
    vs.append(textbox("v10Legenda", 30, 188, 1530, 38, 2700, leg))
    vs.append(botao("v11BotaoDetalhes", 1590, 186, 300, 42, 2800, "Ver detalhes da selecionada",
                    {"show": lit("true"), "type": lit("'Drillthrough'"), "drillthroughSection": txt(PROPOSICAO),
                     "disabledTooltip": txt("Clique em uma linha da tabela para ver os detalhes")}, VERDE, "#FFFFFF", 12))
    vs.append(tabela("v12TabelaCarteira", 30, 236, 1860, 820, 3000, [
        (med("Nível de Atenção"), " ", 26), (med("Atenção Rótulo"), "Atenção", 170),
        (col(MON, "identificacao"), "Proposição", 150), (med("Ementa Trecho"), "Ementa (trecho)", 520),
        (col(POS, "posicao_abcs"), "Posição ABCS", 280), (col(MON, "orgao_atual"), "Órgão", 95),
        (col(MON, "data_ultima_movimentacao"), "Última mov.", 125), (med("Próxima Ação"), "Próxima ação", 300),
        (col(MON, "link_direto"), "Câmara", 80)],
        [{"field": med("Nível de Atenção"), "direction": "Descending"}, {"field": col(MON, "data_ultima_movimentacao"), "direction": "Descending"}],
        atencao=True))
    return "Carteira", vs


def inicio():
    vs = cabecalho(INICIO, "Início")
    vs.append(kpis("v01Indicadores", 30, 90, 1860, 140, 2000, [
        ("Total Proposições Monitoradas", "Proposições no painel"), ("Urgentes", "Urgentes"), ("Prioridades", "Prioridades"),
        ("Movimentaram Últimos 7 Dias", "Movimentaram em 7 dias"), ("Pautas Próximos 14 Dias", "Pautas em 14 dias"),
        ("Audiências Agendadas", "Audiências agendadas")]))
    vs.append(tabela("v02Fila", 30, 245, 1090, 810, 3000, [
        (med("Fila Nível"), " ", 26), (med("Fila Rótulo"), "Atenção", 150), (col(MON, "identificacao"), "Proposição", 160),
        (med("Fila Motivo"), "Motivo", 520), (med("Última Mov."), "Última mov.", 140)],
        [{"field": med("Fila Nível"), "direction": "Descending"}, {"field": med("Última Mov."), "direction": "Descending"}], titulo="Fila de atenção — urgentes primeiro, depois prioridades", atencao=True))
    vs.append(tabela("v03PautasProximas", 1140, 245, 750, 380, 3100, [
        (col(PAU, "data_hora_inicio"), "Data", 150), (col(PAU, "sigla_orgao"), "Comissão", 100),
        (col(PAU, "identificacao"), "Proposição", 140), (col(PAU, "nome_relator"), "Relator", 300)],
        [{"field": col(PAU, "data_hora_inicio"), "direction": "Ascending"}], titulo="Pautas nos próximos 14 dias",
        filtros=[filtro_igual("fAgendado", PAU, "status_alerta", "'Agendado'")]))
    vs.append(card("v04AvisoPautas", 1160, 330, 710, 90, 3150, "Aviso Pautas Próximas", TINTA2, 12))
    vs.append(tabela("v05Movimentacoes", 1140, 645, 750, 410, 3200, [
        (col(MON, "data_ultima_movimentacao"), "Data", 110), (col(MON, "identificacao"), "Proposição", 140),
        (col(MON, "ultima_movimentacao"), "O que aconteceu", 330), (col(MON, "orgao_atual"), "Órgão", 100)],
        [{"field": col(MON, "data_ultima_movimentacao"), "direction": "Descending"}], titulo="Movimentações nos últimos 30 dias",
        filtros=[filtro_ate("fUltimos30", MON, "dias_sem_movimentacao", 30)]))
    vs.append(card("v06AvisoMov", 1160, 730, 710, 110, 3250, "Aviso Movimentações 30 Dias", TINTA2, 12))
    return "Início", vs


def proposicao():
    vs = cabecalho(PROPOSICAO, "Proposição", nav=False)
    vs.append(botao("v01Voltar", 30, 92, 220, 44, 2000, "← Voltar", {"show": lit("true"), "type": lit("'Back'")}, "#FFFFFF", VERDE, 12, True))
    vs.append(card("v02Numero", 270, 84, 420, 60, 2100, "Proposição Selecionada", TINTA, 24))
    vs.append(card("v03Atencao", 700, 92, 360, 44, 2150, "Atenção da Proposição", TINTA2, 13, cor_medida="Atenção Cor Texto"))
    vs.append(botao("v04Camara", 1640, 92, 250, 44, 2200, "Abrir na Câmara ↗",
                    {"show": lit("true"), "type": lit("'WebUrl'"), "webUrl": {"expr": med("Link Câmara")}}, VERDE, "#FFFFFF", 12, True))
    vs.append(card("v05Ementa", 30, 150, 1860, 80, 2300, "Ementa Integral", TINTA, 14, fundo=True))
    vs.append(textbox("v06BlocoTramitacao", 30, 245, 1050, 210, 2400, [run("Tramitação", 14, TINTA, True)], fundo=True))
    for i, (m, r) in enumerate([("Situação atual", "Situação atual"), ("Órgão atual", "Órgão atual"),
                                ("Última movimentação", "Última movimentação"), ("Autor principal", "Autor principal")]):
        vs.append(campo(f"v06Campo{i}", 45 + (i % 2) * 515, 285 + (i // 2) * 82, 500, 78, 2410 + i, m, r))
    vs.append(textbox("v07BlocoPosicionamento", 1100, 245, 790, 210, 2500, [run("Posicionamento ABCS", 14, TINTA, True)], fundo=True))
    for i, (m, r) in enumerate([("Posição ABCS", "Posição ABCS"), ("Prioritária", "Prioritária"), ("Próxima Ação", "Próxima ação"),
                                ("Parecer", "Parecer"), ("Observações", "Observações"), ("Palavra-chave", "Palavra-chave")]):
        vs.append(campo(f"v07Campo{i}", 1110 + (i % 3) * 258, 285 + (i // 3) * 82, 250, 78, 2510 + i, m, r))
    vs.append(tabela("v08Tramitacoes", 30, 470, 1090, 585, 3000, [
        (col("gold vw_tramitacoes", "data_hora"), "Data", 150), (col("gold vw_tramitacoes", "sigla_orgao"), "Órgão", 90),
        (col("gold vw_tramitacoes", "despacho"), "O que aconteceu", 780)],
        [{"field": col("gold vw_tramitacoes", "data_hora"), "direction": "Descending"}], titulo="Tramitações (mais recentes primeiro)"))
    vs.append(tabela("v09Pautas", 1140, 470, 750, 585, 3100, [
        (col(PAU, "data_hora_inicio"), "Data", 140), (col(PAU, "sigla_orgao"), "Comissão", 90),
        (col(PAU, "status_alerta"), "Situação", 140), (col(PAU, "nome_relator"), "Relator", 130), (med("Resultado (trecho)"), "Resultado", 200)],
        [{"field": col(PAU, "data_hora_inicio"), "direction": "Descending"}], titulo="Pautas em que apareceu"))
    return "Proposição", vs


def pautas():
    vs = cabecalho(PAUTAS, "Pautas", "Dados Atualizados Em")
    vs.append(kpis("v01Indicadores", 30, 90, 1180, 130, 2000, [
        ("Pautas Agendadas", "Reuniões agendadas (14 dias)"), ("Total Eventos com Pauta", "Reuniões no histórico"),
        ("Pautas Votadas", "Itens votados"), ("Pautas Canceladas", "Itens em reuniões canceladas")]))
    vs.append(slicer("v02Periodo", 1230, 100, 360, 100, 2100, col(PAU, "periodo"), "Período"))
    vs.append(slicer("v03Comissao", 1610, 100, 280, 100, 2200, col(PAU, "sigla_orgao"), "Comissão"))
    vs.append(tabela("v04Pautas", 30, 235, 1860, 820, 3000, [
        (col(PAU, "data_hora_inicio"), "Data", 170), (col(PAU, "sigla_orgao"), "Comissão", 110),
        (col(PAU, "identificacao"), "Proposição", 150), (col(PAU, "nome_relator"), "Relator", 250),
        (col(PAU, "partido_relator"), "Partido", 130), (col(PAU, "status_alerta"), "Situação", 200), (med("Resultado (trecho)"), "Resultado (trecho)", 760)],
        [{"field": col(PAU, "data_hora_inicio"), "direction": "Descending"}]))
    return "Pautas", vs


def audiencias():
    vs = cabecalho(AUDIENCIAS, "Audiências")
    vs.append(kpis("v01Indicadores", 30, 90, 560, 130, 2000, [("Audiências Agendadas", "Agendadas"), ("Total Audiências de Interesse", "Sugeridas no total")]))
    vs.append(textbox("v02Nota", 610, 110, 960, 90, 2100, [run(
        "Sugestões automáticas: o assunto da audiência contém uma palavra-chave do monitoramento. "
        "Não indicam vínculo com uma proposição específica. O texto completo, com os convidados, está no link da Câmara.", 12)]))
    vs.append(slicer("v03Tema", 1590, 100, 300, 100, 2200, col(AUD, "keywords_encontradas"), "Palavra-chave"))
    vs.append(tabela("v04Audiencias", 30, 235, 1860, 820, 3000, [
        (col(AUD, "data_hora_inicio"), "Data", 170), (col(AUD, "sigla_orgao"), "Comissão", 110),
        (med("Assunto (trecho)"), "Assunto (trecho)", 900), (col(AUD, "keywords_encontradas"), "Palavra-chave", 330),
        (col(AUD, "status_alerta"), "Situação", 140), (col(AUD, "url_registro"), "Câmara", 90)],
        [{"field": col(AUD, "data_hora_inicio"), "direction": "Descending"}]))
    return "Audiências", vs


def autores():
    vs = cabecalho(AUTORES, "Autores e partidos")
    vs.append(kpis("v01Indicadores", 30, 90, 820, 120, 2000, [
        ("Total Autores Distintos", "Autores"), ("Total Partidos Distintos", "Partidos"), ("Total UFs Distintas", "UFs"), ("Origem Senado", "Origem Senado")]))
    vs.append(textbox("v02Nota", 870, 100, 720, 100, 2100, [run(
        "Autoria principal das proposições do painel. Partido e UF são os atuais do autor. "
        "Projetos vindos do Senado têm o Senado Federal como autor, por isso ficam sem partido. "
        "Clique em uma barra para filtrar a página inteira.", 12)]))
    vs.append(slicer("v03Prioridade", 1610, 100, 280, 100, 2200, col(POS, "prioridade"), "Prioritária"))
    vs.append(barras("v04PorAno", 30, 225, 900, 400, 3000, col(MON, "ano_apresentacao"), "Total Proposições Monitoradas",
                     "Proposições por ano de apresentação", "clusteredColumnChart", ordenar_categoria=True))
    vs.append(barras("v05PorUF", 950, 225, 460, 400, 3100, col(MON, "uf_exibicao"), "Total Proposições Monitoradas", "Por UF do autor"))
    vs.append(barras("v06PorTipo", 1430, 225, 460, 400, 3200, col(MON, "sigla_tipo"), "Total Proposições Monitoradas", "Por tipo de proposição"))
    vs.append(barras("v07PorPartido", 30, 640, 1100, 415, 3300, col(MON, "partido_exibicao"), "Total Proposições Monitoradas", "Por partido do autor"))
    vs.append(tabela("v08Autores", 1150, 640, 740, 415, 3400, [
        (col(MON, "autor_principal"), "Autor", 330), (col(MON, "partido_exibicao"), "Partido", 170),
        (col(MON, "uf_exibicao"), "UF", 60), (med("Total Proposições Monitoradas"), "Proposições", 110)],
        [{"field": med("Total Proposições Monitoradas"), "direction": "Descending"}], titulo="Autores com mais proposições", url_icone=False))
    return "Autores e partidos", vs


# ---------- grava ----------
# a caixa de busca (textSlicer) é copiada do Início original, que vai para o backup na 1ª execução
_busca = [DEF / "pages" / INICIO / "visuals" / "e2af0ffe398caea31886" / "visual.json",
          BACKUP / f"visuais_antigos_{INICIO}" / "e2af0ffe398caea31886" / "visual.json"]
BUSCA = json.loads(next(f for f in _busca if f.exists()).read_text(encoding="utf-8"))
PAGINAS = {INICIO: inicio, CARTEIRA: carteira, PROPOSICAO: proposicao, PAUTAS: pautas, AUDIENCIAS: audiencias, AUTORES: autores}
for pid, gerar in PAGINAS.items():
    pdir = DEF / "pages" / pid
    guardado = BACKUP / f"visuais_antigos_{pid}"
    if not guardado.exists():
        guardado.mkdir(parents=True)
        for d in (pdir / "visuals").iterdir():
            if not d.name.startswith("cabecalho"):
                shutil.move(str(d), str(guardado / d.name))
    else:
        for d in (pdir / "visuals").iterdir():
            if not d.name.startswith("cabecalho"):
                shutil.rmtree(d)
    nome, vs = gerar()
    for v in vs:
        d = pdir / "visuals" / v["name"]
        d.mkdir(exist_ok=True)
        (d / "visual.json").write_text(json.dumps(v, ensure_ascii=False, indent=2), encoding="utf-8")
    page = json.loads((pdir / "page.json").read_text(encoding="utf-8"))
    page["displayName"], page["width"], page["height"] = nome, W, H
    if pid == PROPOSICAO:
        page["visibility"] = "HiddenInViewMode"
    (pdir / "page.json").write_text(json.dumps(page, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{nome}: {len(vs)} visuais")

pj = DEF / "pages" / "pages.json"
pages = json.loads(pj.read_text(encoding="utf-8"))
pages["pageOrder"] = [INICIO, CARTEIRA, PAUTAS, AUDIENCIAS, AUTORES, PROPOSICAO]
pages["activePageName"] = INICIO
pages["landingPageName"] = INICIO
pj.write_text(json.dumps(pages, ensure_ascii=False, indent=2), encoding="utf-8")
for f in (DEF / "pages").rglob("*.json"):
    json.loads(f.read_text(encoding="utf-8"))
print("ok")
