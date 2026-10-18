"""Barreira local de operador: terminal, opt-in, frase exata, uso único.

Não autentica identidade institucional nem protege contra código Python
malicioso no mesmo processo. Não é ferramenta disponível a nenhum LLM.
"""

import os
import sys
import threading
import time

from .samsung_contract import TV_ENTITY_ID, SamsungLabError, SamsungRequest

CONTROL_OPT_IN = "JARVIS_SAMSUNG_LAB_CONTROL"
READ_OPT_IN = "JARVIS_SAMSUNG_LAB_READ"
_ISSUER = object()
PERMIT_SECONDS = 60


class ManualPermit:
    __slots__ = ("_action", "_expires", "_used", "_lock")

    def __init__(self, action, expires, *, issuer):
        if issuer is not _ISSUER:
            raise SamsungLabError("manual_authorization_required")
        self._action, self._expires, self._used = action, expires, False
        self._lock = threading.Lock()

    def consume(self, request: SamsungRequest):
        with self._lock:
            if (
                not isinstance(request, SamsungRequest) or request.action != self._action
                or self._used or time.monotonic() >= self._expires
                or os.environ.get(CONTROL_OPT_IN) != "1"
            ):
                raise SamsungLabError("manual_authorization_required")
            self._used = True


def confirmation_phrase(request: SamsungRequest) -> str:
    if not isinstance(request, SamsungRequest):
        raise SamsungLabError("invalid_action")
    return "LIGAR SAMSUNG" if request.action == "turn_on" else "DESLIGAR SAMSUNG"


def authorize_manual(request: SamsungRequest) -> ManualPermit:
    phrase = confirmation_phrase(request)
    if os.environ.get(CONTROL_OPT_IN) != "1":
        raise SamsungLabError("manual_authorization_required")
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise SamsungLabError("confirmation_required")
    print(f"TV: {TV_ENTITY_ID}\nScript: {request.script_entity_id}", file=sys.stderr)
    try:
        answer = input(f"Teste físico manual. Digite exatamente {phrase}: ")
    except (EOFError, OSError, KeyboardInterrupt):
        raise SamsungLabError("cancelled") from None
    if answer != phrase:
        raise SamsungLabError("cancelled")
    return ManualPermit(request.action, time.monotonic() + PERMIT_SECONDS, issuer=_ISSUER)


def consume_manual_permit(permit: ManualPermit, request: SamsungRequest) -> None:
    if type(permit) is not ManualPermit:
        raise SamsungLabError("manual_authorization_required")
    permit.consume(request)
