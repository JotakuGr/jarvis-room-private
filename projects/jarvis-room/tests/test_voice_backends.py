"""Contratos dos workers com bibliotecas falsas; nenhum modelo é baixado."""

import base64
import json
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock, patch

from jarvis_room.voice_backends import (
    LocalChat,
    LocalSpeaker,
    LocalTranscriber,
    OpenWakeWord,
    ProcessMicrophone,
    WorkerRunner,
)
from jarvis_room.voice_contract import VoiceCancelled, VoiceError
from jarvis_room.voice_worker import (
    AcousticGate,
    execute,
    speak_local,
    transcribe_local,
    wait_for_wake,
)
from voice_fakes import OfflineVoiceTest, wav


class VoiceBackendTests(OfflineVoiceTest):
    def assets(self, names):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        for name in names:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fake asset", encoding="utf-8")
        return str(root)

    def stt_assets(self):
        return self.assets(["model.bin", "config.json", "tokenizer.json"])

    def tts_assets(self):
        return self.assets(["config.json", "kokoro-v1_0.pth", "voices/pm_santa.pt"])

    def wake_assets(self):
        return self.assets(
            ["hey_jarvis_v0.1.onnx", "melspectrogram.onnx", "embedding_model.onnx"]
        )

    def test_stt_requires_complete_local_assets(self):
        directory = self.assets(["model.bin", "config.json"])
        with self.assertRaises(VoiceError):
            LocalTranscriber(self.runner(""), directory)

    def test_stt_rejects_model_name_that_would_download(self):
        with self.assertRaises(VoiceError):
            LocalTranscriber(self.runner(""), "tiny")

    def test_stt_worker_preserves_pt_cpu_int8(self):
        constructor = Mock()
        constructor.return_value.transcribe.return_value = SimpleNamespace(
            text="Ligue os LEDs.", language="pt"
        )
        self.enterContext(
            patch.dict(
                sys.modules,
                {
                    "openjarvis.speech.faster_whisper": SimpleNamespace(
                        FasterWhisperBackend=constructor
                    ),
                },
            )
        )
        directory = self.stt_assets()
        result = transcribe_local(
            {"model_dir": directory, "audio": base64.b64encode(wav()).decode()}
        )
        self.assertEqual(result, "Ligue os LEDs.")
        constructor.assert_called_once_with(
            model_size=directory, device="cpu", compute_type="int8"
        )
        self.assertEqual(
            constructor.return_value.transcribe.call_args.kwargs,
            {"language": "pt", "format": "wav"},
        )

    def test_stt_wrong_language_rejected(self):
        backend = Mock()
        backend.return_value.transcribe.return_value = SimpleNamespace(
            text="hello", language="en"
        )
        self.enterContext(
            patch.dict(
                sys.modules,
                {
                    "openjarvis.speech.faster_whisper": SimpleNamespace(
                        FasterWhisperBackend=backend
                    ),
                },
            )
        )
        with self.assertRaises(VoiceError):
            transcribe_local(
                {
                    "model_dir": self.stt_assets(),
                    "audio": base64.b64encode(wav()).decode(),
                }
            )

    def test_stt_validates_wav_before_worker(self):
        runner = self.runner("text")
        transcriber = LocalTranscriber(runner, self.stt_assets())
        with self.assertRaises(VoiceError):
            transcriber.transcribe(b"bad", timeout=2, cancel=Event())
        runner.run.assert_not_called()

    def test_stt_limits_transcript(self):
        transcriber = LocalTranscriber(self.runner("x" * 257), self.stt_assets())
        with self.assertRaises(VoiceError):
            transcriber.transcribe(wav(), timeout=2, cancel=Event())

    def test_stt_accepts_simulated_portuguese(self):
        transcriber = LocalTranscriber(
            self.runner("  Jarvis, ligue os LEDs.  "), self.stt_assets()
        )
        self.assertEqual(
            transcriber.transcribe(wav(), timeout=2, cancel=Event()),
            "Jarvis, ligue os LEDs.",
        )

    def test_microphone_process_passes_limits_and_device(self):
        runner = self.runner(base64.b64encode(wav()).decode())
        mic = ProcessMicrophone(runner, device=3, threshold=600)
        self.assertEqual(mic.capture(timeout=2, cancel=Event()), wav())
        self.assertEqual(
            runner.run.call_args.args,
            ("capture", {"device": 3, "threshold": 600, "seconds": 2}),
        )
        self.assertEqual(runner.run.call_args.kwargs["timeout"], 7)

    def test_tts_has_explicit_brazilian_voice(self):
        runner = self.runner(None)
        speaker = LocalSpeaker(
            runner, self.tts_assets(), speed=1.2, volume=0.5, device=4
        )
        speaker.speak("Olá, operador.", timeout=10, cancel=Event())
        options = runner.run.call_args.args[1]
        self.assertEqual(
            (options["voice"], options["device"], options["speed"], options["volume"]),
            ("pm_santa", 4, 1.2, 0.5),
        )

    def test_tts_does_not_accept_english_default_or_invalid_limits(self):
        directory = self.tts_assets()
        for options in ({"voice": "af_heart"}, {"speed": float("nan")}, {"volume": 2}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                LocalSpeaker(self.runner(None), directory, **options)

    def test_tts_limits_text(self):
        runner = self.runner(None)
        LocalSpeaker(runner, self.tts_assets()).speak(
            "a" * 2000, timeout=5, cancel=Event()
        )
        self.assertEqual(len(runner.run.call_args.args[1]["text"]), 800)

    def test_kokoro_reuses_backend_with_local_config_weights_and_voice(self):
        directory = self.tts_assets()
        model = Mock()
        model.to.return_value.eval.return_value = model
        constructor = Mock(return_value=model)
        pipeline = SimpleNamespace(voices={})
        torch = SimpleNamespace(load=Mock(return_value="tensor"))
        self.enterContext(
            patch.dict(
                sys.modules,
                {"kokoro": SimpleNamespace(KModel=constructor), "torch": torch},
            )
        )

        class FakeKokoro:
            def __init__(self, **kwargs):
                self._model = None

            def _ensure_pipeline(self, lang):
                self.assert_lang = lang
                self._ensure_model()
                return pipeline

            def synthesize(self, text, **kwargs):
                return SimpleNamespace(audio=b"fake WAV")

            def close(self):
                pass

        self.enterContext(
            patch.dict(
                sys.modules,
                {
                    "openjarvis.speech.kokoro_tts": SimpleNamespace(
                        KokoroTTSBackend=FakeKokoro
                    ),
                },
            )
        )
        with patch("jarvis_room.voice_audio.play_audio") as play:
            speak_local(
                {
                    "model_dir": directory,
                    "voice": "pm_santa",
                    "text": "Olá.",
                    "speed": 1,
                    "volume": 0.5,
                    "device": 2,
                    "seconds": 10,
                }
            )
        kwargs = constructor.call_args.kwargs
        self.assertEqual(kwargs["config"], str(Path(directory) / "config.json"))
        self.assertEqual(kwargs["model"], str(Path(directory) / "kokoro-v1_0.pth"))
        model.to.assert_called_once_with("cpu")
        torch.load.assert_called_once_with(
            str(Path(directory) / "voices/pm_santa.pt"),
            map_location="cpu",
            weights_only=True,
        )
        self.assertEqual(pipeline.voices, {"pm_santa": "tensor"})
        play.assert_called_once()

    def test_wake_assets_required_no_name_fallback(self):
        with self.assertRaises(VoiceError):
            OpenWakeWord(self.runner(False), self.assets([]))

    def test_wake_only_accepts_local_onnx_filename(self):
        for name in ("../outside.onnx", "model.tflite", "/tmp/model.onnx"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                OpenWakeWord(self.runner(False), self.wake_assets(), model=name)

    def test_wake_detection_is_boolean_with_timeout(self):
        runner = self.runner(True)
        detector = OpenWakeWord(runner, self.wake_assets(), device=2)
        self.assertTrue(detector.wait(timeout=3, cancel=Event()))
        self.assertEqual(runner.run.call_args.args[0], "wake")
        self.assertEqual(runner.run.call_args.kwargs["timeout"], 8)

    def test_wake_non_boolean_rejected(self):
        detector = OpenWakeWord(self.runner("Jarvis"), self.wake_assets())
        with self.assertRaises(VoiceError):
            detector.wait(timeout=1, cancel=Event())

    def test_wake_gate_requires_consecutive_acoustic_frames(self):
        gate = AcousticGate(0.6)
        self.assertFalse(gate.accept(0.9, 1000))
        self.assertTrue(gate.accept(0.9, 1000))

    def test_wake_gate_rejects_silence_noise_and_nan(self):
        gate = AcousticGate(0.6)
        for score, rms in (
            (0.9, 0),
            (0.2, 1000),
            (float("nan"), 1000),
            (0.9, 1000),
            (0.2, 1000),
        ):
            self.assertFalse(gate.accept(score, rms))

    def test_wake_worker_uses_acoustic_model_cpu_and_closes_stream(self):
        from jarvis_room import voice_audio

        model = Mock(predict=Mock(return_value={"hey_jarvis_v0.1": 0.9}))
        constructor = Mock(return_value=model)
        mic = Mock()

        @contextmanager
        def frames(**kwargs):
            yield iter([bytes([255, 127]) * 1280] * 2)

        mic.frames = frames
        self.enterContext(
            patch.dict(
                sys.modules,
                {
                    "numpy": SimpleNamespace(frombuffer=lambda data, dtype: data),
                    "openwakeword.model": SimpleNamespace(Model=constructor),
                },
            )
        )
        with patch.object(voice_audio, "SoundDeviceMicrophone", return_value=mic):
            detected = wait_for_wake(
                {
                    "model_dir": self.wake_assets(),
                    "model": "hey_jarvis_v0.1.onnx",
                    "threshold": 0.6,
                    "device": 2,
                    "seconds": 3,
                }
            )
        self.assertTrue(detected)
        self.assertEqual(constructor.call_args.kwargs["device"], "cpu")
        self.assertEqual(constructor.call_args.kwargs["inference_framework"], "onnx")
        self.assertEqual(model.predict.call_count, 2)
        mic.close.assert_called_once()
        model.reset.assert_called_once()

    def test_chat_worker_uses_existing_registry_adapter(self):
        adapter = Mock(return_value="Informação local")
        constructor = Mock(return_value=adapter)
        self.enterContext(
            patch.dict(
                sys.modules,
                {
                    "jarvis_room.provider_chat_adapter": SimpleNamespace(
                        RegistryChatAdapter=constructor
                    ),
                },
            )
        )
        self.assertEqual(
            execute("chat", {"prompt": "Explique ciência"}), "Informação local"
        )
        adapter.assert_called_once_with("Explique ciência")

    def test_chat_reuses_worker_informational_route(self):
        runner = self.runner("informação")
        self.assertEqual(
            LocalChat(runner).answer("pergunta", timeout=2, cancel=Event()),
            "informação",
        )
        self.assertEqual(runner.run.call_args.args, ("chat", {"prompt": "pergunta"}))

    def test_worker_rejects_unknown_operation(self):
        with self.assertRaises(VoiceError):
            execute("physical_execute", {})

    def fake_process(self, payload=None, *, code=0, running=False):
        process = Mock(pid=12345, returncode=code)
        process.poll.return_value = None if running else code

        def start(*args, **kwargs):
            self.process_options = kwargs
            kwargs["stdout"].write(
                json.dumps(payload or {"ok": True, "result": "result"}).encode()
            )
            kwargs["stdout"].flush()
            return process

        self.enterContext(patch("subprocess.Popen", side_effect=start))
        self.kill = self.enterContext(patch("os.killpg"))
        return process

    def test_worker_cpu_offline_environment_and_cleanup(self):
        process = self.fake_process()
        self.assertEqual(
            WorkerRunner().run("diagnose", {}, timeout=1, cancel=Event()), "result"
        )
        env = self.process_options["env"]
        self.assertEqual(env["HF_HUB_OFFLINE"], "1")
        self.assertEqual(env["TRANSFORMERS_OFFLINE"], "1")
        self.assertEqual(env["CUDA_VISIBLE_DEVICES"], "")
        self.assertTrue(self.process_options["start_new_session"])
        process.wait.assert_called_once()
        self.kill.assert_not_called()

    def test_worker_timeout_kills_process_group(self):
        process = self.fake_process(running=True)
        with patch("time.monotonic", side_effect=[0, 2]), self.assertRaises(VoiceError):
            WorkerRunner().run("stt", {}, timeout=1, cancel=Event())
        self.kill.assert_called_once()
        process.wait.assert_called_once()

    def test_worker_cancel_kills_process_group(self):
        process = self.fake_process(running=True)
        cancel = Event()

        def poll():
            cancel.set()
            return None

        process.poll.side_effect = poll
        with self.assertRaises(VoiceCancelled):
            WorkerRunner().run("stt", {}, timeout=1, cancel=cancel)
        self.kill.assert_called_once()
        process.wait.assert_called_once()

    def test_worker_ctrl_c_kills_process_group(self):
        process = self.fake_process(running=True)
        with (
            patch("time.monotonic", side_effect=KeyboardInterrupt),
            self.assertRaises(KeyboardInterrupt),
        ):
            WorkerRunner().run("stt", {}, timeout=1, cancel=Event())
        self.kill.assert_called_once()
        process.wait.assert_called_once()

    def test_worker_failure_not_returned_as_transcript(self):
        self.fake_process({"ok": False})
        with self.assertRaises(VoiceError):
            WorkerRunner().run("stt", {}, timeout=1, cancel=Event())

    def test_worker_output_limit(self):
        self.fake_process({"ok": True, "result": "x" * 100})
        with (
            patch("jarvis_room.voice_backends.MAX_RESULT", 20),
            self.assertRaises(VoiceError),
        ):
            WorkerRunner().run("stt", {}, timeout=1, cancel=Event())
