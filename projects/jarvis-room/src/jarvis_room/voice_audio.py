"""Captura limitada e half-duplex. Cada operação fecha o stream e sua fila."""

from __future__ import annotations

import io
import math
import queue
import time
import wave
from contextlib import contextmanager
from threading import Event
from typing import Callable, Iterator

from .voice_contract import VoiceError, check_cancel

RATE = 16000
CHUNK = 1280  # 80 ms: também é a unidade do openWakeWord


def wav_pcm(audio: bytes, *, max_seconds: float = 30) -> bytes:
    """Aceita apenas WAV mono PCM16/16 kHz limitado, sem decodificador externo."""
    if not isinstance(audio, bytes) or len(audio) > RATE * 2 * max_seconds + 4096:
        raise VoiceError("invalid_audio")
    try:
        with wave.open(io.BytesIO(audio), "rb") as source:
            if (
                source.getnchannels(),
                source.getsampwidth(),
                source.getframerate(),
                source.getcomptype(),
            ) != (1, 2, RATE, "NONE"):
                raise VoiceError("invalid_audio_format")
            frames = source.getnframes()
            if not 0 < frames <= RATE * max_seconds:
                raise VoiceError("invalid_audio_duration")
            pcm = source.readframes(frames)
            if len(pcm) != frames * 2:
                raise VoiceError("truncated_audio")
            return pcm
    except (wave.Error, EOFError) as exc:
        raise VoiceError("invalid_wav") from exc


class SoundDeviceMicrophone:
    """Callback com fila limitada: não bloqueia indefinidamente em stream.read()."""

    def __init__(
        self,
        device: int | None = None,
        *,
        threshold: int = 500,
        startup_seconds: float = 4,
        silence_seconds: float = 1.2,
        clock: Callable[[], float] = time.monotonic,
        on_ready: Callable[[], None] | None = None,
    ) -> None:
        if (
            type(threshold) is not int
            or not 1 <= threshold <= 32767
            or not math.isfinite(startup_seconds)
            or not 0.2 <= startup_seconds <= 10
            or not math.isfinite(silence_seconds)
            or not 0.2 <= silence_seconds <= 5
        ):
            raise ValueError("invalid_capture_config")
        self.device = device
        self.threshold = threshold
        self.startup_seconds = startup_seconds
        self.silence_seconds = silence_seconds
        self.clock = clock
        self.on_ready = on_ready
        self._stream = None

    @contextmanager
    def frames(self, *, timeout: float, cancel: Event) -> Iterator[Iterator[bytes]]:
        import sounddevice as sd

        pending: queue.Queue[bytes] = queue.Queue(maxsize=8)
        failed = Event()

        def callback(data, _frames, _timing, status):
            if status:
                failed.set()
                return
            try:
                pending.put_nowait(bytes(data))
            except queue.Full:
                failed.set()  # rejeita captura atrasada em vez de usar áudio antigo

        deadline = self.clock() + timeout

        def read_frames():
            while self.clock() < deadline:
                check_cancel(cancel)
                if failed.is_set():
                    raise VoiceError("audio_overflow")
                try:
                    data = pending.get(
                        timeout=min(0.05, max(0.001, deadline - self.clock()))
                    )
                except queue.Empty:
                    continue
                if len(data) != CHUNK * 2:
                    raise VoiceError("invalid_audio_frame")
                yield data
            check_cancel(cancel)

        check_cancel(cancel)
        try:
            with sd.RawInputStream(
                samplerate=RATE,
                channels=1,
                dtype="int16",
                blocksize=CHUNK,
                device=self.device,
                callback=callback,
            ) as stream:
                self._stream = stream
                if self.on_ready is not None:
                    self.on_ready()
                yield read_frames()
        finally:
            self._stream = None
            # A fila é descartada; nenhuma captura permanece viva durante TTS.
            while not pending.empty():
                pending.get_nowait()

    def capture(self, *, timeout: float, cancel: Event) -> bytes:
        # Reutiliza o formato e cálculo RMS do OpenJarvis; o gravador original
        # não oferece dispositivo, cancelamento nem leitura não bloqueante.
        from openjarvis._audio_pcm import _frames_to_wav, _rms

        if not math.isfinite(timeout) or not 0 < timeout <= 30:
            raise ValueError("invalid_capture_timeout")
        frames: list[bytes] = []
        silence = speech = 0
        started = False
        max_frames = max(1, int(timeout * RATE / CHUNK))
        with self.frames(timeout=timeout, cancel=cancel) as source:
            for data in source:
                check_cancel(cancel)
                frames.append(data)
                if _rms(data) > self.threshold:
                    speech += 1
                    started = started or speech >= 3
                    silence = 0
                else:
                    if not started:
                        speech = 0
                    silence += 1
                if not started and len(frames) * CHUNK / RATE >= self.startup_seconds:
                    return b""
                if started and silence * CHUNK / RATE >= self.silence_seconds:
                    return _frames_to_wav(frames, RATE)
                if len(frames) >= max_frames:
                    break
        check_cancel(cancel)
        if not started:
            return b""  # silêncio/impulso curto não é enviado ao Whisper
        raise VoiceError("capture_limit")  # não interpretar frase cortada

    def close(self) -> None:
        if self._stream is not None:
            self._stream.abort()


def play_audio(
    audio: bytes, *, device: int | None, volume: float, timeout: float, cancel: Event
) -> None:
    """Reprodução interrompível; valida WAV em vez do fallback PCM permissivo."""
    import numpy as np
    import sounddevice as sd
    import soundfile as sf

    if len(audio) > 24000 * 4 * 120 + 4096:
        raise VoiceError("tts_audio_limit")
    data, rate = sf.read(io.BytesIO(audio), dtype="float32")
    if (
        rate <= 0
        or data.ndim != 1
        or not np.isfinite(data).all()
        or len(data) / rate > min(timeout, 120)
    ):
        raise VoiceError("invalid_tts_audio")
    check_cancel(cancel)
    try:
        sd.play(np.clip(data * volume, -1, 1), rate, device=device)
        deadline = time.monotonic() + timeout
        while sd.get_stream().active:
            check_cancel(cancel)
            if time.monotonic() >= deadline:
                raise VoiceError("playback_timeout")
            cancel.wait(0.05)
    finally:
        sd.stop()
