"""Gateway de comandos estruturados para um backend de automação confiável."""

import re
from typing import Protocol

from .control_guard import ToolReceipt, render_action_result


class DeviceBackend(Protocol):
    """Interface para um adaptador de automação confiável."""

    def perform_and_verify(self, entity_id: str, action: str) -> ToolReceipt:
        ...


class RoomControlGateway:
    """Valida comandos e resultados antes de apresentar uma confirmação.

    O formato do identificador não prova existência ou autorização do dispositivo.
    O backend deverá aplicar as permissões e fornecer recibos confiáveis.
    """

    ALLOWED_ACTIONS = frozenset({"turn_on", "turn_off"})

    def __init__(self, backend: DeviceBackend | None = None) -> None:
        self._backend = backend

    def execute(self, entity_id: str, action: str) -> str:
        if not isinstance(action, str) or action not in self.ALLOWED_ACTIONS:
            return "Ação não autorizada."

        if not isinstance(entity_id, str) or not re.fullmatch(
            r"light\.[a-z0-9_]+", entity_id
        ):
            return "Dispositivo inválido ou não autorizado."

        if self._backend is None:
            return render_action_result(entity_id, action)

        try:
            receipt = self._backend.perform_and_verify(entity_id, action)
        except Exception:
            return "Não foi possível executar o comando."

        if (
            not isinstance(receipt, ToolReceipt)
            or type(receipt.success) is not bool
            or type(receipt.state_verified) is not bool
        ):
            return "Ação não confirmada: resultado de ferramenta inválido."

        return render_action_result(entity_id, action, receipt)
