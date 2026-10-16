"""Separa controle determinístico e conversação explicitamente habilitada."""

from dataclasses import dataclass
from typing import Callable, Literal

from .capability_service import (
    control_candidate_enabled,
    render_capability_report,
)
from .command_router import normalize, route_message
from .control_guard import render_action_result
from .room_assistant import handle_message
from .verified_replies import verified_reply_for

ALLOWED_CHAT = frozenset({
    "quem e voce",
    "explique a arquitetura da sala",
    "quais sao os dois monitores da sala",
})

CAPABILITY_STATUS_QUERY = "qual e o estado dos recursos da sala"


@dataclass(frozen=True)
class SafeReply:
    """Resposta textual; texto de um LLM não comprova execução física."""

    text: str
    channel: Literal["control", "conversation", "blocked"]
    action_verified: bool = False


def process_message(
    message: str,
    chat: Callable[[str], str] | None = None,
) -> SafeReply:
    decision = route_message(message)
    # Comandos operacionais nunca chegam ao LLM.
    if decision.kind == "control":
        if not control_candidate_enabled(decision.entity_id):
            return SafeReply(
                text=render_action_result(decision.entity_id, decision.action),
                channel="control",
                action_verified=False,
            )
        return SafeReply(
            text=handle_message(message),
            channel="control",
            action_verified=False,
        )
    if decision.kind == "unsupported":
        return SafeReply(
            text=handle_message(message),
            channel="blocked",
            action_verified=False,
        )

    if normalize(message) == CAPABILITY_STATUS_QUERY:
        try:
            report = render_capability_report()
        except (OSError, ValueError, TypeError):
            return SafeReply(
                text="Inventário indisponível. Nenhuma ação foi executada.",
                channel="blocked",
            )
        return SafeReply(
            text=report,
            channel="conversation",
            action_verified=False,
        )

    if normalize(message) not in ALLOWED_CHAT:
        return SafeReply(
            text=(
                "Solicitação ainda não habilitada nesta interface. "
                "Nenhuma ação foi executada."
            ),
            channel="blocked",
        )

    if chat is None:
        return SafeReply(
            text=(
                "A conversação ainda não está conectada "
                "a esta interface de controle."
            ),
            channel="blocked",
        )

    try:
        response = chat(message)
    except Exception:
        return SafeReply(
            text=(
                "Não foi possível consultar a conversação. "
                "Nenhuma ação foi executada."
            ),
            channel="blocked",
        )

    if not isinstance(response, str) or not response.strip():
        return SafeReply(
            text=(
                "Não foi possível obter uma resposta válida da conversação. "
                "Nenhuma ação foi executada."
            ),
            channel="blocked",
        )

    return SafeReply(
        text=verified_reply_for(message),
        channel="conversation",
        action_verified=False,
    )
