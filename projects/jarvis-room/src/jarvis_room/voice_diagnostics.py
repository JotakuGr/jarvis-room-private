"""Inspeção de áudio sem abrir streams, capturar fala ou alterar configurações."""

from __future__ import annotations

import importlib.util
import os
import platform
import shutil
from pathlib import Path
from typing import Any


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
