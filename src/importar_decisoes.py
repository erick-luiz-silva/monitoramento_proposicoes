"""Importação ensaiada das decisões da planilha para o schema gestao (PRD RN04). Só roda à mão.

Lê as abas "Proposições" (relevância por id_proposicao) e "Posicionamento ABCS" (posição, ação,
parecer, prioridade e observações por identificação), agrupa por api_cache.vw_monitoramento.chave_projeto,
consolida (relevância: SIM > NÃO > pendente) e separa os conflitos que a Ana precisa resolver na planilha.

Uso (de src/; o id da planilha vai em GOOGLE_SHEET_MONITORAMENTO_ID; DATABASE_URL aponta o banco):
    python importar_decisoes.py              # = --ensaio: só relatório (números) e data/conflitos_migracao.csv
    python importar_decisoes.py --aplicar    # grava em gestao; recusa se houver qualquer conflito aberto

O relatório no terminal só tem números. Textos da planilha só aparecem no CSV (ignorado pelo git).
A gravação é idempotente: rodar de novo sem mudança na planilha não grava nada.
"""

import argparse
import csv
import json
import os
import sys
import unicodedata
import uuid
from collections import Counter, defaultdict
from pathlib import Path

from google.auth.transport.requests import AuthorizedSession

from comparar_acompanhamento import ler_aba
from config import casa_de
from db import get_connection
from google_auth import get_credentials

SAIDA_CONFLITOS = Path(__file__).resolve().parents[1] / "data" / "conflitos_migracao.csv"
SAIDA_FORA = Path(__file__).resolve().parents[1] / "data" / "fora_do_monitoramento.csv"
ATOR_NOME = "importação da planilha"
CAMPOS = ("relevancia", "posicao", "prioridade", "acao", "parecer", "observacoes")
POSICOES = {
    "acompanhar": "Acompanhar",
    "a favor": "A favor",
    "contra": "Contra",
    "a favor com ressalvas": "A favor com ressalvas",
    "em analise": "Em análise",
}
DESCONHECIDO = "<desconhecido>"

TIPO_DIVERGENCIA = "Divergência entre as versões do mesmo projeto"
TIPO_PRIORIDADE_SEM_SIM = "Prioridade SIM sem relevância SIM"
TIPO_AMBIGUA = "Identificação ambígua entre casas no Posicionamento"
TIPO_SEM_PROPOSICAO = "Identificação do Posicionamento sem proposição monitorada"
TIPO_SEM_ID = "Linha de Proposições sem id_proposicao válido"
TIPO_ID_DIVERGE = "id_proposicao e identificação do Posicionamento apontam para projetos diferentes"
TIPO_VALOR = "Valor não reconhecido"
TIPO_PROJETOS_DIFERENTES = "Versões do projeto ligadas a projetos diferentes no banco"
TIPO_GRUPOS_DIFERENTES = "Projeto do banco separado em grupos diferentes na importação"


def _sem_acento(texto):
    base = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in base if unicodedata.category(c) != "Mn").lower().strip()


def texto_limpo(valor):
    """Texto como está (trim); vazio vira None. Quebras de linha internas são preservadas."""
    valor = (valor or "").strip()
    return valor or None


def normalizar_relevancia(valor):
    chave = _sem_acento(valor)
    if not chave:
        return None
    if chave == "sim":
        return "SIM"
    if chave == "nao":
        return "NAO"
    return DESCONHECIDO


def normalizar_prioridade(valor):
    chave = _sem_acento(valor)
    if not chave:
        return None
    if chave == "sim":
        return True
    if chave == "nao":
        return False
    return DESCONHECIDO


def normalizar_posicao(valor):
    chave = " ".join(_sem_acento(valor).split())
    if not chave:
        return None
    return POSICOES.get(chave, DESCONHECIDO)


def consolidar_relevancia(valores):
    """SIM > NÃO > pendente (None). Devolve (final, divergente), divergente = houve SIM e NÃO."""
    presentes = {v for v in valores if v in ("SIM", "NAO")}
    if "SIM" in presentes:
        return "SIM", len(presentes) > 1
    if "NAO" in presentes:
        return "NAO", False
    return None, False


