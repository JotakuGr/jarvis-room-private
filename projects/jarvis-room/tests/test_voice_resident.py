"""Protocolo por pipes, supervisão e servidor residente sem processos reais."""

import base64
import io
import os
import struct
import subprocess
import time
from collections import deque
from pathlib import Path
from threading import Event
from unittest.mock import Mock, patch

from jarvis_room.voice_contract import VoiceCancelled, VoiceError
from jarvis_room.voice_resident import (
    MAX_FRAME,
    FramedPipe,
    ResidentWorker,
    decode_payload,
    encode_frame,
)
from jarvis_room.voice_worker import arm_parent_death, read_frame, resident_main
from voice_fakes import OfflineVoiceTest, wav


class ResidentWorkerTests(OfflineVoiceTest):
    def test_parent_death_guard_is_armed_before_native_imports(self):
        libc = Mock()
        libc.prctl.return_value = 0
        with (
            patch.dict("os.environ", {"JARVIS_VOICE_PARENT_PID": "123"}),
            patch("os.getppid", return_value=123),
            patch("ctypes.CDLL", return_value=libc),
        ):
            arm_parent_death()
        libc.prctl.assert_called_once()

    def test_missing_parent_prevents_worker_from_becoming_orphan(self):
        with (
            patch.dict("os.environ", {"JARVIS_VOICE_PARENT_PID": "123"}),
            patch("os.getppid", return_value=1),
            self.assertRaisesRegex(VoiceError, "worker_parent_missing"),
        ):
            arm_parent_death()

    def supervisor(self, replies=None):
        self.sent = []
        pending = deque(replies or [])
        self.pipe = Mock()
        self.pipe.send.side_effect = lambda message, **kwargs: self.sent.append(message)
        self.pipe.receive.side_effect = lambda **kwargs: (
            pending.popleft()
            if pending
            else {
                "id": self.sent[-1]["id"],
                "ok": True,
                "result": {"initialization_seconds": 0.5}
                if self.sent[-1]["op"] == "initialize"
                else {"text": "liga os monitores", "metrics": {"transcriptions": 1}},
            }
        )
        self.process = Mock(pid=998877)
        self.process.poll.return_value = None
        self.process.stdin.fileno.return_value = 10
        self.process.stdout.fileno.return_value = 11
        self.spawn = self.enterContext(
            patch("subprocess.Popen", return_value=self.process)
        )
        self.enterContext(
            patch("jarvis_room.voice_resident.FramedPipe", return_value=self.pipe)
        )
        self.kill = self.enterContext(patch("os.killpg"))
        worker = ResidentWorker("stt", {"model_dir": "/local/model", "device": "cpu"})
        self.addCleanup(worker.close)
        return worker

    def test_start_is_reused_not_reloaded(self):
        worker = self.supervisor()
        worker.start(timeout=1, cancel=Event())
        worker.start(timeout=1, cancel=Event())
        self.spawn.assert_called_once()
        self.assertEqual([item["op"] for item in self.sent], ["initialize"])

    def test_two_requests_share_one_worker_and_have_unique_ids(self):
        worker = self.supervisor()
        worker.start(timeout=1, cancel=Event())
        for _ in range(2):
            worker.request("transcribe", {"audio": "fake"}, timeout=1, cancel=Event())
        self.assertEqual([item["id"] for item in self.sent], [1, 2, 3])
        self.spawn.assert_called_once()

    def test_no_socket_server_and_isolated_process_group(self):
        worker = self.supervisor()
        worker.start(timeout=1, cancel=Event())
        args, kwargs = self.spawn.call_args
        self.assertIn("--resident-stt", args[0])
        self.assertTrue(kwargs["start_new_session"])
        self.assertEqual(kwargs["env"]["CUDA_VISIBLE_DEVICES"], "")

    def test_close_kills_waits_closes_pipes_and_removes_runtime(self):
        worker = self.supervisor()
        worker.start(timeout=1, cancel=Event())
        runtime = Path(worker._runtime.name)
        worker.close()
        worker.close()
        self.kill.assert_called_once()
        self.process.wait.assert_called_once()
        self.process.stdin.close.assert_called_once()
        self.process.stdout.close.assert_called_once()
        self.assertFalse(runtime.exists())

    def test_closed_worker_cannot_restart(self):
        worker = self.supervisor()
        worker.close()
        with self.assertRaises(VoiceError):
            worker.start(timeout=1, cancel=Event())
        self.spawn.assert_not_called()

    def test_wait_failure_still_closes_pipes_and_removes_runtime(self):
        worker = self.supervisor()
        worker.start(timeout=1, cancel=Event())
        runtime = Path(worker._runtime.name)
        self.process.wait.side_effect = subprocess.TimeoutExpired("worker", 5)
        with self.assertRaises(subprocess.TimeoutExpired):
            worker.close()
        self.kill.assert_called_once()
        self.process.stdin.close.assert_called_once()
        self.process.stdout.close.assert_called_once()
        self.assertFalse(runtime.exists())

    def test_cancel_before_start_does_not_spawn(self):
        worker = self.supervisor()
        cancel = Event()
        cancel.set()
        with self.assertRaises(VoiceCancelled):
            worker.start(timeout=1, cancel=cancel)
        self.spawn.assert_not_called()

    def test_timeout_kills_worker_without_retrying_audio(self):
        worker = self.supervisor()
        worker.start(timeout=1, cancel=Event())
        self.pipe.receive.side_effect = VoiceError("ipc_timeout")
        with self.assertRaisesRegex(VoiceError, "ipc_timeout"):
            worker.request("transcribe", {"audio": "one"}, timeout=1, cancel=Event())
        self.assertEqual(len(self.sent), 2)
        self.kill.assert_called_once()
        self.assertIsNone(worker.process)

    def test_ctrl_c_during_request_kills_and_waits(self):
        worker = self.supervisor()
        worker.start(timeout=1, cancel=Event())
        self.pipe.receive.side_effect = KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):
            worker.request("transcribe", {}, timeout=1, cancel=Event())
        self.kill.assert_called_once()
        self.process.wait.assert_called_once()

    def test_cancel_during_request_kills_and_waits(self):
        worker = self.supervisor()
        worker.start(timeout=1, cancel=Event())
        self.pipe.receive.side_effect = VoiceCancelled("cancelled")
        with self.assertRaises(VoiceCancelled):
            worker.request("transcribe", {}, timeout=1, cancel=Event())
        self.kill.assert_called_once()

    def test_startup_failure_does_not_leave_worker(self):
        worker = self.supervisor(
            [{"id": 1, "ok": False, "error": "stt_cuda_unavailable"}]
        )
        with self.assertRaisesRegex(VoiceError, "stt_cuda_unavailable"):
            worker.start(timeout=1, cancel=Event())
        self.assertIsNone(worker.process)
        self.process.wait.assert_called_once()

    def test_wrong_response_id_stops_worker(self):
        worker = self.supervisor([{"id": 7, "ok": True, "result": {}}])
        with self.assertRaisesRegex(VoiceError, "ipc_response_mismatch"):
            worker.start(timeout=1, cancel=Event())
        self.kill.assert_called_once()

    def test_concurrent_request_is_rejected_without_stopping_owner(self):
        worker = self.supervisor()
        worker.start(timeout=1, cancel=Event())
        worker._lock.acquire()
        try:
            with self.assertRaisesRegex(VoiceError, "stt_busy"):
                worker.request("transcribe", {}, timeout=1, cancel=Event())
        finally:
            worker._lock.release()
        self.kill.assert_not_called()

    def test_concurrent_start_is_rejected(self):
        worker = self.supervisor()
        worker._lock.acquire()
        try:
            with self.assertRaises(VoiceError):
                worker.start(timeout=1, cancel=Event())
        finally:
            worker._lock.release()
        self.spawn.assert_not_called()

    def test_recovery_requires_explicit_start_and_never_replays_request(self):
        worker = self.supervisor()
        worker.start(timeout=1, cancel=Event())
        self.pipe.receive.side_effect = VoiceError("ipc_timeout")
        with self.assertRaises(VoiceError):
            worker.request(
                "transcribe", {"audio": "private"}, timeout=1, cancel=Event()
            )
        self.pipe.receive.side_effect = lambda **kwargs: {
            "id": self.sent[-1]["id"],
            "ok": True,
            "result": {},
        }
        worker.start(timeout=1, cancel=Event())
        self.assertEqual(
            [message["op"] for message in self.sent],
            ["initialize", "transcribe", "initialize"],
        )
        self.assertEqual(self.spawn.call_count, 2)

    def test_untrusted_error_does_not_expose_private_details(self):
        worker = self.supervisor(
            [{"id": 1, "ok": False, "error": "/private/token-file"}]
        )
        with self.assertRaisesRegex(VoiceError, "^stt_backend_unavailable$"):
            worker.start(timeout=1, cancel=Event())


