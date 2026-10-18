"""Cliente exclusivamente GET para loopback; desabilitado por padrão.

O token do HA pode ter privilégios amplos. A restrição GET é deste cliente.
O opener injetável destina-se aos testes, não a destinos configuráveis.
"""

import json
import math
import re
import urllib.error
import urllib.parse
import urllib.request

from .ha_lab_manifest import BASE_URL

DEFAULT_ENTITY_ID = "input_boolean.jarvis_lab_light"


class HALabReadError(RuntimeError):
    pass


class HALabReadDisabled(HALabReadError):
    pass


class HALabAuthError(HALabReadError):
    pass


class HALabUnavailable(HALabReadError):
    pass


class HALabNotFound(HALabReadError):
    pass


class HALabInvalidResponse(HALabReadError):
    pass


def valid_lab_entity_id(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(
        r"input_boolean\.jarvis_lab_[a-z0-9_]+", value
    ) is not None


class _RejectRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HALabReadError("redirect_rejected")


def _status_error(status: int) -> None:
    if status in (401, 403):
        raise HALabAuthError("auth_error")
    if status == 404:
        raise HALabNotFound("not_found")
    if 300 <= status < 400:
        raise HALabReadError("redirect_rejected")
    raise HALabUnavailable("unavailable")


def _unique(pairs):
    data = {}
    for key, value in pairs:
        if key in data:
            raise ValueError("duplicate")
        data[key] = value
    return data


def _reject_constant(_):
    raise ValueError("non_finite")


class HALabReadOnlyClient:
    def __init__(
        self, *, token: str, enabled: bool = False,
        base_url: str = BASE_URL, entity_id: str = DEFAULT_ENTITY_ID,
        timeout: float = 3.0, max_response_bytes: int = 16384, opener=None,
    ):
        if base_url != BASE_URL or not valid_lab_entity_id(entity_id):
            raise HALabReadError("target_rejected")
        if type(enabled) is not bool:
            raise HALabReadError("invalid_configuration")
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0.1 <= timeout <= 10:
            raise HALabReadError("invalid_configuration")
        if type(max_response_bytes) is not int or not 1 <= max_response_bytes <= 65536:
            raise HALabReadError("invalid_configuration")
        if not isinstance(token, str) or not token.strip() or len(token) > 4096 or any(char.isspace() for char in token):
            raise HALabAuthError("auth_error")
        self._token = token
        self._enabled = enabled
        self._entity_id = entity_id
        self._timeout = timeout
        self._limit = max_response_bytes
        self._opener = opener

    def _get_json(self, path: str) -> dict:
        if not self._enabled:
            raise HALabReadDisabled("read_disabled")
        allowed = ("/api/", "/api/states/" + urllib.parse.quote(self._entity_id, safe="."))
        if path not in allowed:
            raise HALabReadError("target_rejected")
        url = BASE_URL + path
        try:
            opener = self._opener
            if opener is None:
                opener = urllib.request.build_opener(
                    urllib.request.ProxyHandler({}), _RejectRedirect()
                )
            request = urllib.request.Request(
                url, headers={"Authorization": "Bearer " + self._token, "Accept": "application/json"},
                method="GET",
            )
            with opener.open(request, timeout=self._timeout) as response:
                if response.geturl() != url:
                    raise HALabReadError("redirect_rejected")
                if response.status != 200:
                    _status_error(response.status)
                raw = response.read(self._limit + 1)
            if len(raw) > self._limit:
                raise HALabInvalidResponse("invalid_response")
            try:
                data = json.loads(
                    raw.decode("utf-8"), object_pairs_hook=_unique,
                    parse_constant=_reject_constant,
                )
            except (ValueError, RecursionError):
                raise HALabInvalidResponse("invalid_response") from None
            if not isinstance(data, dict):
                raise HALabInvalidResponse("invalid_response")
            return data
        except HALabReadError:
            raise
        except urllib.error.HTTPError as exc:
            try:
                _status_error(exc.code)
            except HALabReadError as error:
                raise error from None
        except Exception:
            raise HALabUnavailable("unavailable") from None

    def ping(self) -> bool:
        if self._get_json("/api/").get("message") != "API running.":
            raise HALabInvalidResponse("invalid_response")
        return True

    def get_entity(self, entity_id: str) -> dict:
        if not isinstance(entity_id, str) or entity_id != self._entity_id:
            raise HALabReadError("target_rejected")
        data = self._get_json("/api/states/" + urllib.parse.quote(entity_id, safe="."))
        if data.get("entity_id") != entity_id or not isinstance(data.get("state"), str):
            raise HALabInvalidResponse("invalid_response")
        return data
