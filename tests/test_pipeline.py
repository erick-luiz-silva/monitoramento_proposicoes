"""Regressões de falhas e reexecução, sem acessar a API ou o banco real."""

from contextlib import ExitStack, contextmanager
from datetime import date, timedelta
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import check_environment
import comparar_acompanhamento
import config
import extract_bronze
import extract_incremental
import load_api
import load_bronze
import load_dim_deputado
import load_eventos
import load_silver
import pipeline_inclusao
import pipeline_pautas
import setup_db


class FakeConnection:
    """Simula transação abortada após erro SQL, até ocorrer rollback."""

    def __init__(self, fail_table):
        self.fail_table = fail_table
        self.aborted = False
        self.pending = []
        self.persisted = []
        self.rollbacks = 0
        self.closed = 0

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

    def test_bronze_conexao_fechada_levanta_sem_rollback(self):
        conn = FakeConnection("bronze.proposicoes_json")
        conn.closed = 1
        with ExitStack() as stack:
            stack.enter_context(patch.object(load_bronze.time, "sleep"))
            for method in ["buscar_detalhes", "buscar_autores", "buscar_temas", "buscar_tramitacoes"]:
                stack.enter_context(patch.object(load_bronze.api, method, return_value=[]))
            with self.assertRaises(load_bronze.ConexaoPerdida):
                load_bronze.carregar_proposicao_bronze(conn, 123)
        self.assertEqual(conn.rollbacks, 0)

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
        self.acompanhadas = self.stack.enter_context(patch.object(
            extract_incremental, "carregar_ids_acompanhadas", return_value=[]
        ))
        self.carregar_extras = self.stack.enter_context(patch.object(
            extract_incremental, "carregar_ids", side_effect=lambda ids, levantar_erro: (list(ids), 0)
        ))
        self.stack.enter_context(patch.object(extract_incremental, "coletar_ids_unicos", return_value=[123]))
        self.reconciliacao = self.stack.enter_context(patch.object(
            extract_incremental, "executar_reconciliacao",
            return_value=(date(2026, 7, 8), date(2026, 10, 6), [456], 0),
        ))
        self.bronze = self.stack.enter_context(patch.object(
            extract_incremental, "carregar_proposicao_bronze", return_value={"proposicoes_json": "ok"}
        ))
        self.events = []
        self.stages = {}
        for name in ["executar_carga_eventos", "executar_transformacao_silver", "carregar_dim_deputado", "carregar_dim_orgao"]:
            def execute(*args, stage=name, **kwargs):
                self.events.append(stage)
                return 1
            self.stages[name] = self.stack.enter_context(patch.object(
                extract_incremental, name, side_effect=execute
            ))
        self.register = self.stack.enter_context(patch.object(
            extract_incremental, "registrar_execucao", side_effect=lambda *args: self.events.append("checkpoint")
        ))
        self.api = self.stack.enter_context(patch.object(
            extract_incremental, "atualizar_api", side_effect=lambda: self.events.append("api")
        ))

    def tipos_registrados(self):
        return [call.args[1] for call in self.register.call_args_list]

    def test_partial_bronze_failure_does_not_advance_window(self):
        self.bronze.return_value = {"proposicoes_json": "erro: timeout"}
        with self.assertRaisesRegex(RuntimeError, "incompleta"):
            extract_incremental.executar_carga_incremental()
        self.register.assert_not_called()
        self.reconciliacao.assert_not_called()
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

    def test_success_registers_windows_only_after_all_stages(self):
        extract_incremental.executar_carga_incremental()
        self.assertEqual(self.events, [
            "executar_carga_eventos", "executar_transformacao_silver", "carregar_dim_deputado",
            "carregar_dim_orgao", "checkpoint", "checkpoint", "checkpoint", "api"
        ])
        self.assertEqual(self.tipos_registrados(), ["incremental", "eventos", "reconciliacao"])
        self.assertEqual(self.register.call_args_list[2].args[2:], (date(2026, 7, 8), date(2026, 10, 6), 1))

    def test_falha_no_schema_api_nao_trava_janela_e_falha_no_fim(self):
        self.api.side_effect = RuntimeError("lock timeout")
        with self.assertRaisesRegex(RuntimeError, "schema api falhou: lock timeout"):
            extract_incremental.executar_carga_incremental()
        self.assertEqual(self.tipos_registrados(), ["incremental", "eventos", "reconciliacao"])

    def test_schema_api_atualiza_mesmo_com_reconciliacao_falhando(self):
        self.reconciliacao.side_effect = RuntimeError("API fora do ar")
        self.api.side_effect = RuntimeError("lock timeout")
        with self.assertRaisesRegex(RuntimeError, "conciliação.*schema api falhou"):
            extract_incremental.executar_carga_incremental()
        self.api.assert_called_once()

    def test_reconciliacao_roda_apos_d14_sem_repetir_seus_ids(self):
        extract_incremental.executar_carga_incremental()
        self.reconciliacao.assert_called_once_with(90, levantar_erro=False, ignorar=[123])

    def test_dim_deputado_recebe_ids_da_janela_e_da_reconciliacao(self):
        extract_incremental.executar_carga_incremental()
        self.stages["carregar_dim_deputado"].assert_called_once_with(seletivo=True, ids_proposicao=[123, 456])

    def test_acompanhadas_entram_na_carga_diaria_sem_repetir(self):
        self.acompanhadas.return_value = [123, 789]
        extract_incremental.executar_carga_incremental()
        self.assertEqual([c.args[1] for c in self.bronze.call_args_list], [123])
        self.carregar_extras.assert_called_once_with([789], levantar_erro=False)
        self.reconciliacao.assert_called_once_with(90, levantar_erro=False, ignorar=[123, 789])
        self.stages["carregar_dim_deputado"].assert_called_once_with(seletivo=True, ids_proposicao=[123, 789, 456])
        # qtd do incremental conta só a janela D-14
        self.assertEqual(self.register.call_args_list[0].args[1:], ("incremental", date(2026, 10, 3), date(2026, 10, 6), 1))

    def test_acompanhada_com_erro_nao_trava_a_janela(self):
        self.acompanhadas.return_value = [789]
        for efeito in [{"side_effect": lambda ids, levantar_erro: (list(ids), 1)},
                       {"side_effect": RuntimeError("Conexão com o banco perdida")}]:
            with self.subTest(efeito=efeito):
                self.register.reset_mock()
                self.carregar_extras.configure_mock(**efeito)
                with self.assertRaisesRegex(RuntimeError, "acompanhadas"):
                    extract_incremental.executar_carga_incremental()
                self.assertEqual(self.tipos_registrados(), ["incremental", "eventos", "reconciliacao"])

    def test_erro_na_reconciliacao_registra_incremental_e_falha_no_fim(self):
        for efeito in [
            {"return_value": (date(2026, 7, 8), date(2026, 10, 6), [456], 2)},
            {"side_effect": RuntimeError("API fora do ar")},
        ]:
            with self.subTest(efeito=efeito):
                self.register.reset_mock()
                self.reconciliacao.side_effect = None
                self.reconciliacao.configure_mock(**efeito)
                with self.assertRaisesRegex(RuntimeError, "conciliação"):
                    extract_incremental.executar_carga_incremental()
                self.assertEqual(self.tipos_registrados(), ["incremental", "eventos"])
                self.stages["carregar_dim_orgao"].assert_called()

