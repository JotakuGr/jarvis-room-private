"""S7.1: variantes pt-BR com alvos completos e planejamento offline preservado."""

from threading import Event
from unittest.mock import Mock, patch

from jarvis_room.room_device_registry import GROUP_TARGETS, load_room_devices
from jarvis_room.room_intent import parse_room_intent
from jarvis_room.room_orchestrator import orchestrate_room_intent
from jarvis_room.room_responses import respond_to_room_operator
from jarvis_room.samsung_natural_intent import ALLOWED_PHRASES, parse_samsung_intent
from jarvis_room.voice_router import VoiceRouter
from voice_fakes import OfflineVoiceTest, wav

VERBS = (
    ("ligue", "turn_on"),
    ("liga", "turn_on"),
    ("desligue", "turn_off"),
    ("desliga", "turn_off"),
)


class NaturalPortugueseCommandTests(OfflineVoiceTest):
    def assert_intent(self, text, kind, action, target):
        intent = parse_room_intent(text)
        self.assertTrue(intent.recognized)
        self.assertEqual(
            (intent.kind, intent.action, intent.target_id), (kind, action, target)
        )
        self.assertIsNone(intent.reason)
        return intent

    def assert_blocked(self, messages):
        for text in messages:
            with self.subTest(text=text):
                intent = parse_room_intent(text)
                self.assertFalse(intent.recognized)
                self.assertEqual(intent.kind, "blocked")
                self.assertIsNone(intent.action)
                self.assertIsNone(intent.target_id)
                self.assertIsNone(intent.phrase)

    def test_turn_on_with_jarvis(self):
        for verb in ("ligue", "liga"):
            with self.subTest(verb=verb):
                self.assert_intent(
                    f"Jarvis, {verb} os monitores.",
                    "group_control",
                    "turn_on",
                    "monitores",
                )

    def test_turn_on_without_jarvis(self):
        for verb in ("Ligue", "Liga"):
            with self.subTest(verb=verb):
                self.assert_intent(
                    f"{verb} os monitores.", "group_control", "turn_on", "monitores"
                )

    def test_turn_off_with_jarvis(self):
        for verb in ("desligue", "desliga"):
            with self.subTest(verb=verb):
                self.assert_intent(
                    f"Jarvis, {verb} os monitores.",
                    "group_control",
                    "turn_off",
                    "monitores",
                )

    def test_turn_off_without_jarvis(self):
        for verb in ("Desligue", "Desliga"):
            with self.subTest(verb=verb):
                self.assert_intent(
                    f"{verb} os monitores.", "group_control", "turn_off", "monitores"
                )

    def test_registered_group_aliases_with_each_verb(self):
        self.assertEqual(set(GROUP_TARGETS.values()), {"monitores", "leds", "audio"})
        for alias, target in GROUP_TARGETS.items():
            for verb, action in VERBS:
                with self.subTest(alias=alias, verb=verb):
                    self.assert_intent(
                        f"Jarvis, {verb} {alias}.", "group_control", action, target
                    )

    def test_case_accents_punctuation_and_permitted_spaces(self):
        for text, action, target, phrase in (
            ("  JARVIS,  LÍGA   OS LÉDS!!!  ", "turn_on", "leds", "liga os leds"),
            (
                "Jarvis DESLÍGA O SISTEMA DE ÁUDIO?",
                "turn_off",
                "audio",
                "desliga o sistema de audio",
            ),
            ("Jarvis, liga os le\u0301ds.", "turn_on", "leds", "liga os leds"),
            (
                "DESLIGA OS ALTO-FALANTES!",
                "turn_off",
                "audio",
                "desliga os alto falantes",
            ),
        ):
            with self.subTest(text=text):
                intent = self.assert_intent(text, "group_control", action, target)
                self.assertEqual(intent.phrase, phrase)

    def test_registered_device_aliases_with_each_supported_action(self):
        for device in load_room_devices().values():
            for alias in device.aliases:
                for verb, action in VERBS:
                    if action not in device.capabilities:
                        continue
                    with self.subTest(device=device.id, alias=alias, verb=verb):
                        self.assert_intent(
                            f"Jarvis, {verb} {alias}.",
                            "device_control",
                            action,
                            device.id,
                        )

    def test_liga_and_desliga_produce_distinct_actions(self):
        on = self.assert_intent(
            "Jarvis, liga os monitores", "group_control", "turn_on", "monitores"
        )
        off = self.assert_intent(
            "Jarvis, desliga os monitores", "group_control", "turn_off", "monitores"
        )
        self.assertNotEqual(on.action, off.action)

    def test_negation_remains_blocked(self):
        self.assert_blocked(
            [
                "Jarvis, não liga os monitores.",
                "Jarvis, não desliga os monitores.",
                "Não liga os LEDs.",
                "Nunca desliga o sistema de áudio.",
                "Jarvis, liga não os monitores.",
                "Jarvis, desliga não os LEDs.",
            ]
        )

    def test_multiple_actions_conditions_and_schedules_remain_blocked(self):
        self.assert_blocked(
            [
                "Jarvis, liga os monitores e desliga os LEDs.",
                "Liga os monitores e os LEDs.",
                "Desliga a TV ou os alto-falantes.",
                "Liga os monitores. Depois desliga os LEDs.",
                "Liga os monitores, desliga os LEDs.",
                "Se puder liga os monitores.",
                "Liga os monitores se estiverem desligados.",
                "Desliga os monitores amanhã.",
            ]
        )

    def test_unknown_targets_and_partial_aliases_remain_blocked(self):
        self.assert_blocked(
            [
                "Jarvis, liga todos os dispositivos desconhecidos.",
                "Liga o monitor LG.",
                "Desliga o ventilador.",
                "Liga os monitores da sala.",
                "Desliga os LEDs extras.",
                "Liga os monitor.",
                "Desliga o áudio.",
                "Liga media_player.samsung.",
                "Liga http://127.0.0.1.",
            ]
        )

    def test_incomplete_commands_remain_blocked(self):
        self.assert_blocked(
            [
                "liga",
                "desliga",
                "Jarvis, liga.",
                "Jarvis, desliga.",
                "Liga os",
                "Desliga o",
                "Jarvis,",
                "",
            ]
        )

    def test_verbs_are_explicit_not_substrings_or_fuzzy_matches(self):
        self.assert_blocked(
            [
                "Religa os monitores.",
                "Desligados os monitores.",
                "Ligaos monitores.",
                "Desligaos monitores.",
                "Ligas os monitores.",
                "Ligar os monitores.",
                "Liga-os-monitores.",
                "Aliga os monitores.",
            ]
        )

    def test_normalization_does_not_accept_control_characters(self):
        self.assert_blocked(
            [
                "Liga\tos monitores",
                "Desliga os monitores\n",
                "Jarvis, liga\x00 os monitores",
                "ＬＩＧＡ os monitores",
            ]
        )

    def test_sensor_does_not_gain_control_capability(self):
        for verb, _action in VERBS:
            with self.subTest(verb=verb):
                intent = parse_room_intent(f"Jarvis, {verb} o sensor de presença.")
                self.assertFalse(intent.recognized)
                self.assertEqual(intent.reason, "unsupported_capability")

    def test_samsung_authorization_parser_is_not_extended(self):
        self.assertEqual(len(ALLOWED_PHRASES), 8)
        for verb, action in (("liga", "turn_on"), ("desliga", "turn_off")):
            with self.subTest(verb=verb):
                text = f"Jarvis, {verb} a TV Samsung."
                self.assert_intent(text, "device_control", action, "samsung_lab_tv")
                self.assertFalse(parse_samsung_intent(text).recognized)

    def test_room_responses_describe_recognition_and_offline_preview(self):
        for verb, action in VERBS:
            for alias in (
                "os monitores",
                "os LEDs",
                "o sistema de áudio",
                "a TV Samsung",
            ):
                with self.subTest(verb=verb, alias=alias):
                    text = f"Jarvis, {verb} {alias}."
                    result = orchestrate_room_intent(parse_room_intent(text))
                    self.assertEqual(result.mode, "offline_preview")
                    self.assertFalse(
                        result.action_verified or result.physical_action_verified
                    )
                    self.assertTrue(
                        all(
                            item.action == action
                            and item.simulated_state is None
                            and not item.physical_action_verified
                            for item in result.results
                        )
                    )
                    reply = respond_to_room_operator(text)
                    self.assertEqual(reply.channel, "room_plan")
                    self.assertIn("Planejamento offline", reply.text)
                    self.assertIn("Nenhum comando físico foi enviado", reply.text)
                    self.assertFalse(
                        reply.action_verified or reply.physical_action_verified
                    )

    def test_voice_router_routes_new_variants_without_llm(self):
        chat = Mock()
        router = VoiceRouter(chat)
        for verb in ("liga", "desliga"):
            for alias in (
                "os monitores",
                "os LEDs",
                "os alto-falantes",
                "a TV Samsung",
            ):
                with self.subTest(verb=verb, alias=alias):
                    reply = router.respond(
                        f"Jarvis, {verb} {alias}.", timeout=5, cancel=Event()
                    )
                    self.assertEqual(reply.channel, "room_plan")
                    self.assertFalse(
                        reply.action_verified or reply.physical_action_verified
                    )
                    self.assertIn("Nenhum comando físico foi enviado", reply.text)
        chat.answer.assert_not_called()

    def test_simulated_transcripts_reach_session_as_offline_plans(self):
        chat, results = Mock(), []
        session = self.session(
            captures=[wav(), wav(), b""],
            texts=["Jarvis, liga os monitores", "Jarvis, desliga os LEDs."],
            chat=chat,
        )

        def preview(intent):
            result = orchestrate_room_intent(intent)
            results.append(result)
            return result

        with patch(
            "jarvis_room.room_responses.orchestrate_room_intent", side_effect=preview
        ):
            self.assertTrue(session.activate())
        self.assertEqual(
            [(result.target_id, result.results[0].action) for result in results],
            [("monitores", "turn_on"), ("leds", "turn_off")],
        )
        self.assertTrue(
            all(
                result.mode == "offline_preview"
                and not result.action_verified
                and not result.physical_action_verified
                for result in results
            )
        )
        self.assertEqual(len(self.stt.calls), 2)
        self.assertEqual(len(self.speaker.texts), 2)
        self.assertTrue(
            all(
                "Nenhum comando físico foi enviado" in text
                for text in self.speaker.texts
            )
        )
        chat.answer.assert_not_called()

    def test_unsafe_simulated_transcripts_never_generate_plans(self):
        chat = Mock()
        texts = [
            "Jarvis, não liga os monitores.",
            "Jarvis, não desliga os monitores.",
            "Jarvis, liga os monitores e desliga os LEDs.",
            "Jarvis, liga todos os dispositivos desconhecidos.",
        ]
        session = self.session(
            captures=[wav() for _ in texts] + [b""], texts=texts, chat=chat
        )
        with patch(
            "jarvis_room.room_responses.orchestrate_room_intent"
        ) as orchestrator:
            self.assertTrue(session.activate())
        orchestrator.assert_not_called()
        chat.answer.assert_not_called()
        self.assertEqual(len(self.speaker.texts), len(texts))
        self.assertTrue(
            all(
                "Nenhuma ação física foi executada" in text
                for text in self.speaker.texts
            )
        )