def indexar_cache(linhas):
    """Índices do api_cache.vw_monitoramento: por id, por identificacao_casa e por identificacao."""
    por_id = {int(l["id_proposicao"]): l for l in linhas}
    por_casa = defaultdict(set)
    por_ident = defaultdict(set)
    for l in linhas:
        por_casa[(l["identificacao_casa"] or "").strip()].add(l["chave_projeto"])
        por_ident[(l["identificacao"] or "").strip()].add(l["chave_projeto"])
    return {"por_id": por_id, "por_casa": por_casa, "por_ident": por_ident}


def resolver_identificacao(ident, indice):
    """Regra do dim_posicionamento_abcs.tmdl: com sufixo de casa liga àquela versão; sem sufixo, só se
    levar a um único grupo. Devolve ('ok', chave) | ('ambigua', None) | ('sem_proposicao', None)."""
    ident = (ident or "").strip()
    exata = indice["por_casa"].get(ident)
    if exata and len(exata) > 1:
        return "ambigua", None
    if exata:
        return "ok", next(iter(exata))
    grupos = indice["por_ident"].get(ident, set())
    if len(grupos) == 1:
        return "ok", next(iter(grupos))
    if len(grupos) > 1:
        return "ambigua", None
    return "sem_proposicao", None


def _conflito(tipo, identificacao, casa, valores):
    return {"identificacao": identificacao, "casa": casa, "tipo": tipo, "valores": valores}


def _rotulo_grupo(versoes):
    idents = sorted({(v["identificacao"] or "").strip() for v in versoes})
    casas = sorted({"Senado" if v["casa"] == "SF" else "Câmara" for v in versoes})
    return " / ".join(idents), " + ".join(casas)


