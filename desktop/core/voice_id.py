# ── voice_id.py, tell household members apart by voice ─────────────
# Lets journal_entry_plugin.py attach WHO said something, not just
# WHAT (see plugins/examples/journal_entry_plugin.py and
# landonkea-soliloquy's own multi-speaker support). Pure Python, no
# numpy/scipy/librosa -- every other audio-adjacent piece of this app
# (audio.py's chime generator, its RMS loudness check) is hand-rolled
# the same way rather than reaching for a heavier library, so this
# follows suit.
#
# THIS IS NOT a neural speaker-embedding model (the kind
# Resemblyzer/pyannote/SpeechBrain use). It's classic, pre-deep-
# learning DSP: pitch (via autocorrelation) + loudness + zero-crossing
# rate (a rough timbre/brightness proxy), averaged into one small
# fingerprint per person. That means it's genuinely worse at telling
# apart two people with similar-pitched voices than a real embedding
# model would be, worth knowing going in, but it IS real signal
# (pitch/timbre are two of the main things that make voices sound
# different), works fully offline with zero setup and no model
# download, and is good enough to separate a household's voices in
# practice for what this is used for (labeling journal entries).
#
# Profiles live in voice_profiles.json next to this file's project
# root (desktop/), gitignored -- same treatment as
# conversation_history.json, this is personal biometric-ish data, it
# should never end up in git.
# ───────────────────────────────────────────────────────────────────

import json
import math
import os
import struct

SAMPLE_RATE = 22050  # matches audio.py's SAMPLE_RATE -- callers pass audio recorded there

MIN_PITCH_HZ = 80
MAX_PITCH_HZ = 400
_AUTOCORR_STEP = 4  # subsample the correlation sum -- see estimate_pitch()'s docstring
_MAX_SECONDS_ANALYZED = 3.0  # enough for a stable estimate without pitch-tracking a whole long entry

# A new utterance is "close enough" to an enrolled profile if the
# normalized distance is below this. Chosen empirically against real
# TTS-synthesized voices of a few different pitches (see
# tests/test_voice_id.py) -- not a formally derived threshold, revisit
# if real household use shows it's too loose/strict.
_MATCH_THRESHOLD = 0.35

_PROFILES_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "voice_profiles.json")


def _samples_from_pcm16(audio_data: bytes) -> list[int]:
    count = len(audio_data) // 2
    return list(struct.unpack_from(f"<{count}h", audio_data))


