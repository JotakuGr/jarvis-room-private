"""Planejamento da lousa exata, sem comandos seriais ou de rede."""

from dataclasses import asdict, dataclass, field
from pathlib import Path

from ._offline_json import load_object
from .home_assistant_catalog import (
    DEFAULT_PATH as CATALOG_PATH, ControlAssessment, DeviceCatalogError, load_device_plans,
)

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "hikvision_ds_d5b65rb_d.json"
KNOWN_INTERFACES = ("RS-232", "RJ45", "HDMI IN", "HDMI OUT", "Touch-USB")


class HikvisionPlanError(ValueError):
    """Plano inválido ou incompatível com o catálogo planejado."""


@dataclass(frozen=True)
class HikvisionPlan:
    manufacturer: str
    model: str
    device_id: str
    status: str
    control_protocol_verified: bool
    network_control_verified: bool
    rs232_command_set_verified: bool
    ha_entity_id: None
    interfaces: tuple[str, ...] = field(default=KNOWN_INTERFACES, init=False)


def load_hikvision_plan(path: Path = DEFAULT_PATH, catalog_path: Path = CATALOG_PATH) -> HikvisionPlan:
    data = load_object(path, HikvisionPlanError)
    expected = {
        "manufacturer": "Hikvision", "model": "DS-D5B65RB/D",
        "device_id": "hikvision_board", "status": "planned",
        "control_protocol_verified": False, "network_control_verified": False,
        "rs232_command_set_verified": False, "ha_entity_id": None,
    }
    if set(data) != set(expected) or any(
        type(data[key]) is not type(value) or data[key] != value
        for key, value in expected.items()
    ):
        raise HikvisionPlanError("Somente o modelo planejado, sem protocolos verificados, é permitido.")
    try:
        device = load_device_plans(catalog_path).get(data["device_id"])
    except DeviceCatalogError as exc:
        raise HikvisionPlanError("Catálogo vinculado indisponível.") from exc
    if device is None or device.model != data["model"] or device.manufacturer != data["manufacturer"] or device.category != "interactive_display":
        raise HikvisionPlanError("A lousa não corresponde ao catálogo vinculado.")
    return HikvisionPlan(**data)


def hikvision_report(path: Path = DEFAULT_PATH, catalog_path: Path = CATALOG_PATH) -> dict:
    return {
        "mode": "offline", "plan": asdict(load_hikvision_plan(path, catalog_path)),
        "physical_control_enabled": False,
    }


def assess_hikvision_command(command: str, path: Path = DEFAULT_PATH) -> ControlAssessment:
    try:
        load_hikvision_plan(path)
    except HikvisionPlanError:
        return ControlAssessment("plan_unavailable")
    if not isinstance(command, str) or command not in (
        "power_on", "power_off", "set_input", "volume", "touch", "screen_cast"
    ):
        return ControlAssessment("unsupported_action")
    return ControlAssessment("protocol_not_verified")
