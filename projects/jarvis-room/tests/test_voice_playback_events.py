"""PCM, relógio DAC e IPC falsos: nenhum alto-falante ou modelo real."""

import base64
import io
import struct
import sys
import tempfile
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock, patch

from jarvis_room.voice_contract import VoiceCancelled, VoiceError
from jarvis_room.voice_playback import AmplitudeEnvelope, pcm_volume, play_pcm
from jarvis_room.voice_resident import ResidentWorker, encode_frame
from jarvis_room.voice_tts import ResidentSpeaker, tts_prerequisites
from jarvis_room.voice_worker import read_frame, resident_main
from voice_fakes import Clock, OfflineVoiceTest, wav


class PlaybackEventTests(OfflineVoiceTest):
    def test_normalization_and_smoothing_are_bounded(self):
        envelope = AmplitudeEnvelope()
        self.assertEqual(envelope.sample(bytes(100)), 0)
        peak = envelope.sample(struct.pack("<20h", *([-32768] * 20)))
        self.assertGreater(peak, 0)
        self.assertLess(peak, 1)
        release = envelope.sample(bytes(40))
        self.assertGreater(release, 0)
        self.assertLess(release, peak)

    def test_volume_is_applied_before_amplitude(self):
        pcm = struct.pack("<3h", 32767, -32768, 1000)
        self.assertEqual(pcm_volume(pcm, 0), bytes(6))
        self.assertEqual(
            struct.unpack("<3h", pcm_volume(pcm, 0.5)), (16383, -16384, 500)
        )
        for volume in (-1, 2, float("nan"), True):
            with self.subTest(volume=volume), self.assertRaises(VoiceError):
                pcm_volume(pcm, volume)

    def audio(self, *, failure=None):
        self.clock = Clock()
        self.events = []
        outer = self

        class CallbackStop(Exception):
            pass

        class CallbackAbort(Exception):
            pass

        class Stream:
            def __init__(self, **kwargs):
                self.options = kwargs
                self.closed = False
                self.buffers = []
                outer.stream = self

            def __enter__(self):
                if failure:
                    raise failure
                for index in range(2):
                    data = bytearray(1920)
                    try:
                        self.options["callback"](
                            data,
                            960,
                            SimpleNamespace(
                                currentTime=0, outputBufferDacTime=0.1 + index * 0.04
                            ),
                            False,
                        )
                    except CallbackStop:
                        self.buffers.append(bytes(data))
                        break
                    self.buffers.append(bytes(data))
                self.options["finished_callback"]()
                return self

            def __exit__(self, *_args):
                self.closed = True

        self.enterContext(
            patch.dict(
                sys.modules,
                {
                    "sounddevice": SimpleNamespace(
                        RawOutputStream=Stream,
                        CallbackStop=CallbackStop,
                        CallbackAbort=CallbackAbort,
                    )
                },
            )
        )
        return wav(seconds=0.08, rate=24000, amplitude=10000)

    def emit(self, event):
        self.events.append((self.clock(), event))

    def test_events_wait_for_dac_instead_of_firing_during_synthesis(self):
        audio = self.audio()
        play_pcm(
            audio,
            device=0,
            volume=0.7,
            timeout=1,
            cancel=Event(),
            emit=self.emit,
            clock=self.clock,
            wait=self.clock.wait,
        )
        playing = [
            (time, e)
            for time, e in self.events
            if e["type"] == "playback_status" and e["payload"]["state"] == "playing"
        ]
        energy = [
            (time, e)
            for time, e in self.events
            if e["type"] == "voice_amplitude" and e["payload"]["amplitude"] > 0
        ]
        self.assertEqual(len(playing), 1)
        self.assertEqual(len(energy), 2)
        self.assertGreaterEqual(playing[0][0], 0.1)
        self.assertGreater(energy[1][0], energy[0][0])
        self.assertEqual(self.events[-1][1]["payload"], {"amplitude": 0})
        self.assertTrue(self.stream.closed)

    def test_missing_output_never_reports_playing_or_positive_energy(self):
        audio = self.audio(failure=OSError("missing speakers"))
        with self.assertRaises(OSError):
            play_pcm(
                audio,
                device=0,
                volume=0.7,
                timeout=1,
                cancel=Event(),
                emit=self.emit,
                clock=self.clock,
                wait=self.clock.wait,
            )
        self.assertEqual(self.events[0][1]["payload"], {"state": "error"})
        self.assertEqual(self.events[-1][1]["payload"], {"amplitude": 0})

    def test_timeout_before_dac_zeroes_amplitude_and_closes_stream(self):
        audio = self.audio()
        with self.assertRaisesRegex(VoiceError, "playback_timeout"):
            play_pcm(
                audio,
                device=0,
                volume=0.7,
                timeout=0.05,
                cancel=Event(),
                emit=self.emit,
                clock=self.clock,
                wait=self.clock.wait,
            )
        self.assertFalse(
            any(e["payload"].get("state") == "playing" for _, e in self.events)
        )
        self.assertTrue(self.stream.closed)
        self.assertEqual(self.events[-1][1]["payload"], {"amplitude": 0})

    def test_cancel_during_playback_zeroes_amplitude_and_closes_stream(self):
        audio, cancel = self.audio(), Event()

        def wait(seconds):
            self.clock.wait(seconds)
            if self.clock() > 0.11:
                cancel.set()

        with self.assertRaises(VoiceCancelled):
            play_pcm(
                audio,
                device=0,
                volume=0.7,
                timeout=1,
                cancel=cancel,
                emit=self.emit,
                clock=self.clock,
                wait=wait,
            )
        self.assertTrue(self.stream.closed)
        self.assertEqual(self.events[-1][1]["payload"], {"amplitude": 0})


