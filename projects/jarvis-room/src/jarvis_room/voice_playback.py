"""PCM de TTS → PortAudio; eventos temporizados pelo relógio DAC do stream."""

from __future__ import annotations

import base64
import io
import math
import queue
import sys
import time
import wave
from array import array
from threading import Event

from .voice_contract import VoiceError, check_cancel


def pcm_volume(pcm: bytes, volume: float) -> bytes:
    if (
        type(volume) not in (int, float)
        or not math.isfinite(volume)
        or not 0 <= volume <= 1
    ):
        raise VoiceError("invalid_playback_volume")
    samples = array("h")
    samples.frombytes(pcm)
    if sys.byteorder != "little":
        samples.byteswap()
    samples = array("h", (int(value * volume) for value in samples))
    if sys.byteorder != "little":
        samples.byteswap()
    return samples.tobytes()


class AmplitudeEnvelope:
    def __init__(self):
        self.value = 0.0

    def sample(self, pcm: bytes) -> float:
        samples = array("h")
        samples.frombytes(pcm)
        if sys.byteorder != "little":
            samples.byteswap()
        raw = (
            math.sqrt(sum(value * value for value in samples) / max(1, len(samples)))
            / 32768
        )
        alpha = 0.65 if raw > self.value else 0.25
        self.value += alpha * (raw - self.value)
        return min(1.0, max(0.0, self.value))


def play_pcm(
    audio, *, device, volume, timeout, cancel, emit, clock=time.monotonic, wait=None
):
    import sounddevice as sd

    from .voice_tts import validate_tts_wav

    validate_tts_wav(audio)
    if not math.isfinite(timeout) or not 0 < timeout <= 300:
        raise VoiceError("invalid_playback_timeout")
    with wave.open(io.BytesIO(audio), "rb") as source:
        pcm = pcm_volume(source.readframes(source.getnframes()), volume)
    pending = queue.Queue(maxsize=64)
    finished, failed = Event(), Event()
    envelope, offset, playing = AmplitudeEnvelope(), 0, False
    wait = wait or cancel.wait

    def callback(output, frames, timing, status):
        nonlocal offset
        if status:
            failed.set()
            output[:] = bytes(len(output))
            raise sd.CallbackAbort
        frame = pcm[offset : offset + frames * 2]
        output[:] = frame + bytes(len(output) - len(frame))
        if frame:
            # Callback nunca escreve em pipe/rede. DAC inclui latência da saída.
            delay = timing.outputBufferDacTime - timing.currentTime
            if not math.isfinite(delay) or not -0.1 <= delay <= 5:
                failed.set()
                raise sd.CallbackAbort
            try:
                pending.put_nowait((clock() + max(0, delay), envelope.sample(frame)))
            except queue.Full:
                failed.set()
                raise sd.CallbackAbort
            offset += len(frame)
        if offset >= len(pcm):
            raise sd.CallbackStop

    def status(state):
        emit({"type": "playback_status", "payload": {"state": state}})

    deadline = clock() + timeout
    scheduled = None
    try:
        check_cancel(cancel)
        with sd.RawOutputStream(
            samplerate=24000,
            blocksize=960,
            channels=1,
            dtype="int16",
            device=device,
            callback=callback,
            finished_callback=finished.set,
        ):
            while True:
                check_cancel(cancel)
                if failed.is_set():
                    raise VoiceError("playback_failed")
                if clock() >= deadline:
                    raise VoiceError("playback_timeout")
                if scheduled is None:
                    try:
                        scheduled = pending.get_nowait()
                    except queue.Empty:
                        if finished.is_set():
                            break
                if scheduled is not None and clock() >= scheduled[0]:
                    if not playing:
                        status("playing")
                        playing = True
                    emit(
                        {
                            "type": "voice_amplitude",
                            "payload": {"amplitude": scheduled[1]},
                        }
                    )
                    scheduled = None
                    continue
                wait(0.01)
        status("idle" if playing else "unavailable")
    except BaseException:
        status("error")
        raise
    finally:
        emit({"type": "voice_amplitude", "payload": {"amplitude": 0}})


class PlaybackEngine:
    def __init__(self, options):
        if options:
            raise ValueError("invalid_playback_options")

    def health(self):
        return {"device": "cpu", "backend": "portaudio"}

    def play(self, options, emit):
        if set(options) != {"audio", "device", "volume", "seconds"}:
            raise ValueError("invalid_playback_options")
        play_pcm(
            base64.b64decode(options["audio"], validate=True),
            device=options["device"],
            volume=options["volume"],
            timeout=options["seconds"],
            cancel=Event(),
            emit=emit,
        )

    def close(self):
        pass
