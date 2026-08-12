# ───────────────────────────────────────────────────────────────────
# tests/test_wake_word.py, tests for core/wake_word.py
# ───────────────────────────────────────────────────────────────────
# WHY THESE TESTS EXIST
# ----------------------
# core/wake_word.py listens to a real microphone through Porcupine, a
# third-party wake word engine, neither of which is available in a
# test environment. What CAN be tested without any hardware or the
# pvporcupine/pyaudio packages installed is everything wait_for_wake_
# word() is built out of: the detection loop's frame-by-frame logic
# (feed it fake PCM frames and a fake Porcupine that reports "heard
# it" on a chosen frame), the missing-library and missing-access-key
# guards, and that the orchestration function always releases the
# microphone/Porcupine, even when Ctrl+C or an error interrupts it.
# All of this is done by swapping in fakes at the same boundary the
# real code calls through (pvporcupine, pyaudio, the audio stream),
# never by touching a real microphone.
#
# HOW TO RUN
# ----------
#   cd desktop
#   python3 -m unittest discover -s tests -v
# ───────────────────────────────────────────────────────────────────

import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import wake_word  # noqa: E402


def _pcm_frame(frame_length, value=0):
    """Build one fake frame of little-endian 16-bit PCM samples, all
    set to `value`, the same shape audio_stream.read() hands back in
    the real code."""
    return struct.pack("<" + "h" * frame_length, *([value] * frame_length))


class _FakePorcupine:
    """Stands in for a pvporcupine handle. `hits` maps a call index
    (0-based) to the keyword index process() should report for that
    call; any call not listed reports -1 (nothing heard)."""

    def __init__(self, frame_length=4, sample_rate=16000, hits=None):
        self.frame_length = frame_length
        self.sample_rate = sample_rate
        self._hits = hits or {}
        self.process_calls = []
        self.deleted = False

    def process(self, pcm_tuple):
        index = len(self.process_calls)
        self.process_calls.append(pcm_tuple)
        return self._hits.get(index, -1)

    def delete(self):
        self.deleted = True


class _FakeAudioStream:
    """Stands in for the PyAudio stream object. Serves pre-built PCM
    frames from `frames` in order and records read()/stop_stream()/
    close() calls so tests can assert cleanup actually happened."""

    def __init__(self, frames):
        self._frames = list(frames)
        self.read_calls = 0
        self.stopped = False
        self.closed = False

    def read(self, frame_length, exception_on_overflow=False):
        self.read_calls += 1
        return self._frames.pop(0)

    def stop_stream(self):
        self.stopped = True

    def close(self):
        self.closed = True


# ── _detection_loop() ──────────────────────────────────────────────
class DetectionLoopTests(unittest.TestCase):
    def test_returns_true_as_soon_as_wake_word_is_heard(self):
        porcupine = _FakePorcupine(frame_length=4, hits={0: 0})
        stream = _FakeAudioStream([_pcm_frame(4)])

        result = wake_word._detection_loop(porcupine, stream)

        self.assertTrue(result)
        self.assertEqual(stream.read_calls, 1)

    def test_keeps_listening_through_silent_frames_before_detecting(self):
        porcupine = _FakePorcupine(frame_length=4, hits={3: 0})
        stream = _FakeAudioStream([_pcm_frame(4) for _ in range(4)])

        result = wake_word._detection_loop(porcupine, stream)

        self.assertTrue(result)
        # Three silent frames read (and ignored, index -1) before the
        # fourth call reports the keyword.
        self.assertEqual(stream.read_calls, 4)
        self.assertEqual(len(porcupine.process_calls), 4)

    def test_raw_bytes_are_unpacked_into_the_exact_samples_porcupine_receives(self):
        porcupine = _FakePorcupine(frame_length=3, hits={0: 0})
        frame = struct.pack("<hhh", 100, -200, 32000)
        stream = _FakeAudioStream([frame])

        wake_word._detection_loop(porcupine, stream)

        self.assertEqual(porcupine.process_calls[0], (100, -200, 32000))

    def test_reads_exactly_porcupines_frame_length_each_call(self):
        # frame_length isn't hard-coded anywhere in the loop, it must
        # come from the porcupine handle, so a non-default value
        # should still round-trip correctly.
        porcupine = _FakePorcupine(frame_length=8, hits={0: 0})
        stream = _FakeAudioStream([_pcm_frame(8)])

        wake_word._detection_loop(porcupine, stream)

        self.assertEqual(len(porcupine.process_calls[0]), 8)


# ── _import_pvporcupine() / _import_pyaudio() ──────────────────────
class MissingLibraryImportTests(unittest.TestCase):
    """Simulate an uninstalled optional dependency by pointing
    sys.modules at None for its name, the same trick Python's import
    machinery treats as "this import always raises ImportError"."""

    def _simulate_missing(self, module_name):
        self._had_entry = module_name in sys.modules
        self._orig = sys.modules.get(module_name)
        sys.modules[module_name] = None

    def _restore(self, module_name):
        if self._had_entry:
            sys.modules[module_name] = self._orig
        else:
            sys.modules.pop(module_name, None)

    def test_missing_pvporcupine_returns_none(self):
        self._simulate_missing("pvporcupine")
        try:
            self.assertIsNone(wake_word._import_pvporcupine())
        finally:
            self._restore("pvporcupine")

    def test_missing_pyaudio_returns_none(self):
        self._simulate_missing("pyaudio")
        try:
            self.assertIsNone(wake_word._import_pyaudio())
        finally:
            self._restore("pyaudio")


