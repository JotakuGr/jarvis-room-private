import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from samsung_fakes import FAKE_TOKEN, FakeClock, SamsungHTTP
from jarvis_room.samsung_lab_cli import main
from jarvis_room.samsung_manual_policy import CONTROL_OPT_IN, READ_OPT_IN
from jarvis_room.samsung_rest_client import SamsungRESTClient


class TestSamsungLabCLI(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.token = Path(self.directory.name) / "secret.token"
        self.token.write_text(FAKE_TOKEN)
        self.token.chmod(0o600)
        self.audit = Path(self.directory.name) / "audit.jsonl"

    def run_cli(self, args=(), *, env=None, fake=None, tty=True, phrase="LIGAR SAMSUNG"):
        output, errors = StringIO(), StringIO()
        factory_calls = []
        clock = FakeClock()
        def client(**kwargs):
            factory_calls.append(kwargs)
            return SamsungRESTClient(**kwargs, opener=fake or SamsungHTTP())
        with patch.dict(os.environ, env or {}, clear=True), patch("sys.argv", ["samsung", *args]), redirect_stdout(output), redirect_stderr(errors), patch("sys.stdin.isatty", return_value=tty), patch("sys.stdout.isatty", return_value=tty), patch("builtins.input", return_value=phrase), patch("jarvis_room.samsung_lab_cli.SamsungRESTClient", side_effect=client), patch("jarvis_room.samsung_control.time.sleep", side_effect=clock.sleep), patch("jarvis_room.samsung_control.time.monotonic", side_effect=clock.monotonic):
            try:
                main()
                exit_code = 0
            except SystemExit as error:
                exit_code = error.code
        return exit_code, json.loads(output.getvalue()) if output.getvalue() else None, factory_calls

    def execute_args(self, action="turn_on"):
        return ["--execute", action, "--token-file", str(self.token), "--audit-file", str(self.audit)]

    def test_offline_sem_token_nem_rede(self):
        code, report, calls = self.run_cli()
        self.assertEqual(code, 0)
        self.assertFalse(report["execution_enabled"])
        self.assertEqual(calls, [])

    def test_read_exige_opt_in(self):
        code, report, calls = self.run_cli(["--read", "--token-file", str(self.token)])
        self.assertEqual(code, 1)
        self.assertEqual(report["error"], "manual_authorization_required")
        self.assertEqual(calls, [])

    def test_prazo_exige_execute_e_valida_limites_antes_de_rede(self):
        code, _, calls = self.run_cli(["--observation-timeout", "10"])
        self.assertEqual(code, 2)
        self.assertEqual(calls, [])
        for value in ("0", "31", "nan", "inf", "-1"):
            code, report, calls = self.run_cli([*self.execute_args(), "--observation-timeout", value])
            self.assertEqual(code, 1)
            self.assertEqual(report["error"], "invalid_configuration")
            self.assertEqual(calls, [])

    def test_prazo_configurado_produz_metricas_e_auditoria(self):
        fake = SamsungHTTP(tv_states=("off",))
        code, report, _ = self.run_cli([*self.execute_args(), "--observation-timeout", "10"], env={CONTROL_OPT_IN: "1"}, fake=fake)
        self.assertEqual(code, 1)
        self.assertEqual(report["observation"]["query_count"], 5)
        self.assertEqual(report["observation"]["elapsed_seconds"], 10)
        self.assertEqual(report["observation"]["timeout_seconds"], 10)
        self.assertEqual(report["observation"]["outcome"], "timed_out")
        self.assertTrue(report["command_sent"])
        self.assertEqual(sum(r.method == "POST" for r, _ in fake.calls), 1)
        event = json.loads(self.audit.read_text().splitlines()[-1])
        self.assertEqual(event["phase"], "observation_finished")
        self.assertEqual(event["observation"]["query_count"], 5)

    def test_read_faz_apenas_tres_gets(self):
        fake = SamsungHTTP()
        code, report, _ = self.run_cli(["--read", "--token-file", str(self.token)], env={READ_OPT_IN: "1"}, fake=fake)
        self.assertEqual(code, 0)
        self.assertTrue(report["scripts_present"])
        self.assertFalse(report["script_contents_verified"])
        self.assertEqual([r.method for r, _ in fake.calls], ["GET"] * 3)

    def test_execute_exige_opt_in_sem_rede(self):
        code, report, calls = self.run_cli(self.execute_args())
        self.assertEqual(code, 1)
        self.assertEqual(report["error"], "manual_authorization_required")
        self.assertEqual(calls, [])

    def test_execute_exige_terminal(self):
        code, report, calls = self.run_cli(self.execute_args(), env={CONTROL_OPT_IN: "1"}, tty=False)
        self.assertEqual(report["error"], "confirmation_required")
        self.assertEqual(calls, [])

    def test_execute_exige_frase_exata(self):
        code, report, calls = self.run_cli(self.execute_args(), env={CONTROL_OPT_IN: "1"}, phrase="sim")
        self.assertEqual(report["error"], "cancelled")
        self.assertEqual(calls, [])

    def test_execute_exige_token_e_auditoria(self):
        for args, expected in ((["--execute", "turn_on"], "audit_unavailable"), (["--execute", "turn_on", "--audit-file", str(self.audit)], "token_required")):
            code, report, calls = self.run_cli(args, env={CONTROL_OPT_IN: "1"})
            self.assertEqual(report["error"], expected)
            self.assertEqual(calls, [])

    def test_token_nao_pode_ser_destino_da_auditoria(self):
        contents = self.token.read_bytes()
        args = ["--execute", "turn_on", "--token-file", str(self.token), "--audit-file", str(self.token)]
        code, report, calls = self.run_cli(args, env={CONTROL_OPT_IN: "1"})
        self.assertEqual(code, 1)
        self.assertEqual(report["error"], "audit_unavailable")
        self.assertEqual(calls, [])
        self.assertEqual(self.token.read_bytes(), contents)

    def test_execucao_simulada_nunca_confirma_fisicamente(self):
        fake = SamsungHTTP(tv_states=("off", "on"))
        code, report, _ = self.run_cli(self.execute_args(), env={CONTROL_OPT_IN: "1"}, fake=fake)
        self.assertEqual(code, 0)
        self.assertTrue(report["command_sent"])
        self.assertTrue(report["reported_target_match"])
        self.assertFalse(report["physical_action_verified"])
        self.assertEqual(sum(r.method == "POST" for r, _ in fake.calls), 1)
        phases = [json.loads(line)["phase"] for line in self.audit.read_text().splitlines()]
        self.assertEqual(phases, ["authorized", "post_attempted", "post_accepted", "state_reported", "observation_finished"])
        self.assertNotIn(FAKE_TOKEN, self.audit.read_text())

    def test_post_timeout_incerto_sem_retry(self):
        fake = SamsungHTTP(post_error=TimeoutError(FAKE_TOKEN))
        code, report, _ = self.run_cli(self.execute_args(), env={CONTROL_OPT_IN: "1"}, fake=fake)
        self.assertEqual(code, 1)
        self.assertIsNone(report["command_sent"])
        self.assertEqual(report["command_delivery"], "unknown")
        self.assertEqual(sum(r.method == "POST" for r, _ in fake.calls), 1)

    def test_script_renomeado_e_auth_falham_sem_post(self):
        for fake in (SamsungHTTP(script_status=404), SamsungHTTP(status=401), SamsungHTTP(status=403)):
            code, report, _ = self.run_cli(self.execute_args(), env={CONTROL_OPT_IN: "1"}, fake=fake)
            self.assertEqual(code, 1)
            self.assertFalse(report["command_sent"])
            self.assertFalse(any(r.method == "POST" for r, _ in fake.calls))
            self.assertNotIn(FAKE_TOKEN, json.dumps(report))

    def test_cli_nao_aceita_url_servico_metodo_ou_yes(self):
        for flag in ("--url", "--service", "--method", "--yes", "--token"):
            code, report, calls = self.run_cli([flag, "arbitrary"])
            self.assertEqual(code, 2)
            self.assertEqual(calls, [])

    def test_bloqueio_preserva_llm_e_gateway(self):
        with patch("jarvis_room.control_gateway.RoomControlGateway.execute") as gateway, patch("jarvis_room.conversation_adapter.OpenJarvisConversation.__call__") as llm:
            self.run_cli()
            self.run_cli(self.execute_args())
            gateway.assert_not_called()
            llm.assert_not_called()
