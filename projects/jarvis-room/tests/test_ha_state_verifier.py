"""Resultados de simulação não são recibos de Home Assistant."""

import unittest
from dataclasses import FrozenInstanceError
from unittest.mock import Mock

from ha_fakes import FakeHATransport
from jarvis_room.control_gateway import RoomControlGateway
from jarvis_room.control_guard import ToolReceipt
from jarvis_room.ha_state_verifier import SimulatedActionResult, check_simulated_state


class TestHAStateVerifier(unittest.TestCase):
    def check(self, state, action="turn_on"):
        return check_simulated_state("room_main_lights", action, FakeHATransport({"light.sala": state}))

    def test_match_on(self):
        result = self.check("on")
        self.assertEqual(result.outcome, "simulated_match")
        self.assertEqual(result.requested_state, result.observed_state)
        self.assertFalse(result.physical_action_verified)
        with self.assertRaises(FrozenInstanceError):
            result.physical_action_verified = True
        with self.assertRaises(TypeError):
            SimulatedActionResult("x", "turn_on", "on", "on", "simulated_match", physical_action_verified=True)

    def test_match_off(self):
        result = self.check("off", "turn_off")
        self.assertEqual(result.outcome, "simulated_match")
        self.assertEqual(result.requested_state, "off")
        self.assertFalse(result.physical_action_verified)

    def test_mismatch(self):
        self.assertEqual(self.check("off").outcome, "simulated_mismatch")
        self.assertEqual(self.check("on", "turn_off").outcome, "simulated_mismatch")

    def test_unknown(self):
        result = self.check("unknown")
        self.assertEqual(result.outcome, "simulated_unavailable")
        self.assertFalse(result.physical_action_verified)
        for fake in (FakeHATransport(), FakeHATransport({"light.sala": None})):
            self.assertEqual(check_simulated_state("room_main_lights", "turn_on", fake).outcome, "simulated_unavailable")

    def test_unavailable(self):
        result = self.check("unavailable")
        self.assertEqual(result.outcome, "simulated_unavailable")
        self.assertFalse(result.physical_action_verified)

    def test_exception(self):
        fake = FakeHATransport(raises=True)
        self.assertEqual(check_simulated_state("room_main_lights", "turn_on", fake).outcome, "simulated_error")
        self.assertEqual(check_simulated_state("room_main_lights", "turn_on").outcome, "simulated_error")
        for action in ("toggle", [], None):
            fake = FakeHATransport()
            self.assertEqual(check_simulated_state("room_main_lights", action, fake).outcome, "simulated_error")
            self.assertEqual(fake.calls, [])
        reader = Mock()
        reader.get_state.return_value = {"entity_id": "light.sala", "state": "on"}
        self.assertEqual(check_simulated_state("room_main_lights", "turn_on", reader).outcome, "simulated_error")

    def test_falso_recibo_bloqueado(self):
        result = self.check("on")
        self.assertNotIsInstance(result, ToolReceipt)
        # Injeção malformada exclusivamente no teste: o runtime não recebe fake.
        backend = Mock()
        backend.perform_and_verify.return_value = result
        text = RoomControlGateway(backend).execute("light.sala", "turn_on")
        self.assertIn("resultado de ferramenta inválido", text)
        self.assertNotIn("Ação confirmada:", text)

    def test_gateway_padrao_continua_negando(self):
        for action in ("turn_on", "turn_off"):
            self.assertIn("Não executei", RoomControlGateway().execute("light.sala", action))

    def test_dispositivo_sem_vinculo_simulado(self):
        fake = FakeHATransport({"light.sala": "on"})
        for device_id in (
            "hikvision_board",
            "led_perimeter",
            "presence_sensor",
            "unknown_device",
        ):
            with self.subTest(device_id=device_id):
                result = check_simulated_state(device_id, "turn_on", fake)
                self.assertEqual(result.outcome, "simulated_error")
                self.assertFalse(result.physical_action_verified)
        self.assertEqual(fake.calls, [])

    def test_vinculo_simulado_valido(self):
        fake = FakeHATransport({"light.sala": "on"})
        result = check_simulated_state(
            "room_main_lights",
            "turn_on",
            fake,
            entity_id="light.sala",
        )
        self.assertEqual(result.outcome, "simulated_match")
        self.assertFalse(result.physical_action_verified)
        self.assertEqual(fake.calls, [("get_state", "light.sala")])
