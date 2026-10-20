"""Ajuste pontual (20/10/2026): lateral colorida nos cartões de Pautas, Audiências e Autores (mesmo recurso
que o usuário aplicou no Início) e reorganização da parte de cima de Pautas. Só toca nos visuais listados."""
import copy, json, shutil, sys
from pathlib import Path

PG = Path(sys.argv[1]) / "BI_Monitoramento_Proposicoes.Report" / "definition" / "pages"
GUARDA = Path(sys.argv[2])
INICIO, CARTEIRA, PAUTAS, AUDIENCIAS, AUTORES = "144a96dc6239db74d11a", "2f1b62b82156458deeae", "a0b7e00206a8b0176a8a", "0fb3418f7d50e4d08b27", "0e004dfd0732f57f2943"
PAU = "gold vw_pautas_monitoradas"


def ler(pid, nome):
    return json.loads((PG / pid / "visuals" / nome / "visual.json").read_text(encoding="utf-8"))


def gravar(pid, v):
    d = PG / pid / "visuals" / v["name"]
    d.mkdir(exist_ok=True)
    (d / "visual.json").write_text(json.dumps(v, ensure_ascii=False, indent=2), encoding="utf-8")


def lit(v):
    return {"expr": {"Literal": {"Value": v}}}


# --- estilo dos cartões, copiado do Início do usuário ---
modelo = ler(INICIO, "v01Indicadores")["visual"]["objects"]


def com_lateral(pid, cores):
    v = ler(pid, "v01Indicadores")
    obj = v["visual"].setdefault("objects", {})
    obj["border"] = copy.deepcopy(modelo["border"])
    obj["shapeCustomRectangle"] = copy.deepcopy(modelo["shapeCustomRectangle"])
    obj["outline"] = [{"properties": {"weight": lit("1D")}, "selector": {"id": "default"}}]
    obj["accentBar"] = [{"properties": {"show": lit("true")}, "selector": {"id": "default"}}] + [
        {"properties": {"width": lit("5D"), "color": {"solid": {"color": lit(f"'{cor}'")}}}, "selector": {"metadata": f"Medidas.{m}"}}
        for m, cor in cores]
    gravar(pid, v)


com_lateral(PAUTAS, [("Pautas Agendadas", "#00533A"), ("Total Eventos com Pauta", "#C9D1CC"),
                     ("Pautas Votadas", "#09814A"), ("Pautas Canceladas", "#C9D1CC")])
com_lateral(AUDIENCIAS, [("Audiências Agendadas", "#00533A"), ("Total Audiências de Interesse", "#C9D1CC")])
com_lateral(AUTORES, [("Total Autores Distintos", "#00533A"), ("Total Partidos Distintos", "#00533A"),
                      ("Total UFs Distintas", "#00533A"), ("Origem Senado", "#C9D1CC")])

# --- Pautas: cartões na largura toda, filtros numa linha, tabela abaixo; sai o "Período" ---
v = ler(PAUTAS, "v01Indicadores")
v["position"].update({"x": 30, "y": 90, "width": 1860, "height": 120})
gravar(PAUTAS, v)

periodo = PG / PAUTAS / "visuals" / "v02Periodo"
if periodo.exists():
    destino = GUARDA / "pautas_v02Periodo"
    if destino.exists():
        shutil.rmtree(destino)
    shutil.move(str(periodo), str(destino))


def slicer_de(base, nome, x, w, prop, titulo):
    s = copy.deepcopy(base)
    s["name"] = nome
    s["position"].update({"x": x, "y": 220, "width": w, "height": 80})
    pr = s["visual"]["query"]["queryState"]["Values"]["projections"][0]
    pr["field"]["Column"]["Property"] = prop
    pr["queryRef"], pr["nativeQueryRef"] = f"{PAU}.{prop}", prop
    cab = s["visual"].setdefault("objects", {}).setdefault("header", [{"properties": {}}])
    cab[0]["properties"]["text"] = lit(f"'{titulo}'")
    cab[0]["properties"]["show"] = lit("true")
    s.pop("filterConfig", None)
    return s


comissao = ler(PAUTAS, "v03Comissao")
comissao["position"].update({"x": 345, "y": 220, "width": 260, "height": 80})
gravar(PAUTAS, comissao)
gravar(PAUTAS, slicer_de(comissao, "v05Situacao", 620, 260, "status_alerta", "Situação"))
gravar(PAUTAS, slicer_de(comissao, "v06Relator", 895, 320, "nome_relator", "Relator"))

busca = ler(CARTEIRA, "v03Busca")
busca["name"] = "v02Busca"
busca.pop("filterConfig", None)
busca.pop("parentGroupName", None)
busca["position"].update({"x": 30, "y": 220, "width": 300, "height": 80})
pr = busca["visual"]["query"]["queryState"]["Values"]["projections"][0]
pr["field"]["Column"]["Expression"]["SourceRef"]["Entity"] = PAU
pr["queryRef"] = f"{PAU}.identificacao"
gravar(PAUTAS, busca)

tabela = ler(PAUTAS, "v04Pautas")
tabela["position"].update({"x": 30, "y": 315, "width": 1860, "height": 740})
gravar(PAUTAS, tabela)

for f in PG.rglob("*.json"):
    json.loads(f.read_text(encoding="utf-8"))
print("ok")
