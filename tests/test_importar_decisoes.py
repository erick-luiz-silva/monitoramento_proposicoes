"""Lógica pura da importação de decisões da planilha, com linhas sintéticas (sem API, planilha ou banco)."""

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import importar_decisoes as imp
import test_sql_local


def versao(id_, ident, chave, casa="CD", acompanhada=False):
    sufixo = " (Senado)" if casa == "SF" else " (Câmara)"
    return {"id_proposicao": id_, "identificacao": ident, "identificacao_casa": ident + sufixo,
            "casa": casa, "chave_projeto": chave, "acompanhada": acompanhada}


def prop(id_, relevancia, ident="X 1/2020", casa="Câmara"):
    return {"id_proposicao": str(id_), "identificacao": ident, "relevancia": relevancia, "casa": casa}


def pos(ident, posicao="", acao="", parecer="", prioridade="", obs=""):
    return {"identificacao": ident, "posicao_abcs": posicao, "acao": acao, "parecer_abcs": parecer,
            "prioridade": prioridade, "observacoes": obs}


CACHE = [
    versao(1, "PL 1/2020", 1),
    versao(2, "PL 1/2020", 1, "SF"),       # mesmo projeto nas duas casas
    versao(3, "PL 3/2021", 3, acompanhada=True),
    versao(4, "PL 9/2022", 4),
    versao(5, "PL 9/2022", 5, "SF"),       # mesma identificação, projetos diferentes
]


class NormalizacaoTests(unittest.TestCase):
    def test_posicao_ignora_caixa_e_acento(self):
        self.assertEqual(imp.normalizar_posicao(" EM ANALISE "), "Em análise")
        self.assertEqual(imp.normalizar_posicao("a favor com  ressalvas"), "A favor com ressalvas")
        self.assertIsNone(imp.normalizar_posicao("  "))
        self.assertEqual(imp.normalizar_posicao("talvez"), imp.DESCONHECIDO)

    def test_prioridade_e_relevancia(self):
        self.assertIs(imp.normalizar_prioridade("sim"), True)
        self.assertIs(imp.normalizar_prioridade("Não"), False)
        self.assertIs(imp.normalizar_prioridade("NAO"), False)
        self.assertIsNone(imp.normalizar_prioridade(""))
        self.assertEqual(imp.normalizar_prioridade("x"), imp.DESCONHECIDO)
        self.assertEqual(imp.normalizar_relevancia("NÃO"), "NAO")
        self.assertIsNone(imp.normalizar_relevancia(""))

    def test_consolidacao_sim_prevalece(self):
        self.assertEqual(imp.consolidar_relevancia(["NAO", "SIM", None]), ("SIM", True))
        self.assertEqual(imp.consolidar_relevancia(["NAO", None]), ("NAO", False))
        self.assertEqual(imp.consolidar_relevancia([None]), (None, False))
        self.assertEqual(imp.consolidar_relevancia(["SIM", "SIM"]), ("SIM", False))


class ResolucaoTests(unittest.TestCase):
    def setUp(self):
        self.indice = imp.indexar_cache(CACHE)

    def test_sem_sufixo_unico_grupo_liga(self):
        self.assertEqual(imp.resolver_identificacao("PL 1/2020", self.indice), ("ok", 1))

    def test_com_sufixo_de_casa_liga_a_versao(self):
        self.assertEqual(imp.resolver_identificacao("PL 9/2022 (Senado)", self.indice), ("ok", 5))

    def test_ambigua_entre_casas(self):
        self.assertEqual(imp.resolver_identificacao("PL 9/2022", self.indice)[0], "ambigua")

    def test_sem_proposicao(self):
        self.assertEqual(imp.resolver_identificacao("PL 77/2000", self.indice)[0], "sem_proposicao")


