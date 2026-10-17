"""Política de memória e integração com SDK simulado, sem inferência real."""

import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from jarvis_room.conversation_adapter import OpenJarvisConversation
from jarvis_room.experimental_chat import answer_informational_question
from jarvis_room.inference_policy import (
    GIB,
    InferenceDecision,
    LocalInferenceUnavailable,
    MemorySnapshot,
    check_current_resources,
    evaluate_resources,
    parse_meminfo,
)


class TestInferencePolicy(unittest.TestCase):
    def test_leitura_meminfo(self) -> None:
        snapshot = parse_meminfo(
            "MemTotal: 8388608 kB\n"
            "MemAvailable: 2097152 kB\n"
            "SwapFree: 3145728 kB\n"
        )
        self.assertEqual(snapshot.available_ram_bytes, 2 * GIB)
        self.assertEqual(snapshot.free_swap_bytes, 3 * GIB)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "meminfo"
            path.write_text(
                "MemAvailable: 2097152 kB\nSwapFree: 3145728 kB\n",
                encoding="utf-8",
            )
            self.assertTrue(check_current_resources(path).allowed)

    def test_recursos_suficientes(self) -> None:
        for ram, swap in ((3 * GIB, 3 * GIB), (2 * GIB, 2 * GIB)):
            with self.subTest(ram=ram, swap=swap):
                decision = evaluate_resources(MemorySnapshot(ram, swap))
                self.assertTrue(decision.allowed)

    def test_ram_insuficiente(self) -> None:
        for ram in (0, GIB, 2 * GIB - 1):
            with self.subTest(ram=ram):
                decision = evaluate_resources(MemorySnapshot(ram, 3 * GIB))
                self.assertFalse(decision.allowed)
                self.assertIn("RAM disponível insuficiente", decision.reason)

    def test_swap_insuficiente(self) -> None:
        for swap in (0, GIB, 2 * GIB - 1):
            with self.subTest(swap=swap):
                decision = evaluate_resources(MemorySnapshot(3 * GIB, swap))
                self.assertFalse(decision.allowed)
                self.assertIn("Swap livre insuficiente", decision.reason)

    def test_meminfo_invalido(self) -> None:
        for contents in (
            "",
            "MemAvailable: 2097152 kB\n",
            "SwapFree: 2097152 kB\n",
            "MemAvailable 2097152 kB\nSwapFree: 2097152 kB\n",
            "MemAvailable: -1 kB\nSwapFree: 2097152 kB\n",
            "MemAvailable: 2097152 kB\nSwapFree: -1 kB\n",
            "MemAvailable: muito kB\nSwapFree: 2097152 kB\n",
            "MemAvailable: 2.5 kB\nSwapFree: 2097152 kB\n",
            "MemAvailable: 2097152 MB\nSwapFree: 2097152 kB\n",
            "MemAvailable: 2097152\nSwapFree: 2097152 kB\n",
            "MemAvailable: 2097152 kB extra\nSwapFree: 2097152 kB\n",
            "MemAvailable: 2097152 kB\nSwapFree: 2097152 kB\n"
            "SwapFree: 3145728 kB\n",
        ):
            with self.subTest(contents=contents), self.assertRaises(ValueError):
                parse_meminfo(contents)

    def test_falha_na_consulta_bloqueia(self) -> None:
        expected = "Não foi possível verificar os recursos do sistema."
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "meminfo"
            # Arquivo ausente, dados inválidos e codificação inválida.
            decision = check_current_resources(path)
            self.assertFalse(decision.allowed)
            self.assertEqual(decision.reason, expected)
            for contents in (b"MemAvailable: invalid\n", b"\xff"):
                with self.subTest(contents=contents):
                    path.write_bytes(contents)
                    decision = check_current_resources(path)
                    self.assertFalse(decision.allowed)
                    self.assertEqual(decision.reason, expected)
            with patch.object(Path, "read_text", side_effect=PermissionError):
                decision = check_current_resources(path)
                self.assertFalse(decision.allowed)
                self.assertEqual(decision.reason, expected)

    def test_adaptador_bloqueia_antes_de_importar_sdk(self) -> None:
        reason = "RAM disponível insuficiente para inferência local."
        with patch(
            "jarvis_room.conversation_adapter.check_current_resources",
            return_value=InferenceDecision(False, reason),
        ), patch("builtins.__import__", wraps=__import__) as import_spy:
            with self.assertRaisesRegex(LocalInferenceUnavailable, reason):
                OpenJarvisConversation()("Explique MQTT")
            reply = answer_informational_question(
                "Explique MQTT", OpenJarvisConversation()
            )
        self.assertFalse(
            any(call.args[0] == "openjarvis" for call in import_spy.call_args_list)
        )
        self.assertEqual(reply.channel, "blocked")
        self.assertEqual(reply.text, f"Inferência local bloqueada: {reason}")
        self.assertFalse(reply.action_verified)

    def test_adaptador_sdk_simulado(self) -> None:
        sdk = types.ModuleType("openjarvis")
        constructor = MagicMock()
        sdk.Jarvis = constructor
        jarvis = constructor.return_value.__enter__.return_value
        jarvis.ask.return_value = "Resposta simulada"
        with patch.dict(sys.modules, {"openjarvis": sdk}), patch(
            "jarvis_room.conversation_adapter.check_current_resources",
            return_value=InferenceDecision(True, "Recursos suficientes."),
        ) as resource_check:
            response = OpenJarvisConversation()("Explique MQTT")
        self.assertEqual(response, "Resposta simulada")
        resource_check.assert_called_once_with()
        constructor.assert_called_once_with(
            engine_key="ollama", model="jarvis-dev-lite:latest"
        )
        jarvis.ask.assert_called_once_with(
            "Explique MQTT",
            agent="simple",
            tools=[],
            context=False,
            temperature=0.2,
            max_tokens=192,
        )
        constructor.return_value.__exit__.assert_called_once_with(None, None, None)
