import os
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import notify_n8n


class WebhookTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "N8N_WEBHOOK_URL": "https://example.n8n.cloud/webhook/carga",
            "N8N_WEBHOOK_TOKEN": "test-token",
            "GITHUB_RUN_ID": "123", "GITHUB_REPOSITORY": "owner/repo",
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_posts_to_production_with_token_and_run_metadata(self):
        with patch.object(notify_n8n.requests, "post", return_value=Mock(status_code=200)) as post:
            notify_n8n.notify_n8n("pautas")
        post.assert_called_once()
        self.assertEqual(post.call_args.args[0], os.environ["N8N_WEBHOOK_URL"])
        options = post.call_args.kwargs
        self.assertEqual(options["headers"], {"X-Webhook-Token": "test-token"})
        self.assertFalse(options["allow_redirects"])
        self.assertEqual(options["timeout"], (10, 60))
        self.assertEqual(options["json"]["modo"], "pautas")
        self.assertEqual(options["json"]["origem"], "github_actions")
        self.assertEqual(options["json"]["run_id"], "123")
        self.assertNotIn("test-token", str(options["json"]))

    def test_http_errors_and_redirects_fail(self):
        for status in [301, 401, 404, 500]:
            with self.subTest(status=status), patch.object(
                notify_n8n.requests, "post", return_value=Mock(status_code=status)
            ):
                with self.assertRaisesRegex(RuntimeError, f"HTTP {status}"):
                    notify_n8n.notify_n8n("completo")

    def test_timeout_does_not_retry_or_expose_secret(self):
        with patch.object(notify_n8n.requests, "post", side_effect=requests.Timeout("test-token")) as post:
            with self.assertRaises(RuntimeError) as exc:
                notify_n8n.notify_n8n("completo")
        post.assert_called_once()
        self.assertNotIn("test-token", str(exc.exception))

    def test_missing_secret_prevents_request(self):
        with patch.dict(os.environ, {"N8N_WEBHOOK_TOKEN": ""}), patch.object(notify_n8n.requests, "post") as post:
            with self.assertRaisesRegex(RuntimeError, "Configure"):
                notify_n8n.notify_n8n("completo")
        post.assert_not_called()

    def test_test_webhook_or_plain_http_is_rejected(self):
        for url in ["https://example.n8n.cloud/webhook-test/carga", "http://example.n8n.cloud/webhook/carga"]:
            with self.subTest(url=url), patch.dict(os.environ, {"N8N_WEBHOOK_URL": url}):
                with self.assertRaisesRegex(RuntimeError, "produção"):
                    notify_n8n.webhook_config()


if __name__ == "__main__":
    unittest.main()