def consolidar(linhas_proposicoes, linhas_posicionamento, linhas_cache, ids_silver=frozenset()):
    """Lógica pura. Devolve (grupos, conflitos, extras). grupos: {chave: dict com a decisão desejada}.
    Linhas da planilha cujo id não está no cache (fora do monitoramento atual) não são conflito: viram um
    grupo próprio (só o id) e entram em extras["fora"] para a lista do mantenedor."""
    indice = indexar_cache(linhas_cache)
    versoes = defaultdict(list)
    for l in linhas_cache:
        versoes[l["chave_projeto"]].append(l)
    conflitos = []
    fora = []
    # chave -> campo -> lista de valores
    achados = defaultdict(lambda: defaultdict(list))
    relevancias = defaultdict(list)

    def chave_fora(id_, ident, casa):
        chave = f"id{id_}"
        if chave not in versoes:
            versoes[chave] = [{"id_proposicao": id_, "identificacao": ident, "identificacao_casa": ident,
                               "casa": "SF" if _sem_acento(casa) == "senado" else "CD",
                               "chave_projeto": chave, "acompanhada": False}]
        return chave

    def chave_do_id(id_):
        cache = indice["por_id"].get(id_)
        if cache is not None:
            return cache["chave_projeto"]
        if id_ in ids_silver:
            return chave_fora(id_, ident, "Senado" if casa_de(id_) == "SF" else "Câmara")
        return None

    for linha in linhas_proposicoes:
        bruto = (linha.get("id_proposicao") or "").strip()
        relevancia = normalizar_relevancia(linha.get("relevancia"))
        ident_linha = (linha.get("identificacao") or "").strip()
        casa_linha = (linha.get("casa") or "").strip()
        if not bruto.isdigit():
            if bruto or relevancia is not None:
                conflitos.append(_conflito(TIPO_SEM_ID, ident_linha, casa_linha,
                                           f"relevância {(linha.get('relevancia') or '').strip() or 'vazia'}"))
            continue
        id_ = int(bruto)
        cache = indice["por_id"].get(id_)
        if cache is None:
            fora.append({"identificacao": ident_linha, "casa": casa_linha,
                         "relevancia": (linha.get("relevancia") or "").strip()})
            chave = chave_fora(id_, ident_linha, casa_linha)
            rotulo_ident, rotulo_casa = ident_linha, casa_linha
        else:
            chave = cache["chave_projeto"]
            rotulo_ident, rotulo_casa = _rotulo_grupo([cache])
        if relevancia == DESCONHECIDO:
            conflitos.append(_conflito(TIPO_VALOR, rotulo_ident, rotulo_casa,
                                       f"relevância: {(linha.get('relevancia') or '').strip()}"))
            continue
        relevancias[chave].append(relevancia)

    posicionamento_validas = 0
    for linha in linhas_posicionamento:
        ident = (linha.get("identificacao") or "").strip()
        situacao, chave = resolver_identificacao(ident, indice)
        id_bruto = (linha.get("id_proposicao") or "").strip()
        if id_bruto:
            # o id é a ligação preferida; a identificação só confere
            chave_id = chave_do_id(int(id_bruto)) if id_bruto.isdigit() else None
            if chave_id is None:
                conflitos.append(_conflito(TIPO_SEM_PROPOSICAO, ident, "", "o id_proposicao informado não existe no banco"))
                continue
            candidatos = (indice["por_casa"].get(ident)
                          or indice["por_ident"].get(ident, set()))
            if candidatos and chave_id not in candidatos:
                conflitos.append(_conflito(TIPO_ID_DIVERGE, ident, "", "o id_proposicao e a identificação levam a projetos diferentes"))
                continue
            situacao, chave = "ok", chave_id
        if situacao == "ambigua":
            conflitos.append(_conflito(TIPO_AMBIGUA, ident, "Câmara + Senado",
                                       "a identificação existe em mais de um projeto; informe a casa na planilha"))
            continue
        if situacao == "sem_proposicao":
            conflitos.append(_conflito(TIPO_SEM_PROPOSICAO, ident, "", "nenhuma proposição monitorada com esta identificação"))
            continue
        posicionamento_validas += 1
        _, casa = _rotulo_grupo(versoes[chave])
        for campo, normalizar, coluna in (
            ("posicao", normalizar_posicao, "posicao_abcs"),
            ("prioridade", normalizar_prioridade, "prioridade"),
        ):
            valor = normalizar(linha.get(coluna))
            if valor == DESCONHECIDO:
                conflitos.append(_conflito(TIPO_VALOR, ident, casa, f"{campo}: {(linha.get(coluna) or '').strip()}"))
            elif valor is not None:
                achados[chave][campo].append(valor)
        for campo, coluna in (("acao", "acao"), ("parecer", "parecer_abcs"), ("observacoes", "observacoes")):
            valor = texto_limpo(linha.get(coluna))
            if valor is not None:
                achados[chave][campo].append(valor)

    grupos = {}
    for chave in sorted(set(versoes), key=str):
        ident, casa = _rotulo_grupo(versoes[chave])
        relevancia, divergente = consolidar_relevancia(relevancias.get(chave, []))
        desejado = {"relevancia": relevancia}
        for campo in ("posicao", "prioridade", "acao", "parecer", "observacoes"):
            valores = achados[chave][campo]
            distintos = list(dict.fromkeys(valores))
            if len(distintos) > 1:
                texto = " | ".join("SIM" if v is True else "NÃO" if v is False else str(v) for v in distintos)
                conflitos.append(_conflito(TIPO_DIVERGENCIA, ident, casa, f"{campo}: {texto}"))
                desejado[campo] = None
            else:
                desejado[campo] = distintos[0] if distintos else None
        if desejado["prioridade"] is True and relevancia != "SIM":
            final = {"NAO": "NÃO", None: "pendente"}[relevancia]
            conflitos.append(_conflito(TIPO_PRIORIDADE_SEM_SIM, ident, casa, f"prioridade SIM; relevância final {final}"))
            desejado["prioridade"] = None
        grupos[chave] = {
            "chave": chave,
            "ids": sorted(int(v["id_proposicao"]) for v in versoes[chave]),
            "identificacao": ident,
            "casa": casa,
            "acompanhada": any(v["acompanhada"] for v in versoes[chave]),
            "desejado": desejado,
            "relevancia_divergente": divergente,
            "tem_decisao": any(valor is not None for valor in desejado.values()),
        }
    return grupos, conflitos, {"posicionamento_ligadas": posicionamento_validas, "fora": fora}


