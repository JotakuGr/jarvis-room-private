"""Política declarativa offline: nenhum pedido autoriza execução física.

actor_id é metadado não autenticado e nunca concede permissões.
"""

from dataclasses import dataclass
from pathlib import Path

from ._offline_json import nonempty
from .home_assistant_catalog import DEFAULT_PATH, DeviceCatalogError, load_device_plans


@dataclass(frozen=True)
class AutomationRequest:
    device_id: str
    action: str
    actor_id: str


@dataclass(frozen=True)
class ControlDecision:
    allowed: bool
    reason: str


def evaluate_request(request: AutomationRequest, path: Path = DEFAULT_PATH) -> ControlDecision:
    if not isinstance(request, AutomationRequest) or not all(
        nonempty(value) for value in (request.device_id, request.action, request.actor_id)
    ):
        return ControlDecision(False, "invalid_request")
    try:
        plans = load_device_plans(path)
    except DeviceCatalogError:
        return ControlDecision(False, "catalog_unavailable")
    if request.device_id not in plans:
        return ControlDecision(False, "unknown_device")
    if request.action not in ("turn_on", "turn_off"):
        return ControlDecision(False, "unsupported_action")
    if plans[request.device_id].category == "presence_sensor":
        return ControlDecision(False, "read_only_device")
    return ControlDecision(False, "integration_not_verified")
