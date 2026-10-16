"""Conversação experimental, sem acesso a automação física.

A restrição por prefixos limita o uso do protótipo; não é um classificador
completo de segurança. O serviço recebe apenas uma função de conversação.
"""

from dataclasses import dataclass
from typing import Callable, Literal

from .command_router import normalize, route_message

INFORMATION_PREFIXES = (
    "explique ",
    "o que e ",
    "como funciona ",
    "qual a diferenca ",
    "por que ",
    "resuma ",
    "defina ",
    "quem foi ",
    "me explique ",
)


@dataclass(frozen=True)
class ExperimentalReply:
    text: str
    channel: Literal["experimental", "blocked"]
    action_verified: bool = False


def answer_informational_question(
    message: str,
    chat: Callable[[str], str] | None = None,
) -> ExperimentalReply:
    """Consulta o LLM apenas no canal experimental."""
    normalized = normalize(message)
    decision = route_message(message)
    # Restrição inicial a perguntas informativas.
    if decision.kind != "conversation" or not any(
        normalized.startswith(prefix) for prefix in INFORMATION_PREFIXES
    ):
        return ExperimentalReply(
            text=(
                "Modo experimental aceita apenas perguntas "
                "informativas habilitadas. Nenhuma ação foi executada."
            ),
            channel="blocked",
        )

    if chat is None:
        return ExperimentalReply(
            text="Serviço de conversação não conectado.",
            channel="blocked",
        )

    try:
        response = chat(message)
    except Exception:
        return ExperimentalReply(
            text=(
                "Não foi possível consultar a conversação experimental. "
                "Nenhuma ação foi executada."
            ),
            channel="blocked",
        )

    if not isinstance(response, str) or not response.strip():
        return ExperimentalReply(
            text=(
                "Resposta experimental inválida ou vazia. "
                "Nenhuma ação foi executada."
            ),
            channel="blocked",
        )

    return ExperimentalReply(
        text="[RESPOSTA EXPERIMENTAL — NÃO VERIFICADA]\n" + response.strip(),
        channel="experimental",
        action_verified=False,
    )
