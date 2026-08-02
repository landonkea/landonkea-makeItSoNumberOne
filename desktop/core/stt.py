# ── stt.py — Speech-to-Text (Online via Whisper + Offline via Vosk) ──
# This module converts recorded audio into text.
# TWO modes:
#   ONLINE:  OpenAI Whisper API — more accurate, needs internet, costs pennies
#   OFFLINE: Vosk (local) — free, needs a 50MB model download
# The `transcribe()` function tries online first. If it fails (no
# internet, no API key), it automatically falls back to offline.

import os
import wave
import struct
import io
import json


# ── transcribe() — THE MAIN FUNCTION you call from make_it_so.py ──
# It tries online first, then falls back to offline if that fails.
# `audio_data` is raw bytes from the microphone (16-bit, 22050 Hz, mono).
# `config` is a dict loaded from config.yaml that may contain API keys.
def transcribe(audio_data, config):
    # Check the mode setting in config. Default is "auto" — try
    # online first, if it fails, fall back to offline.
    mode = config.get("mode", "auto")
    # Get the Whisper API key from config (might be empty if not set).
    openai_key = config.get("openai_api_key", "")

    # Try online mode if user wants "auto" or "online", AND we
    # have an API key available.
    if mode in ("auto", "online") and openai_key:
        # Call the Whisper API function (the online provider).
        result = transcribe_online(audio_data, config)
        # If online worked (result is not None), return it immediately.
        if result is not None:
            return result
        # If online failed and mode is "online" only (not "auto"),
        # stop here — don't try offline.
        if mode == "online":
            print("  [stt] Online mode failed and mode is set to 'online'.")
            print("  [stt] No fallback attempted.")
            return None
        # If we get here, mode is "auto" — online failed, so we'll
        # fall through to offline below.
        print("  [stt] Online transcription failed — falling back to offline.")

    # ── Offline mode (Vosk) ─────────────────────────────────────
    # If mode is "offline" or auto-fallback from above.
    print("  [stt] Using offline transcription (Vosk)...")
    result = transcribe_offline(audio_data, config)
    # Return whatever Vosk gave us (might be None if Vosk also failed).
    return result


# ── transcribe_online() — Uses OpenAI Whisper API ────────────────
# This is the same as the original transcribe() function. It sends
# audio to the cloud and gets back text. Requires an internet
# connection and a valid OpenAI API key.
def transcribe_online(audio_data, config):
    api_key = config.get("openai_api_key", "")
    if not api_key:
        print("  [stt] No OpenAI API key found in config.yaml.")
        return None

    print("  [stt] Preparing audio for online transcription...")
    # `audio_data` is just raw PCM samples — plain numbers with no
    # header describing the format. The Whisper API needs a proper
    # .wav FILE (samples plus a header stating channel count, sample
    # rate, etc.), so we wrap the raw bytes in a WAV container here.
    # `io.BytesIO()` is an in-memory "file" — it behaves like a real
    # file object (we can write to it, read it back) but lives
    # entirely in RAM, so we never have to touch the disk just to
    # reshape this data before uploading it.
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(22050)
        wf.writeframes(audio_data)
    # Pull the finished WAV bytes back out of the in-memory buffer so
    # we can attach them to the upload below.
    wav_bytes = wav_buffer.getvalue()

    print("  [stt] Sending to Whisper API...")
    try:
        import requests
        response = requests.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            # `files=` tells `requests` to send this as a
            # "multipart/form-data" upload — the same encoding a web
            # browser uses when you pick a file in an upload form —
            # rather than as a plain JSON body. The tuple gives the
            # fake filename, the file's bytes, and its MIME type.
            files={"file": ("recording.wav", wav_bytes, "audio/wav")},
            data={"model": "whisper-1", "language": "en"},
            timeout=30
        )
        if response.status_code != 200:
            print(f"  [stt] Whisper error: {response.status_code}")
            return None
        text = response.json().get("text", "").strip()
        if text:
            print(f"  [stt] Transcribed: \"{text}\"")
            return text
        print("  [stt] Whisper returned empty text.")
        return None
    except Exception as e:
        print(f"  [stt] Online transcription error: {e}")
        return None


