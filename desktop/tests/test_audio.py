# ───────────────────────────────────────────────────────────────────
# tests/test_audio.py, tests for core/audio.py
# ───────────────────────────────────────────────────────────────────
# WHY THESE TESTS EXIST
# ----------------------
# core/audio.py mixes pure computation (sine wave / silence sample
# generation, RMS loudness, the record-until-silence state machine)
# with real I/O (microphone access via pyaudio, playback via
# afplay/aplay/start). The computation is fully testable without any
# hardware, and the I/O boundary, PyAudio's stream object and
# os.system(), is narrow enough to fake or mock. These tests cover
# both: the chime's actual generated WAV content (written to a temp
# file, never desktop/assets/), the loudness math against
# hand-computed RMS values, the silence-detection loop against a
# scripted fake microphone stream, and each platform's playback
# command against a mocked os.system() (never actually invoked).
#
# HOW TO RUN
# ----------
#   cd desktop
#   python3 -m unittest discover -s tests -v
# ───────────────────────────────────────────────────────────────────

import math
import os
import struct
import sys
import tempfile
import unittest
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import audio  # noqa: E402


# ── _generate_sine_wave() / _generate_silence() ────────────────────
class SampleGenerationTests(unittest.TestCase):
    def test_sine_wave_sample_count_matches_duration(self):
        samples = audio._generate_sine_wave(440, 100)
        expected = int(audio.SAMPLE_RATE * 100 / 1000)
        self.assertEqual(len(samples), expected)

    def test_sine_wave_first_sample_is_at_amplitude_zero(self):
        # sin(2*pi*f*0) == 0, so sample index 0 is always silent
        # regardless of frequency or volume.
        samples = audio._generate_sine_wave(880, 50, volume=0.9)
        self.assertEqual(samples[0], 0)

    def test_sine_wave_stays_within_16_bit_signed_range(self):
        samples = audio._generate_sine_wave(880, 200, volume=1.0)
        for s in samples:
            self.assertGreaterEqual(s, -32767)
            self.assertLessEqual(s, 32767)

    def test_higher_volume_produces_louder_peak_amplitude(self):
        quiet = audio._generate_sine_wave(1000, 50, volume=0.2)
        loud = audio._generate_sine_wave(1000, 50, volume=0.8)
        self.assertLess(max(abs(s) for s in quiet), max(abs(s) for s in loud))

    def test_silence_is_all_zeros_of_the_right_length(self):
        samples = audio._generate_silence(75)
        expected = int(audio.SAMPLE_RATE * 75 / 1000)
        self.assertEqual(len(samples), expected)
        self.assertTrue(all(s == 0 for s in samples))


