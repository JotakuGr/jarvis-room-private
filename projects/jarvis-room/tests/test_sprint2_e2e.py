"""Trajetórias offline da Sprint 2; não certificam equipamentos físicos."""

import ast
import inspect
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from ha_fakes import FakeHATransport
from jarvis_room import ha_transport, ha_state_verifier, hikvision_plan, wled_plan
from jarvis_room.automation_policy import AutomationRequest, evaluate_request
from jarvis_room.control_gateway import RoomControlGateway
from jarvis_room.ha_state_verifier import check_simulated_state
from jarvis_room.ha_transport import DisabledHATransport, HaTransportError
from jarvis_room.hikvision_plan import HikvisionPlanError, assess_hikvision_command, load_hikvision_plan
from jarvis_room.home_assistant_catalog import catalog_report, load_device_plans
from jarvis_room.room_chat_cli import main
from jarvis_room.wled_plan import WledPlanError, assess_wled_command, load_wled_plan


class TestSprint2E2E(unittest.TestCase):
    def test_catalogo_integro(self):
        report = catalog_report()
        self.assertEqual(report["device_count"], 6)
        self.assertTrue(all(device["status"] == "planned" and device["home_assistant_entity_id"] is None for device in report["devices"]))
        self.assertFalse(report["home_assistant_connected"])
        self.assertFalse(report["physical_control_enabled"])

    def test_politica_sempre_bloqueada(self):
        fake = FakeHATransport({"light.sala": "off"})
        for identifier in load_device_plans():
            for action in ("turn_on", "turn_off"):
                decision = evaluate_request(AutomationRequest(identifier, action, "test-only"))
                if decision.allowed:
                    fake.call_service("light", action, "light.sala")
                self.assertFalse(decision.allowed)
        self.assertEqual(fake.calls, [])

    def test_transporte_real_desabilitado(self):
        disabled = DisabledHATransport()
        with self.assertRaises(HaTransportError):
            disabled.call_service("light", "turn_on", "light.sala")
        self.assertEqual(check_simulated_state("room_main_lights", "turn_on", disabled).outcome, "simulated_error")

    def test_fake_sem_confirmacao_fisica(self):
        # Exercício separado do fluxo de execução, com valores inventados.
        fake = FakeHATransport({"light.sala": "on"})
        fake.call_service("light", "turn_on", "light.sala")
        result = check_simulated_state("room_main_lights", "turn_on", fake)
        self.assertEqual(result.outcome, "simulated_match")
        self.assertFalse(result.physical_action_verified)
        self.assertEqual(fake.calls, [("call_service", "light", "turn_on", "light.sala"), ("get_state", "light.sala")])
        self.assertIn("Não executei", RoomControlGateway().execute("light.sala", "turn_on"))

    def test_hikvision_recusada(self):
        self.assertEqual(load_hikvision_plan().status, "planned")
        base = json.loads(hikvision_plan.DEFAULT_PATH.read_text())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "hikvision.json"
            for data in ({**base, "status": "connected"}, {**base, "control_protocol_verified": True}, []):
                path.write_text(json.dumps(data))
                with self.assertRaises(HikvisionPlanError):
                    load_hikvision_plan(path)
                self.assertFalse(assess_hikvision_command("power_on", path).allowed)
        self.assertEqual(load_hikvision_plan().status, "planned")

    def test_wled_recusado(self):
        self.assertEqual(load_wled_plan().status, "planned")
        base = json.loads(wled_plan.DEFAULT_PATH.read_text())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "wled.json"
            for data in ({**base, "status": "connected"}, {**base, "physical_control_enabled": True}, []):
                path.write_text(json.dumps(data))
                with self.assertRaises(WledPlanError):
                    load_wled_plan(path)
                self.assertFalse(assess_wled_command("on", path).allowed)
        self.assertEqual(load_wled_plan().status, "planned")

    def test_cli_invariavel(self):
        for flags, message, expected in (
            ([], "Quem é você?", "J.A.R.V.I.S."),
            ([], "Ligue a luz da sala", "Não executei"),
            (["--llm", "--experimental-chat", "--provider", "openjarvis-local"],
             "Ligue a luz da sala", "canal=blocked"),
        ):
            with patch("sys.argv", ["room_chat_cli", *flags, message]), patch(
                "jarvis_room.provider_chat_adapter.RegistryChatAdapter.__call__",
                side_effect=AssertionError("Comando físico não pode chegar ao LLM"),
            ) as chat, redirect_stdout(StringIO()) as out:
                main()
            chat.assert_not_called()
            self.assertIn(expected, out.getvalue())
            self.assertIn("acao_verificada=false", out.getvalue())

    def test_inspecao_sem_trafego_externo(self):
        with patch("socket.socket", side_effect=AssertionError("Socket proibido")) as sock, patch(
            "socket.create_connection", side_effect=AssertionError("Conexão proibida")
        ) as connect, patch("subprocess.Popen", side_effect=AssertionError("Processo proibido")) as process:
            catalog_report()
            evaluate_request(AutomationRequest("room_main_lights", "turn_on", "test"))
            self.assertFalse(assess_hikvision_command("power_on").allowed)
            self.assertFalse(assess_wled_command("on").allowed)
            self.assertFalse(check_simulated_state("room_main_lights", "turn_on", FakeHATransport({"light.sala": "on"})).physical_action_verified)
        sock.assert_not_called()
        connect.assert_not_called()
        process.assert_not_called()
        for module in (ha_transport, ha_state_verifier, hikvision_plan, wled_plan):
            tree = ast.parse(inspect.getsource(module))
            imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
            imports += [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
            for name in imports:
                self.assertNotIn(name.split(".")[0], {"requests", "socket", "urllib", "httpx", "serial", "openjarvis", "ha_fakes"})
        self.assertFalse(hasattr(ha_transport, "FakeHATransport"))
