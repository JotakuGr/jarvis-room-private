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
from .samsung_session_policy import OperatorTurn, SamsungTextSession
from .samsung_state import SamsungCommandResult


def _validated_request(intent: SamsungNaturalIntent) -> SamsungRequest:
    if type(intent) is not SamsungNaturalIntent or intent.recognized is not True:
        raise SamsungLabError("invalid_action")
    # Revalida a correspondência completa, inclusive ação e entidade vinculadas.
    if parse_samsung_intent(intent.phrase) != intent:
        raise SamsungLabError("invalid_action")
    return SamsungRequest(intent.action)


def _validate_paths(token_file: Path, audit_file: Path) -> None:
    if not isinstance(token_file, Path):
        raise SamsungLabError("token_required")
    if not isinstance(audit_file, Path):
        raise SamsungLabError("audit_unavailable")
    try:
        if token_file.expanduser().resolve() == audit_file.expanduser().resolve():
            raise SamsungLabError("audit_unavailable")
    except (OSError, ValueError, RuntimeError):
        raise SamsungLabError("audit_unavailable") from None


def execute_natural_intent(
    intent: SamsungNaturalIntent, *, token_file: Path, audit_file: Path,
    observation_timeout: float = 30.0,
) -> SamsungCommandResult:
    request = _validated_request(intent)
    window = ObservationWindow(observation_timeout)
    load_samsung_inventory()
    _validate_paths(token_file, audit_file)
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


class SamsungSessionControl:
    """Reutiliza credenciais, auditoria e controlador durante o contexto ativo.

    Não lê mensagens nem emite permissões; a sessão confiável faz isso somente
    para um turno obtido diretamente do terminal. Não há HTTP na inicialização.
    """

    def __init__(self, *, token_file: Path, audit_file: Path, observation_timeout=30.0):
        self._window = ObservationWindow(observation_timeout)
        load_samsung_inventory()
        _validate_paths(token_file, audit_file)
        self._token_file, self._audit_file = token_file, audit_file
        self._audit, self._client = None, None

    def __enter__(self):
        token = load_samsung_token(self._token_file)
        audit = PrivateSamsungAudit(self._audit_file)
        try:
            audit.__enter__()
            client = SamsungRESTClient(token=token, read_enabled=True, commands_enabled=True)
        except BaseException:
            audit.close()
            raise
        self._audit, self._client = audit, client
        return self

    def execute(
        self, session: SamsungTextSession, turn: OperatorTurn,
        intent: SamsungNaturalIntent,
    ) -> SamsungCommandResult:
        request = _validated_request(intent)
        if type(session) is not SamsungTextSession or self._audit is None or self._client is None:
            raise SamsungLabError("manual_authorization_required")
        permit = session.authorize(turn, intent)
        return execute_samsung_manual(
            self._client, request, permit, self._audit,
            observation_timeout=self._window.timeout_seconds,
        )

    def __exit__(self, *args):
        audit, self._audit, self._client = self._audit, None, None
        if audit is not None:
            return audit.__exit__(*args)
