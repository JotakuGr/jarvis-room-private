"""Snapshots, observações e progresso recentes com rede/voz/modelos falsos."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from jarvis_room.presentation_health import HealthObserver
from jarvis_room.presentation_hub import EventHub
from jarvis_room.presentation_ipc import PresentationPublisher
from jarvis_room.voice_contract import VoiceState
from voice_fakes import Clock, OfflineVoiceTest

SID = "11111111-1111-4111-8111-111111111111"
MODELS = [{"name": "qwen3.5:4b", "size_bytes": 3_324_173_934}]


class LivePresentationTests(OfflineVoiceTest):
    def publisher(self, **kwargs):
        self.enterContext(patch("threading.Thread"))
        self.clock = Clock()
        result = PresentationPublisher(
            Path("/tmp/unused-s92.sock"), clock=self.clock, **kwargs
        )
        self.addCleanup(result.close)
        return result

    def model_payload(self, hub):
        return hub.cache[("service_status", "llm")]["payload"]

    def test_new_subscriber_gets_fresh_handshake_without_redating_voice(self):
        clock = Clock()
        origin = datetime(2026, 10, 21, tzinfo=timezone.utc)
        hub = EventHub(
            clock=clock, now=lambda: (origin + timedelta(seconds=clock())).isoformat()
        )
        event = hub.publish("voice_state", {"state": "IDLE"})
        clock.wait(30)
        client = hub.subscribe()
        handshake = client.get_nowait()
        self.assertNotEqual(handshake["observedAt"], event["observedAt"])
        self.assertEqual(client.get_nowait(), event)

    def test_snapshot_expires_dead_voice_producer_before_replay(self):
        clock, hub = Clock(), EventHub()
        hub.clock = clock
        hub.last_producer = hub.last_amplitude = hub.last_heartbeat = clock()
        lease = hub.attach(SID)
        hub.ingest("voice_state", {"state": "RESPONDING"}, lease=lease)
        hub.ingest("playback_status", {"state": "playing"}, lease=lease)
        hub.ingest("voice_amplitude", {"amplitude": 0.7}, lease=lease)
        old = hub.session_id
        clock.wait(7)
        hub.subscribe()
        self.assertFalse(hub.producer)
        self.assertNotEqual(hub.session_id, old)
        self.assertEqual(
            hub.cache[("voice_amplitude", None)]["payload"], {"amplitude": 0}
        )

    def test_first_pcm_has_watchdog_budget_after_long_idle(self):
        clock = Clock()
        hub = EventHub(clock=clock)
        clock.wait(60)
        hub.publish("playback_status", {"state": "playing"})
        hub.tick()
        self.assertTrue(hub.playing)
        clock.wait(0.8)
        hub.tick()
        self.assertFalse(hub.playing)

    def test_voice_error_immediately_clears_playback_and_energy(self):
        hub = EventHub()
        lease = hub.attach(SID)
        hub.ingest("playback_status", {"state": "playing"}, lease=lease)
        hub.ingest("voice_amplitude", {"amplitude": 0.8}, lease=lease)
        hub.ingest("voice_state", {"state": "ERROR"}, lease=lease)
        self.assertFalse(hub.playing)
        self.assertEqual(
            hub.cache[("voice_amplitude", None)]["payload"], {"amplitude": 0}
        )

    def test_publisher_error_invalidates_even_recent_queued_pcm(self):
        publisher = self.publisher()
        publisher.emit("playback_status", {"state": "playing"})
        publisher.emit("voice_amplitude", {"amplitude": 0.6})
        sample = list(publisher.pending.queue)[-1]
        publisher.state(VoiceState.ERROR)
        connection = Mock()
        publisher._send(connection, sample)
        connection.sendall.assert_not_called()
        self.assertEqual(
            publisher.cache[("voice_amplitude", None)]["payload"], {"amplitude": 0}
        )

    def test_installed_model_is_not_evidence_of_inference(self):
        hub = EventHub()
        with patch("jarvis_room.presentation_health.local_models", return_value=MODELS):
            HealthObserver(hub).poll()
        self.assertEqual(self.model_payload(hub)["status"], "unknown")
        self.assertIn(
            "instalado; sem resposta observada", self.model_payload(hub)["detail"]
        )

    def test_inventory_does_not_overwrite_confirmed_generation(self):
        hub = EventHub()
        lease = hub.attach(SID, "qwen3.5:4b")
        payload = {
            "id": "llm",
            "status": "connected",
            "detail": "qwen3.5:4b · resposta gerada nesta sessão",
        }
        hub.ingest("service_status", payload, lease=lease)
        event = hub.cache[("service_status", "llm")]
        with patch("jarvis_room.presentation_health.local_models", return_value=MODELS):
            HealthObserver(hub).poll()
        self.assertIs(hub.cache[("service_status", "llm")], event)

    def test_inventory_failure_invalidates_success_and_recovers_without_faking_use(
        self,
    ):
        hub = EventHub()
        lease = hub.attach(SID, "qwen3.5:4b")
        hub.ingest(
            "service_status",
            {"id": "llm", "status": "connected", "detail": "Resposta observada"},
            lease=lease,
        )
        health = HealthObserver(hub)
        with patch(
            "jarvis_room.presentation_health.local_models",
            side_effect=[OSError("private"), MODELS],
        ):
            health.poll()
            self.assertEqual(self.model_payload(hub)["status"], "unavailable")
            health.poll()
        self.assertEqual(self.model_payload(hub)["status"], "unknown")
        self.assertNotIn("private", str(hub.cache))

    def test_inventory_cannot_overwrite_replacement_voice_session(self):
        hub = EventHub()
        lease = hub.attach(SID, "qwen3.5:4b")

        def inventory():
            hub.detach(lease=lease)
            current = hub.attach(SID, "other:local")
            hub.ingest(
                "service_status",
                {
                    "id": "llm",
                    "status": "connected",
                    "detail": "other:local · resposta observada",
                },
                lease=current,
            )
            return MODELS

        with patch(
            "jarvis_room.presentation_health.local_models", side_effect=inventory
        ):
            HealthObserver(hub).poll()
        self.assertIn("other:local", self.model_payload(hub)["detail"])

    def test_generation_health_arrives_before_tts_without_conversation_opt_in(self):
        publisher = self.publisher(model="qwen3.5:4b")
        session = self.session(
            texts=["Jarvis, explique o projeto"],
            chat=Mock(answer=Mock(return_value="Uma resposta informativa.")),
        )
        session.on_metrics = publisher.metrics

        def during_tts():
            self.assertEqual(
                publisher.cache[("service_status", "llm")]["payload"]["status"],
                "connected",
            )
            self.assertTrue(
                all(m["type"] != "conversation" for m in list(publisher.pending.queue))
            )

        self.speaker.hook = during_tts
        session.activate()
        self.assertIn(
            "resposta gerada",
            publisher.cache[("service_status", "llm")]["payload"]["detail"],
        )

    def test_call_greeting_does_not_claim_llm_generation(self):
        publisher = self.publisher(model="qwen3.5:4b")
        session = self.session(texts=["Jarvis"])
        session.on_metrics = publisher.metrics
        session.activate()
        self.assertNotIn(("service_status", "llm"), publisher.cache)

    def test_llm_failure_health_is_sanitized(self):
        publisher = self.publisher()
        publisher.metrics(
            {"stage": "router_complete", "router_llm_error_code": "private exception"}
        )
        payload = publisher.cache[("service_status", "llm")]["payload"]
        self.assertEqual(payload["status"], "unavailable")
        self.assertNotIn("private", str(payload))

    def test_reconnection_snapshot_contains_no_old_playback_conversation_or_use(self):
        publisher = self.publisher(share_conversation=True)
        publisher.emit("voice_state", {"state": "RESPONDING"})
        publisher.emit("playback_status", {"state": "playing"})
        publisher.emit("voice_amplitude", {"amplitude": 0.8})
        publisher.emit(
            "conversation", {"question": "Como?", "answer": "Informação pessoal"}
        )
        publisher.service("llm", "connected", "Resposta anterior")
        snapshot = publisher._reconnection_snapshot()
        self.assertTrue(publisher.pending.empty())
        self.assertNotIn("Informação pessoal", str(snapshot))
        self.assertNotIn("RESPONDING", str(snapshot))
        self.assertNotIn("playing", str(snapshot))
        self.assertEqual(snapshot[2]["payload"], {"amplitude": 0})
        self.assertEqual(snapshot[3]["payload"]["status"], "unknown")

    def test_delayed_positive_energy_is_dropped_but_zero_is_always_sent(self):
        publisher = self.publisher()
        connection = Mock()
        publisher.emit("playback_status", {"state": "playing"})
        publisher.emit("voice_amplitude", {"amplitude": 0.9})
        message = list(publisher.pending.queue)[-1]
        self.clock.wait(1)
        publisher._send(connection, message)
        connection.sendall.assert_not_called()
        publisher.emit("voice_amplitude", {"amplitude": 0})
        zero = list(publisher.pending.queue)[-1]
        self.clock.wait(1)
        publisher._send(connection, zero)
        self.assertEqual(
            json.loads(connection.sendall.call_args.args[0]),
            {"type": "voice_amplitude", "payload": {"amplitude": 0}},
        )

    def test_fresh_pcm_resumes_playing_after_reconnection(self):
        publisher = self.publisher()
        publisher.emit("voice_state", {"state": "RESPONDING"})
        publisher.emit("playback_status", {"state": "playing"})
        publisher._reconnection_snapshot()
        publisher.emit("voice_amplitude", {"amplitude": 0.4})
        connection = Mock()
        publisher._send(connection, publisher.pending.get_nowait())
        frames = [
            json.loads(call.args[0]) for call in connection.sendall.call_args_list
        ]
        self.assertEqual(
            [frame["type"] for frame in frames],
            ["voice_state", "playback_status", "voice_amplitude"],
        )
        self.assertEqual(frames[1]["payload"], {"state": "playing"})
        self.assertTrue(all(set(frame) == {"type", "payload"} for frame in frames))

    def test_pcm_without_a_voice_state_does_not_invent_a_machine_transition(self):
        publisher = self.publisher()
        publisher.emit("playback_status", {"state": "playing"})
        publisher.emit("voice_amplitude", {"amplitude": 0.4})
        connection = Mock()
        publisher._send(connection, list(publisher.pending.queue)[-1])
        frames = [
            json.loads(call.args[0]) for call in connection.sendall.call_args_list
        ]
        self.assertEqual(
            [frame["type"] for frame in frames], ["playback_status", "voice_amplitude"]
        )

    def test_finished_audio_never_resumes_from_a_queued_sample(self):
        publisher = self.publisher()
        publisher.emit("playback_status", {"state": "playing"})
        publisher.emit("voice_amplitude", {"amplitude": 0.4})
        message = list(publisher.pending.queue)[-1]
        publisher.emit("playback_status", {"state": "idle"})
        connection = Mock()
        publisher._send(connection, message)
        connection.sendall.assert_not_called()

    def test_old_busy_state_and_personal_text_are_not_sent_after_delay(self):
        publisher = self.publisher(share_conversation=True)
        publisher.emit("voice_state", {"state": "THINKING"})
        publisher.emit("conversation", {"question": "Como?", "answer": "Texto privado"})
        self.clock.wait(9)
        connection = Mock()
        for message in list(publisher.pending.queue):
            publisher._send(connection, message)
        connection.sendall.assert_not_called()

    def test_rejected_transcription_still_can_report_stt_health_without_text(self):
        publisher = self.publisher()
        publisher.metrics(
            {"stage": "voice_admission", "accepted": False, "stt_seconds": 0.2}
        )
        payload = publisher.cache[("service_status", "stt")]["payload"]
        self.assertEqual(
            payload,
            {"id": "stt", "status": "connected", "detail": "Modelo STT carregado"},
        )

    def test_model_identifier_is_bounded_in_generated_health(self):
        publisher = self.publisher(model="a" * 128)
        publisher.metrics(
            {"stage": "router_complete", "reply_channel": "informational"}
        )
        self.assertLessEqual(
            len(publisher.cache[("service_status", "llm")]["payload"]["detail"]), 128
        )
