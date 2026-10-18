"""Prontidão offline WLED; pendências não são dimensionamento elétrico."""

from dataclasses import dataclass
from pathlib import Path

from ._offline_json import load_object, matches_exact_plan
from .wled_plan import load_wled_plan

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "wled_lab_readiness.json"
PENDING_FIELDS = (
    "power_watts_per_meter", "current_per_led_amps", "strip_batch",
    "segment_lengths_m", "power_supply_locations", "cable_sections_mm2",
    "circuit_protection", "fuses", "power_injection_points", "voltage_drop",
    "ground_reference", "controller_count", "refresh_rate_hz",
    "total_power_watts", "power_supply_count",
)


class WledReadinessError(ValueError):
    pass


@dataclass(frozen=True)
class WledReadiness:
    status: str
    premises: tuple
    pending_fields: tuple[str, ...]
    controller_connected: bool = False
    power_design_verified: bool = False
    physical_control_enabled: bool = False


def load_wled_readiness(path: Path = DEFAULT_PATH) -> WledReadiness:
    data = load_object(path, WledReadinessError)
    try:
        plan = load_wled_plan()
    except ValueError:
        raise WledReadinessError("Plano WLED indisponível.") from None
    premises = {key: getattr(plan, key) for key in (
        "led_type", "voltage_nominal_v", "length_m", "leds_per_meter", "controller_family", "firmware"
    )}
    premises["declared_led_count"] = plan.length_m * plan.leds_per_meter
    expected = {
        "schema_version": 1, "status": "planned", "premises": premises,
        "controller_connected": False, "power_design_verified": False,
        "physical_control_enabled": False, "zones_count": None,
        "measurements": dict.fromkeys(PENDING_FIELDS),
    }
    if not matches_exact_plan(data, expected):
        raise WledReadinessError("Dimensionamento não comprovado ou configuração inválida.")
    return WledReadiness("planned", tuple(premises.items()), PENDING_FIELDS)


def readiness_report(path: Path = DEFAULT_PATH) -> dict:
    data = load_wled_readiness(path)
    return {
        "mode": "offline", "status": data.status, "premises": dict(data.premises),
        "pending_measurements": dict.fromkeys(data.pending_fields),
        "controller_connected": False, "power_design_verified": False,
        "physical_control_enabled": False, "total_power_watts": None,
        "power_supply_count": None, "zones_count": None,
    }
