"""Publicação privada autenticada por UID Linux; navegador não possui esta API."""

from __future__ import annotations

import json
import os
import queue
import socket
import stat
import struct
import threading
import time
import uuid
from pathlib import Path

from .presentation_contract import LIMIT, VERSION, validate_payload


def default_socket() -> Path:
    return Path(f"/tmp/jarvis-presentation-{os.getuid()}/events.sock")


def private_directory(path: Path):
    if not path.is_absolute():
        raise ValueError("absolute_socket_path_required")
    path.parent.mkdir(mode=0o700, parents=False, exist_ok=True)
    info = path.parent.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise ValueError("unsafe_presentation_directory")


def verify_peer(connection):
    _pid, uid, _gid = struct.unpack(
        "3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
    )
    if uid != os.getuid():
        raise ValueError("presentation_peer_rejected")


class PresentationPublisher:
    """Fila não bloqueante; falha de apresentação nunca interrompe voz."""

    def __init__(
        self, path: Path, *, share_conversation=False, model=None, clock=time.monotonic
    ):
        self.path = path
        self.session_id = str(uuid.uuid4())
        self.share_conversation = share_conversation
        self.model = model
        self.clock = clock
        self._playing_sent = False
        self.stop = threading.Event()
        self.pending = queue.Queue(maxsize=64)
        self.lock = threading.Lock()
        self.cache: dict[tuple, dict] = {}
        self.connection = None
        self.thread = threading.Thread(
            target=self._run, daemon=True, name="presentation-publisher"
        )
        self.thread.start()

    def emit(self, kind, payload):
        validate_payload(kind, payload)
        if kind == "conversation" and not self.share_conversation:
            return
        if self.stop.is_set():
            return
        message = {"type": kind, "payload": payload.copy(), "_queued_at": self.clock()}
        with self.lock:
            if self.stop.is_set():
                return
            if kind not in {"conversation", "heartbeat"}:
                self.cache[(kind, payload.get("id"))] = message
            try:
                self.pending.put_nowait(message)
            except queue.Full:
                # Desconectar invalida dados em vez de atrasar áudio.
                self._disconnect()

    def state(self, state):
        if state.value == "LISTENING":
            self.service("voice", "connected", "Captura aberta na sessão")
        elif state.value == "ERROR":
            self.service("voice", "unavailable", "Erro observado na sessão")
        self.emit("voice_state", {"state": state.value})
        if state.value == "ERROR":
            self.emit("playback_status", {"state": "error"})
            self.emit("voice_amplitude", {"amplitude": 0})

    def service(self, identifier, status, detail):
        self.emit(
            "service_status", {"id": identifier, "status": status, "detail": detail}
        )

    def metrics(self, value):
        if value.get("stage") in {"stt_initialization", "voice_admission"}:
            self.service("stt", "connected", "Modelo STT carregado")
        elif value.get("status") == "error":
            identifier = (
                "stt" if str(value.get("stage", "")).startswith("stt") else "voice"
            )
            self.service(identifier, "unavailable", "Falha ou timeout da sessão")
        elif value.get("stage") == "router_complete":
            if value.get("router_llm_error_code"):
                self.service("llm", "unavailable", "Conversa local indisponível")
            elif value.get("reply_channel") == "informational":
                # Só o roteador confirma geração; inventário não é inferência.
                from .voice_llm import LLMSettings

                if self.model is not None:
                    LLMSettings(self.model)
                    detail = self.model[:80] + " · resposta gerada nesta sessão"
                else:
                    detail = "Resposta informativa gerada; modelo não informado"
                self.service("llm", "connected", detail)

    def playback(self, event):
        if event["type"] == "playback_status":
            state = event["payload"]["state"]
            self.service(
                "tts",
                "unavailable"
                if state in {"error", "unavailable"}
                else "unknown"
                if state == "synthesizing"
                else "connected",
                "Reprodução ativa"
                if state == "playing"
                else "Estado da saída de voz: " + state,
            )
        self.emit(event["type"], event["payload"])

    def conversation(self, question, reply):
        if self.share_conversation and reply.channel == "informational":

            def clean(s, n):
                return " ".join(s.split())[:n]

            self.emit(
                "conversation",
                {"question": clean(question, 256), "answer": clean(reply.text, 700)},
            )

    def _write(self, connection, message):
        raw = json.dumps(message, ensure_ascii=False, allow_nan=False).encode() + b"\n"
        if len(raw) > LIMIT:
            raise ValueError("presentation_message_limit")
        connection.sendall(raw)

    def _send(self, connection, message):
        kind, payload = message["type"], message["payload"]
        age = self.clock() - message.get("_queued_at", self.clock())
        if kind == "voice_amplitude" and payload["amplitude"] > 0:
            with self.lock:
                current = self.cache.get(("playback_status", None))
                voice = self.cache.get(("voice_state", None))
            if age > 0.5 or not current or current["payload"]["state"] != "playing":
                return
            if not self._playing_sent:
                # Retomar só com PCM recente, nunca pelo cache de "playing".
                if voice and voice["payload"]["state"] == "RESPONDING":
                    self._write(
                        connection, {"type": "voice_state", "payload": voice["payload"]}
                    )
                self._write(
                    connection,
                    {"type": "playback_status", "payload": {"state": "playing"}},
                )
                self._playing_sent = True
        elif kind == "playback_status":
            if payload["state"] in {"playing", "synthesizing"} and age > 0.5:
                return
            self._playing_sent = payload["state"] == "playing"
        elif (
            kind == "voice_state"
            and payload["state"] not in {"IDLE", "ERROR"}
            and age > 0.5
        ):
            return
        elif kind == "conversation" and age > 8:
            return
        elif kind == "service_status" and payload["status"] == "connected" and age > 8:
            return
        # Metadado de fila é interno, não altera o contrato Unix/SSE.
        self._write(connection, {"type": kind, "payload": payload})

    def _reconnection_snapshot(self):
        with self.lock:
            cached = list(self.cache.values())
            while not self.pending.empty():
                self.pending.get_nowait()
        self._playing_sent = False
        result = [
            {"type": "voice_state", "payload": {"state": "IDLE"}},
            {"type": "playback_status", "payload": {"state": "unavailable"}},
            {"type": "voice_amplitude", "payload": {"amplitude": 0}},
        ]
        for message in cached:
            if message["type"] == "service_status":
                payload = message["payload"]
                result.append(
                    {
                        "type": "service_status",
                        "payload": {
                            "id": payload["id"],
                            "status": "unavailable"
                            if payload["status"] == "unavailable"
                            else "unknown",
                            "detail": "Sem nova observação nesta conexão",
                        },
                    }
                )
        # Sem conversa, fala ocupada ou energia histórica no snapshot de retorno.
        return result

    def _disconnect(self):
        connection = self.connection
        if connection is not None:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def _run(self):
        while not self.stop.is_set():
            try:
                private_directory(self.path)
                info = self.path.lstat()
                if (
                    not stat.S_ISSOCK(info.st_mode)
                    or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) != 0o600
                ):
                    raise ValueError("unsafe_presentation_socket")
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                    connection.settimeout(1)
                    self.connection = connection
                    connection.connect(str(self.path))
                    verify_peer(connection)
                    snapshot = self._reconnection_snapshot()
                    self._write(
                        connection,
                        {
                            "version": VERSION,
                            "sessionId": self.session_id,
                            "model": self.model,
                        },
                    )
                    for message in snapshot:
                        self._send(connection, message)
                    while not self.stop.is_set():
                        try:
                            message = self.pending.get(timeout=2)
                        except queue.Empty:
                            message = {"type": "heartbeat", "payload": {}}
                        self._send(connection, message)
            except (OSError, ValueError):
                self.stop.wait(2)
            finally:
                self.connection = None

    def close(self):
        self.stop.set()
        self._disconnect()
        self.thread.join(timeout=3)
        self.cache.clear()
        while not self.pending.empty():
            self.pending.get_nowait()
