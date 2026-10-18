"""Inventário físico Samsung separado dos planos e helpers das Sprints 2/3."""

from dataclasses import asdict, dataclass, field
from pathlib import Path

from ._offline_json import load_object, matches_exact_plan
from .samsung_contract import ACTION_SCRIPTS, BASE_URL, TV_ENTITY_ID, SamsungLabError

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "samsung_lab.json"
EXPECTED = {
    "schema_version": 1, "mode": "physical_samsung_lab",
    "status": "pending_physical_acceptance", "manufacturer": "Samsung",
    "model": "LH32BETBLGGXZD", "device_id": "samsung_lab_tv",
    "base_url": BASE_URL, "entity_id": TV_ENTITY_ID,
    "scripts": dict(ACTION_SCRIPTS), "execution_enabled_by_default": False,
    "llm_control_enabled": False, "independent_physical_verification": False,
    "entity_source": "user_report",
}


@dataclass(frozen=True, slots=True)
class SamsungInventory:
    model: str = field(default="LH32BETBLGGXZD", init=False)
    entity_id: str = field(default=TV_ENTITY_ID, init=False)
    base_url: str = field(default=BASE_URL, init=False)
    scripts: tuple[tuple[str, str], ...] = field(default=ACTION_SCRIPTS, init=False)
    physical_action_verified: bool = field(default=False, init=False)


def load_samsung_inventory(path: Path = DEFAULT_PATH) -> SamsungInventory:
    try:
        data = load_object(path, ValueError)
        if not matches_exact_plan(data, EXPECTED):
            raise ValueError()
    except (OSError, ValueError, TypeError):
        raise SamsungLabError("invalid_inventory") from None
    return SamsungInventory()


def inventory_report(path: Path = DEFAULT_PATH) -> dict:
    return {
        **asdict(load_samsung_inventory(path)), "mode": "offline",
        "status": "pending_physical_acceptance", "execution_enabled": False,
        "llm_control_enabled": False, "live_entities_checked": False,
    }
