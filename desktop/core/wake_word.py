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

# Import the "struct" module so we can convert between Python data
# and raw bytes (like turning microphone audio into numbers).
import struct
# Import the "sys" module so we can access system-specific stuff
# (though we don't actually use it in this file — it's here for
# consistency with other modules in the project).
import sys


# Define a function called "wait_for_wake_word" that takes one
# argument called "config". "config" is a dictionary (like a
# labeled box of settings) that contains things like API keys
# and preferences loaded from the config.yaml file.
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

    It's broken into smaller helper functions below — one to check
    the required libraries are installed, one to read/validate the
    AccessKey, one to start up Porcupine + the microphone, and one
    to run the actual listen loop — so each step can be understood
    (and tested) on its own.
    """
    # ── Step 1: make sure both required libraries are installed ──
    pvporcupine = _import_pvporcupine()
    if pvporcupine is None:
        return False
    pyaudio = _import_pyaudio()
    if pyaudio is None:
        return False

    # ── Step 2: make sure we have a Picovoice AccessKey ──────────
    access_key = config.get("porcupine_access_key", "")
    if not access_key:
        _print_missing_access_key_help()
        return False

    # ── Step 3: start up the wake word engine ────────────────────
    porcupine = _init_porcupine(pvporcupine, access_key)
    if porcupine is None:
        return False

    # ── Step 4: open the microphone ───────────────────────────────
    p = pyaudio.PyAudio()
    audio_stream = p.open(
        rate=porcupine.sample_rate,  # Porcupine needs 16000 Hz.
        channels=1,                   # Mono (single channel) audio.
        format=pyaudio.paInt16,       # 16-bit signed integer format.
        input=True,                   # This is an input stream (mic).
        frames_per_buffer=porcupine.frame_length  # Chunk size.
    )

    _print_listening_banner()

    # ── Step 5: listen until the wake word is heard or Ctrl+C ────
    # Use try/except/finally so we can catch Ctrl+C and clean up.
    try:
        return _detection_loop(porcupine, audio_stream)
    # If the user presses Ctrl+C on their keyboard, Python raises
    # a KeyboardInterrupt exception. We catch it here to shut down
    # gracefully instead of showing an ugly error message.
    except KeyboardInterrupt:
        # User pressed Ctrl+C — clean up and exit.
        print()
        print("  [wake] Shutting down...")
        return False
    # The "finally" block runs NO MATTER WHAT — whether the try
    # succeeded, failed, or was interrupted. This guarantees we
    # always clean up resources like the microphone and Porcupine.
    finally:
        # Stop the microphone stream from recording.
        audio_stream.stop_stream()
        # Close the stream to release the microphone hardware.
        audio_stream.close()
        # Terminate the PyAudio session to release resources.
        p.terminate()
        # Delete the Porcupine instance from memory.
        porcupine.delete()


def _import_pvporcupine():
    """
    Try to import the pvporcupine library (Picovoice's wake word
    detection engine). Returns the imported module on success, or
    None (after printing setup instructions) if it isn't installed.

    "try/except ImportError" is the standard Python pattern for
    treating a missing optional library as a normal, recoverable
    situation instead of letting the program crash with a scary
    traceback.
    """
    try:
        import pvporcupine
        return pvporcupine
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
        return None


def _import_pyaudio():
    """
    Try to import pyaudio, which lets Python access the computer's
    microphone. Returns the imported module on success, or None
    (after printing setup instructions) if it isn't installed.
    """
    try:
        import pyaudio
        return pyaudio
    except ImportError:
        print()
        print("  ╔══════════════════════════════════════════════════╗")
        print("  ║  PyAudio not installed — needed for microphone. ║")
        print("  ║                                                ║")
        print("  ║  Run:  pip install pyaudio                     ║")
        print("  ╚══════════════════════════════════════════════════╝")
        print()
        return None


def _print_missing_access_key_help():
    """Print step-by-step instructions for getting a free AccessKey."""
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


def _init_porcupine(pvporcupine, access_key):
    """
    Create and return a Porcupine wake-word-detection instance
    listening for "computer", or None if creation fails (bad key,
    network issue, etc.).

    NOTE: We pass `keywords=["computer"]` below, which tells
    pvporcupine to use its own bundled built-in "computer" model.
    pvporcupine finds that file internally — we don't need to
    locate it ourselves. (An earlier version of this function
    manually hunted for the model's file path here, but that
    result was never actually used anywhere, so it was removed.)
    """
    print("  [wake] Initializing wake word engine...")
    try:
        # Create a Porcupine instance that listens for "Computer".
        # `keywords=["computer"]` tells it to only listen for that
        # one word. You can add multiple keywords if you want.
        return pvporcupine.create(
            access_key=access_key,
            keywords=["computer"]  # Built-in keyword.
            # You can also use custom .ppn files with `keyword_paths`.
        )
    except Exception as e:
        print(f"  [wake] ERROR: Could not initialize Porcupine: {e}")
        return None


def _print_listening_banner():
    """Print the Star-Trek-themed startup banner."""
    print()
    print("  ╔══════════════════════════════════════════════════╗")
    print("  ║  🖖  Make It So Number One  🖖                 ║")
    print("  ║                                                ║")
    print("  ║  Say \"Computer\" to activate...                ║")
    print("  ║  Press Ctrl+C to quit.                         ║")
    print("  ╚══════════════════════════════════════════════════╝")
    print()


def _detection_loop(porcupine, audio_stream):
    """
    Read audio from the microphone forever, one Porcupine "frame" at
    a time, until the wake word "computer" is detected.

    RETURNS
    -------
    bool
        Always True — this function only returns once the wake word
        has actually been heard; any other way out of listening
        (Ctrl+C, an error) happens via an exception, which the
        caller's try/except/finally handles instead.
    """
    # Loop forever (while True means "keep going until broken").
    while True:
        # Read one frame of audio from the microphone.
        # porcupine.frame_length tells us how many samples to
        # read. exception_on_overflow=False means don't crash if
        # the audio buffer overflows (just drop the excess).
        pcm = audio_stream.read(
            porcupine.frame_length, exception_on_overflow=False
        )
        # Convert the raw bytes to a tuple of signed 16-bit ints
        # (the format Porcupine expects). The "<" means
        # little-endian byte order, and "h" means signed 16-bit
        # short. We multiply "h" by frame_length to unpack that
        # many values.
        pcm_tuple = struct.unpack_from(
            "<" + "h" * porcupine.frame_length, pcm
        )

        # Process the audio — Porcupine returns the index of
        # the detected keyword, or -1 if nothing was heard.
        keyword_index = porcupine.process(pcm_tuple)

        # If keyword_index is 0 or higher, a wake word was
        # detected. -1 means nothing was heard.
        if keyword_index >= 0:
            # Wake word detected! The "computer" keyword is
            # at index 0 (our only keyword).
            print("  [wake] 🔺 \"Computer\" detected!")
            return True