def conflitos_de_estado(grupos, assoc):
    """Grupos cujas versões já estão ligadas a projetos diferentes no banco (não deveria ocorrer)."""
    conflitos = []
    grupos_por_uuid = defaultdict(list)
    for chave, g in grupos.items():
        uuids = {assoc[i] for i in g["ids"] if i in assoc}
        if len(uuids) > 1:
            conflitos.append(_conflito(TIPO_PROJETOS_DIFERENTES, g["identificacao"], g["casa"],
                                       "versões do grupo ligadas a mais de um projeto"))
        for uuid_projeto in uuids:
            grupos_por_uuid[uuid_projeto].append(g)
    for ligados in grupos_por_uuid.values():
        if len(ligados) > 1:
            conflitos.append(_conflito(
                TIPO_GRUPOS_DIFERENTES,
                " / ".join(g["identificacao"] for g in ligados),
                " + ".join(sorted({g["casa"] for g in ligados})),
                "o mesmo projeto está separado em grupos; mantenedor precisa reconciliar antes de importar"))
    return conflitos


def planejar_grupo(g, uuids, ids_associados, decisao, so_migracao):
    """Decide o que gravar para um grupo (pura). `uuids`: projetos já ligados às versões; `decisao`:
    dict da decisão atual ou None; `so_migracao`: a decisão atual só tem histórico da migração.
    Devolve {criar_projeto, associar, decisao: None|'inserir'|'atualizar'|'igual'|'preservada', diferencas}."""
    criar = not uuids and (g["tem_decisao"] or g["acompanhada"])
    plano = {"criar_projeto": criar, "associar": [], "decisao": None, "diferencas": {}}
    if criar or uuids:
        plano["associar"] = [i for i in g["ids"] if i not in ids_associados]
    if not g["tem_decisao"] and decisao is None:
        return plano
    desejado = g["desejado"]
    if decisao is None:
        plano["decisao"] = "inserir"
        base = {campo: None for campo in CAMPOS}
    else:
        base = {campo: decisao[campo] for campo in CAMPOS}
        if base == desejado:
            plano["decisao"] = "igual"
            return plano
        plano["decisao"] = "atualizar" if so_migracao else "preservada"
    dif = {c: {"de": base[c], "para": desejado[c]} for c in CAMPOS if base[c] != desejado[c]}
    plano["diferencas"] = dif
    if plano["decisao"] != "preservada" and g["relevancia_divergente"] and "relevancia" in dif:
        dif["consolidacao_relevancia"] = "versões com SIM e NÃO; SIM prevalece (RN04)"
    return plano


# --- Planilha e banco (I/O) -------------------------------------------------------------------

def ler_planilha():
    sheet_id = os.getenv("GOOGLE_SHEET_MONITORAMENTO_ID", "").strip()
    if not sheet_id:
        raise RuntimeError("Defina GOOGLE_SHEET_MONITORAMENTO_ID.")
    sessao = AuthorizedSession(get_credentials())
    return ler_aba(sessao, sheet_id, "Proposições"), ler_aba(sessao, sheet_id, "Posicionamento ABCS")


def ler_cache(cur):
    cur.execute(
        """
        SELECT id_proposicao, identificacao, identificacao_casa, casa, chave_projeto, acompanhada
        FROM api_cache.vw_monitoramento
        """
    )
    nomes = [d[0] for d in cur.description]
    return [dict(zip(nomes, linha)) for linha in cur.fetchall()]


def ler_ids_silver(cur):
    cur.execute("SELECT id_proposicao FROM silver.proposicao")
    return {r[0] for r in cur.fetchall()}


def ler_estado(cur):
    """Associações e decisões atuais: ({id: uuid}, {uuid: decisao}, {uuid: só_migração})."""
    cur.execute("SELECT id_proposicao, uuid_projeto FROM contrato.vw_associacao")
    assoc = {i: u for i, u in cur.fetchall()}
    cur.execute(
        """
        SELECT d.uuid_projeto, d.relevancia, d.posicao, d.prioridade, d.acao, d.parecer, d.observacoes,
               NOT EXISTS (SELECT 1 FROM gestao.historico_alteracao h
                           WHERE h.uuid_projeto = d.uuid_projeto AND h.origem <> 'migracao')
        FROM gestao.decisao_projeto d
        """
    )
    decisoes, so_migracao = {}, {}
    for u, *campos, so in cur.fetchall():
        decisoes[u] = dict(zip(CAMPOS, campos))
        so_migracao[u] = so
    return assoc, decisoes, so_migracao


