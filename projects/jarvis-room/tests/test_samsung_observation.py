"""Prazo monotônico e HTTP simulados; nenhuma espera real ou equipamento."""

import os
import unittest
from contextlib import redirect_stderr
from io import StringIO
from unittest.mock import patch

from samsung_fakes import FAKE_TOKEN, FakeClock, SamsungHTTP
from jarvis_room.samsung_audit import SamsungAuditRecorder
from jarvis_room.samsung_contract import TV_ENTITY_ID, SamsungLabError, SamsungRequest
from jarvis_room.samsung_control import execute_samsung_manual
from jarvis_room.samsung_credentials import SamsungToken
from jarvis_room.samsung_manual_policy import CONTROL_OPT_IN, authorize_manual
from jarvis_room.samsung_observation import ObservationSummary
from jarvis_room.samsung_rest_client import SamsungRESTClient


class DelayedTV(SamsungHTTP):
    def __init__(self, clock, *, on_at=8, state=None, failure_until=0, read_duration=0, read_error=None, **kwargs):
        super().__init__(**kwargs)
        self.clock, self.on_at, self.state = clock, on_at, state
        self.failure_until, self.read_duration, self.read_error = failure_until, read_duration, read_error
        self.observation_timeouts = []

    def open(self, request, *, timeout):
        observing = request.method == "GET" and request.full_url.endswith(TV_ENTITY_ID) and any(r.method == "POST" for r, _ in self.calls)
        if observing:
            self.observation_timeouts.append(timeout)
            self.clock.sleep(self.read_duration)
            if self.read_error is not None or self.clock.seconds < self.failure_until:
                self.calls.append((request, timeout))
                raise self.read_error or TimeoutError("fake connection failure")
            self.tv_states = [self.state if self.state is not None else ("on" if self.clock.seconds >= self.on_at else "off")]
        return super().open(request, timeout=timeout)


