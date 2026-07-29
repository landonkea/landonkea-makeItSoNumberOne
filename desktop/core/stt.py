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

# Import the "os" module for operating system operations (like
# file paths). We import it here for consistency but actually use
# it indirectly through other modules in the project.
import os
# Import "wave" from Python's standard library — it lets us create
# and read .wav audio files (the format Whisper expects).
import wave
# Import "struct" for converting between Python data and raw bytes.
# We use it to pack audio data into the WAV format correctly.
import struct
# Import "io" (input/output) which gives us BytesIO — a tool that
# lets us work with bytes in memory as if they were a file, without
# actually writing anything to disk.
import io


# Define a function called "transcribe" that takes two arguments:
# "audio_data" (raw microphone bytes) and "config" (settings dict).
# This function sends the audio to OpenAI Whisper and returns text.
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
    # Look up the OpenAI API key from the config dictionary.
    # config.get() looks for the key "openai_api_key" and returns
    # it, or an empty string "" if it's not found.
    api_key = config.get("openai_api_key", "")
    # Check if the API key is empty or missing.
    if not api_key:
        # Blank line before the error message for readability.
        print()
        # Draw a nice box in the terminal telling the user their
        # OpenAI API key is missing from the config file.
        print("  ╔══════════════════════════════════════════════════╗")
        print("  ║  Missing OpenAI API Key!                       ║")
        print("  ║                                                ║")
        # Show the exact YAML format they need in config.yaml.
        print("  ║  Add to desktop/config.yaml:                   ║")
        print("  ║     openai_api_key: \"sk-...\"                  ║")
        print("  ║                                                ║")
        # Tell them where to sign up for an API key.
        print("  ║  Get one at: https://platform.openai.com/      ║")
        print("  ╚══════════════════════════════════════════════════╝")
        # Blank line after the box.
        print()
        # Return None to indicate that transcription failed because
        # we don't have a valid API key.
        return None

    # ── Wrap raw PCM data in a WAV file ──────────────────────────
    # Whisper API needs a standard audio format, not raw bytes.
    # We create a WAV in memory (using io.BytesIO) so we don't have
    # to write a temporary file to disk.
    # Let the user know we're preparing the audio for the API call.
    print("  [stt] Preparing audio for transcription...")

    # Create a BytesIO object — this acts like a file but stores
    # its contents in memory (RAM) instead of on your hard drive.
    wav_buffer = io.BytesIO()
    # Open wav_buffer as a WAV file for writing ("wb" = write binary).
    # The "with" statement ensures the file is properly closed when
    # we're done, even if an error occurs.
    with wave.open(wav_buffer, "wb") as wf:
        # Set the WAV file to have 1 audio channel (mono). This
        # matches how we record from the microphone.
        wf.setnchannels(1)      # Mono.
        # Set the sample width to 2 bytes (16-bit audio). This
        # determines the quality/range of each audio sample.
        wf.setsampwidth(2)      # 16-bit.
        # Set the frame rate (sample rate) to 22050 Hz. This means
        # 22,050 samples per second — good enough for voice.
        wf.setframerate(22050)  # 22050 Hz.
        # Write the raw audio data into the WAV file structure.
        # The wave module handles adding the proper headers.
        wf.writeframes(audio_data)

    # Get the complete WAV file contents as a bytes object by
    # calling .getvalue() on the BytesIO buffer.
    wav_bytes = wav_buffer.getvalue()

    # ── Send to OpenAI Whisper API ───────────────────────────────
    # Tell the user we're about to send audio to the cloud for
    # transcription (this may take a couple seconds).
    print("  [stt] Sending to Whisper API for transcription...")

    # Use a try/except block so we can handle errors gracefully
    # (like network failures or a missing "requests" library).
    try:
        # Import the "requests" library, which lets Python make
        # HTTP requests to web APIs (like OpenAI's servers).
        import requests

        # The full URL for OpenAI's audio transcription endpoint.
        # This is the web address we send our audio file to.
        url = "https://api.openai.com/v1/audio/transcriptions"

        # We send a multipart form request (like uploading a file).
        # `files` contains the audio file, `data` contains options.
        # requests.post() sends an HTTP POST request to the API.
        response = requests.post(
            # The URL we're sending the request to.
            url,
            # Headers are extra information sent with the request.
            # Here we include the Authorization header with our
            # API key so OpenAI knows who we are and that we're
            # allowed to use the service.
            headers={
                "Authorization": f"Bearer {api_key}"
            },
            # The "files" parameter simulates uploading a file.
            # We give it a filename ("recording.wav"), the WAV bytes,
            # and the MIME type for WAV audio.
            files={
                "file": ("recording.wav", wav_bytes, "audio/wav")
            },
            # The "data" parameter contains form fields (not files).
            # "model" tells OpenAI which AI model to use for
            # transcription. "whisper-1" is the standard model.
            data={
                "model": "whisper-1",  # The Whisper model name.
                "language": "en"       # Force English (faster, more
                                       # accurate for English speech).
            },
            # Set a 30-second timeout. If the API doesn't respond
            # within 30 seconds, the request will be cancelled and
            # an exception will be raised (preventing the program
            # from hanging forever).
            timeout=30  # 30-second timeout for the network request.
        )

        # Check if the HTTP response status code is NOT 200.
        # Status code 200 means "OK" (success). Anything else means
        # something went wrong (like bad auth, rate limit, etc.).
        if response.status_code != 200:
            # Print the error status code so the user can troubleshoot.
            print(f"  [stt] Whisper API error: {response.status_code}")
            # Print the full response body — it usually contains a
            # helpful error message from OpenAI about what went wrong.
            print(f"  [stt] Response: {response.text}")
            # Return None because transcription failed.
            return None

        # Parse the JSON response from the API. .json() converts
        # the JSON string into a Python dictionary we can work with.
        result = response.json()
        # Extract the "text" field from the result dictionary, then
        # strip any leading/trailing whitespace (spaces, newlines).
        text = result.get("text", "").strip()

        # Check if we got actual text back (non-empty).
        if text:
            # Print what the user said so they can see it worked.
            print(f"  [stt] Transcribed: \"{text}\"")
            # Return the transcribed text to whoever called this
            # function (so Claude can process it as a command).
            return text
        # If text was empty or None, handle that case.
        else:
            # Let the user know Whisper didn't return any text
            # (maybe silence, maybe background noise).
            print("  [stt] Whisper returned empty text.")
            # Return None to indicate no speech was recognized.
            return None

    # If the "requests" library isn't installed, catch the error
    # and give a helpful message instead of crashing.
    except ImportError:
        # Tell the user they need to install the requests library.
        print("  [stt] `requests` library not installed.")
        # Show the pip command to install it.
        print("  Run: pip install requests")
        # Return None because we can't make the API call.
        return None
    # Catch any other unexpected errors (network down, timeout, etc.)
    except Exception as e:
        # Print the error message so we know what went wrong.
        print(f"  [stt] Transcription error: {e}")
        # Return None because transcription could not complete.
        return None
