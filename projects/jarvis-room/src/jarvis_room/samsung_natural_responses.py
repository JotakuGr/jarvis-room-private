"""Apresentação em português; aceite e estado HA não comprovam ação física."""

from dataclasses import asdict, dataclass, field

from .samsung_contract import SamsungLabError
from .samsung_natural_intent import SamsungNaturalIntent
from .samsung_state import SamsungCommandResult


@dataclass(frozen=True, slots=True)
class SamsungNaturalReply:
    text: str
    status: str
    action_verified: bool = field(default=False, init=False)
    physical_action_verified: bool = field(default=False, init=False)

    def report(self) -> dict:
        return asdict(self)


def recognition_reply(intent: SamsungNaturalIntent) -> SamsungNaturalReply:
    if type(intent) is not SamsungNaturalIntent or not intent.recognized:
        return SamsungNaturalReply("Esse comando não está habilitado para os dispositivos da sala.", "unsupported")
    verb = "ligar" if intent.action == "turn_on" else "desligar"
    return SamsungNaturalReply(
        f"Identifiquei a solicitação para {verb} a televisão Samsung. "
        "Aguardando autorização. Nenhum comando foi enviado.",
        "awaiting_authorization",
    )


def error_reply(error: BaseException) -> SamsungNaturalReply:
    code = error.code if isinstance(error, SamsungLabError) else None
    if code == "invalid_action":
        return recognition_reply(None)
    if code in ("manual_authorization_required", "confirmation_required", "cancelled"):
        return SamsungNaturalReply("A operação não foi autorizada. Nenhum comando foi enviado.", "not_authorized")
    # Não ecoar erros internos nem presumir ausência de envio em erro inesperado.
    return SamsungNaturalReply(
        "Não foi possível concluir a operação. Consulte a auditoria antes de qualquer nova tentativa.",
        "interrupted",
    )


def result_reply(result: SamsungCommandResult) -> SamsungNaturalReply:
    if type(result) is not SamsungCommandResult:
        return error_reply(RuntimeError())
    if result.delivery == "unknown":
        return SamsungNaturalReply(
            "Não foi possível determinar se o comando foi recebido. "
            "Nenhuma nova tentativa automática será realizada.", "delivery_uncertain",
        )
    if result.delivery == "accepted":
        if not result.audit_complete:
            return SamsungNaturalReply(
                "O Home Assistant aceitou o comando, mas a auditoria ficou incompleta. "
                "Consulte o registro antes de qualquer nova tentativa.", "audit_incomplete",
            )
        if result.observation.outcome == "matched" and result.reported_target_match and result.error_code is None:
            state = "ligada" if result.action == "turn_on" else "desligada"
            return SamsungNaturalReply(
                f"O Home Assistant aceitou o comando e informou que a televisão está {state}.",
                "ha_state_reported",
            )
        if result.observation.outcome in ("timed_out", "unavailable"):
            return SamsungNaturalReply(
                "O comando foi aceito pelo Home Assistant, mas o estado da televisão "
                "não foi confirmado dentro do prazo.", "state_unconfirmed",
            )
        return SamsungNaturalReply(
            "O Home Assistant aceitou o comando, mas a observação do estado não foi concluída. "
            "Consulte a auditoria antes de qualquer nova tentativa.", "observation_interrupted",
        )
    if result.delivery == "rejected":
        return SamsungNaturalReply("O Home Assistant não aceitou o comando. O estado físico não foi verificado.", "rejected")
    if result.error_code in ("manual_authorization_required", "confirmation_required", "cancelled"):
        return error_reply(SamsungLabError(result.error_code))
    return SamsungNaturalReply("Nenhum comando de controle foi enviado. Não foi possível preparar a operação.", "not_sent")