def _estado_do_grupo(g, assoc, decisoes, so_migracao):
    uuids = {assoc[i] for i in g["ids"] if i in assoc}
    unico = next(iter(uuids)) if len(uuids) == 1 else None
    return uuids, {i for i in g["ids"] if i in assoc}, decisoes.get(unico), so_migracao.get(unico, False), unico


def planejar_tudo(grupos, assoc, decisoes, so_migracao):
    return {chave: planejar_grupo(g, *_estado_do_grupo(g, assoc, decisoes, so_migracao)[:4]) for chave, g in grupos.items()}


def aplicar_grupo(cur, g):
    """Grava um grupo sob a trava do grupo (mesma convenção de gestao.gravar_decisao)."""
    cur.execute("SELECT pg_advisory_xact_lock(hashtextextended('gestao.grupo:' || %s::text, 0))", (g["chave"],))
    assoc, decisoes, so_migracao = ler_estado_grupo(cur, g["ids"])
    uuids, ids_assoc, decisao, so_mig, unico = _estado_do_grupo(g, assoc, decisoes, so_migracao)
    if len(uuids) > 1:
        raise RuntimeError("versões do grupo ligadas a projetos diferentes; resolva antes de importar")
    if unico is not None:
        cur.execute("SELECT pg_advisory_xact_lock(hashtextextended('gestao.projeto:' || %s::text, 0))", (str(unico),))
        # Uma edição por UUID pode terminar enquanto esperamos a trava. A decisão e a
        # origem do histórico precisam ser relidas antes de decidir o que sobrescrever.
        assoc, decisoes, so_migracao = ler_estado_grupo(cur, g["ids"])
        estado = _estado_do_grupo(g, assoc, decisoes, so_migracao)
        if estado[4] != unico or len(estado[0]) != 1:
            raise RuntimeError("associação do projeto mudou durante a importação; repita o ensaio")
        uuids, ids_assoc, decisao, so_mig, unico = estado
    plano = planejar_grupo(g, uuids, ids_assoc, decisao, so_mig)
    resultado = Counter()
    if plano["criar_projeto"]:
        unico = uuid.uuid4()
        cur.execute("INSERT INTO gestao.projeto (uuid) VALUES (%s)", (str(unico),))
        resultado["projetos_criados"] += 1
        if not g["tem_decisao"]:
            cur.execute(
                "INSERT INTO gestao.historico_alteracao (uuid_projeto, operacao, diferencas, origem, ator_nome) "
                "VALUES (%s, 'projeto_criado', %s, 'migracao', %s)",
                (str(unico), json.dumps({"acompanhada": True}), ATOR_NOME),
            )
    if unico is not None:
        cur.execute("SELECT pg_advisory_xact_lock(hashtextextended('gestao.projeto:' || %s::text, 0))", (str(unico),))
    for id_proposicao in plano["associar"]:
        cur.execute(
            "INSERT INTO gestao.projeto_proposicao (id_proposicao, uuid_projeto, origem) VALUES (%s, %s, 'migracao') "
            "ON CONFLICT (id_proposicao) DO NOTHING",
            (id_proposicao, str(unico)),
        )
        resultado["associacoes"] += 1
    d = g["desejado"]
    if plano["decisao"] in ("inserir", "atualizar"):
        revisao = 1 if plano["decisao"] == "inserir" else None
        if revisao is None:
            cur.execute("SELECT revisao FROM gestao.decisao_projeto WHERE uuid_projeto = %s FOR UPDATE", (str(unico),))
            revisao = cur.fetchone()[0] + 1
        cur.execute(
            """
            INSERT INTO gestao.decisao_projeto (uuid_projeto, relevancia, posicao, prioridade, acao, parecer,
                observacoes, revisao, prioridade_desde, atualizado_em, atualizado_por_nome)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                    CASE WHEN %s THEN now() END, now(), %s)
            ON CONFLICT (uuid_projeto) DO UPDATE SET
                relevancia = EXCLUDED.relevancia, posicao = EXCLUDED.posicao, prioridade = EXCLUDED.prioridade,
                acao = EXCLUDED.acao, parecer = EXCLUDED.parecer, observacoes = EXCLUDED.observacoes,
                revisao = EXCLUDED.revisao,
                prioridade_desde = CASE
                    WHEN EXCLUDED.prioridade IS NOT TRUE THEN NULL
                    WHEN gestao.decisao_projeto.prioridade IS TRUE THEN gestao.decisao_projeto.prioridade_desde
                    ELSE EXCLUDED.prioridade_desde END,
                atualizado_em = EXCLUDED.atualizado_em, atualizado_por_nome = EXCLUDED.atualizado_por_nome
            """,
            (str(unico), d["relevancia"], d["posicao"], d["prioridade"], d["acao"], d["parecer"],
             d["observacoes"], revisao, d["prioridade"] is True, ATOR_NOME),
        )
        cur.execute(
            "INSERT INTO gestao.historico_alteracao (uuid_projeto, operacao, diferencas, origem, ator_nome, revisao) "
            "VALUES (%s, 'importacao_planilha', %s, 'migracao', %s, %s)",
            (str(unico), json.dumps(plano["diferencas"]), ATOR_NOME, revisao),
        )
        resultado["decisoes_gravadas"] += 1
    elif plano["decisao"] == "preservada":
        resultado["decisoes_preservadas"] += 1
    return resultado


