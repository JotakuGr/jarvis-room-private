"""Respostas determinísticas para resultados de automação da Sala Temática.

Os recibos devem ser fornecidos exclusivamente por um adaptador confiável do
Home Assistant. Os campos deste objeto não autenticam sua origem e não devem
ser preenchidos com resultados inventados ou gerados pelo modelo de linguagem.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ToolReceipt:
    """Resultado de execução e verificação emitido pelo adaptador confiável."""

    source: str
    entity_id: str
    action: str
    success: bool
    state_verified: bool


def render_action_result(
    entity_id: str,
    action: str,
    receipt: ToolReceipt | None = None,
) -> str:
    """Nunca confirma uma ação sem resultado confiável e verificado."""
    if receipt is None:
        return (
            "Não executei esse comando. "
            "O controle deste dispositivo ainda não está disponível."
        )

    if (
        receipt.source != "home_assistant"
        or receipt.entity_id != entity_id
        or receipt.action != action
    ):
        return "Ação não confirmada: resultado de ferramenta inválido."

    if not receipt.success:
        return "Não foi possível executar o comando."

    if not receipt.state_verified:
        return (
            "O comando foi enviado, mas o estado do dispositivo "
            "ainda não foi confirmado."
        )

    return f"Ação confirmada: {entity_id} — {action}."
