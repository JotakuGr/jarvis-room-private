"""Orquestração manual exclusiva Samsung, sem gateway genérico ou LLM."""

import time
import uuid

from .samsung_audit import SamsungAuditEvent, SamsungAuditRecorder
from .samsung_contract import SamsungCommandUncertain, SamsungLabError, SamsungRequest
from .samsung_manual_policy import consume_manual_permit
from .samsung_observation import ObservationSummary, ObservationWindow
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
    recorder: SamsungAuditRecorder, *, observation_timeout: float = 30.0,
    poll_interval: float = 2.0, sleep=None, clock=None,
) -> SamsungCommandResult:
    if not isinstance(client, SamsungRESTClient) or not isinstance(request, SamsungRequest):
        raise SamsungLabError("invalid_configuration")
    if not isinstance(recorder, SamsungAuditRecorder):
        raise SamsungLabError("audit_unavailable")
    window = ObservationWindow(observation_timeout, poll_interval)
    consume_manual_permit(permit, request)
    request_id = uuid.uuid4().hex
    before = after = None
    delivery, error_code, audit_complete = "not_attempted", None, True
    post_started = False
    sleep = time.sleep if sleep is None else sleep
    clock = time.monotonic if clock is None else clock
    observation_started = None
    observation_finished = None
    query_count, observation_outcome = 0, "not_started"
    saw_available_state = False

    def record(phase, *, state=None, error=None, observation=None):
        nonlocal audit_complete
        try:
            recorder.record(SamsungAuditEvent(request_id, request.action, phase, state, error, observation))
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
        observation_started = clock()
        deadline = observation_started + window.timeout_seconds
        observation_outcome = "error"
        while clock() < deadline:
            remaining = deadline - clock()
            if remaining <= 0:
                break
            query_count += 1
            try:
                after = parse_samsung_state(client.get_tv_state(timeout=remaining))
            except SamsungLabError as error:
                # Apenas indisponibilidade transitória permite novos GETs.
                # Autenticação, redirect e JSON inválido encerram a observação.
                if error.code != "unavailable":
                    raise
            else:
                received_at = clock()
                saw_available_state = saw_available_state or after.available
                record("state_reported", state=after.state)
                if received_at <= deadline and SamsungCommandResult(request.action, delivery, before, after).reported_target_match:
                    observation_outcome = "matched"
                    observation_finished = received_at
                    break
            remaining = deadline - clock()
            if remaining > 0:
                sleep(min(window.interval_seconds, remaining))
        if observation_outcome != "matched":
            observation_finished = clock()
            observation_outcome = "timed_out" if saw_available_state else "unavailable"
            error_code = "state_observation_timeout" if saw_available_state else "unavailable"
    except SamsungCommandUncertain:
        delivery, error_code = "unknown", "command_outcome_unknown"
        try:
            record("post_uncertain", error=error_code)
        except SamsungLabError:
            pass
    except (Exception, KeyboardInterrupt) as error:
        if observation_started is not None:
            observation_finished = clock()
        error_code = error.code if isinstance(error, SamsungLabError) else ("cancelled" if isinstance(error, KeyboardInterrupt) else "operation_failed")
        if post_started and delivery != "accepted":
            delivery = "rejected" if error_code in ("auth_error", "not_found", "disabled", "target_rejected", "script_not_verified") else "unknown"
        try:
            record("failed", error=error_code)
        except SamsungLabError:
            pass
    elapsed = 0.0 if observation_started is None else max(0.0, observation_finished - observation_started)
    observation = ObservationSummary(query_count, elapsed, window.timeout_seconds, observation_outcome)
    if post_started:
        try:
            record("observation_finished", error=error_code, observation=observation)
        except SamsungLabError:
            error_code = "audit_unavailable"
    return SamsungCommandResult(request.action, delivery, before, after, error_code, audit_complete, observation)
