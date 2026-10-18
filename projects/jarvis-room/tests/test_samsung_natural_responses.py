import unittest
from dataclasses import FrozenInstanceError

from jarvis_room.samsung_contract import SamsungLabError
from jarvis_room.samsung_natural_intent import parse_samsung_intent
from jarvis_room.samsung_natural_responses import error_reply, recognition_reply, result_reply
from jarvis_room.samsung_observation import ObservationSummary
from jarvis_room.samsung_state import SamsungCommandResult, SamsungReportedState


class TestSamsungNaturalResponses(unittest.TestCase):
    def test_reconhecido_aguarda_autorizacao(self):
        reply = recognition_reply(parse_samsung_intent("Ligue a TV"))
        self.assertIn("ligar a televisão Samsung", reply.text)
        self.assertIn("Aguardando autorização", reply.text)
        self.assertIn("Nenhum comando", reply.text)

    def test_comando_nao_suportado(self):
        self.assertEqual(recognition_reply(parse_samsung_intent("Ligue todas as TVs")).status, "unsupported")

    def test_nao_autorizado(self):
        for code in ("manual_authorization_required", "confirmation_required", "cancelled"):
            reply = error_reply(SamsungLabError(code))
            self.assertIn("não foi autorizada", reply.text)
            self.assertIn("Nenhum comando foi enviado", reply.text)

    def test_ha_reportou_ligada_e_desligada(self):
        for action, state, word in (("turn_on", "on", "ligada"), ("turn_off", "off", "desligada")):
            result = SamsungCommandResult(action, "accepted", after=SamsungReportedState(state), observation=ObservationSummary(1, 0, 30, "matched"))
            reply = result_reply(result)
            self.assertEqual(reply.status, "ha_state_reported")
            self.assertIn("Home Assistant", reply.text)
            self.assertIn("informou", reply.text)
            self.assertIn(word, reply.text)
            self.assertFalse(reply.action_verified)

    def test_aceite_isolado_nao_declara_conclusao(self):
        reply = result_reply(SamsungCommandResult("turn_on", "accepted"))
        self.assertEqual(reply.status, "observation_interrupted")
        self.assertNotIn("está ligada", reply.text)

    def test_timeout_nao_afirma_falha_fisica(self):
        result = SamsungCommandResult("turn_on", "accepted", error_code="state_observation_timeout", observation=ObservationSummary(15, 30, 30, "timed_out"))
        reply = result_reply(result)
        self.assertIn("não foi confirmado dentro do prazo", reply.text)
        self.assertNotIn("falhou", reply.text)
        self.assertNotIn("Nenhum comando foi enviado", reply.text)

    def test_indisponibilidade(self):
        result = SamsungCommandResult("turn_on", "accepted", observation=ObservationSummary(15, 30, 30, "unavailable"))
        self.assertEqual(result_reply(result).status, "state_unconfirmed")

    def test_entrega_incerta(self):
        reply = result_reply(SamsungCommandResult("turn_on", "unknown", error_code="command_outcome_unknown"))
        self.assertEqual(reply.status, "delivery_uncertain")
        self.assertIn("Nenhuma nova tentativa automática", reply.text)

    def test_cancelamento_apos_aceite_nao_apaga_envio(self):
        reply = result_reply(SamsungCommandResult("turn_on", "accepted", error_code="cancelled", observation=ObservationSummary(1, 0, 30, "error")))
        self.assertIn("aceitou o comando", reply.text)
        self.assertNotIn("Nenhum comando foi enviado", reply.text)

    def test_falha_de_auditoria_e_rejeicao(self):
        reply = result_reply(SamsungCommandResult("turn_off", "accepted", audit_complete=False))
        self.assertEqual(reply.status, "audit_incomplete")
        self.assertIn("aceitou", reply.text)
        self.assertEqual(result_reply(SamsungCommandResult("turn_on", "rejected")).status, "rejected")

    def test_estado_tardio_nao_publica_sucesso(self):
        result = SamsungCommandResult("turn_on", "accepted", after=SamsungReportedState("on"), error_code="state_observation_timeout", observation=ObservationSummary(1, 31, 30, "timed_out"))
        self.assertEqual(result_reply(result).status, "state_unconfirmed")

    def test_flags_de_verificacao_nao_elevaveis(self):
        reply = recognition_reply(parse_samsung_intent("Ligue a TV"))
        self.assertFalse(reply.action_verified)
        self.assertFalse(reply.physical_action_verified)
        with self.assertRaises(FrozenInstanceError):
            reply.action_verified = True

    def test_erros_privados_nao_sao_publicados(self):
        reply = error_reply(RuntimeError("Bearer secret-value; private headers"))
        self.assertNotIn("secret-value", reply.text)
        self.assertNotIn("headers", reply.text)
        self.assertEqual(result_reply(None).status, "interrupted")
