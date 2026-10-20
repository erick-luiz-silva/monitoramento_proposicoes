"""Cabeçalho montado no Power BI (barra verde + logo branca), agrupado e igual em todas as páginas.
Substitui a imagem de fundo "ABCS Data Insights" (header degradê + rodapé com redes sociais)."""
import json, shutil, sys
from pathlib import Path

REPORT = Path(sys.argv[1])  # .../BI_Monitoramento_Proposicoes.Report
LOGO = Path(sys.argv[2])
DEF = REPORT / "definition"
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.12.0/schema.json"
LOGO_ITEM = "abcs_logo_branca.png"
VERDE = "#00533A"


def lit(v):
    return {"expr": {"Literal": {"Value": v}}}


# registra a logo
shutil.copy(LOGO, REPORT / "StaticResources" / "RegisteredResources" / LOGO_ITEM)
rep = json.loads((DEF / "report.json").read_text(encoding="utf-8"))
reg = next(p for p in rep["resourcePackages"] if p["name"] == "RegisteredResources")
if not any(i["name"] == LOGO_ITEM for i in reg["items"]):
    reg["items"].append({"name": LOGO_ITEM, "path": LOGO_ITEM, "type": "Image"})
(DEF / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")

ordem = json.loads((DEF / "pages" / "pages.json").read_text(encoding="utf-8"))["pageOrder"]
for pid in ordem:
    pdir = DEF / "pages" / pid
    page = json.loads((pdir / "page.json").read_text(encoding="utf-8"))
    s = page["width"] / 1280
    alt = round(50 * s)

    # sem imagem de fundo: a página usa o fundo do tema
    page.get("objects", {}).pop("background", None)
    if not page.get("objects"):
        page.pop("objects", None)
    (pdir / "page.json").write_text(json.dumps(page, ensure_ascii=False, indent=2), encoding="utf-8")

    grupo = {
        "$schema": SCHEMA,
        "name": "cabecalhoGrupo",
        "position": {"x": 0, "y": 0, "z": 0, "height": alt, "width": page["width"], "tabOrder": 0},
        "visualGroup": {"displayName": "Cabeçalho", "groupMode": "ScaleMode"},
    }
    barra = {
        "$schema": SCHEMA,
        "name": "cabecalhoBarra",
        "position": {"x": 0, "y": 0, "z": 0, "height": alt, "width": page["width"], "tabOrder": 0},
        "visual": {
            "visualType": "textbox",
            "objects": {"general": [{"properties": {"paragraphs": [{"textRuns": [{"value": ""}]}]}}]},
            "visualContainerObjects": {
                "background": [{"properties": {"show": lit("true"), "color": {"solid": {"color": lit(f"'{VERDE}'")}}, "transparency": lit("0D")}}],
                "border": [{"properties": {"show": lit("false")}}],
                "dropShadow": [{"properties": {"show": lit("false")}}],
                "visualHeader": [{"properties": {"show": lit("false")}}],
            },
            "drillFilterOtherVisuals": True,
        },
        "parentGroupName": "cabecalhoGrupo",
    }
    logo = {
        "$schema": SCHEMA,
        "name": "cabecalhoLogo",
        "position": {"x": round(16 * s), "y": round(8 * s), "z": 1, "height": round(34 * s), "width": round(130 * s), "tabOrder": 1},
        "visual": {
            "visualType": "image",
            "objects": {"image": [{"properties": {"sourceFile": {"image": {
                "name": lit("'ABCS'"),
                "url": {"expr": {"ResourcePackageItem": {"PackageName": "RegisteredResources", "PackageType": 1, "ItemName": LOGO_ITEM}}},
                "scaling": lit("'Fit'"),
            }}}}]},
            "visualContainerObjects": {
                "background": [{"properties": {"show": lit("false")}}],
                "border": [{"properties": {"show": lit("false")}}],
                "visualHeader": [{"properties": {"show": lit("false")}}],
                "general": [{"properties": {"altText": lit("'Logo da ABCS'")}}],
            },
            "drillFilterOtherVisuals": True,
        },
        "parentGroupName": "cabecalhoGrupo",
    }
    for v in (grupo, barra, logo):
        d = pdir / "visuals" / v["name"]
        d.mkdir(exist_ok=True)
        (d / "visual.json").write_text(json.dumps(v, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{page['displayName']}: {page['width']}x{page['height']}, cabeçalho {alt}px")
