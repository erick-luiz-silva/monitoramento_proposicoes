"""Testes de SQL contra um Postgres real e descartável (sem credenciais reais).

Pulam sem TEST_DATABASE_URL. Localmente: eval "$(scripts/postgres_teste.sh)". Em CI, service postgres:17.
Cada teste recebe um banco limpo (schemas derrubados) com setup_db.aplicar_schemas aplicado.
"""

import os
import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

SCHEMAS = ("api", "api_cache", "gold", "silver", "bronze", "gestao", "contrato")


def _validar_destino():
    """Os testes derrubam schemas: só rodam em banco local e nunca em produção/homologação."""
    from urllib.parse import urlsplit

    host = urlsplit(TEST_DATABASE_URL).hostname
    if host not in ("localhost", "127.0.0.1"):
        raise RuntimeError("TEST_DATABASE_URL precisa apontar para localhost/127.0.0.1.")
    for nome in ("DATABASE_URL", "DATABASE_URL_HOMOLOGACAO"):
        if os.getenv(nome) and os.getenv(nome) == TEST_DATABASE_URL:
            raise RuntimeError(f"TEST_DATABASE_URL não pode ser igual a {nome}.")


def conectar():
    _validar_destino()
    import psycopg2

    return psycopg2.connect(TEST_DATABASE_URL)


def criar_banco_limpo(cur):
    """Derruba os schemas do projeto e reaplica tudo. Ponto de extensão para as próximas camadas."""
    for esquema in SCHEMAS:
        cur.execute(f"DROP SCHEMA IF EXISTS {esquema} CASCADE;")
    from setup_db import aplicar_schemas

    aplicar_schemas(cur)


@unittest.skipUnless(TEST_DATABASE_URL, "TEST_DATABASE_URL não definida")
class BancoLimpoTests(unittest.TestCase):
    def setUp(self):
        self.conn = conectar()
        self.cur = self.conn.cursor()
        criar_banco_limpo(self.cur)
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_schemas_existem(self):
        self.cur.execute("SELECT nspname FROM pg_namespace WHERE nspname = ANY(%s)", (["bronze", "silver", "gold", "api", "api_cache"],))
        self.assertEqual({l[0] for l in self.cur.fetchall()}, {"bronze", "silver", "gold", "api", "api_cache"})

    def test_aplicar_schemas_e_idempotente(self):
        from setup_db import aplicar_schemas

        aplicar_schemas(self.cur)
        self.conn.commit()

    def test_gestao_sobrevive_a_novo_setup(self):
        from setup_db import aplicar_schemas

        self.cur.execute("INSERT INTO gestao.projeto (uuid) VALUES ('00000000-0000-0000-0000-000000000001')")
        self.cur.execute("INSERT INTO gestao.decisao_projeto (uuid_projeto, relevancia, prioridade) VALUES ('00000000-0000-0000-0000-000000000001', 'SIM', true)")
        self.conn.commit()
        aplicar_schemas(self.cur)
        self.conn.commit()
        self.cur.execute("SELECT relevancia, prioridade FROM gestao.decisao_projeto")
        self.assertEqual(self.cur.fetchall(), [("SIM", True)])
        self.cur.execute("SELECT count(*) FROM gestao.situacao_encerramento")
        self.assertEqual(self.cur.fetchone()[0], 6)

    def test_historico_imutavel(self):
        import psycopg2

        self.cur.execute("INSERT INTO gestao.projeto (uuid) VALUES ('00000000-0000-0000-0000-000000000001')")
        self.cur.execute("INSERT INTO gestao.historico_alteracao (uuid_projeto, operacao, origem) VALUES ('00000000-0000-0000-0000-000000000001', 'criar', 'aplicacao')")
        self.conn.commit()
        for comando in ("UPDATE gestao.historico_alteracao SET operacao = 'x'", "DELETE FROM gestao.historico_alteracao", "TRUNCATE gestao.historico_alteracao"):
            with self.assertRaises(psycopg2.Error, msg=comando):
                self.cur.execute(comando)
            self.conn.rollback()
        self.cur.execute("SELECT count(*) FROM gestao.historico_alteracao")
        self.assertEqual(self.cur.fetchone()[0], 1)

    def test_anon_sem_acesso_a_gestao(self):
        import psycopg2

        self.cur.execute("SET ROLE anon")
        with self.assertRaises(psycopg2.errors.InsufficientPrivilege):
            self.cur.execute("SELECT * FROM gestao.projeto")
        self.conn.rollback()
        for papel in ("anon", "authenticated"):
            self.cur.execute("SELECT has_table_privilege(%s, 'gestao.projeto', 'SELECT')", (papel,))
            self.assertFalse(self.cur.fetchone()[0], papel)

    def test_prioridade_exige_relevancia_sim(self):
        import psycopg2

        self.cur.execute("INSERT INTO gestao.projeto (uuid) VALUES ('00000000-0000-0000-0000-000000000001')")
        with self.assertRaises(psycopg2.errors.CheckViolation):
            self.cur.execute("INSERT INTO gestao.decisao_projeto (uuid_projeto, relevancia, prioridade) VALUES ('00000000-0000-0000-0000-000000000001', 'NAO', true)")
        self.conn.rollback()
        # relevância pendente (NULL) também não admite prioridade
        with self.assertRaises(psycopg2.errors.CheckViolation):
            self.cur.execute("INSERT INTO gestao.decisao_projeto (uuid_projeto, relevancia, prioridade) VALUES ('00000000-0000-0000-0000-000000000001', NULL, true)")
        self.conn.rollback()

    def test_unaccent_disponivel(self):
        self.cur.execute("SELECT extensions.unaccent('suínos')")
        self.assertEqual(self.cur.fetchone()[0], "suinos")