class SpeakerPresentationTests(OfflineVoiceTest):
    def assets(self):
        root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        for name in (
            "config.json",
            "kokoro-v1_0.pth",
            "voices/pm_santa.pt",
            "voices/pm_alex.pt",
        ):
            file = root / name
            file.parent.mkdir(exist_ok=True)
            file.write_bytes(b"fake")
        return str(root)

    def test_absent_tts_packages_are_detected_without_loading_models(self):
        with (
            patch("jarvis_room.voice_tts.version", side_effect=PackageNotFoundError),
            patch("jarvis_room.voice_tts.which", return_value="/usr/bin/espeak-ng"),
        ):
            result = tts_prerequisites(self.assets())
        self.assertFalse(result["ready"])
        self.assertIn("torch", result["missing"])

    def test_prepared_local_tts_prerequisites_are_reported_without_synthesis(self):
        with (
            patch("jarvis_room.voice_tts.version", return_value="test"),
            patch("jarvis_room.voice_tts.which", return_value="/usr/bin/espeak-ng"),
        ):
            self.assertTrue(tts_prerequisites(self.assets())["ready"])

    def test_synthesis_emits_no_positive_amplitude_before_output_worker(self):
        worker, playback = Mock(), Mock()
        events = []
        worker.request.return_value = {
            "audio": base64.b64encode(wav(rate=24000)).decode(),
            "metrics": {},
        }

        def play(*args, **kwargs):
            self.assertEqual([e["type"] for e in events], ["playback_status"])
            self.assertEqual(events[0]["payload"]["state"], "synthesizing")
            kwargs["on_event"](
                {"type": "playback_status", "payload": {"state": "playing"}}
            )
            kwargs["on_event"](
                {"type": "voice_amplitude", "payload": {"amplitude": 0.3}}
            )
            kwargs["on_event"](
                {"type": "playback_status", "payload": {"state": "idle"}}
            )

        playback.request.side_effect = play
        runner = self.runner(None)
        speaker = ResidentSpeaker(
            runner,
            self.assets(),
            worker=worker,
            on_playback=events.append,
            playback_factory=lambda: playback,
        )
        speaker.speak("Olá.", timeout=3, cancel=Event())
        playback.close.assert_called_once()
        runner.run.assert_not_called()
        self.assertEqual(events[-1]["payload"], {"amplitude": 0})

    def test_synthesis_failure_resets_events_without_starting_output(self):
        worker, factory, events = Mock(), Mock(), []
        worker.start.side_effect = VoiceError("tts_unavailable")
        speaker = ResidentSpeaker(
            self.runner(None),
            self.assets(),
            worker=worker,
            on_playback=events.append,
            playback_factory=factory,
        )
        with self.assertRaises(VoiceError):
            speaker.speak("Olá.", timeout=1, cancel=Event())
        factory.assert_not_called()
        self.assertEqual(events[-2]["payload"]["state"], "error")
        self.assertEqual(events[-1]["payload"]["amplitude"], 0)

    def test_playback_cancel_closes_child_and_zeroes_events(self):
        worker, playback, events = Mock(), Mock(), []
        worker.request.return_value = {
            "audio": base64.b64encode(wav(rate=24000)).decode(),
            "metrics": {},
        }
        playback.request.side_effect = VoiceCancelled("cancelled")
        speaker = ResidentSpeaker(
            self.runner(None),
            self.assets(),
            worker=worker,
            on_playback=events.append,
            playback_factory=lambda: playback,
        )
        with self.assertRaises(VoiceCancelled):
            speaker.speak("Olá.", timeout=2, cancel=Event())
        playback.close.assert_called_once()
        self.assertEqual(events[-1]["payload"]["amplitude"], 0)


