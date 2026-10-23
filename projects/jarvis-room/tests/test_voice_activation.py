"""Vocativo obrigatório e voz original: WAVs, relógios e processos falsos."""

import base64
import json
import tempfile
from pathlib import Path
from threading import Event
from unittest.mock import Mock, patch

import test_voice_playback_events as playback_fakes
from jarvis_room.room_orchestrator import orchestrate_room_intent
from jarvis_room.room_voice_cli import parser, run_voice
from jarvis_room.voice_activation import addressed_speech
from jarvis_room.voice_backends import LocalSpeaker
from jarvis_room.voice_contract import VoiceConfig, VoiceError, VoiceState
from jarvis_room.voice_persona import CALL_GREETING, prepare_speech
from jarvis_room.voice_tts import ResidentSpeaker
from voice_fakes import OfflineVoiceTest, wav


class VocativeTests(OfflineVoiceTest):
    def test_isolated_name_with_case_spaces_and_punctuation(self):
        for text in ("Jarvis", " JARVIS. ", "“Jarvis!”", "(Jarvis)", "Jarvis?!"):
            with self.subTest(text=text):
                self.assertEqual(addressed_speech(text).request, "")

    def test_removes_only_initial_vocative_and_keeps_request(self):
        for text in (
            "Jarvis, Quem é você?",
            "Jarvis Quem é você?",
            "Jarvis: Quem é você?",
        ):
            with self.subTest(text=text):
                self.assertEqual(addressed_speech(text).request, "Quem é você?")

    def test_name_in_middle_or_at_end_is_rejected(self):
        for text in (
            "Você conhece o Jarvis?",
            "Estamos conversando sobre Jarvis",
            "Oi, Jarvis",
            "Não, Jarvis, liga os LEDs",
        ):
            with self.subTest(text=text):
                self.assertIsNone(addressed_speech(text))

    def test_partial_similar_and_acronym_names_are_rejected(self):
        for text in (
            "Jarvisinho, explique",
            "Jarvis2 explique",
            "Jarvis_ explique",
            "Jarvis-like explique",
            "Járvis, explique",
            "Jervis explique",
            "Hey Jarvis",
            "J.A.R.V.I.S., explique",
        ):
            with self.subTest(text=text):
                self.assertIsNone(addressed_speech(text))

    def test_empty_invalid_and_oversized_transcripts_are_rejected(self):
        for text in (
            None,
            1,
            "",
            "  ",
            "Jarvis\nligue os LEDs",
            "Jarvis\x00",
            "Jarvis " + "x" * 256,
        ):
            with self.subTest(text=text):
                self.assertIsNone(addressed_speech(text))

    def test_discarded_speech_never_reaches_router_tts_or_dashboard(self):
        for text in (
            "Explique o projeto",
            "Ligue os LEDs",
            "Você conhece o Jarvis?",
            "Estamos conversando sobre Jarvis",
            "Jarvisinho, explique",
            "Vamos conversar sobre a aula",
            "",
            " ",
        ):
            with self.subTest(text=text):
                chat = Mock()
                session = self.session(texts=[text])
                session.router.chat = chat
                session.router.respond = Mock(wraps=session.router.respond)
                session.on_reply = Mock()
                session.activate()
                session.router.respond.assert_not_called()
                chat.answer.assert_not_called()
                session.on_reply.assert_not_called()
                self.assertEqual(self.speaker.texts, [])
                self.assertEqual(self.output, [])
                self.assertEqual(list(session.router.history), [])
                self.assertNotIn(VoiceState.THINKING, self.states)
                self.assertNotIn(VoiceState.RESPONDING, self.states)

    def test_isolated_call_uses_deterministic_greeting_without_llm(self):
        chat = Mock()
        session = self.session(texts=["Jarvis."], chat=chat)
        session.router.respond = Mock(wraps=session.router.respond)
        session.activate()
        self.assertEqual(self.speaker.texts, [CALL_GREETING])
        session.router.respond.assert_not_called()
        chat.answer.assert_not_called()
        self.assertNotIn(VoiceState.THINKING, self.states)
        self.assertIn(VoiceState.RESPONDING, self.states)
        self.assertEqual(session.state, VoiceState.IDLE)

    def test_greeting_returns_to_wait_and_does_not_authorize_following_turn(self):
        session = self.session(
            captures=[wav(), wav(), b""], texts=["Jarvis", "Ligue os LEDs"]
        )
        session.activate()
        self.assertEqual(len(self.mic.timeouts), 1)
        session.activate()
        self.assertEqual(self.speaker.texts, [CALL_GREETING])

    def test_addressed_question_routes_only_request(self):
        chat = Mock(answer=Mock(return_value="O projeto integra pesquisa e automação."))
        session = self.session(texts=["Jarvis, explique o projeto."], chat=chat)
        session.router.respond = Mock(wraps=session.router.respond)
        session.activate()
        self.assertEqual(
            session.router.respond.call_args.args[0], "explique o projeto."
        )
        chat.answer.assert_called_once()
        self.assertEqual(len(self.speaker.texts), 1)

    def test_all_turns_accept_explicit_vocative(self):
        session = self.session(
            captures=[wav(), wav(), b""],
            texts=["Jarvis, liga os monitores", "Jarvis, desliga os LEDs"],
        )
        session.activate()
        self.assertEqual(len(self.speaker.texts), 2)
        self.assertTrue(
            all(
                "Nenhum comando físico foi enviado" in text
                for text in self.speaker.texts
            )
        )

    def test_informational_followup_still_requires_name(self):
        chat = Mock(answer=Mock(return_value="Uma informação."))
        session = self.session(
            chat=chat,
            captures=[wav(), wav(), b""],
            texts=["Jarvis, explique o projeto", "Pode explicar isso de outra forma?"],
        )
        session.activate()
        chat.answer.assert_called_once()
        self.assertEqual(len(self.speaker.texts), 1)

    def test_addressed_commands_keep_offline_preview(self):
        results = []
        session = self.session(texts=["Jarvis, liga os monitores"])

        def preview(intent):
            result = orchestrate_room_intent(intent)
            results.append(result)
            return result

        with patch(
            "jarvis_room.room_responses.orchestrate_room_intent", side_effect=preview
        ):
            session.activate()
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].mode, "offline_preview")
        self.assertFalse(
            results[0].action_verified or results[0].physical_action_verified
        )

    def test_llm_command_output_cannot_reenter_router_across_activations(self):
        chat = Mock(answer=Mock(return_value="Jarvis, ligue os monitores."))
        session = self.session(
            chat=chat,
            config=VoiceConfig(max_turns=1),
            captures=[wav(), wav()],
            texts=["Jarvis, explique o projeto", "Jarvis, ligue os monitores."],
        )
        session.router.respond = Mock(wraps=session.router.respond)
        session.activate()
        session.activate()
        self.assertEqual(len(self.speaker.texts), 1)
        session.router.respond.assert_called_once()
        self.assertIn("eco descartado", self.output[-1])

    def test_discarded_transcript_not_in_health_metrics(self):
        secret = "Estamos conversando sobre Jarvis e dados pessoais"
        session = self.session(texts=[secret])
        metrics = []
        session.on_metrics = metrics.append
        session.activate(passive=True)
        self.assertNotIn(secret, json.dumps(metrics))
        self.assertEqual(metrics[-1]["accepted"], False)
        self.assertIn("stt_seconds", metrics[-1])