FIXTURE_GESTAO = Path(__file__).resolve().parent / "fixtures" / "gestao" / "silver_sintetica.sql"
ATOR = "00000000-0000-0000-0000-0000000000aa"
FUNCOES_APP = (
    "gestao.confirmar_movimentacoes(uuid, jsonb, uuid, text)",
    "gestao.salvar_decisao(uuid, bigint, int, jsonb, uuid, text)",
    "gestao.avaliar(bigint, text, int, uuid, text)",
    "gestao.desfazer_avaliacao(bigint, uuid, text)",
    "gestao.solicitar_inclusao(text, text, uuid, text)",
    "gestao.tentar_inclusao_agora(bigint, uuid, text)",
)
FUNCOES_INTERNAS = (
    "gestao.gravar_decisao(uuid, bigint, int, jsonb, uuid, text, text)",
    "gestao.registrar_inclusao_resolvida(bigint, bigint)",
    "gestao.concluir_inclusoes()",
    "gestao.falhar_inclusao(bigint, text, boolean)",
)
COLUNAS_PAINEL = ["id_proposicao", "casa", "uuid_projeto", "relevancia", "posicao", "prioridade", "em_carteira"]


def uuid_teste(n):
    return f"00000000-0000-0000-0000-{n:012d}"


class _ComDados(unittest.TestCase):
    """Banco limpo + silver sintética + cache atualizado (como no fim de uma carga)."""

    def setUp(self):
        self.conn = conectar()
        self.cur = self.conn.cursor()
        criar_banco_limpo(self.cur)
        self.cur.execute(FIXTURE_GESTAO.read_text(encoding="utf-8"))
        self.atualizar_cache()
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def atualizar_cache(self):
        import load_api

        load_api.atualizar_cache(self.cur)

    def decidir(self, uuid, ids, relevancia=None, prioridade=None, posicao=None):
        """Decisão gravada direto nas tabelas (como a migração), para montar cenários."""
        self.cur.execute("INSERT INTO gestao.projeto (uuid) VALUES (%s) ON CONFLICT DO NOTHING", (uuid,))
        for id_prop in ids:
            self.cur.execute(
                "INSERT INTO gestao.projeto_proposicao (id_proposicao, uuid_projeto, origem) VALUES (%s, %s, 'migracao')",
                (id_prop, uuid))
        self.cur.execute(
            "INSERT INTO gestao.decisao_projeto (uuid_projeto, relevancia, prioridade, posicao) VALUES (%s, %s, %s, %s)",
            (uuid, relevancia, prioridade, posicao))

    def projeto(self, id_proposicao, *colunas):
        self.cur.execute(
            f"SELECT {', '.join(colunas)} FROM contrato.vw_projeto WHERE %s = ANY(ids_proposicao)", (id_proposicao,))
        linhas = self.cur.fetchall()
        self.assertEqual(len(linhas), 1, f"projeto de {id_proposicao}")
        return linhas[0] if len(colunas) > 1 else linhas[0][0]

    def chamar(self, funcao, *args):
        from psycopg2.extras import Json

        args = [Json(a) if isinstance(a, dict) else a for a in args]
        self.cur.execute(f"SELECT {funcao}({', '.join(['%s'] * len(args))})", args)
        return self.cur.fetchone()[0]

    def assertErroDominio(self, mensagem, funcao, *args):
        import psycopg2

        with self.assertRaises(psycopg2.Error) as ctx:
            self.chamar(funcao, *args)
        self.conn.rollback()
        self.assertEqual(ctx.exception.pgcode, "P0001")
        self.assertEqual(ctx.exception.diag.message_primary, mensagem)

    def contar(self, sql, *params):
        self.cur.execute(sql, params)
        return self.cur.fetchone()[0]


