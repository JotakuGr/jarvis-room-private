"""Intenções completas e determinísticas. Reconhecimento não autoriza hardware."""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .room_device_registry import DEFAULT_PATH, GROUP_TARGETS, RoomRegistryError, load_room_devices, valid_id
from .room_text import normalize_room_text

SCENE_PHRASES = {
    "ativar modo apresentacao": ("modo_apresentacao", "activate"),
    "ativar o modo apresentacao": ("modo_apresentacao", "activate"),
    "ative modo apresentacao": ("modo_apresentacao", "activate"),
    "ative o modo apresentacao": ("modo_apresentacao", "activate"),
    "encerrar apresentacao": ("encerrar_apresentacao", "deactivate"),
    "encerre a apresentacao": ("encerrar_apresentacao", "deactivate"),
    "desative o modo apresentacao": ("encerrar_apresentacao", "deactivate"),
    "desativar modo apresentacao": ("encerrar_apresentacao", "deactivate"),
}


@dataclass(frozen=True, slots=True)
class RoomIntent:
    kind: Literal["device_control", "group_control", "scene_control", "blocked"]
    recognized: bool
    action: str | None = None
    target_id: str | None = None
    phrase: str | None = None
    reason: str | None = None

    def __post_init__(self):
        if self.recognized is False:
            valid = (self.kind == "blocked" and self.action is None and self.target_id is None
                     and self.phrase is None and self.reason in (
                         "invalid_input", "unsupported_command", "unsupported_capability", "catalog_unavailable"))
        elif self.recognized is True:
            actions = ("activate", "deactivate") if self.kind == "scene_control" else ("turn_on", "turn_off")
            valid = (self.kind in ("device_control", "group_control", "scene_control")
                     and self.action in actions and valid_id(self.target_id)
                     and isinstance(self.phrase, str) and bool(self.phrase) and self.reason is None)
        else:
            valid = False
        if not valid:
            raise ValueError("invalid_room_intent")


def parse_room_intent(message: object, path: Path = DEFAULT_PATH) -> RoomIntent:
    phrase = normalize_room_text(message)
    if phrase is None:
        return RoomIntent("blocked", False, reason="invalid_input")
    try:
        devices = load_room_devices(path)
    except RoomRegistryError:
        return RoomIntent("blocked", False, reason="catalog_unavailable")
    if phrase in SCENE_PHRASES:
        target, action = SCENE_PHRASES[phrase]
        return RoomIntent("scene_control", True, action, target, phrase)
    for verb, action in (("ligue ", "turn_on"), ("desligue ", "turn_off")):
        if not phrase.startswith(verb):
            continue
        target = phrase[len(verb):]
        if target in GROUP_TARGETS:
            return RoomIntent("group_control", True, action, GROUP_TARGETS[target], phrase)
        for device in devices.values():
            if target in device.aliases:
                if action not in device.capabilities:
                    return RoomIntent("blocked", False, reason="unsupported_capability")
                return RoomIntent("device_control", True, action, device.id, phrase)
    return RoomIntent("blocked", False, reason="unsupported_command")
