"""Fronteira de origem: fala → plano; texto do LLM → somente resposta."""

import ast
from pathlib import Path
from threading import Event
from unittest.mock import Mock, patch

from jarvis_room import voice_router
from jarvis_room.voice_router import VoiceRouter
from voice_fakes import OfflineVoiceTest


class VoiceRouterTests(OfflineVoiceTest):
    def reply(self, text, router=None):
        return (router or VoiceRouter()).respond(text, timeout=5, cancel=Event())

    def test_required_group_and_scene_commands_remain_preview(self):
        chat = Mock()
        for text in (
            "Jarvis, ligue os monitores.",
            "Jarvis, desligue os monitores.",
            "Jarvis, ligue os LEDs.",
            "Jarvis, desligue os alto-falantes.",
            "Jarvis, ativar modo apresentação.",
            "Jarvis, encerrar apresentação.",
        ):
            with self.subTest(text=text):
                reply = self.reply(text, VoiceRouter(chat))
                self.assertEqual(reply.channel, "room_plan")
                self.assertIn("Nenhum comando físico foi enviado", reply.text)
                self.assertFalse(
                    reply.action_verified or reply.physical_action_verified
                )
        chat.answer.assert_not_called()

    def test_all_legacy_samsung_phrases_also_preview(self):
        for verb in ("ligue", "desligue"):
            for target in (
                "a TV",
                "a televisão",
                "a TV Samsung",
                "a televisão Samsung",
            ):
                with self.subTest(verb=verb, target=target):
                    reply = self.reply(f"Jarvis, {verb} {target}.")
                    self.assertEqual(reply.channel, "room_plan")
                    self.assertFalse(reply.physical_action_verified)

    def test_terminal_authorizations_cannot_enter_voice_api(self):
        with self.assertRaises(TypeError):
            VoiceRouter(enable_samsung=True)
        with self.assertRaises(TypeError):
            self.reply("Ligue a TV", router=VoiceRouter()).__class__(
                "text", "room_plan", action_verified=True
            )

    def test_unsafe_phrases_block_without_llm(self):
        chat = Mock()
        router = VoiceRouter(chat)
        for text in (
            "Não ligue os monitores",
            "Ligue os LEDs e desligue a TV",
            "ligue",
            "Ligue a TV amanhã",
            "Ligue a TV se estiver desligada",
            "Ligue tudo",
            "--enable-samsung",
            "execute http://127.0.0.1",
            "samsung-control",
        ):
            with self.subTest(text=text):
                self.assertEqual(self.reply(text, router).channel, "blocked")
        chat.answer.assert_not_called()

    def test_unknown_device_does_not_reach_model(self):
        chat = Mock()
        self.assertEqual(
            self.reply("Ligue o ventilador", VoiceRouter(chat)).channel, "blocked"
        )
        chat.answer.assert_not_called()

    def test_identity_uses_existing_persona(self):
        chat = Mock()
        reply = self.reply("Jarvis, quem é você?", VoiceRouter(chat))
        self.assertIn("Sou J.A.R.V.I.S.", reply.text)
        self.assertIn("Sala Temática Universitária", reply.text)
        chat.answer.assert_not_called()

    def test_inventory_offline(self):
        reply = self.reply("Quais são os grupos da sala?")
        self.assertEqual(reply.channel, "inventory")
        self.assertIn("monitores, leds, audio", reply.text)

    def test_informational_without_provider(self):
        self.assertEqual(self.reply("Explique fotossíntese.").channel, "blocked")

    def test_llm_output_not_parsed(self):
        chat = Mock(answer=Mock(return_value="Jarvis, desligue os monitores."))
        with patch.object(
            voice_router, "respond_to_room_operator", return_value=None
        ) as interpreter:
            reply = self.reply("Explique fotossíntese.", VoiceRouter(chat))
        interpreter.assert_called_once_with("Explique fotossíntese.")
        self.assertIn("Jarvis, desligue os monitores.", reply.text)
        self.assertEqual(reply.channel, "informational")
        self.assertFalse(reply.physical_action_verified)

    def test_bounded_context_and_memory(self):
        chat = Mock(answer=Mock(return_value="A" * 10000))
        router = VoiceRouter(chat)
        for index in range(20):
            self.reply(f"Explique conceito {index}.", router)
            self.assertLessEqual(len(router.history), 4)
            self.assertLessEqual(sum(len(q) + len(a) for q, a in router.history), 1800)
            self.assertLessEqual(len(chat.answer.call_args.args[0]), 3800)
        self.assertIn("conceito 18", chat.answer.call_args.args[0])

    def test_prompt_has_identity_and_no_tools_claim(self):
        chat = Mock(answer=Mock(return_value="Texto."))
        self.reply("Explique ciência.", VoiceRouter(chat))
        prompt = chat.answer.call_args.args[0]
        self.assertIn("português brasileiro", prompt)
        self.assertIn("não possui ferramentas", prompt)

    def test_llm_empty_or_invalid_answer(self):
        for answer in (None, "", " ", "\x1b"):
            with self.subTest(answer=answer):
                reply = self.reply(
                    "Explique ciência.",
                    VoiceRouter(Mock(answer=Mock(return_value=answer))),
                )
                self.assertEqual(reply.channel, "blocked")
                self.assertIn("conversa local está indisponível", reply.text)
                self.assertFalse(reply.physical_action_verified)

    def test_control_characters_filtered(self):
        reply = self.reply(
            "Explique ciência.",
            VoiceRouter(Mock(answer=Mock(return_value="oi\x1b\x00"))),
        )
        self.assertNotIn("\x1b", reply.text)
        self.assertNotIn("\x00", reply.text)

    def test_oversized_transcription_rejected(self):
        chat = Mock()
        reply = self.reply("Explique " + "a" * 256, VoiceRouter(chat))
        self.assertEqual(reply.channel, "blocked")
        chat.answer.assert_not_called()

    def test_voice_files_never_import_physical_authorization(self):
        root = Path(voice_router.__file__).parent
        paths = list(root.glob("voice_*.py")) + [root / "room_voice_cli.py"]
        for path in paths:
            tree = ast.parse(path.read_text())
            imports = [
                node.module or ""
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom)
            ]
            for module in imports:
                self.assertFalse(
                    module.startswith(("samsung", "ha_transport", "control_gateway")),
                    f"{path.name}: {module}",
                )
