import json
import unittest
from unittest.mock import patch

from samsung_fakes import FAKE_TOKEN, SamsungHTTP
from samsung_natural_fakes import NaturalEnvironment
from jarvis_room.samsung_text_cli import main, process_natural_message


class TestSamsungTextCLI(unittest.TestCase):
    def run_cli(self, env, args):
        with patch("sys.argv", ["samsung_text", *args]):
            try:
                main()
                code = 0
            except SystemExit as error:
                code = error.code
        raw = env.stdout.getvalue()
        return code, json.loads(raw) if raw else None

    def execute_args(self, env, message="Jarvis, ligue a TV"):
        return ["--execute", "--token-file", str(env.token_file), "--audit-file", str(env.audit_file), message]

    def test_preview_sem_credenciais_autorizacao_ou_rede(self):
        with NaturalEnvironment() as env, patch("jarvis_room.samsung_natural_control.authorize_manual") as authorize, patch("jarvis_room.samsung_natural_control.load_samsung_token") as token:
            code, report = self.run_cli(env, ["Jarvis, ligue a televisão Samsung."])
            self.assertEqual(code, 0)
            self.assertEqual(report["mode"], "samsung_text_preview")
            self.assertEqual(report["intent"]["action"], "turn_on")
            self.assertIsNone(report["result"])
            self.assertFalse(report["action_verified"])
            authorize.assert_not_called()
            token.assert_not_called()
            env.factory.assert_not_called()

    def test_preview_nao_reconhecido_sem_eco_de_segredos(self):
        with NaturalEnvironment() as env:
            code, report = self.run_cli(env, ["Bearer private-value; ligue a TV"])
            self.assertEqual(code, 1)
            self.assertEqual(report["response"]["status"], "unsupported")
            self.assertNotIn("private-value", env.stdout.getvalue())
            self.assertEqual(env.http.calls, [])

    def test_execucao_manual_simulada(self):
        with NaturalEnvironment() as env:
            code, report = self.run_cli(env, self.execute_args(env))
            self.assertEqual(code, 0)
            self.assertEqual(report["response"]["status"], "ha_state_reported")
            self.assertTrue(report["result"]["command_sent"])
            self.assertFalse(report["physical_action_verified"])
            self.assertEqual(sum(r.method == "POST" for r, _ in env.http.calls), 1)

    def test_falta_opt_in_ou_terminal(self):
        for options in ({"opt_in": False}, {"tty": False}):
            with NaturalEnvironment(**options) as env:
                code, report = self.run_cli(env, self.execute_args(env))
                self.assertEqual(code, 1)
                self.assertEqual(report["response"]["status"], "not_authorized")
                self.assertEqual(env.http.calls, [])

    def test_negacao_com_execute_nem_solicita_autorizacao(self):
        with NaturalEnvironment() as env:
            code, report = self.run_cli(env, self.execute_args(env, "Jarvis, não ligue a TV"))
            self.assertEqual(code, 1)
            env.prompt.assert_not_called()
            self.assertEqual(env.http.calls, [])

    def test_confirmacao_incorreta(self):
        with NaturalEnvironment(phrase="sim") as env:
            code, report = self.run_cli(env, self.execute_args(env))
            self.assertEqual(code, 1)
            self.assertEqual(report["error"], "cancelled")
            self.assertEqual(env.http.calls, [])

    def test_opcoes_exigem_execute(self):
        for args in (["--token-file", "/tmp/fake", "Ligue a TV"], ["--audit-file", "/tmp/fake", "Ligue a TV"], ["--observation-timeout", "5", "Ligue a TV"]):
            with NaturalEnvironment() as env:
                code, report = self.run_cli(env, args)
                self.assertEqual(code, 2)
                self.assertIsNone(report)
                self.assertEqual(env.http.calls, [])

    def test_argumentos_sensiveis_nao_ecoam(self):
        for flag in ("--token", "--url", "--service", "--yes", "--exec"):
            with NaturalEnvironment() as env:
                code, _ = self.run_cli(env, [flag, "secret-value", "Ligue a TV"])
                self.assertEqual(code, 2)
                self.assertNotIn("secret-value", env.stderr.getvalue())

    def test_erro_interno_sanitizado(self):
        with NaturalEnvironment() as env, patch("jarvis_room.samsung_text_cli.execute_natural_intent", side_effect=RuntimeError(FAKE_TOKEN)):
            code, report = self.run_cli(env, self.execute_args(env))
            self.assertEqual(code, 1)
            self.assertEqual(report["error"], "operation_failed")
            self.assertNotIn(FAKE_TOKEN, env.stdout.getvalue() + env.stderr.getvalue())

    def test_post_incerto_nao_diz_que_nada_foi_enviado(self):
        with NaturalEnvironment(fake=SamsungHTTP(post_error=TimeoutError("private"))) as env:
            code, report = self.run_cli(env, self.execute_args(env))
            self.assertEqual(code, 1)
            self.assertEqual(report["response"]["status"], "delivery_uncertain")
            self.assertIsNone(report["result"]["command_sent"])

    def test_prazo_personalizado_e_timeout(self):
        with NaturalEnvironment(fake=SamsungHTTP(tv_states=("off",))) as env:
            code, report = self.run_cli(env, [*self.execute_args(env), "--observation-timeout", "5"])
            self.assertEqual(code, 1)
            self.assertEqual(report["result"]["observation"]["timeout_seconds"], 5)
            self.assertEqual(report["response"]["status"], "state_unconfirmed")

    def test_execute_de_tipo_invalido_nao_inicia_fluxo(self):
        with NaturalEnvironment() as env:
            report = process_natural_message("Ligue a TV", execute="true")
            self.assertEqual(report["error"], "invalid_configuration")
            self.assertEqual(env.http.calls, [])