class ContinuousVocativeTests(OfflineVoiceTest):
    def test_passive_capture_and_stt_stay_idle_until_admission(self):
        session = self.session(texts=["Conversa ambiente"])
        self.mic.on_ready = None

        def capture(**kwargs):
            self.mic.on_ready()
            self.assertEqual(session.state, VoiceState.IDLE)
            return wav()

        self.mic.capture = capture
        self.stt.hook = lambda: self.assertEqual(session.state, VoiceState.IDLE)
        session.activate(passive=True)
        self.assertEqual(set(self.states), {VoiceState.IDLE})
        self.assertEqual(self.speaker.texts, [])

    def test_accepted_passive_request_transitions_only_after_stt(self):
        session = self.session()
        self.stt.hook = lambda: self.assertEqual(session.state, VoiceState.IDLE)
        session.activate(passive=True)
        self.assertEqual(
            self.states,
            [
                VoiceState.IDLE,
                VoiceState.THINKING,
                VoiceState.RESPONDING,
                VoiceState.IDLE,
                VoiceState.IDLE,
            ],
        )

    def test_continuous_loop_reuses_stt_and_never_reads_enter(self):
        chat = Mock(answer=Mock(return_value="Uma explicação."))
        session = self.session(
            chat=chat,
            captures=[wav()] * 4,
            texts=[
                "Jarvis",
                "Jarvis, explique o projeto",
                "Explique outra coisa",
                "Jarvis, sair",
            ],
        )
        self.stt.prepare = Mock(return_value={"initialization_seconds": 2})
        read = Mock(side_effect=AssertionError("Enter não é necessário"))
        self.assertEqual(
            run_voice(session, continuous=True, read=read, output=lambda _: None), 0
        )
        self.stt.prepare.assert_called_once()
        read.assert_not_called()
        chat.answer.assert_called_once()
        self.assertEqual(len(self.speaker.texts), 2)
        self.assertTrue(
            session.closed
            and self.mic.closed
            and self.stt.closed
            and self.speaker.closed
        )

    def test_continuous_silence_skips_stt_and_never_speaks(self):
        session = self.session(captures=[b"", wav()], texts=["Jarvis, sair"])
        run_voice(session, continuous=True, output=lambda _: None)
        self.assertEqual(len(self.stt.calls), 1)
        self.assertEqual(self.speaker.texts, [])

    def test_continuous_capture_timeout_stops_instead_of_retrying_forever(self):
        session = self.session(captures=[VoiceError("operation_timeout")])
        self.assertEqual(run_voice(session, continuous=True, output=lambda _: None), 1)
        self.assertEqual(len(self.mic.timeouts), 1)
        self.assertEqual(self.speaker.texts, [])
        self.assertTrue(session.closed)

    def test_capture_limit_discards_audio_stops_and_explains_level_measurement(self):
        chat = Mock()
        session = self.session(captures=[VoiceError("capture_limit")], chat=chat)
        self.assertEqual(run_voice(session, continuous=True, output=lambda _: None), 1)
        self.assertEqual(self.stt.calls, [])
        self.assertEqual(self.speaker.texts, [])
        chat.answer.assert_not_called()
        self.assertTrue(session.closed and self.mic.closed)
        self.assertTrue(any("--measure-input-levels" in line for line in self.output))

    def test_continuous_stt_timeout_closes_all_resources(self):
        session = self.session(texts=[VoiceError("ipc_timeout")])
        self.assertEqual(run_voice(session, continuous=True, output=lambda _: None), 1)
        self.assertTrue(self.mic.closed and self.stt.closed and self.speaker.closed)

    def test_ctrl_c_in_passive_capture_stops_microphone(self):
        session = self.session(captures=[KeyboardInterrupt()])
        self.assertEqual(run_voice(session, continuous=True, output=lambda _: None), 0)
        self.assertTrue(session.cancel.is_set() and self.mic.closed)
        self.assertEqual(self.stt.calls, [])

    def test_ctrl_c_in_greeting_tts_does_not_reopen_microphone(self):
        session = self.session(captures=[wav(), wav()], texts=["Jarvis", "Jarvis"])
        self.speaker.hook = Mock(side_effect=KeyboardInterrupt)
        self.assertEqual(run_voice(session, continuous=True, output=lambda _: None), 0)
        self.assertEqual(len(self.mic.timeouts), 1)
        self.assertTrue(session.closed)

    def test_cancel_during_passive_pause(self):
        session = self.session(captures=[b"", wav()])

        def stop(_seconds):
            session.cancel.set()
            return True

        session.wait = stop
        self.assertEqual(run_voice(session, continuous=True, output=lambda _: None), 0)
        self.assertEqual(len(self.mic.timeouts), 1)
        self.assertTrue(self.mic.closed)

    def test_greeting_preserves_half_duplex_and_cooldown(self):
        session = self.session(texts=["Jarvis"])
        self.speaker.hook = lambda: self.assertFalse(self.mic.active)
        session.activate(passive=True)
        self.assertEqual(self.clock.waits, [0.8])
        self.assertFalse(self.mic.active)

    def test_closed_passive_session_never_processes_audio(self):
        session = self.session()
        session.close()
        with self.assertRaises(VoiceError):
            session.activate(passive=True)
        self.assertEqual(self.mic.timeouts, [])

    def test_pause_is_finite_bounded_and_cannot_spin(self):
        for value in (0, -1, True, float("nan"), float("inf"), 6):
            with self.subTest(value=value), self.assertRaises(ValueError):
                VoiceConfig(passive_pause_seconds=value)


