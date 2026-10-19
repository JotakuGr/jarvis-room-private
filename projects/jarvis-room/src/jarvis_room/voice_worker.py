"""Worker privado. Não oferece controlador, transporte HA ou ferramentas ao LLM."""

from __future__ import annotations

import base64
import contextlib
import json
import os
import sys
from pathlib import Path
from threading import Event

from .voice_backends import PT_VOICES, local_file
from .voice_contract import VoiceError


def notify_audio_ready() -> None:
    path = os.environ.get("JARVIS_VOICE_READY_FILE")
    if path:
        Path(path).touch()


def transcribe_local(options: dict) -> str:
    from openjarvis.speech.faster_whisper import FasterWhisperBackend

    from .voice_audio import wav_pcm

    audio = base64.b64decode(options["audio"], validate=True)
    wav_pcm(audio)
    directory = options["model_dir"]
    for name in ("model.bin", "config.json", "tokenizer.json"):
        local_file(directory, name)
    backend = FasterWhisperBackend(
        model_size=directory, device="cpu", compute_type="int8"
    )
    # pt é o código aceito pelo Whisper; pt-BR não é um código separado.
    result = backend.transcribe(audio, language="pt", format="wav")
    if result.language not in (None, "pt") or len(result.text) > 256:
        raise VoiceError("invalid_transcription")
    return result.text


def speak_local(options: dict) -> None:
    import torch
    from kokoro import KModel

    from openjarvis.speech.kokoro_tts import KokoroTTSBackend

    from .voice_audio import play_audio

    directory, voice = options["model_dir"], options["voice"]
    if voice not in PT_VOICES:
        raise VoiceError("invalid_pt_voice")

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

    backend = LocalKokoro(device="cpu", max_cached_pipelines=1)
    try:
        # Pré-carrega o tensor local: KPipeline.load_voice não consulta HF.
        pipeline = backend._ensure_pipeline("p")
        pipeline.voices[voice] = torch.load(
            local_file(directory, f"voices/{voice}.pt"),
            map_location="cpu",
            weights_only=True,
        )
        result = backend.synthesize(
            options["text"][:800],
            voice_id=voice,
            speed=options["speed"],
            output_format="wav",
        )
        if not result.audio:
            raise VoiceError("empty_tts")
        play_audio(
            result.audio,
            device=options["device"],
            volume=options["volume"],
            timeout=options["seconds"],
            cancel=Event(),
        )
    finally:
        backend.close()


def wait_for_wake(options: dict) -> bool:
    import numpy as np
    from openwakeword.model import Model

    from openjarvis.speech.voice_io import _rms

    from .voice_audio import SoundDeviceMicrophone

    directory = options["model_dir"]
    model = Model(
        wakeword_models=[local_file(directory, options["model"])],
        inference_framework="onnx",
        melspec_model_path=local_file(directory, "melspectrogram.onnx"),
        embedding_model_path=local_file(directory, "embedding_model.onnx"),
        device="cpu",
        ncpu=1,
    )
    detector = AcousticGate(options["threshold"])
    mic = SoundDeviceMicrophone(options["device"])
    try:
        with mic.frames(timeout=options["seconds"], cancel=Event()) as frames:
            for frame in frames:
                scores = model.predict(np.frombuffer(frame, dtype="<i2"))
                if detector.accept(
                    max(float(score) for score in scores.values()), _rms(frame)
                ):
                    return True
        return False
    finally:
        mic.close()
        model.reset()


class AcousticGate:
    """Dois frames consecutivos acima do limiar e com energia mínima."""

    def __init__(self, threshold: float) -> None:
        self.threshold, self.consecutive = threshold, 0

    def accept(self, score: float, rms: float) -> bool:
        self.consecutive = (
            self.consecutive + 1 if self.threshold <= score <= 1 and rms > 500 else 0
        )
        return self.consecutive >= 2


def execute(operation: str, options: dict):
    if operation == "diagnose":
        from .voice_diagnostics import audio_diagnostics

        return audio_diagnostics()
    if operation == "capture":
        from .voice_audio import SoundDeviceMicrophone

        mic = SoundDeviceMicrophone(
            options["device"],
            threshold=options["threshold"],
            on_ready=notify_audio_ready,
        )
        try:
            return base64.b64encode(
                mic.capture(timeout=options["seconds"], cancel=Event())
            ).decode()
        finally:
            mic.close()
    if operation == "stt":
        return transcribe_local(options)
    if operation == "benchmark_stt":
        import resource
        import time

        start = time.monotonic()
        text = transcribe_local(options)
        return {
            "text": text,
            "seconds": time.monotonic() - start,
            "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        }
    if operation == "speak":
        return speak_local(options)
    if operation == "wake":
        return wait_for_wake(options)
    if operation == "chat":
        from .provider_chat_adapter import RegistryChatAdapter

        return RegistryChatAdapter()(options["prompt"])
    raise VoiceError("invalid_operation")


def main() -> None:
    try:
        request = json.loads(sys.stdin.buffer.read(2 * 1024 * 1024))
        # Bibliotecas que imprimem mensagens não corrompem o protocolo JSON.
        with contextlib.redirect_stdout(sys.stderr):
            result = execute(request["operation"], request["options"])
        print(json.dumps({"ok": True, "result": result}))
    except Exception:
        print(json.dumps({"ok": False}))


if __name__ == "__main__":
    main()