# ── transcribe_offline() — Uses Vosk (runs 100% locally) ────────
# Vosk is an offline speech recognition engine. It uses a small
# AI model (~50MB) that runs entirely on your computer.
# No internet needed, no API key needed, no costs ever.
#
# HOW TO SET UP VOSK:
#   1. pip install vosk
#   2. Download a model from: https://alphacephei.com/vosk/models
#   3. Extract the folder into: desktop/models/vosk-model-small-en-us-0.15
#      (the "small" model is ~50MB and good enough for voice commands)
def transcribe_offline(audio_data, config):
    # ── Find the Vosk model folder ──────────────────────────────
    # The model lives in desktop/models/ relative to this file.
    models_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "models"
    )
    # Look for any folder starting with "vosk-model" in models/.
    model_path = None
    if os.path.exists(models_dir):
        for item in os.listdir(models_dir):
            if item.startswith("vosk-model"):
                model_path = os.path.join(models_dir, item)
                break

    # If no Vosk model is found, give instructions and bail out.
    if not model_path:
        print()
        print("  ╔══════════════════════════════════════════════════╗")
        print("  ║  Vosk model not found!                         ║")
        print("  ║                                                ║")
        print("  ║  Download a small model from:                   ║")
        print("  ║  https://alphacephei.com/vosk/models           ║")
        print("  ║                                                ║")
        print("  ║  Then extract it into:                         ║")
        print("  ║  desktop/models/vosk-model-small-en-us-0.15/   ║")
        print("  ╚══════════════════════════════════════════════════╝")
        print()
        return None

    # ── Try to use Vosk ─────────────────────────────────────────
    try:
        import vosk
        vosk.SetLogLevel(-1)  # Silence Vosk's internal logging.
    except ImportError:
        print("  [stt] Vosk not installed. Run: pip install vosk")
        return None

    print(f"  [stt] Loading Vosk model from {model_path}...")
    try:
        # Load the Vosk model (this reads the AI model from disk
        # into memory — takes 2-5 seconds the first time).
        model = vosk.Model(model_path)
        # Create a "recognizer" — the object that actually turns
        # incoming audio into text, using the loaded model. `16000`
        # tells it to expect 16,000 audio samples per second (Vosk's
        # required rate), which is why we resample below.
        rec = vosk.KaldiRecognizer(model, 16000)

        resampled_data = _resample_22050_to_16000(audio_data)

        # Feed the whole clip to Vosk in one call. `AcceptWaveform`
        # can also be called repeatedly with small chunks for live,
        # streaming recognition, but since we already recorded the
        # full utterance before calling this function, we hand it
        # over all at once.
        rec.AcceptWaveform(resampled_data)
        # Ask Vosk for its best-guess transcript now that all audio
        # has been fed in. `FinalResult()` returns a JSON STRING
        # (text that looks like a Python dict but isn't one yet).
        result_json = rec.FinalResult()
        # Parse that JSON string into an actual Python dict so we can
        # look up its "text" field. Vosk's JSON looks like:
        # {"text": "hello world"}
        result = json.loads(result_json)
        text = result.get("text", "").strip()

        if text:
            print(f"  [stt] Offline transcribed: \"{text}\"")
            return text
        else:
            print("  [stt] Vosk could not understand the audio.")
            return None

    except Exception as e:
        print(f"  [stt] Vosk error: {e}")
        return None


def _resample_22050_to_16000(audio_data):
    """
    Downsample raw 16-bit PCM audio from 22050 Hz to 16000 Hz.

    PARAMETERS
    ----------
    audio_data : bytes
        Raw audio recorded at 22050 samples/second (our mic's
        recording rate — see audio.py's SAMPLE_RATE constant).

    RETURNS
    -------
    bytes
        The same audio re-packed at 16000 samples/second, the rate
        Vosk's recognizer requires.

    HOW IT WORKS
    ------------
    "Sample rate" is how many audio measurements are taken per
    second — a higher rate captures more detail but produces more
    data. Vosk was trained on 16kHz audio and expects input at
    exactly that rate; our microphone records at 22050 Hz instead,
    so we have to convert (downsample) before handing audio to Vosk.

    This uses the simplest possible resampling method: since
    22050 Hz has 22050/16000 ≈ 1.378 times as many samples per
    second as 16000 Hz, we walk through the original samples
    picking every ~1.378th one and throw the rest away. This is
    much cruder than a "real" audio resampling algorithm (which
    would smooth between samples to avoid introducing distortion),
    but it's simple, fast, and accurate enough for recognizing
    spoken commands — perfect audio fidelity doesn't matter here,
    only whether Vosk can make out the words.
    """
    # `struct.unpack_from` converts the raw bytes into a tuple of
    # individual numbers. "<h" means "little-endian signed 16-bit
    # integer" — the same format our audio was recorded in — and we
    # multiply "h" by the sample count to unpack that many values at
    # once. `len(audio_data) // 2` is the sample count because each
    # 16-bit sample takes up 2 bytes.
    samples = struct.unpack_from(
        "<" + "h" * (len(audio_data) // 2), audio_data
    )

    # Walk through the original samples in increasing steps, keeping
    # only the sample nearest each step. `step` is how far to advance
    # the "read position" for every ONE output sample we keep — a
    # step of ~1.378 means we output roughly 16000 samples for every
    # 22050 input samples, matching the target rate.
    resampled = []
    step = 22050.0 / 16000.0
    i = 0.0
    while int(i) < len(samples):
        resampled.append(samples[int(i)])
        i += step

    # Pack the kept samples back into raw bytes in the same 16-bit
    # little-endian format Vosk expects to receive.
    return struct.pack("<" + "h" * len(resampled), *resampled)