# ── _init_porcupine() ──────────────────────────────────────────────
class InitPorcupineTests(unittest.TestCase):
    class _FakePvporcupineModule:
        def __init__(self, result=None, raises=None):
            self._result = result
            self._raises = raises
            self.create_kwargs = None

        def create(self, **kwargs):
            self.create_kwargs = kwargs
            if self._raises:
                raise self._raises
            return self._result

    def test_success_returns_the_created_instance_and_forwards_the_key(self):
        fake_instance = object()
        module = self._FakePvporcupineModule(result=fake_instance)

        result = wake_word._init_porcupine(module, "my-access-key")

        self.assertIs(result, fake_instance)
        self.assertEqual(module.create_kwargs["access_key"], "my-access-key")
        self.assertEqual(module.create_kwargs["keywords"], ["computer"])

    def test_exception_during_create_is_caught_and_returns_none(self):
        module = self._FakePvporcupineModule(raises=ValueError("bad access key"))

        result = wake_word._init_porcupine(module, "bad-key")

        self.assertIsNone(result)


# ── wait_for_wake_word() orchestration ─────────────────────────────
class WaitForWakeWordOrchestrationTests(unittest.TestCase):
    """Patches the module-level helper functions wait_for_wake_word()
    calls through, so the whole flow can be driven without pvporcupine
    or pyaudio being installed and without a real microphone."""

    def setUp(self):
        self._orig_import_pvporcupine = wake_word._import_pvporcupine
        self._orig_import_pyaudio = wake_word._import_pyaudio
        self._orig_init_porcupine = wake_word._init_porcupine
        self._orig_detection_loop = wake_word._detection_loop

    def tearDown(self):
        wake_word._import_pvporcupine = self._orig_import_pvporcupine
        wake_word._import_pyaudio = self._orig_import_pyaudio
        wake_word._init_porcupine = self._orig_init_porcupine
        wake_word._detection_loop = self._orig_detection_loop

    def test_missing_pvporcupine_library_returns_false_without_touching_pyaudio(self):
        wake_word._import_pvporcupine = lambda: None
        pyaudio_called = []
        wake_word._import_pyaudio = lambda: pyaudio_called.append(True)

        result = wake_word.wait_for_wake_word({"porcupine_access_key": "key"})

        self.assertFalse(result)
        self.assertEqual(pyaudio_called, [])

    def test_missing_access_key_returns_false_without_initializing_porcupine(self):
        wake_word._import_pvporcupine = lambda: object()
        wake_word._import_pyaudio = lambda: object()
        init_called = []
        wake_word._init_porcupine = lambda *a: init_called.append(True)

        result = wake_word.wait_for_wake_word({})

        self.assertFalse(result)
        self.assertEqual(init_called, [])

    def test_porcupine_init_failure_returns_false(self):
        wake_word._import_pvporcupine = lambda: object()
        wake_word._import_pyaudio = lambda: object()
        wake_word._init_porcupine = lambda *a: None

        result = wake_word.wait_for_wake_word({"porcupine_access_key": "key"})

        self.assertFalse(result)

    def _patch_full_success_path(self, porcupine, stream, holder):
        wake_word._import_pvporcupine = lambda: object()

        class _FakePyAudioModule:
            paInt16 = "paInt16"

            def PyAudio(self):
                p = _FakePyAudioObject(stream)
                holder["p"] = p
                return p

        class _FakePyAudioObject:
            def __init__(self, stream):
                self._stream = stream
                self.terminated = False

            def open(self, **kwargs):
                holder["open_kwargs"] = kwargs
                return self._stream

            def terminate(self):
                self.terminated = True

        wake_word._import_pyaudio = lambda: _FakePyAudioModule()
        wake_word._init_porcupine = lambda *a: porcupine

    def test_happy_path_returns_true_and_cleans_up_everything(self):
        porcupine = _FakePorcupine(frame_length=4, hits={0: 0})
        stream = _FakeAudioStream([_pcm_frame(4)])
        holder = {}
        self._patch_full_success_path(porcupine, stream, holder)

        result = wake_word.wait_for_wake_word({"porcupine_access_key": "key"})

        self.assertTrue(result)
        self.assertTrue(stream.stopped)
        self.assertTrue(stream.closed)
        self.assertTrue(holder["p"].terminated)
        self.assertTrue(porcupine.deleted)
        # The stream should have been opened at Porcupine's required
        # sample rate/frame size, not some hard-coded default.
        self.assertEqual(holder["open_kwargs"]["rate"], porcupine.sample_rate)
        self.assertEqual(holder["open_kwargs"]["frames_per_buffer"], porcupine.frame_length)

    def test_keyboard_interrupt_during_listening_returns_false_but_still_cleans_up(self):
        porcupine = _FakePorcupine(frame_length=4)
        stream = _FakeAudioStream([])
        holder = {}
        self._patch_full_success_path(porcupine, stream, holder)
        wake_word._detection_loop = lambda *a: (_ for _ in ()).throw(KeyboardInterrupt())

        result = wake_word.wait_for_wake_word({"porcupine_access_key": "key"})

        self.assertFalse(result)
        self.assertTrue(stream.stopped)
        self.assertTrue(stream.closed)
        self.assertTrue(holder["p"].terminated)
        self.assertTrue(porcupine.deleted)


if __name__ == "__main__":
    unittest.main()
