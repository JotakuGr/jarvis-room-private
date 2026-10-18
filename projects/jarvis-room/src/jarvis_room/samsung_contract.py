"""Contrato exclusivo Samsung; texto de IA não representa autorização."""

from dataclasses import dataclass

BASE_URL = "http://127.0.0.1:18123"
TV_ENTITY_ID = "media_player.samsung_bet_series_32_lh32betblggxzd"
ON_SCRIPT = "script.jarvis_ligar_samsung"
OFF_SCRIPT = "script.jarvis_desligar_samsung"
ACTION_SCRIPTS = (("turn_on", ON_SCRIPT), ("turn_off", OFF_SCRIPT))
ALLOWED_ENTITIES = frozenset({TV_ENTITY_ID, ON_SCRIPT, OFF_SCRIPT})
ERROR_CODES = frozenset({
    "invalid_inventory", "invalid_action", "invalid_configuration", "disabled",
    "target_rejected", "token_required", "auth_error", "not_found",
    "unavailable", "invalid_response", "redirect_rejected", "tls_error",
    "manual_authorization_required", "confirmation_required", "cancelled",
    "script_not_verified", "audit_unavailable", "operation_failed", "command_outcome_unknown", "state_not_matched",
    "state_observation_timeout",
})


class SamsungLabError(RuntimeError):
    """Somente códigos públicos, nunca texto de resposta HTTP ou credenciais."""

    def __init__(self, code: str):
        self.code = code if isinstance(code, str) and code in ERROR_CODES else "operation_failed"
        super().__init__(self.code)


class SamsungCommandUncertain(SamsungLabError):
    """O POST pode ter sido recebido. Não repetir automaticamente."""

    def __init__(self):
        super().__init__("command_outcome_unknown")


@dataclass(frozen=True, slots=True)
class SamsungRequest:
    action: str

    def __post_init__(self):
        if not isinstance(self.action, str) or self.action not in dict(ACTION_SCRIPTS):
            raise SamsungLabError("invalid_action")

    @property
    def script_entity_id(self) -> str:
        return dict(ACTION_SCRIPTS)[self.action]