# ── generate_chime() ────────────────────────────────────────────────
class GenerateChimeTests(unittest.TestCase):
    def test_writes_a_valid_wav_with_the_right_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, "chime.wav")
            audio.generate_chime(out_path)

            self.assertTrue(os.path.exists(out_path))
            with wave.open(out_path, "rb") as wf:
                self.assertEqual(wf.getnchannels(), audio.CHANNELS)
                self.assertEqual(wf.getsampwidth(), audio.SAMPLE_WIDTH)
                self.assertEqual(wf.getframerate(), audio.SAMPLE_RATE)
                # Two tones (150ms + 120ms) plus a 50ms gap, each
                # rounded to a whole number of samples independently
                # (matching generate_chime()'s own per-segment
                # rounding, which doesn't necessarily equal rounding
                # the 320ms total in one shot).
                expected_frames = (
                    int(audio.SAMPLE_RATE * 150 / 1000)
                    + int(audio.SAMPLE_RATE * 50 / 1000)
                    + int(audio.SAMPLE_RATE * 120 / 1000)
                )
                self.assertEqual(wf.getnframes(), expected_frames)

    def test_chime_is_not_silent(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_path = os.path.join(tmp, "chime.wav")
            audio.generate_chime(out_path)
            with wave.open(out_path, "rb") as wf:
                raw = wf.readframes(wf.getnframes())
            samples = struct.unpack_from("<" + "h" * (len(raw) // 2), raw)
            self.assertTrue(any(s != 0 for s in samples))


# ── _chunk_loudness() ───────────────────────────────────────────────
class ChunkLoudnessTests(unittest.TestCase):
    def test_silence_has_zero_loudness(self):
        chunk = struct.pack("<hhhh", 0, 0, 0, 0)
        self.assertEqual(audio._chunk_loudness(chunk), 0)

    def test_empty_chunk_returns_zero_without_raising(self):
        self.assertEqual(audio._chunk_loudness(b""), 0)

    def test_matches_hand_computed_rms(self):
        values = (1000, -2000, 3000, -4000)
        chunk = struct.pack("<hhhh", *values)
        expected = math.sqrt(sum(v * v for v in values) / len(values))
        self.assertAlmostEqual(audio._chunk_loudness(chunk), expected, places=6)

    def test_louder_samples_produce_higher_rms(self):
        quiet = struct.pack("<hh", 100, -100)
        loud = struct.pack("<hh", 10000, -10000)
        self.assertLess(audio._chunk_loudness(quiet), audio._chunk_loudness(loud))


# ── _record_chunks_until_silence() ──────────────────────────────────
class _FakeMicStream:
    """Fake PyAudio input stream. Serves pre-built chunks in order and
    raises if asked to read past the end, standing in for the real
    microphone boundary record_until_silence() calls through."""

    def __init__(self, chunks):
        self._chunks = list(chunks)
        self.read_calls = 0

    def read(self, chunk_size, exception_on_overflow=False):
        self.read_calls += 1
        if not self._chunks:
            raise AssertionError("fake mic stream ran out of chunks")
        return self._chunks.pop(0)


def _loud_chunk(chunk_size=4):
    # Well above SILENCE_THRESHOLD (500).
    return struct.pack("<" + "h" * chunk_size, *([20000] * chunk_size))


def _quiet_chunk(chunk_size=4):
    # Well below SILENCE_THRESHOLD.
    return struct.pack("<" + "h" * chunk_size, *([0] * chunk_size))


class RecordChunksUntilSilenceTests(unittest.TestCase):
    def test_leading_silence_before_speech_is_discarded(self):
        rate = 4  # 1 chunk == 1 "second" at chunk_size=4, keeps the math simple
        chunk_size = 4
        chunks = [_quiet_chunk(), _quiet_chunk(), _loud_chunk()]
        # Enough trailing silence chunks to cross the 1.5s silence limit.
        chunks += [_quiet_chunk()] * 2
        stream = _FakeMicStream(chunks)

        frames = audio._record_chunks_until_silence(
            stream, chunk_size, rate,
            timeout_seconds=10, silence_limit_seconds=1.5
        )

        # The two leading silent chunks (before speech ever started)
        # must not appear in the result.
        self.assertEqual(len(frames), 3)

    def test_stops_after_silence_limit_following_speech(self):
        rate = 4
        chunk_size = 4
        # 1 loud chunk, then quiet chunks until 1.5s of trailing
        # silence (>= 6 chunks at this rate/chunk_size) triggers stop.
        chunks = [_loud_chunk()] + [_quiet_chunk()] * 6
        stream = _FakeMicStream(chunks)

        frames = audio._record_chunks_until_silence(
            stream, chunk_size, rate,
            timeout_seconds=10, silence_limit_seconds=1.5
        )

        # Loop should have stopped as soon as the silence limit was
        # crossed rather than reading every chunk we supplied.
        self.assertLess(stream.read_calls, len(chunks))
        self.assertGreaterEqual(len(frames), 1)

    def test_never_speaking_returns_empty_list_at_timeout(self):
        rate = 4
        chunk_size = 4
        chunks = [_quiet_chunk() for _ in range(8)]
        stream = _FakeMicStream(chunks)

        frames = audio._record_chunks_until_silence(
            stream, chunk_size, rate,
            timeout_seconds=2, silence_limit_seconds=1.5
        )

        self.assertEqual(frames, [])

    def test_timeout_caps_total_reads_even_without_silence(self):
        rate = 4
        chunk_size = 4
        # Continuous speech, never enough trailing silence to stop
        # naturally, only the timeout should end the loop.
        chunks = [_loud_chunk() for _ in range(100)]
        stream = _FakeMicStream(chunks)

        frames = audio._record_chunks_until_silence(
            stream, chunk_size, rate,
            timeout_seconds=2, silence_limit_seconds=1.5
        )

        max_chunks = int(2 * rate / chunk_size)
        self.assertEqual(stream.read_calls, max_chunks)
        self.assertEqual(len(frames), max_chunks)


# ── platform-specific playback commands ────────────────────────────
class PlaybackCommandTests(unittest.TestCase):
    """Verifies each platform's playback helper shells out to the
    right command, mocking os.system() so no audio is ever actually
    played and no subprocess is spawned."""

    def setUp(self):
        self._orig_system = audio.os.system
        self.calls = []
        audio.os.system = lambda cmd: self.calls.append(cmd)

    def tearDown(self):
        audio.os.system = self._orig_system

    def test_macos_uses_afplay(self):
        audio._play_sound_osx("/tmp/chime.wav")
        self.assertEqual(self.calls, ['afplay "/tmp/chime.wav"'])

    def test_linux_uses_aplay(self):
        audio._play_sound_linux("/tmp/chime.wav")
        self.assertEqual(self.calls, ['aplay "/tmp/chime.wav"'])

    def test_windows_uses_start(self):
        audio._play_sound_windows("/tmp/chime.wav")
        self.assertEqual(self.calls, ['start "" "/tmp/chime.wav"'])


class PlayChimeDispatchTests(unittest.TestCase):
    """play_chime() itself, checking it dispatches to the right
    per-platform helper and reuses an already-generated chime file
    instead of regenerating it."""

    def setUp(self):
        self._orig_osx = audio._play_sound_osx
        self._orig_linux = audio._play_sound_linux
        self._orig_windows = audio._play_sound_windows
        self._orig_generate = audio.generate_chime
        self._orig_exists = audio.os.path.exists
        self._orig_makedirs = audio.os.makedirs
        self.dispatched = []
        audio._play_sound_osx = lambda p: self.dispatched.append(("osx", p))
        audio._play_sound_linux = lambda p: self.dispatched.append(("linux", p))
        audio._play_sound_windows = lambda p: self.dispatched.append(("windows", p))
        self.generate_calls = []
        audio.generate_chime = lambda p: self.generate_calls.append(p)
        # Pretend the chime file already exists so we never touch disk.
        audio.os.path.exists = lambda p: True

    def tearDown(self):
        audio._play_sound_osx = self._orig_osx
        audio._play_sound_linux = self._orig_linux
        audio._play_sound_windows = self._orig_windows
        audio.generate_chime = self._orig_generate
        audio.os.path.exists = self._orig_exists
        audio.os.makedirs = self._orig_makedirs

    def _run_with_fake_os(self, os_name):
        import platform as real_platform
        orig = real_platform.system
        real_platform.system = lambda: os_name
        try:
            audio.play_chime()
        finally:
            real_platform.system = orig

    def test_darwin_dispatches_to_osx_player(self):
        self._run_with_fake_os("Darwin")
        self.assertEqual(self.dispatched[0][0], "osx")
        self.assertEqual(self.generate_calls, [])

    def test_linux_dispatches_to_linux_player(self):
        self._run_with_fake_os("Linux")
        self.assertEqual(self.dispatched[0][0], "linux")

    def test_windows_dispatches_to_windows_player(self):
        self._run_with_fake_os("Windows")
        self.assertEqual(self.dispatched[0][0], "windows")

    def test_existing_chime_file_is_not_regenerated(self):
        self._run_with_fake_os("Darwin")
        self.assertEqual(self.generate_calls, [])

    def test_missing_chime_file_is_generated_first(self):
        audio.os.path.exists = lambda p: False
        audio.os.makedirs = lambda *a, **kw: None
        self._run_with_fake_os("Darwin")
        self.assertEqual(len(self.generate_calls), 1)
        self.assertEqual(self.dispatched[0][0], "osx")


if __name__ == "__main__":
    unittest.main()
