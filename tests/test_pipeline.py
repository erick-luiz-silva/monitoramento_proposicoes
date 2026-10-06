"""Regressões de falhas e reexecução, sem acessar a API ou o banco real."""

from contextlib import ExitStack, contextmanager
from datetime import date
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import check_environment
import extract_incremental
import load_bronze
import load_dim_deputado
import load_eventos
import load_silver
import pipeline_pautas


class FakeConnection:
    """Simula transação abortada após erro SQL, até ocorrer rollback."""

    def __init__(self, fail_table):
        self.fail_table = fail_table
        self.aborted = False
        self.pending = []
        self.persisted = []
        self.rollbacks = 0

    @contextmanager
    def cursor(self):
        yield self

    def execute(self, sql, params):
        if self.aborted:
            raise RuntimeError("transaction is aborted")
        if self.fail_table in sql:
            self.aborted = True
            raise RuntimeError("simulated SQL failure")
        self.pending.append(params)

    def commit(self):
        if self.aborted:
            self.pending.clear()
        else:
            self.persisted.extend(self.pending)
            self.pending.clear()
        self.aborted = False

    def rollback(self):
        self.pending.clear()
        self.aborted = False
        self.rollbacks += 1


class LoaderTests(unittest.TestCase):
    def test_bronze_recovers_after_sql_failure_and_preserves_other_endpoints(self):
        conn = FakeConnection("bronze.autores_json")
        with ExitStack() as stack:
            stack.enter_context(patch.object(load_bronze.time, "sleep"))
            for method in ["buscar_detalhes", "buscar_autores", "buscar_temas", "buscar_tramitacoes"]:
                stack.enter_context(patch.object(load_bronze.api, method, return_value=[]))
            result = load_bronze.carregar_proposicao_bronze(conn, 123)
        self.assertEqual(conn.rollbacks, 1)
        self.assertEqual(len(conn.persisted), 3)
        self.assertEqual(result["proposicoes_json"], "ok")
        self.assertTrue(result["autores_json"].startswith("erro:"))
        self.assertEqual(result["temas_json"], "ok")
        self.assertEqual(result["tramitacoes_json"], "ok")

    def test_events_recovers_transaction_after_pauta_failure(self):
        conn = FakeConnection("bronze.eventos_pauta_json")
        with patch.object(load_eventos.time, "sleep"), patch.object(
            load_eventos.api, "buscar_pauta_evento", return_value=[]
        ):
            result = load_eventos.carregar_evento_bronze(conn, {"id": 123})
        self.assertEqual(conn.rollbacks, 1)
        self.assertEqual(len(conn.persisted), 1)
        self.assertEqual(result["evento"], "ok")
        self.assertTrue(result["pauta"].startswith("erro:"))

    def test_event_batch_raises_on_partial_failure(self):
        conn = MagicMock()
        with patch.object(load_eventos, "get_connection", return_value=conn), patch.object(
            load_eventos.api, "listar_eventos", return_value=[{"id": 123}]
        ), patch.object(load_eventos, "carregar_evento_bronze", return_value={
            "evento": "ok", "pauta": "erro: timeout"
        }):
            with self.assertRaisesRegex(RuntimeError, "incompleta"):
                load_eventos.executar_carga_eventos(date(2026, 10, 1), date(2026, 10, 6))

    def test_deputado_batch_rolls_back_and_signals_failure(self):
        conn = MagicMock()
        db = conn.__enter__.return_value
        cur = db.cursor.return_value.__enter__.return_value
        cur.fetchall.return_value = [(1,), (2,)]
        cur.execute.side_effect = [None, RuntimeError("SQL failure"), None]
        with patch.object(load_dim_deputado, "get_connection", return_value=conn), patch.object(
            load_dim_deputado.api, "buscar_deputado", return_value={"ultimoStatus": {}}
        ), patch.object(load_dim_deputado.time, "sleep"):
            with self.assertRaisesRegex(RuntimeError, "incompleta"):
                load_dim_deputado.carregar_dim_deputado()
        db.rollback.assert_called_once()
        db.commit.assert_called_once()


class IncrementalTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(extract_incremental, "get_connection", return_value=MagicMock()))
        self.stack.enter_context(patch.object(extract_incremental, "calcular_janela", return_value=(
            date(2026, 10, 3), date(2026, 10, 6)
        )))
        self.stack.enter_context(patch.object(extract_incremental, "coletar_ids_unicos", return_value=[123]))
        self.bronze = self.stack.enter_context(patch.object(
            extract_incremental, "carregar_proposicao_bronze", return_value={"proposicoes_json": "ok"}
        ))
        self.events = []
        self.stages = {}
        for name in ["executar_carga_eventos", "executar_transformacao_silver", "carregar_dim_deputado", "carregar_dim_orgao"]:
            def execute(*args, stage=name):
                self.events.append(stage)
                return 1
            self.stages[name] = self.stack.enter_context(patch.object(
                extract_incremental, name, side_effect=execute
            ))
        self.register = self.stack.enter_context(patch.object(
            extract_incremental, "registrar_execucao", side_effect=lambda *args: self.events.append("checkpoint")
        ))

    def test_partial_bronze_failure_does_not_advance_window(self):
        self.bronze.return_value = {"proposicoes_json": "erro: timeout"}
        with self.assertRaisesRegex(RuntimeError, "incompleta"):
            extract_incremental.executar_carga_incremental()
        self.register.assert_not_called()
        self.stages["executar_carga_eventos"].assert_not_called()

    def test_failure_in_any_downstream_stage_does_not_advance_window(self):
        for name, mock in self.stages.items():
            with self.subTest(stage=name):
                previous_effect = mock.side_effect
                mock.side_effect = RuntimeError("stage failed")
                with self.assertRaisesRegex(RuntimeError, "stage failed"):
                    extract_incremental.executar_carga_incremental()
                self.register.assert_not_called()
                mock.side_effect = previous_effect

    def test_success_registers_both_windows_only_after_all_stages(self):
        extract_incremental.executar_carga_incremental()
        self.assertEqual(self.events, [
            "executar_carga_eventos", "executar_transformacao_silver", "carregar_dim_deputado",
            "carregar_dim_orgao", "checkpoint", "checkpoint"
        ])
        self.assertEqual([call.args[1] for call in self.register.call_args_list], ["incremental", "eventos"])


