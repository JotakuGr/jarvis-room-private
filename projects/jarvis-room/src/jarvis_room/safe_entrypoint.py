"""Separa controle determinístico e conversação explicitamente habilitada."""

from dataclasses import dataclass
from typing import Callable, Literal

from .command_router import normalize, route_message
from .room_assistant import handle_message

ALLOWED_CHAT = frozenset({
    "quem e voce",
    "explique a arquitetura da sala",
    "quais sao os dois monitores da sala",
})


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
    if decision.kind != "conversation":
        return SafeReply(
            text=handle_message(message),
            channel="control" if decision.kind == "control" else "blocked",
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

    return SafeReply(text=response, channel="conversation")
