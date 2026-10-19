"""Apresentação de planos e inventário; nenhum caminho de execução física."""

from dataclasses import dataclass, field

from .room_device_registry import load_room_devices
from .room_intent import parse_room_intent
from .room_orchestrator import RoomExecutionResult, orchestrate_room_intent
from .room_text import normalize_room_text

INVENTORY_QUERIES = frozenset({
    "quais sao os grupos da sala", "liste os grupos da sala",
    "quais sao os dispositivos da sala", "liste os dispositivos da sala",
    "mostre o inventario da sala",
})


@dataclass(frozen=True, slots=True)
class RoomReply:
    text: str
    channel: str
    action_verified: bool = field(default=False, init=False)
    physical_action_verified: bool = field(default=False, init=False)


def render_room_execution(result: RoomExecutionResult) -> RoomReply:
    if type(result) is not RoomExecutionResult or result.mode not in ("offline_preview", "simulation"):
        raise ValueError("invalid_room_result")
    devices = load_room_devices()
    if result.intent_kind == "scene_control":
        prefix = ("Preparei o plano de apresentação com iluminação LED, monitores e áudio."
                  if result.target_id == "modo_apresentacao" else
                  "Preparei o encerramento: áudio, monitores e LEDs; o computador e a sessão continuam ativos.")
    elif result.intent_kind == "group_control":
        prefix = f"Identifiquei o grupo {result.target_id}."
    else:
        prefix = f"Comando reconhecido para {devices[result.target_id].name}."
    details = []
    for item in result.results:
        device = devices[item.device_id]
        state = ("integração de laboratório existente; somente preview nesta rota"
                 if device.integration_status == "lab_existing" else "integração física pendente")
        details.append(f"{device.name}: {state} [{item.outcome}]")
    status = ("Planejamento offline; controle físico não habilitado nesta rota."
              if result.mode == "offline_preview" else
              f"Resultado exclusivamente simulado: {result.status}.")
    return RoomReply(
        prefix + "\n" + "\n".join(details) + "\n" + status
        + " Nenhum comando físico foi enviado nesta simulação.", "room_plan",
    )


def respond_to_room_operator(message: str) -> RoomReply | None:
    """Recebe só texto e nunca recebe cliente, token, sessão ou permissão."""
    normalized = normalize_room_text(message)
    if normalized in INVENTORY_QUERIES:
        try:
            devices = load_room_devices()
            lines = ["Inventário declarativo da sala, sem consulta de estado real:"]
            for device in devices.values():
                lines.append(f"{device.id}: {device.name}; grupo={device.group or 'sem grupo'}; "
                             f"{device.integration_status}; {device.record_kind}.")
            lines.append("Grupos: monitores, leds, audio. Slots de exibição não confirmam equipamentos adicionais.")
            return RoomReply("\n".join(lines), "inventory")
        except (ValueError, OSError):
            return RoomReply("Inventário da sala indisponível. Nenhuma ação foi executada.", "blocked")
    intent = parse_room_intent(message)
    if not intent.recognized:
        if intent.reason in ("unsupported_capability", "catalog_unavailable") and normalized and normalized.startswith(("ligue ", "desligue ", "ative ", "ativar ", "desative ", "encerrar ")):
            return RoomReply("Comando da sala indisponível ou sem capacidade autorizada. Nenhuma ação foi executada.", "blocked")
        return None
    try:
        return render_room_execution(orchestrate_room_intent(intent))
    except (ValueError, OSError):
        return RoomReply("Plano da sala indisponível. Nenhuma ação foi executada.", "blocked")
