"""Ponto de entrada determinístico, sem conexão com modelos de linguagem."""

from .command_router import route_message
from .control_gateway import RoomControlGateway


def handle_message(
    text: str,
    gateway: RoomControlGateway | None = None,
) -> str:
    decision = route_message(text)
    if decision.kind == "control":
        controller = gateway if gateway is not None else RoomControlGateway()
        return controller.execute(decision.entity_id, decision.action)
    if decision.kind == "unsupported":
        return (
            "Não executei esse comando. "
            "Este dispositivo ou ação ainda não está habilitado."
        )
    return (
        "A conversação ainda não está conectada "
        "a esta interface de controle."
    )
