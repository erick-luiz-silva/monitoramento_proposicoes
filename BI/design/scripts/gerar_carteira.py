"""Gera a página Carteira (antiga "Monitoramento") em PBIR, no padrão do mockup aprovado."""
import json, shutil, sys
from pathlib import Path

RAIZ = Path(sys.argv[1])  # .../BI_Monitoramento_Proposicoes.Report/definition
PAGINA = RAIZ / "pages" / "2f1b62b82156458deeae"
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.12.0/schema.json"
DETALHE = "b65619ca9073f1dd488a"
BACKUP = Path(sys.argv[2])

MON = "gold vw_monitoramento"
POS = "gold dim_posicionamento_abcs"
MED = "Medidas"


def lit(v):
    return {"expr": {"Literal": {"Value": v}}}


def col(ent, prop):
    return {"Column": {"Expression": {"SourceRef": {"Entity": ent}}, "Property": prop}}


def med(prop):
    return {"Measure": {"Expression": {"SourceRef": {"Entity": MED}}, "Property": prop}}


def proj(field, nome=None, ativo=None):
    ent = field[next(iter(field))]["Expression"]["SourceRef"]["Entity"]
    prop = field[next(iter(field))]["Property"]
    p = {"field": field, "queryRef": f"{ent}.{prop}", "nativeQueryRef": prop}
    if nome is not None:
        p["displayName"] = nome
    if ativo:
        p["active"] = True
    return p


def cor_campo(medida):
    return {"solid": {"color": {"expr": med(medida)}}}


def cor(hexa):
    return {"solid": {"color": lit(f"'{hexa}'")}}


def sem_fundo_borda():
    return {
        "background": [{"properties": {"show": lit("false")}}],
        "border": [{"properties": {"show": lit("false")}}],
        "title": [{"properties": {"show": lit("false")}}],
        "visualHeader": [{"properties": {"show": lit("false")}}],
    }


def container(nome, x, y, w, h, z, visual, tab=None):
    return {
        "$schema": SCHEMA,
        "name": nome,
        "position": {"x": x, "y": y, "z": z, "height": h, "width": w, "tabOrder": tab if tab is not None else z},
        "visual": visual,
    }


def textbox(nome, x, y, w, h, z, runs, align="left"):
    return container(nome, x, y, w, h, z, {
        "visualType": "textbox",
        "objects": {"general": [{"properties": {"paragraphs": [{"textRuns": runs, "horizontalTextAlignment": align}]}}]},
        "visualContainerObjects": sem_fundo_borda(),
        "drillFilterOtherVisuals": True,
    })


def card(nome, x, y, w, h, z, medida, cor_texto, tamanho, align="'left'"):
    return container(nome, x, y, w, h, z, {
        "visualType": "card",
        "query": {"queryState": {"Values": {"projections": [proj(med(medida))]}}},
        "objects": {
            "labels": [{"properties": {"color": cor(cor_texto), "fontSize": lit(f"{tamanho}D"), "fontFamily": lit("'Segoe UI'")}}],
            "categoryLabels": [{"properties": {"show": lit("false")}}],
            "wordWrap": [{"properties": {"show": lit("true")}}],
        },
        "visualContainerObjects": sem_fundo_borda(),
        "drillFilterOtherVisuals": True,
    })


def slicer(nome, x, y, w, h, z, field, titulo):
    return container(nome, x, y, w, h, z, {
        "visualType": "slicer",
        "query": {"queryState": {"Values": {"projections": [proj(field, ativo=True)]}}},
        "objects": {
            "data": [{"properties": {"mode": lit("'Dropdown'")}}],
            "header": [{"properties": {"show": lit("true"), "text": lit(f"'{titulo}'"), "fontColor": cor("#4A5A51"), "textSize": lit("9D")}}],
            "items": [{"properties": {"textSize": lit("10D")}}],
        },
        "visualContainerObjects": {
            "background": [{"properties": {"show": lit("false")}}],
            "border": [{"properties": {"show": lit("false")}}],
            "title": [{"properties": {"show": lit("false")}}],
        },
        "drillFilterOtherVisuals": True,
    })