@unittest.skipUnless(TEST_DATABASE_URL, "TEST_DATABASE_URL não definida")
class ContratosTests(_ComDados):
    def test_corte_de_12_meses_e_elegibilidade(self):
        # CA04: prioridade antiga continua ativa; parado sai; volta com movimento recente
        self.decidir(uuid_teste(1), [900001], "SIM", True)
        self.decidir(uuid_teste(2), [900002], "SIM")
        self.decidir(uuid_teste(3), [900003], "SIM")
        self.decidir(uuid_teste(4), [900004], "NAO")
        cols = ("elegivel", "em_carteira", "motivo_historico")
        self.assertEqual(self.projeto(900001, *cols), (True, True, None))
        self.assertEqual(self.projeto(900002, *cols), (True, False, "parado há mais de 12 meses"))
        self.assertEqual(self.projeto(900003, *cols), (True, False, "sem data"))
        self.assertEqual(self.projeto(900004, *cols), (False, False, "marcado NÃO"))
        # acompanhada sem decisão é elegível pelo acompanhamento; keyword antiga sem decisão não aparece
        self.assertEqual(self.projeto(900032, "uuid_projeto", "em_carteira"), (None, True))
        self.assertEqual(self.projeto(900033, *cols, "pendente_avaliacao"), (False, False, None, False))

        self.cur.execute("UPDATE silver.proposicao SET data_ultima_movimentacao = (now() AT TIME ZONE 'America/Sao_Paulo') - interval '1 day' WHERE id_proposicao = 900002")
        self.atualizar_cache()
        self.cur.execute(f"UPDATE gestao.decisao_projeto SET prioridade = true WHERE uuid_projeto = '{uuid_teste(3)}'")
        self.assertEqual(self.projeto(900002, *cols), (True, True, None))
        self.assertEqual(self.projeto(900003, *cols), (True, True, None))  # prioridade sem data fica ativa

    def test_encerramento_entre_casas(self):
        # sem UUID nem acompanhamento: remessa/divergência não poluem a lista do mantenedor
        self.assertFalse(self.projeto(900007, "a_conferir"))
        self.decidir(uuid_teste(5), [900005, 1990000005], "SIM")
        self.decidir(uuid_teste(6), [900006], "SIM", True)
        self.decidir(uuid_teste(16), [1990000016], "SIM")
        self.decidir(uuid_teste(7), [900007], "NAO")  # conferência independe de relevância/elegibilidade
        self.decidir(uuid_teste(8), [900008, 1990000008], "SIM")
        cols = ("encerrado", "em_carteira", "motivo_historico", "motivos_conferencia")
        # CA05: versão arquivada não esconde a versão ativa da outra casa
        self.assertEqual(self.projeto(900005, *cols), (False, True, None, []))
        # efetivamente encerrado vai ao histórico, mesmo prioritário
        self.assertEqual(self.projeto(900006, *cols), (True, False, "encerrado", []))
        # Senado casa por texto, sem caixa nem acento
        self.assertEqual(self.projeto(1990000016, *cols), (True, False, "encerrado", []))
        self.assertEqual(self.projeto(900007, *cols), (False, False, "marcado NÃO", ["remessa sem a versão da outra casa carregada"]))
        self.assertEqual(self.projeto(900008, *cols), (False, True, None, ["encerramento divergente entre as versões"]))
        self.cur.execute("SELECT uuid_projeto::text, motivo FROM contrato.vw_conferencia ORDER BY 1")
        self.assertEqual(self.cur.fetchall(), [
            (uuid_teste(7), "remessa sem a versão da outra casa carregada"),
            (uuid_teste(8), "encerramento divergente entre as versões")])

    def test_associacao_pelo_grupo_e_alias(self):
        self.decidir(uuid_teste(11), [900011], "SIM")
        self.cur.execute("SELECT id_proposicao, uuid_projeto::text, chave_agrupamento, associada FROM contrato.vw_versao WHERE chave_projeto = 900011 ORDER BY 1")
        self.assertEqual(self.cur.fetchall(), [
            (900011, uuid_teste(11), uuid_teste(11), True),
            (1990000011, uuid_teste(11), uuid_teste(11), False)])  # inequívoca: associada na leitura
        self.assertEqual(self.projeto(900011, "ids_proposicao", "relevancia"), ([900011, 1990000011], "SIM"))
        # sem UUID: chave derivada 'k' || chave_projeto
        self.assertEqual(self.projeto(900021, "chave_agrupamento", "uuid_projeto", "revisao"), ("k900021", None, 0))
        # alias da reconciliação: segue substituido_por
        self.decidir(uuid_teste(15), [], "SIM")
        self.decidir(uuid_teste(14), [900014], "NAO")
        self.cur.execute(f"UPDATE gestao.projeto SET substituido_por = '{uuid_teste(15)}' WHERE uuid = '{uuid_teste(14)}'")
        self.assertEqual(self.projeto(900014, "uuid_projeto::text", "relevancia"), (uuid_teste(15), "SIM"))

    def test_conferencia_de_uuids_divergentes(self):
        # CA14: UUIDs diferentes no mesmo grupo; UUID com versões em grupos diferentes
        self.decidir(uuid_teste(12), [900012], "SIM", True)
        self.decidir(uuid_teste(13), [1990000012], "NAO")
        self.decidir(uuid_teste(20), [900013, 1990000013], "SIM")
        self.cur.execute("SELECT uuid_projeto::text, ids_proposicao, relevancia, motivos_conferencia FROM contrato.vw_projeto WHERE a_conferir ORDER BY 1")
        self.assertEqual(self.cur.fetchall(), [
            (uuid_teste(12), [900012], "SIM", ["versões do grupo com projetos diferentes"]),
            (uuid_teste(13), [1990000012], "NAO", ["versões do grupo com projetos diferentes"]),
            (uuid_teste(20), [900013, 1990000013], "SIM", ["projeto com versões em grupos diferentes"])])

    def test_vinculo_novo_entre_projetos_nao_funde_decisoes(self):
        self.decidir(uuid_teste(11), [900011], "SIM", True, "A favor")
        self.decidir(uuid_teste(12), [900012], "NAO", None, "Contra")
        self.conn.commit()
        # o pipeline liga os dois grupos (vínculo novo): nada é fundido, tudo vai à conferência
        self.cur.execute("INSERT INTO silver.proposicao_vinculo VALUES (900012, 1990000011, 'revisora')")
        self.atualizar_cache()
        self.conn.commit()
        self.cur.execute("SELECT chave_agrupamento, relevancia, posicao, a_conferir FROM contrato.vw_projeto WHERE 900011 = ANY(chaves_projeto) ORDER BY 1")
        self.assertEqual(self.cur.fetchall(), [
            (uuid_teste(11), "SIM", "A favor", True),
            (uuid_teste(12), "NAO", "Contra", True),
            ("k900011", None, None, True)])  # versões sem associação não escolhem lado
        self.assertErroDominio("projeto_a_conferir", "gestao.salvar_decisao", None, 1990000011, 0, {"relevancia": "SIM"}, ATOR, "Ana")
        # editar pela versão associada vale só para o seu UUID e não puxa as versões soltas do grupo
        r = self.chamar("gestao.salvar_decisao", None, 900011, 1, {"acao": "Conferir vínculo"}, ATOR, "Ana")
        self.assertEqual((r["uuid_projeto"], r["revisao"]), (uuid_teste(11), 2))
        self.assertEqual(self.contar("SELECT count(*) FROM gestao.projeto_proposicao WHERE id_proposicao >= 1000000000"), 0)
        self.conn.rollback()
        self.cur.execute("SELECT uuid_projeto::text, relevancia, prioridade, revisao FROM gestao.decisao_projeto ORDER BY 1")
        self.assertEqual(self.cur.fetchall(), [(uuid_teste(11), "SIM", True, 1), (uuid_teste(12), "NAO", None, 1)])

    def test_urgencia_por_pauta(self):
        self.decidir(uuid_teste(9), [900009], "SIM")
        self.assertFalse(self.projeto(900009, "urgente_pauta"))  # sem prioridade
        self.cur.execute(f"UPDATE gestao.decisao_projeto SET prioridade = true WHERE uuid_projeto = '{uuid_teste(9)}'")
        urgente, quando, orgao = self.projeto(900009, "urgente_pauta", "proxima_pauta_em", "proxima_pauta_orgao")
        self.assertTrue(urgente)
        self.assertEqual(orgao, "CAPADR")
        self.assertEqual(quando.hour, 10)
        hoje = "(now() AT TIME ZONE 'America/Sao_Paulo')::date"
        casos = [
            ("Adiada", f"{hoje} + 3 + time '10:00'", False),
            ("Cancelada", f"{hoje} + 3 + time '10:00'", False),
            ("Convocada", f"({hoje} + 15)::timestamp", False),       # fim exclusivo
            ("Convocada", f"({hoje} + 15)::timestamp - interval '1 minute'", True),
            ("Convocada", f"{hoje}::timestamp", True),               # início de hoje, inclusivo
            (None, f"{hoje} + 3 + time '10:00'", False),             # sem status não é agendada
            ("Encerrada", f"{hoje} + 3 + time '10:00'", False),
            ("Encerrada (Final)", f"{hoje} + 3 + time '10:00'", False),
            ("Realizada", f"{hoje} + 3 + time '10:00'", False),
            ("Convocada", f"{hoje}::timestamp - interval '1 minute'", False),
        ]
        for situacao, inicio, esperado in casos:
            self.cur.execute(f"UPDATE silver.evento SET situacao = %s, data_hora_inicio = {inicio} WHERE id_evento = 9100001", (situacao,))
            self.atualizar_cache()
            self.assertEqual(self.projeto(900009, "urgente_pauta"), esperado, (situacao, inicio))
        # pauta da vw_pauta com o status na leitura
        self.cur.execute("SELECT chave_agrupamento, status_alerta FROM contrato.vw_pauta")
        self.assertEqual(self.cur.fetchall(), [(uuid_teste(9), "Encerrado sem votação")])

    def test_conferencia_suspende_urgencia(self):
        self.decidir(uuid_teste(9), [900009], "SIM", True)
        self.assertTrue(self.projeto(900009, "urgente_pauta"))
        # a versão passa a "remessa" sem a outra casa carregada: vai à conferência, sem urgência automática
        self.cur.execute("UPDATE silver.proposicao SET cod_situacao = 926 WHERE id_proposicao = 900009")
        self.atualizar_cache()
        self.assertEqual(self.projeto(900009, "a_conferir", "urgente_pauta", "em_carteira"), (True, False, True))

    def test_agenda_futura_nao_aplica_corte(self):
        # RN06: elegível, sem prioridade, parado há 2 anos, com pauta agendada daqui a 40 dias → Ativas
        self.decidir(uuid_teste(2), [900002], "SIM")
        self.assertFalse(self.projeto(900002, "em_carteira"))
        self.cur.execute("""INSERT INTO silver.evento (id_evento, data_hora_inicio, descricao_tipo, situacao, sigla_orgao)
            SELECT 9100002, (now() AT TIME ZONE 'America/Sao_Paulo')::date + 40 + time '14:00', 'Reunião Deliberativa', 'Convocada', 'CCJC'""")
        self.cur.execute("INSERT INTO silver.evento_pauta (id_evento, ordem, id_proposicao, votado) VALUES (9100002, 1, 900002, false)")
        self.atualizar_cache()
        self.assertEqual(self.projeto(900002, "em_carteira", "motivo_historico", "urgente_pauta", "proxima_pauta_orgao"),
                         (True, None, False, "CCJC"))
        # reunião que não está agendada (encerrada) não segura o projeto nas Ativas
        self.cur.execute("UPDATE silver.evento SET situacao = 'Encerrada' WHERE id_evento = 9100002")
        self.atualizar_cache()
        self.assertEqual(self.projeto(900002, "em_carteira", "motivo_historico"), (False, "parado há mais de 12 meses"))

    def test_fila_de_avaliacao(self):
        self.assertEqual(self.projeto(900031, "pendente_avaliacao", "em_carteira", "id_proposicao_recente"), (True, False, 900031))
        self.assertFalse(self.projeto(900032, "pendente_avaliacao"))  # acompanhada: elegível, não pendente
        self.assertFalse(self.projeto(900033, "pendente_avaliacao"))  # fora do radar
        resultado = self.chamar("gestao.avaliar", 900031, "SIM", 0, ATOR, "Ana")
        self.assertEqual((resultado["relevancia"], resultado["revisao"], resultado["criado"]), ("SIM", 1, True))
        self.assertEqual(self.projeto(900031, "pendente_avaliacao", "em_carteira"), (False, True))

    def test_frescor(self):
        self.cur.execute("INSERT INTO bronze.controle_execucao (tipo_carga, data_inicio_janela, data_fim_janela, executado_em) VALUES ('incremental', current_date, current_date, now() + interval '1 minute'), ('incremental_senado', current_date, current_date, now())")
        self.cur.execute("SELECT falha_diaria, falha_senado, falha_api FROM contrato.vw_frescor")
        self.assertEqual(self.cur.fetchone(), (False, False, True))  # cache anterior à carga diária
        self.conn.commit()
        self.atualizar_cache()
        self.cur.execute("UPDATE bronze.controle_execucao SET executado_em = now() + interval '2 minutes' WHERE tipo_carga = 'atualizacao_api' AND executado_em = now()")
        self.cur.execute("SELECT falha_api, ultima_atualizacao_api IS NOT NULL FROM contrato.vw_frescor")
        self.assertEqual(self.cur.fetchone(), (False, True))
        self.cur.execute("SELECT ultima_atualizacao_api IS NOT NULL FROM api.vw_ultima_carga")
        self.assertTrue(self.cur.fetchone()[0])


