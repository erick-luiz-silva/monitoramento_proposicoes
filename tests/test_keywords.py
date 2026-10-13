"""Precisão das keywords com ementas fixas, sem banco.

As regexes são POSIX (operador ~* do Postgres). Para testar em Python, \\m vira
início de palavra: (?<!\\w)(?=\\w). ~* é case-insensitive, então usamos re.I.
"""

from pathlib import Path
import re
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from keywords import KEYWORDS


def _posix_para_python(padrao):
    return padrao.replace(r"\m", r"(?<!\w)(?=\w)")


def _casa(padrao, texto):
    return re.search(_posix_para_python(padrao), texto, re.I | re.S) is not None


def _keyword(rotulo):
    return next(k for k in KEYWORDS if k[0] == rotulo)


def _rotulos_que_casam(ementa, keywords_camara=""):
    """Replica gold.vw_proposicao_keywords: termo em ementa ou keywords, e o requerido também."""
    casados = set()
    for rotulo, termo, requerido in KEYWORDS:
        if not (_casa(termo, ementa) or _casa(termo, keywords_camara)):
            continue
        if requerido is not None and not (_casa(requerido, ementa) or _casa(requerido, keywords_camara)):
            continue
        casados.add(rotulo)
    return casados


class KeywordPatternTests(unittest.TestCase):
    def test_todos_os_padroes_compilam(self):
        for rotulo, termo, requerido in KEYWORDS:
            with self.subTest(rotulo=rotulo):
                re.compile(_posix_para_python(termo), re.I | re.S)
                if requerido is not None:
                    re.compile(_posix_para_python(requerido), re.I | re.S)

    def test_animais_de_producao_nao_pega_producoes_cinematograficas(self):
        self.assertNotIn("animais de produção", _rotulos_que_casam(
            "Dispõe sobre produções cinematográficas e animais de estimação"
        ))

    def test_animais_de_producao_pega_a_expressao_completa(self):
        self.assertIn("animais de produção", _rotulos_que_casam(
            "Altera a Lei para dispor sobre animais de produção e bem-estar"
        ))
        self.assertIn("animais de produção", _rotulos_que_casam(
            "Dispõe sobre a produção animal em propriedades rurais"
        ))

    def test_aves_exige_contexto_de_producao(self):
        self.assertNotIn("aves", _rotulos_que_casam("Dispõe sobre aves silvestres e a Navegação"))
        self.assertIn("aves", _rotulos_que_casam("Proteção de aves em granjas comerciais"))
        self.assertIn("aves", _rotulos_que_casam("Regras para aves poedeiras"))

    def test_racoes_e_milho_exigem_contexto_de_producao(self):
        self.assertNotIn("rações animais", _rotulos_que_casam("Ração para animais de estimação"))
        self.assertIn("rações animais", _rotulos_que_casam("Ração para animais de produção confinados"))
        self.assertNotIn("milho", _rotulos_que_casam("Política de preços do milho no Plano Safra"))
        self.assertIn("milho", _rotulos_que_casam("Preço do milho para granjas e confinamento"))

    def test_rotulo_pega_rotulagem_com_contexto_de_carne(self):
        self.assertIn("rótulo", _rotulos_que_casam("Rotulagem de carne bovina e suína"))
        self.assertIn("rótulo", _rotulos_que_casam("Rótulo de produtos de origem animal"))
        self.assertNotIn("rótulo", _rotulos_que_casam("Rótulo de produtos de higiene pessoal"))

    def test_trabalhador_rural_exige_contexto(self):
        self.assertNotIn("trabalhador rural", _rotulos_que_casam("Direitos do trabalhador rural urbano"))
        self.assertIn("trabalhador rural", _rotulos_que_casam("Direitos do trabalhador rural na safra"))

    def test_maus_tratos_nao_casa_mais_sem_contexto(self):
        # Decisão [T] do plano (passo 2): PL 3789/2023 sai e volta no passo 8.
        self.assertNotIn("animais de produção", _rotulos_que_casam(
            "Tipifica maus-tratos contra animais domésticos"
        ))


if __name__ == "__main__":
    unittest.main()
