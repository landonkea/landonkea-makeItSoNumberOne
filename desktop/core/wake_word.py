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

# Import the "os" module so we can work with file paths and the
# operating system (like joining folder paths together).
import os
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
    """
    # ── Try to import Porcupine ───────────────────────────────
    # If the user hasn't installed it yet, show a helpful message.
    # "try" means: attempt this code, and if it fails, catch the
    # error in "except" instead of crashing the program.
    try:
        # Try to import the pvporcupine library (a wake word
        # detection engine made by Picovoice). If this library
        # isn't installed, Python will raise an ImportError.
        import pvporcupine
    # If the import failed (library not installed), run this block
    # instead of letting the program crash.
    except ImportError:
        # Print a blank line for spacing in the terminal.
        print()
        # Print a fancy box that tells the user Porcupine is missing.
        print("  ╔══════════════════════════════════════════════════╗")
        print("  ║  Porcupine wake word engine not installed.      ║")
        print("  ║                                                ║")
        # Tell them the exact pip command to install it.
        print("  ║  Run:  pip install pvporcupine                  ║")
        print("  ║                                                ║")
        # Tell them they also need a free API key from Picovoice.
        print("  ║  Then get a FREE AccessKey at:                  ║")
        print("  ║  https://console.picovoice.ai/                   ║")
        print("  ╚══════════════════════════════════════════════════╝")
        # Print another blank line at the bottom of the box.
        print()
        # Return False to tell the caller that wake word detection
        # could not start (because Porcupine is missing).
        return False

    # Another try block to handle a missing PyAudio library.
    try:
        # Try to import pyaudio, which lets Python access the
        # computer's microphone to record sound.
        import pyaudio
    # If pyaudio isn't installed, catch the error and show a message.
    except ImportError:
        # Blank line before the error box.
        print()
        # Draw a box telling the user PyAudio is missing.
        print("  ╔══════════════════════════════════════════════════╗")
        print("  ║  PyAudio not installed — needed for microphone. ║")
        print("  ║                                                ║")
        # Show the pip command to install PyAudio.
        print("  ║  Run:  pip install pyaudio                     ║")
        print("  ╚══════════════════════════════════════════════════╝")
        # Blank line after the box.
        print()
        # Return False because we can't access the microphone.
        return False

    # ── Get the AccessKey from config ─────────────────────────
    # Pull the "porcupine_access_key" value out of the config
    # dictionary. If it's not there, default to an empty string.
    access_key = config.get("porcupine_access_key", "")
    # Check if the access key is empty (not provided by the user).
    if not access_key:
        # Blank line before the error box.
        print()
        # Draw a box explaining the missing AccessKey.
        print("  ╔══════════════════════════════════════════════════╗")
        print("  ║  Missing Porcupine AccessKey!                   ║")
        print("  ║                                                ║")
        # Step-by-step instructions to get a free key.
        print("  ║  1. Go to: https://console.picovoice.ai/        ║")
        print("  ║  2. Sign up for free (Hobby plan)              ║")
        print("  ║  3. Copy your AccessKey                        ║")
        print("  ║  4. Add to desktop/config.yaml:                ║")
        # Show the exact YAML format the user needs in config.
        print("  ║     porcupine_access_key: \"your-key-here\"     ║")
        print("  ╚══════════════════════════════════════════════════╝")
        # Blank line after the box.
        print()
        # Return False because we don't have a valid key.
        return False

    # ── Path to the "Computer" wake word model file ───────────
    # Porcupine requires a .ppn file for each wake word. The
    # built-in "Computer" keyword is included with pvporcupine.
    # We'll look for it in the pvporcupine package.
    # Start with keyword_path set to None (meaning "no path yet").
    keyword_path = None
    # Try to find the built-in keyword file inside Porcupine's
    # installed package folder.
    try:
        # Import Porcupine's internal module to access file paths.
        import pvporcupine._porcupine as _pc  # Internal path info.
        # Build the full path to the porcupine_params.pv file by
        # joining the folder pvporcupine is installed in with
        # "lib/common/porcupine_params.pv". os.path.join knows how
        # to combine paths properly on any operating system.
        keyword_path = os.path.join(
            os.path.dirname(pvporcupine.__file__),
            "lib", "common", "porcupine_params.pv"
        )
        # The built-in keyword "computer" is known by Porcupine
        # and accessed by keyword index, not a file path.
        # Porcupine's built-in keywords for English include
        # "computer" as one of the available options.
        # Set keyword_index to 0 because "computer" is typically
        # the first built-in keyword in Porcupine's English list.
        keyword_index = 0  # "computer" is usually built-in index 0.
    # If anything goes wrong finding the built-in path (maybe a
    # different version of Porcupine), don't crash — just handle it.
    except Exception:
        # Fall back to searching for the keyword file.
        # Set keyword_path back to None so the code below uses
        # a custom .ppn file path instead of the built-in keyword.
        keyword_path = None

    # ── Initialize Porcupine ──────────────────────────────────
    # Print a status message so the user knows we're starting up.
    print("  [wake] Initializing wake word engine...")
    # Try to create a Porcupine instance. If it fails (bad key,
    # network issue, etc.), we catch the error.
    try:
        # Create a Porcupine instance that listens for "Computer".
        # `keywords=["computer"]` tells it to only listen for that
        # one word. You can add multiple keywords if you want.
        porcupine = pvporcupine.create(
            access_key=access_key,
            keywords=["computer"]  # Built-in keyword.
            # You can also use custom .ppn files with `keyword_paths`.
        )
    # If anything goes wrong during initialization, catch the error.
    except Exception as e:
        # Print the error message so the user knows what failed.
        print(f"  [wake] ERROR: Could not initialize Porcupine: {e}")
        # Return False because we can't listen without Porcupine.
        return False

    # ── Open the microphone ───────────────────────────────────
    # Create a PyAudio object that manages access to the mic.
    p = pyaudio.PyAudio()
    # Open an audio stream (a live connection to the microphone)
    # with the correct settings that Porcupine expects.
    audio_stream = p.open(
        rate=porcupine.sample_rate,  # Porcupine needs 16000 Hz.
        channels=1,                   # Mono (single channel) audio.
        format=pyaudio.paInt16,       # 16-bit signed integer format.
        input=True,                   # This is an input stream (mic).
        frames_per_buffer=porcupine.frame_length  # Chunk size.
    )

    # Print a blank line before the fancy banner.
    print()
    # Draw a Star-Trek-themed startup banner in the terminal.
    print("  ╔══════════════════════════════════════════════════╗")
    print("  ║  🖖  Make It So Number One  🖖                 ║")
    print("  ║                                                ║")
    # Tell the user to say the wake word to activate the assistant.
    print("  ║  Say \"Computer\" to activate...                ║")
    print("  ║  Press Ctrl+C to quit.                         ║")
    print("  ╚══════════════════════════════════════════════════╝")
    # Print another blank line to make the banner stand out.
    print()

    # ── Main wake word detection loop ─────────────────────────
    # Use try/except/finally so we can catch Ctrl+C and clean up.
    try:
        # Loop forever (while True means "keep going until broken").
        while True:
            # Read one frame of audio from the microphone.
            # porcupine.frame_length tells us how many samples to
            # read. exception_on_overflow=False means don't crash if
            # the audio buffer overflows (just drop the excess).
            pcm = audio_stream.read(porcupine.frame_length,
                                    exception_on_overflow=False)
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
                # Return True to tell the caller the wake word
                # was heard and we're ready to record a command.
                return True

    # If the user presses Ctrl+C on their keyboard, Python raises
    # a KeyboardInterrupt exception. We catch it here to shut down
    # gracefully instead of showing an ugly error message.
    except KeyboardInterrupt:
        # User pressed Ctrl+C — clean up and exit.
        # Print a blank line to separate from the continuous output.
        print()
        # Tell the user we're shutting down because they pressed Ctrl+C.
        print("  [wake] Shutting down...")
        # Return False because we didn't detect the wake word.
        return False

    # The "finally" block runs NO MATTER WHAT — whether the try
    # succeeded, failed, or was interrupted. This guarantees we
    # always clean up resources like the microphone and Porcupine.
    finally:
        # Check if 'audio_stream' was created (exists in the list
        # of local variables). If it does, we need to close it.
        if 'audio_stream' in locals():
            # Stop the microphone stream from recording.
            audio_stream.stop_stream()
            # Close the stream to release the microphone hardware.
            audio_stream.close()
        # Check if 'p' (the PyAudio object) was created.
        if 'p' in locals():
            # Terminate the PyAudio session to release resources.
            p.terminate()
        # Check if 'porcupine' (the Porcupine engine) was created.
        if 'porcupine' in locals():
            # Delete the Porcupine instance from memory.
            porcupine.delete()
