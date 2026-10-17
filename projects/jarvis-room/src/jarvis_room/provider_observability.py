"""Diagnóstico offline e eventos mínimos de provedores.

Não importa OpenJarvis, executa inferência ou armazena conteúdo de conversação.
"""

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .inference_policy import check_current_resources
from .provider_config import DEFAULT_PATH, ProviderConfigError, load_provider_config

EventOutcome = Literal[
    "response_unverified",
    "resources_blocked",
    "provider_blocked",
]


@dataclass(frozen=True)
class ProviderEvent:
    provider_id: str
    outcome: EventOutcome
    action_verified: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.provider_id, str) or re.fullmatch(
            r"[a-z][a-z0-9_-]*", self.provider_id
        ) is None:
            raise ValueError("Identificador de provedor inválido.")
        if self.outcome not in (
            "response_unverified", "resources_blocked", "provider_blocked"
        ):
            raise ValueError("Resultado de evento inválido.")


class EventRecorder:
    """Guarda somente eventos operacionais em memória, sem persistência."""

    def __init__(self) -> None:
        self._events: list[ProviderEvent] = []

    def record(self, event: ProviderEvent) -> None:
        if not isinstance(event, ProviderEvent):
            raise ValueError("Evento de provedor inválido.")
        self._events.append(event)

    @property
    def events(self) -> tuple[ProviderEvent, ...]:
        return tuple(self._events)


def diagnose(path: Path = DEFAULT_PATH) -> dict:
    """Consulta configuração e memória sem consultar o provedor.

    Elegibilidade é instantânea e não garante estabilidade ou qualidade.
    """
    report = {
        "schema_version": 1,
        "mode": "offline",
        "provider_id": None,
        "configuration_valid": False,
        "local_enabled": False,
        "remote_provider_allowed": False,
        "resource_minimum_met": False,
        "status": "configuration_blocked",
        "action_verified": False,
        "inference_executed_by_diagnostic": False,
    }
    try:
        config = load_provider_config(path)
    except ProviderConfigError:
        return report
    decision = check_current_resources()
    report.update(
        provider_id=config.default_provider,
        configuration_valid=True,
        local_enabled=config.local_enabled,
        resource_minimum_met=decision.allowed,
    )
    if not config.local_enabled:
        report["status"] = "provider_blocked"
    elif not decision.allowed:
        report["status"] = "resources_blocked"
    else:
        report["status"] = "experimental_eligible"
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnóstico offline de provedores")
    parser.add_argument("--config", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = diagnose(args.config)
    contents = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output is None:
        print(contents)
        return
    try:
        args.output.write_text(contents + "\n", encoding="utf-8")
    except OSError as exc:
        parser.error(str(exc))
    print(f"Diagnóstico offline salvo em: {args.output}")


if __name__ == "__main__":
    main()
