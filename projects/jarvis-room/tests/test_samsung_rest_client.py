import json
import ssl
import unittest
import urllib.error
from unittest.mock import patch

from samsung_fakes import FAKE_TOKEN, SamsungHTTP
from jarvis_room.samsung_contract import BASE_URL, OFF_SCRIPT, ON_SCRIPT, TV_ENTITY_ID, SamsungCommandUncertain, SamsungLabError, SamsungRequest
from jarvis_room.samsung_credentials import SamsungToken
from jarvis_room.samsung_rest_client import SERVICE_PATH, SamsungRESTClient, _RejectRedirect


class TestSamsungRESTClient(unittest.TestCase):
    def client(self, fake, **kwargs):
        return SamsungRESTClient(token=SamsungToken(FAKE_TOKEN), opener=fake, **kwargs)

    def test_desabilitado_sem_rede(self):
        fake = SamsungHTTP()
        client = self.client(fake)
        with self.assertRaisesRegex(SamsungLabError, "disabled"):
            client.get_tv_state()
        with self.assertRaisesRegex(SamsungLabError, "disabled"):
            client.send_script(SamsungRequest("turn_on"))
        self.assertEqual(fake.calls, [])

    def test_get_fixo_bearer_e_timeout(self):
        fake = SamsungHTTP()
        self.client(fake, read_enabled=True).get_tv_state()
        request, timeout = fake.calls[0]
        self.assertEqual(request.full_url, BASE_URL + "/api/states/" + TV_ENTITY_ID)
        self.assertEqual(request.method, "GET")
        self.assertEqual(request.get_header("Authorization"), "Bearer " + FAKE_TOKEN)
        self.assertNotIn(FAKE_TOKEN, request.full_url)
        self.assertEqual(timeout, 5)

    def test_post_apenas_dois_scripts(self):
        for action, script in (("turn_on", ON_SCRIPT), ("turn_off", OFF_SCRIPT)):
            fake = SamsungHTTP()
            self.client(fake, read_enabled=True, commands_enabled=True).send_script(SamsungRequest(action))
            self.assertEqual(len(fake.calls), 2)
            request = fake.calls[-1][0]
            self.assertEqual(request.full_url, BASE_URL + SERVICE_PATH)
            self.assertEqual(request.method, "POST")
            self.assertEqual(json.loads(request.data), {"entity_id": script})

    def test_read_enabled_nao_autoriza_post(self):
        fake = SamsungHTTP()
        with self.assertRaisesRegex(SamsungLabError, "disabled"):
            self.client(fake, read_enabled=True).send_script(SamsungRequest("turn_on"))
        self.assertEqual(fake.calls, [])

    def test_url_remota_troca_de_porta_e_userinfo_rejeitados(self):
        for url in ("http://192.0.2.1:8123", "https://example.com", "http://127.0.0.1:8123", "http://secret@127.0.0.1:18123", "http://127.0.0.1:18123/"):
            with self.subTest(url=url), self.assertRaisesRegex(SamsungLabError, "target_rejected"):
                self.client(SamsungHTTP(), base_url=url)

    def test_redirect_rejeitado_sem_segunda_requisicao(self):
        fake = SamsungHTTP(redirect="https://example.com")
        with self.assertRaisesRegex(SamsungLabError, "redirect_rejected"):
            self.client(fake, read_enabled=True).get_tv_state()
        self.assertEqual(len(fake.calls), 1)
        with self.assertRaisesRegex(SamsungLabError, "redirect_rejected"):
            _RejectRedirect().redirect_request(None, None, 302, None, None, "https://example.com")

    def test_erros_sanitizados_auth_notfound_timeout_tls(self):
        for status, code in ((401, "auth_error"), (403, "auth_error"), (404, "not_found"), (503, "unavailable"), (302, "redirect_rejected")):
            with self.subTest(status=status), self.assertRaisesRegex(SamsungLabError, "^" + code + "$"):
                self.client(SamsungHTTP(status=status), read_enabled=True).get_tv_state()
        for error, code in ((TimeoutError(FAKE_TOKEN), "unavailable"), (ssl.SSLCertVerificationError(FAKE_TOKEN), "tls_error"), (urllib.error.HTTPError("private", 401, FAKE_TOKEN, {}, None), "auth_error")):
            with self.subTest(code=code), self.assertRaisesRegex(SamsungLabError, "^" + code + "$"):
                self.client(SamsungHTTP(error=error), read_enabled=True).get_tv_state()

    def test_json_duplicado_invalido_oversize_e_entidade_trocada(self):
        for raw in (b"{}", b"[]", b"{", b"NaN", b' {"state":"on","state":"off"}', b"x" * 32769, json.dumps({"entity_id": "light.sala", "state": "on"}).encode()):
            with self.subTest(raw=raw[:20]), self.assertRaisesRegex(SamsungLabError, "invalid_response"):
                self.client(SamsungHTTP(raw=raw), read_enabled=True).get_tv_state()

    def test_script_renomeado_404_nao_envia_post(self):
        fake = SamsungHTTP(script_status=404)
        with self.assertRaisesRegex(SamsungLabError, "not_found"):
            self.client(fake, read_enabled=True, commands_enabled=True).send_script(SamsungRequest("turn_on"))
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(fake.calls[0][0].full_url, BASE_URL + "/api/states/" + ON_SCRIPT)

    def test_comandos_genericos_negados(self):
        fake = SamsungHTTP()
        client = self.client(fake, read_enabled=True, commands_enabled=True)
        for method, path, body in (("DELETE", SERVICE_PATH, None), ("POST", SERVICE_PATH, {"entity_id": TV_ENTITY_ID}), ("POST", "/api/states/" + TV_ENTITY_ID, {}), ("GET", "/api/states/https://example.com", None), ("POST", SERVICE_PATH, {"entity_id": ON_SCRIPT, "variables": {}})):
            with self.subTest(method=method, path=path), self.assertRaises(SamsungLabError):
                client._request(method, path, body)
        self.assertEqual(fake.calls, [])

    def test_post_incerto_nao_repetido(self):
        fake = SamsungHTTP(post_error=TimeoutError(FAKE_TOKEN))
        with self.assertRaises(SamsungCommandUncertain):
            self.client(fake, read_enabled=True, commands_enabled=True).send_script(SamsungRequest("turn_on"))
        self.assertEqual(sum(r.method == "POST" for r, _ in fake.calls), 1)

    def test_limites_e_proxy_sem_configuracao_externa(self):
        for options in ({"timeout": True}, {"timeout": 0}, {"timeout": float("nan")}, {"max_response_bytes": True}, {"max_response_bytes": 999999}, {"read_enabled": 1}, {"commands_enabled": True}):
            with self.subTest(options=options), self.assertRaises(SamsungLabError):
                self.client(SamsungHTTP(), **options)
        with patch("jarvis_room.samsung_rest_client.urllib.request.build_opener", return_value=SamsungHTTP()) as factory:
            SamsungRESTClient(token=SamsungToken(FAKE_TOKEN), read_enabled=True).get_tv_state()
            self.assertEqual(factory.call_args.args[0].proxies, {})