class WindowTests(unittest.TestCase):
    def test_windows_cover_initial_recent_and_missed_runs(self):
        for last, expected in [
            (None, date(2026, 9, 22)),
            (date(2026, 10, 5), date(2026, 9, 21)),
            (date(2026, 9, 20), date(2026, 9, 6)),
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


class BackfillTests(unittest.TestCase):
    def test_janelas_sao_contiguas_limitadas_e_ate_hoje(self):
        janelas = extract_bronze.gerar_janelas(date(2023, 2, 1), date(2026, 10, 13))
        self.assertEqual(janelas[0][0], date(2023, 2, 1))
        self.assertEqual(janelas[-1][1], date(2026, 10, 13))
        for (ini, fim), (prox_ini, _) in zip(janelas, janelas[1:]):
            self.assertLessEqual((fim - ini).days, 89)
            self.assertEqual(prox_ini, fim + timedelta(days=1))
        self.assertLessEqual((janelas[-1][1] - janelas[-1][0]).days, 89)

    def test_janela_unica_quando_periodo_cabe_no_limite(self):
        self.assertEqual(
            extract_bronze.gerar_janelas(date(2026, 10, 1), date(2026, 10, 13)),
            [(date(2026, 10, 1), date(2026, 10, 13))],
        )
        self.assertEqual(extract_bronze.gerar_janelas(date(2026, 10, 2), date(2026, 10, 1)), [])

    def test_ids_deduplicados_entre_janelas_e_temas(self):
        def listar(cod_tema, data_inicio, data_fim):
            return [{"id": 1}, {"id": 2}] if data_inicio.month == 1 else [{"id": 2}, {"id": 3}]

        janelas = [(date(2026, 1, 1), date(2026, 1, 31)), (date(2026, 2, 1), date(2026, 2, 28))]
        with patch.object(extract_bronze.api, "listar_proposicoes_por_tema", side_effect=listar):
            ids = extract_bronze.coletar_ids_janelas(janelas)
        self.assertEqual(ids, [1, 2, 3])

    def test_pular_existentes_nao_recarrega_ids_completos(self):
        conn = MagicMock()
        cur = conn.__enter__.return_value.cursor.return_value.__enter__.return_value
        cur.fetchall.return_value = [(1,)]
        with patch.object(extract_bronze, "get_connection", return_value=conn), patch.object(
            extract_bronze, "carregar_proposicao_bronze", return_value={"proposicoes_json": "ok"}
        ) as carregar:
            extract_bronze.carregar_ids([1, 2], pular_existentes=True)
        carregar.assert_called_once()
        self.assertEqual(carregar.call_args.args[1], 2)

    def test_falha_parcial_levanta_erro_sem_registrar_janela(self):
        conn = MagicMock()
        with patch.object(extract_bronze, "get_connection", return_value=conn), patch.object(
            extract_bronze, "carregar_proposicao_bronze", return_value={"autores_json": "erro: timeout"}
        ):
            with self.assertRaisesRegex(RuntimeError, "incompleta"):
                extract_bronze.carregar_ids([123])
        executed = [c.args[0] for c in conn.__enter__.return_value.cursor.return_value.__enter__.return_value.execute.call_args_list]
        self.assertFalse(any("controle_execucao" in sql for sql in executed))

    def test_reconecta_apos_queda_e_tenta_de_novo_a_mesma_proposicao(self):
        conn1, conn2 = MagicMock(), MagicMock()
        chamadas = []

        def carregar(conn, id_prop):
            chamadas.append((conn, id_prop))
            if id_prop == 2 and len(chamadas) == 2:
                raise extract_bronze.ConexaoPerdida("server closed the connection unexpectedly")
            return {"proposicoes_json": "ok"}

        with patch.object(extract_bronze, "get_connection", side_effect=[conn1, conn2]) as get_conn, patch.object(
            extract_bronze, "carregar_proposicao_bronze", side_effect=carregar
        ), patch.object(extract_bronze.time, "sleep"):
            extract_bronze.carregar_ids([1, 2, 3])
        self.assertEqual(get_conn.call_count, 2)
        self.assertEqual([id_prop for _, id_prop in chamadas], [1, 2, 2, 3])
        self.assertIs(chamadas[2][0], conn2.__enter__.return_value)
        conn1.__exit__.assert_called_once()

    def test_reconexao_esgotada_levanta_erro_para_retomar(self):
        conn = MagicMock()
        falha = extract_bronze.psycopg2.OperationalError("connection refused")
        with patch.object(
            extract_bronze, "get_connection", side_effect=[conn] + [falha] * len(extract_bronze.RECONEXAO_ESPERAS)
        ), patch.object(
            extract_bronze, "carregar_proposicao_bronze", side_effect=extract_bronze.ConexaoPerdida("caiu")
        ), patch.object(extract_bronze.time, "sleep"):
            with self.assertRaisesRegex(RuntimeError, "--pular-existentes"):
                extract_bronze.carregar_ids([1])
        executed = [c.args[0] for c in conn.__enter__.return_value.cursor.return_value.__enter__.return_value.execute.call_args_list]
        self.assertFalse(any("controle_execucao" in sql for sql in executed))

    def test_reconciliacao_carrega_so_ausentes(self):
        # 1 e 2: já na bronze; 3: ausente; 4: ausente, mas já carregado neste run
        with patch.object(extract_bronze, "date") as mock_date, patch.object(
            extract_bronze, "coletar_ids_janelas", return_value=[1, 2, 3, 4]
        ) as coletar, patch.object(extract_bronze, "get_connection"), patch.object(
            extract_bronze, "carregar_ids_existentes", return_value={1, 2}
        ), patch.object(extract_bronze, "carregar_ids", return_value=([3], 0)) as carregar:
            mock_date.today.return_value = date(2026, 10, 13)
            resultado = extract_bronze.executar_reconciliacao(60, levantar_erro=False, ignorar=[4])
        janelas = coletar.call_args.args[0]
        self.assertEqual(janelas[0][0], date(2026, 10, 13) - timedelta(days=60))
        self.assertEqual(janelas[-1][1], date(2026, 10, 13))
        carregar.assert_called_once_with([3], levantar_erro=False)
        self.assertEqual(resultado, (date(2026, 10, 13) - timedelta(days=60), date(2026, 10, 13), [3], 0))

    def test_carregar_ids_sem_levantar_devolve_erros(self):
        with patch.object(extract_bronze, "get_connection"), patch.object(
            extract_bronze, "carregar_proposicao_bronze", return_value={"autores_json": "erro: 500"}
        ):
            self.assertEqual(extract_bronze.carregar_ids([5], levantar_erro=False), ([5], 1))


class CliBackfillTests(unittest.TestCase):
    def executar_cli(self, *argv):
        with patch.object(extract_bronze, "executar_carga_bronze") as carga, patch.object(
            extract_bronze, "carregar_ids"
        ) as carregar, patch.object(extract_bronze, "listar_ids_novos") as listar, patch.object(
            extract_bronze, "executar_reconciliacao"
        ):
            extract_bronze.main(list(argv))
        return carga, carregar, listar

    def test_ate_e_so_listar_vao_para_a_carga_por_janelas(self):
        carga, carregar, _ = self.executar_cli("--desde", "2023-02-01", "--ate", "2025-10-12", "--so-listar")
        carga.assert_called_once_with(
            desde=date(2023, 2, 1), ate=date(2025, 10, 12), pular_existentes=False, limit=None, so_listar=True
        )
        carregar.assert_not_called()

    def test_ids_carrega_so_os_ids_dados(self):
        carga, carregar, listar = self.executar_cli("--ids", "10,20, 30", "--pular-existentes")
        carregar.assert_called_once_with([10, 20, 30], pular_existentes=True, limit=None)
        carga.assert_not_called()
        listar.assert_not_called()

    def test_ids_com_so_listar_nao_carrega(self):
        _, carregar, listar = self.executar_cli("--ids", "10", "--so-listar")
        listar.assert_called_once_with([10])
        carregar.assert_not_called()

    def test_so_listar_nao_carrega_nada(self):
        with patch.object(extract_bronze, "coletar_ids_janelas", return_value=[1, 2]), patch.object(
            extract_bronze, "listar_ids_novos"
        ) as listar, patch.object(extract_bronze, "carregar_ids") as carregar:
            extract_bronze.executar_carga_bronze(date(2026, 1, 1), date(2026, 2, 1), so_listar=True)
        listar.assert_called_once_with([1, 2])
        carregar.assert_not_called()


class TemasTests(unittest.TestCase):
    def test_temas_definidos_so_em_config(self):
        self.assertEqual(config.TEMAS, [64, 48, 66])
        for modulo in (extract_bronze, extract_incremental, comparar_acompanhamento):
            self.assertIs(modulo.TEMAS, config.TEMAS, modulo.__name__)
        src = Path(__file__).resolve().parents[1] / "src"
        definicoes = [f.name for f in src.glob("*.py") if re.search(r"^TEMAS\s*=", f.read_text(encoding="utf-8"), re.M)]
        self.assertEqual(definicoes, ["config.py"])


class DimDeputadoSelecaoTests(unittest.TestCase):
    def consulta(self, **kwargs):
        conn = MagicMock()
        cur = conn.__enter__.return_value.cursor.return_value.__enter__.return_value
        cur.fetchall.return_value = []
        with patch.object(load_dim_deputado, "get_connection", return_value=conn):
            load_dim_deputado.carregar_dim_deputado(**kwargs)
        return cur.execute.call_args.args

    def test_sem_argumentos_carrega_todos(self):
        sql, params = self.consulta()
        self.assertIn("proposicoes_proponentes", sql)
        self.assertNotIn("dim_deputado", sql)
        self.assertIsNone(params)

    def test_seletivo_ausentes_autores_do_run_e_defasados(self):
        sql, params = self.consulta(seletivo=True, ids_proposicao=[1, 2])
        self.assertIn("NOT EXISTS (SELECT 1 FROM silver.dim_deputado", sql)
        self.assertIn("id_proposicao = ANY(%(ids)s)", sql)
        self.assertIn("d.data_extracao < now() - make_interval(days => %(refresh_dias)s)", sql)
        self.assertIn("LIMIT", sql)
        self.assertEqual(params, {"refresh_dias": 7, "ids": [1, 2]})

    def test_seletivo_relatores_nao_consulta_autores(self):
        sql, params = self.consulta(seletivo=True, somente_relatores=True)
        self.assertIn("silver.evento_pauta", sql)
        self.assertIn("NOT EXISTS (SELECT 1 FROM silver.dim_deputado", sql)
        self.assertIn("make_interval", sql)
        self.assertNotIn("proposicoes_proponentes", sql)
        self.assertEqual(params["ids"], [])


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
                     "carregar_dim_orgao", "registrar_execucao", "atualizar_api"]:
            mock = self.stack.enter_context(patch.object(pipeline_pautas, name))
            self.calls.attach_mock(mock, name)
            self.stages[name] = mock
        self.stages["executar_carga_eventos"].return_value = 12

    def test_refreshes_events_and_relatores_without_advancing_propositions(self):
        pipeline_pautas.executar_pipeline_pautas()
        self.stages["executar_carga_eventos"].assert_called_once_with(date(2026, 9, 29), date(2026, 10, 20))
        self.stages["carregar_dim_deputado"].assert_called_once_with(somente_relatores=True, seletivo=True)
        register = self.stages["registrar_execucao"]
        register.assert_called_once()
        self.assertEqual(register.call_args.args[1:], ("eventos", date(2026, 9, 29), date(2026, 10, 20), 12))
        self.assertEqual([c[0] for c in self.calls.mock_calls], [
            "executar_carga_eventos", "executar_transformacao_eventos", "carregar_dim_deputado",
            "carregar_dim_orgao", "registrar_execucao", "atualizar_api"
        ])

    def test_falha_no_schema_api_nao_registra_incremental(self):
        self.stages["atualizar_api"].side_effect = RuntimeError("lock timeout")
        with self.assertRaisesRegex(RuntimeError, "lock timeout"):
            pipeline_pautas.executar_pipeline_pautas()
        self.assertEqual([c.args[1] for c in self.stages["registrar_execucao"].call_args_list], ["eventos"])

    def test_failed_stage_does_not_register_success(self):
        for name in ["executar_carga_eventos", "executar_transformacao_eventos", "carregar_dim_deputado", "carregar_dim_orgao"]:
            with self.subTest(stage=name):
                self.stages[name].side_effect = RuntimeError("refresh failed")
                with self.assertRaisesRegex(RuntimeError, "refresh failed"):
                    pipeline_pautas.executar_pipeline_pautas()
                self.stages["registrar_execucao"].assert_not_called()
                self.stages["atualizar_api"].assert_not_called()
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


