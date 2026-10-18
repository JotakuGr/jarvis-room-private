"""Vínculo declarado do helper LAB; não prova criação, origem ou isolamento."""

from dataclasses import dataclass
from pathlib import Path

from ._offline_json import load_object
from .ha_lab_readonly_client import valid_lab_entity_id

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "ha_lab_entities.json"


class HALabBindingError(ValueError):
    pass


@dataclass(frozen=True)
class HALabBinding:
    device_id: str
    entity_id: str
    kind: str
    physical: bool
    read_only: bool


def load_ha_lab_bindings(path: Path = DEFAULT_PATH) -> dict[str, HALabBinding]:
    data = load_object(path, HALabBindingError)
    if set(data) != {"schema_version", "mode", "bindings"} or type(data["schema_version"]) is not int or data["schema_version"] != 1 or data["mode"] != "lab_virtual_only":
        raise HALabBindingError("invalid_bindings")
    if not isinstance(data["bindings"], list) or not data["bindings"]:
        raise HALabBindingError("invalid_bindings")
    result = {}
    entities = set()
    for raw in data["bindings"]:
        if not isinstance(raw, dict) or set(raw) != {"device_id", "entity_id", "kind", "physical", "read_only"}:
            raise HALabBindingError("invalid_bindings")
        if raw["device_id"] != "room_main_lights" or not valid_lab_entity_id(raw["entity_id"]):
            raise HALabBindingError("binding_not_allowed")
        if raw["kind"] != "virtual_helper" or raw["physical"] is not False or raw["read_only"] is not True:
            raise HALabBindingError("binding_not_allowed")
        if raw["device_id"] in result or raw["entity_id"] in entities:
            raise HALabBindingError("duplicate_binding")
        result[raw["device_id"]] = HALabBinding(**raw)
        entities.add(raw["entity_id"])
    return result


def require_lab_binding(device_id: str, path: Path = DEFAULT_PATH) -> HALabBinding:
    bindings = load_ha_lab_bindings(path)
    if not isinstance(device_id, str) or device_id not in bindings:
        raise HALabBindingError("unknown_lab_device")
    return bindings[device_id]


def validate_observed_binding(binding: HALabBinding, observed_entity_id: str) -> None:
    if not isinstance(binding, HALabBinding) or not isinstance(observed_entity_id, str) or observed_entity_id != binding.entity_id:
        raise HALabBindingError("entity_mismatch")
