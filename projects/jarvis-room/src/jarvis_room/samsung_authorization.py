"""Seleção fechada de capacidades confiáveis; não aceita autorização textual."""

from .samsung_contract import SamsungLabError, SamsungRequest
from .samsung_manual_policy import ManualPermit, consume_manual_permit
from .samsung_session_policy import SessionPermit


def consume_control_permit(permit, request: SamsungRequest) -> None:
    if type(permit) is ManualPermit:
        consume_manual_permit(permit, request)
    elif type(permit) is SessionPermit:
        permit.consume(request)
    else:
        raise SamsungLabError("manual_authorization_required")