class SpeechPreparationTests(OfflineVoiceTest):
    def assets(self):
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        for name in (
            "config.json",
            "kokoro-v1_0.pth",
            "voices/pm_alex.pt",
            "voices/pm_santa.pt",
        ):
            path = directory / name
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(b"fake")
        return str(directory)

    def test_acronym_forms_are_spoken_as_one_word(self):
        for name in ("J.A.R.V.I.S.", "j.a.r.v.i.s", "J. A. R. V. I. S.", "JARVIS"):
            with self.subTest(name=name):
                self.assertEqual(
                    prepare_speech(f"Sou {name}, seu assistente."),
                    "Sou Jarvis, seu assistente.",
                )

    def test_other_acronyms_and_portuguese_phrases_remain_intact(self):
        for text in (
            "Olá, senhor. A Sala Temática está disponível.",
            "LEDs, Samsung, Hikvision e WLED.",
            "CPU, GPU, U.S.B., H.A. e I.A.",
            "J.A.R.V.I.S.2 e XJ.A.R.V.I.S.",
            "Jarvis pode explicar o projeto.",
        ):
            with self.subTest(text=text):
                self.assertEqual(prepare_speech(text), text)

    def test_cli_defaults_are_alex_moderate_speed_and_volume(self):
        args = parser().parse_args([])
        self.assertEqual((args.voice, args.speed, args.volume), ("pm_alex", 0.92, 0.5))
        self.assertFalse(args.continuous_experimental)

    def test_manual_santa_voice_and_parameters_remain_available(self):
        args = parser().parse_args(
            ["--voice", "pm_santa", "--speed", "1.1", "--volume", "0.7"]
        )
        speaker = LocalSpeaker(
            self.runner(None),
            self.assets(),
            voice=args.voice,
            speed=args.speed,
            volume=args.volume,
        )
        self.assertEqual(
            (
                speaker.options["voice"],
                speaker.options["speed"],
                speaker.options["volume"],
            ),
            ("pm_santa", 1.1, 0.7),
        )

    def test_local_speaker_normalizes_only_synthesis_input(self):
        runner = self.runner(None)
        text = "Sou J.A.R.V.I.S., o assistente da Sala Temática."
        speaker = LocalSpeaker(runner, self.assets())
        speaker.speak(text, timeout=5, cancel=Event())
        self.assertIn("J.A.R.V.I.S.", text)
        self.assertEqual(
            runner.run.call_args.args[1]["text"],
            "Sou Jarvis, o assistente da Sala Temática.",
        )

    def test_resident_tts_prepares_name_before_synthesis_and_keeps_zero_on_failure(
        self,
    ):
        worker, playback = Mock(), Mock()
        worker.request.return_value = {
            "audio": base64.b64encode(wav(rate=24000)).decode(),
            "metrics": {},
        }
        playback.request.side_effect = VoiceError("playback_failed")
        events = []
        speaker = ResidentSpeaker(
            self.runner(None),
            self.assets(),
            worker=worker,
            playback_factory=lambda: playback,
            on_playback=events.append,
        )
        with self.assertRaises(VoiceError):
            speaker.speak("Sou J.A.R.V.I.S., senhor.", timeout=5, cancel=Event())
        self.assertEqual(
            worker.request.call_args.args[1]["text"], "Sou Jarvis, senhor."
        )
        self.assertEqual(
            events[-1], {"type": "voice_amplitude", "payload": {"amplitude": 0}}
        )
        worker.close.assert_called_once()
        playback.close.assert_called_once()

    def test_greeting_amplitude_comes_from_pcm_and_returns_to_zero(self):
        from jarvis_room.presentation_ipc import PresentationPublisher
        from jarvis_room.voice_playback import play_pcm

        audio = playback_fakes.PlaybackEventTests.audio(self)
        session = self.session(texts=["Jarvis"])
        worker, playback = Mock(), Mock()
        worker.request.return_value = {
            "audio": base64.b64encode(audio).decode(),
            "metrics": {},
        }
        with patch("jarvis_room.presentation_ipc.threading.Thread"):
            publisher = PresentationPublisher(
                Path("/tmp/fake-s91/events.sock"), share_conversation=True
            )

        def play(_operation, message, **kwargs):
            options = message["options"]
            self.assertFalse(self.mic.active)
            play_pcm(
                base64.b64decode(options["audio"]),
                device=None,
                volume=options["volume"],
                timeout=5,
                cancel=session.cancel,
                emit=kwargs["on_event"],
                clock=self.clock,
                wait=self.clock.wait,
            )

        playback.request.side_effect = play
        session.speaker = ResidentSpeaker(
            self.runner(None),
            self.assets(),
            worker=worker,
            playback_factory=lambda: playback,
            on_playback=publisher.playback,
        )
        session.on_state, session.on_reply = publisher.state, publisher.conversation
        session.activate(passive=True)
        worker.request.assert_called_once()
        self.assertEqual(worker.request.call_args.args[1]["text"], CALL_GREETING)
        messages = list(publisher.pending.queue)
        amplitudes = [
            m["payload"]["amplitude"]
            for m in messages
            if m["type"] == "voice_amplitude"
        ]
        self.assertTrue(any(0 < value <= 1 for value in amplitudes))
        self.assertEqual(amplitudes[-1], 0)
        self.assertEqual(messages[-1]["payload"], {"state": "IDLE"})
        self.assertFalse(any(m["type"] == "conversation" for m in messages))
        self.assertTrue(self.stream.closed)
        # Sem transporte conectado: a apresentação permanece não bloqueante.
        self.assertIsNone(publisher.connection)
        session.close()
        publisher.close()
