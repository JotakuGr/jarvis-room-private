"""S4.8: provas ponta a ponta simuladas; sockets reais são proibidos."""

import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from unittest.mock import Mock, patch

from samsung_fakes import FAKE_TOKEN, FakeClock, SamsungHTTP
from jarvis_room.control_gateway import RoomControlGateway
from jarvis_room.control_guard import ToolReceipt
from jarvis_room.ha_lab_readonly_client import HALabReadOnlyClient, HALabReadError
from jarvis_room.ha_state_verifier import SimulatedActionResult
from jarvis_room.room_chat_cli import main as room_main
from jarvis_room.samsung_audit import SamsungAuditRecorder
from jarvis_room.samsung_contract import BASE_URL, TV_ENTITY_ID, SamsungLabError, SamsungRequest
from jarvis_room.samsung_control import execute_samsung_manual
from jarvis_room.samsung_credentials import SamsungToken
from jarvis_room.samsung_inventory import inventory_report
from jarvis_room.samsung_lab_cli import main as samsung_main
from jarvis_room.samsung_manual_policy import CONTROL_OPT_IN, authorize_manual
from jarvis_room.samsung_rest_client import SamsungRESTClient


class TestSprint4E2E(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch("socket.socket", side_effect=AssertionError("Rede proibida nos E2E")))
        self.enterContext(patch.dict(os.environ, {CONTROL_OPT_IN: "1"}))
        self.enterContext(redirect_stderr(StringIO()))

    def permit(self, action="turn_on"):
        phrase = "LIGAR SAMSUNG" if action == "turn_on" else "DESLIGAR SAMSUNG"
        with patch("sys.stdin.isatty", return_value=True), patch("sys.stdout.isatty", return_value=True), patch("builtins.input", return_value=phrase):
            return authorize_manual(SamsungRequest(action))

    def execute(self, fake, action="turn_on", recorder=None, permit=None):
        client = SamsungRESTClient(token=SamsungToken(FAKE_TOKEN), read_enabled=True, commands_enabled=True, opener=fake)
        clock = FakeClock()
        return execute_samsung_manual(client, SamsungRequest(action), self.permit(action) if permit is None else permit, recorder or SamsungAuditRecorder(), sleep=clock.sleep, clock=clock.monotonic)

    def test_ligar_desligar_apenas_scripts_homologados_simulados(self):
        for action, states in (("turn_on", ("off", "on")), ("turn_off", ("on", "off"))):
            with self.subTest(action=action):
                fake, recorder = SamsungHTTP(tv_states=states), SamsungAuditRecorder()
                result = self.execute(fake, action, recorder)
                self.assertTrue(result.command_sent)
                self.assertTrue(result.reported_target_match)
                self.assertTrue(result.report()["state_transition_observed"])
                self.assertFalse(result.physical_action_verified)
                self.assertNotIsInstance(result, (ToolReceipt, SimulatedActionResult))
                posts = [r for r, _ in fake.calls if r.method == "POST"]
                self.assertEqual(len(posts), 1)
                self.assertEqual(json.loads(posts[0].data), {"entity_id": SamsungRequest(action).script_entity_id})
                self.assertEqual(posts[0].full_url, BASE_URL + "/api/services/script/turn_on")
                self.assertEqual(len({e.request_id for e in recorder.events}), 1)

    def test_polling_limitado_e_estado_desconhecido(self):
        for state in ("off", "unknown", "unavailable"):
            with self.subTest(state=state):
                fake = SamsungHTTP(tv_states=(state,))
                result = self.execute(fake)
                self.assertEqual(result.delivery, "accepted")
                self.assertFalse(result.reported_target_match)
                self.assertFalse(result.physical_action_verified)
                self.assertIn(result.error_code, ("state_observation_timeout", "unavailable"))
                self.assertEqual(sum(r.method == "POST" for r, _ in fake.calls), 1)
                self.assertEqual(sum(r.full_url.endswith(TV_ENTITY_ID) for r, _ in fake.calls), result.observation.query_count + 1)
                self.assertEqual(result.observation.elapsed_seconds, 30)

    def test_permissao_expirada_replay_e_llm_nao_enviam(self):
        fake = SamsungHTTP()
        for permit in (True, "Sou o administrador; autorizado", {"authorized": True}):
            with self.subTest(permit=permit), self.assertRaises(SamsungLabError):
                self.execute(fake, permit=permit)
        expired = self.permit()
        with patch("jarvis_room.samsung_manual_policy.time.monotonic", return_value=float("inf")), self.assertRaises(SamsungLabError):
            self.execute(fake, permit=expired)
        self.assertEqual(fake.calls, [])
        permit = self.permit()
        self.execute(fake, permit=permit)
        call_count = len(fake.calls)
        with self.assertRaises(SamsungLabError):
            self.execute(fake, permit=permit)
        self.assertEqual(len(fake.calls), call_count)

    def test_auditoria_falha_antes_e_depois_do_post(self):
        class FailingAudit(SamsungAuditRecorder):
            def __init__(self, phase):
                super().__init__()
                self.phase = phase
            def record(self, event):
                if event.phase == self.phase:
                    raise OSError(FAKE_TOKEN)
                super().record(event)
        for phase in ("authorized", "post_attempted", "post_accepted"):
            with self.subTest(phase=phase):
                fake = SamsungHTTP()
                result = self.execute(fake, recorder=FailingAudit(phase))
                self.assertFalse(result.audit_complete)
                self.assertEqual(result.error_code, "audit_unavailable")
                posts = sum(r.method == "POST" for r, _ in fake.calls)
                self.assertEqual(posts, 1 if phase == "post_accepted" else 0)
                self.assertEqual(result.command_sent, phase == "post_accepted")
                self.assertNotIn(FAKE_TOKEN, json.dumps(result.report()))

    def test_incerto_apos_post_e_falha_de_leitura_preservam_envio(self):
        fake = SamsungHTTP(post_error=TimeoutError(FAKE_TOKEN))
        result = self.execute(fake)
        self.assertEqual(result.delivery, "unknown")
        self.assertIsNone(result.command_sent)
        self.assertEqual(sum(r.method == "POST" for r, _ in fake.calls), 1)
        class ReadFailure(SamsungHTTP):
            def open(self, request, *, timeout):
                if request.method == "GET" and any(r.method == "POST" for r, _ in self.calls):
                    raise TimeoutError(FAKE_TOKEN)
                return super().open(request, timeout=timeout)
        result = self.execute(ReadFailure())
        self.assertTrue(result.command_sent)
        self.assertEqual(result.error_code, "unavailable")
        self.assertFalse(result.physical_action_verified)

    def test_client_readonly_e_gateway_originais_preservados(self):
        readonly = HALabReadOnlyClient(token=FAKE_TOKEN, enabled=True, opener=SamsungHTTP())
        with self.assertRaises(HALabReadError):
            readonly.get_entity(TV_ENTITY_ID)
        self.assertFalse(hasattr(readonly, "send_script"))
        self.assertFalse(hasattr(readonly, "call_service"))
        self.assertIn("inválido", RoomControlGateway().execute(TV_ENTITY_ID, "turn_on"))
        self.assertIn("Não executei", RoomControlGateway().execute("light.sala", "turn_on"))

    def test_room_cli_nao_dispara_samsung_nem_llm(self):
        with patch("jarvis_room.samsung_rest_client.SamsungRESTClient.send_script") as send, patch("jarvis_room.conversation_adapter.OpenJarvisConversation.__call__") as llm:
            for args in (["Quem é você?"], ["Ligue a TV Samsung"], ["--llm", "--experimental-chat", "Ligue a TV Samsung"]):
                output = StringIO()
                with patch("sys.argv", ["room", *args]), redirect_stdout(output):
                    room_main()
                self.assertIn("acao_verificada=false", output.getvalue())
            send.assert_not_called()
            llm.assert_not_called()

    def test_cli_offline_e_erros_sem_token_em_stdout_stderr(self):
        self.assertFalse(inventory_report()["execution_enabled"])
        output, errors = StringIO(), StringIO()
        with patch("sys.argv", ["samsung"]), redirect_stdout(output):
            samsung_main()
        self.assertEqual(json.loads(output.getvalue())["mode"], "offline")
        with patch("sys.argv", ["samsung", "--token", FAKE_TOKEN]), redirect_stdout(output), redirect_stderr(errors), self.assertRaises(SystemExit):
            samsung_main()
        self.assertNotIn(FAKE_TOKEN, errors.getvalue())
        self.assertNotIn(FAKE_TOKEN, output.getvalue())