class TestSamsungObservation(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.audit = SamsungAuditRecorder()
        self.enterContext(patch("socket.socket", side_effect=AssertionError("Sem rede real")))
        self.enterContext(patch.dict(os.environ, {CONTROL_OPT_IN: "1"}))
        self.enterContext(redirect_stderr(StringIO()))

    def permit(self):
        with patch("sys.stdin.isatty", return_value=True), patch("sys.stdout.isatty", return_value=True), patch("builtins.input", return_value="LIGAR SAMSUNG"):
            return authorize_manual(SamsungRequest("turn_on"))

    def execute(self, fake, *, timeout=30, interval=2, audit=None):
        client = SamsungRESTClient(token=SamsungToken(FAKE_TOKEN), read_enabled=True, commands_enabled=True, opener=fake)
        return execute_samsung_manual(client, SamsungRequest("turn_on"), self.permit(), audit or self.audit, observation_timeout=timeout, poll_interval=interval, sleep=self.clock.sleep, clock=self.clock.monotonic)

    def assert_one_post(self, fake):
        self.assertEqual(sum(r.method == "POST" for r, _ in fake.calls), 1)

    def test_tv_informa_on_so_depois_de_oito_segundos(self):
        fake = DelayedTV(self.clock, on_at=8)
        result = self.execute(fake)
        self.assertIsNone(result.error_code)
        self.assertTrue(result.command_sent)
        self.assertEqual(result.observation, ObservationSummary(5, 8, 30, "matched"))
        self.assertFalse(result.physical_action_verified)
        self.assert_one_post(fake)

    def test_tv_demorada_apos_vinte_e_seis_segundos(self):
        fake = DelayedTV(self.clock, on_at=26)
        result = self.execute(fake)
        self.assertEqual(result.observation, ObservationSummary(14, 26, 30, "matched"))
        self.assertLess(self.clock.seconds, 30)
        self.assert_one_post(fake)

    def test_encerra_imediatamente_quando_alvo_informado(self):
        fake = DelayedTV(self.clock, on_at=0)
        result = self.execute(fake)
        self.assertEqual(result.observation.query_count, 1)
        self.assertEqual(result.observation.elapsed_seconds, 0)
        self.assertEqual(self.clock.seconds, 0)
        self.assert_one_post(fake)

    def test_timeout_nao_afirma_falha_fisica(self):
        fake = DelayedTV(self.clock, on_at=99)
        result = self.execute(fake)
        self.assertEqual(result.observation, ObservationSummary(15, 30, 30, "timed_out"))
        self.assertEqual(result.error_code, "state_observation_timeout")
        self.assertTrue(result.command_sent)
        self.assertIn("não foi confirmado dentro do prazo", result.report()["observation"]["message"])
        self.assertFalse(result.physical_action_verified)
        self.assert_one_post(fake)

    def test_prazo_personalizado_limita_ultima_consulta_e_sleep(self):
        fake = DelayedTV(self.clock, on_at=99)
        result = self.execute(fake, timeout=11)
        self.assertEqual(result.observation, ObservationSummary(6, 11, 11, "timed_out"))
        self.assertEqual(fake.observation_timeouts, [5, 5, 5, 5, 3, 1])
        self.assert_one_post(fake)

    def test_configuracao_invalida_negada_antes_de_rede(self):
        fake = DelayedTV(self.clock)
        for timeout in (0, -1, 31, True, "30", float("inf"), float("nan")):
            with self.subTest(timeout=timeout), self.assertRaisesRegex(SamsungLabError, "invalid_configuration"):
                self.execute(fake, timeout=timeout)
        for interval in (0, 0.1, 6, True, float("nan")):
            with self.subTest(interval=interval), self.assertRaises(SamsungLabError):
                self.execute(fake, interval=interval)
        self.assertEqual(fake.calls, [])
        self.assertEqual(self.audit.events, ())

    def test_unknown_e_unavailable_nao_sao_sucesso(self):
        for state in ("unknown", "unavailable"):
            self.clock.seconds = 0
            fake = DelayedTV(self.clock, state=state)
            result = self.execute(fake)
            self.assertEqual(result.observation.outcome, "unavailable")
            self.assertEqual(result.observation.elapsed_seconds, 30)
            self.assertEqual(result.observation.query_count, 15)
            self.assertEqual(result.error_code, "unavailable")
            self.assertTrue(result.command_sent)
            self.assertFalse(result.reported_target_match)
            self.assert_one_post(fake)

    def test_indisponibilidade_transitoria_seguida_de_on(self):
        fake = DelayedTV(self.clock, on_at=6, failure_until=6)
        result = self.execute(fake)
        self.assertEqual(result.observation, ObservationSummary(4, 6, 30, "matched"))
        self.assertIsNone(result.error_code)
        self.assert_one_post(fake)

    def test_timeouts_de_get_preservam_envio_e_respeitam_prazo(self):
        fake = DelayedTV(self.clock, read_duration=3, read_error=TimeoutError(FAKE_TOKEN))
        result = self.execute(fake)
        self.assertEqual(result.observation, ObservationSummary(6, 30, 30, "unavailable"))
        self.assertTrue(result.command_sent)
        self.assertEqual(result.error_code, "unavailable")
        self.assert_one_post(fake)

    def test_auth_redirect_e_json_invalido_interrompem_gets(self):
        for code in ("auth_error", "not_found", "redirect_rejected", "invalid_response"):
            self.clock.seconds = 0
            fake = DelayedTV(self.clock, read_error=SamsungLabError(code))
            result = self.execute(fake)
            self.assertEqual(result.error_code, code)
            self.assertEqual(result.observation, ObservationSummary(1, 0, 30, "error"))
            self.assertTrue(result.command_sent)
            self.assert_one_post(fake)

    def test_post_incerto_nao_inicia_observacao_ou_reenvio(self):
        fake = DelayedTV(self.clock, post_error=TimeoutError(FAKE_TOKEN))
        result = self.execute(fake)
        self.assertIsNone(result.command_sent)
        self.assertEqual(result.observation, ObservationSummary(0, 0, 30, "not_started"))
        self.assertEqual(fake.observation_timeouts, [])
        self.assertEqual(result.error_code, "command_outcome_unknown")
        self.assert_one_post(fake)

    def test_cancelamento_da_observacao_preserva_comando_aceito(self):
        fake = DelayedTV(self.clock, read_error=KeyboardInterrupt())
        result = self.execute(fake)
        self.assertEqual(result.error_code, "cancelled")
        self.assertEqual(result.observation.outcome, "error")
        self.assertEqual(result.observation.query_count, 1)
        self.assertTrue(result.command_sent)
        self.assertFalse(result.physical_action_verified)
        self.assert_one_post(fake)

    def test_resposta_apos_prazo_nao_gera_observacao_matched(self):
        fake = DelayedTV(self.clock, on_at=0, read_duration=31)
        result = self.execute(fake)
        self.assertEqual(result.observation.outcome, "timed_out")
        self.assertEqual(result.observation.elapsed_seconds, 31)
        self.assertEqual(result.error_code, "state_observation_timeout")
        self.assertTrue(result.command_sent)
        self.assert_one_post(fake)

    def test_auditoria_e_relatorio_registram_mesmas_metricas(self):
        result = self.execute(DelayedTV(self.clock, on_at=8))
        event = self.audit.events[-1]
        self.assertEqual(event.phase, "observation_finished")
        self.assertEqual(event.observation, result.observation)
        self.assertEqual(result.report()["observation"]["query_count"], 5)
        self.assertEqual(result.report()["observation"]["elapsed_seconds"], 8)
        self.assertFalse(event.physical_action_verified)

    def test_metrica_encerra_no_recebimento_antes_da_gravacao_final(self):
        clock = self.clock
        class SlowAudit(SamsungAuditRecorder):
            def record(self, event):
                if event.phase == "state_reported":
                    clock.sleep(31)
                super().record(event)
        fake = DelayedTV(clock, on_at=0)
        result = self.execute(fake, audit=SlowAudit())
        self.assertEqual(result.observation, ObservationSummary(1, 0, 30, "matched"))
        self.assertIsNone(result.error_code)
        self.assertTrue(result.command_sent)
        self.assert_one_post(fake)

    def test_falha_auditoria_final_nao_apaga_aceite(self):
        class BrokenAudit(SamsungAuditRecorder):
            def record(self, event):
                if event.phase == "observation_finished":
                    raise OSError("private detail")
                super().record(event)
        fake = DelayedTV(self.clock, on_at=0)
        result = self.execute(fake, audit=BrokenAudit())
        self.assertFalse(result.audit_complete)
        self.assertTrue(result.command_sent)
        self.assertEqual(result.error_code, "audit_unavailable")
        self.assert_one_post(fake)

    def test_metricas_validam_tipos_e_coerencia(self):
        for values in ({"query_count": True}, {"elapsed_seconds": float("nan")}, {"timeout_seconds": 31}, {"outcome": "private text"}, {"query_count": 1}, {"query_count": 1, "elapsed_seconds": 31, "timeout_seconds": 30, "outcome": "matched"}):
            with self.subTest(values=values), self.assertRaises(SamsungLabError):
                ObservationSummary(**values)