class PipeProtocolTests(OfflineVoiceTest):
    def pipe(self):
        reader, writer = os.pipe()
        self.addCleanup(os.close, reader)
        self.addCleanup(os.close, writer)
        return FramedPipe(reader, writer)

    def test_json_round_trip_over_private_os_pipe(self):
        pipe = self.pipe()
        message = {"id": 1, "op": "transcribe", "audio": "áudio falso"}
        pipe.send(message, deadline=time.monotonic() + 1, cancel=Event())
        self.assertEqual(
            pipe.receive(deadline=time.monotonic() + 1, cancel=Event()), message
        )

    def test_frame_limit_checked_before_write(self):
        with self.assertRaises(VoiceError):
            encode_frame({"audio": "x" * MAX_FRAME})

    def test_oversized_declared_frame_rejected_before_body(self):
        pipe = self.pipe()
        os.write(pipe.writer, struct.pack("!I", MAX_FRAME + 1))
        with self.assertRaisesRegex(VoiceError, "ipc_frame_limit"):
            pipe.receive(deadline=time.monotonic() + 1, cancel=Event())

    def test_expired_deadline_is_immediate(self):
        with self.assertRaisesRegex(VoiceError, "ipc_timeout"):
            self.pipe().receive(deadline=time.monotonic() - 1, cancel=Event())

    def test_cancelled_receive_is_immediate(self):
        cancel = Event()
        cancel.set()
        with self.assertRaises(VoiceCancelled):
            self.pipe().receive(deadline=time.monotonic() + 1, cancel=cancel)

    def test_invalid_json_or_non_object_rejected(self):
        for data in (b"invalid", b"[]", b'"text"', b'{"value":NaN}'):
            with self.subTest(data=data), self.assertRaises(VoiceError):
                decode_payload(data)

    def test_truncated_frame_rejected(self):
        with self.assertRaises(VoiceError):
            read_frame(io.BytesIO(struct.pack("!I", 10) + b"{}"))

    def test_resident_server_loads_engine_once_for_multiple_turns(self):
        requests = [{"id": 1, "op": "initialize", "options": {"model_dir": "/local"}}]
        requests.extend(
            {"id": index, "op": "transcribe", "audio": base64.b64encode(wav()).decode()}
            for index in (2, 3)
        )
        reader, writer = (
            io.BytesIO(b"".join(encode_frame(item) for item in requests)),
            io.BytesIO(),
        )
        engine = Mock()
        engine.health.return_value = {"initialization_seconds": 1}
        engine.transcribe.return_value = {"text": "liga os monitores", "metrics": {}}
        with patch(
            "jarvis_room.voice_stt.SpeechEngine", return_value=engine
        ) as constructor:
            resident_main("stt", reader, writer)
        constructor.assert_called_once()
        self.assertEqual(engine.transcribe.call_count, 2)
        engine.close.assert_called_once()
        writer.seek(0)
        self.assertEqual([read_frame(writer)["id"] for _ in range(3)], [1, 2, 3])

    def test_resident_server_rejects_execution_and_reinitialization(self):
        for operation in ("physical_execute", "initialize"):
            requests = [
                {"id": 1, "op": "initialize", "options": {"model_dir": "/local"}},
                {"id": 2, "op": operation, "options": {}},
            ]
            output, engine = io.BytesIO(), Mock()
            engine.health.return_value = {}
            with (
                self.subTest(operation=operation),
                patch("jarvis_room.voice_stt.SpeechEngine", return_value=engine),
            ):
                resident_main(
                    "stt",
                    io.BytesIO(b"".join(encode_frame(item) for item in requests)),
                    output,
                )
            output.seek(0)
            read_frame(output)
            self.assertEqual(read_frame(output)["error"], "ipc_operation_forbidden")
            engine.transcribe.assert_not_called()
            engine.close.assert_called_once()

    def test_resident_server_rejects_extra_fields(self):
        requests = [
            {"id": 1, "op": "initialize", "options": {"model_dir": "/local"}},
            {"id": 2, "op": "transcribe", "audio": "", "command": "execute"},
        ]
        output, engine = io.BytesIO(), Mock()
        engine.health.return_value = {}
        with patch("jarvis_room.voice_stt.SpeechEngine", return_value=engine):
            resident_main(
                "stt",
                io.BytesIO(b"".join(encode_frame(item) for item in requests)),
                output,
            )
        output.seek(0)
        read_frame(output)
        self.assertEqual(read_frame(output)["error"], "ipc_invalid_message")
        engine.transcribe.assert_not_called()
