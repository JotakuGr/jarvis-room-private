"""CLI exercitada com transporte HTTP falso e token fictício."""

import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from ha_lab_http_fakes import LabHTTP
from jarvis_room import ha_lab_cli
from jarvis_room.ha_lab_cli import build_report, main
from jarvis_room.ha_lab_readonly_client import BASE_URL, HALabAuthError, HALabReadOnlyClient

TEST_TOKEN = "unit-test-not-a-credential"


class TestHALabCLI(unittest.TestCase):
    def read_fake(self, fake):
        with patch.dict(os.environ, {"JARVIS_HA_LAB_READ": "1"}), patch(
            "sys.stdin.isatty", return_value=True
        ), patch("getpass.getpass", return_value=TEST_TOKEN), patch(
            "jarvis_room.ha_lab_cli.HALabReadOnlyClient",
            side_effect=lambda **kwargs: HALabReadOnlyClient(**kwargs, opener=fake),
        ):
            return build_report(read_lab=True)

    def test_modo_offline(self):
        with patch("socket.socket", side_effect=AssertionError("Sem rede")), patch(
            "jarvis_room.ha_lab_cli.HALabReadOnlyClient"
        ) as client, patch("getpass.getpass") as prompt, patch("sys.argv", ["ha_lab_cli"]), redirect_stdout(StringIO()) as out:
            main()
        report = json.loads(out.getvalue())
        self.assertEqual(report["mode"], "offline")
        self.assertEqual(report["status"], "read_disabled")
        client.assert_not_called()
        prompt.assert_not_called()

    def test_opt_in_ausente(self):
        with patch.dict(os.environ, {"JARVIS_HA_LAB_READ": "0"}), patch(
            "jarvis_room.ha_lab_cli.HALabReadOnlyClient"
        ) as client, patch("getpass.getpass") as prompt:
            self.assertEqual(build_report(read_lab=True)["status"], "opt_in_required")
        client.assert_not_called()
        prompt.assert_not_called()

    def test_opt_in_sem_token_e_arquivo_privado(self):
        with patch.dict(os.environ, {"JARVIS_HA_LAB_READ": "1"}), patch(
            "sys.stdin.isatty", return_value=True
        ), patch("getpass.getpass", return_value=""), patch(
            "jarvis_room.ha_lab_cli.HALabReadOnlyClient"
        ) as client:
            self.assertEqual(build_report(read_lab=True)["status"], "token_required")
        client.assert_not_called()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "private.txt"
            path.write_text(TEST_TOKEN)
            path.chmod(0o644)
            with self.assertRaises(HALabAuthError):
                ha_lab_cli._read_token_file(path)
            path.chmod(0o600)
            self.assertEqual(ha_lab_cli._read_token_file(path), TEST_TOKEN)
            with patch.object(ha_lab_cli, "REPOSITORY_ROOT", Path(directory)):
                with self.assertRaises(HALabAuthError):
                    ha_lab_cli._read_token_file(path)

    def test_url_fixa(self):
        fake = LabHTTP()
        self.assertTrue(self.read_fake(fake)["connected"])
        self.assertEqual([request.full_url for request, _ in fake.calls], [BASE_URL + "/api/", BASE_URL + "/api/states/input_boolean.jarvis_lab_light"])
        for flags in (["--url", "http://invalid.example"], ["--method", "POST"], ["--endpoint", "/api/services"]):
            with patch("sys.argv", ["ha_lab_cli", *flags]), redirect_stderr(StringIO()), self.assertRaises(SystemExit):
                main()

    def test_get_helper(self):
        for state in ("on", "off"):
            fake = LabHTTP(state)
            report = self.read_fake(fake)
            self.assertEqual(report["state"], state)
            self.assertEqual(report["mode"], "read_only_lab")
            self.assertEqual(report["status"], "read_ok")
            self.assertFalse(report["physical_action_verified"])
            self.assertTrue(all(request.method == "GET" for request, _ in fake.calls))

    def test_falhas_401_403_timeout(self):
        for fake, expected in ((LabHTTP(status=401), "auth_error"), (LabHTTP(status=403), "auth_error"), (LabHTTP(error=TimeoutError(TEST_TOKEN)), "unavailable")):
            report = self.read_fake(fake)
            self.assertEqual(report["status"], expected)
            self.assertFalse(report["physical_action_verified"])
            self.assertNotIn(TEST_TOKEN, json.dumps(report))

    def test_json_sanitizado(self):
        fake = LabHTTP()
        fake.state_payload["attributes"] = {"private": TEST_TOKEN}
        report = self.read_fake(fake)
        self.assertNotIn(TEST_TOKEN, json.dumps(report))
        self.assertEqual(set(report), {"mode", "connected", "entity_id", "state", "status", "physical_action_verified"})
        self.assertEqual(self.read_fake(LabHTTP(raw=b"{"))["status"], "invalid_response")

    def test_nenhuma_chamada_llm_gateway(self):
        with patch("jarvis_room.control_gateway.RoomControlGateway.execute", side_effect=AssertionError("Gateway proibido")) as gateway, patch(
            "jarvis_room.provider_chat_adapter.RegistryChatAdapter.__call__", side_effect=AssertionError("LLM proibido")
        ) as chat:
            self.assertEqual(self.read_fake(LabHTTP())["status"], "read_ok")
        gateway.assert_not_called()
        chat.assert_not_called()
