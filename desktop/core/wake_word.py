# ───────────────────────────────────────────────────────────────────
# wake_word.py — listens for "Computer" on the microphone
# ───────────────────────────────────────────────────────────────────
# This module uses Picovoice Porcupine to detect the wake word
# "Computer" (just like on Star Trek TNG). Porcupine is a tiny,
# fast, offline wake word engine that runs on any platform.
#
# HOW IT WORKS
# ------------
# 1. Porcupine loads a small .ppn file (the wake word model).
# 2. It continuously reads audio from the microphone in chunks.
# 3. For each chunk, it returns a keyword index (0-3) or -1.
# 4. If the index matches our keyword, the wake word was heard!
#
# PREREQUISITE
# ------------
# You need a FREE Picovoice AccessKey from console.picovoice.ai.
# Put it in config.yaml like:
#   porcupine_access_key: "your-key-here"
# ───────────────────────────────────────────────────────────────────

import os
import struct
import sys


def wait_for_wake_word(config):
    """
    Continuously listen to the microphone until "Computer" is heard.

    PARAMETERS
    ----------
    config : dict
        Configuration dictionary loaded from config.yaml. Must
        contain "porcupine_access_key".

    RETURNS
    -------
    bool
        True if wake word was detected and we're ready to proceed.
        False if there was an error.

    HOW IT WORKS
    ------------
    This function blocks (keeps running) until:
    1. The wake word "Computer" is detected, OR
    2. The user presses Ctrl+C to quit.
    """
    # ── Try to import Porcupine ───────────────────────────────
    # If the user hasn't installed it yet, show a helpful message.
    try:
        import pvporcupine
    except ImportError:
        print()
        print("  ╔══════════════════════════════════════════════════╗")
        print("  ║  Porcupine wake word engine not installed.      ║")
        print("  ║                                                ║")
        print("  ║  Run:  pip install pvporcupine                  ║")
        print("  ║                                                ║")
        print("  ║  Then get a FREE AccessKey at:                  ║")
        print("  ║  https://console.picovoice.ai/                   ║")
        print("  ╚══════════════════════════════════════════════════╝")
        print()
        return False

    try:
        import pyaudio
    except ImportError:
        print()
        print("  ╔══════════════════════════════════════════════════╗")
        print("  ║  PyAudio not installed — needed for microphone. ║")
        print("  ║                                                ║")
        print("  ║  Run:  pip install pyaudio                     ║")
        print("  ╚══════════════════════════════════════════════════╝")
        print()
        return False

    # ── Get the AccessKey from config ─────────────────────────
    access_key = config.get("porcupine_access_key", "")
    if not access_key:
        print()
        print("  ╔══════════════════════════════════════════════════╗")
        print("  ║  Missing Porcupine AccessKey!                   ║")
        print("  ║                                                ║")
        print("  ║  1. Go to: https://console.picovoice.ai/        ║")
        print("  ║  2. Sign up for free (Hobby plan)              ║")
        print("  ║  3. Copy your AccessKey                        ║")
        print("  ║  4. Add to desktop/config.yaml:                ║")
        print("  ║     porcupine_access_key: \"your-key-here\"     ║")
        print("  ╚══════════════════════════════════════════════════╝")
        print()
        return False

    # ── Path to the "Computer" wake word model file ───────────
    # Porcupine requires a .ppn file for each wake word. The
    # built-in "Computer" keyword is included with pvporcupine.
    # We'll look for it in the pvporcupine package.
    keyword_path = None
    try:
        # Porcupine stores built-in keywords with the package.
        import pvporcupine._porcupine as _pc  # Internal path info.
        keyword_path = os.path.join(
            os.path.dirname(pvporcupine.__file__),
            "lib", "common", "porcupine_params.pv"
        )
        # The built-in keyword "computer" is known by Porcupine
        # and accessed by keyword index, not a file path.
        # Porcupine's built-in keywords for English include
        # "computer" as one of the available options.
        keyword_index = 0  # "computer" is usually built-in index 0.
    except Exception:
        # Fall back to searching for the keyword file.
        keyword_path = None

    # ── Initialize Porcupine ──────────────────────────────────
    print("  [wake] Initializing wake word engine...")
    try:
        # Create a Porcupine instance that listens for "Computer".
        # `keywords=["computer"]` tells it to only listen for that
        # one word. You can add multiple keywords if you want.
        porcupine = pvporcupine.create(
            access_key=access_key,
            keywords=["computer"]  # Built-in keyword.
            # You can also use custom .ppn files with `keyword_paths`.
        )
    except Exception as e:
        print(f"  [wake] ERROR: Could not initialize Porcupine: {e}")
        return False

    # ── Open the microphone ───────────────────────────────────
    p = pyaudio.PyAudio()
    audio_stream = p.open(
        rate=porcupine.sample_rate,  # Porcupine needs 16000 Hz.
        channels=1,
        format=pyaudio.paInt16,
        input=True,
        frames_per_buffer=porcupine.frame_length
    )

    print()
    print("  ╔══════════════════════════════════════════════════╗")
    print("  ║  🖖  Make It So Number One  🖖                 ║")
    print("  ║                                                ║")
    print("  ║  Say \"Computer\" to activate...                ║")
    print("  ║  Press Ctrl+C to quit.                         ║")
    print("  ╚══════════════════════════════════════════════════╝")
    print()

    # ── Main wake word detection loop ─────────────────────────
    try:
        while True:
            # Read one frame of audio from the microphone.
            pcm = audio_stream.read(porcupine.frame_length,
                                    exception_on_overflow=False)
            # Convert the raw bytes to a tuple of signed 16-bit ints
            # (the format Porcupine expects).
            pcm_tuple = struct.unpack_from(
                "<" + "h" * porcupine.frame_length, pcm
            )

            # Process the audio — Porcupine returns the index of
            # the detected keyword, or -1 if nothing was heard.
            keyword_index = porcupine.process(pcm_tuple)

            if keyword_index >= 0:
                # Wake word detected! The "computer" keyword is
                # at index 0 (our only keyword).
                print("  [wake] 🔺 \"Computer\" detected!")
                return True

    except KeyboardInterrupt:
        # User pressed Ctrl+C — clean up and exit.
        print()
        print("  [wake] Shutting down...")
        return False

    finally:
        # Always clean up resources to prevent audio device lockup.
        if 'audio_stream' in locals():
            audio_stream.stop_stream()
            audio_stream.close()
        if 'p' in locals():
            p.terminate()
        if 'porcupine' in locals():
            porcupine.delete()
