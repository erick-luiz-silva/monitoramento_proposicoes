"""Sessão HTTP da Câmara e tentativas, sem chamadas reais."""

from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, call, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import api_client


class SessaoCamaraTests(unittest.TestCase):
    def test_get_reutiliza_sessao_com_parametros_e_timeout(self):
        resposta = MagicMock(status_code=200)
        resposta.json.return_value = {"dados": {"id": 123}}
        with patch.object(api_client.SESSAO, "get", return_value=resposta) as get, patch.object(
            api_client.time, "sleep"
        ) as sleep:
            for _ in range(2):
                self.assertEqual(api_client._get("url-teste", {"id": 123}), resposta.json.return_value)
        self.assertEqual(get.call_args_list, [
            call("url-teste", params={"id": 123}, timeout=15),
            call("url-teste", params={"id": 123}, timeout=15),
        ])
        sleep.assert_not_called()

    def test_get_repete_5xx_com_mesmo_backoff_ate_recuperar(self):
        resposta = MagicMock(status_code=200)
        resposta.json.return_value = {"dados": []}
        with patch.object(api_client.SESSAO, "get", side_effect=[
            MagicMock(status_code=503), MagicMock(status_code=500), resposta,
        ]) as get, patch.object(api_client.time, "sleep") as sleep:
            self.assertEqual(api_client._get("url-teste"), {"dados": []})
        self.assertEqual(get.call_count, 3)
        self.assertEqual(sleep.call_args_list, [call(2), call(4)])

    def test_get_levanta_apos_tres_falhas(self):
        with patch.object(api_client.SESSAO, "get", return_value=MagicMock(status_code=503)) as get, patch.object(
            api_client.time, "sleep"
        ) as sleep:
            with self.assertRaisesRegex(RuntimeError, "após 3 tentativas: HTTP 503"):
                api_client._get("url-teste")
        self.assertEqual(get.call_count, 3)
        self.assertEqual(sleep.call_args_list, [call(2), call(4)])
