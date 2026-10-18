"""Compara valores simulados; nunca emite recibo de confirmação física.

simulated_match significa somente consistência de valores inventados no teste.
O verificador não chama serviços nem instala backend no gateway de produção.
"""

import re
from dataclasses import dataclass, field
from typing import Literal

from .ha_transport import (
    SIMULATED_DEVICE_BINDINGS,
    DisabledHATransport,
    HATransport,
    StateSnapshot,
    validate_entity_id,
)


@dataclass(frozen=True)
class SimulatedActionResult:
    device_id: str
    action: str
    requested_state: str | None
    observed_state: str | None
    outcome: Literal[
        "simulated_match", "simulated_mismatch", "simulated_unavailable", "simulated_error"
    ]
    physical_action_verified: bool = field(default=False, init=False)


def check_simulated_state(
    device_id: str,
    action: str,
    transport: HATransport | None = None,
    *,
    entity_id: str = "light.sala",
) -> SimulatedActionResult:
    requested = {"turn_on": "on", "turn_off": "off"}.get(action) if isinstance(action, str) else None

    def result(outcome, observed=None):
        return SimulatedActionResult(device_id, action, requested, observed, outcome)

    if (
        not isinstance(device_id, str)
        or re.fullmatch(r"[a-z][a-z0-9_]*", device_id) is None
        or requested is None
        or SIMULATED_DEVICE_BINDINGS.get(device_id) != entity_id
    ):
        return result("simulated_error")
    try:
        validate_entity_id(entity_id)
        reader = DisabledHATransport() if transport is None else transport
        snapshot = reader.get_state(entity_id)
        if snapshot is None:
            return result("simulated_unavailable")
        if not isinstance(snapshot, StateSnapshot) or snapshot.entity_id != entity_id:
            return result("simulated_error")
        if snapshot.state in ("unknown", "unavailable"):
            return result("simulated_unavailable", snapshot.state)
        if snapshot.state not in ("on", "off"):
            return result("simulated_error")
        return result("simulated_match" if snapshot.state == requested else "simulated_mismatch", snapshot.state)
    except Exception:
        return result("simulated_error")
