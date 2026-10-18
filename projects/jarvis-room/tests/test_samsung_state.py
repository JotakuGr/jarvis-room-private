import json
import unittest
from dataclasses import FrozenInstanceError

from jarvis_room.samsung_contract import TV_ENTITY_ID, SamsungLabError
from jarvis_room.samsung_state import SamsungCommandResult, SamsungReportedState, parse_samsung_state


class TestSamsungState(unittest.TestCase):
    def payload(self, state="on", **kwargs):
        return {"entity_id": TV_ENTITY_ID, "state": state, **kwargs}

    def test_on_off_e_estados_media_player(self):
        for state in ("on", "off", "idle", "playing", "paused", "buffering", "standby"):
            self.assertEqual(parse_samsung_state(self.payload(state)).state, state)

    def test_unknown_unavailable_nao_confirmam(self):
        for state in ("unknown", "unavailable"):
            reported = parse_samsung_state(self.payload(state))
            self.assertFalse(reported.available)
            result = SamsungCommandResult("turn_on", "accepted", after=reported)
            self.assertFalse(result.reported_target_match)
            self.assertFalse(result.physical_action_verified)

    def test_entidade_trocada_e_schema_invalido(self):
        for payload in ([], {}, self.payload(True), self.payload("invented"), self.payload(entity_id="light.sala"), self.payload(extra="private")):
            with self.subTest(payload=payload), self.assertRaises(SamsungLabError):
                parse_samsung_state(payload)

    def test_timestamp_opcional_valido(self):
        self.assertIsNone(parse_samsung_state(self.payload()).observed_at)
        timestamp = "2026-10-18T12:00:00+00:00"
        self.assertEqual(parse_samsung_state(self.payload(last_updated=timestamp)).observed_at, timestamp)
        for value in (123, [], "invalid", "2026-10-18T12:00:00"):
            with self.subTest(value=value), self.assertRaises(SamsungLabError):
                parse_samsung_state(self.payload(last_changed=value))

    def test_atributos_privados_nao_propagados(self):
        state = parse_samsung_state(self.payload(attributes={"private": "do-not-publish"}, context={"token": "do-not-publish"}))
        report = SamsungCommandResult("turn_on", "accepted", after=state).report()
        self.assertNotIn("do-not-publish", json.dumps(report))
        self.assertNotIn("attributes", report)

    def test_confirmacao_fisica_nao_elevavel(self):
        for factory in (lambda: SamsungReportedState("on", physical_action_verified=True), lambda: SamsungCommandResult("turn_on", physical_action_verified=True)):
            with self.assertRaises(TypeError):
                factory()
        result = SamsungCommandResult("turn_on")
        with self.assertRaises(FrozenInstanceError):
            result.physical_action_verified = True

    def test_envio_estado_e_causalidade_sao_distintos(self):
        on = SamsungReportedState("on")
        result = SamsungCommandResult("turn_on", "accepted", on, on)
        self.assertTrue(result.command_sent)
        self.assertTrue(result.reported_target_match)
        self.assertFalse(result.report()["state_transition_observed"])
        self.assertFalse(result.physical_action_verified)
        self.assertFalse(SamsungCommandResult("turn_on", "accepted", after=SamsungReportedState("standby")).reported_target_match)

    def test_falha_incerta_e_rejeicao(self):
        self.assertIsNone(SamsungCommandResult("turn_off", "unknown", error_code="command_outcome_unknown").command_sent)
        for delivery in ("rejected", "not_attempted"):
            self.assertFalse(SamsungCommandResult("turn_on", delivery).command_sent)
        for kwargs in ({"delivery": "invented"}, {"before": {}}, {"error_code": "private detail"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(SamsungLabError):
                SamsungCommandResult("turn_on", **kwargs)
