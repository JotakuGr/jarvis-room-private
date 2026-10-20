"""Configuração e motor STT residente, independentes de PortAudio."""

from __future__ import annotations

import math
import resource
import time
from dataclasses import asdict, dataclass
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
from typing import Any

from .voice_audio import wav_pcm
from .voice_contract import VoiceError

ROOM_TERMS = (
    "J.A.R.V.I.S., monitores, Samsung, Hikvision, LEDs, "
    "modo apresentação, alto-falantes, Sala Temática."
)
COMPUTE_TYPES = frozenset(
    {"int8", "float16", "float32", "int8_float16", "int8_float32", "bfloat16"}
)


@dataclass(frozen=True, slots=True)
class STTSettings:
    model_dir: str
    device: str = "cpu"
    compute_type: str = "int8"
    gpu_index: int = 0
    beam_size: int = 1
    vad_filter: bool = False
    room_terms: bool = False

    def __post_init__(self) -> None:
        if self.device not in {"cpu", "cuda"} or self.compute_type not in COMPUTE_TYPES:
            raise ValueError("stt_invalid_configuration")
        if type(self.gpu_index) is not int or not 0 <= self.gpu_index <= 31:
            raise ValueError("stt_invalid_gpu_index")
        if type(self.beam_size) is not int or not 1 <= self.beam_size <= 5:
            raise ValueError("stt_invalid_beam_size")
        if type(self.vad_filter) is not bool or type(self.room_terms) is not bool:
            raise ValueError("stt_invalid_options")
        if not isinstance(self.model_dir, str) or not self.model_dir:
            raise ValueError("stt_invalid_model_directory")

    def options(self) -> dict[str, Any]:
        result = asdict(self)
        result["model_dir"] = str(Path(self.model_dir).expanduser().resolve())
        return result

    def validate_assets(self) -> None:
        directory = Path(self.model_dir).expanduser().resolve()
        if not all(
            (directory / name).is_file()
            for name in (
                "model.bin",
                "config.json",
                "tokenizer.json",
            )
        ):
            raise VoiceError("stt_local_model_missing")


def cuda_library_paths() -> list[str]:
    """Inspeciona metadados pip sem importar CUDA, Torch ou criar contexto GPU."""
    directories: set[str] = set()
    for name in ("nvidia-cublas-cu12", "nvidia-cudnn-cu12"):
        try:
            package = distribution(name)
        except PackageNotFoundError:
            continue
        for item in package.files or ():
            if ".so" in str(item):
                path = Path(package.locate_file(item)).resolve()
                if path.is_file():
                    directories.add(str(path.parent))
    return sorted(directories)


def verify_compute(settings: STTSettings, ct2: Any) -> None:
    try:
        if settings.device == "cuda" and ct2.get_cuda_device_count() < 1:
            raise VoiceError("stt_cuda_unavailable")
        supported = ct2.get_supported_compute_types(settings.device)
    except VoiceError:
        raise
    except Exception as exc:
        raise VoiceError("stt_device_unavailable") from exc
    if settings.compute_type not in supported:
        raise VoiceError("stt_compute_type_unsupported")


class SpeechEngine:
    """Uma instância de backend OpenJarvis, carregada uma vez no worker."""

    def __init__(self, settings: STTSettings) -> None:
        import ctranslate2

        from openjarvis.speech.faster_whisper import FasterWhisperBackend

        settings.validate_assets()
        verify_compute(settings, ctranslate2)
        self.settings = settings
        self.turns = 0
        started = time.monotonic()
        self.backend = FasterWhisperBackend(
            model_size=settings.options()["model_dir"],
            device=settings.device,
            compute_type=settings.compute_type,
            local_files_only=True,
            in_memory_audio=True,
        )
        try:
            loaded = self.backend._ensure_model()
        except Exception as exc:
            raise VoiceError("stt_model_load_failed") from exc
        self.initialization_seconds = time.monotonic() - started
        native = getattr(loaded, "model", None)
        self.actual_device = getattr(native, "device", settings.device)
        self.actual_compute_type = getattr(
            native, "compute_type", settings.compute_type
        )

    def health(self) -> dict[str, Any]:
        return {
            "model": Path(self.settings.model_dir).name,
            "device": self.actual_device,
            "compute_type": self.actual_compute_type,
            "gpu_index": self.settings.gpu_index
            if self.settings.device == "cuda"
            else None,
            "initialization_seconds": self.initialization_seconds,
            "transcriptions": self.turns,
            "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        }

    def transcribe(self, audio: bytes) -> dict[str, Any]:
        wav_pcm(audio)
        started = time.monotonic()
        try:
            result = self.backend.transcribe(
                audio,
                language="pt",
                format="wav",
                beam_size=self.settings.beam_size,
                condition_on_previous_text=False,
                vad_filter=self.settings.vad_filter,
                initial_prompt=ROOM_TERMS if self.settings.room_terms else None,
            )
        except Exception as exc:
            raise VoiceError("stt_transcription_failed") from exc
        if (
            result.language not in (None, "pt")
            or not isinstance(result.text, str)
            or len(result.text) > 256
        ):
            raise VoiceError("stt_invalid_transcription")
        self.turns += 1
        return {
            "text": result.text.strip(),
            "metrics": {
                **self.health(),
                "transcription_seconds": time.monotonic() - started,
                "first_transcription": self.turns == 1,
            },
        }

    def close(self) -> None:
        self.backend._model = None


def validate_timeout(value: float) -> None:
    if isinstance(value, bool) or not math.isfinite(value) or not 0 < value <= 300:
        raise VoiceError("invalid_operation_timeout")