visuais = []
# --- cabeçalho (sobre o fundo atual: logo à esquerda, faixa verde) ---
visuais.append(textbox("v01Titulo", 150, 5, 420, 40, 1000,
    [{"value": "Carteira de proposições", "textStyle": {"fontWeight": "bold", "fontFamily": "Segoe UI", "fontSize": "18pt", "color": "#FFFFFF"}}]))
visuais.append(card("v02Atualizacao", 860, 1, 400, 48, 1100, "Dados Atualizados Em", "#FFFFFF", 10))

# --- filtros numa linha ---
busca = json.loads((RAIZ / "pages/144a96dc6239db74d11a/visuals/e2af0ffe398caea31886/visual.json").read_text(encoding="utf-8"))
busca.pop("parentGroupName", None)
busca["name"] = "v03Busca"
busca["position"] = {"x": 20, "y": 76, "z": 2000, "height": 56, "width": 190, "tabOrder": 2000}
busca["visual"].setdefault("visualContainerObjects", {})["title"] = [{"properties": {"show": lit("true"), "text": lit("'Buscar proposição'"), "fontSize": lit("9D"), "fontColor": cor("#4A5A51")}}]
visuais.append(busca)
visuais.append(slicer("v04FiltroPrioridade", 222, 76, 120, 56, 2100, col(POS, "prioridade"), "Prioritária"))
visuais.append(slicer("v05FiltroPosicao", 354, 76, 170, 56, 2200, col(POS, "posicao_abcs"), "Posição ABCS"))
visuais.append(slicer("v06FiltroSituacao", 536, 76, 190, 56, 2300, col(MON, "situacao_atual"), "Situação"))
visuais.append(slicer("v07FiltroOrgao", 738, 76, 120, 56, 2400, col(MON, "orgao_atual"), "Órgão atual"))
visuais.append(slicer("v08FiltroTema", 870, 76, 190, 56, 2500, col(MON, "keywords_encontradas"), "Palavra-chave"))
visuais.append(card("v09Contagem", 1050, 84, 220, 48, 2600, "Contagem Carteira", "#14231B", 10))

# --- legenda (cor nunca sozinha) ---
def faixa(hexa, texto):
    return [{"value": "▌", "textStyle": {"fontSize": "11pt", "color": hexa}},
            {"value": f" {texto}      ", "textStyle": {"fontFamily": "Segoe UI", "fontSize": "9pt", "color": "#4A5A51"}}]
legenda = [{"value": "Legenda:  ", "textStyle": {"fontFamily": "Segoe UI", "fontSize": "9pt", "color": "#4A5A51"}}]
legenda += faixa("#D92D20", "Urgente — prioritária que se movimentou nos últimos 7 dias ou entra em pauta em até 14 dias")
legenda += faixa("#E8590C", "Prioridade — marcada como prioritária pela ABCS")
legenda += faixa("#D0D5DD", "Acompanhamento")
visuais.append(textbox("v10Legenda", 20, 134, 1020, 26, 2700, legenda))

# --- botão de detalhamento ---
botao = json.loads((RAIZ / "pages/144a96dc6239db74d11a/visuals/d0b85bb678628604ad39/visual.json").read_text(encoding="utf-8"))
botao.pop("parentGroupName", None)
botao["name"] = "v11BotaoDetalhes"
botao["position"] = {"x": 1060, "y": 132, "z": 2800, "height": 28, "width": 200, "tabOrder": 2800}
botao["visual"]["objects"]["text"] = [
    {"properties": {"show": lit("true")}},
    {"properties": {"text": lit("'Ver detalhes da selecionada'"), "fontSize": lit("10D"), "fontColor": cor("#FFFFFF")}, "selector": {"id": "default"}},
]
botao["visual"]["objects"]["fill"] = [{"properties": {"show": lit("true"), "fillColor": cor("#00533A"), "transparency": lit("0D")}, "selector": {"id": "default"}}]
botao["visual"]["visualContainerObjects"]["visualLink"][0]["properties"]["disabledTooltip"] = lit("'Clique em uma linha da tabela para ver os detalhes'")
visuais.append(botao)

