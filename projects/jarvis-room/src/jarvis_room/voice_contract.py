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


PUBLIC_ERRORS = frozenset(
    {
        "worker_parent_missing",
        "worker_parent_guard_unavailable",
        "stt_cuda_unavailable",
        "stt_device_unavailable",
        "stt_compute_type_unsupported",
        "stt_model_load_failed",
        "stt_transcription_failed",
        "stt_invalid_transcription",
        "stt_local_model_missing",
        "stt_closed",
        "stt_busy",
        "stt_not_ready",
        "stt_backend_unavailable",
        "tts_backend_unavailable",
        "tts_closed",
        "tts_busy",
        "tts_not_ready",
        "tts_audio_limit",
        "tts_invalid_wav",
        "tts_text_limit",
        "tts_timeout",
        "llm_endpoint_forbidden",
        "llm_server_unavailable",
        "llm_inventory_limit",
        "llm_invalid_inventory",
        "llm_model_resource_limit",
        "llm_model_not_installed",
        "llm_busy",
        "llm_recovery_required",
        "ipc_timeout",
        "ipc_closed",
        "ipc_frame_limit",
        "ipc_invalid_json",
        "ipc_invalid_message",
        "ipc_response_mismatch",
        "ipc_request_mismatch",
        "ipc_operation_forbidden",
        "ipc_truncated_frame",
        "wake_activation_rate_limit",
        "wake_license_unavailable",
        "audio_overflow",
        "capture_limit",
        "operation_timeout",
        "local_backend_unavailable",
        "playback_timeout",
        "playback_failed",
        "playback_backend_unavailable",
        "playback_not_ready",
        "playback_busy",
        "playback_closed",
    }
)


def public_error(exc: BaseException, fallback: str) -> str:
    code = str(exc)
    return code if isinstance(exc, VoiceError) and code in PUBLIC_ERRORS else fallback


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
    inactivity_seconds: float | None = None
    retain_context: bool = False
    passive_pause_seconds: float = 0.25

    def __post_init__(self) -> None:
        for value, low, high in (
            (self.active_seconds, 1, 300),
            (self.capture_seconds, 1, 30),
            (self.operation_seconds, 1, 120),
            (self.wake_seconds, 1, 60),
            (self.cooldown_seconds, 0.3, 5),
            (self.passive_pause_seconds, 0.2, 5),
        ):
            if (
                isinstance(value, bool)
                or not math.isfinite(value)
                or not low <= value <= high
            ):
                raise ValueError("invalid_voice_limits")
        if type(self.max_turns) is not int or not 1 <= self.max_turns <= 20:
            raise ValueError("invalid_voice_turn_limit")
        if self.inactivity_seconds is not None and (
            isinstance(self.inactivity_seconds, bool)
            or not math.isfinite(self.inactivity_seconds)
            or not 1 <= self.inactivity_seconds <= 120
        ):
            raise ValueError("invalid_inactivity_limit")
        if type(self.retain_context) is not bool:
            raise ValueError("invalid_context_policy")


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
