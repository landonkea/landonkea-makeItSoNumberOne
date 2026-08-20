# ───────────────────────────────────────────────────────────────────
# tests/test_voice_id.py, tests for core/voice_id.py
# ───────────────────────────────────────────────────────────────────
# Real synthesized tones (via core.audio's own sine-wave generator,
# same technique test_audio.py already uses), not mocked math -- pitch
# estimation is exactly the kind of thing that looks right by
# inspection and is subtly wrong in practice, so these feed real PCM16
# samples through estimate_pitch()/enroll()/identify() and check the
# actual numbers that come back, including that two clearly different
# pitches (an octave apart) are told apart, and that voice_profiles.json
# never touches the real one at the project root (a temp path is
# patched in for every test).
#
# HOW TO RUN
#   cd desktop
#   python3 -m unittest discover -s tests -v
# ───────────────────────────────────────────────────────────────────

import os
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import audio, voice_id  # noqa: E402


def _tone(frequency_hz, duration_ms=1000, volume=0.6, sample_rate=voice_id.SAMPLE_RATE):
    samples = audio._generate_sine_wave(frequency_hz, duration_ms, volume=volume)
    return struct.pack(f"<{len(samples)}h", *samples)


def _silence(duration_ms=1000, sample_rate=voice_id.SAMPLE_RATE):
    count = int(sample_rate * duration_ms / 1000)
    return struct.pack(f"<{count}h", *([0] * count))


class VoiceIdTests(unittest.TestCase):
    def setUp(self):
        # Every test gets its own scratch profiles file -- never the
        # real voice_profiles.json at the project root.
        self._tmpdir = tempfile.TemporaryDirectory()
        self._profiles_path = os.path.join(self._tmpdir.name, "voice_profiles.json")
        self._orig_path = voice_id._PROFILES_PATH
        voice_id._PROFILES_PATH = self._profiles_path

    def tearDown(self):
        voice_id._PROFILES_PATH = self._orig_path
        self._tmpdir.cleanup()

    # ── estimate_pitch ──────────────────────────────────────────────

    def test_estimate_pitch_finds_the_frequency_of_a_pure_tone(self):
        tone = _tone(150)
        samples = list(struct.unpack_from(f"<{len(tone) // 2}h", tone))
        pitch = voice_id.estimate_pitch(samples)
        self.assertIsNotNone(pitch)
        self.assertAlmostEqual(pitch, 150, delta=10)

    def test_estimate_pitch_returns_none_for_silence(self):
        silence = _silence()
        samples = list(struct.unpack_from(f"<{len(silence) // 2}h", silence))
        self.assertIsNone(voice_id.estimate_pitch(samples))

    # ── extract_voiceprint ──────────────────────────────────────────

    def test_extract_voiceprint_returns_none_for_silence(self):
        self.assertIsNone(voice_id.extract_voiceprint(_silence()))

    def test_extract_voiceprint_returns_none_for_very_short_audio(self):
        short_tone = _tone(150, duration_ms=100)  # well under 300ms
        self.assertIsNone(voice_id.extract_voiceprint(short_tone))

    def test_extract_voiceprint_returns_a_real_fingerprint_for_a_usable_tone(self):
        voiceprint = voice_id.extract_voiceprint(_tone(150))
        self.assertIsNotNone(voiceprint)
        self.assertAlmostEqual(voiceprint["pitch_hz"], 150, delta=10)
        self.assertGreater(voiceprint["rms"], 0)

    # ── enroll / identify ────────────────────────────────────────────

    def test_enroll_saves_a_profile_and_returns_true(self):
        self.assertTrue(voice_id.enroll("Landon", _tone(120)))
        self.assertEqual(voice_id.enrolled_names(), ["Landon"])

    def test_enroll_returns_false_and_saves_nothing_for_unusable_audio(self):
        self.assertFalse(voice_id.enroll("Landon", _silence()))
        self.assertEqual(voice_id.enrolled_names(), [])

    def test_identify_returns_none_when_nothing_is_enrolled(self):
        self.assertIsNone(voice_id.identify(_tone(150)))

    def test_identify_matches_the_closest_enrolled_voice(self):
        voice_id.enroll("Low Voice", _tone(100))
        voice_id.enroll("High Voice", _tone(300))

        self.assertEqual(voice_id.identify(_tone(105)), "Low Voice")
        self.assertEqual(voice_id.identify(_tone(290)), "High Voice")

    def test_identify_returns_none_when_nothing_is_close_enough(self):
        voice_id.enroll("Low Voice", _tone(100))
        # An octave-plus away from the only enrolled profile -- should
        # not get force-matched to the nearest (only) option.
        self.assertIsNone(voice_id.identify(_tone(390)))

    def test_identify_returns_none_for_unusable_audio(self):
        voice_id.enroll("Landon", _tone(150))
        self.assertIsNone(voice_id.identify(_silence()))

    def test_enroll_overwrites_an_existing_profile_for_the_same_name(self):
        voice_id.enroll("Landon", _tone(100))
        voice_id.enroll("Landon", _tone(300))

        self.assertEqual(voice_id.enrolled_names(), ["Landon"])
        self.assertEqual(voice_id.identify(_tone(300)), "Landon")


if __name__ == "__main__":
    unittest.main()