class InclusaoTests(unittest.TestCase):
    def test_carrega_so_acompanhadas_ausentes_sem_registrar_janela(self):
        conn = MagicMock()
        with patch.object(pipeline_inclusao, "get_connection", return_value=conn), patch.object(
            pipeline_inclusao, "carregar_ids_acompanhadas", return_value=[1, 2, 3]
        ), patch.object(
            pipeline_inclusao, "carregar_ids_existentes", side_effect=[{1, 3}, {1, 2, 3}]
        ), patch.object(
            pipeline_inclusao, "carregar_ids", return_value=([2], 0)
        ) as carregar, patch.object(pipeline_inclusao, "executar_transformacao_silver") as silver, patch.object(
            pipeline_inclusao, "carregar_dim_deputado"
        ) as dep, patch.object(pipeline_inclusao, "carregar_dim_orgao") as orgao, patch.object(
            pipeline_inclusao, "atualizar_api"
        ) as api:
            pipeline_inclusao.executar_pipeline_inclusao()
        api.assert_called_once()
        carregar.assert_called_once_with([2], levantar_erro=False)
        silver.assert_called_once()
        dep.assert_called_once_with(seletivo=True, ids_proposicao=[2])
        orgao.assert_called_once()
        self.assertFalse(hasattr(pipeline_inclusao, "registrar_execucao"))

    def rodar(self, ausentes, erros, existentes_depois=()):
        with patch.object(pipeline_inclusao, "get_connection"), patch.object(
            pipeline_inclusao, "carregar_ids_acompanhadas", return_value=ausentes
        ), patch.object(
            pipeline_inclusao, "carregar_ids_existentes", side_effect=[set(), set(existentes_depois)]
        ), patch.object(
            pipeline_inclusao, "carregar_ids", return_value=(ausentes, erros)
        ), patch.object(pipeline_inclusao, "executar_transformacao_silver") as silver, patch.object(
            pipeline_inclusao, "carregar_dim_deputado"
        ), patch.object(pipeline_inclusao, "carregar_dim_orgao"), patch.object(pipeline_inclusao, "atualizar_api"):
            pipeline_inclusao.executar_pipeline_inclusao()
        return silver

    def test_id_invalido_nao_bloqueia_as_demais(self):
        # 2 proposições, 4 endpoints com erro (uma inteira falhou): segue para a silver
        self.rodar([2, 3], 4, existentes_depois={3}).assert_called_once()

    def test_falha_total_interrompe_antes_da_silver(self):
        with self.assertRaisesRegex(RuntimeError, "Nenhuma proposição"):
            self.rodar([2], 4)


