"""Contratos de voz sem capacidade de autorização ou execução física."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from threading import Event
from typing import Protocol


class VoiceError(RuntimeError):
    """Falha operacional; mensagens públicas não expõem dados de bibliotecas."""


class VoiceCancelled(VoiceError):
    """Cancelamento cooperativo ou interrupção do operador."""


class VoiceState(str, Enum):
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    TRANSCRIBING = "TRANSCRIBING"
    THINKING = "THINKING"
    RESPONDING = "RESPONDING"
    ERROR = "ERROR"


@dataclass(frozen=True, slots=True)
class VoiceConfig:
    active_seconds: float = 45.0
    capture_seconds: float = 15.0
    operation_seconds: float = 60.0
    wake_seconds: float = 30.0
    cooldown_seconds: float = 0.8
    max_turns: int = 8

    def __post_init__(self) -> None:
        for value, low, high in (
            (self.active_seconds, 1, 300),
            (self.capture_seconds, 1, 30),
            (self.operation_seconds, 1, 120),
            (self.wake_seconds, 1, 60),
            (self.cooldown_seconds, 0.3, 5),
        ):
            if (
                isinstance(value, bool)
                or not math.isfinite(value)
                or not low <= value <= high
            ):
                raise ValueError("invalid_voice_limits")
        if type(self.max_turns) is not int or not 1 <= self.max_turns <= 20:
            raise ValueError("invalid_voice_turn_limit")


class Microphone(Protocol):
    def capture(self, *, timeout: float, cancel: Event) -> bytes: ...
    def close(self) -> None: ...


class Transcriber(Protocol):
    def transcribe(self, audio: bytes, *, timeout: float, cancel: Event) -> str: ...
    def close(self) -> None: ...


class Speaker(Protocol):
    def speak(self, text: str, *, timeout: float, cancel: Event) -> None: ...
    def close(self) -> None: ...


class WakeWord(Protocol):
    """Detecção acústica local; nunca autentica a origem da voz."""

    def wait(self, *, timeout: float, cancel: Event) -> bool: ...
    def close(self) -> None: ...


def check_cancel(cancel: Event) -> None:
    if cancel.is_set():
        raise VoiceCancelled("cancelled")
