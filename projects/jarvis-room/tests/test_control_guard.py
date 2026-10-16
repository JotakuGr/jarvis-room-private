"""Testes das respostas determinísticas de controle da Sala Temática."""

import unittest

from jarvis_room.control_guard import ToolReceipt, render_action_result


class TestControlGuard(unittest.TestCase):
    def setUp(self) -> None:
        self.entity_id = "light.sala"
        self.action = "turn_on"

    def test_sem_ferramenta(self) -> None:
        response = render_action_result(self.entity_id, self.action)
        self.assertEqual(
            response,
            "Não executei esse comando. "
            "O controle deste dispositivo ainda não está disponível.",
        )

    def test_ferramenta_falhou(self) -> None:
        receipt = ToolReceipt(
            "home_assistant", self.entity_id, self.action, False, False
        )
        response = render_action_result(self.entity_id, self.action, receipt)
        self.assertEqual(response, "Não foi possível executar o comando.")

    def test_estado_nao_confirmado(self) -> None:
        receipt = ToolReceipt(
            "home_assistant", self.entity_id, self.action, True, False
        )
        response = render_action_result(self.entity_id, self.action, receipt)
        self.assertEqual(
            response,
            "O comando foi enviado, mas o estado do dispositivo "
            "ainda não foi confirmado.",
        )

    def test_confirmacao_valida(self) -> None:
        receipt = ToolReceipt(
            "home_assistant", self.entity_id, self.action, True, True
        )
        response = render_action_result(self.entity_id, self.action, receipt)
        self.assertEqual(response, "Ação confirmada: light.sala — turn_on.")

    def test_resultado_de_outra_ferramenta(self) -> None:
        receipt = ToolReceipt(
            "modelo_llm", self.entity_id, self.action, True, True
        )
        response = render_action_result(self.entity_id, self.action, receipt)
        self.assertEqual(
            response, "Ação não confirmada: resultado de ferramenta inválido."
        )

    def test_resultado_de_outro_dispositivo(self) -> None:
        receipt = ToolReceipt(
            "home_assistant", "light.outra_sala", self.action, True, True
        )
        response = render_action_result(self.entity_id, self.action, receipt)
        self.assertEqual(
            response, "Ação não confirmada: resultado de ferramenta inválido."
        )