class WindowTests(unittest.TestCase):
    def test_windows_cover_initial_recent_and_missed_runs(self):
        for last, expected in [
            (None, date(2026, 10, 3)),
            (date(2026, 10, 5), date(2026, 10, 2)),
            (date(2026, 9, 20), date(2026, 9, 17)),
        ]:
            with self.subTest(last=last):
                conn = MagicMock()
                conn.cursor.return_value.__enter__.return_value.fetchone.return_value = (last,)
                with patch.object(extract_incremental, "date") as mock_date:
                    mock_date.today.return_value = date(2026, 10, 6)
                    self.assertEqual(extract_incremental.calcular_janela(conn), (expected, date(2026, 10, 6)))


class EnvironmentTests(unittest.TestCase):
    def setUp(self):
        self.conn = MagicMock()
        self.cur = self.conn.__enter__.return_value.cursor.return_value.__enter__.return_value

    def test_missing_schema_blocks_execution(self):
        self.cur.fetchone.return_value = (None,)
        with patch.object(check_environment, "get_connection", return_value=self.conn):
            with self.assertRaisesRegex(RuntimeError, "Banco não inicializado"):
                check_environment.check_environment()

    def test_empty_keywords_blocks_execution(self):
        self.cur.fetchone.side_effect = [(name,) for name in check_environment.REQUIRED_RELATIONS] + [(0,)]
        with patch.object(check_environment, "get_connection", return_value=self.conn):
            with self.assertRaisesRegex(RuntimeError, "Nenhuma keyword ativa"):
                check_environment.check_environment()

    def test_initialized_database_passes(self):
        self.cur.fetchone.side_effect = [(name,) for name in check_environment.REQUIRED_RELATIONS] + [(10,)]
        with patch.object(check_environment, "get_connection", return_value=self.conn):
            check_environment.check_environment()
        self.conn.__enter__.return_value.commit.assert_not_called()


class PautaTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(pipeline_pautas, "get_connection", return_value=MagicMock()))
        mock_date = self.stack.enter_context(patch.object(pipeline_pautas, "date"))
        mock_date.today.return_value = date(2026, 10, 6)
        self.calls = MagicMock()
        self.stages = {}
        for name in ["executar_carga_eventos", "executar_transformacao_eventos", "carregar_dim_deputado",
                     "carregar_dim_orgao", "registrar_execucao"]:
            mock = self.stack.enter_context(patch.object(pipeline_pautas, name))
            self.calls.attach_mock(mock, name)
            self.stages[name] = mock
        self.stages["executar_carga_eventos"].return_value = 12

    def test_refreshes_events_and_relatores_without_advancing_propositions(self):
        pipeline_pautas.executar_pipeline_pautas()
        self.stages["executar_carga_eventos"].assert_called_once_with(date(2026, 9, 29), date(2026, 10, 20))
        self.stages["carregar_dim_deputado"].assert_called_once_with(somente_relatores=True)
        register = self.stages["registrar_execucao"]
        register.assert_called_once()
        self.assertEqual(register.call_args.args[1:], ("eventos", date(2026, 9, 29), date(2026, 10, 20), 12))
        self.assertEqual([c[0] for c in self.calls.mock_calls], [
            "executar_carga_eventos", "executar_transformacao_eventos", "carregar_dim_deputado",
            "carregar_dim_orgao", "registrar_execucao"
        ])

    def test_failed_stage_does_not_register_success(self):
        for name in ["executar_carga_eventos", "executar_transformacao_eventos", "carregar_dim_deputado", "carregar_dim_orgao"]:
            with self.subTest(stage=name):
                self.stages[name].side_effect = RuntimeError("refresh failed")
                with self.assertRaisesRegex(RuntimeError, "refresh failed"):
                    pipeline_pautas.executar_pipeline_pautas()
                self.stages["registrar_execucao"].assert_not_called()
                self.stages[name].side_effect = None

    def test_event_transformation_does_not_write_propositions(self):
        conn = MagicMock()
        with patch.object(load_silver, "get_connection", return_value=conn):
            load_silver.executar_transformacao_eventos()
        sql = conn.__enter__.return_value.cursor.return_value.__enter__.return_value.execute.call_args.args[0]
        self.assertIn("INSERT INTO silver.evento", sql)
        self.assertIn("INSERT INTO silver.evento_pauta", sql)
        self.assertNotIn("INSERT INTO silver.proposicao", sql)
        conn.__enter__.return_value.commit.assert_called_once()

    def test_relatores_mode_does_not_query_authors(self):
        conn = MagicMock()
        cur = conn.__enter__.return_value.cursor.return_value.__enter__.return_value
        cur.fetchall.return_value = []
        with patch.object(load_dim_deputado, "get_connection", return_value=conn):
            load_dim_deputado.carregar_dim_deputado(somente_relatores=True)
        sql = cur.execute.call_args.args[0]
        self.assertIn("silver.evento_pauta", sql)
        self.assertNotIn("proposicoes_proponentes", sql)


if __name__ == "__main__":
    unittest.main()
