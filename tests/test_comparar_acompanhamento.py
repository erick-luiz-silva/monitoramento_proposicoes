"""Funções puras do comparador de acompanhamento, sem API, planilha ou banco."""

from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import comparar_acompanhamento as comp


class IdentificadoresTests(unittest.TestCase):
    def test_extrai_siglas_e_normaliza_numero(self):
        self.assertEqual(
            comp.identificadores("PL 3584/2015; pl 0752 de 2023 e PLP 10/2019"),
            {"PL 3584/2015", "PL 752/2023", "PLP 10/2019"},
        )

    def test_texto_vazio_nao_gera_identificadores(self):
        self.assertEqual(comp.identificadores(None), set())
        self.assertEqual(comp.identificadores(""), set())


class PrecisaoTests(unittest.TestCase):
    def test_conta_sim_e_nao_por_keyword_da_planilha(self):
        linhas = [
            {"relevancia": "SIM", "keywords_encontradas": "suínos, sanidade"},
            {"relevancia": "NÃO", "keywords_encontradas": "sanidade"},
            {"relevancia": "", "keywords_encontradas": "suínos"},
        ]
        contagem = comp.precisao_por_keyword(linhas)
        self.assertEqual(contagem["suínos"], {"SIM": 1, "NÃO": 0})
        self.assertEqual(contagem["sanidade"], {"SIM": 1, "NÃO": 1})

    def test_usa_rotulos_simulados_quando_informados(self):
        linhas = [{"id_proposicao": "10", "relevancia": "NAO", "keywords_encontradas": "ignorado"}]
        contagem = comp.precisao_por_keyword(linhas, {10: "aves"})
        self.assertEqual(contagem["aves"], {"SIM": 0, "NÃO": 1})
        self.assertNotIn("ignorado", contagem)


class ClassificacaoTests(unittest.TestCase):
    def test_grupos_na_ordem_do_plano(self):
        self.assertEqual(comp.classificar(1, [64], {1}, {1}), "A_NO_GOLD")
        self.assertEqual(comp.classificar(2, [64], set(), {2}), "B_SILVER_SEM_KEYWORD")
        self.assertEqual(comp.classificar(3, [48], set(), set()), "C1_FORA_BANCO_DENTRO_TEMAS")
        self.assertEqual(comp.classificar(4, [66], set(), set()), "C2_FORA_TEMAS")


class LeituraDaPlanilhaTests(unittest.TestCase):
    def test_completa_celulas_vazias_no_fim_da_linha(self):
        resposta = MagicMock()
        resposta.json.return_value = {"values": [["relevancia", "id_proposicao"], ["SIM"]]}
        sessao = MagicMock()
        sessao.get.return_value = resposta
        linhas = comp.ler_aba(sessao, "sheet", "Proposições")
        self.assertEqual(linhas, [{"relevancia": "SIM", "id_proposicao": ""}])


if __name__ == "__main__":
    unittest.main()
