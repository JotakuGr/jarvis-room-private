"""Premissas WLED offline; não configura controladores nem dimensiona potência."""

from dataclasses import asdict, dataclass
from pathlib import Path

from ._offline_json import load_object
from .home_assistant_catalog import ControlAssessment

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "wled_zones.json"


class WledPlanError(ValueError):
    """Plano fora das premissas autorizadas para esta sprint."""


@dataclass(frozen=True)
class WledPlan:
    schema_version: int
    status: str
    led_type: str
    voltage_nominal_v: int
    length_m: int
    leds_per_meter: int
    controller_family: str
    firmware: str
    power_design_verified: bool
    physical_control_enabled: bool


def load_wled_plan(path: Path = DEFAULT_PATH) -> WledPlan:
    data = load_object(path, WledPlanError)
    expected = {
        "schema_version": 1, "status": "planned", "led_type": "WS2815",
        "voltage_nominal_v": 12, "length_m": 100, "leds_per_meter": 60,
        "controller_family": "ESP32", "firmware": "WLED",
        "power_design_verified": False, "physical_control_enabled": False,
    }
    if set(data) != set(expected) or any(
        type(data[key]) is not type(value) or data[key] != value
        for key, value in expected.items()
    ):
        raise WledPlanError("Somente premissas planejadas sem controle físico são permitidas.")
    return WledPlan(**data)


def wled_report(path: Path = DEFAULT_PATH) -> dict:
    plan = load_wled_plan(path)
    return {
        "mode": "offline",
        "assumptions": asdict(plan),
        "declared_led_count": plan.length_m * plan.leds_per_meter,
        "installation_confirmed": False,
        "power_dimensioned": False,
        "total_power_watts": None,
        "power_supply_count": None,
        "controller_count": None,
        "home_assistant_connected": False,
        "physical_control_enabled": False,
    }


def assess_wled_command(command: str, path: Path = DEFAULT_PATH) -> ControlAssessment:
    try:
        load_wled_plan(path)
    except WledPlanError:
        return ControlAssessment("plan_unavailable")
    if not isinstance(command, str) or command not in ("on", "off", "color", "brightness", "effect"):
        return ControlAssessment("unsupported_action")
    return ControlAssessment("power_design_not_verified")
