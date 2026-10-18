"""Contrato offline de transporte; não implementa cliente HTTP ou autenticação.

A allowlist abaixo pertence somente à simulação, não ao inventário físico.
"""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

SIMULATED_ENTITY_IDS = frozenset({"light.sala"})


class HaTransportError(RuntimeError):
    """Transporte desabilitado ou solicitação simulada inválida."""


def validate_entity_id(entity_id: str) -> None:
    if not isinstance(entity_id, str) or entity_id not in SIMULATED_ENTITY_IDS:
        raise HaTransportError("Entidade fora da allowlist da simulação.")


def validate_service_call(domain: str, service: str, entity_id: str) -> None:
    validate_entity_id(entity_id)
    if not isinstance(domain, str) or domain != "light":
        raise HaTransportError("Domínio não permitido na simulação.")
    if not isinstance(service, str) or service not in ("turn_on", "turn_off"):
        raise HaTransportError("Ação não permitida na simulação.")


@dataclass(frozen=True)
class StateSnapshot:
    """Valor transportado, sem prova de procedência ou execução física."""

    entity_id: str
    state: str

    def __post_init__(self):
        validate_entity_id(self.entity_id)
        if not isinstance(self.state, str) or self.state not in ("on", "off", "unknown", "unavailable"):
            raise HaTransportError("Estado simulado inválido.")


@runtime_checkable
class HATransport(Protocol):
    def call_service(self, domain: str, service: str, entity_id: str) -> None:
        ...

    def get_state(self, entity_id: str) -> StateSnapshot | None:
        ...


class DisabledHATransport:
    def call_service(self, domain: str, service: str, entity_id: str) -> None:
        raise HaTransportError("Transporte real desabilitado.")

    def get_state(self, entity_id: str) -> StateSnapshot | None:
        raise HaTransportError("Transporte real desabilitado.")