@unittest.skipUnless(TEST_DATABASE_URL, "TEST_DATABASE_URL não definida")
class FuncoesGestaoTests(_ComDados):
    def test_primeira_decisao_cria_uuid_associa_grupo_e_audita(self):
        r = self.chamar("gestao.salvar_decisao", None, 900021, 0, {"relevancia": "SIM", "posicao": "A favor"}, ATOR, "Ana")
        self.assertTrue(r["criado"])
        self.assertEqual((r["revisao"], r["relevancia"], r["posicao"], r["prioridade"]), (1, "SIM", "A favor", None))
        self.cur.execute("SELECT id_proposicao, uuid_projeto::text, origem FROM gestao.projeto_proposicao ORDER BY 1")
        self.assertEqual(self.cur.fetchall(), [(900021, r["uuid_projeto"], "aplicacao"), (1990000021, r["uuid_projeto"], "aplicacao")])
        self.cur.execute("SELECT operacao, diferencas, origem, ator_id::text, ator_nome, revisao FROM gestao.historico_alteracao")
        self.assertEqual(self.cur.fetchall(), [("salvar_decisao", {
            "relevancia": {"de": None, "para": "SIM"}, "posicao": {"de": None, "para": "A favor"}},
            "aplicacao", ATOR, "Ana", 1)])
        self.assertEqual(self.projeto(900021, "uuid_projeto::text", "revisao", "em_carteira"), (r["uuid_projeto"], 1, True))

    def test_conflito_de_revisao_nao_grava_nada(self):
        # CA02
        r = self.chamar("gestao.salvar_decisao", None, 900021, 0, {"relevancia": "SIM"}, ATOR, "Ana")
        self.conn.commit()
        self.assertErroDominio("conflito_revisao", "gestao.salvar_decisao", None, 900021, 0, {"posicao": "Contra"}, ATOR, "Outra")
        self.assertErroDominio("conflito_revisao", "gestao.salvar_decisao", r["uuid_projeto"], None, 2, {"posicao": "Contra"}, ATOR, "Outra")
        self.assertEqual(self.contar("SELECT count(*) FROM gestao.historico_alteracao"), 1)
        self.assertEqual(self.contar("SELECT count(*) FROM gestao.projeto"), 1)
        r2 = self.chamar("gestao.salvar_decisao", r["uuid_projeto"], None, 1, {"acao": "Falar com o relator"}, ATOR, "Ana")
        self.assertEqual(r2["revisao"], 2)
        self.assertEqual(r2["diferencas"], {"acao": {"de": None, "para": "Falar com o relator"}})
        # sem mudança efetiva: nada gravado, revisão mantida
        r3 = self.chamar("gestao.salvar_decisao", r["uuid_projeto"], None, 2, {"acao": "Falar com o relator"}, ATOR, "Ana")
        self.assertEqual((r3["alterado"], r3["revisao"], r3["historico_id"]), (False, 2, None))
        self.assertEqual(self.contar("SELECT count(*) FROM gestao.historico_alteracao"), 2)

    def test_erro_no_meio_nao_deixa_rastro(self):
        self.assertErroDominio("posicao_invalida", "gestao.salvar_decisao", None, 900021, 0, {"relevancia": "SIM", "posicao": "Talvez"}, ATOR, "Ana")
        self.assertErroDominio("campo_invalido", "gestao.salvar_decisao", None, 900021, 0, {"parecer_x": "a"}, ATOR, "Ana")
        self.assertErroDominio("ator_obrigatorio", "gestao.salvar_decisao", None, 900021, 0, {"relevancia": "SIM"}, None, "Ana")
        self.assertErroDominio("proposicao_nao_encontrada", "gestao.salvar_decisao", None, 123, 0, {"relevancia": "SIM"}, ATOR, "Ana")
        for tabela in ("projeto", "projeto_proposicao", "decisao_projeto", "historico_alteracao"):
            self.assertEqual(self.contar(f"SELECT count(*) FROM gestao.{tabela}"), 0, tabela)

    def test_primeiras_decisoes_simultaneas_criam_um_so_projeto(self):
        import threading

        import psycopg2

        self.chamar("gestao.salvar_decisao", None, 900021, 0, {"relevancia": "SIM"}, ATOR, "Ana")  # transação aberta
        resultado = {}

        def outra_sessao():
            conn = conectar()
            try:
                # entra pela outra versão do mesmo grupo
                conn.cursor().execute("SELECT gestao.salvar_decisao(NULL, 1990000021, 0, '{\"relevancia\": \"NAO\"}', %s, 'Outra')", (ATOR,))
                conn.commit()
                resultado["ok"] = True
            except psycopg2.Error as erro:
                resultado["erro"] = erro.diag.message_primary
            finally:
                conn.close()

        t = threading.Thread(target=outra_sessao)
        t.start()
        t.join(1.5)
        self.assertTrue(t.is_alive(), "a segunda sessão deveria esperar a trava do grupo")
        self.conn.commit()
        t.join(10)
        self.assertEqual(resultado, {"erro": "conflito_revisao"})
        self.assertEqual(self.contar("SELECT count(*) FROM gestao.projeto"), 1)
        self.assertEqual(self.contar("SELECT count(*) FROM gestao.decisao_projeto WHERE relevancia = 'SIM'"), 1)

    def test_rn05_prioridade_e_nao(self):
        self.assertErroDominio("prioridade_exige_sim", "gestao.salvar_decisao", None, 900021, 0, {"prioridade": True}, ATOR, "Ana")
        r = self.chamar("gestao.salvar_decisao", None, 900021, 0, {"relevancia": "SIM", "prioridade": True}, ATOR, "Ana")
        self.conn.commit()
        self.assertEqual(self.contar("SELECT count(*) FROM gestao.decisao_projeto WHERE prioridade_desde IS NOT NULL"), 1)
        self.assertErroDominio("confirmar_retirada_prioridade", "gestao.salvar_decisao", r["uuid_projeto"], None, 1, {"relevancia": "NAO"}, ATOR, "Ana")
        self.assertErroDominio("prioridade_exige_sim", "gestao.salvar_decisao", r["uuid_projeto"], None, 1, {"relevancia": None}, ATOR, "Ana")
        r2 = self.chamar("gestao.salvar_decisao", r["uuid_projeto"], None, 1, {"relevancia": "NAO", "retirar_prioridade": True}, ATOR, "Ana")
        self.assertEqual((r2["relevancia"], r2["prioridade"], r2["revisao"]), ("NAO", False, 2))
        self.assertEqual(r2["diferencas"], {"relevancia": {"de": "SIM", "para": "NAO"}, "prioridade": {"de": True, "para": False}})
        self.assertEqual(self.contar("SELECT count(*) FROM gestao.decisao_projeto WHERE prioridade_desde IS NULL"), 1)

    def test_avaliar_e_desfazer(self):
        a = self.chamar("gestao.avaliar", 900031, "SIM", 0, ATOR, "Ana")
        self.conn.commit()
        d = self.chamar("gestao.desfazer_avaliacao", a["historico_id"], ATOR, "Ana")
        self.assertEqual((d["relevancia"], d["revisao"]), (None, 2))
        self.assertTrue(self.projeto(900031, "pendente_avaliacao"))  # voltou para a fila
        self.conn.commit()
        self.assertErroDominio("desfazer_recusado", "gestao.desfazer_avaliacao", a["historico_id"], ATOR, "Ana")
        # avaliação seguida de outra mudança: desfazer é recusado
        a2 = self.chamar("gestao.avaliar", 900031, "NAO", 2, ATOR, "Ana")
        self.chamar("gestao.salvar_decisao", a2["uuid_projeto"], None, 3, {"posicao": "Contra"}, ATOR, "Ana")
        self.conn.commit()
        self.assertErroDominio("desfazer_recusado", "gestao.desfazer_avaliacao", a2["historico_id"], ATOR, "Ana")
        self.assertErroDominio("desfazer_recusado", "gestao.desfazer_avaliacao", a2["historico_id"] + 1, ATOR, "Ana")  # não é avaliação
        self.assertErroDominio("relevancia_invalida", "gestao.avaliar", 900031, "TALVEZ", 4, ATOR, "Ana")

    def test_inclusao_duplicada_falha_e_retomada(self):
        # CA08
        p = self.chamar("gestao.solicitar_inclusao", "PL 99/2026", "CD:PL 99/2026", ATOR, "Ana")
        self.assertEqual((p["estado"], p["existente"]), ("solicitada", False))
        dup = self.chamar("gestao.solicitar_inclusao", "https://www.camara.leg.br/...", "CD:PL 99/2026", ATOR, "Ana")
        self.assertEqual((dup["id"], dup["existente"], dup["retomado"]), (p["id"], True, False))
        f = self.chamar("gestao.falhar_inclusao", p["id"], "Não encontrada na Câmara", False)
        self.assertEqual(f["estado"], "falhou")
        ret = self.chamar("gestao.solicitar_inclusao", "PL 99/2026", "CD:PL 99/2026", ATOR, "Ana")
        self.assertEqual((ret["id"], ret["estado"], ret["retomado"]), (p["id"], "solicitada", True))
        self.assertEqual(self.contar("SELECT count(*) FROM gestao.inclusao_manual"), 1)
        # falha temporária: nova tentativa espaçada; "Tentar agora" antecipa
        t = self.chamar("gestao.falhar_inclusao", p["id"], "Timeout", True)
        self.assertEqual((t["estado"], t["tentativas"]), ("solicitada", 1))
        self.assertIsNotNone(t["proxima_tentativa_em"])
        self.conn.commit()
        self.assertErroDominio("ator_obrigatorio", "gestao.tentar_inclusao_agora", p["id"], None, "Ana")
        self.chamar("gestao.falhar_inclusao", p["id"], "Timeout", True)
        self.assertTrue(self.chamar("gestao.tentar_inclusao_agora", p["id"], ATOR, "Bia")["alterado"])
        self.cur.execute("SELECT tentativas, retomado_por_id::text, retomado_por_nome, retomado_em IS NOT NULL FROM gestao.inclusao_manual")
        self.assertEqual(self.cur.fetchone(), (0, ATOR, "Bia", True))
        # resolvido: vira acompanhada do sistema e só conclui quando aparece no cache
        r = self.chamar("gestao.registrar_inclusao_resolvida", p["id"], 900099)
        self.assertEqual((r["estado"], r["ja_acompanhada"]), ("carregando", False))
        self.assertEqual(self.chamar("gestao.registrar_inclusao_resolvida", p["id"], 900099)["estado"], "carregando")  # idempotente
        self.cur.execute("SELECT origem FROM silver.proposicao_acompanhada WHERE id_proposicao = 900099")
        self.assertEqual(self.cur.fetchone()[0], "sistema")
        self.assertEqual(self.chamar("gestao.concluir_inclusoes")["concluidas"], 0)
        outro = self.chamar("gestao.solicitar_inclusao", "PL 99/26", "CD:PL 99/26", ATOR, "Ana")
        self.conn.commit()
        self.assertErroDominio("inclusao_duplicada", "gestao.registrar_inclusao_resolvida", outro["id"], 900099)
        # um PL sem keyword incluído pelo sistema chega à gold pelo acompanhamento
        self.cur.execute("INSERT INTO silver.proposicao (id_proposicao, sigla_tipo, numero, ano, ementa) VALUES (900099, 'PL', 99, 2026, 'Tema sem palavra-chave')")
        self.atualizar_cache()
        c = self.chamar("gestao.concluir_inclusoes")
        self.assertEqual((c["concluidas"], c["marcadas_sim"]), (1, 1))
        self.assertEqual(self.projeto(900099, "relevancia", "acompanhada", "elegivel"), ("SIM", True, True))
        self.assertEqual(self.chamar("gestao.concluir_inclusoes")["concluidas"], 0)
        self.assertErroDominio("inclusao_ja_concluida", "gestao.falhar_inclusao", p["id"], "x", True)

    def test_inclusao_de_ja_monitorada_nao_reativa_nada(self):
        # RF08: marcada NÃO, na fila de avaliação, ou só associada em gestao (fora do cache)
        self.decidir(uuid_teste(33), [900033], "NAO")
        self.decidir(uuid_teste(97), [900097], "SIM")
        for numero, id_prop in ((33, 900033), (31, 900031), (97, 900097)):
            p = self.chamar("gestao.solicitar_inclusao", f"PL {numero}", f"CD:PL {numero}", ATOR, "Ana")
            r = self.chamar("gestao.registrar_inclusao_resolvida", p["id"], id_prop)
            self.assertEqual((r["estado"], r["ja_monitorada"], r["ja_acompanhada"]), ("concluida", True, False), id_prop)
            # idempotente
            self.assertEqual(self.chamar("gestao.registrar_inclusao_resolvida", p["id"], id_prop)["estado"], "concluida")
        self.assertEqual(self.chamar("gestao.concluir_inclusoes"), {"concluidas": 0, "marcadas_sim": 0, "expiradas": 0})
        self.assertEqual(self.contar("SELECT count(*) FROM silver.proposicao_acompanhada WHERE id_proposicao IN (900033, 900031, 900097)"), 0)
        self.assertEqual(self.projeto(900033, "relevancia", "elegivel"), ("NAO", False))
        self.assertEqual(self.projeto(900031, "relevancia", "pendente_avaliacao"), (None, True))
        self.assertEqual(self.contar("SELECT count(*) FROM gestao.inclusao_manual WHERE ja_monitorada AND estado = 'concluida'"), 3)

    def test_inclusao_carregando_expira(self):
        q = self.chamar("gestao.solicitar_inclusao", "PL 1/1999", "CD:PL 1/1999", ATOR, "Ana")
        self.chamar("gestao.registrar_inclusao_resolvida", q["id"], 900098)
        self.cur.execute("UPDATE gestao.inclusao_manual SET atualizado_em = now() - interval '7 hours' WHERE id = %s", (q["id"],))
        self.assertEqual(self.chamar("gestao.concluir_inclusoes")["expiradas"], 1)
        self.cur.execute("SELECT estado, tentativas FROM gestao.inclusao_manual WHERE id = %s", (q["id"],))
        self.assertEqual(self.cur.fetchone(), ("solicitada", 1))


