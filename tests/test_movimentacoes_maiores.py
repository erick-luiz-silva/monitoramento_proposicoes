"""Urgência e confirmação por identidade oficial, em PostgreSQL local descartável."""

import json
import unittest

import test_sql_local as banco


@unittest.skipUnless(banco.TEST_DATABASE_URL, "TEST_DATABASE_URL não definida")
class MovimentacoesTests(banco._ComDados):
    def preparar(self, id_prop=900001, dias=10):
        uuid = banco.uuid_teste(id_prop)
        self.decidir(uuid, [id_prop], "SIM", True)
        self.cur.execute(
            "UPDATE gestao.decisao_projeto SET prioridade_desde = now() - %s * interval '1 day' WHERE uuid_projeto = %s",
            (dias, uuid))
        return uuid

    def movimento(self, id_prop=900001, seq=1, codigo="320", descricao="Designação de relator", dias=1):
        self.cur.execute("""
            INSERT INTO silver.tramitacao
                (id_proposicao, sequencia, cod_tipo_tramitacao, descricao_tramitacao, data_hora, data_extracao, casa)
            SELECT %s, %s, %s, %s, (now() AT TIME ZONE 'America/Sao_Paulo') - %s * interval '1 day',
                   now() AT TIME ZONE 'America/Sao_Paulo', %s
        """, (id_prop, seq, codigo, descricao, dias, "SF" if id_prop >= 1_000_000_000 else "CD"))

    def confirmar(self, uuid, *itens):
        return self.chamar("gestao.confirmar_movimentacoes", uuid,
                           json.dumps(list(itens)), banco.ATOR, "Ana")

    def item(self, seq, id_prop=900001):
        return {"id_proposicao": id_prop, "sequencia": seq}

    def test_maior_apos_referencia_abre_urgencia_rotina_e_antigo_nao(self):
        self.preparar()
        self.movimento(seq=1)
        self.movimento(seq=2, codigo="500", descricao="Recebimento")
        self.movimento(seq=3, dias=11)
        self.assertEqual(self.projeto(900001, "movimentacoes_a_confirmar", "urgente_movimentacao", "urgente", "motivos_urgencia"),
                         (1, True, True, ["movimentação"]))
        self.cur.execute("SELECT sequencia, apos_referencia FROM contrato.vw_movimentacao_maior ORDER BY sequencia")
        self.assertEqual(self.cur.fetchall(), [(1, True), (3, False)])

    def test_confirmacao_parcial_nova_ocorrencia_e_idempotencia(self):
        uuid = self.preparar()
        self.movimento(seq=1)
        self.movimento(seq=2)
        self.assertEqual(self.confirmar(uuid, self.item(1)), {"confirmadas": 1, "ignoradas": 0})
        self.assertEqual(self.projeto(900001, "movimentacoes_a_confirmar"), 1)
        self.assertEqual(self.confirmar(uuid, self.item(1)), {"confirmadas": 0, "ignoradas": 1})
        self.confirmar(uuid, self.item(2))
        self.assertFalse(self.projeto(900001, "urgente"))
        self.movimento(seq=3)
        self.assertEqual(self.projeto(900001, "movimentacoes_a_confirmar"), 1)
        self.assertEqual(self.contar("SELECT count(*) FROM gestao.historico_alteracao WHERE operacao = 'confirmar_movimentacoes'"), 2)

    def test_itens_de_outro_projeto_rotina_antigo_e_malformado_sao_ignorados(self):
        uuid = self.preparar()
        self.movimento(seq=1, codigo="500")
        self.movimento(seq=2, dias=11)
        self.preparar(900002)
        self.movimento(900002)
        self.assertEqual(self.confirmar(uuid, self.item(1), self.item(2), self.item(1, 900002), {"sequencia": "inválida"}),
                         {"confirmadas": 0, "ignoradas": 4})
        self.assertEqual(self.contar("SELECT count(*) FROM gestao.confirmacao_movimentacao"), 0)

    def test_pauta_mantem_urgencia_depois_de_confirmar(self):
        uuid = self.preparar(900009)
        self.movimento(900009)
        self.assertEqual(self.projeto(900009, "motivos_urgencia"), ["movimentação", "pauta"])
        self.confirmar(uuid, self.item(1, 900009))
        self.assertEqual(self.projeto(900009, "urgente_movimentacao", "urgente_pauta", "urgente", "motivos_urgencia"),
                         (False, True, True, ["pauta"]))

    def test_baseline_implantacao_prevalece_e_sem_referencia_nao_abre(self):
        self.preparar()
        self.movimento(dias=2)
        self.cur.execute("UPDATE gestao.parametro SET valor = (now() - interval '1 day')::text WHERE chave = 'data_implantacao'")
        self.assertFalse(self.projeto(900001, "urgente"))
        self.cur.execute("UPDATE gestao.parametro SET valor = NULL")
        self.cur.execute("UPDATE gestao.decisao_projeto SET prioridade_desde = NULL")
        self.assertFalse(self.projeto(900001, "urgente"))

    def test_senado_com_e_sem_acento(self):
        id_prop = 1990000013
        self.preparar(id_prop)
        for seq, descricao in enumerate(("Aprovação do parecer", "Aprovacao do parecer", "Remetido à Câmara dos Deputados", "Recebido o documento", "Declarado prejuízo da matéria", "SANCIONADA. LEI 15503", "Vetado totalmente"), 1):
            self.movimento(id_prop, seq, None, descricao)
        self.assertEqual(self.projeto(id_prop, "movimentacoes_a_confirmar"), 6)

    def test_tipos_desconhecidos_sao_rotina_e_listados_para_mantenedor(self):
        self.preparar()
        self.movimento(codigo="999999", descricao="Novo tipo oficial")
        self.assertFalse(self.projeto(900001, "urgente"))
        self.cur.execute("SELECT cod_tipo_tramitacao, ocorrencias FROM contrato.vw_tipos_sem_classificacao")
        self.assertEqual(self.cur.fetchall(), [("999999", 1)])

    def test_nao_encerrado_e_conferencia_nao_geram_urgencia(self):
        for id_prop in (900004, 900006, 900007):
            self.preparar(id_prop)
            self.movimento(id_prop)
        self.cur.execute("UPDATE gestao.decisao_projeto SET relevancia = 'NAO', prioridade = false WHERE uuid_projeto = %s", (banco.uuid_teste(900004),))
        for id_prop in (900004, 900006, 900007):
            self.assertFalse(self.projeto(id_prop, "urgente"), id_prop)

    def test_confirmacao_pelo_papel_app_e_preservacao_apos_setup(self):
        from setup_db import aplicar_schemas
        uuid = self.preparar()
        self.movimento()
        self.conn.commit()
        self.cur.execute("SET ROLE legislativo_app")
        self.assertEqual(self.confirmar(uuid, self.item(1)), {"confirmadas": 1, "ignoradas": 0})
        self.cur.execute("RESET ROLE")
        self.conn.commit()
        aplicar_schemas(self.cur)
        self.atualizar_cache()
        self.assertEqual(self.contar("SELECT count(*) FROM gestao.confirmacao_movimentacao"), 1)
        self.assertFalse(self.projeto(900001, "urgente"))
        for relacao in ("confirmacao_movimentacao", "tipo_movimentacao", "regra_movimentacao_senado", "parametro"):
            self.assertFalse(self.contar("SELECT has_table_privilege('legislativo_app', %s, 'SELECT')", "gestao." + relacao))

    def test_confirmacao_aceita_uuid_antigo_apos_reconciliacao(self):
        atual = self.preparar()
        self.movimento()
        antigo = banco.uuid_teste(999)
        self.cur.execute("INSERT INTO gestao.projeto(uuid, substituido_por) VALUES (%s, %s)", (antigo, atual))
        self.assertEqual(self.confirmar(antigo, self.item(1)), {"confirmadas": 1, "ignoradas": 0})
        self.cur.execute("SELECT uuid_projeto::text FROM gestao.confirmacao_movimentacao")
        self.assertEqual(self.cur.fetchone()[0], atual)


if __name__ == "__main__":
    unittest.main()