class GoldSqlTests(unittest.TestCase):
    SQL_DIR = Path(__file__).resolve().parents[1] / "sql"

    def view(self, nome):
        sql = re.sub(r"--[^\n]*", "", (self.SQL_DIR / "schema_gold.sql").read_text(encoding="utf-8"))
        return re.search(rf"CREATE OR REPLACE VIEW gold\.{nome} AS(.*?);", sql, re.S).group(1)

    def test_monitoramento_inclui_acompanhadas_e_radar_com_corte(self):
        v = self.view("vw_monitoramento")
        self.assertIn("LEFT JOIN gold.vw_proposicao_keywords kw", v)
        # acompanhada pelo grupo do projeto (as duas casas), calculada em vw_grupo_projeto
        self.assertIn("WHERE kw.id_proposicao IS NOT NULL OR g.grupo_acompanhado", v)
        self.assertIn("coalesce(p.data_apresentacao_origem, p.data_apresentacao) >= DATE '2026-09-01'", v)
        self.assertNotIn("UNION", v)
        # colunas novas só no fim (CREATE OR REPLACE VIEW não aceita reordenar)
        select = v.split("FROM silver.proposicao p")[0]
        self.assertLess(select.index("nome_orgao_atual"), select.index("AS acompanhada"))
        self.assertLess(select.index("AS acompanhada"), select.index("AS em_radar"))
        # depois de em_radar, só colunas acrescentadas no fim (tipo e apresentação, para o BI;
        # casa e grupo do projeto, para o Senado)
        self.assertTrue(select.rstrip().endswith("ids_vinculados"))

    def test_pautas_expoem_filtros_no_fim(self):
        select = self.view("vw_pautas_monitoradas").split("FROM silver.evento_pauta")[0]
        self.assertTrue(select.rstrip().endswith("chave_projeto"))
        self.assertLess(select.index("m.em_radar"), select.index("casa"))
        self.assertLess(select.index("e.nome_orgao"), select.index("m.id_proposicao"))

    def test_movimentacoes_usa_marca_do_alerta_e_limite_de_30_dias(self):
        v = self.view("vw_movimentacoes")
        self.assertIn("tipo_carga = 'alerta_movimentacoes'", v)
        self.assertIn("t.data_extracao >", v)
        self.assertIn("t.data_hora >= current_date - 30", v)
        self.assertIn("eh_relator", v)

    def test_seed_idempotente_aplicada_antes_da_gold(self):
        seed = (self.SQL_DIR / "seed_acompanhadas.sql").read_text(encoding="utf-8")
        self.assertIn("ON CONFLICT (id_proposicao) DO NOTHING", seed)
        self.assertGreaterEqual(len(re.findall(r"\(\d+, 'planilha_antiga'", seed)), 50)
        fonte = Path(setup_db.__file__).read_text(encoding="utf-8")
        self.assertLess(fonte.index("schema_silver.sql"), fonte.index("seed_acompanhadas.sql"))
        self.assertLess(fonte.index("seed_acompanhadas.sql"), fonte.index("schema_gold.sql"))

    def test_api_derrubado_antes_da_gold_e_recriado_depois(self):
        fonte = Path(setup_db.__file__).read_text(encoding="utf-8")
        ordem = [fonte.index(f'apply_sql_file(cur, "{nome}")') for nome in ("drop_api.sql", "schema_gold.sql", "schema_api.sql")]
        self.assertEqual(ordem, sorted(ordem))

    def test_api_expoe_so_views_finas_com_relogio_na_leitura(self):
        sql = re.sub(r"--[^\n]*", "", (self.SQL_DIR / "schema_api.sql").read_text(encoding="utf-8"))
        cache = re.findall(r"CREATE MATERIALIZED VIEW api_cache\.(\w+)", sql)
        self.assertEqual(sorted(cache), sorted(load_api.MATERIALIZADAS))
        # vw_ultima_carga é a única sem cache: lê bronze.controle_execucao direto
        self.assertEqual(sorted(re.findall(r"CREATE VIEW api\.(\w+)", sql)), sorted(cache + ["vw_ultima_carga"]))
        # índice único em todas: exigido pelo REFRESH ... CONCURRENTLY
        self.assertEqual(sorted(re.findall(r"CREATE UNIQUE INDEX ON api_cache\.(\w+)", sql)), sorted(cache))
        # nada que dependa do relógio congelado no cache
        for bloco in re.findall(r"CREATE MATERIALIZED VIEW.*?;", sql, re.S):
            self.assertNotRegex(bloco, r"now\(\)|CURRENT_DATE|dias_sem_movimentacao|status_alerta")
        self.assertIn("GRANT SELECT ON ALL TABLES IN SCHEMA api TO anon", sql)
        self.assertNotRegex(sql, r"GRANT[^;]*api_cache[^;]*anon")
        # chave anon é pública (modelo do Power BI no repositório): gold só para leitura
        self.assertRegex(sql, r"REVOKE INSERT, UPDATE, DELETE, TRUNCATE[^;]*ON ALL TABLES IN SCHEMA gold FROM anon")
        self.assertRegex(sql, r"ALTER DEFAULT PRIVILEGES[^;]*IN SCHEMA gold\s+REVOKE INSERT[^;]*FROM anon")
        # tramitações filtradas pelo cache, atualizado antes na mesma transação
        self.assertLess(load_api.MATERIALIZADAS.index("vw_monitoramento"), load_api.MATERIALIZADAS.index("vw_tramitacoes"))

    def test_relogio_em_horario_de_brasilia(self):
        # sessão UTC × horários da Câmara sem fuso: now()/CURRENT_DATE puros erram 3 h
        for arquivo in ("schema_gold.sql", "schema_api.sql"):
            sql = re.sub(r"--[^\n]*", "", (self.SQL_DIR / arquivo).read_text(encoding="utf-8"))
            self.assertNotRegex(sql, r"data_hora_inicio > now\(\)|CURRENT_DATE - (p\.)?data_ultima")
            self.assertIn("data_hora_inicio > (now() AT TIME ZONE 'America/Sao_Paulo')", sql)

    def test_status_cancelada_primeiro_e_igual_na_gold_e_no_api(self):
        def casos(arquivo):
            sql = re.sub(r"--[^\n]*", "", (self.SQL_DIR / arquivo).read_text(encoding="utf-8"))
            # o CASE mais próximo do alias (há outros CASE antes no arquivo)
            blocos = re.findall(r"CASE((?:(?!CASE).)*?)END AS status_alerta", sql, re.S)
            # sem alias de tabela e sem espaços, para comparar a regra e não a formatação
            return [re.sub(r"\s+", " ", re.sub(r"\b(e|ep|m)\.", "", b)).replace("situacao_evento", "situacao").strip()
                    for b in blocos]
        gold, api = casos("schema_gold.sql"), casos("schema_api.sql")
        self.assertEqual(len(gold), 2)
        self.assertEqual(gold, api)
        for bloco in gold:
            self.assertTrue(bloco.startswith(
                "WHEN situacao = 'Cancelada' THEN 'Cancelada' WHEN situacao = 'Adiada' THEN 'Adiada'"), bloco)

    def test_refresh_concorrente_numa_transacao(self):
        conn = MagicMock()
        with patch.object(load_api, "get_connection", return_value=conn):
            load_api.atualizar_api()
        cur = conn.__enter__.return_value.cursor.return_value.__enter__.return_value
        sqls = [c.args[0] for c in cur.execute.call_args_list]
        self.assertEqual(len(sqls), len(load_api.MATERIALIZADAS))
        self.assertTrue(all(s.startswith("REFRESH MATERIALIZED VIEW CONCURRENTLY api_cache.") for s in sqls))
        conn.__enter__.return_value.commit.assert_called_once()

    def test_destaque_so_para_designacao_de_relator(self):
        # calculado na silver (cada casa escreve a designação de um jeito)
        self.assertIn("t.eh_relator", self.view("vw_movimentacoes"))

    def test_ambiente_exige_tabela_e_view_novas(self):
        self.assertIn("silver.proposicao_acompanhada", check_environment.REQUIRED_RELATIONS)
        self.assertIn("gold.vw_movimentacoes", check_environment.REQUIRED_RELATIONS)
        self.assertIn("api.vw_tramitacoes", check_environment.REQUIRED_RELATIONS)


