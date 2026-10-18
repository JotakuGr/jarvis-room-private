"""Manifesto imutável do laboratório, com relatório exclusivamente offline."""

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from ._offline_json import load_object

BASE_URL = "http://127.0.0.1:18123"
DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "ha_lab_manifest.json"


class HALabManifestError(ValueError):
    """Manifesto ausente, inválido ou permissivo."""


@dataclass(frozen=True)
class HALabManifest:
    schema_version: int
    mode: str
    base_url: str
    physical_control_enabled: bool
    real_devices_allowed: bool
    read_client_enabled_by_default: bool
    container_privileged: bool
    network_mode: str


def load_ha_lab_manifest(path: Path = DEFAULT_PATH) -> HALabManifest:
    data = load_object(path, HALabManifestError)
    expected = {
        "schema_version": 1, "mode": "isolated_lab", "base_url": BASE_URL,
        "physical_control_enabled": False, "real_devices_allowed": False,
        "read_client_enabled_by_default": False, "container_privileged": False,
        "network_mode": "bridge",
    }
    if set(data) != set(expected) or any(
        type(data[key]) is not type(value) or data[key] != value
        for key, value in expected.items()
    ):
        raise HALabManifestError("Manifesto de laboratório não autorizado.")
    return HALabManifest(**data)


def manifest_report(path: Path = DEFAULT_PATH) -> dict:
    return {
        "mode": "offline", "manifest": asdict(load_ha_lab_manifest(path)),
        "inference_executed": False, "physical_action_verified": False,
        "lab_connection_verified": False,
    }


if __name__ == "__main__":
    print(json.dumps(manifest_report(), ensure_ascii=False, indent=2))
