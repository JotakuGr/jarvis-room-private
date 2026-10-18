"""GET simulado, sem Home Assistant e sem credenciais reais."""

import inspect
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from unittest.mock import patch

from ha_lab_http_fakes import FakeHTTP
from jarvis_room.ha_lab_readonly_client import (
    BASE_URL, DEFAULT_ENTITY_ID, HALabAuthError, HALabInvalidResponse,
    HALabNotFound, HALabReadDisabled, HALabReadError, HALabReadOnlyClient,
    HALabUnavailable, _RejectRedirect,
)

TEST_TOKEN = "unit-test-not-a-credential"


class TestHALabReadOnlyClient(unittest.TestCase):
    def test_desabilitado_sem_rede(self):
        fake = FakeHTTP()
        with patch("socket.socket", side_effect=AssertionError("Sem rede")):
            client = HALabReadOnlyClient(token=TEST_TOKEN, opener=fake)
            with self.assertRaises(HALabReadDisabled):
                client.ping()
            with self.assertRaises(HALabReadDisabled):
                client.get_entity(DEFAULT_ENTITY_ID)
        self.assertEqual(fake.calls, [])

    def test_get_permitido_com_fake(self):
        fake = FakeHTTP()
        client = HALabReadOnlyClient(token=TEST_TOKEN, enabled=True, opener=fake)
        self.assertTrue(client.ping())
        fake.payload = {"entity_id": DEFAULT_ENTITY_ID, "state": "on"}
        self.assertEqual(client.get_entity(DEFAULT_ENTITY_ID)["state"], "on")
        self.assertEqual(len(fake.calls), 2)
        for request, timeout in fake.calls:
            self.assertEqual(request.method, "GET")
            self.assertTrue(request.full_url.startswith(BASE_URL + "/api/"))
            self.assertEqual(request.get_header("Authorization"), "Bearer " + TEST_TOKEN)
            self.assertNotIn(TEST_TOKEN, request.full_url)
            self.assertLessEqual(timeout, 10)

    def test_post_inexistente(self):
        for method in ("post", "request", "call_service", "perform_and_verify", "set_state"):
            self.assertFalse(hasattr(HALabReadOnlyClient, method))
        self.assertNotIn('method="POST"', inspect.getsource(HALabReadOnlyClient))

    def test_alvo_nao_local_rejeitado(self):
        for url in ("http://localhost:18123", "http://127.0.0.1:18123@invalid.example", "https://invalid.example", BASE_URL + "/"):
            with self.assertRaises(HALabReadError):
                HALabReadOnlyClient(token=TEST_TOKEN, enabled=True, base_url=url)
        for entity in ("light.sala", "switch.sala", "http://invalid.example", "input_boolean.real"):
            with self.assertRaises(HALabReadError):
                HALabReadOnlyClient(token=TEST_TOKEN, entity_id=entity)

    def test_redirect_rejeitado(self):
        for fake in (FakeHTTP(status=302), FakeHTTP(redirect_url="https://invalid.example")):
            with self.assertRaisesRegex(HALabReadError, "redirect_rejected"):
                HALabReadOnlyClient(token=TEST_TOKEN, enabled=True, opener=fake).ping()
            self.assertEqual(len(fake.calls), 1)
        with self.assertRaises(HALabReadError):
            _RejectRedirect().redirect_request(None, None, 302, "", {}, "https://invalid.example")

    def test_token_nao_vaza_em_erro_log(self):
        fake = FakeHTTP(error=RuntimeError(TEST_TOKEN))
        output = StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            with self.assertRaises(HALabReadError) as error:
                HALabReadOnlyClient(token=TEST_TOKEN, enabled=True, opener=fake).ping()
        self.assertNotIn(TEST_TOKEN, str(error.exception))
        self.assertEqual(output.getvalue(), "")
        self.assertIsNone(error.exception.__cause__)
        self.assertNotIn(TEST_TOKEN, repr(HALabReadOnlyClient(token=TEST_TOKEN)))

    def test_401_403_timeout_not_found(self):
        for status, cls, code in ((401, HALabAuthError, "auth_error"), (403, HALabAuthError, "auth_error"), (404, HALabNotFound, "not_found"), (503, HALabUnavailable, "unavailable")):
            for fake in (FakeHTTP(status=status), FakeHTTP(error=urllib.error.HTTPError(BASE_URL, status, TEST_TOKEN, {}, None))):
                with self.subTest(status=status), self.assertRaisesRegex(cls, code):
                    HALabReadOnlyClient(token=TEST_TOKEN, enabled=True, opener=fake).ping()
        for exc in (TimeoutError(TEST_TOKEN), ConnectionError(TEST_TOKEN), urllib.error.URLError(TEST_TOKEN)):
            with self.assertRaisesRegex(HALabUnavailable, "unavailable"):
                HALabReadOnlyClient(token=TEST_TOKEN, enabled=True, opener=FakeHTTP(error=exc)).ping()

    def test_json_entidade_e_limite(self):
        for raw in (b"{", b"\xff", b"[]", b'{"message":"a","message":"b"}', b'{"x":NaN}', b" " * 65):
            with self.subTest(raw=raw), self.assertRaises(HALabInvalidResponse):
                HALabReadOnlyClient(token=TEST_TOKEN, enabled=True, opener=FakeHTTP(raw=raw), max_response_bytes=64).ping()
        fake = FakeHTTP({"entity_id": "input_boolean.outro", "state": "on"})
        client = HALabReadOnlyClient(token=TEST_TOKEN, enabled=True, opener=fake)
        for entity in ("light.sala", [], None, DEFAULT_ENTITY_ID + "/../x"):
            with self.assertRaises(HALabReadError):
                client.get_entity(entity)
        self.assertEqual(fake.calls, [])
        with self.assertRaises(HALabInvalidResponse):
            client.get_entity(DEFAULT_ENTITY_ID)
        for kwargs in ({"timeout": True}, {"timeout": 100}, {"timeout": float("inf")}, {"max_response_bytes": True}):
            with self.assertRaises(HALabReadError):
                HALabReadOnlyClient(token=TEST_TOKEN, **kwargs)
