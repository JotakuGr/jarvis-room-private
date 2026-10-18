"""Ponte tipada de intenção Samsung para o fluxo manual da Sprint 4.

Não recebe respostas de LLM, não envia HTTP e não emite auditoria duplicada.
Só as interfaces explícitas de operador podem chamar esta função.
"""

from dataclasses import replace
from pathlib import Path

from .samsung_audit import PrivateSamsungAudit
from .samsung_contract import SamsungLabError, SamsungRequest
from .samsung_control import execute_samsung_manual
from .samsung_credentials import load_samsung_token
from .samsung_inventory import load_samsung_inventory
from .samsung_manual_policy import authorize_manual
from .samsung_natural_intent import SamsungNaturalIntent, parse_samsung_intent
from .samsung_observation import ObservationWindow
from .samsung_rest_client import SamsungRESTClient
from .samsung_state import SamsungCommandResult


def execute_natural_intent(
    intent: SamsungNaturalIntent, *, token_file: Path, audit_file: Path,
    observation_timeout: float = 30.0,
) -> SamsungCommandResult:
    if type(intent) is not SamsungNaturalIntent or intent.recognized is not True:
        raise SamsungLabError("invalid_action")
    # Revalida a correspondência completa, inclusive ação e entidade vinculadas.
    if parse_samsung_intent(intent.phrase) != intent:
        raise SamsungLabError("invalid_action")
    request = SamsungRequest(intent.action)
    window = ObservationWindow(observation_timeout)
    load_samsung_inventory()
    if not isinstance(token_file, Path):
        raise SamsungLabError("token_required")
    if not isinstance(audit_file, Path):
        raise SamsungLabError("audit_unavailable")
    try:
        if token_file.expanduser().resolve() == audit_file.expanduser().resolve():
            raise SamsungLabError("audit_unavailable")
    except (OSError, ValueError, RuntimeError):
        raise SamsungLabError("audit_unavailable") from None
    permit = authorize_manual(request)
    token = load_samsung_token(token_file)
    result = None
    try:
        with PrivateSamsungAudit(audit_file) as audit:
            client = SamsungRESTClient(token=token, read_enabled=True, commands_enabled=True)
            result = execute_samsung_manual(
                client, request, permit, audit,
                observation_timeout=window.timeout_seconds,
            )
    except (Exception, KeyboardInterrupt):
        if type(result) is not SamsungCommandResult:
            raise
        # Erro ao fechar o log não apaga um aceite já obtido pelo controlador.
        return replace(result, audit_complete=False, error_code="audit_unavailable")
    return result
