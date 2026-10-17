"""Contrato comum para provedores de conversação.

Não define operações físicas nem ferramentas de automação.
"""

import re
from dataclasses import dataclass, field
from typing import Literal, Protocol


class ProviderUnavailable(RuntimeError):
    """Provedor indisponível ou bloqueado pela política."""


class ProviderResourceUnavailable(ProviderUnavailable):
    """Inferência recusada pela política de recursos locais."""


def _valid_identifier(value: object) -> bool:
    return (
        isinstance(value, str)
        and re.fullmatch(r"[a-z][a-z0-9_-]*", value) is not None
    )


@dataclass(frozen=True)
class ProviderRequest:
    prompt: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.prompt, str)
            or not self.prompt.strip()
            or len(self.prompt) > 4096
        ):
            raise ValueError("Prompt inválido.")


@dataclass(frozen=True)
class ProviderInfo:
    identifier: str
    location: Literal["local", "remote"]
    enabled: bool = False

    def __post_init__(self) -> None:
        if not _valid_identifier(self.identifier):
            raise ValueError("Identificador de provedor inválido.")
        if self.location not in ("local", "remote"):
            raise ValueError("Localização de provedor inválida.")
        if type(self.enabled) is not bool:
            raise ValueError("Estado de habilitação inválido.")


@dataclass(frozen=True)
class ProviderResponse:
    text: str
    provider_id: str
    action_verified: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("Resposta de provedor inválida.")
        if not _valid_identifier(self.provider_id):
            raise ValueError("Identificador de provedor inválido.")


class ConversationProvider(Protocol):
    """Interface exclusivamente textual; habilitação não autoriza ações físicas."""

    info: ProviderInfo

    def respond(self, request: ProviderRequest) -> ProviderResponse:
        ...
