"""Transportes exclusivamente em memória; nenhum dispositivo é acessado."""

import io
import json

from jarvis_room.samsung_contract import TV_ENTITY_ID

FAKE_TOKEN = "samsung-unit-test-not-a-credential"


class SamsungHTTP:
    def __init__(self, *, tv_states=("off", "on"), status=200, raw=None, error=None, redirect=None, script_status=200, post_status=200, post_error=None):
        self.tv_states = list(tv_states)
        self.status, self.raw, self.error = status, raw, error
        self.redirect, self.script_status = redirect, script_status
        self.post_status, self.post_error = post_status, post_error
        self.calls = []

    def open(self, request, *, timeout):
        self.calls.append((request, timeout))
        if self.error is not None:
            raise self.error
        status = self.status
        if request.method == "POST":
            if self.post_error is not None:
                raise self.post_error
            payload = []
            status = self.post_status
        else:
            entity = request.full_url.rsplit("/", 1)[-1]
            if entity == TV_ENTITY_ID:
                state = self.tv_states[0]
                if len(self.tv_states) > 1:
                    self.tv_states.pop(0)
            else:
                state, status = "off", self.script_status
            payload = {"entity_id": entity, "state": state}
        response = io.BytesIO(json.dumps(payload).encode() if self.raw is None else self.raw)
        response.status = status
        response.geturl = lambda: self.redirect or request.full_url
        return response
