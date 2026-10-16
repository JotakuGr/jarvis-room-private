"""Testes de roteamento e encaminhamento, sem LLM ou dispositivos reais."""

import unittest

from jarvis_room.command_router import route_message
from jarvis_room.room_assistant import handle_message


class SpyGateway:
    def __init__(self):
        self.calls = []

    def execute(self, entity_id, action):
        self.calls.append((entity_id, action))
        return "Resultado simulado do teste"


class TestCommandRouter(unittest.TestCase):
    def test_ligar_luz(self) -> None:
        for message in ("Ligue a luz da sala", "Acenda a luz da sala"):
            with self.subTest(message=message):
                decision = route_message(message)
                self.assertEqual(decision.kind, "control")
                self.assertEqual(decision.entity_id, "light.sala")
                self.assertEqual(decision.action, "turn_on")

    def test_desligar_luz(self) -> None:
        for message in ("Desligue a luz da sala", "Apague a luz da sala"):
            with self.subTest(message=message):
                decision = route_message(message)
                self.assertEqual(decision.kind, "control")
                self.assertEqual(decision.entity_id, "light.sala")
                self.assertEqual(decision.action, "turn_off")

    def test_nome_e_pontuacao(self) -> None:
        for message in (
            "Jarvis, por favor, acenda a luz da sala!",
            "  JARVIS,   por favor, ACENDA a luz da sála!  ",
            "Por favor, acenda a luz da sala.",
        ):
            with self.subTest(message=message):
                decision = route_message(message)
                self.assertEqual(decision.kind, "control")
                self.assertEqual(decision.entity_id, "light.sala")
                self.assertEqual(decision.action, "turn_on")

    def test_todas_as_luzes_nao_habilitadas(self) -> None:
        gateway = SpyGateway()
        for message in (
            "Ligue todas as luzes da Sala Temática",
            "Desligue todas as luzes",
            "Abra a porta",
            "Configure o ar-condicionado",
            "Ligue a luz da sala e apague todas as outras",
        ):
            with self.subTest(message=message):
                decision = route_message(message)
                self.assertEqual(decision.kind, "unsupported")
                self.assertIsNone(decision.entity_id)
                self.assertIsNone(decision.action)
                self.assertEqual(
                    handle_message(message, gateway),
                    "Não executei esse comando. "
                    "Este dispositivo ou ação ainda não está habilitado.",
                )
        self.assertEqual(gateway.calls, [])

    def test_conversacao_bloqueada(self) -> None:
        gateway = SpyGateway()
        for message in ("Quem é você?", "Não ligue a luz da sala", ""):
            with self.subTest(message=message):
                decision = route_message(message)
                self.assertEqual(decision.kind, "conversation")
                self.assertIsNone(decision.entity_id)
                self.assertIsNone(decision.action)
                self.assertEqual(
                    handle_message(message, gateway),
                    "A conversação ainda não está conectada "
                    "a esta interface de controle.",
                )
        self.assertEqual(gateway.calls, [])

    def test_encaminhamento_ao_gateway(self) -> None:
        for message, action in (
            ("Ligue a luz da sala", "turn_on"),
            ("Desligue a luz da sala", "turn_off"),
        ):
            with self.subTest(message=message):
                gateway = SpyGateway()
                self.assertEqual(
                    handle_message(message, gateway), "Resultado simulado do teste"
                )
                self.assertEqual(gateway.calls, [("light.sala", action)])

    def test_comando_reconhecido_sem_backend(self) -> None:
        for message in ("Ligue a luz da sala", "Desligue a luz da sala"):
            with self.subTest(message=message):
                self.assertEqual(
                    handle_message(message),
                    "Não executei esse comando. "
                    "O controle deste dispositivo ainda não está disponível.",
                )