class ConsolidarTests(unittest.TestCase):
    def tipos(self, conflitos):
        return sorted(c["tipo"] for c in conflitos)

    def test_grupo_com_duas_versoes_consolida_relevancia_sem_conflito(self):
        grupos, conflitos, _ = imp.consolidar([prop(1, "NÃO"), prop(2, "SIM")], [pos("PL 1/2020", "Contra", prioridade="sim")], CACHE)
        g = grupos[1]
        self.assertEqual(g["ids"], [1, 2])
        self.assertEqual(g["desejado"]["relevancia"], "SIM")
        self.assertTrue(g["relevancia_divergente"])
        self.assertIs(g["desejado"]["prioridade"], True)
        self.assertEqual(conflitos, [])

    def test_divergencia_de_texto_entre_versoes_vira_conflito(self):
        pos_linhas = [pos("PL 1/2020 (Câmara)", acao="A"), pos("PL 1/2020 (Senado)", acao="B", parecer="p")]
        grupos, conflitos, _ = imp.consolidar([prop(1, "SIM")], pos_linhas, CACHE)
        self.assertEqual(self.tipos(conflitos), [imp.TIPO_DIVERGENCIA])
        self.assertIn("acao: A | B", conflitos[0]["valores"])
        self.assertEqual(conflitos[0]["casa"], "Câmara + Senado")
        self.assertIsNone(grupos[1]["desejado"]["acao"])
        self.assertEqual(grupos[1]["desejado"]["parecer"], "p")   # vazio numa versão não diverge

    def test_divergencia_de_posicao_e_prioridade(self):
        pos_linhas = [pos("PL 1/2020 (Câmara)", "Contra", prioridade="sim"), pos("PL 1/2020 (Senado)", "A favor", prioridade="não")]
        _, conflitos, _ = imp.consolidar([prop(1, "SIM")], pos_linhas, CACHE)
        self.assertEqual(self.tipos(conflitos), [imp.TIPO_DIVERGENCIA, imp.TIPO_DIVERGENCIA])

    def test_prioridade_sim_com_relevancia_nao(self):
        grupos, conflitos, _ = imp.consolidar([prop(3, "NÃO")], [pos("PL 3/2021", prioridade="sim")], CACHE)
        self.assertEqual(self.tipos(conflitos), [imp.TIPO_PRIORIDADE_SEM_SIM])
        self.assertIn("NÃO", conflitos[0]["valores"])

    def test_prioridade_sim_com_relevancia_pendente_tambem_e_conflito(self):
        _, conflitos, _ = imp.consolidar([], [pos("PL 3/2021", prioridade="sim")], CACHE)
        self.assertEqual(self.tipos(conflitos), [imp.TIPO_PRIORIDADE_SEM_SIM])

    def test_identificacao_ambigua_e_sem_proposicao(self):
        _, conflitos, _ = imp.consolidar([], [pos("PL 9/2022", "Contra"), pos("PL 77/2000")], CACHE)
        self.assertEqual(self.tipos(conflitos), [imp.TIPO_AMBIGUA, imp.TIPO_SEM_PROPOSICAO])

    def test_linha_de_proposicoes_fora_do_cache_nao_e_conflito_e_vira_grupo_proprio(self):
        grupos, conflitos, extras = imp.consolidar([prop(999, "SIM", "PL 5/2019")], [], CACHE)
        self.assertEqual(conflitos, [])
        self.assertEqual(extras["fora"], [{"identificacao": "PL 5/2019", "casa": "Câmara", "relevancia": "SIM"}])
        g = grupos["id999"]
        self.assertEqual((g["ids"], g["desejado"]["relevancia"], g["acompanhada"]), ([999], "SIM", False))

    def test_linha_de_proposicoes_sem_id_com_relevancia_e_conflito(self):
        _, conflitos, _ = imp.consolidar([prop("", "SIM", "PL 5/2019")], [], CACHE)
        self.assertEqual(self.tipos(conflitos), [imp.TIPO_SEM_ID])

    def test_posicionamento_por_id_tem_prioridade_sobre_identificacao_ambigua(self):
        l = pos("PL 9/2022", "Contra")
        l["id_proposicao"] = "5"
        grupos, conflitos, _ = imp.consolidar([], [l], CACHE)
        self.assertEqual(conflitos, [])
        self.assertEqual(grupos[5]["desejado"]["posicao"], "Contra")

    def test_id_de_terceiro_projeto_nao_desambigua_identificacao(self):
        linha = pos("PL 9/2022", "Contra")
        linha["id_proposicao"] = "1"
        _, conflitos, _ = imp.consolidar([], [linha], CACHE)
        self.assertEqual(self.tipos(conflitos), [imp.TIPO_ID_DIVERGE])

    def test_posicionamento_id_que_discorda_da_identificacao_e_conflito(self):
        l = pos("PL 3/2021", "Contra")
        l["id_proposicao"] = "4"
        _, conflitos, _ = imp.consolidar([], [l], CACHE)
        self.assertEqual(self.tipos(conflitos), [imp.TIPO_ID_DIVERGE])

    def test_posicionamento_id_inexistente_e_conflito_e_id_so_no_silver_vale(self):
        l = pos("PL 5/2019", "Contra")
        l["id_proposicao"] = "999"
        _, conflitos, _ = imp.consolidar([], [l], CACHE)
        self.assertEqual(self.tipos(conflitos), [imp.TIPO_SEM_PROPOSICAO])
        grupos, conflitos, _ = imp.consolidar([], [l], CACHE, {999})
        self.assertEqual(conflitos, [])
        self.assertEqual(grupos["id999"]["desejado"]["posicao"], "Contra")

    def test_identificacao_casa_em_mais_de_um_grupo_e_ambigua(self):
        cache = CACHE + [versao(6, "PL 1/2020", 6)]   # mesma identificacao_casa do id 1, outro grupo
        self.assertEqual(imp.resolver_identificacao("PL 1/2020 (Câmara)", imp.indexar_cache(cache))[0], "ambigua")

    def test_linha_vazia_fora_do_cache_nao_gera_conflito(self):
        _, conflitos, _ = imp.consolidar([prop("", "")], [], CACHE)
        self.assertEqual(conflitos, [])

    def test_valor_desconhecido_e_conflito(self):
        _, conflitos, _ = imp.consolidar([prop(4, "TALVEZ")], [pos("PL 3/2021", posicao="x", prioridade="y")], CACHE)
        self.assertEqual(self.tipos(conflitos), [imp.TIPO_VALOR] * 3)

    def test_vazios_e_textos_preservados(self):
        grupos, conflitos, _ = imp.consolidar([prop(3, "")], [pos("PL 3/2021", acao="  fazer  \n  isso ", obs="")], CACHE)
        d = grupos[3]["desejado"]
        self.assertEqual(d["acao"], "fazer  \n  isso")
        self.assertIsNone(d["observacoes"])
        self.assertIsNone(d["prioridade"])      # vazio não vira false
        self.assertEqual(conflitos, [])

    def test_grupo_acompanhado_sem_decisao(self):
        grupos, _, _ = imp.consolidar([], [], CACHE)
        self.assertTrue(grupos[3]["acompanhada"])
        self.assertFalse(grupos[3]["tem_decisao"])


