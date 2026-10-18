import ast
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from samsung_fakes import FAKE_TOKEN
from samsung_natural_fakes import NaturalEnvironment
from jarvis_room.samsung_audit import PrivateSamsungAudit
from jarvis_room.samsung_contract import SamsungLabError
from jarvis_room.samsung_control import execute_samsung_manual
from jarvis_room.samsung_manual_policy import authorize_manual
from jarvis_room.samsung_natural_control import execute_natural_intent
from jarvis_room.samsung_natural_intent import parse_samsung_intent
from jarvis_room.samsung_text_cli import process_natural_message


class TestSamsungNaturalSecurity(unittest.TestCase):
    def test_intencao_adulterada_revalidada_antes_de_autorizar(self):
        with NaturalEnvironment() as env:
            for field, value in (("entity_id", "light.sala"), ("action", "turn_off"), ("phrase", "ligue todas as tvs"), ("recognized", 1)):
                intent = parse_samsung_intent("Ligue a TV")
                object.__setattr__(intent, field, value)
                with self.subTest(field=field), self.assertRaises(SamsungLabError):
                    env.execute(intent)
            env.prompt.assert_not_called()
            self.assertEqual(env.http.calls, [])

    def test_sem_token_em_resposta_auditoria_ou_urls(self):
        with NaturalEnvironment() as env:
            report = process_natural_message("Jarvis, ligue a TV", execute=True, token_file=env.token_file, audit_file=env.audit_file)
            self.assertNotIn(FAKE_TOKEN, json.dumps(report))
            self.assertNotIn(FAKE_TOKEN, env.audit_file.read_text())
            self.assertNotIn(FAKE_TOKEN, env.stdout.getvalue() + env.stderr.getvalue())
            for request, _ in env.http.calls:
                self.assertNotIn(FAKE_TOKEN, request.full_url)
                self.assertNotIn(FAKE_TOKEN.encode(), request.data or b"")

    def test_mesma_autorizacao_controlador_e_correlacao_sem_duplicar(self):
        with NaturalEnvironment() as env, patch("jarvis_room.samsung_natural_control.authorize_manual", wraps=authorize_manual) as authorize, patch("jarvis_room.samsung_natural_control.execute_samsung_manual", wraps=execute_samsung_manual) as controller:
            env.execute(parse_samsung_intent("Ligue a TV"))
            authorize.assert_called_once()
            controller.assert_called_once()
            events = [json.loads(line) for line in env.audit_file.read_text().splitlines()]
            self.assertEqual(sum(e["phase"] == "authorized" for e in events), 1)
            self.assertEqual(sum(e["phase"] == "post_accepted" for e in events), 1)
            self.assertEqual(sum(e["phase"] == "observation_finished" for e in events), 1)
            self.assertEqual(len({e["request_id"] for e in events}), 1)
            summary = events[-1]["observation"]
            self.assertEqual(summary["outcome"], "matched")
            self.assertFalse(events[-1]["physical_action_verified"])

    def test_token_e_auditoria_nao_compartilham_arquivo(self):
        with NaturalEnvironment() as env:
            before = env.token_file.read_bytes()
            with self.assertRaisesRegex(SamsungLabError, "audit_unavailable"):
                execute_natural_intent(parse_samsung_intent("Ligue a TV"), token_file=env.token_file, audit_file=env.token_file)
            self.assertEqual(env.token_file.read_bytes(), before)
            env.prompt.assert_not_called()
            self.assertEqual(env.http.calls, [])

    def test_symlink_de_token_recusado_pelo_loader_existente(self):
        with NaturalEnvironment() as env:
            linked = env.token_file.with_name("linked.token")
            linked.symlink_to(env.token_file)
            with self.assertRaisesRegex(SamsungLabError, "token_required"):
                execute_natural_intent(parse_samsung_intent("Ligue a TV"), token_file=linked, audit_file=env.audit_file)
            self.assertEqual(env.http.calls, [])

    def test_falha_de_configuracao_bloqueia_antes_do_prompt(self):
        with NaturalEnvironment() as env, patch("jarvis_room.samsung_natural_control.load_samsung_inventory", side_effect=SamsungLabError("invalid_inventory")):
            report = process_natural_message("Ligue a TV", execute=True, token_file=env.token_file, audit_file=env.audit_file)
            self.assertEqual(report["error"], "invalid_inventory")
            env.prompt.assert_not_called()
            self.assertEqual(env.http.calls, [])

    def test_falha_ao_fechar_auditoria_preserva_envio(self):
        original = PrivateSamsungAudit.__exit__
        def failing_exit(self, *args):
            original(self, *args)
            raise OSError(FAKE_TOKEN)
        with NaturalEnvironment() as env, patch.object(PrivateSamsungAudit, "__exit__", failing_exit):
            report = process_natural_message("Ligue a TV", execute=True, token_file=env.token_file, audit_file=env.audit_file)
            self.assertTrue(report["result"]["command_sent"])
            self.assertFalse(report["result"]["audit_complete"])
            self.assertEqual(report["response"]["status"], "audit_incomplete")
            self.assertNotIn(FAKE_TOKEN, json.dumps(report))
            self.assertEqual(sum(r.method == "POST" for r, _ in env.http.calls), 1)

    def test_erros_de_configuracao_de_caminhos_nao_abrem_cliente(self):
        with NaturalEnvironment() as env:
            for paths in ((None, env.audit_file), (env.token_file, None), (str(env.token_file), env.audit_file)):
                with self.subTest(paths=tuple(type(x) for x in paths)), self.assertRaises(SamsungLabError):
                    execute_natural_intent(parse_samsung_intent("Ligue a TV"), token_file=paths[0], audit_file=paths[1])
            env.factory.assert_not_called()

    def test_novos_modulos_nao_criam_transporte_ou_processos(self):
        source = Path(__file__).resolve().parents[1] / "src/jarvis_room"
        for name in ("samsung_natural_control", "samsung_natural_intent", "samsung_natural_responses", "samsung_text_cli"):
            tree = ast.parse((source / (name + ".py")).read_text())
            modules = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    modules.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    modules.append(node.module)
            self.assertFalse(any(module.split(".")[0] in {"urllib", "requests", "http", "socket", "subprocess", "openjarvis"} for module in modules))
