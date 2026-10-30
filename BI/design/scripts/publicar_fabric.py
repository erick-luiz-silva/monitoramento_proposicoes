"""Publica o PBIP (modelo TMDL + relatório PBIR) num workspace do Fabric pela API (Create Item with Definition).

Uso: python publicar_fabric.py <pasta BI> <workspace_id> modelo|relatorio [<semantic_model_id>]
Não é idempotente: cria um item novo a cada chamada (confira o workspace antes).
"""
import base64, json, subprocess, sys, time, urllib.request, urllib.error
from pathlib import Path

BI, WS, ETAPA = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
NOME = "BI_Monitoramento_Proposicoes"
API = "https://api.fabric.microsoft.com/v1"
HDR_SKILL = {"x-ms-fabric-skill": "semantic-model-authoring"}


def token():
    return subprocess.check_output(["az", "account", "get-access-token", "--resource", "https://api.fabric.microsoft.com",
                                    "--query", "accessToken", "-o", "tsv"], text=True).strip()


def chamar(metodo, url, corpo=None):
    req = urllib.request.Request(url, method=metodo, data=json.dumps(corpo).encode() if corpo else None,
                                 headers={"Authorization": f"Bearer {token()}", "Content-Type": "application/json", **HDR_SKILL})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, dict(r.headers), (json.loads(r.read() or b"null"))
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode()


def parte(caminho, arquivo):
    return {"path": caminho, "payload": base64.b64encode(arquivo.read_bytes()).decode(), "payloadType": "InlineBase64"}


def partes_de(raiz, extras=()):
    out = []
    for f in sorted(raiz.rglob("*")):
        rel = f.relative_to(raiz).as_posix()
        if f.is_file() and (rel.startswith("definition/") or rel.startswith("StaticResources/") or rel in extras):
            out.append(parte(rel, f))
    return out


def criar(tipo_url, corpo):
    st, h, resp = chamar("POST", f"{API}/workspaces/{WS}/{tipo_url}", corpo)
    print("POST", st)
    if st == 202:
        op = h.get("Location") or h.get("location")
        while True:
            time.sleep(int(h.get("Retry-After", 5)))
            st2, h2, r2 = chamar("GET", op)
            estado = (r2 or {}).get("status") if isinstance(r2, dict) else r2
            print("  operação:", estado)
            if estado in ("Succeeded", "Failed"):
                if estado == "Failed":
                    print(json.dumps(r2, ensure_ascii=False)[:2000])
                    sys.exit(1)
                st3, _, r3 = chamar("GET", op + "/result")
                return r3
    if st in (200, 201):
        return resp
    print(str(resp)[:3000])
    sys.exit(1)


if ETAPA == "modelo":
    raiz = BI / f"{NOME}.SemanticModel"
    partes = [parte("definition.pbism", raiz / "definition.pbism")] + partes_de(raiz, ("diagramLayout.json",))
    print(len(partes), "partes do modelo")
    r = criar("semanticModels", {"displayName": NOME, "definition": {"format": "TMDL", "parts": partes}})
    print("MODELO", r.get("id"), r.get("displayName"))
elif ETAPA == "relatorio":
    modelo_id = sys.argv[4]
    raiz = BI / f"{NOME}.Report"
    pbir = {"version": "4.0", "datasetReference": {"byConnection": {
        "connectionString": f"Data Source=\"powerbi://api.powerbi.com/v1.0/myorg/Dados e Inteligência de Negócios - ABCS\";initial catalog={NOME};"
                            f"access mode=readonly;integrated security=ClaimsToken;semanticmodelid={modelo_id}",
        "pbiServiceModelId": None, "pbiModelVirtualServerName": "sobe_wowvirtualserver",
        "pbiModelDatabaseName": modelo_id, "name": "EntityDataSource", "connectionType": "pbiServiceXmlaStyleLive"}}}
    partes = [{"path": "definition.pbir", "payload": base64.b64encode(json.dumps(pbir).encode()).decode(), "payloadType": "InlineBase64"}]
    partes += partes_de(raiz)
    print(len(partes), "partes do relatório")
    r = criar("reports", {"displayName": NOME, "definition": {"format": "PBIR", "parts": partes}})
    print("RELATORIO", r.get("id"), r.get("displayName"))
