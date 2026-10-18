"""Checklist offline de duas trilhas independentes; não habilita controle."""

from dataclasses import asdict, dataclass
from pathlib import Path

from ._offline_json import load_object, matches_exact_plan
from .hikvision_plan import load_hikvision_plan

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "hikvision_lab_readiness.json"


class HikvisionReadinessError(ValueError):
    pass


@dataclass(frozen=True)
class DisplayTrack:
    host_computer: str
    hdmi_cable: str
    touch_usb_cable: str
    display_verified: bool


@dataclass(frozen=True)
class ControlTrack:
    equipment_available: str
    label_revision: str
    firmware: str
    rs232_protocol_verified: bool
    command_set_verified: bool
    state_feedback_verified: bool
    network_access_authorized: bool
    institutional_permission: bool


@dataclass(frozen=True)
class HikvisionReadiness:
    schema_version: int
    model: str
    device_id: str
    status: str
    control_verified: bool
    display_track: DisplayTrack
    control_track: ControlTrack


def load_hikvision_readiness(path: Path = DEFAULT_PATH) -> HikvisionReadiness:
    data = load_object(path, HikvisionReadinessError)
    expected = {
        "schema_version": 1, "model": "DS-D5B65RB/D", "device_id": "hikvision_board",
        "status": "planned", "control_verified": False,
        "display_track": {"host_computer": "unknown", "hdmi_cable": "unknown", "touch_usb_cable": "unknown", "display_verified": False},
        "control_track": {
            "equipment_available": "unknown", "label_revision": "unknown", "firmware": "unknown",
            "rs232_protocol_verified": False, "command_set_verified": False,
            "state_feedback_verified": False, "network_access_authorized": False,
            "institutional_permission": False,
        },
    }
    if not matches_exact_plan(data, expected):
        raise HikvisionReadinessError("Prontidão não comprovada ou configuração inválida.")
    try:
        load_hikvision_plan()
    except ValueError:
        raise HikvisionReadinessError("Plano da lousa indisponível.") from None
    return HikvisionReadiness(
        data["schema_version"], data["model"], data["device_id"], data["status"],
        data["control_verified"], DisplayTrack(**data["display_track"]), ControlTrack(**data["control_track"]),
    )


def readiness_report(path: Path = DEFAULT_PATH) -> dict:
    return {
        "mode": "offline", "readiness": asdict(load_hikvision_readiness(path)),
        "display_is_equipment_control": False, "physical_control_enabled": False,
        "second_display_model": "unknown",
    }
