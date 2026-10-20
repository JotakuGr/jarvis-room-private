"""Worker privado. Não oferece controlador, transporte HA ou ferramentas ao LLM."""

from __future__ import annotations

import base64
import contextlib
import json
import os
import signal
import struct
import sys
from pathlib import Path
from threading import Event

from .voice_backends import PT_VOICES, local_file
from .voice_contract import VoiceError, public_error


def notify_audio_ready() -> None:
    path = os.environ.get("JARVIS_VOICE_READY_FILE")
    if path:
        Path(path).touch()


def arm_parent_death() -> None:
    """Linux/WSL2: nem SIGKILL no supervisor deixa inferência órfã."""
    expected = os.environ.get("JARVIS_VOICE_PARENT_PID")
    if expected is None:
        return
    import ctypes

    try:
        parent = int(expected)
        if os.getppid() != parent:
            raise VoiceError("worker_parent_missing")
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0:
            raise VoiceError("worker_parent_guard_unavailable")
        if os.getppid() != parent:
            raise VoiceError("worker_parent_missing")
    except (ValueError, AttributeError, OSError) as exc:
        raise VoiceError("worker_parent_guard_unavailable") from exc


def transcribe_local(options: dict) -> str:
    if "device" in options:
        from .voice_stt import SpeechEngine, STTSettings

        settings = STTSettings(
            **{
                key: value
                for key, value in options.items()
                if key in STTSettings.__dataclass_fields__
            }
        )
        engine = SpeechEngine(settings)
        try:
            return engine.transcribe(base64.b64decode(options["audio"], validate=True))[
                "text"
            ]
        finally:
            engine.close()
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

    from openjarvis._audio_pcm import _rms

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
    if operation == "ollama_diagnose":
        from .voice_llm import OLLAMA_ENDPOINT, local_models, ollama_get

        models = local_models()
        return {
            "endpoint": OLLAMA_ENDPOINT,
            "models": models,
            "running": ollama_get("/api/ps").get("models", []),
            "version": ollama_get("/api/version").get("version"),
            "inference_performed": False,
        }
    if operation == "gpu_diagnose":
        from .voice_diagnostics import gpu_snapshot

        return gpu_snapshot()
    if operation == "stt_capabilities":
        import ctranslate2

        from .voice_stt import STTSettings, verify_compute

        settings = STTSettings(**options)
        settings.validate_assets()
        verify_compute(settings, ctranslate2)
        return {
            "device": settings.device,
            "compute_type": settings.compute_type,
            "supported": sorted(
                ctranslate2.get_supported_compute_types(settings.device)
            ),
            "cuda_devices_visible": ctranslate2.get_cuda_device_count(),
            "model_loaded": False,
            "inference_performed": False,
        }
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
    if operation == "play":
        from .voice_audio import play_audio

        return play_audio(
            base64.b64decode(options["audio"], validate=True),
            device=options["device"],
            volume=options["volume"],
            timeout=options["seconds"],
            cancel=Event(),
        )
    if operation == "wake":
        return wait_for_wake(options)
    if operation == "chat":
        from .provider_chat_adapter import RegistryChatAdapter

        if "model" not in options:
            return RegistryChatAdapter()(options["prompt"])
        from .voice_llm import LLMSettings, require_model

        settings = LLMSettings(
            options["model"],
            max_tokens=options.get("max_tokens", 192),
            context_tokens=options.get("context_tokens", 4096),
        )
        require_model(settings)
        os.environ["JARVIS_NUM_CTX"] = str(settings.context_tokens)
        return RegistryChatAdapter(
            model=settings.model, max_tokens=settings.max_tokens
        )(options["prompt"])
    raise VoiceError("invalid_operation")


def read_frame(stream):
    from .voice_resident import MAX_FRAME, decode_payload

    def read_exact(size):
        data = bytearray()
        while len(data) < size:
            chunk = stream.read(size - len(data))
            if not chunk:
                if not data and size == 4:
                    return None
                raise VoiceError("ipc_truncated_frame")
            data.extend(chunk)
        return bytes(data)

    header = read_exact(4)
    if header is None:
        return None
    size = struct.unpack("!I", header)[0]
    if not 0 < size <= MAX_FRAME:
        raise VoiceError("ipc_frame_limit")
    data = read_exact(size)
    if data is None:
        raise VoiceError("ipc_truncated_frame")
    return decode_payload(data)


def resident_main(kind: str, reader=None, writer=None) -> None:
    from .voice_resident import encode_frame

    reader = reader if reader is not None else sys.stdin.buffer
    writer = writer if writer is not None else sys.stdout.buffer
    engine, sequence = None, 0
    try:
        while True:
            request = read_frame(reader)
            if request is None:
                break
            identifier = request.get("id")
            if type(identifier) is not int or identifier != sequence + 1:
                raise VoiceError("ipc_request_mismatch")
            sequence = identifier
            try:
                with contextlib.redirect_stdout(sys.stderr):
                    if engine is None and request.get("op") == "initialize":
                        if set(request) != {"id", "op", "options"}:
                            raise VoiceError("ipc_invalid_message")
                        if kind == "stt":
                            from .voice_stt import SpeechEngine, STTSettings

                            engine = SpeechEngine(STTSettings(**request["options"]))
                        else:
                            from .voice_tts import KokoroEngine

                            engine = KokoroEngine(request["options"])
                        result = engine.health()
                    elif (
                        kind == "stt"
                        and engine is not None
                        and request.get("op") == "transcribe"
                    ):
                        if set(request) != {"id", "op", "audio"}:
                            raise VoiceError("ipc_invalid_message")
                        result = engine.transcribe(
                            base64.b64decode(request["audio"], validate=True)
                        )
                    elif (
                        kind == "tts"
                        and engine is not None
                        and request.get("op") == "synthesize"
                    ):
                        if set(request) != {"id", "op", "text"}:
                            raise VoiceError("ipc_invalid_message")
                        result = engine.synthesize(request["text"])
                    else:
                        raise VoiceError("ipc_operation_forbidden")
                reply = {"id": identifier, "ok": True, "result": result}
            except Exception as exc:
                code = public_error(exc, f"{kind}_backend_unavailable")
                reply = {"id": identifier, "ok": False, "error": code}
            writer.write(encode_frame(reply))
            writer.flush()
            if not reply["ok"]:
                break
    finally:
        if engine is not None:
            engine.close()


def main() -> None:
    arm_parent_death()
    if sys.argv[1:] in (["--resident-stt"], ["--resident-tts"]):
        try:
            resident_main("stt" if sys.argv[1] == "--resident-stt" else "tts")
        except Exception:
            pass  # EOF fará o supervisor identificar falha de protocolo.
        return
    try:
        request = json.loads(sys.stdin.buffer.read(2 * 1024 * 1024))
        # Bibliotecas que imprimem mensagens não corrompem o protocolo JSON.
        with contextlib.redirect_stdout(sys.stderr):
            result = execute(request["operation"], request["options"])
        print(json.dumps({"ok": True, "result": result}))
    except Exception as exc:
        code = public_error(exc, "")
        error = {"error": code} if code else {}
        print(json.dumps({"ok": False, **error}))


if __name__ == "__main__":
    main()
