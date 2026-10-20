"""Fakes de voz: WAV sintético, relógio virtual; hardware/rede/processos proibidos."""

import importlib.util
import io
import math
import socket
import struct
import sys
import unittest
import wave
from collections import deque
from pathlib import Path
from unittest.mock import Mock, patch

from jarvis_room.voice_contract import VoiceConfig
from jarvis_room.voice_router import VoiceRouter
from jarvis_room.voice_session import VoiceSession


def wav(*, seconds=0.4, amplitude=2000, rate=16000, channels=1, width=2):
    samples = [
        int(amplitude * math.sin(2 * math.pi * 440 * i / rate))
        for i in range(int(seconds * rate))
    ]
    data = struct.pack(f"<{len(samples)}h", *samples)
    out = io.BytesIO()
    with wave.open(out, "wb") as stream:
        stream.setnchannels(channels)
        stream.setsampwidth(width)
        stream.setframerate(rate)
        stream.writeframes(data)
    return out.getvalue()


class Clock:
    def __init__(self):
        self.now = 0.0
        self.waits = []

    def __call__(self):
        return self.now

    def wait(self, seconds):
        self.waits.append(seconds)
        self.now += seconds
        return False


class Microphone:
    def __init__(self, captures=None):
        self.captures = deque([wav(), b""] if captures is None else captures)
        self.closed = False
        self.active = False
        self.timeouts = []
        self.hook = lambda: None

    def capture(self, *, timeout, cancel):
        self.timeouts.append(timeout)
        self.active = True
        try:
            self.hook()
            result = self.captures.popleft() if self.captures else b""
            if isinstance(result, BaseException):
                raise result
            return result
        finally:
            self.active = False

    def close(self):
        self.closed = True
        self.active = False


class Transcriber:
    def __init__(self, texts=None):
        self.texts = deque(["Jarvis, ligue os monitores."] if texts is None else texts)
        self.closed = False
        self.calls = []
        self.hook = lambda: None

    def transcribe(self, audio, *, timeout, cancel):
        self.calls.append((audio, timeout))
        self.hook()
        result = self.texts.popleft()
        if isinstance(result, BaseException):
            raise result
        return result

    def close(self):
        self.closed = True


class Speaker:
    def __init__(self, mic):
        self.mic, self.closed = mic, False
        self.texts = []
        self.hook = lambda: None

    def speak(self, text, *, timeout, cancel):
        if self.mic.active:
            raise AssertionError("Microfone ativo durante TTS")
        self.texts.append(text)
        self.hook()

    def close(self):
        self.closed = True


class OfflineVoiceTest(unittest.TestCase):
    def setUp(self):
        self.enterContext(
            patch.object(socket, "socket", side_effect=AssertionError("Rede proibida"))
        )
        self.enterContext(
            patch(
                "subprocess.Popen", side_effect=AssertionError("Processo real proibido")
            )
        )
        # Carrega apenas os helpers stdlib reais, sem inicializar backends opcionais.
        path = Path(__file__).resolve().parents[3] / "src/openjarvis/speech/voice_io.py"
        spec = importlib.util.spec_from_file_location("voice_io_offline", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.enterContext(
            patch.dict(sys.modules, {"openjarvis.speech.voice_io": module})
        )

    def session(
        self,
        *,
        captures=None,
        texts=None,
        chat=None,
        config=None,
        speaker=True,
        wake=None,
    ):
        self.clock = Clock()
        self.mic = Microphone(captures)
        self.stt = Transcriber(texts)
        self.speaker = Speaker(self.mic)
        self.output, self.states = [], []
        return VoiceSession(
            self.mic,
            self.stt,
            VoiceRouter(chat),
            speaker=self.speaker if speaker else None,
            wake=wake,
            clock=self.clock,
            wait=self.clock.wait,
            output=self.output.append,
            on_state=self.states.append,
            config=config or VoiceConfig(),
        )

    def runner(self, result):
        return Mock(run=Mock(return_value=result))
