"""SSE GET loopback + produtor Unix privado. Nenhuma rota executa operações."""

from __future__ import annotations

import argparse
import json
import os
import queue
import signal
import socketserver
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .presentation_contract import LIMIT, SESSION, VERSION, strict_json
from .presentation_health import HealthObserver, ha_client_from_file
from .presentation_hub import EventHub
from .presentation_ipc import default_socket, private_directory, verify_peer
from .voice_llm import DEFAULT_VOICE_MODEL, LLMSettings

FRONTEND_ORIGIN = "http://127.0.0.1:5174"


def allowed_request(host, origin, site, port):
    return (
        host == f"127.0.0.1:{port}"
        and origin in (None, FRONTEND_ORIGIN)
        and site in (None, "same-origin", "same-site", "none")
    )


def sse_frame(event):
    return (
        "data: " + json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n\n"
    ).encode()


class EventHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_args):
        pass  # Não registrar URL, origens ou conteúdo de conversa.

    def do_GET(self):
        if not allowed_request(
            self.headers.get("Host"),
            self.headers.get("Origin"),
            self.headers.get("Sec-Fetch-Site"),
            self.server.server_port,
        ):
            self.send_error(403)
            return
        if self.path != "/events":
            self.send_error(404)
            return
        try:
            client = self.server.hub.subscribe()
        except ValueError:
            self.send_error(503)
            return
        self.connection.settimeout(5)
        try:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Accel-Buffering", "no")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Connection", "close")
            self.end_headers()
            while not self.server.stop.is_set():
                try:
                    event = client.get(timeout=3)
                except queue.Empty:
                    continue
                if event is None:
                    break
                self.wfile.write(sse_frame(event))
                self.wfile.flush()
        except OSError:
            pass
        finally:
            self.server.hub.unsubscribe(client)
            self.close_connection = True


class BoundedHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, hub, stop):
        if address[0] != "127.0.0.1":
            raise ValueError("loopback_required")
        self.hub, self.stop = hub, stop
        self.slots = threading.BoundedSemaphore(8)
        super().__init__(address, EventHandler)

    def verify_request(self, request, _address):
        request.settimeout(5)
        return self.slots.acquire(blocking=False)

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


class ProducerHandler(socketserver.StreamRequestHandler):
    def handle(self):
        lease = None
        try:
            self.request.settimeout(4)
            verify_peer(self.request)
            hello = strict_json(self.rfile.readline(LIMIT + 1))
            if (
                set(hello) != {"version", "sessionId", "model"}
                or type(hello["version"]) is not int
                or hello["version"] != VERSION
                or not isinstance(hello["sessionId"], str)
                or not SESSION.fullmatch(hello["sessionId"])
            ):
                raise ValueError("invalid_producer_hello")
            lease = self.server.hub.attach(hello["sessionId"], hello["model"])
            while not self.server.stop.is_set():
                raw = self.rfile.readline(LIMIT + 1)
                if not raw:
                    break
                message = strict_json(raw)
                if set(message) != {"type", "payload"}:
                    raise ValueError("invalid_producer_message")
                self.server.hub.ingest(message["type"], message["payload"], lease=lease)
        except (OSError, ValueError):
            pass
        finally:
            if lease is not None:
                self.server.hub.detach(lease=lease)


class PrivateProducerServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    request_queue_size = 2

    def __init__(self, path, hub, stop):
        private_directory(path)
        self.hub, self.stop = hub, stop
        self.slots = threading.BoundedSemaphore(2)
        super().__init__(str(path), ProducerHandler)
        os.chmod(path, 0o600)

    def verify_request(self, request, _address):
        return self.slots.acquire(blocking=False)

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


def main():
    parser = argparse.ArgumentParser(
        description="Apresentação SSE local somente leitura", allow_abbrev=False
    )
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--socket", type=Path, default=default_socket())
    parser.add_argument("--llm-model", default=DEFAULT_VOICE_MODEL)
    parser.add_argument("--read-lab", action="store_true")
    parser.add_argument("--ha-token-file", type=Path)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535 or args.ha_token_file and not args.read_lab:
        parser.error("Porta inválida ou token sem opt-in de leitura.")
    hub, stop = EventHub(), threading.Event()
    http = ipc = None
    threads = []
    server_threads = {}
    socket_inode = None
    previous_term = signal.signal(signal.SIGTERM, lambda *_: stop.set())
    try:
        LLMSettings(args.llm_model)
        ha = ha_client_from_file(args.ha_token_file) if args.read_lab else None
        observer = HealthObserver(hub, model=args.llm_model, ha_client=ha)
        ipc = PrivateProducerServer(args.socket, hub, stop)
        socket_inode = args.socket.lstat().st_ino
        http = BoundedHTTPServer(("127.0.0.1", args.port), hub, stop)
        hub.detach()

        def heartbeat():
            while not stop.wait(0.25):
                hub.tick()

        def health():
            while not stop.is_set():
                observer.poll()
                stop.wait(5)

        for owner, target in (
            (http, http.serve_forever),
            (ipc, ipc.serve_forever),
            (None, heartbeat),
            (None, health),
        ):
            thread = threading.Thread(target=target, daemon=True)
            threads.append(thread)
            if owner is not None:
                server_threads[owner] = thread
            thread.start()
        print(
            f"Apresentação somente leitura em 127.0.0.1:{args.port}; Ctrl+C encerra.",
            flush=True,
        )
        stop.wait()
    except KeyboardInterrupt:
        pass
    except Exception:
        parser.exit(
            1, "Apresentação indisponível: confira porta, socket privado e opt-in HA.\n"
        )
    finally:
        stop.set()
        signal.signal(signal.SIGTERM, previous_term)
        hub.close()
        for server in (http, ipc):
            if server is not None:
                if (
                    server in server_threads
                    and server_threads[server].ident is not None
                ):
                    server.shutdown()
                server.server_close()
        if (
            ipc is not None
            and args.socket.exists()
            and args.socket.lstat().st_ino == socket_inode
        ):
            args.socket.unlink()
        for thread in threads:
            if thread.ident is not None:
                thread.join(timeout=5)


if __name__ == "__main__":
    main()
