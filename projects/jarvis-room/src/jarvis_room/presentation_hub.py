"""Fan-out limitado e volátil; dois monitores compartilham uma sessão de voz."""

from __future__ import annotations

import copy
import queue
import threading
import time
import uuid
from datetime import datetime, timezone

from .presentation_contract import VERSION, validate_event, validate_payload


class EventHub:
    def __init__(self, *, clock=time.monotonic, now=None):
        self.clock = clock
        self.now = now or (lambda: datetime.now(timezone.utc).isoformat())
        self.lock = threading.RLock()
        self.clients: set[queue.Queue] = set()
        self.session_id = str(uuid.uuid4())
        self.sequence = 0
        self.cache: dict[tuple, dict] = {}
        self.producer = False
        self.closed = False
        self.lease = None
        self.voice_session_id = None
        self.model = None
        self.last_producer = self.last_amplitude = self.clock()
        self.last_heartbeat = self.clock()
        self.playing = False
        self.llm_observed = False
        self.publish("connection", {"state": "connected"})

    def publish(self, kind: str, payload: dict):
        validate_payload(kind, payload)
        with self.lock:
            if self.closed:
                return None
            if kind == "voice_amplitude":
                if payload["amplitude"] and not self.playing:
                    raise ValueError("amplitude_without_playback")
                self.last_amplitude = self.clock()
            if kind == "playback_status":
                if not self.playing and payload["state"] == "playing":
                    self.last_amplitude = self.clock()
                self.playing = payload["state"] == "playing"
            self.sequence += 1
            event = validate_event(
                {
                    "version": VERSION,
                    "source": "backend",
                    "sessionId": self.session_id,
                    "sequence": self.sequence,
                    "type": kind,
                    "observedAt": self.now(),
                    "payload": copy.deepcopy(payload),
                }
            )
            if kind != "heartbeat":
                self.cache[(kind, payload.get("id"))] = event
            for client in tuple(self.clients):
                try:
                    client.put_nowait(event)
                except queue.Full:
                    self.clients.remove(client)
                    while not client.empty():
                        client.get_nowait()
                    client.put_nowait(None)
            return event

    def subscribe(self):
        with self.lock:
            if self.closed or len(self.clients) >= 6:
                raise ValueError("presentation_client_limit")
            self.tick()  # snapshot nunca ressuscita um lease ou áudio vencido
            client = queue.Queue(maxsize=128)
            for event in sorted(self.cache.values(), key=lambda e: e["sequence"]):
                current = copy.deepcopy(event)
                if event["type"] in {"connection", "playback_status"}:
                    # Conexão atual; reprodução confirmada pelo watchdog acima.
                    current["observedAt"] = self.now()
                client.put_nowait(current)
            self.clients.add(client)
            return client

    def unsubscribe(self, client):
        with self.lock:
            self.clients.discard(client)

    def reset(self, session_id: str | None = None):
        with self.lock:
            self.session_id = session_id or str(uuid.uuid4())
            self.sequence = 0
            self.cache.clear()
            self.playing = False
            self.llm_observed = False
            self.publish("connection", {"state": "connected"})
            self.publish("voice_state", {"state": "IDLE"})
            self.publish("playback_status", {"state": "unavailable"})
            self.publish("voice_amplitude", {"amplitude": 0})

    def attach(self, session_id: str, model=None):
        from .presentation_contract import SESSION
        from .voice_llm import LLMSettings

        if not isinstance(session_id, str) or not SESSION.fullmatch(session_id):
            raise ValueError("invalid_producer_session")
        if model is not None:
            LLMSettings(model)
        with self.lock:
            if self.producer:
                raise ValueError("voice_producer_busy")
            # Cada ligação possui época própria, mesmo após reconexão do produtor.
            self.reset()
            self.voice_session_id = session_id
            self.model = model
            self.lease = str(uuid.uuid4())
            self.producer = True
            self.last_producer = self.clock()
            self.publish(
                "service_status",
                {
                    "id": "voice",
                    "status": "connected",
                    "detail": "Sessão local conectada",
                },
            )
            return self.lease

    def ingest(self, kind: str, payload: dict, *, lease=None):
        validate_payload(kind, payload)
        if kind not in {
            "heartbeat",
            "voice_state",
            "voice_amplitude",
            "playback_status",
            "service_status",
            "conversation",
        }:
            raise ValueError("producer_event_forbidden")
        validate_payload(kind, payload)
        if kind == "service_status" and payload["id"] not in {
            "voice",
            "stt",
            "tts",
            "llm",
        }:
            raise ValueError("producer_service_forbidden")
        with self.lock:
            if not self.producer or (lease is not None and lease != self.lease):
                raise ValueError("voice_producer_missing")
            self.last_producer = self.clock()
            if kind != "heartbeat":
                if kind == "service_status" and payload["id"] == "llm":
                    self.llm_observed = True
                self.publish(kind, payload)
                if kind == "voice_state" and payload["state"] == "ERROR":
                    self.publish("playback_status", {"state": "error"})
                    self.publish("voice_amplitude", {"amplitude": 0})
                if kind == "playback_status" and payload["state"] != "playing":
                    self.publish("voice_amplitude", {"amplitude": 0})

    def detach(self, *, lease=None):
        with self.lock:
            if lease is not None and lease != self.lease:
                return
            if self.producer:
                self.producer = False
                self.lease = None
                self.reset()
            self.model = None
            for identifier in ("voice", "stt", "tts", "llm"):
                self.publish(
                    "service_status",
                    {
                        "id": identifier,
                        "status": "unavailable",
                        "detail": "Sem observação de sessão ativa",
                    },
                )

    def tick(self):
        with self.lock:
            if self.producer and self.clock() - self.last_producer > 6:
                self.detach()
            if self.playing and self.clock() - self.last_amplitude > 0.75:
                self.publish("playback_status", {"state": "error"})
                self.publish("voice_amplitude", {"amplitude": 0})
            if self.clock() - self.last_heartbeat >= 2:
                self.last_heartbeat = self.clock()
                self.publish("heartbeat", {})

    def close(self):
        with self.lock:
            self.closed = True
            for client in tuple(self.clients):
                while not client.empty():
                    client.get_nowait()
                client.put_nowait(None)
            self.clients.clear()
            self.cache.clear()