class PlanejarTests(unittest.TestCase):
    def grupo(self, **desejado):
        d = {c: None for c in imp.CAMPOS}
        d.update(desejado)
        return {"chave": 1, "ids": [1, 2], "identificacao": "PL 1/2020", "casa": "Câmara",
                "acompanhada": False, "desejado": d, "relevancia_divergente": False,
                "tem_decisao": any(v is not None for v in d.values())}

    def test_grupo_novo_com_decisao_cria_projeto_e_associa_todas_as_versoes(self):
        p = imp.planejar_grupo(self.grupo(relevancia="SIM", prioridade=True), set(), set(), None, False)
        self.assertTrue(p["criar_projeto"])
        self.assertEqual(p["associar"], [1, 2])
        self.assertEqual(p["decisao"], "inserir")
        self.assertEqual(p["diferencas"]["relevancia"], {"de": None, "para": "SIM"})

    def test_grupo_sem_decisao_e_sem_acompanhamento_nao_cria_nada(self):
        p = imp.planejar_grupo(self.grupo(), set(), set(), None, False)
        self.assertEqual((p["criar_projeto"], p["associar"], p["decisao"]), (False, [], None))

    def test_acompanhado_sem_decisao_cria_so_o_projeto(self):
        g = self.grupo()
        g["acompanhada"] = True
        p = imp.planejar_grupo(g, set(), set(), None, False)
        self.assertTrue(p["criar_projeto"])
        self.assertIsNone(p["decisao"])

    def test_idempotente_quando_nada_mudou(self):
        g = self.grupo(relevancia="NAO", acao="a")
        atual = {c: None for c in imp.CAMPOS}
        atual.update(relevancia="NAO", acao="a")
        p = imp.planejar_grupo(g, {"u"}, {1, 2}, atual, True)
        self.assertEqual((p["criar_projeto"], p["associar"], p["decisao"], p["diferencas"]), (False, [], "igual", {}))

    def test_versao_nova_no_grupo_so_associa(self):
        g = self.grupo(relevancia="NAO")
        atual = {c: None for c in imp.CAMPOS}
        atual["relevancia"] = "NAO"
        p = imp.planejar_grupo(g, {"u"}, {1}, atual, True)
        self.assertEqual((p["associar"], p["decisao"]), ([2], "igual"))

    def test_mudanca_na_planilha_atualiza_se_so_migracao_senao_preserva(self):
        g = self.grupo(relevancia="SIM")
        atual = {c: None for c in imp.CAMPOS}
        atual["relevancia"] = "NAO"
        self.assertEqual(imp.planejar_grupo(g, {"u"}, {1, 2}, atual, True)["decisao"], "atualizar")
        preservada = imp.planejar_grupo(g, {"u"}, {1, 2}, atual, False)
        self.assertEqual(preservada["decisao"], "preservada")

    def test_todos_os_campos_esvaziados_atualizam_migracao_e_preservam_edicao(self):
        atual = {c: None for c in imp.CAMPOS}
        atual["acao"] = "ação anterior"
        for so_migracao, esperado in ((True, "atualizar"), (False, "preservada")):
            p = imp.planejar_grupo(self.grupo(), {"u"}, {1, 2}, atual, so_migracao)
            self.assertEqual(p["decisao"], esperado)
            self.assertEqual(p["diferencas"]["acao"], {"de": "ação anterior", "para": None})

    def test_historico_registra_consolidacao_com_divergencia(self):
        g = self.grupo(relevancia="SIM")
        g["relevancia_divergente"] = True
        p = imp.planejar_grupo(g, set(), set(), None, False)
        self.assertIn("consolidacao_relevancia", p["diferencas"])

    def test_conflito_de_projetos_diferentes_no_banco(self):
        grupos, _, _ = imp.consolidar([], [], CACHE)
        c = imp.conflitos_de_estado(grupos, {1: "u1", 2: "u2", 3: "u3"})
        self.assertEqual([x["tipo"] for x in c], [imp.TIPO_PROJETOS_DIFERENTES])

    def test_uuid_com_versao_fora_do_cache_nao_tem_decisao_separada(self):
        grupos, _, _ = imp.consolidar([prop(1, "SIM"), prop(99, "NÃO")], [], CACHE)
        conflitos = imp.conflitos_de_estado(grupos, {1: "mesmo-uuid", 99: "mesmo-uuid"})
        self.assertEqual([c["tipo"] for c in conflitos], [imp.TIPO_GRUPOS_DIFERENTES])


