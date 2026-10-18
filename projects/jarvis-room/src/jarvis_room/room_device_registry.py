"""Catálogo canônico offline, com vínculos explícitos aos inventários legados."""

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from types import MappingProxyType

from ._offline_json import load_object, matches_exact_plan
from .home_assistant_catalog import load_device_plans
from .room_text import normalize_room_text
from .samsung_contract import TV_ENTITY_ID, SamsungLabError
from .samsung_inventory import load_samsung_inventory
from .wled_plan import load_wled_plan

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "room_devices.json"
GROUPS = frozenset({"monitores", "leds", "audio"})
GROUP_TARGETS = MappingProxyType({
    "os monitores": "monitores", "todos os monitores": "monitores",
    "todas as tvs": "monitores", "as tvs": "monitores",
    "os leds": "leds", "as luzes led": "leds", "todas as luzes led": "leds",
    "o sistema de audio": "audio", "os alto falantes": "audio",
})
CAPABILITIES = frozenset({"turn_on", "turn_off", "read_state"})


class RoomRegistryError(ValueError):
    """Catálogo ausente/inconsistente; mensagem sem conteúdo do arquivo."""


@dataclass(frozen=True, slots=True)
class RoomDevice:
    id: str
    name: str
    aliases: tuple[str, ...]
    group: str | None
    category: str
    manufacturer: str | None
    model: str | None
    capabilities: tuple[str, ...]
    adapter: str
    entity_id: str | None
    integration_status: str
    execution_available: bool
    requires_physical_authorization: bool
    record_kind: str
    legacy_ids: tuple[str, ...]
    assumptions: tuple[tuple[str, object], ...]
    physical_control_enabled: bool = field(default=False, init=False)


def valid_id(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,63}", value) is not None


def _label(value):
    return isinstance(value, str) and 0 < len(value.strip()) <= 160 and not any(ord(c) < 32 for c in value)


def load_room_devices(path: Path = DEFAULT_PATH) -> dict[str, RoomDevice]:
    try:
        if not isinstance(path, Path):
            raise ValueError()
        data = load_object(path, ValueError)
        if set(data) != {"schema_version", "devices"} or type(data["schema_version"]) is not int or data["schema_version"] != 1:
            raise ValueError()
        if type(data["devices"]) is not list or not 1 <= len(data["devices"]) <= 128:
            raise ValueError()
        fields = set(RoomDevice.__dataclass_fields__) - {"physical_control_enabled"}
        devices, aliases, entities, links = {}, set(), set(), set()
        legacy = load_device_plans()
        for raw in data["devices"]:
            if type(raw) is not dict or set(raw) != fields:
                raise ValueError()
            if not valid_id(raw["id"]) or raw["id"] in devices or not _label(raw["name"]):
                raise ValueError()
            if type(raw["aliases"]) is not list or not 1 <= len(raw["aliases"]) <= 12:
                raise ValueError()
            normalized = []
            for alias in raw["aliases"]:
                key = normalize_room_text(alias, address=False)
                if key is None or re.fullmatch(r"[a-z][a-z0-9 ]*", key) is None or key in aliases or key in GROUP_TARGETS:
                    raise ValueError()
                aliases.add(key)
                normalized.append(key)
            category = raw["category"]
            expected_groups = {"display": "monitores", "led_strip": "leds", "audio": "audio",
                               "light": None, "climate": None, "presence_sensor": None}
            if not isinstance(category, str) or category not in expected_groups or raw["group"] != expected_groups[category]:
                raise ValueError()
            if any(value is not None and not _label(value) for value in (raw["manufacturer"], raw["model"])):
                raise ValueError()
            for identifier, manufacturer, model in (
                ("samsung_lab_tv", "Samsung", "LH32BETBLGGXZD"),
                ("hikvision_board", "Hikvision", "DS-D5B65RB/D"),
            ):
                if (raw["manufacturer"], raw["model"]) == (manufacturer, model) and raw["id"] != identifier:
                    raise ValueError()
            caps = raw["capabilities"]
            if type(caps) is not list or not caps or any(type(c) is not str or c not in CAPABILITIES for c in caps) or len(set(caps)) != len(caps):
                raise ValueError()
            if category == "presence_sensor" and caps != ["read_state"]:
                raise ValueError()
            if type(raw["execution_available"]) is not bool or raw["execution_available"] is not False:
                raise ValueError()
            if type(raw["requires_physical_authorization"]) is not bool or raw["requires_physical_authorization"] != bool(set(caps) & {"turn_on", "turn_off"}):
                raise ValueError()
            if raw["id"] == "samsung_lab_tv":
                load_samsung_inventory()
                if (raw["adapter"], raw["entity_id"], raw["integration_status"], raw["manufacturer"], raw["model"], raw["category"], raw["record_kind"]) != (
                    "samsung_sprint5", TV_ENTITY_ID, "lab_existing", "Samsung", "LH32BETBLGGXZD", "display", "identified_device"
                ):
                    raise ValueError()
            elif (raw["adapter"] != "planned" or raw["entity_id"] is not None
                  or raw["integration_status"] != "planned" or raw["record_kind"] not in ("planned_device", "planned_role")):
                raise ValueError()
            if raw["record_kind"] == "planned_role" and (category != "display" or raw["manufacturer"] is not None or raw["model"] is not None):
                raise ValueError()
            entity = raw["entity_id"]
            if entity is not None:
                if entity in entities:
                    raise ValueError()
                entities.add(entity)
            refs = raw["legacy_ids"]
            if type(refs) is not list or any(not valid_id(ref) or ref not in legacy or ref in links for ref in refs) or len(set(refs)) != len(refs):
                raise ValueError()
            for ref in refs:
                old = legacy[ref]
                if ref != raw["id"] or (old.model is not None and old.model != raw["model"]) or (old.manufacturer is not None and old.manufacturer != raw["manufacturer"]):
                    raise ValueError()
                links.add(ref)
            assumptions = raw["assumptions"]
            if raw["id"] == "led_perimeter":
                plan = load_wled_plan()
                expected = {"led_type": plan.led_type, "voltage_nominal_v": plan.voltage_nominal_v,
                            "length_m": plan.length_m, "leds_per_meter": plan.leds_per_meter, "power_design_verified": False}
            else:
                expected = {}
            if not matches_exact_plan(assumptions, expected):
                raise ValueError()
            values = {**raw, "aliases": tuple(normalized), "capabilities": tuple(caps),
                      "legacy_ids": tuple(refs), "assumptions": tuple(assumptions.items())}
            devices[raw["id"]] = RoomDevice(**values)
        if links != set(legacy) or "samsung_lab_tv" not in devices:
            raise ValueError()
        return devices
    except (OSError, ValueError, TypeError, KeyError, RecursionError, SamsungLabError):
        raise RoomRegistryError("room_catalog_unavailable") from None


def legacy_catalog_links(path: Path = DEFAULT_PATH) -> dict[str, str]:
    return {legacy: device.id for device in load_room_devices(path).values() for legacy in device.legacy_ids}


def room_registry_report(path: Path = DEFAULT_PATH) -> dict:
    devices = load_room_devices(path)
    return {"mode": "offline", "device_count": len(devices), "devices": [asdict(d) for d in devices.values()],
            "physical_control_enabled": False, "live_state_queried": False,
            "display_roles_are_not_confirmed_additional_hardware": True}


def main():
    try:
        print(json.dumps(room_registry_report(), ensure_ascii=False, indent=2))
    except RoomRegistryError:
        raise SystemExit("Catálogo da sala indisponível.") from None


if __name__ == "__main__":
    main()
