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
    # Wrap raw PCM bytes in a WAV container (Whisper needs this).
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(22050)
        wf.writeframes(audio_data)
    wav_bytes = wav_buffer.getvalue()

    print("  [stt] Sending to Whisper API...")
    try:
        import requests
        response = requests.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
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
        # Create a recognizer that processes 16-bit mono audio
        # at 16000 Hz (Vosk needs 16kHz, so we'll resample).
        rec = vosk.KaldiRecognizer(model, 16000)

        # ── Convert 22050 Hz audio to 16000 Hz ─────────────────
        # Vosk expects 16kHz audio, but our microphone records at
        # 22050 Hz. We need to downsample (remove some samples).
        # Simple approach: keep every (22050/16000) ≈ 1.38th sample.
        # We do this by reading the raw PCM and resampling.
        samples = struct.unpack_from(
            "<" + "h" * (len(audio_data) // 2), audio_data
        )
        # Resample: take sample 0, then every 1.38 steps.
        resampled = []
        step = 22050.0 / 16000.0
        i = 0.0
        while int(i) < len(samples):
            resampled.append(samples[int(i)])
            i += step

        # Pack the resampled data back into bytes.
        resampled_data = struct.pack(
            "<" + "h" * len(resampled), *resampled
        )

        # Feed audio to Vosk in chunks (it processes in 4000-byte
        # chunks internally, but we can feed it in larger pieces).
        rec.AcceptWaveform(resampled_data)
        # Get the final result (with all audio processed).
        result_json = rec.FinalResult()
        # Parse the JSON result. Vosk returns: {"text": "hello world"}
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