def estimate_pitch(samples: list[int], sample_rate: int = SAMPLE_RATE) -> float | None:
    """Fundamental frequency in Hz via autocorrelation: for each
    candidate lag (a time-shift), sum samples[i] * samples[i+lag] --
    the lag where a voiced signal lines up best with a shifted copy of
    itself IS its pitch period. Subsampled (_AUTOCORR_STEP) since a
    plain O(samples * lag_range) sum over a few seconds of real audio
    is slow enough in pure Python to matter otherwise. Returns None
    for silence/unvoiced audio (no lag correlates well)."""
    samples = samples[: int(sample_rate * _MAX_SECONDS_ANALYZED)]
    n = len(samples)
    min_lag = max(1, sample_rate // MAX_PITCH_HZ)
    max_lag = min(sample_rate // MIN_PITCH_HZ, n - 1)
    if max_lag <= min_lag:
        return None

    energy = sum(s * s for s in samples[::_AUTOCORR_STEP]) or 1

    best_lag, best_corr = None, 0.0
    for lag in range(min_lag, max_lag):
        corr = sum(samples[i] * samples[i + lag] for i in range(0, n - lag, _AUTOCORR_STEP))
        if corr > best_corr:
            best_corr, best_lag = corr, lag

    # A weak best-correlation (relative to the signal's own energy)
    # means nothing lined up well -- silence, noise, or unvoiced
    # sounds (like "s" or "f") rather than a real pitched voice.
    if best_lag is None or best_corr / energy < 0.15:
        return None
    return sample_rate / best_lag


def _zero_crossing_rate(samples: list[int]) -> float:
    if len(samples) < 2:
        return 0.0
    crossings = sum(1 for i in range(1, len(samples)) if (samples[i - 1] >= 0) != (samples[i] >= 0))
    return crossings / len(samples)


def _rms_energy(samples: list[int]) -> float:
    if not samples:
        return 0.0
    return math.sqrt(sum(s * s for s in samples) / len(samples))


def extract_voiceprint(audio_data: bytes, sample_rate: int = SAMPLE_RATE) -> dict | None:
    """A small fingerprint {"pitch_hz", "zcr", "rms"} for one
    utterance, or None if the audio was too quiet/short/unvoiced to
    say anything meaningful about (matches Transcriber's own
    convention elsewhere in this app: no signal means None, not a
    fabricated zero)."""
    samples = _samples_from_pcm16(audio_data)
    if len(samples) < sample_rate * 0.3:  # under ~300ms, not enough to say anything real
        return None

    pitch = estimate_pitch(samples, sample_rate)
    if pitch is None:
        return None

    return {"pitch_hz": pitch, "zcr": _zero_crossing_rate(samples), "rms": _rms_energy(samples)}


def _distance(a: dict, b: dict) -> float:
    """Normalized distance between two voiceprints -- each component
    scaled by roughly its own natural range first (pitch varies over
    hundreds of Hz, ZCR is a 0-1 fraction, RMS depends on recording
    volume) so no single component dominates just because its raw
    numbers happen to be bigger."""
    pitch_diff = abs(a["pitch_hz"] - b["pitch_hz"]) / MAX_PITCH_HZ
    zcr_diff = abs(a["zcr"] - b["zcr"])
    rms_diff = abs(a["rms"] - b["rms"]) / max(a["rms"], b["rms"], 1.0)
    return (pitch_diff * 0.6) + (zcr_diff * 0.25) + (rms_diff * 0.15)


def _load_profiles() -> dict:
    if not os.path.exists(_PROFILES_PATH):
        return {}
    with open(_PROFILES_PATH) as f:
        return json.load(f)


def _save_profiles(profiles: dict) -> None:
    with open(_PROFILES_PATH, "w") as f:
        json.dump(profiles, f, indent=2)


def enroll(name: str, audio_data: bytes, sample_rate: int = SAMPLE_RATE) -> bool:
    """Saves (or overwrites) a voice profile for `name` from one
    recording. Returns False (and saves nothing) if the recording
    wasn't usable -- same "too quiet/short/unvoiced" check as
    extract_voiceprint(); a bad enrollment recording would otherwise
    silently produce a profile that never matches anyone, including
    the person it's supposed to represent."""
    voiceprint = extract_voiceprint(audio_data, sample_rate)
    if voiceprint is None:
        return False

    profiles = _load_profiles()
    profiles[name] = voiceprint
    _save_profiles(profiles)
    return True


def identify(audio_data: bytes, sample_rate: int = SAMPLE_RATE) -> str | None:
    """Best-guess enrolled speaker for this utterance, or None if
    nothing's enrolled, the audio wasn't usable, or the closest match
    still isn't close enough (_MATCH_THRESHOLD) -- an uncertain guess
    is worse than no guess for something that ends up labeling a
    journal entry, so this only ever returns a name it's reasonably
    confident about."""
    profiles = _load_profiles()
    if not profiles:
        return None

    voiceprint = extract_voiceprint(audio_data, sample_rate)
    if voiceprint is None:
        return None

    best_name, best_distance = None, float("inf")
    for name, profile in profiles.items():
        distance = _distance(voiceprint, profile)
        if distance < best_distance:
            best_name, best_distance = name, distance

    return best_name if best_distance < _MATCH_THRESHOLD else None


def enrolled_names() -> list[str]:
    return sorted(_load_profiles().keys())
