"""Processo residente com pipes privados e mensagens JSON enquadradas/limitadas.

Não usa sockets, portas, pickle ou arquivos de áudio. Uma solicitação por vez.
"""

from __future__ import annotations

import base64
import json
import os
import select
import signal
import struct
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any

from .voice_audio import wav_pcm
from .voice_backends import worker_environment
from .voice_contract import VoiceError, check_cancel, public_error
from .voice_stt import STTSettings, validate_timeout

MAX_FRAME = 2 * 1024 * 1024


def encode_frame(payload: dict) -> bytes:
    data = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode()
    if len(data) > MAX_FRAME:
        raise VoiceError("ipc_frame_limit")
    return struct.pack("!I", len(data)) + data


def decode_payload(data: bytes) -> dict:
    try:

        def invalid_constant(_value):
            raise ValueError("non_finite_json")

        result = json.loads(data, parse_constant=invalid_constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise VoiceError("ipc_invalid_json") from exc
    if not isinstance(result, dict):
        raise VoiceError("ipc_invalid_message")
    return result


class FramedPipe:
    def __init__(self, reader: int, writer: int) -> None:
        self.reader, self.writer = reader, writer
        os.set_blocking(reader, False)
        os.set_blocking(writer, False)

    def _ready(
        self, fd: int, *, writing: bool, deadline: float, cancel: threading.Event
    ) -> None:
        while True:
            check_cancel(cancel)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise VoiceError("ipc_timeout")
            readers, writers, _ = select.select(
                [] if writing else [fd],
                [fd] if writing else [],
                [],
                min(0.05, remaining),
            )
            if readers or writers:
                return

    def send(self, payload: dict, *, deadline: float, cancel: threading.Event) -> None:
        data = memoryview(encode_frame(payload))
        while data:
            self._ready(self.writer, writing=True, deadline=deadline, cancel=cancel)
            try:
                written = os.write(self.writer, data[:65536])
            except BlockingIOError:
                continue
            if written <= 0:
                raise VoiceError("ipc_closed")
            data = data[written:]

    def _read(self, count: int, *, deadline: float, cancel: threading.Event) -> bytes:
        data = bytearray()
        while len(data) < count:
            self._ready(self.reader, writing=False, deadline=deadline, cancel=cancel)
            try:
                part = os.read(self.reader, min(65536, count - len(data)))
            except BlockingIOError:
                continue
            if not part:
                raise VoiceError("ipc_closed")
            data.extend(part)
        return bytes(data)

    def receive(self, *, deadline: float, cancel: threading.Event) -> dict:
        size = struct.unpack("!I", self._read(4, deadline=deadline, cancel=cancel))[0]
        if not 0 < size <= MAX_FRAME:
            raise VoiceError("ipc_frame_limit")
        return decode_payload(self._read(size, deadline=deadline, cancel=cancel))


class ResidentWorker:
    def __init__(self, kind: str, options: dict[str, Any]) -> None:
        if kind not in {"stt", "tts", "playback"}:
            raise ValueError("invalid_resident_kind")
        self.kind, self.options = kind, options.copy()
        self.process = self.pipe = self._runtime = None
        self.health: dict[str, Any] = {}
        self._sequence = 0
        self._lock = threading.Lock()
        self.closed = False

    def _exchange(
        self,
        operation: str,
        data: dict,
        *,
        timeout: float,
        cancel: threading.Event,
        on_event=None,
    ) -> Any:
        validate_timeout(timeout)
        check_cancel(cancel)
        self._sequence += 1
        deadline = time.monotonic() + timeout
        self.pipe.send(
            {**data, "id": self._sequence, "op": operation},
            deadline=deadline,
            cancel=cancel,
        )
        while True:
            reply = self.pipe.receive(deadline=deadline, cancel=cancel)
            if type(reply.get("id")) is not int or reply["id"] != self._sequence:
                raise VoiceError("ipc_response_mismatch")
            if "event" not in reply:
                break
            if self.kind != "playback" or set(reply) != {"id", "event"}:
                raise VoiceError("ipc_invalid_message")
            event = reply["event"]
            from .presentation_contract import validate_payload

            if (
                type(event) is not dict
                or set(event) != {"type", "payload"}
                or event["type"] not in ("voice_amplitude", "playback_status")
            ):
                raise VoiceError("ipc_invalid_message")
            validate_payload(event["type"], event["payload"])
            if on_event is not None:
                on_event(event)
        check_cancel(cancel)
        if type(reply.get("id")) is not int or reply["id"] != self._sequence:
            raise VoiceError("ipc_response_mismatch")
        if reply.get("ok") is not True:
            raise VoiceError(
                public_error(
                    VoiceError(reply.get("error", "")),
                    f"{self.kind}_backend_unavailable",
                )
            )
        return reply.get("result")

    def start(self, *, timeout: float, cancel: threading.Event) -> dict:
        if not self._lock.acquire(blocking=False):
            raise VoiceError(f"{self.kind}_busy")
        try:
            return self._start(timeout=timeout, cancel=cancel)
        finally:
            self._lock.release()

    def _start(self, *, timeout: float, cancel: threading.Event) -> dict:
        validate_timeout(timeout)
        check_cancel(cancel)
        if self.closed:
            raise VoiceError(f"{self.kind}_closed")
        if self.process is not None and self.process.poll() is None:
            return self.health.copy()
        self._stop()
        started = time.monotonic()
        try:
            self._runtime = tempfile.TemporaryDirectory(prefix=f"jarvis-{self.kind}-")
            env = worker_environment(
                f"resident_{self.kind}", self.options, self._runtime.name
            )
            self.process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "jarvis_room.voice_worker",
                    f"--resident-{self.kind}",
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                env=env,
                start_new_session=True,
                bufsize=0,
            )
            self.pipe = FramedPipe(
                self.process.stdout.fileno(), self.process.stdin.fileno()
            )
            self.health = self._exchange(
                "initialize", {"options": self.options}, timeout=timeout, cancel=cancel
            )
            self.health["worker_initialization_seconds"] = time.monotonic() - started
            return self.health.copy()
        except BaseException:
            self._stop()
            raise

    def request(
        self,
        operation: str,
        data: dict,
        *,
        timeout: float,
        cancel: threading.Event,
        on_event=None,
    ) -> Any:
        if not self._lock.acquire(blocking=False):
            raise VoiceError(f"{self.kind}_busy")
        try:
            if self.closed or self.process is None or self.process.poll() is not None:
                raise VoiceError(f"{self.kind}_not_ready")
            return self._exchange(
                operation, data, timeout=timeout, cancel=cancel, on_event=on_event
            )
        except BaseException:
            # Falha/timeout nunca reaproveita resultado atrasado nem reenvia áudio.
            self._stop()
            raise
        finally:
            self._lock.release()

    def _stop(self) -> None:
        process, self.process = self.process, None
        self.pipe = None
        try:
            if process is not None:
                try:
                    if process.poll() is None:
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                finally:
                    try:
                        process.wait(timeout=5)
                    finally:
                        for stream in (process.stdin, process.stdout):
                            if stream is not None:
                                stream.close()
        finally:
            if self._runtime is not None:
                self._runtime.cleanup()
                self._runtime = None

    def close(self) -> None:
        self.closed = True
        self._stop()


