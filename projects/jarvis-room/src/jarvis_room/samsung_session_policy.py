"""Capacidades de uma sessão textual local, sem autorização por texto de IA.

Esta fronteira protege o fluxo da aplicação, não código Python malicioso no
mesmo processo. Não é uma autorização para microfone, arquivos ou ferramentas.
"""

import os
import sys
import threading
import time
from dataclasses import dataclass

from .samsung_contract import SamsungLabError, SamsungRequest
from .samsung_natural_intent import SamsungNaturalIntent, parse_samsung_intent

_ISSUER = object()
PERMIT_SECONDS = 60


@dataclass(frozen=True, slots=True, init=False, repr=False)
class OperatorTurn:
    text: str

    def __init__(self, text: str, *, issuer):
        if issuer is not _ISSUER or not isinstance(text, str):
            raise SamsungLabError("manual_authorization_required")
        object.__setattr__(self, "text", text)


class SamsungTextSession:
    """Lê diretamente o terminal; somente a opção inicial habilita controle."""

    def __init__(self, *, enable_samsung: bool = False):
        if type(enable_samsung) is not bool:
            raise SamsungLabError("invalid_configuration")
        self._stdin, self._stdout = sys.stdin, sys.stdout
        self._owner = (os.getpid(), threading.get_ident())
        self._enabled, self._active = enable_samsung, True
        self._turn, self._issued = None, False
        self._validate_terminal()

    def _validate_terminal(self):
        if (
            not self._active or (os.getpid(), threading.get_ident()) != self._owner
            or sys.stdin is not self._stdin or sys.stdout is not self._stdout
            or not self._stdin.isatty() or not self._stdout.isatty()
        ):
            raise SamsungLabError("confirmation_required")

    def read_turn(self) -> OperatorTurn:
        self._validate_terminal()
        self.finish_turn()
        # Não há API que converta uma string externa em turno autorizado.
        text = input("Você: ")
        self._validate_terminal()
        self._turn = OperatorTurn(text, issuer=_ISSUER)
        return self._turn

    def authorize(self, turn: OperatorTurn, intent: SamsungNaturalIntent):
        self._validate_terminal()
        if (
            not self._enabled or type(turn) is not OperatorTurn
            or turn is not self._turn or self._issued
            or type(intent) is not SamsungNaturalIntent or not intent.recognized
            or parse_samsung_intent(turn.text) != intent
        ):
            raise SamsungLabError("manual_authorization_required")
        self._issued = True
        return SessionPermit(self, turn, SamsungRequest(intent.action), issuer=_ISSUER)

    def finish_turn(self):
        self._turn, self._issued = None, False

    def close(self):
        self._active = False
        self.finish_turn()

    def __enter__(self):
        self._validate_terminal()
        return self

    def __exit__(self, *_):
        self.close()


class SessionPermit:
    """Uso único, ação vinculada, prazo curto e revogação pelo ciclo da sessão."""

    __slots__ = ("_session", "_turn", "_action", "_expires", "_used", "_lock")

    def __init__(self, session, turn, request, *, issuer):
        if issuer is not _ISSUER:
            raise SamsungLabError("manual_authorization_required")
        self._session, self._turn, self._action = session, turn, request.action
        self._expires, self._used = time.monotonic() + PERMIT_SECONDS, False
        self._lock = threading.Lock()

    def consume(self, request: SamsungRequest):
        with self._lock:
            self._session._validate_terminal()
            if (
                self._used or type(request) is not SamsungRequest
                or request.action != self._action
                or time.monotonic() >= self._expires
                or not self._session._enabled
                or self._session._turn is not self._turn
            ):
                raise SamsungLabError("manual_authorization_required")
            self._used = True