@unittest.skipUnless(TEST_DATABASE_URL, "TEST_DATABASE_URL não definida")
class PrivilegiosContratosTests(_ComDados):
    def test_setup_repetido_preserva_gestao_e_grants(self):
        # CA09/CA12
        from setup_db import aplicar_schemas

        r = self.chamar("gestao.salvar_decisao", None, 900021, 0, {"relevancia": "SIM", "parecer": "texto interno"}, ATOR, "Ana")
        self.conn.commit()
        aplicar_schemas(self.cur)
        self.atualizar_cache()
        self.conn.commit()
        self.assertEqual(self.projeto(900021, "uuid_projeto::text", "revisao", "parecer"), (r["uuid_projeto"], 1, "texto interno"))
        self.cur.execute("SELECT relevancia, em_carteira FROM api.vw_painel_decisoes WHERE id_proposicao = 1990000021")
        self.assertEqual(self.cur.fetchone(), ("SIM", True))
        for funcao in FUNCOES_APP:
            self.assertTrue(self.contar("SELECT has_function_privilege('legislativo_app', %s, 'EXECUTE')", funcao), funcao)
        # nenhuma função de gestao executável por PUBLIC (proacl NULL = padrão, que inclui PUBLIC)
        self.assertEqual(self.contar("""
            SELECT count(*) FROM pg_proc p
            WHERE p.pronamespace = 'gestao'::regnamespace AND p.prorettype <> 'trigger'::regtype
              AND (p.proacl IS NULL OR EXISTS (SELECT 1 FROM aclexplode(p.proacl) a WHERE a.grantee = 0))"""), 0)

    def test_funcoes_pertencem_ao_dono_restrito(self):
        import psycopg2

        self.cur.execute("""SELECT DISTINCT pg_get_userbyid(p.proowner) FROM pg_proc p
            WHERE p.pronamespace = 'gestao'::regnamespace AND p.prorettype <> 'trigger'::regtype""")
        self.assertEqual(self.cur.fetchall(), [("gestao_dono",)])
        self.assertFalse(self.contar("SELECT rolcanlogin OR rolsuper OR rolcreaterole FROM pg_roles WHERE rolname = 'gestao_dono'"))
        self.assertFalse(self.contar("SELECT has_schema_privilege('gestao_dono', 'gestao', 'CREATE')"))
        for relacao in ("bronze.controle_execucao", "silver.proposicao", "gold.vw_monitoramento", "api.vw_monitoramento"):
            self.assertFalse(self.contar("SELECT has_table_privilege('gestao_dono', %s, 'SELECT')", relacao), relacao)
        for relacao in ("gestao.decisao_projeto", "gestao.historico_alteracao"):
            self.assertFalse(self.contar("SELECT has_table_privilege('gestao_dono', %s, 'DELETE')", relacao), relacao)
        for comando in ("DROP TABLE gestao.projeto", "ALTER TABLE gestao.decisao_projeto ADD COLUMN x int",
                        "CREATE TABLE gestao.x (a int)", "TRUNCATE gestao.inclusao_manual",
                        "SELECT * FROM bronze.controle_execucao", "SELECT * FROM silver.proposicao"):
            self.cur.execute("SET ROLE gestao_dono")
            with self.assertRaises(psycopg2.errors.InsufficientPrivilege, msg=comando):
                self.cur.execute(comando)
            self.conn.rollback()
        # e as funções continuam funcionando com esses privilégios
        r = self.chamar("gestao.salvar_decisao", None, 900021, 0, {"relevancia": "SIM"}, ATOR, "Ana")
        self.assertEqual(r["revisao"], 1)

    def test_anon_e_authenticated_so_leem_a_projecao(self):
        import psycopg2

        for papel in ("anon", "authenticated"):
            for esquema in ("gestao", "contrato"):
                self.assertFalse(self.contar("SELECT has_schema_privilege(%s, %s, 'USAGE')", papel, esquema), (papel, esquema))
            for relacao in ("contrato.vw_projeto", "contrato.vw_versao", "gestao.decisao_projeto", "gestao.historico_alteracao"):
                self.assertFalse(self.contar("SELECT has_table_privilege(%s, %s, 'SELECT')", papel, relacao), (papel, relacao))
            for funcao in FUNCOES_APP + FUNCOES_INTERNAS:
                self.assertFalse(self.contar("SELECT has_function_privilege(%s, %s, 'EXECUTE')", papel, funcao), (papel, funcao))
        self.cur.execute("SET ROLE anon")
        self.cur.execute("SET statement_timeout = '3s'")
        self.cur.execute("SELECT * FROM api.vw_painel_decisoes")
        self.assertEqual([c.name for c in self.cur.description], COLUNAS_PAINEL)
        self.assertGreater(len(self.cur.fetchall()), 0)
        with self.assertRaises(psycopg2.errors.InsufficientPrivilege):
            self.cur.execute("SELECT * FROM contrato.vw_projeto")
        self.conn.rollback()

    def test_legislativo_app_le_contratos_e_executa_so_as_suas_funcoes(self):
        import psycopg2

        for relacao in ("gestao.projeto", "gestao.projeto_proposicao", "gestao.decisao_projeto",
                        "gestao.historico_alteracao", "gestao.inclusao_manual", "gestao.situacao_encerramento",
                        "silver.proposicao", "silver.proposicao_acompanhada", "api_cache.vw_monitoramento"):
            for privilegio in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                self.assertFalse(self.contar("SELECT has_table_privilege('legislativo_app', %s, %s)", relacao, privilegio), (relacao, privilegio))
        for funcao in FUNCOES_INTERNAS:
            self.assertFalse(self.contar("SELECT has_function_privilege('legislativo_app', %s, 'EXECUTE')", funcao), funcao)
        self.cur.execute("SET ROLE legislativo_app")
        for view in ("vw_versao", "vw_projeto", "vw_conferencia", "vw_tramitacao", "vw_pauta", "vw_frescor"):
            self.cur.execute(f"SELECT count(*) FROM contrato.{view}")
        r = self.chamar("gestao.salvar_decisao", None, 900021, 0, {"relevancia": "SIM"}, ATOR, "Ana")
        self.assertEqual(r["revisao"], 1)
        self.conn.commit()
        for comando in ("UPDATE gestao.decisao_projeto SET relevancia = 'NAO'",
                        "INSERT INTO gestao.projeto (uuid) VALUES (gen_random_uuid())",
                        "SELECT * FROM gestao.historico_alteracao",
                        "SELECT gestao.concluir_inclusoes()",
                        "SELECT * FROM silver.proposicao"):
            self.cur.execute("SET ROLE legislativo_app")
            with self.assertRaises(psycopg2.errors.InsufficientPrivilege, msg=comando):
                self.cur.execute(comando)
            self.conn.rollback()


if __name__ == "__main__":
    unittest.main()