class TotaisTests(unittest.TestCase):
    def test_totais_da_planilha_contam_campos(self):
        t = imp.totais_planilha(
            [prop(1, "SIM"), prop(2, "NÃO"), prop(3, "")],
            [pos("a", "Contra", prioridade="sim", acao="x"), pos("b", prioridade="não"), pos("c")],
        )
        self.assertEqual(t["relevancia"], {"SIM": 1, "NÃO": 1, "vazio": 1})
        self.assertEqual((t["posicao"], t["acao"], t["parecer"]), (1, 1, 0))
        self.assertEqual(t["prioridade"], {"SIM": 1, "NÃO": 1, "vazio": 1})


@unittest.skipUnless(test_sql_local.TEST_DATABASE_URL, "TEST_DATABASE_URL não definida")
class AplicarNoBancoTests(test_sql_local._ComDados):
    """aplicar_grupo contra um Postgres real: grava, associa todas as versões e é idempotente."""

    def executar(self, acao="agir", relevancias=("SIM", "NÃO"), prioridade="sim"):
        cache = imp.ler_cache(self.cur)
        por_id = {int(l["id_proposicao"]): l for l in cache}
        proposicoes = [prop(900011, relevancias[0]), prop(1990000011, relevancias[1])]
        posicionamento = [pos(por_id[900011]["identificacao"] + " (Câmara)", "Contra", acao=acao, prioridade=prioridade)]
        return self.aplicar(proposicoes, posicionamento)

    def aplicar(self, proposicoes, posicionamento):
        cache = imp.ler_cache(self.cur)
        grupos, conflitos, _ = imp.consolidar(proposicoes, posicionamento, cache, imp.ler_ids_silver(self.cur))
        self.assertEqual(conflitos, [])
        resultado = imp.Counter()
        for chave in sorted(grupos, key=str):
            resultado.update(imp.aplicar_grupo(self.cur, grupos[chave]))
        self.conn.commit()
        return grupos, resultado

    def test_campo_esvaziado_na_planilha_vira_null_e_valor_novo_sobe_revisao(self):
        self.executar()
        hist = lambda: self.contar("SELECT count(*) FROM gestao.historico_alteracao WHERE operacao = 'importacao_planilha'")
        antes = hist()
        _, r = self.executar(acao="")           # esvaziado
        self.assertEqual(r["decisoes_gravadas"], 1)
        self.cur.execute("SELECT acao, revisao FROM gestao.decisao_projeto WHERE relevancia = 'SIM'")
        self.assertEqual(self.cur.fetchall(), [(None, 2)])
        self.assertEqual(hist(), antes + 1)
        _, r = self.executar(acao="outra")      # valor novo
        self.cur.execute("SELECT acao, revisao FROM gestao.decisao_projeto WHERE relevancia = 'SIM'")
        self.assertEqual(self.cur.fetchall(), [("outra", 3)])
        self.assertEqual(hist(), antes + 2)

    def test_id_fora_do_cache_importa_sem_conflito_e_e_idempotente(self):
        self.cur.execute("SELECT max(id_proposicao) + 1000 FROM silver.proposicao")
        novo = self.cur.fetchone()[0]
        self.aplicar([prop(novo, "NÃO", "PL 5/2019")], [])
        self.assertEqual(self.contar("SELECT count(*) FROM gestao.projeto_proposicao WHERE id_proposicao = %s", novo), 1)
        self.assertEqual(self.contar("SELECT count(*) FROM gestao.decisao_projeto WHERE relevancia = 'NAO'"), 1)
        _, r = self.aplicar([prop(novo, "NÃO", "PL 5/2019")], [])
        self.assertEqual(sum(r.values()), 0)

    def test_posicionamento_so_na_silver_preserva_campos_e_identidade(self):
        linha = pos("PL fora do cache", "Contra", acao="Preservar esta ação")
        linha["id_proposicao"] = "900011"
        grupos, conflitos, _ = imp.consolidar([], [linha], [], {900011})
        self.assertEqual(conflitos, [])
        self.assertEqual(grupos["id900011"]["ids"], [900011])
        self.assertEqual(grupos["id900011"]["desejado"]["acao"], "Preservar esta ação")
        imp.aplicar_grupo(self.cur, grupos["id900011"])
        self.cur.execute("SELECT acao FROM gestao.decisao_projeto")
        self.assertEqual(self.cur.fetchall(), [("Preservar esta ação",)])

    def test_reimportar_outro_campo_preserva_inicio_da_prioridade(self):
        self.executar()
        self.cur.execute("UPDATE gestao.decisao_projeto SET prioridade_desde = now() - interval '30 days' WHERE prioridade")
        self.cur.execute("SELECT prioridade_desde FROM gestao.decisao_projeto WHERE prioridade")
        antes = self.cur.fetchone()[0]
        self.conn.commit()
        self.executar(acao="Ação alterada")
        self.cur.execute("SELECT prioridade_desde FROM gestao.decisao_projeto WHERE prioridade")
        self.assertEqual(self.cur.fetchone()[0], antes)

    def test_edicao_entre_leitura_e_trava_e_preservada(self):
        self.executar()
        ler_original = imp.ler_estado_grupo
        editou = False

        def ler_com_edicao(cur, ids):
            nonlocal editou
            estado = ler_original(cur, ids)
            if not editou:
                editou = True
                self.chamar("gestao.salvar_decisao", None, 900011, 1,
                            {"acao": "Decisão humana concorrente"}, test_sql_local.ATOR, "Ana")
            return estado

        with patch.object(imp, "ler_estado_grupo", side_effect=ler_com_edicao):
            _, resultado = self.executar(acao="Valor anterior da planilha")
        self.assertEqual(resultado["decisoes_preservadas"], 1)
        self.cur.execute("SELECT acao FROM gestao.decisao_projeto WHERE relevancia = 'SIM'")
        self.assertEqual(self.cur.fetchone()[0], "Decisão humana concorrente")

    def test_grava_associa_todas_as_versoes_e_nao_duplica(self):
        grupos, primeira = self.executar()
        self.assertEqual(primeira["decisoes_gravadas"], 1)
        self.assertEqual(primeira["projetos_criados"], self.contar("SELECT count(*) FROM gestao.projeto"))
        self.assertEqual(self.contar("SELECT count(DISTINCT uuid_projeto) FROM gestao.projeto_proposicao WHERE id_proposicao IN (900011, 1990000011)"), 1)
        self.assertEqual(self.contar("SELECT count(*) FROM gestao.projeto_proposicao WHERE origem <> 'migracao'"), 0)
        self.cur.execute("SELECT relevancia, posicao, prioridade, acao, revisao, atualizado_por_nome FROM gestao.decisao_projeto")
        self.assertEqual(self.cur.fetchall(), [("SIM", "Contra", True, "agir", 1, imp.ATOR_NOME)])
        self.assertEqual(self.contar("SELECT count(*) FROM gestao.historico_alteracao WHERE operacao = 'importacao_planilha' AND origem = 'migracao'"), 1)
        # acompanhada sem decisão: projeto criado, sem linha em decisao_projeto
        self.assertEqual(self.contar("SELECT count(*) FROM gestao.projeto_proposicao WHERE id_proposicao = 900032"), 1)
        projetos, assoc, hist = (self.contar(f"SELECT count(*) FROM gestao.{t}") for t in ("projeto", "projeto_proposicao", "historico_alteracao"))

        segunda_grupos, segunda = self.executar()
        self.assertEqual(sum(segunda.values()), 0)
        self.assertEqual(
            tuple(self.contar(f"SELECT count(*) FROM gestao.{t}") for t in ("projeto", "projeto_proposicao", "historico_alteracao")),
            (projetos, assoc, hist))

    def test_decisao_alterada_pela_aplicacao_e_preservada(self):
        self.executar()
        self.cur.execute("UPDATE gestao.decisao_projeto SET acao = 'mudou no sistema', revisao = 2")
        self.cur.execute(
            "INSERT INTO gestao.historico_alteracao (uuid_projeto, operacao, origem, ator_nome) "
            "SELECT uuid_projeto, 'salvar_decisao', 'aplicacao', 'Fulano' FROM gestao.decisao_projeto")
        self.conn.commit()
        _, resultado = self.executar()
        self.assertEqual(resultado["decisoes_preservadas"], 1)
        self.assertEqual(self.contar("SELECT count(*) FROM gestao.decisao_projeto WHERE acao = 'mudou no sistema'"), 1)


if __name__ == "__main__":
    unittest.main()
