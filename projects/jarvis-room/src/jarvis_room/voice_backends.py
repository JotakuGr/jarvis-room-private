"""Adaptadores locais isolados, canceláveis e sem download implícito."""

from __future__ import annotations

import base64
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from threading import Event
from typing import Any, Callable

from .voice_contract import VoiceError, check_cancel

MAX_RESULT = 12 * 1024 * 1024
PT_VOICES = ("pm_santa", "pm_alex", "pf_dora")
VOICE_OLLAMA_CONFIG = """[engine.ollama]
host = "http://127.0.0.1:11434"
[telemetry]
enabled = false
gpu_metrics = false
[analytics]
enabled = false
[traces]
enabled = false
[mcp]
enabled = false
[tools]
enabled = ""
"""


def local_file(directory: str, name: str) -> str:
    path = Path(directory).expanduser().resolve() / name
    if not path.is_file():
        raise VoiceError("local_model_missing")
    return str(path)


class WorkerRunner:
    """Processos descartáveis limitam memória retida e permitem matar libs nativas."""

    def run(
        self,
        operation: str,
        options: dict[str, Any],
        *,
        timeout: float,
        cancel: Event,
        on_ready: Callable[[], None] | None = None,
    ) -> Any:
        check_cancel(cancel)
        env = os.environ.copy()
        env.update(
            HF_HUB_OFFLINE="1",
            TRANSFORMERS_OFFLINE="1",
            HF_HUB_DISABLE_TELEMETRY="1",
            DO_NOT_TRACK="1",
            CUDA_VISIBLE_DEVICES="",
            OMP_NUM_THREADS="2",
        )
        # Origem local explícita também permite iniciar sem instalar o SDK.
        source = Path(__file__).resolve().parents[4] / "src"
        env["PYTHONPATH"] = os.pathsep.join(
            filter(
                None,
                (
                    str(Path(__file__).resolve().parents[1]),
                    str(source),
                    env.get("PYTHONPATH"),
                ),
            )
        )
        with (
            tempfile.TemporaryDirectory(prefix="jarvis-voice-") as runtime,
            tempfile.TemporaryFile() as request,
            tempfile.TemporaryFile() as result,
        ):
            # Não herdar configuração, memória, MCP ou destinos de rede de uma
            # sessão de terminal. Logs privados do SDK morrem com este diretório.
            config = Path(runtime) / "config.toml"
            config.write_text(VOICE_OLLAMA_CONFIG, encoding="utf-8")
            env.update(
                OPENJARVIS_HOME=runtime,
                OPENJARVIS_CONFIG=str(config),
                OLLAMA_HOST="http://127.0.0.1:11434",
                NO_PROXY="127.0.0.1,localhost",
                no_proxy="127.0.0.1,localhost",
            )
            ready = Path(runtime) / "audio.ready"
            env["JARVIS_VOICE_READY_FILE"] = str(ready)
            for key in (
                "HTTP_PROXY",
                "HTTPS_PROXY",
                "ALL_PROXY",
                "http_proxy",
                "https_proxy",
                "all_proxy",
            ):
                env.pop(key, None)
            request.write(
                json.dumps({"operation": operation, "options": options}).encode()
            )
            request.seek(0)
            process = subprocess.Popen(
                [sys.executable, "-m", "jarvis_room.voice_worker"],
                stdin=request,
                stdout=result,
                stderr=subprocess.DEVNULL,
                env=env,
                start_new_session=True,
            )
            try:
                deadline = time.monotonic() + timeout
                while process.poll() is None:
                    check_cancel(cancel)
                    if on_ready is not None and ready.exists():
                        on_ready()
                        on_ready = None
                    if time.monotonic() >= deadline:
                        raise VoiceError("operation_timeout")
                    if os.fstat(result.fileno()).st_size > MAX_RESULT:
                        raise VoiceError("worker_result_limit")
                    cancel.wait(0.05)
                check_cancel(cancel)
                if process.returncode or os.fstat(result.fileno()).st_size > MAX_RESULT:
                    raise VoiceError("local_backend_unavailable")
                result.seek(0)
                try:
                    payload = json.load(result)
                except (ValueError, UnicodeError) as exc:
                    raise VoiceError("invalid_worker_result") from exc
                if not payload.get("ok"):
                    raise VoiceError("local_backend_unavailable")
                return payload["result"]
            finally:
                # Inclui Ctrl+C; nenhum resultado atrasado é reaproveitado.
                if process.poll() is None:
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                process.wait()


