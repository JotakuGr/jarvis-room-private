"""CPU/CUDA e persistência do motor com bibliotecas nativas falsas."""

import importlib.util
import io
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from jarvis_room.voice_backends import worker_environment
from jarvis_room.voice_contract import VoiceError
from jarvis_room.voice_stt import (
    ROOM_TERMS,
    SpeechEngine,
    STTSettings,
    cuda_library_paths,
    verify_compute,
)
from voice_fakes import OfflineVoiceTest, wav


class STTConfigurationTests(OfflineVoiceTest):
    def upstream_backend(self):
        registry = SimpleNamespace(register=lambda name: lambda cls: cls)
        constructor = Mock()
        constructor.return_value.transcribe.return_value = (
            [],
            SimpleNamespace(language="pt"),
        )
        self.enterContext(
            patch.dict(
                sys.modules,
                {
                    "openjarvis.core.registry": SimpleNamespace(
                        SpeechRegistry=registry
                    ),
                    "openjarvis.speech._stubs": SimpleNamespace(
                        Segment=lambda **kw: SimpleNamespace(**kw),
                        SpeechBackend=object,
                        TranscriptionResult=lambda **kw: SimpleNamespace(**kw),
                    ),
                    "faster_whisper": SimpleNamespace(WhisperModel=constructor),
                    "ctranslate2": SimpleNamespace(
                        get_supported_compute_types=lambda device: {"int8"}
                    ),
                },
            )
        )
        path = (
            Path(__file__).resolve().parents[3]
            / "src/openjarvis/speech/faster_whisper.py"
        )
        spec = importlib.util.spec_from_file_location("isolated_upstream_whisper", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module, constructor

    def test_upstream_in_memory_audio_and_local_only_options(self):
        module, constructor = self.upstream_backend()
        seen = {}

        def transcribe(source, **options):
            self.assertIsInstance(source, io.BytesIO)
            seen.update(audio=source.read(), options=options, source=source)
            return [], SimpleNamespace(language="pt")

        constructor.return_value.transcribe.side_effect = transcribe
        backend = module.FasterWhisperBackend(
            "/local/model",
            device="cpu",
            compute_type="int8",
            local_files_only=True,
            in_memory_audio=True,
        )
        with patch.object(
            module.tempfile,
            "NamedTemporaryFile",
            side_effect=AssertionError("Áudio deve ficar em RAM"),
        ):
            backend.transcribe(
                b"fake audio",
                language="pt",
                beam_size=1,
                condition_on_previous_text=False,
                vad_filter=False,
            )
        constructor.assert_called_once_with(
            "/local/model", device="cpu", compute_type="int8", local_files_only=True
        )
        self.assertEqual(seen["audio"], b"fake audio")
        self.assertFalse(seen["options"]["condition_on_previous_text"])
        self.assertTrue(seen["source"].closed)

    def test_upstream_in_memory_stream_closes_on_failure(self):
        module, constructor = self.upstream_backend()
        seen = []

        def fail(source, **kwargs):
            seen.append(source)
            raise RuntimeError("fake decoder failure")

        constructor.return_value.transcribe.side_effect = fail
        backend = module.FasterWhisperBackend(
            device="cpu", compute_type="int8", in_memory_audio=True
        )
        with self.assertRaises(RuntimeError):
            backend.transcribe(b"fake")
        self.assertTrue(seen[0].closed)

    def test_upstream_legacy_temporary_file_behavior_is_preserved(self):
        module, constructor = self.upstream_backend()
        seen = []

        def transcribe(path, **kwargs):
            seen.append(path)
            self.assertEqual(Path(path).read_bytes(), b"fake audio")
            return [], SimpleNamespace(language="pt")

        constructor.return_value.transcribe.side_effect = transcribe
        module.FasterWhisperBackend(device="cpu", compute_type="int8").transcribe(
            b"fake audio"
        )
        self.assertFalse(Path(seen[0]).exists())

    def assets(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        for name in ("model.bin", "config.json", "tokenizer.json"):
            (root / name).write_text("fake model")
        return str(root)

    def native(self, device="cpu", compute="int8"):
        ct2 = SimpleNamespace(
            get_cuda_device_count=Mock(return_value=1),
            get_supported_compute_types=Mock(return_value={compute}),
        )
        constructor = Mock()
        backend = constructor.return_value
        backend._ensure_model.return_value = SimpleNamespace(
            model=SimpleNamespace(device=device, compute_type=compute)
        )
        backend.transcribe.return_value = SimpleNamespace(
            text="Jarvis, liga os monitores", language="pt"
        )
        self.enterContext(
            patch.dict(
                sys.modules,
                {
                    "ctranslate2": ct2,
                    "openjarvis.speech.faster_whisper": SimpleNamespace(
                        FasterWhisperBackend=constructor
                    ),
                },
            )
        )
        return ct2, constructor, backend

    def test_cpu_int8_configuration(self):
        settings = STTSettings(self.assets())
        self.assertEqual((settings.device, settings.compute_type), ("cpu", "int8"))
        self.assertFalse(settings.vad_filter or settings.room_terms)

    def test_cuda_float16_configuration(self):
        settings = STTSettings(
            self.assets(), device="cuda", compute_type="float16", gpu_index=1
        )
        self.assertEqual(settings.options()["gpu_index"], 1)

    def test_invalid_device_and_compute_type(self):
        for values in (
            {"device": "auto"},
            {"device": "mps"},
            {"compute_type": "unknown"},
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                STTSettings(self.assets(), **values)

    def test_beam_gpu_and_boolean_limits(self):
        for values in (
            {"beam_size": 0},
            {"beam_size": 6},
            {"beam_size": True},
            {"gpu_index": -1},
            {"gpu_index": 32},
            {"vad_filter": "yes"},
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                STTSettings(self.assets(), **values)

    def test_model_assets_are_required(self):
        directory = self.assets()
        (Path(directory) / "tokenizer.json").unlink()
        with self.assertRaises(VoiceError):
            STTSettings(directory).validate_assets()

    def test_compute_type_must_be_supported_no_silent_fallback(self):
        ct2, _, _ = self.native()
        with self.assertRaisesRegex(VoiceError, "stt_compute_type_unsupported"):
            verify_compute(STTSettings(self.assets(), compute_type="float16"), ct2)

    def test_missing_cuda_is_explicit_error(self):
        ct2, _, _ = self.native()
        ct2.get_cuda_device_count.return_value = 0
        with self.assertRaisesRegex(VoiceError, "stt_cuda_unavailable"):
            verify_compute(
                STTSettings(self.assets(), device="cuda", compute_type="float16"), ct2
            )

    def test_cuda_driver_failure_is_sanitized(self):
        ct2, _, _ = self.native()
        ct2.get_cuda_device_count.side_effect = RuntimeError("private driver path")
        with self.assertRaisesRegex(VoiceError, "^stt_device_unavailable$"):
            verify_compute(STTSettings(self.assets(), device="cuda"), ct2)

    def test_gpu_visibility_is_scoped_to_stt_operation(self):
        runtime = self.enterContext(tempfile.TemporaryDirectory())
        options = STTSettings(
            self.assets(), device="cuda", compute_type="float16", gpu_index=1
        ).options()
        with patch(
            "jarvis_room.voice_stt.cuda_library_paths",
            return_value=["/venv/cublas/lib", "/venv/cudnn/lib"],
        ):
            for operation in (
                "resident_stt",
                "stt",
                "stt_capabilities",
                "benchmark_stt",
            ):
                with self.subTest(operation=operation):
                    env = worker_environment(operation, options, runtime)
                    self.assertEqual(env["CUDA_VISIBLE_DEVICES"], "1")
                    self.assertTrue(
                        env["LD_LIBRARY_PATH"].startswith(
                            "/venv/cublas/lib:/venv/cudnn/lib"
                        )
                    )

    def test_capture_wake_tts_and_llm_never_inherit_cuda_visibility(self):
        runtime = self.enterContext(tempfile.TemporaryDirectory())
        with (
            patch.dict("os.environ", {"CUDA_VISIBLE_DEVICES": "0"}),
            patch("jarvis_room.voice_stt.cuda_library_paths") as discover,
        ):
            for operation in (
                "capture",
                "wake",
                "resident_tts",
                "speak",
                "play",
                "chat",
            ):
                with self.subTest(operation=operation):
                    self.assertEqual(
                        worker_environment(operation, {"device": "cuda"}, runtime)[
                            "CUDA_VISIBLE_DEVICES"
                        ],
                        "",
                    )
        discover.assert_not_called()

    def test_cuda_library_discovery_uses_metadata_without_importing_cuda(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        library = root / "libcublas.so.12"
        library.write_bytes(b"fake")
        package = SimpleNamespace(
            files=[Path("libcublas.so.12"), Path("metadata.txt")],
            locate_file=lambda p: root / p,
        )
        with patch("jarvis_room.voice_stt.distribution", return_value=package):
            self.assertEqual(cuda_library_paths(), [str(root)])

    def test_model_is_loaded_once_for_two_transcriptions(self):
        _, constructor, backend = self.native()
        engine = SpeechEngine(STTSettings(self.assets()))
        first, second = engine.transcribe(wav()), engine.transcribe(wav())
        constructor.assert_called_once()
        backend._ensure_model.assert_called_once()
        self.assertEqual(backend.transcribe.call_count, 2)
        self.assertTrue(first["metrics"]["first_transcription"])
        self.assertFalse(second["metrics"]["first_transcription"])
        self.assertEqual(second["metrics"]["transcriptions"], 2)

    def test_portuguese_options_and_previous_text_disabled(self):
        _, _, backend = self.native()
        engine = SpeechEngine(
            STTSettings(self.assets(), beam_size=3, vad_filter=True, room_terms=True)
        )
        engine.transcribe(wav())
        options = backend.transcribe.call_args.kwargs
        self.assertEqual(options["language"], "pt")
        self.assertEqual(options["beam_size"], 3)
        self.assertFalse(options["condition_on_previous_text"])
        self.assertTrue(options["vad_filter"])
        self.assertEqual(options["initial_prompt"], ROOM_TERMS)

    def test_linguistic_context_never_replaces_dangerous_words(self):
        _, _, backend = self.native()
        backend.transcribe.return_value.text = "Jarvis, não desliga os monitores"
        engine = SpeechEngine(STTSettings(self.assets(), room_terms=True))
        self.assertEqual(
            engine.transcribe(wav())["text"], "Jarvis, não desliga os monitores"
        )

    def test_invalid_audio_never_reaches_backend(self):
        _, _, backend = self.native()
        engine = SpeechEngine(STTSettings(self.assets()))
        with self.assertRaises(VoiceError):
            engine.transcribe(b"invalid")
        backend.transcribe.assert_not_called()

    def test_gpu_out_of_memory_becomes_component_error(self):
        _, _, backend = self.native("cuda", "float16")
        backend.transcribe.side_effect = RuntimeError("CUDA OOM with private details")
        engine = SpeechEngine(
            STTSettings(self.assets(), device="cuda", compute_type="float16")
        )
        with self.assertRaisesRegex(VoiceError, "^stt_transcription_failed$"):
            engine.transcribe(wav())

    def test_empty_transcript_is_allowed_but_oversized_is_not(self):
        _, _, backend = self.native()
        engine = SpeechEngine(STTSettings(self.assets()))
        backend.transcribe.return_value.text = ""
        self.assertEqual(engine.transcribe(wav())["text"], "")
        backend.transcribe.return_value.text = "a" * 257
        with self.assertRaises(VoiceError):
            engine.transcribe(wav())

    def test_reported_device_precision_and_memory_are_metadata_only(self):
        self.native("cuda", "float16")
        engine = SpeechEngine(
            STTSettings(self.assets(), device="cuda", compute_type="float16")
        )
        health = engine.health()
        self.assertEqual(
            (health["device"], health["compute_type"]), ("cuda", "float16")
        )
        self.assertGreater(health["peak_rss_kib"], 0)
        self.assertNotIn("text", health)
        engine.close()
        self.assertIsNone(engine.backend._model)
