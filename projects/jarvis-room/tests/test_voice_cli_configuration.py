"""CLI configurável: inventário/modelo explícito e diagnóstico sem inferência."""

import io
import json
import sys
from unittest.mock import Mock, patch

from jarvis_room import room_voice_cli
from voice_fakes import OfflineVoiceTest


class VoiceCLIConfigurationTests(OfflineVoiceTest):
    def setup_cli(self, arguments):
        output = io.StringIO()
        self.enterContext(patch("sys.argv", ["room_voice_cli", *arguments]))
        self.enterContext(patch("sys.stdout", output))
        self.enterContext(patch("sys.stderr", io.StringIO()))
        self.enterContext(patch.object(sys.stdin, "isatty", return_value=True))
        self.enterContext(patch.object(sys.stdout, "isatty", return_value=True))
        return output

    def test_text_chat_selects_installed_model_without_constructing_audio(self):
        self.setup_cli(["--text-chat", "--llm", "--llm-model", "qwen3.5:0.8b"])
        runner = self.runner({"models": [{"name": "qwen3.5:0.8b", "size_bytes": 1}]})
        with (
            patch.object(room_voice_cli, "WorkerRunner", return_value=runner),
            patch.object(room_voice_cli, "run_text_chat", return_value=0) as chat,
            patch.object(room_voice_cli, "ProcessMicrophone") as mic,
            patch.object(room_voice_cli, "ResidentTranscriber") as stt,
            self.assertRaises(SystemExit) as result,
        ):
            room_voice_cli.main()
        self.assertEqual(result.exception.code, 0)
        self.assertEqual(chat.call_args.args[0].chat.model, "qwen3.5:0.8b")
        mic.assert_not_called()
        stt.assert_not_called()

    def test_nonexistent_model_never_starts_conversation(self):
        self.setup_cli(["--text-chat", "--llm", "--llm-model", "missing:latest"])
        runner = self.runner({"models": [{"name": "qwen3.5:0.8b", "size_bytes": 1}]})
        with (
            patch.object(room_voice_cli, "WorkerRunner", return_value=runner),
            patch.object(room_voice_cli, "run_text_chat") as chat,
            self.assertRaises(SystemExit) as result,
        ):
            room_voice_cli.main()
        self.assertEqual(result.exception.code, 2)
        chat.assert_not_called()

    def test_missing_preferred_model_does_not_silently_select_another_model(self):
        self.setup_cli(["--text-chat", "--llm"])
        runner = self.runner({"models": [{"name": "qwen3.5:0.8b", "size_bytes": 1}]})
        with (
            patch.object(room_voice_cli, "WorkerRunner", return_value=runner),
            self.assertRaises(SystemExit) as result,
        ):
            room_voice_cli.main()
        self.assertEqual(result.exception.code, 2)

    def test_default_voice_model_selects_installed_qwen_4b(self):
        self.setup_cli(["--text-chat", "--llm"])
        runner = self.runner(
            {"models": [{"name": "qwen3.5:4b", "size_bytes": 4_000_000_000}]}
        )
        with (
            patch.object(room_voice_cli, "WorkerRunner", return_value=runner),
            patch.object(room_voice_cli, "run_text_chat", return_value=0) as chat,
            self.assertRaises(SystemExit) as result,
        ):
            room_voice_cli.main()
        self.assertEqual(result.exception.code, 0)
        self.assertEqual(chat.call_args.args[0].chat.model, "qwen3.5:4b")

    def test_stt_capability_diagnostic_does_not_load_model(self):
        output = self.setup_cli(
            [
                "--diagnose-stt",
                "--stt-model-dir",
                "/local/model",
                "--stt-device",
                "cuda",
            ]
        )
        runner = self.runner({"model_loaded": False, "inference_performed": False})
        with patch.object(room_voice_cli, "WorkerRunner", return_value=runner):
            room_voice_cli.main()
        self.assertFalse(json.loads(output.getvalue())["stt"]["model_loaded"])
        self.assertEqual(runner.run.call_args.args[0], "stt_capabilities")
        self.assertEqual(runner.run.call_args.args[1]["compute_type"], "float16")

    def test_explicit_load_check_closes_worker_without_audio(self):
        output = self.setup_cli(["--stt-check", "--stt-model-dir", "/local/model"])
        transcriber = Mock()
        transcriber.prepare.return_value = {"device": "cpu", "transcriptions": 0}
        with (
            patch.object(
                room_voice_cli, "ResidentTranscriber", return_value=transcriber
            ),
            patch.object(room_voice_cli, "ProcessMicrophone") as mic,
        ):
            room_voice_cli.main()
        self.assertTrue(json.loads(output.getvalue())["released"])
        transcriber.prepare.assert_called_once()
        transcriber.transcribe.assert_not_called()
        transcriber.close.assert_called()
        mic.assert_not_called()

    def test_load_check_cannot_be_disguised_as_passive_diagnostic(self):
        self.setup_cli(["--stt-check", "--diagnose"])
        with self.assertRaises(SystemExit) as result:
            room_voice_cli.main()
        self.assertEqual(result.exception.code, 2)

    def test_missing_wake_license_falls_back_without_constructing_detector(self):
        output = self.setup_cli(
            ["--stt-model-dir", "/local/model", "--wake-model-dir", "/local/wake"]
        )
        with (
            patch.object(room_voice_cli, "ResidentTranscriber"),
            patch.object(room_voice_cli, "OpenWakeWord") as wake,
            patch.object(room_voice_cli, "run_voice", return_value=0) as run,
            self.assertRaises(SystemExit),
        ):
            room_voice_cli.main()
        wake.assert_not_called()
        self.assertTrue(run.call_args.kwargs["manual"])
        self.assertIn("registro de licença", output.getvalue())

    def test_llm_model_flag_without_opt_in_is_rejected(self):
        self.setup_cli(["--text-chat", "--llm-model", "qwen3.5:0.8b"])
        with self.assertRaises(SystemExit) as result:
            room_voice_cli.main()
        self.assertEqual(result.exception.code, 2)

    def test_conversation_sharing_requires_presentation_opt_in(self):
        self.setup_cli(["--share-conversation"])
        with self.assertRaises(SystemExit) as result:
            room_voice_cli.main()
        self.assertEqual(result.exception.code, 2)

    def test_voice_cli_binds_presentation_callbacks_and_closes_publisher(self):
        self.setup_cli(
            [
                "--stt-model-dir",
                "/local/model",
                "--presentation",
                "--share-conversation",
            ]
        )
        publisher = Mock()

        def run(session, **kwargs):
            session._state(room_voice_cli.VoiceState.LISTENING)
            session.on_metrics({"stage": "stt_initialization"})
            self.assertEqual(session.on_reply, publisher.conversation)
            return 0

        with (
            patch.object(room_voice_cli, "ResidentTranscriber"),
            patch(
                "jarvis_room.presentation_ipc.PresentationPublisher",
                return_value=publisher,
            ),
            patch.object(room_voice_cli, "run_voice", side_effect=run),
            self.assertRaises(SystemExit) as result,
        ):
            room_voice_cli.main()
        self.assertEqual(result.exception.code, 0)
        publisher.state.assert_called_once_with(room_voice_cli.VoiceState.LISTENING)
        publisher.metrics.assert_called_once()
        publisher.close.assert_called_once()
