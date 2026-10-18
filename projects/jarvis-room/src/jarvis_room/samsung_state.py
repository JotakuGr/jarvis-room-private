"""Estado reportado pelo HA não é confirmação física independente da TV."""

from dataclasses import asdict, dataclass, field
from datetime import datetime

from .samsung_contract import ERROR_CODES, TV_ENTITY_ID, SamsungLabError, SamsungRequest
from .samsung_observation import ObservationSummary

STATES = frozenset({"on", "off", "idle", "playing", "paused", "buffering", "standby", "unknown", "unavailable"})
ON_STATES = frozenset({"on", "idle", "playing", "paused"})


def _timestamp(value):
    if value is None:
        return None
    try:
        if not isinstance(value, str):
            raise ValueError()
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError()
    except (ValueError, OverflowError):
        raise SamsungLabError("invalid_response") from None
    return value


@dataclass(frozen=True, slots=True)
class SamsungReportedState:
    state: str
    observed_at: str | None = None
    entity_id: str = field(default=TV_ENTITY_ID, init=False)
    source: str = field(default="home_assistant_reported", init=False)
    physical_action_verified: bool = field(default=False, init=False)

    def __post_init__(self):
        if not isinstance(self.state, str) or self.state not in STATES:
            raise SamsungLabError("invalid_response")
        _timestamp(self.observed_at)

    @property
    def available(self):
        return self.state not in ("unknown", "unavailable")


def parse_samsung_state(payload: dict) -> SamsungReportedState:
    fields = {"entity_id", "state", "last_changed", "last_updated", "last_reported", "attributes", "context"}
    if not isinstance(payload, dict) or not set(payload) <= fields or payload.get("entity_id") != TV_ENTITY_ID:
        raise SamsungLabError("invalid_response")
    for key in ("last_changed", "last_updated", "last_reported"):
        _timestamp(payload.get(key))
    return SamsungReportedState(payload.get("state"), payload.get("last_updated") or payload.get("last_changed") or payload.get("last_reported"))


@dataclass(frozen=True, slots=True)
class SamsungCommandResult:
    action: str
    delivery: str = "not_attempted"
    before: SamsungReportedState | None = None
    after: SamsungReportedState | None = None
    error_code: str | None = None
    audit_complete: bool = True
    observation: ObservationSummary = field(default_factory=ObservationSummary)
    physical_action_verified: bool = field(default=False, init=False)

    def __post_init__(self):
        SamsungRequest(self.action)
        if type(self.audit_complete) is not bool:
            raise SamsungLabError("invalid_response")
        if type(self.observation) is not ObservationSummary:
            raise SamsungLabError("invalid_response")
        if not isinstance(self.delivery, str) or self.delivery not in ("not_attempted", "accepted", "rejected", "unknown"):
            raise SamsungLabError("invalid_response")
        if any(item is not None and not isinstance(item, SamsungReportedState) for item in (self.before, self.after)):
            raise SamsungLabError("invalid_response")
        if self.error_code is not None and (not isinstance(self.error_code, str) or self.error_code not in ERROR_CODES):
            raise SamsungLabError("invalid_response")

    @property
    def command_sent(self) -> bool | None:
        if self.delivery == "unknown":
            return None
        return self.delivery == "accepted"

    @property
    def reported_target_match(self) -> bool:
        if self.after is None:
            return False
        return self.after.state in ON_STATES if self.action == "turn_on" else self.after.state == "off"

    def report(self) -> dict:
        return {
            "mode": "manual_samsung_lab", "entity_id": TV_ENTITY_ID,
            "action": self.action, "command_delivery": self.delivery,
            "command_sent": self.command_sent,
            "state_before": None if self.before is None else self.before.state,
            "state_reported": None if self.after is None else self.after.state,
            "reported_at": None if self.after is None else self.after.observed_at,
            "reported_target_match": self.reported_target_match,
            "state_transition_observed": self.before is not None and self.after is not None and self.before.available and self.after.available and self.before.state != self.after.state,
            "physical_action_verified": False,
            "independent_physical_confirmation": "not_collected",
            "error": self.error_code,
            "audit_complete": self.audit_complete,
            "observation": {**asdict(self.observation), "message": self.observation.message},
        }