class PlaybackProtocolTests(OfflineVoiceTest):
    def test_supervisor_consumes_typed_progress_before_final_result(self):
        worker = ResidentWorker("playback", {})
        worker.pipe = Mock()
        worker.pipe.receive.side_effect = [
            {
                "id": 1,
                "emittedAt": 100,
                "event": {"type": "playback_status", "payload": {"state": "playing"}},
            },
            {
                "id": 1,
                "emittedAt": 100,
                "event": {"type": "voice_amplitude", "payload": {"amplitude": 0.2}},
            },
            {"id": 1, "ok": True, "result": None},
        ]
        emit = Mock()
        with patch("jarvis_room.voice_resident.time.monotonic", return_value=100):
            worker._exchange("play", {}, timeout=1, cancel=Event(), on_event=emit)
        self.assertEqual(emit.call_count, 2)

    def test_progress_cannot_publish_commands_or_raw_audio(self):
        worker = ResidentWorker("playback", {})
        worker.pipe = Mock()
        worker.pipe.receive.return_value = {
            "id": 1,
            "emittedAt": 100,
            "event": {"type": "execute", "payload": {"script": "x"}},
        }
        with self.assertRaises(VoiceError):
            worker._exchange("play", {}, timeout=1, cancel=Event(), on_event=Mock())

    def test_delayed_progress_is_discarded_but_zero_is_always_delivered(self):
        worker = ResidentWorker("playback", {})
        worker.pipe = Mock()
        worker.pipe.receive.side_effect = [
            {
                "id": 1,
                "emittedAt": 99,
                "event": {"type": "playback_status", "payload": {"state": "playing"}},
            },
            {
                "id": 1,
                "emittedAt": 99,
                "event": {"type": "voice_amplitude", "payload": {"amplitude": 0.8}},
            },
            {
                "id": 1,
                "emittedAt": 99,
                "event": {"type": "voice_amplitude", "payload": {"amplitude": 0}},
            },
            {"id": 1, "ok": True, "result": None},
        ]
        emit = Mock()
        with patch("jarvis_room.voice_resident.time.monotonic", return_value=100):
            worker._exchange("play", {}, timeout=1, cancel=Event(), on_event=emit)
        emit.assert_called_once_with(
            {"type": "voice_amplitude", "payload": {"amplitude": 0}}
        )

    def test_worker_emits_framed_progress_on_same_private_channel(self):
        requests = [
            {"id": 1, "op": "initialize", "options": {}},
            {"id": 2, "op": "play", "options": {}},
        ]
        reader, writer = (
            io.BytesIO(b"".join(encode_frame(r) for r in requests)),
            io.BytesIO(),
        )
        engine = Mock()
        engine.health.return_value = {"backend": "portaudio"}

        def play(options, emit):
            emit({"type": "voice_amplitude", "payload": {"amplitude": 0}})

        engine.play.side_effect = play
        with patch("jarvis_room.voice_playback.PlaybackEngine", return_value=engine):
            resident_main("playback", reader, writer)
        output = io.BytesIO(writer.getvalue())
        read_frame(output)
        self.assertEqual(read_frame(output)["event"]["payload"], {"amplitude": 0})
        self.assertTrue(read_frame(output)["ok"])
        engine.close.assert_called_once()
