"""Kokoro brasileiro residente em CPU; reprodução continua em outro processo."""

from __future__ import annotations

import base64
import io
import time
import wave
from threading import Event

from .voice_backends import PT_VOICES, LocalSpeaker, local_file
from .voice_contract import VoiceError
from .voice_resident import ResidentWorker


def validate_tts_wav(audio: bytes) -> None:
    if not isinstance(audio, bytes) or not 44 <= len(audio) <= 1_500_000:
        raise VoiceError("tts_audio_limit")
    try:
        with wave.open(io.BytesIO(audio), "rb") as source:
            if (
                source.getnchannels(),
                source.getsampwidth(),
                source.getframerate(),
                source.getcomptype(),
            ) != (1, 2, 24000, "NONE"):
                raise VoiceError("tts_invalid_wav")
            frames = source.getnframes()
            if (
                not 0 < frames <= 24000 * 30
                or len(source.readframes(frames)) != frames * 2
            ):
                raise VoiceError("tts_audio_limit")
    except (wave.Error, EOFError) as exc:
        raise VoiceError("tts_invalid_wav") from exc


class KokoroEngine:
    def __init__(self, options: dict) -> None:
        import torch
        from kokoro import KModel

        from openjarvis.speech.kokoro_tts import KokoroTTSBackend

        started = time.monotonic()
        directory, voice = options["model_dir"], options["voice"]
        if voice not in PT_VOICES or not 0.5 <= options["speed"] <= 2:
            raise VoiceError("tts_invalid_configuration")
        for name in ("config.json", "kokoro-v1_0.pth", f"voices/{voice}.pt"):
            local_file(directory, name)

        class LocalKokoro(KokoroTTSBackend):
            def _ensure_model(self):
                if self._model is None:
                    self._model = (
                        KModel(
                            repo_id="hexgrad/Kokoro-82M",
                            config=local_file(directory, "config.json"),
                            model=local_file(directory, "kokoro-v1_0.pth"),
                        )
                        .to("cpu")
                        .eval()
                    )
                return self._model

        self.backend = LocalKokoro(device="cpu", max_cached_pipelines=1)
        try:
            pipeline = self.backend._ensure_pipeline("p")
            pipeline.voices[voice] = torch.load(
                local_file(directory, f"voices/{voice}.pt"),
                map_location="cpu",
                weights_only=True,
            )
        except BaseException:
            self.backend.close()
            raise
        self.options, self.count = options.copy(), 0
        self.initialization_seconds = time.monotonic() - started

    def health(self) -> dict:
        return {
            "backend": "kokoro",
            "device": "cpu",
            "voice": self.options["voice"],
            "language": "pt-BR",
            "initialization_seconds": self.initialization_seconds,
            "syntheses": self.count,
        }

    def synthesize(self, text: str) -> dict:
        if not isinstance(text, str) or not text.strip() or len(text) > 380:
            raise VoiceError("tts_text_limit")
        started = time.monotonic()
        result = self.backend.synthesize(
            text,
            voice_id=self.options["voice"],
            speed=self.options["speed"],
            output_format="wav",
        )
        validate_tts_wav(result.audio)
        self.count += 1
        return {
            "audio": base64.b64encode(result.audio).decode(),
            "metrics": {
                **self.health(),
                "synthesis_seconds": time.monotonic() - started,
            },
        }

    def close(self) -> None:
        self.backend.close()


class ResidentSpeaker(LocalSpeaker):
    def __init__(
        self, *args, startup_seconds: float = 120, worker=None, **kwargs
    ) -> None:
        super().__init__(*args, **kwargs)
        from .voice_stt import validate_timeout

        validate_timeout(startup_seconds)
        self.startup_seconds = startup_seconds
        self.worker = (
            worker if worker is not None else ResidentWorker("tts", self.options)
        )
        self.last_metrics: dict = {}

    def speak(self, text: str, *, timeout: float, cancel: Event) -> None:
        deadline = time.monotonic() + timeout
        self.worker.start(timeout=min(timeout, self.startup_seconds), cancel=cancel)
        remaining = deadline - time.monotonic()
        result = self.worker.request(
            "synthesize", {"text": text[:380]}, timeout=remaining, cancel=cancel
        )
        try:
            audio = base64.b64decode(result["audio"], validate=True)
            validate_tts_wav(audio)
            self.last_metrics = result["metrics"]
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise VoiceError("tts_timeout")
            self.runner.run(
                "play",
                {
                    "audio": result["audio"],
                    "device": self.options["device"],
                    "volume": self.options["volume"],
                    "seconds": remaining,
                },
                timeout=remaining,
                cancel=cancel,
            )
        except BaseException:
            self.worker.close()
            raise

    def close(self) -> None:
        self.worker.close()
