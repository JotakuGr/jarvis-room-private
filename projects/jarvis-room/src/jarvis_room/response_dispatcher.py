"""Seleciona respostas rápidas e o fluxo seguro existente."""

from typing import Callable

from .command_router import normalize, route_message
from .safe_entrypoint import ALLOWED_CHAT, SafeReply, process_message
from .verified_replies import verified_reply_for


def dispatch_message(
    message: str,
    chat: Callable[[str], str] | None = None,
) -> SafeReply:
    """Responde fatos cadastrados sem chamar o modelo."""
    decision = route_message(message)
    normalized = normalize(message)
    # Somente perguntas informativas explicitamente permitidas usam o atalho.
    if decision.kind == "conversation" and normalized in ALLOWED_CHAT:
        return SafeReply(
            text=verified_reply_for(message),
            channel="conversation",
            action_verified=False,
        )

    # Comandos, consultas ao inventário e mensagens não cadastradas seguem
    # a política de segurança existente.
    return process_message(message, chat=chat)
