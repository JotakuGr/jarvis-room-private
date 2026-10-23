"""SSE/Unix/HA simulados: sem rede, equipamento, áudio ou inferência reais."""

import io
import json
import os
import queue
import struct
import tempfile
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock, patch

from jarvis_room.presentation_contract import (
    LAB_ENTITY,
    strict_json,
    validate_event,
    validate_payload,
)
from jarvis_room.presentation_health import HealthObserver, ha_client_from_file
from jarvis_room.presentation_hub import EventHub
from jarvis_room.presentation_ipc import (
    PresentationPublisher,
    private_directory,
    verify_peer,
)
from jarvis_room.presentation_server import (
    EventHandler,
    ProducerHandler,
    allowed_request,
    sse_frame,
)
from jarvis_room.voice_contract import VoiceState
from jarvis_room.voice_router import VoiceReply
from voice_fakes import Clock, OfflineVoiceTest

SID = "11111111-1111-4111-8111-111111111111"


class PresentationContractTests(OfflineVoiceTest):
    def test_six_real_voice_states_are_validated(self):
        for state in VoiceState:
            validate_payload("voice_state", {"state": state.value})

    def test_invalid_payloads_never_become_events(self):
        for kind, payload in (
            ("execute", {"action": "turn_on"}),
            ("voice_state", {"state": "EXECUTING"}),
            ("voice_state", {"state": "IDLE", "token": "private"}),
            ("voice_amplitude", {"amplitude": True}),
            ("voice_amplitude", {"amplitude": float("nan")}),
            ("voice_amplitude", {"amplitude": 1.1}),
            ("service_status", {"id": "secret", "status": "connected", "detail": "x"}),
            ("service_status", {"id": "tts", "status": "connected", "detail": "a\nb"}),
            ("conversation", {"question": "x" * 257, "answer": "x"}),
            (
                "lab_observation",
                {"entityId": "switch.tv", "status": "connected", "state": "on"},
            ),
            ([], {}),
        ):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                validate_payload(kind, payload)

    def test_planned_equipment_cannot_be_promoted(self):
        with self.assertRaises(ValueError):
            validate_payload(
                "device_status",
                {"id": "hikvision_board", "status": "connected", "state": "on"},
            )
        validate_payload(
            "device_status",
            {"id": "hikvision_board", "status": "planned", "state": None},
        )

    def test_no_fabricated_temperature_contract(self):
        with self.assertRaises(ValueError):
            validate_payload("sensor_reading", {"kind": "temperature", "value": 22})

    def test_raw_audio_and_credentials_are_not_payload_fields(self):
        for field in ("audio", "token", "entity_id", "tools"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_payload("voice_amplitude", {"amplitude": 0.4, field: "x"})

    def test_envelope_rejects_unknown_fields_and_unsafe_numbers(self):
        event = EventHub().publish("voice_state", {"state": "IDLE"})
        validate_event(event)
        for changes in (
            {"version": 1},
            {"sequence": True},
            {"sequence": 2**53},
            {"sessionId": "other"},
            {"observedAt": "yesterday"},
            {"token": "x"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_event({**event, **changes})

    def test_json_limits_duplicates_and_nonfinite_rejected(self):
        for raw in (b"[]", b'{"x":1,"x":2}', b'{"x":NaN}', b"x" * 8193):
            with self.subTest(raw=raw[:30]), self.assertRaises(ValueError):
                strict_json(raw)


class PresentationHubTests(OfflineVoiceTest):
    def setUp(self):
        super().setUp()
        self.clock = Clock()
        self.hub = EventHub(clock=self.clock, now=lambda: "2026-10-21T21:00:00Z")

    def test_two_monitors_receive_same_session_and_increasing_sequences(self):
        first, second = self.hub.subscribe(), self.hub.subscribe()
        initial = first.get_nowait()
        self.assertEqual(initial, second.get_nowait())
        for state in VoiceState:
            event = self.hub.publish("voice_state", {"state": state.value})
            self.assertEqual(first.get_nowait(), event)
            self.assertEqual(second.get_nowait(), event)
            self.assertGreater(event["sequence"], initial["sequence"])

    def test_reconnect_replays_latest_snapshot_in_order(self):
        self.hub.publish("voice_state", {"state": "THINKING"})
        self.hub.publish("voice_state", {"state": "RESPONDING"})
        client = self.hub.subscribe()
        events = []
        while not client.empty():
            events.append(client.get_nowait())
        self.assertEqual([e["type"] for e in events], ["connection", "voice_state"])
        self.assertEqual(events[-1]["payload"]["state"], "RESPONDING")

    def test_amplitude_requires_actual_playback_status(self):
        with self.assertRaisesRegex(ValueError, "amplitude_without_playback"):
            self.hub.publish("voice_amplitude", {"amplitude": 0.5})
        self.hub.publish("playback_status", {"state": "playing"})
        self.hub.publish("voice_amplitude", {"amplitude": 0.5})

    def test_playback_watchdog_zeroes_energy(self):
        self.hub.publish("playback_status", {"state": "playing"})
        self.hub.publish("voice_amplitude", {"amplitude": 0.9})
        self.clock.wait(1)
        self.hub.tick()
        self.assertFalse(self.hub.playing)
        self.assertEqual(
            self.hub.cache[("voice_amplitude", None)]["payload"], {"amplitude": 0}
        )

    def test_missing_producer_heartbeat_invalidates_old_session(self):
        self.hub.attach(SID)
        previous = self.hub.session_id
        self.hub.ingest("voice_state", {"state": "LISTENING"})
        self.clock.wait(7)
        self.hub.tick()
        self.assertFalse(self.hub.producer)
        self.assertNotEqual(previous, self.hub.session_id)
        self.assertEqual(
            self.hub.cache[("voice_state", None)]["payload"]["state"], "IDLE"
        )

    def test_only_one_voice_producer_and_observations_restricted(self):
        self.hub.attach(SID)
        with self.assertRaises(ValueError):
            self.hub.attach(SID)
        for kind, payload in (
            ("connection", {"state": "connected"}),
            (
                "device_status",
                {"id": "samsung_lab_tv", "status": "connected", "state": "on"},
            ),
            (
                "service_status",
                {"id": "home_assistant", "status": "connected", "detail": "fake"},
            ),
        ):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.hub.ingest(kind, payload)

    def test_expired_producer_cannot_detach_new_owner(self):
        old = self.hub.attach(SID)
        self.hub.detach(lease=old)
        new = self.hub.attach(SID)
        self.assertNotEqual(old, new)
        self.hub.detach(lease=old)
        self.assertTrue(self.hub.producer)
        with self.assertRaises(ValueError):
            self.hub.ingest("voice_state", {"state": "ERROR"}, lease=old)

    def test_slow_client_is_disconnected_instead_of_buffering_forever(self):
        client = self.hub.subscribe()
        for _ in range(130):
            self.hub.publish("heartbeat", {})
        self.assertNotIn(client, self.hub.clients)
        self.assertIsNone(client.get_nowait())

    def test_client_limit_and_close_release_queues(self):
        clients = [self.hub.subscribe() for _ in range(6)]
        with self.assertRaises(ValueError):
            self.hub.subscribe()
        self.hub.close()
        self.assertEqual(len(self.hub.clients), 0)
        for client in clients:
            self.assertIsNone(client.get_nowait())

    def test_restart_of_same_voice_process_gets_new_epoch(self):
        self.hub.attach(SID)
        epoch = self.hub.session_id
        self.hub.detach()
        self.hub.attach(SID)
        self.assertNotEqual(epoch, self.hub.session_id)

    def test_closed_hub_does_not_retain_late_observations(self):
        self.hub.close()
        self.hub.publish("voice_state", {"state": "LISTENING"})
        self.assertEqual(self.hub.cache, {})


class PresentationTransportTests(OfflineVoiceTest):
    def test_origin_and_host_reject_cross_site_and_dns_rebinding(self):
        self.assertTrue(
            allowed_request(
                "127.0.0.1:8765", "http://127.0.0.1:5174", "same-site", 8765
            )
        )
        for host, origin, site in (
            ("evil.local:8765", None, None),
            ("127.0.0.1:8765", "https://other.example", None),
            ("127.0.0.1:8765", None, "cross-site"),
        ):
            self.assertFalse(allowed_request(host, origin, site, 8765))

    def handler(self, *, path="/events", origin=None):
        handler = object.__new__(EventHandler)
        handler.headers = {"Host": "127.0.0.1:8765"}
        if origin:
            handler.headers["Origin"] = origin
        handler.path = path
        handler.connection = Mock()
        handler.wfile = io.BytesIO()
        client = queue.Queue()
        client.put(EventHub().publish("voice_state", {"state": "IDLE"}))
        client.put(None)
        hub = Mock(subscribe=Mock(return_value=client))
        handler.server = SimpleNamespace(hub=hub, stop=Event(), server_port=8765)
        for method in ("send_error", "send_response", "send_header", "end_headers"):
            setattr(handler, method, Mock())
        return handler

    def test_sse_http_is_read_only_no_cache_and_closes_subscription(self):
        handler = self.handler()
        handler.do_GET()
        handler.send_response.assert_called_once_with(200)
        handler.send_header.assert_any_call("Cache-Control", "no-store")
        self.assertIn(b'"version": 2', handler.wfile.getvalue())
        handler.server.hub.unsubscribe.assert_called_once()
        self.assertFalse(hasattr(EventHandler, "do_POST"))

    def test_no_browser_publication_endpoint(self):
        handler = self.handler(path="/publish")
        handler.do_GET()
        handler.send_error.assert_called_once_with(404)
        handler.server.hub.subscribe.assert_not_called()

    def test_cross_origin_request_never_subscribes(self):
        handler = self.handler(origin="https://other.example")
        handler.do_GET()
        handler.send_error.assert_called_once_with(403)
        handler.server.hub.subscribe.assert_not_called()

    def test_private_directory_permissions_are_enforced(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        path = root / "private" / "events.sock"
        private_directory(path)
        self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
        path.parent.chmod(0o755)
        with self.assertRaises(ValueError):
            private_directory(path)

    def test_unix_peer_is_authenticated_by_uid(self):
        connection = Mock()
        connection.getsockopt.return_value = struct.pack("3i", 1, os.getuid(), 1)
        verify_peer(connection)
        connection.getsockopt.return_value = struct.pack("3i", 1, os.getuid() + 1, 1)
        with self.assertRaises(ValueError):
            verify_peer(connection)

    def test_private_ingress_rejects_commands_and_detaches_lease(self):
        handler = object.__new__(ProducerHandler)
        handler.request = Mock()
        handler.request.getsockopt.return_value = struct.pack("3i", 1, os.getuid(), 1)
        handler.server = SimpleNamespace(hub=EventHub(), stop=Event())
        hello = {"version": 2, "sessionId": SID, "model": "qwen3.5:4b"}
        handler.rfile = io.BytesIO(
            (
                json.dumps(hello)
                + "\n"
                + json.dumps({"type": "execute", "payload": {"script": "x"}})
                + "\n"
            ).encode()
        )
        handler.handle()
        self.assertFalse(handler.server.hub.producer)

    def test_sse_json_cannot_inject_sse_headers(self):
        event = EventHub().publish(
            "conversation", {"question": "Como?", "answer": "Texto informativo."}
        )
        frame = sse_frame(event)
        self.assertEqual(frame.count(b"\n"), 2)
        self.assertNotIn(b"event: execute", frame)


class PresentationHealthTests(OfflineVoiceTest):
    def setup_health(self, ha=None):
        hub = EventHub()
        self.enterContext(
            patch(
                "jarvis_room.presentation_health.local_models",
                return_value=[{"name": "qwen3.5:4b", "size_bytes": 3324173934}],
            )
        )
        return hub, HealthObserver(hub, ha_client=ha)

    def test_inventory_observation_does_not_generate_inference(self):
        hub, health = self.setup_health()
        health.poll()
        self.assertEqual(
            hub.cache[("service_status", "llm")]["payload"]["detail"],
            "qwen3.5:4b · instalado; sem resposta observada",
        )
        self.assertEqual(
            hub.cache[("service_status", "home_assistant")]["payload"]["status"],
            "unknown",
        )

    def test_disabled_voice_llm_is_not_claimed_active(self):
        hub, health = self.setup_health()
        hub.attach(SID)
        health.poll()
        self.assertEqual(
            hub.cache[("service_status", "llm")]["payload"]["status"], "unknown"
        )

    def test_ollama_unavailable_invalidates_model_health(self):
        hub, health = self.setup_health()
        with patch(
            "jarvis_room.presentation_health.local_models",
            side_effect=OSError("private"),
        ):
            health.poll()
        self.assertEqual(
            hub.cache[("service_status", "ollama")]["payload"]["status"], "unavailable"
        )
        self.assertNotIn("private", json.dumps(list(hub.cache.values())))

    def test_real_lab_helper_is_separate_from_planned_physical_device(self):
        client = Mock(
            get_entity=Mock(return_value={"entity_id": LAB_ENTITY, "state": "on"})
        )
        hub, health = self.setup_health(client)
        health.poll()
        client.get_entity.assert_called_once_with(LAB_ENTITY)
        self.assertEqual(hub.cache[("lab_observation", None)]["payload"]["state"], "on")
        self.assertNotIn(("device_status", "room_main_lights"), hub.cache)

    def test_ha_failure_clears_helper_state_without_exposing_token(self):
        hub, health = self.setup_health(
            Mock(get_entity=Mock(side_effect=OSError("Bearer secret")))
        )
        health.poll()
        self.assertIsNone(hub.cache[("lab_observation", None)]["payload"]["state"])
        self.assertNotIn("secret", json.dumps(list(hub.cache.values())))

    def test_ha_read_requires_existing_explicit_opt_in(self):
        with (
            patch.dict(os.environ, {"JARVIS_HA_LAB_READ": "0"}),
            self.assertRaises(ValueError),
        ):
            ha_client_from_file(Path("/not/read"))


class VoicePresentationBindingTests(OfflineVoiceTest):
    def publisher(self, **kwargs):
        self.enterContext(patch("threading.Thread"))
        publisher = PresentationPublisher(Path("/tmp/unused.sock"), **kwargs)
        self.addCleanup(publisher.close)
        return publisher

    def test_state_callback_uses_actual_session_transitions(self):
        publisher = self.publisher()
        session = self.session()
        session.on_state = publisher.state
        session.activate()
        states = []
        while not publisher.pending.empty():
            event = publisher.pending.get_nowait()
            if event["type"] == "voice_state":
                states.append(event["payload"]["state"])
        self.assertIn("LISTENING", states)
        self.assertIn("TRANSCRIBING", states)
        self.assertIn("THINKING", states)
        self.assertIn("RESPONDING", states)
        self.assertEqual(states[-1], "IDLE")

    def test_conversation_is_not_published_without_operator_opt_in(self):
        publisher = self.publisher()
        publisher.conversation("Como?", VoiceReply("Informação", "informational"))
        self.assertTrue(publisher.pending.empty())

    def test_only_informational_reply_is_shared_when_enabled(self):
        publisher = self.publisher(share_conversation=True)
        publisher.conversation("Como?", VoiceReply("Resposta\nsegura", "informational"))
        publisher.conversation("Ligue os LEDs", VoiceReply("Plano", "room_plan"))
        event = publisher.pending.get_nowait()
        self.assertEqual(event["payload"]["answer"], "Resposta segura")
        self.assertTrue(publisher.pending.empty())
        self.assertEqual(publisher.cache, {})

    def test_queue_overflow_disconnects_instead_of_blocking_voice(self):
        publisher = self.publisher()
        publisher.connection = Mock()
        for _ in range(66):
            publisher.state(VoiceState.IDLE)
        self.assertLessEqual(publisher.pending.qsize(), 64)
        publisher.connection.shutdown.assert_called()

    def test_close_prevents_late_events_and_clears_cache(self):
        publisher = self.publisher()
        publisher.close()
        publisher.state(VoiceState.LISTENING)
        self.assertTrue(publisher.pending.empty())
        self.assertEqual(publisher.cache, {})
