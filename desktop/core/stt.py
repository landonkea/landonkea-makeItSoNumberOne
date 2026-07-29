# ───────────────────────────────────────────────────────────────────
# stt.py — Speech-to-Text using OpenAI Whisper
# ───────────────────────────────────────────────────────────────────
# This module converts recorded audio (from the microphone) into
# text that Claude can understand and respond to.
#
# We use OpenAI's Whisper API because:
#   1. It's extremely accurate (better than free alternatives).
#   2. It costs ~$0.006 per minute of audio (pennies per session).
#   3. It handles different accents, mumbling, and background noise.
#   4. No local installation needed — just an API call.
#
# The audio data must be a WAV file (or similar) that we send as a
# file upload to Whisper. We save the recorded PCM data as a WAV
# before sending it.
# ───────────────────────────────────────────────────────────────────

import os
import wave
import struct
import io


def transcribe(audio_data, config):
    """
    Send recorded audio to OpenAI Whisper and get back text.

    PARAMETERS
    ----------
    audio_data : bytes
        Raw PCM audio data (16-bit, 22050 Hz, mono) from the
        microphone recording.
    config : dict
        Configuration dictionary. Must contain "openai_api_key".

    RETURNS
    -------
    str or None
        The transcribed text (what the user said).
        Returns None if transcription failed.

    HOW IT WORKS
    ------------
    1. We take the raw audio bytes and wrap them in a WAV container
       (Whisper expects standard audio file formats).
    2. We send the WAV bytes to OpenAI's /v1/audio/transcriptions
       endpoint using the "whisper-1" model.
    3. The API returns the transcribed text as a string.
    """
    api_key = config.get("openai_api_key", "")
    if not api_key:
        print()
        print("  ╔══════════════════════════════════════════════════╗")
        print("  ║  Missing OpenAI API Key!                       ║")
        print("  ║                                                ║")
        print("  ║  Add to desktop/config.yaml:                   ║")
        print("  ║     openai_api_key: \"sk-...\"                  ║")
        print("  ║                                                ║")
        print("  ║  Get one at: https://platform.openai.com/      ║")
        print("  ╚══════════════════════════════════════════════════╝")
        print()
        return None

    # ── Wrap raw PCM data in a WAV file ──────────────────────────
    # Whisper API needs a standard audio format, not raw bytes.
    # We create a WAV in memory (using io.BytesIO) so we don't have
    # to write a temporary file to disk.
    print("  [stt] Preparing audio for transcription...")

    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, "wb") as wf:
        # WAV header settings — must match how we recorded.
        wf.setnchannels(1)      # Mono.
        wf.setsampwidth(2)      # 16-bit.
        wf.setframerate(22050)  # 22050 Hz.
        wf.writeframes(audio_data)

    # Get the WAV bytes from the buffer.
    wav_bytes = wav_buffer.getvalue()

    # ── Send to OpenAI Whisper API ───────────────────────────────
    print("  [stt] Sending to Whisper API for transcription...")

    try:
        # Use the `requests` library (must be installed).
        import requests

        # OpenAI's audio transcription endpoint.
        url = "https://api.openai.com/v1/audio/transcriptions"

        # We send a multipart form request (like uploading a file).
        # `files` contains the audio file, `data` contains options.
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {api_key}"
            },
            files={
                "file": ("recording.wav", wav_bytes, "audio/wav")
            },
            data={
                "model": "whisper-1",  # The Whisper model name.
                "language": "en"       # Force English (faster, more
                                       # accurate for English speech).
            },
            timeout=30  # 30-second timeout for the network request.
        )

        if response.status_code != 200:
            print(f"  [stt] Whisper API error: {response.status_code}")
            print(f"  [stt] Response: {response.text}")
            return None

        # Parse the JSON response. The transcribed text is in the
        # "text" field.
        result = response.json()
        text = result.get("text", "").strip()

        if text:
            print(f"  [stt] Transcribed: \"{text}\"")
            return text
        else:
            print("  [stt] Whisper returned empty text.")
            return None

    except ImportError:
        print("  [stt] `requests` library not installed.")
        print("  Run: pip install requests")
        return None
    except Exception as e:
        print(f"  [stt] Transcription error: {e}")
        return None
