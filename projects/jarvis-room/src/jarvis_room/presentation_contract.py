"""Contrato v2 somente leitura; nenhum áudio, token ou operação física."""

from __future__ import annotations

import json
import math
import re
from datetime import datetime
from functools import lru_cache

from .room_device_registry import load_room_devices
from .voice_contract import VoiceState

VERSION = 2
LIMIT = 8192
STATUSES = frozenset({"planned", "unknown", "offline", "connected", "unavailable"})
SERVICES = frozenset({"voice", "ollama", "llm", "stt", "tts", "home_assistant"})
PLAYBACK = frozenset({"idle", "synthesizing", "playing", "unavailable", "error"})
LAB_ENTITY = "input_boolean.jarvis_lab_light"
SESSION = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")


def text(value: object, limit: int) -> bool:
    return (
        isinstance(value, str)
        and 0 < len(value) <= limit
        and all(c.isprintable() for c in value)
    )


@lru_cache(maxsize=1)
def catalog():
    return load_room_devices()


def validate_payload(kind: object, payload: object) -> None:
    valid = False
    if not isinstance(kind, str) or type(payload) is not dict:
        raise ValueError("invalid_presentation_payload")
    keys = set(payload)
    if kind == "connection":
        valid = keys == {"state"} and payload["state"] in (
            "connected",
            "disconnected",
            "connecting",
            "reconnecting",
        )
    elif kind == "heartbeat":
        valid = not payload
    elif kind == "voice_state":
        valid = keys == {"state"} and payload["state"] in tuple(
            s.value for s in VoiceState
        )
    elif kind == "playback_status":
        valid = (
            keys == {"state"}
            and isinstance(payload["state"], str)
            and payload["state"] in PLAYBACK
        )
    elif kind == "voice_amplitude":
        value = payload.get("amplitude")
        valid = (
            keys == {"amplitude"}
            and type(value) in (int, float)
            and math.isfinite(value)
            and 0 <= value <= 1
        )
    elif kind == "service_status":
        valid = (
            keys == {"id", "status", "detail"}
            and payload["id"] in tuple(SERVICES)
            and payload["status"] in tuple(STATUSES)
            and text(payload["detail"], 128)
        )
    elif kind == "device_status":
        device = (
            catalog().get(payload.get("id"))
            if isinstance(payload.get("id"), str)
            else None
        )
        valid = (
            keys == {"id", "status", "state"}
            and device is not None
            and payload["status"] in tuple(STATUSES)
            and payload["state"] in (None, "on", "off", "unknown", "unavailable")
        )
        if valid and device.integration_status == "planned":
            valid = payload["status"] == "planned" and payload["state"] is None
    elif kind == "lab_observation":
        valid = (
            keys == {"entityId", "status", "state"}
            and payload["entityId"] == LAB_ENTITY
            and payload["status"] in tuple(STATUSES)
            and payload["state"] in (None, "on", "off", "unknown", "unavailable")
        )
        if valid and payload["status"] != "connected":
            valid = payload["state"] in (None, "unavailable")
    elif kind == "conversation":
        valid = (
            keys == {"question", "answer"}
            and text(payload["question"], 256)
            and text(payload["answer"], 700)
        )
    if not valid:
        raise ValueError("invalid_presentation_payload")


def validate_event(event: object) -> dict:
    if type(event) is not dict or set(event) != {
        "version",
        "source",
        "sessionId",
        "sequence",
        "type",
        "observedAt",
        "payload",
    }:
        raise ValueError("invalid_presentation_event")
    if (
        type(event["version"]) is not int
        or event["version"] != VERSION
        or event["source"] != "backend"
    ):
        raise ValueError("invalid_presentation_version")
    if not isinstance(event["sessionId"], str) or not SESSION.fullmatch(
        event["sessionId"]
    ):
        raise ValueError("invalid_presentation_session")
    if type(event["sequence"]) is not int or not 0 <= event["sequence"] <= 2**53 - 1:
        raise ValueError("invalid_presentation_sequence")
    observed = event["observedAt"]
    if not isinstance(observed, str) or not re.fullmatch(
        r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|[+-]\d\d:\d\d)", observed
    ):
        raise ValueError("invalid_presentation_timestamp")
    datetime.fromisoformat(observed.replace("Z", "+00:00"))
    validate_payload(event["type"], event["payload"])
    return event


def strict_json(raw: bytes) -> dict:
    if not raw or len(raw) > LIMIT:
        raise ValueError("presentation_message_limit")

    def pairs(values):
        result = {}
        for key, value in values:
            if key in result:
                raise ValueError("duplicate_field")
            result[key] = value
        return result

    def constant(_):
        raise ValueError("non_finite")

    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeError, RecursionError) as exc:
        raise ValueError("invalid_presentation_json") from exc
    if type(value) is not dict:
        raise ValueError("invalid_presentation_json")
    return value
