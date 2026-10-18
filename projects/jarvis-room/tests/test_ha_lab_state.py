"""Estados informativos sem recibo ou confirmação física."""

import json
import unittest
from dataclasses import FrozenInstanceError

from jarvis_room.ha_lab_readonly_client import DEFAULT_ENTITY_ID
from jarvis_room.ha_lab_state import HALabState, HALabStateError, parse_lab_state, state_report


class TestHALabState(unittest.TestCase):
    def parse(self, state, **extra):
        return parse_lab_state({"entity_id": DEFAULT_ENTITY_ID, "state": state, **extra}, DEFAULT_ENTITY_ID)

    def test_on(self):
        state = self.parse("on", last_updated="2026-10-17T01:02:03Z")
        self.assertTrue(state.available)
        self.assertEqual(state.state, "on")
        self.assertEqual(state.observed_at, "2026-10-17T01:02:03Z")
        self.assertFalse(state.physical_action_verified)

    def test_off(self):
        state = self.parse("off")
        self.assertTrue(state.available)
        self.assertIsNone(state.observed_at)
        self.assertEqual(state.source, "home_assistant_lab")

    def test_unknown(self):
        self.assertFalse(self.parse("unknown").available)
        self.assertFalse(self.parse("unknown").physical_action_verified)

    def test_unavailable(self):
        self.assertFalse(self.parse("unavailable").available)
        self.assertFalse(self.parse("unavailable").physical_action_verified)

    def test_troca_entidade(self):
        for entity in ("light.sala", "input_boolean.jarvis_lab_other", None):
            with self.assertRaises(HALabStateError):
                parse_lab_state({"entity_id": entity, "state": "on"}, DEFAULT_ENTITY_ID)

    def test_schema_invalido(self):
        for payload in (None, [], {}, {"entity_id": DEFAULT_ENTITY_ID}, {"entity_id": DEFAULT_ENTITY_ID, "state": "on", "extra": True}):
            with self.assertRaises(HALabStateError):
                parse_lab_state(payload, DEFAULT_ENTITY_ID)
        for state in (True, [], 1, "running", "ON"):
            with self.assertRaises(HALabStateError):
                self.parse(state)
        for timestamp in (True, [], "ontem", "2026-10-17", "2026-99-01T00:00:00Z"):
            with self.assertRaises(HALabStateError):
                self.parse("on", last_updated=timestamp)

    def test_atributos_sensiveis_nao_propagados(self):
        report = state_report(self.parse("on", attributes={"secret": "private-test-value"}, context={"user_id": "private-test-user"}))
        self.assertNotIn("private-test", json.dumps(report))
        self.assertNotIn("attributes", report)
        self.assertNotIn("context", report)
        self.assertEqual(set(report), {"entity_id", "state", "observed_at", "source", "physical_action_verified", "available"})

    def test_nao_eleva_confirmacao(self):
        state = self.parse("on")
        for field in ("physical_action_verified", "source"):
            with self.assertRaises(FrozenInstanceError):
                setattr(state, field, True)
        with self.assertRaises(TypeError):
            HALabState(DEFAULT_ENTITY_ID, "on", physical_action_verified=True)
        with self.assertRaises(TypeError):
            HALabState(DEFAULT_ENTITY_ID, "on", source="home_assistant")
