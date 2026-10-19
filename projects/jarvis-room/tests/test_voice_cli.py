"""Diagnóstico passivo e flags: nenhuma autorização física exposta."""

import io
import sys
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import Mock, patch

from jarvis_room import room_voice_cli
from jarvis_room.voice_contract import VoiceError
from jarvis_room.voice_diagnostics import audio_diagnostics
from jarvis_room.voice_worker import main as worker_main
from voice_fakes import OfflineVoiceTest


class VoiceCLITests(OfflineVoiceTest):
    def test_diagnostic_does_not_capture_or_change_settings(self):
        sd = Mock()
        sd.default.device = (0, 1)
        sd.get_portaudio_version.return_value = (1, "fake PortAudio")
        sd.query_hostapis.return_value = [{"name": "PulseAudio"}]
        sd.query_devices.return_value = [
            {
                "name": "Microphone",
                "max_input_channels": 1,
                "max_output_channels": 0,
                "default_samplerate": 48000,
            },
            {
                "name": "Speaker",
                "max_input_channels": 0,
                "max_output_channels": 2,
                "default_samplerate": 48000,
            },
        ]
        with patch("importlib.util.find_spec", return_value=None):
            report = audio_diagnostics(sd)
        self.assertTrue(report["input_available"] and report["output_available"])
        self.assertFalse(report["capture_performed"] or report["system_changes"])
        sd.RawInputStream.assert_not_called()
        sd.play.assert_not_called()
        self.assertEqual(report["audio_status"], "enumerated_not_validated")

    def test_diagnostic_missing_dependency(self):
        with patch("importlib.util.find_spec", return_value=None):
            report = audio_diagnostics()
        self.assertEqual(report["audio_status"], "sounddevice_missing")
        self.assertFalse(report["input_available"])

    def test_diagnostic_portaudio_failure(self):
        sd = Mock(get_portaudio_version=Mock(side_effect=OSError))
        with patch("importlib.util.find_spec", return_value=None):
            report = audio_diagnostics(sd)
        self.assertEqual(report["audio_status"], "portaudio_unavailable")

    def test_diagnostic_no_devices_is_not_success(self):
        sd = Mock()
        sd.get_portaudio_version.return_value = (1, "fake")
        sd.default.device = (-1, -1)
        sd.query_hostapis.return_value = []
        sd.query_devices.return_value = []
        with patch("importlib.util.find_spec", return_value=None):
            report = audio_diagnostics(sd)
        self.assertFalse(report["input_available"] or report["output_available"])

    def test_cli_diagnostic_no_tty_or_model_needed(self):
        runner = self.runner({"capture_performed": False})
        with (
            patch.object(sys, "argv", ["room_voice_cli", "--diagnose"]),
            patch.object(room_voice_cli, "WorkerRunner", return_value=runner),
            redirect_stdout(io.StringIO()) as out,
        ):
            room_voice_cli.main()
        self.assertIn('"capture_performed": false', out.getvalue())

    def test_cli_diagnostic_failure_exit_code(self):
        runner = Mock(run=Mock(side_effect=VoiceError("private failure")))
        with (
            patch.object(sys, "argv", ["room_voice_cli", "--diagnose"]),
            patch.object(room_voice_cli, "WorkerRunner", return_value=runner),
            redirect_stdout(io.StringIO()) as out,
            self.assertRaises(SystemExit) as exc,
        ):
            room_voice_cli.main()
        self.assertEqual(exc.exception.code, 1)
        self.assertNotIn("private failure", out.getvalue())

    def test_cli_forbids_execution_flags(self):
        for option in ("--execute", "--enable-samsung", "--token-file", "--audit-file"):
            with (
                self.subTest(option=option),
                redirect_stdout(io.StringIO()),
                patch("sys.stderr", io.StringIO()),
                self.assertRaises(SystemExit),
            ):
                room_voice_cli.parser().parse_args([option])

    def test_cli_non_tty_refused(self):
        with (
            patch.object(sys, "argv", ["room_voice_cli"]),
            patch.object(sys.stdin, "isatty", return_value=False),
            patch("sys.stderr", io.StringIO()),
            self.assertRaises(SystemExit) as exc,
        ):
            room_voice_cli.main()
        self.assertEqual(exc.exception.code, 2)

    def test_worker_exception_returns_no_private_details(self):
        fake_stdin = SimpleNamespace(
            buffer=io.BytesIO(b'{"operation":"physical_execute","options":{}}')
        )
        with patch("sys.stdin", fake_stdin), redirect_stdout(io.StringIO()) as out:
            worker_main()
        self.assertEqual(out.getvalue().strip(), '{"ok": false}')

    def test_worker_malformed_request(self):
        with (
            patch("sys.stdin", SimpleNamespace(buffer=io.BytesIO(b"invalid"))),
            redirect_stdout(io.StringIO()) as out,
        ):
            worker_main()
        self.assertEqual(out.getvalue().strip(), '{"ok": false}')