class WorkflowYamlTests(unittest.TestCase):
    def test_aviso_de_falha_so_quando_a_carga_falha_e_timeout_vira_falha(self):
        yml = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "pipeline.yml").read_text(encoding="utf-8")
        self.assertIn("id: carga", yml)
        self.assertIn("if: ${{ failure() && steps.carga.outcome == 'failure' }}", yml)
        passo = int(re.search(r"id: carga[\s\S]*?timeout-minutes: (\d+)", yml).group(1))
        job = int(re.search(r"^    timeout-minutes: (\d+)", yml, re.M).group(1))
        self.assertLess(passo, job)
        self.assertIn("inclusao) python src/pipeline_inclusao.py", yml)


class SilverSqlTests(unittest.TestCase):
    def test_filhos_ignoram_proposicao_ausente_na_silver(self):
        sql_path = Path(__file__).resolve().parents[1] / "sql" / "transform_bronze_to_silver.sql"
        sql = re.sub(r"--[^\n]*", "", sql_path.read_text(encoding="utf-8"))
        comandos = {re.search(r"INSERT INTO (\S+)", c).group(1): c for c in sql.split(";") if "INSERT INTO" in c}
        guarda = "WHERE EXISTS (SELECT 1 FROM silver.proposicao p WHERE p.id_proposicao = b.id_proposicao)"
        for tabela in ("silver.proposicoes_proponentes", "silver.proposicao_tema", "silver.tramitacao"):
            self.assertIn(guarda, comandos[tabela], tabela)


if __name__ == "__main__":
    unittest.main()
