"""Testes do gateway com backend exclusivamente simulado."""

import unittest

from jarvis_room.control_gateway import RoomControlGateway
from jarvis_room.control_guard import ToolReceipt


class FakeBackend:
    """Simulação exclusiva dos testes; não autentica resultados externos."""

    def __init__(self, receipt=None, raises=False):
        self.receipt = receipt
        self.raises = raises
        self.calls = []

    def perform_and_verify(self, entity_id, action):
        self.calls.append((entity_id, action))
        if self.raises:
            raise RuntimeError("Backend indisponível")
        return self.receipt


class TestControlGateway(unittest.TestCase):
    def test_sem_backend(self) -> None:
        gateway = RoomControlGateway()
        for action in ("turn_on", "turn_off"):
            with self.subTest(action=action):
                self.assertEqual(
                    gateway.execute("light.sala", action),
                    "Não executei esse comando. "
                    "O controle deste dispositivo ainda não está disponível.",
                )

    def test_acao_nao_permitida(self) -> None:
        backend = FakeBackend()
        gateway = RoomControlGateway(backend)
        for action in ("delete", "toggle", "", None, []):
            with self.subTest(action=action):
                self.assertEqual(
                    gateway.execute("light.sala", action),
                    "Ação não autorizada.",
                )
        self.assertEqual(backend.calls, [])

    def test_dispositivo_invalido(self) -> None:
        backend = FakeBackend()
        gateway = RoomControlGateway(backend)
        for entity_id in (
            "climate.sala",
            "light.",
            "light.Sala",
            "light.sala;delete",
            "light.sala\n",
            "",
            None,
        ):
            with self.subTest(entity_id=entity_id):
                self.assertEqual(
                    gateway.execute(entity_id, "turn_on"),
                    "Dispositivo inválido ou não autorizado.",
                )
        self.assertEqual(backend.calls, [])

    def test_backend_indisponivel(self) -> None:
        backend = FakeBackend(raises=True)
        gateway = RoomControlGateway(backend)
        self.assertEqual(
            gateway.execute("light.sala", "turn_on"),
            "Não foi possível executar o comando.",
        )
        self.assertEqual(backend.calls, [("light.sala", "turn_on")])

    def test_recibo_invalido(self) -> None:
        for receipt in (
            None,
            {"source": "home_assistant", "success": True},
            ToolReceipt("modelo_llm", "light.sala", "turn_on", True, True),
            ToolReceipt("home_assistant", "light.outra", "turn_on", True, True),
            ToolReceipt("home_assistant", "light.sala", "turn_off", True, True),
            ToolReceipt("home_assistant", "light.sala", "turn_on", "true", True),
            ToolReceipt("home_assistant", "light.sala", "turn_on", True, "true"),
        ):
            with self.subTest(receipt=receipt):
                backend = FakeBackend(receipt)
                gateway = RoomControlGateway(backend)
                self.assertEqual(
                    gateway.execute("light.sala", "turn_on"),
                    "Ação não confirmada: resultado de ferramenta inválido.",
                )
                self.assertEqual(backend.calls, [("light.sala", "turn_on")])

    def test_resultado_sem_confirmacao(self) -> None:
        for success, verified, expected in (
            (False, False, "Não foi possível executar o comando."),
            (False, True, "Não foi possível executar o comando."),
            (
                True,
                False,
                "O comando foi enviado, mas o estado do dispositivo "
                "ainda não foi confirmado.",
            ),
        ):
            with self.subTest(success=success, verified=verified):
                receipt = ToolReceipt(
                    "home_assistant", "light.sala", "turn_on", success, verified
                )
                gateway = RoomControlGateway(FakeBackend(receipt))
                self.assertEqual(gateway.execute("light.sala", "turn_on"), expected)

    def test_confirmacao_valida_simulada(self) -> None:
        for action in ("turn_on", "turn_off"):
            with self.subTest(action=action):
                receipt = ToolReceipt(
                    "home_assistant", "light.sala_1", action, True, True
                )
                backend = FakeBackend(receipt)
                gateway = RoomControlGateway(backend)
                self.assertEqual(
                    gateway.execute("light.sala_1", action),
                    f"Ação confirmada: light.sala_1 — {action}.",
                )
                self.assertEqual(backend.calls, [("light.sala_1", action)])
