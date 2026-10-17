"""Testes offline de observabilidade dos provedores."""

import json
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import FrozenInstanceError, asdict
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from jarvis_room.experimental_chat import answer_informational_question
from jarvis_room.inference_policy import InferenceDecision, LocalInferenceUnavailable
from jarvis_room.provider_chat_adapter import RegistryChatAdapter
from jarvis_room.provider_config import DEFAULT_PATH
from jarvis_room.provider_contract import ProviderUnavailable
from jarvis_room.provider_observability import (
    EventRecorder,
    ProviderEvent,
    diagnose,
    main,
)


class TestProviderObservability(unittest.TestCase):
    def test_evento_sem_conteudo_sensivel(self) -> None:
        recorder = EventRecorder()
        event = ProviderEvent("openjarvis-local", "response_unverified")
        recorder.record(event)
        self.assertEqual(asdict(recorder.events[0]), {
            "provider_id": "openjarvis-local",
            "outcome": "response_unverified",
            "action_verified": False,
        })
        for provider_id in (None, "", "um prompt", "https://invalid.example", 42):
            with self.subTest(provider_id=provider_id), self.assertRaises(ValueError):
                ProviderEvent(provider_id, "response_unverified")
        for outcome in (None, [], "texto de resposta", "success"):
            with self.subTest(outcome=outcome), self.assertRaises(ValueError):
                ProviderEvent("openjarvis-local", outcome)
        with self.assertRaises(TypeError):
            ProviderEvent(
                "openjarvis-local", "response_unverified", action_verified=True
            )
        with self.assertRaises(FrozenInstanceError):
            event.action_verified = True

    def test_registro_opcional_e_validado(self) -> None:
        recorder = EventRecorder()
        snapshot = recorder.events
        recorder.record(ProviderEvent("openjarvis-local", "provider_blocked"))
        self.assertEqual(snapshot, ())
        self.assertEqual(len(recorder.events), 1)
        for invalid in (None, {}, "texto"):
            with self.subTest(event=invalid), self.assertRaises(ValueError):
                recorder.record(invalid)
        for invalid in ([], {}, "texto"):
            with self.subTest(recorder=invalid), self.assertRaises(ValueError):
                RegistryChatAdapter(recorder=invalid)
        with patch(
            "jarvis_room.openjarvis_provider.OpenJarvisConversation"
        ) as conversation, patch.object(EventRecorder, "record") as record:
            conversation.return_value.return_value = "Resposta simulada"
            self.assertEqual(
                RegistryChatAdapter()("Explique MQTT"), "Resposta simulada"
            )
        record.assert_not_called()

    def test_resposta_simulada_registra_somente_resultado(self) -> None:
        recorder = EventRecorder()
        chat = RegistryChatAdapter(recorder=recorder)
        with patch(
            "jarvis_room.openjarvis_provider.OpenJarvisConversation"
        ) as conversation:
            conversation.return_value.return_value = "Conteúdo simulado da resposta"
            self.assertEqual(
                chat("Explique conteúdo do prompt"), "Conteúdo simulado da resposta"
            )
        self.assertEqual(recorder.events, (
            ProviderEvent("openjarvis-local", "response_unverified"),
        ))
        serialized = json.dumps([asdict(event) for event in recorder.events])
        self.assertNotIn("Conteúdo", serialized)
        self.assertNotIn("Explique", serialized)
        self.assertNotIn("prompt", serialized)

    def test_bloqueio_de_memoria_registra_codigo(self) -> None:
        recorder = EventRecorder()
        chat = RegistryChatAdapter(recorder=recorder)
        reason = "RAM indisponível; detalhe que não deve ser registrado"
        with patch(
            "jarvis_room.conversation_adapter.check_current_resources",
            return_value=InferenceDecision(False, reason),
        ):
            with self.assertRaises(LocalInferenceUnavailable) as error:
                chat("Explique MQTT")
        self.assertEqual(str(error.exception), reason)
        self.assertEqual(recorder.events, (
            ProviderEvent("openjarvis-local", "resources_blocked"),
        ))
        self.assertNotIn(
            reason, json.dumps([asdict(event) for event in recorder.events])
        )

    def test_falha_de_provedor_e_recusa_do_roteador(self) -> None:
        recorder = EventRecorder()
        chat = RegistryChatAdapter(recorder=recorder)
        failure = ProviderUnavailable("Detalhe interno que não deve ser registrado")
        with patch.object(chat._registry, "respond", side_effect=failure) as respond:
            reply = answer_informational_question("Ligue a luz da sala", chat)
            self.assertEqual(reply.channel, "blocked")
            self.assertEqual(recorder.events, ())
            respond.assert_not_called()
            with self.assertRaises(ProviderUnavailable) as error:
                chat("Explique MQTT")
        self.assertIs(error.exception, failure)
        self.assertEqual(recorder.events, (
            ProviderEvent("openjarvis-local", "provider_blocked"),
        ))
        self.assertNotIn(
            "Detalhe", json.dumps([asdict(event) for event in recorder.events])
        )

    def test_diagnostico_de_recursos_sem_importar_sdk(self) -> None:
        for allowed, expected in (
            (False, "resources_blocked"), (True, "experimental_eligible")
        ):
            with self.subTest(allowed=allowed), patch(
                "jarvis_room.provider_observability.check_current_resources",
                return_value=InferenceDecision(allowed, "Detalhe não publicado"),
            ) as check, patch("builtins.__import__", wraps=__import__) as imports:
                report = diagnose()
            check.assert_called_once_with()
            self.assertEqual(report, {
                "schema_version": 1,
                "mode": "offline",
                "provider_id": "openjarvis-local",
                "configuration_valid": True,
                "local_enabled": True,
                "remote_provider_allowed": False,
                "resource_minimum_met": allowed,
                "status": expected,
                "action_verified": False,
                "inference_executed_by_diagnostic": False,
            })
            self.assertFalse(any(
                call.args[0] == "openjarvis" for call in imports.call_args_list
            ))

    def test_configuracao_ausente_remota_e_desabilitada(self) -> None:
        base = json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "providers.json"
            with patch(
                "jarvis_room.provider_observability.check_current_resources"
            ) as check:
                report = diagnose(path)
                self.assertFalse(report["configuration_valid"])
                self.assertEqual(report["status"], "configuration_blocked")
                check.assert_not_called()
            for raw in ("{", json.dumps({**base, "remote_enabled": True})):
                path.write_text(raw, encoding="utf-8")
                report = diagnose(path)
                self.assertEqual(report["status"], "configuration_blocked")
                self.assertFalse(report["remote_provider_allowed"])
            base["providers"]["openjarvis-local"]["enabled"] = False
            path.write_text(json.dumps(base), encoding="utf-8")
            with patch(
                "jarvis_room.provider_observability.check_current_resources",
                return_value=InferenceDecision(True, "Recursos suficientes"),
            ):
                report = diagnose(path)
            self.assertTrue(report["configuration_valid"])
            self.assertFalse(report["local_enabled"])
            self.assertTrue(report["resource_minimum_met"])
            self.assertEqual(report["status"], "provider_blocked")
            self.assertFalse(report["inference_executed_by_diagnostic"])

    def test_cli_stdout_e_arquivo(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "diagnostics.json"
            with patch(
                "jarvis_room.provider_observability.check_current_resources",
                return_value=InferenceDecision(False, "Sem recursos"),
            ), patch("sys.argv", ["provider_observability"]), redirect_stdout(
                StringIO()
            ) as stdout:
                main()
            expected = json.loads(stdout.getvalue())
            with patch(
                "jarvis_room.provider_observability.check_current_resources",
                return_value=InferenceDecision(False, "Sem recursos"),
            ), patch("sys.argv", [
                "provider_observability", "--output", str(output),
            ]), redirect_stdout(StringIO()) as stdout:
                main()
            self.assertIn(str(output), stdout.getvalue())
            self.assertEqual(json.loads(output.read_text()), expected)
