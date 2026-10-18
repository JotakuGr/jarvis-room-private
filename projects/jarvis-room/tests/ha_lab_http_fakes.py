"""HTTP exclusivamente simulado em memória; credenciais dos testes são fictícias."""

import io
import json


class FakeHTTP:
    def __init__(self, payload=None, *, status=200, raw=None, error=None, redirect_url=None):
        self.payload = {"message": "API running."} if payload is None else payload
        self.status = status
        self.raw = raw
        self.error = error
        self.redirect_url = redirect_url
        self.calls = []

    def open(self, request, *, timeout):
        self.calls.append((request, timeout))
        if self.error is not None:
            raise self.error
        raw = json.dumps(self.payload).encode() if self.raw is None else self.raw
        response = io.BytesIO(raw)
        response.status = self.status
        response.geturl = lambda: self.redirect_url or request.full_url
        return response
