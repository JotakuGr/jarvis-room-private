import json
import unittest
from unittest.mock import patch

from samsung_fakes import SamsungHTTP
from samsung_natural_fakes import NaturalEnvironment
from jarvis_room.samsung_contract import SamsungLabError, SamsungRequest
from jarvis_room.samsung_manual_policy import authorize_manual
from jarvis_room.samsung_natural_control import execute_natural_intent
from jarvis_room.samsung_natural_intent import parse_samsung_intent


class TestSamsungNaturalControl(unittest.TestCase):
    def setUp(self):
        self.intent = parse_samsung_intent("Jarvis, ligue a TV Samsung")

    def test_reutiliza_controlador_e_um_post(self):
        with NaturalEnvironment() as env:
            result = env.execute(self.intent)
            self.assertTrue(result.command_sent)
            self.assertTrue(result.reported_target_match)
            self.assertFalse(result.physical_action_verified)
            self.assertEqual(sum(r.method == "POST" for r, _ in env.http.calls), 1)
            events = [json.loads(line) for line in env.audit_file.read_text().splitlines()]
            self.assertEqual([e["phase"] for e in events].count("authorized"), 1)
            self.assertEqual([e["phase"] for e in events].count("post_attempted"), 1)
            self.assertEqual(len({e["request_id"] for e in events}), 1)

    def test_desligar_reutiliza_script_correto(self):
        with NaturalEnvironment(fake=SamsungHTTP(tv_states=("on", "off")), phrase="DESLIGAR SAMSUNG") as env:
            result = env.execute(parse_samsung_intent("Desligue a televisão"))
            self.assertTrue(result.reported_target_match)
            post = next(r for r, _ in env.http.calls if r.method == "POST")
            self.assertEqual(json.loads(post.data), {"entity_id": "script.jarvis_desligar_samsung"})

    def test_texto_dict_e_intencao_bloqueada_nao_executam(self):
        with NaturalEnvironment() as env:
            for intent in ("Ligue a TV", {"action": "turn_on", "authorized": True}, parse_samsung_intent("Não ligue a TV"), None):
                with self.subTest(intent=type(intent)), self.assertRaisesRegex(SamsungLabError, "invalid_action"):
                    env.execute(intent)
            env.prompt.assert_not_called()
            env.factory.assert_not_called()

    def test_falta_opt_in(self):
        with NaturalEnvironment(opt_in=False) as env:
            with self.assertRaisesRegex(SamsungLabError, "manual_authorization_required"):
                env.execute(self.intent)
            env.prompt.assert_not_called()
            self.assertEqual(env.http.calls, [])

    def test_terminal_nao_interativo(self):
        with NaturalEnvironment(tty=False) as env:
            with self.assertRaisesRegex(SamsungLabError, "confirmation_required"):
                env.execute(self.intent)
            env.prompt.assert_not_called()
            self.assertEqual(env.http.calls, [])

    def test_confirmacao_incorreta_e_cancelamento(self):
        with NaturalEnvironment(phrase="sim") as env:
            with self.assertRaisesRegex(SamsungLabError, "cancelled"):
                env.execute(self.intent)
            env.prompt.side_effect = KeyboardInterrupt()
            with self.assertRaisesRegex(SamsungLabError, "cancelled"):
                env.execute(self.intent)
            self.assertEqual(env.http.calls, [])

    def test_permissao_expirada(self):
        with NaturalEnvironment() as env:
            permit = authorize_manual(SamsungRequest("turn_on"))
            env.clock.sleep(61)
            with patch("jarvis_room.samsung_natural_control.authorize_manual", return_value=permit), self.assertRaisesRegex(SamsungLabError, "manual_authorization_required"):
                env.execute(self.intent)
            self.assertEqual(env.http.calls, [])

    def test_permissao_reutilizada_negada_sem_outro_post(self):
        with NaturalEnvironment() as env:
            permit = authorize_manual(SamsungRequest("turn_on"))
            with patch("jarvis_room.samsung_natural_control.authorize_manual", return_value=permit):
                env.execute(self.intent)
                count = len(env.http.calls)
                with self.assertRaises(SamsungLabError):
                    env.execute(self.intent)
            self.assertEqual(len(env.http.calls), count)
            self.assertEqual(sum(r.method == "POST" for r, _ in env.http.calls), 1)

    def test_token_invalido(self):
        with NaturalEnvironment() as env:
            env.token_file.chmod(0o644)
            with self.assertRaisesRegex(SamsungLabError, "token_required"):
                env.execute(self.intent)
            self.assertEqual(env.http.calls, [])

    def test_script_ausente_nao_faz_fallback(self):
        with NaturalEnvironment(fake=SamsungHTTP(script_status=404)) as env:
            result = env.execute(self.intent)
            self.assertEqual(result.error_code, "not_found")
            self.assertFalse(result.command_sent)
            self.assertFalse(any(r.method == "POST" for r, _ in env.http.calls))

    def test_http_auth_error_preserva_bloqueio(self):
        with NaturalEnvironment(fake=SamsungHTTP(status=401)) as env:
            result = env.execute(self.intent)
            self.assertEqual(result.error_code, "auth_error")
            self.assertFalse(result.command_sent)

    def test_post_incerto_nao_repetido(self):
        with NaturalEnvironment(fake=SamsungHTTP(post_error=TimeoutError("private"))) as env:
            result = env.execute(self.intent)
            self.assertIsNone(result.command_sent)
            self.assertEqual(result.observation.outcome, "not_started")
            self.assertEqual(sum(r.method == "POST" for r, _ in env.http.calls), 1)

    def test_timeout_observacao_preserva_aceite(self):
        with NaturalEnvironment(fake=SamsungHTTP(tv_states=("off",))) as env:
            result = env.execute(self.intent, observation_timeout=5)
            self.assertTrue(result.command_sent)
            self.assertEqual(result.observation.outcome, "timed_out")
            self.assertEqual(result.observation.elapsed_seconds, 5)
            self.assertFalse(result.physical_action_verified)

    def test_auditoria_indisponivel(self):
        with NaturalEnvironment() as env:
            env.audit_file.touch(mode=0o644)
            with self.assertRaisesRegex(SamsungLabError, "audit_unavailable"):
                env.execute(self.intent)
            self.assertEqual(env.http.calls, [])

    def test_configuracao_invalida_antes_de_confirmar(self):
        with NaturalEnvironment() as env:
            for timeout in (0, 31, True, float("nan")):
                with self.assertRaises(SamsungLabError):
                    env.execute(self.intent, observation_timeout=timeout)
            with self.assertRaises(SamsungLabError):
                execute_natural_intent(self.intent, token_file=env.token_file, audit_file=env.token_file)
            env.prompt.assert_not_called()
            self.assertEqual(env.http.calls, [])
