"""Grupos lógicos da sala: resolução declarativa, nunca execução física."""

from dataclasses import dataclass
from pathlib import Path

from .room_device_registry import DEFAULT_PATH, GROUPS, RoomDevice, RoomRegistryError, load_room_devices


class RoomGroupError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class GroupResolution:
    group_id: str
    members: tuple[RoomDevice, ...]


def resolve_group(group_id: str, path: Path = DEFAULT_PATH) -> GroupResolution:
    if not isinstance(group_id, str) or group_id not in GROUPS:
        raise RoomGroupError("unknown_group")
    try:
        devices = load_room_devices(path)
    except RoomRegistryError:
        raise RoomGroupError("group_catalog_unavailable") from None
    # O catálogo é indexado por ID único; não se duplicam membros por alias.
    return GroupResolution(group_id, tuple(d for d in devices.values() if d.group == group_id))


def group_inventory_report(path: Path = DEFAULT_PATH) -> dict:
    devices = load_room_devices(path)
    return {
        "mode": "offline", "physical_control_enabled": False,
        "groups": {
            group: [{"device_id": d.id, "name": d.name, "integration_status": d.integration_status,
                     "record_kind": d.record_kind, "execution_available": False}
                    for d in devices.values() if d.group == group]
            for group in sorted(GROUPS)
        },
    }
