import importlib.util
import shutil
import subprocess
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

spec = importlib.util.spec_from_file_location("filtro_segredos", RAIZ / "BI" / "filtro_segredos.py")
filtro = importlib.util.module_from_spec(spec)
spec.loader.exec_module(filtro)

TMDL = (
    b'expression SupabaseUrl = "https://abcdefghij.supabase.co" meta [IsParameterQuery=true]\r\n'
    # JWT partido em dois literais para o próprio teste não casar com PADROES
    b'expression SupabaseAnonKey = "eyJ' b'hbGciOiJIUzI1NiJ9.eyJyb2xlIjoiYW5vbiJ9.assinatura" meta [IsParameterQuery=true]\r\n'
    b'Origem = GoogleSheets.Contents("https://docs.google.com/spreadsheets/d/1AbC_dEf-123/edit?usp=sharing"),\r\n'
)


class FiltroSegredosTests(unittest.TestCase):
    def test_clean_troca_acessos_por_marcadores(self):
        limpo = filtro.limpar(TMDL)
        for segredo in (b"abcdefghij", b"eyJ", b"1AbC_dEf-123"):
            self.assertNotIn(segredo, limpo)
        self.assertIn(b'SupabaseAnonKey = "COLE-A-CHAVE-ANON"', limpo)
        self.assertIn(b"spreadsheets/d/ID-DA-PLANILHA/edit", limpo)
        self.assertIn(b"\r\n", limpo)
        self.assertEqual(filtro.limpar(limpo), limpo)

    def test_smudge_sem_env_mantem_marcadores(self):
        limpo = filtro.limpar(TMDL)
        original, filtro.ler_env = filtro.ler_env, lambda caminho: {}
        try:
            self.assertEqual(filtro.restaurar(limpo), limpo)
        finally:
            filtro.ler_env = original


@unittest.skipUnless(shutil.which("git") and (RAIZ / ".git").exists(), "fora de um clone do git")
class RepositorioSemAcessosTests(unittest.TestCase):
    # O repositório é público: nada de chave do Supabase (JWT) ou link de planilha no índice.
    PADROES = (r"eyJhbGci[A-Za-z0-9_-]{10,}", r"sb_(secret|publishable)_[A-Za-z0-9_-]{10,}",
               r"docs\.google\.com/spreadsheets/d/[A-Za-z0-9_-]{20,}")

    def test_nenhum_acesso_versionado(self):
        for padrao in self.PADROES:
            achados = subprocess.run(["git", "grep", "--cached", "-lIE", padrao], cwd=RAIZ,
                                     capture_output=True, text=True).stdout.split()
            self.assertEqual(achados, [], padrao)


if __name__ == "__main__":
    unittest.main()
