"""E2E com GET simulado; zero instância HA, LLM ou equipamento real."""

import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from ha_lab_http_fakes import LabHTTP
from jarvis_room.control_gateway import RoomControlGateway
from jarvis_room.control_guard import ToolReceipt
from jarvis_room.ha_lab_cli import build_report, main as lab_main
from jarvis_room.ha_lab_readonly_client import DEFAULT_ENTITY_ID, HALabReadError, HALabReadOnlyClient
from jarvis_room.ha_lab_state import parse_lab_state
from jarvis_room.ha_state_verifier import SimulatedActionResult
from jarvis_room.hikvision_readiness import (
    DEFAULT_PATH as HIKVISION_PATH, HikvisionReadinessError, load_hikvision_readiness,
)
from jarvis_room.room_chat_cli import main as room_main
from jarvis_room.wled_readiness import (
    DEFAULT_PATH as WLED_PATH, WledReadinessError, load_wled_readiness, readiness_report,
)

TEST_TOKEN = "unit-test-not-a-credential"


class TestSprint3E2E(unittest.TestCase):
    def read(self, fake):
        with patch.dict(os.environ, {"JARVIS_HA_LAB_READ": "1"}), patch("sys.stdin.isatty", return_value=True), patch("getpass.getpass", return_value=TEST_TOKEN), patch(
            "jarvis_room.ha_lab_cli.HALabReadOnlyClient",
            side_effect=lambda **kwargs: HALabReadOnlyClient(**kwargs, opener=fake),
        ):
            return build_report(read_lab=True)

    def test_desabilitado_por_padrao(self):
        with patch("socket.socket", side_effect=AssertionError("Sem rede")) as network, patch("sys.argv", ["ha_lab_cli"]), redirect_stdout(StringIO()) as out:
            lab_main()
        report = json.loads(out.getvalue())
        self.assertEqual(report["status"], "read_disabled")
        self.assertFalse(report["connected"])
        network.assert_not_called()

    def test_opt_in_indevido(self):
        with patch("jarvis_room.ha_lab_cli.HALabReadOnlyClient") as client:
            with patch.dict(os.environ, {"JARVIS_HA_LAB_READ": "0"}):
                self.assertEqual(build_report(read_lab=True)["status"], "opt_in_required")
            with patch.dict(os.environ, {"JARVIS_HA_LAB_READ": "1"}), patch("sys.stdin.isatty", return_value=False):
                self.assertEqual(build_report(read_lab=True)["status"], "token_required")
        client.assert_not_called()

    def test_helper_virtual_get_fake(self):
        for state in ("on", "off"):
            fake = LabHTTP(state)
            report = self.read(fake)
            self.assertEqual(report["status"], "read_ok")
            self.assertEqual(report["state"], state)
            self.assertFalse(report["physical_action_verified"])
            self.assertEqual(len(fake.calls), 2)
            self.assertTrue(all(request.method == "GET" for request, _ in fake.calls))

    def test_erros_seguros(self):
        for fake, status in (
            (LabHTTP(status=401), "auth_error"), (LabHTTP(status=403), "auth_error"),
            (LabHTTP(error=TimeoutError(TEST_TOKEN)), "unavailable"),
            (LabHTTP(status=302), "redirect_rejected"),
            (LabHTTP(redirect_url="https://invalid.example"), "redirect_rejected"),
            (LabHTTP(raw=b"{"), "invalid_response"),
        ):
            report = self.read(fake)
            self.assertEqual(report["status"], status)
            rendered = json.dumps(report)
            self.assertNotIn(TEST_TOKEN, rendered)
            self.assertNotIn("Traceback", rendered)
            self.assertNotIn("Authorization", rendered)
            self.assertFalse(report["physical_action_verified"])

    def test_alvo_diferente_recusado_antes_http(self):
        fake = LabHTTP()
        client = HALabReadOnlyClient(token=TEST_TOKEN, enabled=True, opener=fake)
        for entity in ("light.sala", "input_boolean.jarvis_lab_other", "http://invalid.example", "media_player.hikvision"):
            with self.assertRaises(HALabReadError):
                client.get_entity(entity)
        self.assertEqual(fake.calls, [])

    def test_inexistencia_controle_fisico(self):
        for method in ("post", "call_service", "perform_and_verify", "set_state", "request"):
            self.assertFalse(hasattr(HALabReadOnlyClient, method))
        state = parse_lab_state({"entity_id": DEFAULT_ENTITY_ID, "state": "on"}, DEFAULT_ENTITY_ID)
        self.assertNotIsInstance(state, ToolReceipt)
        self.assertNotIsInstance(state, SimulatedActionResult)
        self.assertFalse(state.physical_action_verified)
        self.assertIn("Não executei", RoomControlGateway().execute("light.sala", "turn_on"))

    def test_room_cli_preservada(self):
        for flags, message, expected in (
            ([], "Quem é você?", "J.A.R.V.I.S."),
            ([], "Ligue a luz da sala", "Não executei"),
            (["--llm", "--experimental-chat", "--provider", "openjarvis-local"], "Ligue a luz da sala", "canal=blocked"),
        ):
            with patch("sys.argv", ["room_chat_cli", *flags, message]), patch(
                "jarvis_room.openjarvis_provider.OpenJarvisConversation", side_effect=AssertionError("LLM proibido")
            ) as llm, patch("jarvis_room.ha_lab_readonly_client.HALabReadOnlyClient.ping", side_effect=AssertionError("GET proibido")) as http, redirect_stdout(StringIO()) as out:
                room_main()
            self.assertIn(expected, out.getvalue())
            self.assertIn("acao_verificada=false", out.getvalue())
            llm.assert_not_called()
            http.assert_not_called()

    def test_hikvision_wled_planejados(self):
        self.assertEqual(load_hikvision_readiness().status, "planned")
        self.assertFalse(load_hikvision_readiness().control_verified)
        report = readiness_report()
        self.assertEqual(report["status"], "planned")
        self.assertFalse(report["power_design_verified"])
        self.assertIsNone(report["power_supply_count"])
        for source, flag, loader, error in (
            (HIKVISION_PATH, "control_verified", load_hikvision_readiness, HikvisionReadinessError),
            (WLED_PATH, "physical_control_enabled", load_wled_readiness, WledReadinessError),
        ):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "plan.json"
                data = json.loads(source.read_text())
                data[flag] = True
                path.write_text(json.dumps(data))
                with self.assertRaises(error):
                    loader(path)
