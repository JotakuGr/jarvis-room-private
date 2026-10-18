"""Orquestração manual exclusiva Samsung, sem gateway genérico ou LLM."""

import math
import time
import uuid

from .samsung_audit import SamsungAuditEvent, SamsungAuditRecorder
from .samsung_contract import SamsungCommandUncertain, SamsungLabError, SamsungRequest
from .samsung_manual_policy import consume_manual_permit
from .samsung_rest_client import SamsungRESTClient
from .samsung_state import SamsungCommandResult, parse_samsung_state


def read_samsung_status(client: SamsungRESTClient) -> dict:
    state = parse_samsung_state(client.get_tv_state())
    for action in ("turn_on", "turn_off"):
        client.check_script(SamsungRequest(action))
    return {
        "mode": "read_only_samsung_lab", "state_reported": state.state,
        "reported_at": state.observed_at, "scripts_present": True,
        "script_contents_verified": False, "physical_action_verified": False,
    }


def execute_samsung_manual(
    client: SamsungRESTClient, request: SamsungRequest, permit,
    recorder: SamsungAuditRecorder, *, poll_attempts: int = 3,
    poll_interval: float = 2.0, sleep=None,
) -> SamsungCommandResult:
    if not isinstance(client, SamsungRESTClient) or not isinstance(request, SamsungRequest):
        raise SamsungLabError("invalid_configuration")
    if not isinstance(recorder, SamsungAuditRecorder):
        raise SamsungLabError("audit_unavailable")
    if type(poll_attempts) is not int or not 1 <= poll_attempts <= 3 or type(poll_interval) not in (int, float) or not math.isfinite(poll_interval) or not 0 <= poll_interval <= 2:
        raise SamsungLabError("invalid_configuration")
    consume_manual_permit(permit, request)
    request_id = uuid.uuid4().hex
    before = after = None
    delivery, error_code, audit_complete = "not_attempted", None, True
    post_started = False
    sleep = time.sleep if sleep is None else sleep

    def record(phase, *, state=None, error=None):
        nonlocal audit_complete
        try:
            recorder.record(SamsungAuditEvent(request_id, request.action, phase, state, error))
        except Exception:
            audit_complete = False
            raise SamsungLabError("audit_unavailable") from None

    try:
        record("authorized")
        # Verifica o ID exato; script.state=off só significa que não está rodando.
        client.check_script(request)
        before = parse_samsung_state(client.get_tv_state())
        record("post_attempted")
        post_started = True
        client.send_script(request)
        delivery = "accepted"
        record("post_accepted")
        for index in range(poll_attempts):
            if index:
                sleep(poll_interval)
            after = parse_samsung_state(client.get_tv_state())
            record("state_reported", state=after.state)
            if SamsungCommandResult(request.action, delivery, before, after).reported_target_match:
                break
        else:
            error_code = "state_not_matched" if after.available else "unavailable"
    except SamsungCommandUncertain:
        delivery, error_code = "unknown", "command_outcome_unknown"
        try:
            record("post_uncertain", error=error_code)
        except SamsungLabError:
            pass
    except Exception as error:
        error_code = error.code if isinstance(error, SamsungLabError) else "operation_failed"
        if post_started and delivery != "accepted":
            delivery = "rejected" if error_code in ("auth_error", "not_found", "disabled", "target_rejected", "script_not_verified") else "unknown"
        try:
            record("failed", error=error_code)
        except SamsungLabError:
            pass
    return SamsungCommandResult(request.action, delivery, before, after, error_code, audit_complete)
