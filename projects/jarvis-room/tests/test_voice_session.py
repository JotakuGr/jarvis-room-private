"""Estados, prazo absoluto, cancelamento, eco e limpeza sem áudio real."""

from unittest.mock import Mock

from jarvis_room.room_voice_cli import run_voice
from jarvis_room.voice_contract import (
    VoiceCancelled,
    VoiceConfig,
    VoiceError,
    VoiceState,
)
from voice_fakes import OfflineVoiceTest, wav


class VoiceSessionTests(OfflineVoiceTest):
    def test_full_state_sequence(self):
        session = self.session()
        self.assertTrue(session.activate())
        self.assertEqual(
            self.states,
            [
                VoiceState.LISTENING,
                VoiceState.TRANSCRIBING,
                VoiceState.THINKING,
                VoiceState.RESPONDING,
                VoiceState.IDLE,
                VoiceState.LISTENING,
                VoiceState.IDLE,
            ],
        )
        self.assertIn("Planejamento offline", self.output[0])

    def test_following_turn_without_jarvis_is_ignored(self):
        session = self.session(
            captures=[wav(), wav(), b""],
            texts=["Jarvis, ligue os monitores.", "Desligue os LEDs."],
        )
        session.activate()
        self.assertEqual(len(self.speaker.texts), 1)
        self.assertEqual(len(self.stt.calls), 2)

    def test_silence_never_transcribes(self):
        session = self.session(captures=[b""])
        session.activate()
        self.assertEqual(self.stt.calls, [])
        self.assertEqual(self.speaker.texts, [])

    def test_empty_transcription_closes_window(self):
        session = self.session(texts=[" "])
        session.activate()
        self.assertEqual(self.output, [])

    def test_max_turns(self):
        session = self.session(config=VoiceConfig(max_turns=1), captures=[wav(), wav()])
        session.activate()
        self.assertEqual(len(self.mic.timeouts), 1)

    def test_active_deadline_caps_capture(self):
        session = self.session(config=VoiceConfig(active_seconds=2))
        session.activate()
        self.assertEqual(self.mic.timeouts[0], 2)

    def test_capture_finishing_after_deadline_is_discarded(self):
        session = self.session()
        self.mic.hook = lambda: self.clock.wait(50)
        session.activate()
        self.assertEqual(self.stt.calls, [])

    def test_late_transcript_never_routes(self):
        session = self.session()
        self.stt.hook = lambda: self.clock.wait(50)
        session.activate()
        self.assertEqual(self.output, [])

    def test_llm_late_reply_never_spoken(self):
        chat = Mock()
        session = self.session(texts=["Jarvis, explique fotossíntese."], chat=chat)
        chat.answer.side_effect = lambda *a, **k: self.clock.wait(50) or "resposta"
        session.activate()
        self.assertEqual(self.output, [])

    def test_microphone_failure_closes_window(self):
        session = self.session(captures=[OSError("private detail")])
        session.activate()
        self.assertIn(VoiceState.ERROR, self.states)
        self.assertNotIn("private detail", " ".join(self.output))
        self.assertEqual(session.state, VoiceState.IDLE)

    def test_stt_failure_closes_window(self):
        session = self.session(texts=[VoiceError("model")])
        session.activate()
        self.assertIn(VoiceState.ERROR, self.states)

    def test_tts_failure_preserves_text_and_cooldown(self):
        session = self.session()
        self.speaker.hook = Mock(side_effect=OSError("speaker missing"))
        session.activate()
        self.assertIn("Planejamento offline", self.output[0])
        self.assertIn("resposta textual", self.output[1])
        self.assertEqual(self.clock.waits, [0.8])

    def test_text_fallback_without_tts(self):
        session = self.session(speaker=False)
        session.activate()
        self.assertTrue(self.output)
        self.assertEqual(self.clock.waits, [])

    def test_capture_closed_while_speaking(self):
        session = self.session()

        def assert_isolated():
            self.assertFalse(self.mic.active)
            self.assertEqual(session.state, VoiceState.RESPONDING)
            self.assertFalse(session.await_wake())
            with self.assertRaises(VoiceError):
                session.activate()

        self.speaker.hook = assert_isolated
        session.activate()

    def test_synthesized_command_echo_never_reinterpreted(self):
        chat = Mock()
        chat.answer.return_value = "Jarvis, ligue os monitores."
        session = self.session(
            chat=chat,
            captures=[wav(), wav()],
            texts=["Jarvis, explique fotossíntese.", "Jarvis, ligue os monitores."],
        )
        session.activate()
        self.assertEqual(len(self.speaker.texts), 1)
        self.assertIn("eco descartado", self.output[-1])
        self.assertNotIn("room_plan", " ".join(self.output))

    def test_cancel_before_capture(self):
        session = self.session()
        session.cancel.set()
        with self.assertRaises(VoiceCancelled):
            session.activate()
        self.assertEqual(self.mic.timeouts, [])

    def test_cancel_during_transcription(self):
        session = self.session()
        self.stt.hook = session.cancel.set
        with self.assertRaises(VoiceCancelled):
            session.activate()
        self.assertEqual(self.output, [])

    def test_cancel_during_tts(self):
        session = self.session()
        self.speaker.hook = session.cancel.set
        with self.assertRaises(VoiceCancelled):
            session.activate()
        self.assertEqual(len(self.mic.timeouts), 1)

    def test_ctrl_c_during_capture_closes_all(self):
        session = self.session(captures=[KeyboardInterrupt()])
        code = run_voice(session, read=lambda _: "", output=self.output.append)
        self.assertEqual(code, 0)
        self.assertTrue(self.mic.closed and self.stt.closed and self.speaker.closed)
        self.assertTrue(session.cancel.is_set())

    def test_ctrl_c_during_tts_closes_all(self):
        session = self.session()
        self.speaker.hook = Mock(side_effect=KeyboardInterrupt)
        run_voice(session, read=lambda _: "", output=self.output.append)
        self.assertTrue(session.closed)

    def test_eof_closes_resources(self):
        session = self.session()
        read = Mock(side_effect=EOFError)
        self.assertEqual(run_voice(session, read=read, output=self.output.append), 0)
        self.assertTrue(session.closed)

    def test_manual_start_and_exit(self):
        session = self.session()
        read = Mock(side_effect=["", "sair"])
        run_voice(session, read=read, output=self.output.append)
        self.assertEqual(len(self.stt.calls), 1)

    def test_terminal_text_is_not_voice_command(self):
        session = self.session()
        read = Mock(side_effect=["ligue os monitores", "sair"])
        run_voice(session, read=read, output=self.output.append)
        self.assertEqual(self.stt.calls, [])

    def test_spoken_exit(self):
        session = self.session(texts=["Jarvis, sair."])
        self.assertFalse(session.activate())

    def test_spoken_cancel_only_ends_window(self):
        session = self.session(texts=["Jarvis, cancelar"])
        self.assertTrue(session.activate())
        self.assertFalse(session.cancel.is_set())

    def test_wake_failure_falls_back_to_enter(self):
        wake = Mock(wait=Mock(side_effect=VoiceError("missing")))
        session = self.session(wake=wake)
        run_voice(
            session, manual=False, read=lambda _: "sair", output=self.output.append
        )
        self.assertIn("Fallback manual", " ".join(self.output))
        self.assertEqual(self.stt.calls, [])

    def test_wake_activates_one_multiturn_window(self):
        wake = Mock(wait=Mock(return_value=True))
        session = self.session(
            wake=wake,
            captures=[wav(), wav()],
            texts=["Jarvis, ligue os LEDs.", "Jarvis, sair"],
        )
        run_voice(session, manual=False, output=self.output.append)
        wake.wait.assert_called_once()
        self.assertEqual(len(self.stt.calls), 2)

    def test_false_wake_does_not_capture(self):
        wake = Mock(wait=Mock(side_effect=[False, KeyboardInterrupt()]))
        session = self.session(wake=wake)
        run_voice(session, manual=False, output=self.output.append)
        self.assertEqual(self.stt.calls, [])

    def test_memory_erased_at_window_end(self):
        chat = Mock(answer=Mock(return_value="Uma explicação."))
        session = self.session(chat=chat, texts=["Jarvis, explique fotossíntese."])
        session.activate()
        self.assertEqual(list(session.router.history), [])

    def test_close_idempotent_and_cannot_reactivate(self):
        session = self.session()
        session.close()
        session.close()
        with self.assertRaises(VoiceError):
            session.activate()

    def test_cleanup_continues_if_one_resource_fails(self):
        session = self.session()
        self.mic.close = Mock(side_effect=OSError)
        session.close()
        self.assertTrue(self.stt.closed and self.speaker.closed)

    def test_limits_reject_nan_infinite_out_of_range(self):
        for field, value in (
            ("active_seconds", float("nan")),
            ("capture_seconds", 31),
            ("operation_seconds", float("inf")),
            ("cooldown_seconds", 0),
            ("max_turns", True),
            ("max_turns", 21),
            ("wake_seconds", -1),
        ):
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                VoiceConfig(**{field: value})
