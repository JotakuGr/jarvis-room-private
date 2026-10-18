"""Orquestração offline e contrato de simulação, sem adaptadores físicos.

Nenhuma autorização Samsung é aceita aqui. Não há backend fake padrão nem
registro dinâmico de transportes. Integrações reais exigem outra política.
"""

import argparse
import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Protocol

from .room_device_registry import DEFAULT_PATH as CATALOG_PATH, RoomDevice, load_room_devices, valid_id
from .room_intent import RoomIntent, parse_room_intent
from .room_scenes import DEFAULT_PATH as SCENES_PATH, ExecutionPlan, RoomPlanError, build_room_plan


class RoomOrchestrationError(ValueError):
    pass


class SimulationUnavailable(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SimulationBackendInfo:
    identifier: str
    mode: str = field(default="simulation", init=False)
    physical_control_enabled: bool = field(default=False, init=False)

    def __post_init__(self):
        if not valid_id(self.identifier):
            raise ValueError("invalid_simulation_backend")


@dataclass(frozen=True, slots=True)
class SimulationObservation:
    device_id: str
    action: str
    state: str
    source: str = field(default="simulation", init=False)
    physical_action_verified: bool = field(default=False, init=False)

    def __post_init__(self):
        if (not valid_id(self.device_id) or self.action not in ("turn_on", "turn_off")
            or self.state not in ("on", "off", "unknown", "unavailable")):
            raise ValueError("invalid_simulation_observation")


class RoomSimulationBackend(Protocol):
    info: SimulationBackendInfo

    def simulate_step(self, device: RoomDevice, action: str) -> SimulationObservation: ...


@dataclass(frozen=True, slots=True)
class DeviceOperationResult:
    device_id: str
    action: str
    integration_status: str
    outcome: str
    simulated_state: str | None = None
    action_verified: bool = field(default=False, init=False)
    physical_action_verified: bool = field(default=False, init=False)


@dataclass(frozen=True, slots=True)
class OrchestrationEvent:
    correlation_id: str
    mode: str
    device_id: str
    action: str
    outcome: str
    physical_action_verified: bool = field(default=False, init=False)


@dataclass(frozen=True, slots=True)
class RoomExecutionResult:
    mode: str
    status: str
    intent_kind: str
    target_id: str
    results: tuple[DeviceOperationResult, ...]
    events: tuple[OrchestrationEvent, ...]
    elapsed_seconds: float
    action_verified: bool = field(default=False, init=False)
    physical_action_verified: bool = field(default=False, init=False)

    def report(self) -> dict:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class FutureAuthorizationScope:
    """Lista declarativa para futura revisão; não é credencial consumível."""

    targets: tuple[tuple[str, str], ...]
    physical_execution_authorized: bool = field(default=False, init=False)


def future_authorization_scope(plan: ExecutionPlan) -> FutureAuthorizationScope:
    if type(plan) is not ExecutionPlan:
        raise RoomOrchestrationError("invalid_plan")
    return FutureAuthorizationScope(tuple((step.device_id, step.action) for step in plan.steps))


def run_room_plan(plan: ExecutionPlan, *, backend: RoomSimulationBackend | None = None,
                  catalog_path: Path = CATALOG_PATH, scenes_path: Path = SCENES_PATH,
                  clock=None) -> RoomExecutionResult:
    # Reconstituir o plano antes de qualquer chamada detecta intenção, alvo,
    # ação, dependência ou capacidade adulterados, além de mudanças no catálogo.
    if type(plan) is not ExecutionPlan or plan != build_room_plan(plan.intent, catalog_path, scenes_path):
        raise RoomOrchestrationError("invalid_plan")
    if backend is not None:
        info = getattr(backend, "info", None)
        if (type(info) is not SimulationBackendInfo or info.mode != "simulation"
            or info.physical_control_enabled is not False or not callable(getattr(backend, "simulate_step", None))):
            raise RoomOrchestrationError("simulation_backend_required")
    clock = time.monotonic if clock is None else clock
    started, results, events = clock(), {}, []
    correlation = uuid.uuid4().hex
    devices = load_room_devices(catalog_path)
    mode = "offline_preview" if backend is None else "simulation"
    for step in plan.steps:
        device, observed = devices[step.device_id], None
        if not step.capability_supported:
            outcome = "unsupported_capability"
        elif backend is None:
            outcome = "lab_integration_available" if device.integration_status == "lab_existing" else "pending_integration"
        elif any(results[dependency].outcome != "simulated_match" for dependency in step.depends_on):
            outcome = "blocked_dependency"
        else:
            try:
                observation = backend.simulate_step(device, step.action)
                if (type(observation) is not SimulationObservation or observation.source != "simulation"
                    or observation.device_id != step.device_id or observation.action != step.action
                    or observation.physical_action_verified is not False):
                    raise ValueError()
                observed = observation.state
                expected = "on" if step.action == "turn_on" else "off"
                outcome = "simulated_match" if observed == expected else "simulated_unconfirmed"
            except SimulationUnavailable:
                outcome = "backend_unavailable"
            except Exception:
                outcome = "simulated_error"
        results[step.device_id] = DeviceOperationResult(device.id, step.action, device.integration_status, outcome, observed)
        events.append(OrchestrationEvent(correlation, mode, device.id, step.action, outcome))
    completed = sum(item.outcome == "simulated_match" for item in results.values())
    status = "plan_ready" if backend is None else (
        "simulated_complete" if completed == len(results) else "simulated_partial" if completed else "simulated_failed"
    )
    return RoomExecutionResult(mode, status, plan.intent.kind, plan.intent.target_id,
                               tuple(results.values()), tuple(events), max(0.0, clock() - started))


def orchestrate_room_intent(intent: RoomIntent, *, backend: RoomSimulationBackend | None = None,
                            catalog_path: Path = CATALOG_PATH, scenes_path: Path = SCENES_PATH,
                            clock=None) -> RoomExecutionResult:
    plan = build_room_plan(intent, catalog_path, scenes_path)
    return run_room_plan(plan, backend=backend, catalog_path=catalog_path, scenes_path=scenes_path, clock=clock)


def main():
    parser = argparse.ArgumentParser(description="Plano offline da sala; sem opção de execução física", allow_abbrev=False)
    parser.add_argument("message", nargs="+")
    args = parser.parse_args()
    try:
        result = orchestrate_room_intent(parse_room_intent(" ".join(args.message)))
    except (ValueError, OSError):
        raise SystemExit("Comando ou configuração da sala indisponível. Nenhuma ação foi executada.") from None
    print(json.dumps(result.report(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
