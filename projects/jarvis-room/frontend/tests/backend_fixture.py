"""Fixture E2E opt-in: transporte real loopback, produtor falso, sem serviços IA.

Controle só por stdin do processo de testes; nenhuma rota HTTP de publicação.
Não usar como backend operacional nem iniciar áudio, HA ou inventário Ollama.
"""

from __future__ import annotations

import json
import os
import select
import signal
import sys
import tempfile
import threading
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(PROJECT / "src"), str(PROJECT.parents[1] / "src")]

from jarvis_room import presentation_server  # noqa: E402
from jarvis_room.presentation_hub import EventHub  # noqa: E402
from jarvis_room.presentation_ipc import PresentationPublisher  # noqa: E402
from jarvis_room.presentation_server import (  # noqa: E402
    BoundedHTTPServer,
    PrivateProducerServer,
)
from jarvis_room.voice_contract import VoiceState  # noqa: E402


def main():
    if os.environ.get("JARVIS_PRESENTATION_E2E") != "1":
        raise SystemExit("Fixture exclusiva dos testes: opt-in ausente")
    presentation_server.FRONTEND_ORIGIN = "http://127.0.0.1:15174"
    hub, stop = EventHub(), threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    http = ipc = producer = None
    threads = []

    def until(condition):
        # Publicador: espera de heartbeat até 2 s + backoff de reconexão 2 s.
        deadline = time.monotonic() + 6
        while not condition():
            if stop.wait(0.01) or time.monotonic() >= deadline:
                raise RuntimeError("fixture_timeout")

    def tick():
        while not stop.wait(0.1):
            hub.tick()

    with tempfile.TemporaryDirectory(prefix="jarvis-s92-e2e-") as directory:
        try:
            path = Path(directory) / "events.sock"
            # Abortar se a porta estiver ocupada; nunca reutilizar backend real.
            http = BoundedHTTPServer(("127.0.0.1", 18765), hub, stop)
            ipc = PrivateProducerServer(path, hub, stop)
            hub.detach()
            for target in (http.serve_forever, ipc.serve_forever, tick):
                thread = threading.Thread(target=target, daemon=True)
                thread.start()
                threads.append(thread)
            print(json.dumps({"ready": True}), flush=True)
            while not stop.is_set():
                if not select.select([sys.stdin], [], [], 0.1)[0]:
                    continue
                line = sys.stdin.readline(8193)
                if not line:
                    break
                message = json.loads(line)
                if message == {"disconnect": True}:
                    if producer is not None:
                        producer.close()
                        producer = None
                        until(lambda: not hub.producer)
                    print(json.dumps({"ok": True}), flush=True)
                    continue
                if message == {"reconnect": True}:
                    previous = hub.session_id
                    producer._disconnect()
                    until(lambda: hub.producer and hub.session_id != previous)
                    print(json.dumps({"ok": True}), flush=True)
                    continue
                if producer is None:
                    producer = PresentationPublisher(path, model="qwen3.5:4b")
                    until(lambda: hub.producer)
                before = hub.sequence
                if message["type"] == "voice_state":
                    producer.state(VoiceState(message["payload"]["state"]))
                elif message["type"] in {"voice_amplitude", "playback_status"}:
                    producer.playback(message)
                else:
                    producer.emit(message["type"], message["payload"])
                key = (message["type"], message["payload"].get("id"))
                until(lambda: key in hub.cache and hub.cache[key]["sequence"] > before)
                print(json.dumps({"ok": True, "sessionId": hub.session_id}), flush=True)
        finally:
            stop.set()
            if producer is not None:
                producer.close()
            hub.close()
            for server in (http, ipc):
                if server is not None:
                    if threads:
                        server.shutdown()
                    server.server_close()
            for thread in threads:
                thread.join(timeout=3)


if __name__ == "__main__":
    main()