class ProcessMicrophone:
    def __init__(
        self,
        runner: WorkerRunner,
        *,
        device: int | None = None,
        threshold: int = 500,
        on_ready: Callable[[], None] | None = None,
    ) -> None:
        self.runner, self.device, self.threshold = runner, device, threshold
        self.on_ready = on_ready

    def capture(self, *, timeout: float, cancel: Event) -> bytes:
        result = self.runner.run(
            "capture",
            {
                "device": self.device,
                "threshold": self.threshold,
                "seconds": timeout,
            },
            timeout=timeout + 5,
            cancel=cancel,
            on_ready=self.on_ready,
        )
        return base64.b64decode(result, validate=True)

    def close(self) -> None:
        pass  # cada processo/stream é fechado ao terminar a operação


class LocalTranscriber:
    def __init__(self, runner: WorkerRunner, model_dir: str) -> None:
        for name in ("model.bin", "config.json", "tokenizer.json"):
            local_file(model_dir, name)
        self.runner, self.model_dir = (
            runner,
            str(Path(model_dir).expanduser().resolve()),
        )

    def transcribe(self, audio: bytes, *, timeout: float, cancel: Event) -> str:
        from .voice_audio import wav_pcm

        wav_pcm(audio)
        result = self.runner.run(
            "stt",
            {
                "model_dir": self.model_dir,
                "audio": base64.b64encode(audio).decode(),
            },
            timeout=timeout,
            cancel=cancel,
        )
        if not isinstance(result, str) or len(result) > 256:
            raise VoiceError("transcription_limit")
        return result.strip()

    def close(self) -> None:
        pass


class LocalSpeaker:
    def __init__(
        self,
        runner: WorkerRunner,
        model_dir: str,
        *,
        voice: str = "pm_santa",
        speed: float = 1,
        volume: float = 0.7,
        device: int | None = None,
    ) -> None:
        if voice not in PT_VOICES or not 0.5 <= speed <= 2 or not 0 <= volume <= 1:
            raise ValueError("invalid_voice_output")
        for name in ("config.json", "kokoro-v1_0.pth", f"voices/{voice}.pt"):
            local_file(model_dir, name)
        self.runner = runner
        self.options = {
            "model_dir": str(Path(model_dir).expanduser().resolve()),
            "voice": voice,
            "speed": speed,
            "volume": volume,
            "device": device,
        }

    def speak(self, text: str, *, timeout: float, cancel: Event) -> None:
        self.runner.run(
            "speak",
            {**self.options, "text": text[:800], "seconds": timeout},
            timeout=timeout,
            cancel=cancel,
        )

    def close(self) -> None:
        pass


class OpenWakeWord:
    """ONNX CPU: modelo acústico explícito, nunca busca texto em transcrições."""

    def __init__(
        self,
        runner: WorkerRunner,
        model_dir: str,
        *,
        model: str = "hey_jarvis_v0.1.onnx",
        threshold: float = 0.6,
        device: int | None = None,
    ) -> None:
        if (
            Path(model).name != model
            or not model.endswith(".onnx")
            or not 0.1 <= threshold <= 1
        ):
            raise ValueError("invalid_wake_config")
        for name in (model, "melspectrogram.onnx", "embedding_model.onnx"):
            local_file(model_dir, name)
        self.runner = runner
        self.options = {
            "model_dir": str(Path(model_dir).expanduser().resolve()),
            "model": model,
            "threshold": threshold,
            "device": device,
        }

    def wait(self, *, timeout: float, cancel: Event) -> bool:
        result = self.runner.run(
            "wake",
            {**self.options, "seconds": timeout},
            timeout=timeout + 5,
            cancel=cancel,
        )
        if type(result) is not bool:
            raise VoiceError("invalid_wake_result")
        return result

    def close(self) -> None:
        pass


class LocalChat:
    def __init__(self, runner: WorkerRunner) -> None:
        self.runner = runner

    def answer(self, prompt: str, *, timeout: float, cancel: Event) -> str:
        return self.runner.run(
            "chat", {"prompt": prompt}, timeout=timeout, cancel=cancel
        )
