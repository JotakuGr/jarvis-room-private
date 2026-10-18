"""Interpreta estado informativo do LAB; origem descritiva não autentica backend."""

from dataclasses import asdict, dataclass, field
from datetime import datetime

from .ha_lab_readonly_client import valid_lab_entity_id


class HALabStateError(ValueError):
    pass


def _timestamp(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise HALabStateError("invalid_response")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError()
    except (ValueError, OverflowError):
        raise HALabStateError("invalid_response") from None
    return value


@dataclass(frozen=True)
class HALabState:
    entity_id: str
    state: str
    observed_at: str | None = None
    source: str = field(default="home_assistant_lab", init=False)
    physical_action_verified: bool = field(default=False, init=False)

    def __post_init__(self):
        if not valid_lab_entity_id(self.entity_id) or not isinstance(self.state, str) or self.state not in ("on", "off", "unknown", "unavailable"):
            raise HALabStateError("invalid_response")
        _timestamp(self.observed_at)

    @property
    def available(self) -> bool:
        return self.state in ("on", "off")


def parse_lab_state(payload: dict, requested_entity_id: str) -> HALabState:
    fields = {"entity_id", "state", "last_updated", "last_changed", "last_reported", "attributes", "context"}
    if not isinstance(payload, dict) or not set(payload) <= fields or not valid_lab_entity_id(requested_entity_id):
        raise HALabStateError("invalid_response")
    if payload.get("entity_id") != requested_entity_id:
        raise HALabStateError("entity_mismatch")
    for key in ("last_updated", "last_changed", "last_reported"):
        _timestamp(payload.get(key))
    observed = payload.get("last_updated") or payload.get("last_changed") or payload.get("last_reported")
    return HALabState(payload["entity_id"], payload.get("state"), observed)


def state_report(state: HALabState) -> dict:
    if not isinstance(state, HALabState):
        raise HALabStateError("invalid_response")
    return {**asdict(state), "available": state.available}
