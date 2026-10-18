"""Catálogo de planejamento offline; não contém estados ou permissões reais."""

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ._offline_json import load_object, nonempty

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "home_assistant_devices.json"
CATEGORIES = frozenset({
    "light", "led_strip", "climate", "interactive_display", "display", "presence_sensor",
})
FUTURE_ACTIONS = frozenset({"turn_on", "turn_off"})


class DeviceCatalogError(ValueError):
    """Catálogo planejado indisponível ou não autorizado."""


@dataclass(frozen=True)
class PlannedDevice:
    id: str
    name: str
    category: str
    manufacturer: str | None
    model: str | None
    status: str
    home_assistant_entity_id: None


@dataclass(frozen=True)
class ControlAssessment:
    reason: str
    allowed: bool = field(default=False, init=False)


def load_device_plans(path: Path = DEFAULT_PATH) -> dict[str, PlannedDevice]:
    data = load_object(path, DeviceCatalogError)
    if (
        set(data) != {"schema_version", "devices"}
        or type(data.get("schema_version")) is not int
        or data["schema_version"] != 1
        or not isinstance(data.get("devices"), list)
        or not data["devices"]
    ):
        raise DeviceCatalogError("Estrutura ou versão do catálogo inválida.")
    fields = {
        "id", "name", "category", "manufacturer", "model", "status",
        "home_assistant_entity_id",
    }
    devices = {}
    for raw in data["devices"]:
        if not isinstance(raw, dict) or set(raw) != fields:
            raise DeviceCatalogError("Campos do dispositivo inválidos.")
        identifier = raw["id"]
        if not isinstance(identifier, str) or re.fullmatch(r"[a-z][a-z0-9_]*", identifier) is None:
            raise DeviceCatalogError("Identificador inválido.")
        if identifier in devices:
            raise DeviceCatalogError("Identificador duplicado.")
        if not nonempty(raw["name"]) or not isinstance(raw["category"], str) or raw["category"] not in CATEGORIES:
            raise DeviceCatalogError("Nome ou categoria inválidos.")
        if any(raw[key] is not None and not nonempty(raw[key]) for key in ("manufacturer", "model")):
            raise DeviceCatalogError("Fabricante ou modelo inválido.")
        if raw["status"] != "planned" or raw["home_assistant_entity_id"] is not None:
            raise DeviceCatalogError("Somente planos sem entidade real são permitidos.")
        devices[identifier] = PlannedDevice(**raw)
    return devices


def catalog_report(path: Path = DEFAULT_PATH) -> dict:
    devices = load_device_plans(path)
    return {
        "mode": "offline",
        "device_count": len(devices),
        "device_ids": list(devices),
        "devices": [asdict(device) for device in devices.values()],
        "home_assistant_connected": False,
        "physical_control_enabled": False,
    }


def assess_control(device_id: str, action: str, path: Path = DEFAULT_PATH) -> ControlAssessment:
    try:
        devices = load_device_plans(path)
    except DeviceCatalogError:
        return ControlAssessment("catalog_unavailable")
    if not isinstance(device_id, str) or device_id not in devices:
        return ControlAssessment("unknown_device")
    if not isinstance(action, str) or action not in FUTURE_ACTIONS:
        return ControlAssessment("unsupported_action")
    if devices[device_id].category == "presence_sensor":
        return ControlAssessment("read_only_device")
    return ControlAssessment("integration_not_verified")


def main() -> None:
    try:
        print(json.dumps(catalog_report(), ensure_ascii=False, indent=2))
    except DeviceCatalogError:
        raise SystemExit("Catálogo offline indisponível.")


if __name__ == "__main__":
    main()
