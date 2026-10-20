"""Métricas da avaliação, com WAV/modelos sintéticos e worker falso."""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from jarvis_room.voice_benchmark import evaluate, evaluate_resident, word_errors
from jarvis_room.voice_contract import VoiceError
from jarvis_room.voice_stt import STTSettings
from voice_fakes import OfflineVoiceTest, wav


class VoiceBenchmarkTests(OfflineVoiceTest):
    def test_resident_evaluation_initializes_once_and_separates_load_time(self):
        root, manifest = self.fixture(
            samples=[
                {"wav": "speech.wav", "expected": "Liga os monitores"},
                {"wav": "speech.wav", "expected": "Desliga os monitores"},
            ]
        )
        transcriber = Mock()
        transcriber.prepare.return_value = {"initialization_seconds": 1.5}
        transcriber.transcribe.side_effect = [
            "Liga os monitores",
            "Desliga os monitores",
        ]
        transcriber.last_metrics = {"transcription_seconds": 0.2}
        with patch(
            "jarvis_room.voice_benchmark.ResidentTranscriber", return_value=transcriber
        ):
            result = evaluate_resident(manifest, STTSettings(str(root / "tiny")))
        transcriber.prepare.assert_called_once()
        self.assertEqual(transcriber.transcribe.call_count, 2)
        transcriber.close.assert_called_once()
        self.assertEqual(result["initialization"]["initialization_seconds"], 1.5)
        self.assertEqual(result["records"][0]["transcription_seconds"], 0.2)
        self.assertEqual(result["wer"], 0)

    def test_resident_evaluation_closes_worker_on_invalid_audio(self):
        root, manifest = self.fixture()
        (root / "speech.wav").write_bytes(b"invalid")
        transcriber = Mock()
        with (
            patch(
                "jarvis_room.voice_benchmark.ResidentTranscriber",
                return_value=transcriber,
            ),
            self.assertRaises(VoiceError),
        ):
            evaluate_resident(manifest, STTSettings(str(root / "tiny")))
        transcriber.transcribe.assert_not_called()
        transcriber.close.assert_called_once()

    def fixture(self, samples=None):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        for model in ("tiny", "base"):
            directory = root / model
            directory.mkdir()
            for name in ("model.bin", "config.json", "tokenizer.json"):
                (directory / name).write_text("fake model")
        (root / "speech.wav").write_bytes(wav())
        manifest = root / "corpus.json"
        manifest.write_text(
            json.dumps(
                samples
                or [
                    {"wav": "speech.wav", "expected": "Ligue os monitores."},
                ]
            )
        )
        return root, manifest

    def test_wer_normalizes_portuguese_and_counts_substitutions(self):
        self.assertEqual(word_errors("Ligue os LEDs.", "ligue os leds"), (0, 3))
        self.assertEqual(
            word_errors("Ligue os monitores", "desligue os monitores"), (1, 3)
        )
        self.assertEqual(word_errors("ligue os leds", "ligue leds agora"), (2, 3))

    def test_both_models_evaluated_offline_and_intent_compared(self):
        root, manifest = self.fixture()
        runner = Mock(
            run=Mock(
                return_value={
                    "text": "Ligue os monitores.",
                    "seconds": 0.5,
                    "peak_rss_kib": 123456,
                }
            )
        )
        result = evaluate(
            manifest,
            {"tiny": str(root / "tiny"), "base": str(root / "base")},
            runner=runner,
        )
        self.assertEqual(runner.run.call_count, 2)
        self.assertEqual(result["models"]["tiny"]["wer"], 0)
        self.assertTrue(result["models"]["base"]["records"][0]["room_intent_match"])
        self.assertFalse(result["physical_action_verified"])

    def test_wrong_action_counts_as_intent_mismatch(self):
        root, manifest = self.fixture()
        runner = Mock(
            run=Mock(
                return_value={
                    "text": "Desligue os monitores.",
                    "seconds": 0.5,
                    "peak_rss_kib": 1,
                }
            )
        )
        result = evaluate(manifest, {"tiny": str(root / "tiny")}, runner=runner)
        self.assertFalse(result["models"]["tiny"]["records"][0]["room_intent_match"])

    def test_invalid_wav_rejected_before_worker(self):
        root, manifest = self.fixture()
        (root / "speech.wav").write_bytes(b"not audio")
        runner = Mock()
        with self.assertRaises(VoiceError):
            evaluate(manifest, {"tiny": str(root / "tiny")}, runner=runner)
        runner.run.assert_not_called()

    def test_manifest_size_limited(self):
        root, manifest = self.fixture()
        manifest.write_text(" " * 65537)
        with self.assertRaises(ValueError):
            evaluate(manifest, {"tiny": str(root / "tiny")}, runner=Mock())