def ler_estado_grupo(cur, ids):
    cur.execute("SELECT id_proposicao, uuid_projeto FROM contrato.vw_associacao WHERE id_proposicao = ANY(%s)", (ids,))
    assoc = {i: u for i, u in cur.fetchall()}
    decisoes, so_migracao = {}, {}
    if assoc:
        cur.execute(
            """
            SELECT d.uuid_projeto, d.relevancia, d.posicao, d.prioridade, d.acao, d.parecer, d.observacoes,
                   NOT EXISTS (SELECT 1 FROM gestao.historico_alteracao h
                               WHERE h.uuid_projeto = d.uuid_projeto AND h.origem <> 'migracao')
            FROM gestao.decisao_projeto d WHERE d.uuid_projeto = ANY(%s::uuid[])
            """,
            ([str(u) for u in set(assoc.values())],),
        )
        for u, *campos, so in cur.fetchall():
            decisoes[u] = dict(zip(CAMPOS, campos))
            so_migracao[u] = so
    return assoc, decisoes, so_migracao


# --- Relatório ---------------------------------------------------------------------------------

def totais_planilha(linhas_proposicoes, linhas_posicionamento):
    rel = Counter(
        {"SIM": "SIM", "NAO": "NÃO", None: "vazio"}.get(normalizar_relevancia(l.get("relevancia")), "outro")
        for l in linhas_proposicoes
    )
    pri = Counter(
        {True: "SIM", False: "NÃO", None: "vazio"}.get(normalizar_prioridade(l.get("prioridade")), "outro")
        for l in linhas_posicionamento
    )
    preenchidos = lambda col: sum(1 for l in linhas_posicionamento if texto_limpo(l.get(col)))
    return {
        "proposicoes_linhas": len(linhas_proposicoes),
        "relevancia": dict(rel),
        "acompanhadas": sum(1 for l in linhas_proposicoes if _sem_acento(l.get("acompanhada")) == "sim"),
        "posicionamento_linhas": len(linhas_posicionamento),
        "posicao": preenchidos("posicao_abcs"),
        "acao": preenchidos("acao"),
        "parecer": preenchidos("parecer_abcs"),
        "observacoes": preenchidos("observacoes"),
        "prioridade": dict(pri),
    }


