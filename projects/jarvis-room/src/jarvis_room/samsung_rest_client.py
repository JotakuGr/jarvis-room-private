"""REST Samsung separado: três estados GET e um serviço POST, todos fixos.

Os flags são barreiras do código, não autenticação do operador. Somente a CLI
manual supervisionada deve habilitá-los. Não há retry de POST nem redirects.
"""

import json
import math
import ssl
import urllib.error
import urllib.request

from .samsung_contract import (
    ALLOWED_ENTITIES, BASE_URL, TV_ENTITY_ID, SamsungCommandUncertain,
    SamsungLabError, SamsungRequest,
)
from .samsung_credentials import SamsungToken

SERVICE_PATH = "/api/services/script/turn_on"


class _RejectRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise SamsungLabError("redirect_rejected")


def _unique(pairs):
    data = {}
    for key, value in pairs:
        if key in data:
            raise ValueError()
        data[key] = value
    return data


def _invalid_constant(_):
    raise ValueError()


def _http_error(status):
    if status in (401, 403):
        raise SamsungLabError("auth_error")
    if status == 404:
        raise SamsungLabError("not_found")
    if 300 <= status < 400:
        raise SamsungLabError("redirect_rejected")
    raise SamsungLabError("unavailable")


class SamsungRESTClient:
    def __init__(
        self, *, token: SamsungToken, read_enabled: bool = False,
        commands_enabled: bool = False, base_url: str = BASE_URL,
        timeout: float = 5.0, max_response_bytes: int = 32768, opener=None,
    ):
        if not isinstance(token, SamsungToken):
            raise SamsungLabError("token_required")
        if base_url != BASE_URL:
            # Nenhum HTTP remoto, HTTPS não homologado, userinfo ou URL variável.
            raise SamsungLabError("target_rejected")
        if (
            type(read_enabled) is not bool or type(commands_enabled) is not bool
            or commands_enabled and not read_enabled
            or type(timeout) not in (int, float) or not math.isfinite(timeout)
            or not 0.1 <= timeout <= 8
            or type(max_response_bytes) is not int or not 1 <= max_response_bytes <= 65536
        ):
            raise SamsungLabError("invalid_configuration")
        self._token = token
        self._read_enabled = read_enabled
        self._commands_enabled = commands_enabled
        self._timeout = timeout
        self._limit = max_response_bytes
        self._opener = opener

    def _request(self, method: str, path: str, body: dict | None = None):
        if not self._read_enabled:
            raise SamsungLabError("disabled")
        state_paths = {"/api/states/" + entity for entity in ALLOWED_ENTITIES}
        if method == "GET":
            if path not in state_paths or body is not None:
                raise SamsungLabError("target_rejected")
        elif method == "POST":
            if not self._commands_enabled:
                raise SamsungLabError("disabled")
            scripts = ALLOWED_ENTITIES - {TV_ENTITY_ID}
            if path != SERVICE_PATH or not isinstance(body, dict) or set(body) != {"entity_id"} or not isinstance(body["entity_id"], str) or body["entity_id"] not in scripts:
                raise SamsungLabError("target_rejected")
        else:
            raise SamsungLabError("target_rejected")
        url = BASE_URL + path
        try:
            opener = self._opener
            if opener is None:
                opener = urllib.request.build_opener(
                    urllib.request.ProxyHandler({}), _RejectRedirect(),
                )
            data = None if body is None else json.dumps(body).encode("utf-8")
            request = urllib.request.Request(
                url, data=data, method=method,
                headers={"Authorization": self._token.authorization_header(),
                         "Accept": "application/json", "Content-Type": "application/json"},
            )
            with opener.open(request, timeout=self._timeout) as response:
                if response.geturl() != url:
                    raise SamsungLabError("redirect_rejected")
                if response.status != 200:
                    _http_error(response.status)
                raw = response.read(self._limit + 1)
            if len(raw) > self._limit:
                raise SamsungLabError("invalid_response")
            try:
                return json.loads(raw.decode("utf-8"), object_pairs_hook=_unique, parse_constant=_invalid_constant)
            except (ValueError, RecursionError):
                raise SamsungLabError("invalid_response") from None
        except SamsungLabError:
            raise
        except urllib.error.HTTPError as error:
            try:
                _http_error(error.code)
            except SamsungLabError as sanitized:
                raise sanitized from None
        except ssl.SSLError:
            raise SamsungLabError("tls_error") from None
        except Exception:
            raise SamsungLabError("unavailable") from None

    def _entity(self, entity_id: str) -> dict:
        if not isinstance(entity_id, str) or entity_id not in ALLOWED_ENTITIES:
            raise SamsungLabError("target_rejected")
        payload = self._request("GET", "/api/states/" + entity_id)
        if not isinstance(payload, dict) or payload.get("entity_id") != entity_id or not isinstance(payload.get("state"), str):
            raise SamsungLabError("invalid_response")
        return payload

    def get_tv_state(self) -> dict:
        return self._entity(TV_ENTITY_ID)

    def check_script(self, request: SamsungRequest) -> None:
        if not isinstance(request, SamsungRequest):
            raise SamsungLabError("invalid_action")
        if self._entity(request.script_entity_id)["state"] not in ("on", "off"):
            raise SamsungLabError("script_not_verified")

    def send_script(self, request: SamsungRequest) -> None:
        if not self._commands_enabled:
            raise SamsungLabError("disabled")
        # Um 404 não causa descoberta/renomeação/fallback para outro script.
        self.check_script(request)
        try:
            payload = self._request("POST", SERVICE_PATH, {"entity_id": request.script_entity_id})
            if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
                raise SamsungLabError("invalid_response")
        except SamsungLabError as error:
            if error.code in ("auth_error", "not_found", "disabled", "target_rejected"):
                raise
            raise SamsungCommandUncertain() from None