# --- tabela ---
colunas = [
    (med("Nível de Atenção"), " ", 18),
    (med("Atenção Rótulo"), "Atenção", 116),
    (col(MON, "identificacao"), "Proposição", 96),
    (med("Ementa Trecho"), "Ementa (trecho)", 356),
    (col(POS, "posicao_abcs"), "Posição ABCS", 190),
    (col(MON, "orgao_atual"), "Órgão", 62),
    (col(MON, "data_ultima_movimentacao"), "Última mov.", 82),
    (med("Próxima Ação"), "Próxima ação", 200),
    (col(MON, "link_direto"), "Câmara", 56),
]
projs = [proj(f, n) for f, n, _ in colunas]
refs = [p["queryRef"] for p in projs]
todas = {"data": [{"dataViewWildcard": {"matchingOption": 1}}]}

values = [
    {"properties": {"urlIcon": lit("true"), "wordWrap": lit("true"), "fontSize": lit("10D")}},
]
for ref in refs:
    values.append({"properties": {"backColor": cor_campo("Atenção Cor Fundo")}, "selector": {**todas, "metadata": ref}})
# faixa: número do nível pintado da mesma cor do fundo da célula = só a cor aparece (serve para ordenar)
values.append({"properties": {"backColor": cor_campo("Atenção Cor"), "fontColor": cor_campo("Atenção Cor")}, "selector": {**todas, "metadata": refs[0]}})
values.append({"properties": {"fontColor": cor_campo("Atenção Cor Texto")}, "selector": {**todas, "metadata": refs[1]}})
values.append({"properties": {"fontColor": cor_campo("Próxima Ação Cor")}, "selector": {**todas, "metadata": refs[7]}})

tabela = container("v12TabelaCarteira", 20, 164, 1240, 540, 3000, {
    "visualType": "tableEx",
    "query": {
        "queryState": {"Values": {"projections": projs}},
        "sortDefinition": {"sort": [
            {"field": med("Nível de Atenção"), "direction": "Descending"},
            {"field": col(MON, "data_ultima_movimentacao"), "direction": "Descending"},
        ]},
    },
    "objects": {
        "columnHeaders": [{"properties": {"wordWrap": lit("true"), "fontSize": lit("10D"), "fontColor": cor("#14231B"), "backColor": cor("#F2F5F3")}}],
        "values": values,
        "grid": [{"properties": {"gridVertical": lit("false"), "gridHorizontal": lit("true"), "gridHorizontalColor": cor("#E3E8E5"), "rowPadding": lit("4D")}}],
        "total": [{"properties": {"totals": lit("false")}}],
        "columnWidth": [{"properties": {"value": lit(f"{w}D")}, "selector": {"metadata": ref}} for ref, (_, _, w) in zip(refs, colunas)],
    },
    "visualContainerObjects": {
        "title": [{"properties": {"show": lit("false")}}],
        "background": [{"properties": {"show": lit("true"), "color": cor("#FFFFFF"), "transparency": lit("0D")}}],
        "border": [{"properties": {"show": lit("false")}}],
    },
    "drillFilterOtherVisuals": True,
})
visuais.append(tabela)

# --- grava: move os visuais antigos para o backup e escreve os novos ---
destino_antigo = BACKUP / "carteira_visuais_antigos"
if destino_antigo.exists():
    # o original já está guardado; aqui só há visuais gerados (o cabeçalho, gerado à parte, fica)
    for d in (PAGINA / "visuals").glob("v[0-9][0-9]*"):
        shutil.rmtree(d)
else:
    shutil.move(str(PAGINA / "visuals"), str(destino_antigo))
    (PAGINA / "visuals").mkdir()
for v in visuais:
    d = PAGINA / "visuals" / v["name"]
    d.mkdir()
    (d / "visual.json").write_text(json.dumps(v, ensure_ascii=False, indent=2), encoding="utf-8")

pagina = json.loads((PAGINA / "page.json").read_text(encoding="utf-8"))
pagina["displayName"] = "Carteira"
pagina["width"], pagina["height"] = 1280, 720
(PAGINA / "page.json").write_text(json.dumps(pagina, ensure_ascii=False, indent=2), encoding="utf-8")

for f in PAGINA.rglob("*.json"):
    json.loads(f.read_text(encoding="utf-8"))
print(f"ok: {len(visuais)} visuais")
