"""Inspeção de áudio sem abrir streams, capturar fala ou alterar configurações."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import os
import platform
import shutil
from pathlib import Path
from typing import Any


def dependency_versions() -> dict[str, str | None]:
    result = {}
    for name in (
        "faster-whisper",
        "ctranslate2",
        "sounddevice",
        "soundfile",
        "numpy",
        "kokoro",
        "torch",
        "openwakeword",
        "onnxruntime",
        "nvidia-cublas-cu12",
        "nvidia-cudnn-cu12",
    ):
        try:
            result[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            result[name] = None
    return result


def asset_status(directory: str | None, names: tuple[str, ...]) -> dict:
    if directory is None:
        return {"configured": False, "available": False}
    root = Path(directory).expanduser().resolve()
    files = {name: (root / name).is_file() for name in names}
    return {
        "configured": True,
        "model": root.name,
        "files": files,
        "available": all(files.values()),
    }


def gpu_snapshot() -> dict:
    import subprocess

    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.total,memory.used,memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=2,
            check=True,
        )
        rows = []
        for line in result.stdout.splitlines()[:32]:
            index, name, total, used, free = [part.strip() for part in line.split(",")]
            rows.append(
                {
                    "index": int(index),
                    "name": name,
                    "total_mib": int(total),
                    "used_mib": int(used),
                    "free_mib": int(free),
                }
            )
        return {"status": "observed", "gpus": rows, "scope": "whole_gpu_not_process"}
    except (OSError, ValueError, subprocess.SubprocessError):
        return {"status": "unavailable", "gpus": []}


def audio_diagnostics(sd: Any = None) -> dict[str, Any]:
    packages = {
        name: importlib.util.find_spec(name) is not None
        for name in (
            "sounddevice",
            "soundfile",
            "numpy",
            "faster_whisper",
            "ctranslate2",
            "kokoro",
            "openwakeword",
            "onnxruntime",
        )
    }
    result: dict[str, Any] = {
        "system": platform.system(),
        "kernel": platform.release(),
        "python": platform.python_version(),
        "packages": packages,
        "versions": dependency_versions(),
        "wsl": "microsoft" in platform.release().lower(),
        "wslg_directory": Path("/mnt/wslg").is_dir(),
        "wslg_pulse_socket": Path("/mnt/wslg/PulseServer").exists(),
        "pulse_server_configured": bool(os.environ.get("PULSE_SERVER")),
        "permissions": {
            "wslg_pulse_readable": os.access("/mnt/wslg/PulseServer", os.R_OK),
            "wslg_pulse_writable": os.access("/mnt/wslg/PulseServer", os.W_OK),
            "snd_directory_exists": Path("/dev/snd").is_dir(),
            "snd_directory_readable": os.access("/dev/snd", os.R_OK),
            "snd_directory_writable": os.access("/dev/snd", os.W_OK),
        },
        "tools": {
            name: shutil.which(name) is not None
            for name in (
                "pactl",
                "arecord",
                "aplay",
                "espeak-ng",
            )
        },
        "devices": [],
        "host_apis": [],
        "default_devices": None,
        "input_available": False,
        "output_available": False,
        "capture_performed": False,
        "system_changes": False,
    }
    if sd is None and not packages["sounddevice"]:
        result["audio_status"] = "sounddevice_missing"
        return result
    try:
        if sd is None:
            import sounddevice as sd
        result["portaudio"] = list(sd.get_portaudio_version())
        result["host_apis"] = [str(item["name"]) for item in sd.query_hostapis()]
        result["default_devices"] = list(sd.default.device)
        for index, device in enumerate(sd.query_devices()):
            result["devices"].append(
                {
                    "index": index,
                    "name": str(device["name"]),
                    "input_channels": int(device["max_input_channels"]),
                    "output_channels": int(device["max_output_channels"]),
                    "default_samplerate": float(device["default_samplerate"]),
                }
            )
        result["input_available"] = any(
            d["input_channels"] > 0 for d in result["devices"]
        )
        result["output_available"] = any(
            d["output_channels"] > 0 for d in result["devices"]
        )
        result["audio_status"] = "enumerated_not_validated"
    except Exception:
        result["audio_status"] = "portaudio_unavailable"
    return result