def totais_grupos(grupos):
    rel = Counter({"SIM": "SIM", "NAO": "NÃO", None: "pendente"}[g["desejado"]["relevancia"]] for g in grupos.values())
    pri = Counter({True: "SIM", False: "NÃO", None: "vazio"}[g["desejado"]["prioridade"]] for g in grupos.values())
    return {
        "grupos": len(grupos),
        "relevancia": dict(rel),
        "relevancia_consolidada_com_divergencia": sum(1 for g in grupos.values() if g["relevancia_divergente"]),
        "acompanhados": sum(1 for g in grupos.values() if g["acompanhada"]),
        "posicao": sum(1 for g in grupos.values() if g["desejado"]["posicao"]),
        "acao": sum(1 for g in grupos.values() if g["desejado"]["acao"]),
        "parecer": sum(1 for g in grupos.values() if g["desejado"]["parecer"]),
        "observacoes": sum(1 for g in grupos.values() if g["desejado"]["observacoes"]),
        "prioridade": dict(pri),
    }


def totais_plano(plano):
    c = Counter()
    for p in plano.values():
        c["projetos_a_criar"] += p["criar_projeto"]
        c["associacoes_a_criar"] += len(p["associar"])
        if p["decisao"]:
            c[f"decisoes_{p['decisao']}"] += 1
    return dict(c)


def gravar_csv(conflitos, caminho=SAIDA_CONFLITOS):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["identificacao", "casa", "tipo_do_conflito", "valores_encontrados"])
        for c in sorted(conflitos, key=lambda c: (c["tipo"], c["identificacao"])):
            w.writerow([c["identificacao"], c["casa"], c["tipo"], c["valores"]])


def gravar_fora(fora, caminho=SAIDA_FORA):
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["identificacao", "casa", "relevancia"])
        for l in sorted(fora, key=lambda l: l["identificacao"]):
            w.writerow([l["identificacao"], l["casa"], l["relevancia"]])


def imprimir(titulo, dados):
    print(f"{titulo}:")
    for chave, valor in dados.items():
        print(f"  {chave}: {valor}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument("--ensaio", action="store_true", help="só relatório (padrão)")
    grupo.add_argument("--aplicar", action="store_true", help="grava em gestao; recusa com conflito aberto")
    args = parser.parse_args()

    proposicoes, posicionamento = ler_planilha()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cache = ler_cache(cur)
            ids_silver = ler_ids_silver(cur)
            assoc, decisoes, so_migracao = ler_estado(cur)
        conn.rollback()  # leitura: não deixa transação aberta durante o resto
        grupos, conflitos, extras = consolidar(proposicoes, posicionamento, cache, ids_silver)
        conflitos += conflitos_de_estado(grupos, assoc)
        plano = planejar_tudo(grupos, assoc, decisoes, so_migracao)

        imprimir("Planilha (linhas lidas)", totais_planilha(proposicoes, posicionamento))
        imprimir("Projetos consolidados (por grupo)", totais_grupos(grupos))
        imprimir("O que seria gravado", totais_plano(plano))
        por_tipo = Counter(c["tipo"] for c in conflitos)
        imprimir(f"Conflitos ({len(conflitos)})", dict(por_tipo))
        gravar_csv(conflitos)
        gravar_fora(extras["fora"])
        print(f"Fora do monitoramento (importadas, lista do mantenedor): {len(extras['fora'])}")
        print(f"Lista para a Ana: {SAIDA_CONFLITOS.relative_to(SAIDA_CONFLITOS.parents[1])}")

        if not args.aplicar:
            print("Ensaio: nada foi gravado.")
            return 0
        if conflitos:
            print("RECUSADO: há conflitos em aberto; resolva na planilha e rode de novo. Nada foi gravado.")
            return 2
        resultado = Counter()
        try:
            with conn.cursor() as cur:
                for chave in sorted(grupos, key=str):
                    previsto = plano[chave]
                    # O ensaio já leu o estado inteiro. Nada mudou: não abrir centenas
                    # de consultas/travas no pooler só para repetir a comparação.
                    # Uma edição posterior a essa leitura também fica preservada.
                    if (not previsto["criar_projeto"] and not previsto["associar"]
                            and previsto["decisao"] in (None, "igual", "preservada")):
                        if previsto["decisao"] == "preservada":
                            resultado["decisoes_preservadas"] += 1
                        continue
                    resultado.update(aplicar_grupo(cur, grupos[chave]))
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        imprimir("Gravado", dict(resultado) or {"nada_a_gravar": 0})
    return 0


if __name__ == "__main__":
    sys.exit(main())
