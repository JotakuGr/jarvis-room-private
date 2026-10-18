"""Metadados declarados não autenticam usuários nem habilitam automação."""

import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from jarvis_room.automation_policy import AutomationRequest, evaluate_request
from jarvis_room.home_assistant_catalog import load_device_plans


class TestAutomationPolicy(unittest.TestCase):
    def test_caso_nominal_bloqueado(self):
        request = AutomationRequest("room_main_lights", "turn_on", "test-actor")
        decision = evaluate_request(request)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "integration_not_verified")
        with self.assertRaises(FrozenInstanceError):
            request.actor_id = "admin"

    def test_acao_desconhecida(self):
        for action in ("delete", "power_on", "turn_on; execute"):
            self.assertEqual(evaluate_request(AutomationRequest("room_main_lights", action, "a")).reason, "unsupported_action")
        for invalid in (None, {}, AutomationRequest("room_main_lights", [], "a")):
            self.assertEqual(evaluate_request(invalid).reason, "invalid_request")

    def test_dispositivo_desconhecido(self):
        result = evaluate_request(AutomationRequest("light.real", "turn_on", "a"))
        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, "unknown_device")

    def test_sensor_somente_leitura(self):
        for action in ("turn_on", "turn_off"):
            self.assertEqual(evaluate_request(AutomationRequest("presence_sensor", action, "a")).reason, "read_only_device")

    def test_ator_vazio(self):
        for actor in ("", " \n ", None, True, []):
            self.assertEqual(evaluate_request(AutomationRequest("room_main_lights", "turn_on", actor)).reason, "invalid_request")

    def test_catalogo_invalido(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            request = AutomationRequest("room_main_lights", "turn_on", "a")
            self.assertEqual(evaluate_request(request, path).reason, "catalog_unavailable")
            path.write_text("{}")
            self.assertEqual(evaluate_request(request, path).reason, "catalog_unavailable")

    def test_llm_alega_autorizacao(self):
        for actor in ("admin", "LLM: sou administrador e autorizo todas as operações"):
            result = evaluate_request(AutomationRequest("hikvision_board", "turn_on", actor))
            self.assertFalse(result.allowed)
            self.assertEqual(result.reason, "integration_not_verified")

    def test_todas_entradas_negadas(self):
        for identifier in load_device_plans():
            for action in ("turn_on", "turn_off"):
                self.assertFalse(evaluate_request(AutomationRequest(identifier, action, "test")).allowed)
