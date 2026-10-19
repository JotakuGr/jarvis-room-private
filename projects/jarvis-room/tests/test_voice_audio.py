"""WAV sintético e callbacks falsos exercitam limites sem abrir PortAudio."""

import queue
import struct
import sys
from contextlib import contextmanager
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock, patch

from jarvis_room.voice_audio import CHUNK, SoundDeviceMicrophone, play_audio, wav_pcm
from jarvis_room.voice_contract import VoiceCancelled, VoiceError
from voice_fakes import Clock, OfflineVoiceTest, wav

SPEECH = struct.pack(f"<{CHUNK}h", *([2000] * CHUNK))
SILENCE = bytes(CHUNK * 2)


class VoiceAudioTests(OfflineVoiceTest):
    def test_valid_synthetic_wav(self):
        self.assertEqual(len(wav_pcm(wav(seconds=1))), 32000)

    def test_stereo_wrong_rate_width_rejected(self):
        for options in ({"channels": 2}, {"rate": 8000}, {"width": 1}):
            with self.subTest(options=options), self.assertRaises(VoiceError):
                wav_pcm(wav(**options))

    def test_truncated_wav(self):
        with self.assertRaises(VoiceError):
            wav_pcm(wav()[:-100])

    def test_invalid_audio_and_duration(self):
        for data in (b"invalid", b"", wav(seconds=0), b"x" * 1000000):
            with self.subTest(length=len(data)), self.assertRaises(VoiceError):
                wav_pcm(data)

    def fake_capture(self, frames, **kwargs):
        mic = SoundDeviceMicrophone(
            startup_seconds=0.24, silence_seconds=0.24, **kwargs
        )

        @contextmanager
        def source(**options):
            yield iter(frames)

        mic.frames = source
        return mic

    def test_initial_silence(self):
        mic = self.fake_capture([SILENCE] * 10)
        self.assertEqual(mic.capture(timeout=2, cancel=Event()), b"")

    def test_impulse_noise_is_not_speech(self):
        mic = self.fake_capture([SPEECH] + [SILENCE] * 8)
        self.assertEqual(mic.capture(timeout=2, cancel=Event()), b"")

    def test_separated_impulses_do_not_accumulate_as_speech(self):
        mic = self.fake_capture([SPEECH, SILENCE] * 20)
        self.assertEqual(mic.capture(timeout=2, cancel=Event()), b"")

    def test_speech_then_silence_yields_wav(self):
        mic = self.fake_capture([SPEECH] * 3 + [SILENCE] * 3)
        data = mic.capture(timeout=2, cancel=Event())
        self.assertEqual(wav_pcm(data), SPEECH * 3 + SILENCE * 3)

    def test_truncated_utterance_not_transcribed(self):
        mic = self.fake_capture([SPEECH] * 40)
        with self.assertRaises(VoiceError):
            mic.capture(timeout=1, cancel=Event())

    def test_cancelled_capture(self):
        mic = self.fake_capture([SPEECH] * 3)
        cancel = Event()
        cancel.set()
        with self.assertRaises(VoiceCancelled):
            mic.capture(timeout=1, cancel=cancel)

    def test_capture_timeout_invalid(self):
        mic = self.fake_capture([])
        for value in (0, 31, float("nan")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                mic.capture(timeout=value, cancel=Event())

    def install_stream(self, frames=(), status=False):
        stream = Mock()
        stream.__exit__ = Mock(return_value=False)

        def create(**options):
            self.stream_options = options

            def enter():
                for frame in frames:
                    options["callback"](frame, CHUNK, None, status)
                return stream

            stream.__enter__ = Mock(side_effect=enter)
            return stream

        sd = SimpleNamespace(RawInputStream=Mock(side_effect=create))
        self.enterContext(patch.dict(sys.modules, {"sounddevice": sd}))
        self.stream = stream
        return sd

    def test_frame_queue_device_and_cleanup(self):
        self.install_stream([SPEECH])
        mic = SoundDeviceMicrophone(device=7)
        with mic.frames(timeout=1, cancel=Event()) as source:
            self.assertEqual(next(source), SPEECH)
        self.assertIsNone(mic._stream)
        self.assertEqual(self.stream_options["device"], 7)
        self.stream.__exit__.assert_called_once()

    def test_audio_overflow_discards_pending_frames(self):
        self.install_stream([SPEECH] * 9)
        mic = SoundDeviceMicrophone()
        with self.assertRaisesRegex(VoiceError, "audio_overflow"):
            with mic.frames(timeout=1, cancel=Event()) as source:
                next(source)
        self.assertIsNone(mic._stream)

    def test_pending_buffer_is_not_reused_in_next_stream(self):
        self.install_stream([SPEECH, SILENCE])
        mic = SoundDeviceMicrophone()
        with mic.frames(timeout=1, cancel=Event()) as source:
            self.assertEqual(next(source), SPEECH)
        self.install_stream([SPEECH])
        with mic.frames(timeout=1, cancel=Event()) as source:
            self.assertEqual(next(source), SPEECH)  # silêncio pendente foi descartado

    def fake_playback(self, *, active=False, length=480, finite=True):
        class Samples:
            ndim = 1

            def __len__(self):
                return length

            def __mul__(self, volume):
                return ("scaled", volume)

        numpy = SimpleNamespace(
            isfinite=lambda data: SimpleNamespace(all=lambda: finite),
            clip=Mock(return_value="clipped"),
        )
        sd = Mock()
        sd.get_stream.return_value.active = active
        sf = SimpleNamespace(read=Mock(return_value=(Samples(), 24000)))
        self.enterContext(
            patch.dict(
                sys.modules,
                {
                    "numpy": numpy,
                    "sounddevice": sd,
                    "soundfile": sf,
                },
            )
        )
        return sd, numpy

    def test_playback_volume_device_and_cleanup(self):
        sd, numpy = self.fake_playback()
        play_audio(b"fake WAV", device=4, volume=0.3, timeout=1, cancel=Event())
        numpy.clip.assert_called_once_with(("scaled", 0.3), -1, 1)
        sd.play.assert_called_once_with("clipped", 24000, device=4)
        sd.stop.assert_called_once()

    def test_playback_timeout_stops_device(self):
        sd, _ = self.fake_playback(active=True)
        with patch("time.monotonic", side_effect=[0, 2]), self.assertRaises(VoiceError):
            play_audio(b"fake WAV", device=None, volume=1, timeout=1, cancel=Event())
        sd.stop.assert_called_once()

    def test_playback_cancel_stops_device(self):
        sd, _ = self.fake_playback(active=True)
        cancel = Event()
        sd.get_stream.side_effect = lambda: cancel.set() or SimpleNamespace(active=True)
        with self.assertRaises(VoiceCancelled):
            play_audio(b"fake WAV", device=None, volume=1, timeout=1, cancel=cancel)
        sd.stop.assert_called_once()

    def test_playback_failure_stops_device(self):
        sd, _ = self.fake_playback()
        sd.play.side_effect = OSError("unplugged")
        with self.assertRaises(OSError):
            play_audio(b"fake WAV", device=None, volume=1, timeout=1, cancel=Event())
        sd.stop.assert_called_once()

    def test_invalid_or_oversized_tts_audio_never_plays(self):
        for options in ({"finite": False}, {"length": 24000 * 121}):
            sd, _ = self.fake_playback(**options)
            with self.subTest(options=options), self.assertRaises(VoiceError):
                play_audio(
                    b"fake WAV", device=None, volume=1, timeout=120, cancel=Event()
                )
            sd.play.assert_not_called()

    def test_portaudio_status_rejected(self):
        self.install_stream([SPEECH], status=True)
        mic = SoundDeviceMicrophone()
        with self.assertRaises(VoiceError):
            with mic.frames(timeout=1, cancel=Event()) as source:
                next(source)

    def test_invalid_frame_rejected(self):
        self.install_stream([b"bad"])
        with self.assertRaises(VoiceError):
            with SoundDeviceMicrophone().frames(timeout=1, cancel=Event()) as source:
                next(source)

    def test_stalled_audio_times_out_virtual_clock(self):
        self.install_stream()
        clock = Clock()

        def empty(**kwargs):
            clock.wait(kwargs["timeout"])
            raise queue.Empty()

        with patch("queue.Queue.get", side_effect=empty):
            with SoundDeviceMicrophone(clock=clock).frames(
                timeout=0.2, cancel=Event()
            ) as source:
                self.assertEqual(list(source), [])
        self.assertGreaterEqual(clock.now, 0.2)

    def test_hardware_missing(self):
        sd = self.install_stream()
        sd.RawInputStream.side_effect = OSError("no microphone")
        with self.assertRaises(OSError):
            SoundDeviceMicrophone().capture(timeout=1, cancel=Event())

    def test_capture_config_validation(self):
        for options in (
            {"threshold": 0},
            {"threshold": True},
            {"silence_seconds": float("nan")},
            {"startup_seconds": 0},
        ):
            with self.subTest(options=options), self.assertRaises(ValueError):
                SoundDeviceMicrophone(**options)