class ResidentTranscriber:
    def __init__(
        self,
        settings: STTSettings,
        *,
        worker: ResidentWorker | None = None,
        startup_seconds: float = 120,
    ) -> None:
        settings.validate_assets()
        validate_timeout(startup_seconds)
        self.settings, self.startup_seconds = settings, startup_seconds
        self.worker = (
            worker if worker is not None else ResidentWorker("stt", settings.options())
        )
        self.last_metrics: dict[str, Any] = {}

    def prepare(self, *, cancel: threading.Event) -> dict:
        self.last_metrics = self.worker.start(
            timeout=self.startup_seconds, cancel=cancel
        )
        return self.last_metrics.copy()

    def transcribe(
        self, audio: bytes, *, timeout: float, cancel: threading.Event
    ) -> str:
        wav_pcm(audio)
        reply = self.worker.request(
            "transcribe",
            {"audio": base64.b64encode(audio).decode()},
            timeout=timeout,
            cancel=cancel,
        )
        if (
            not isinstance(reply, dict)
            or not isinstance(reply.get("text"), str)
            or len(reply["text"]) > 256
        ):
            self.worker.close()
            raise VoiceError("stt_invalid_transcription")
        self.last_metrics = reply.get("metrics", {})
        return reply["text"].strip()

    def close(self) -> None:
        self.worker.close()
