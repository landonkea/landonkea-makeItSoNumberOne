#!/usr/bin/env python3
# The line above is called a "shebang." It tells your computer that
# this file should be run with Python 3. On Linux/Mac, you can run
# the file directly (./make_it_so.py) without typing "python" first.
# It's like a label on the file that says "I need Python to run."

# ───────────────────────────────────────────────────────────────────
# make_it_so.py — Main entry point for Make It So Number One
# ───────────────────────────────────────────────────────────────────
# This is the main loop of the entire voice assistant.
# It runs forever, waiting for "Computer" and then processing
# whatever the user says.
#
# THE LOOP (runs until Ctrl+C):
#   1. 🌙  SLEEP — listening for wake word "Computer"
#   2. 🔺  WAKE — "Computer" heard!
#   3. 🔔  CHIME — play Star Trek acknowledgment sound
#   4. 🎤  LISTEN — record user's voice
#   5. 📝  TRANSCRIBE — convert speech to text (Whisper)
#   6. 🧠  THINK — send text to Claude
#   7. 🔊  SPEAK — Claude's response spoken aloud
#   8. 🎯  ACT — execute Claude's actions (open apps, search, etc.)
#   9. 🔄  LOOP — go back to step 1
#
# USAGE
# -----
#   python make_it_so.py
#
# Or after building with PyInstaller:
#   ./MakeItSo.exe  (or .app on Mac, or binary on Linux)
#
# CONFIG
# ------
# Create desktop/config.yaml with your API keys:
#   anthropic_api_key: "sk-ant-..."
#   openai_api_key: "sk-..."
#   porcupine_access_key: "your-key-..."
#
# See config.example.yaml for all available options.
# ───────────────────────────────────────────────────────────────────

# Import the `os` module to interact with the operating system.
# We use it to change directories and check if files exist.
import os

# Import the `sys` module for system-specific functions.
# We use it to get the path of the current script and to exit the
# program if needed.
import sys

# Import the `time` module for time-related functions.
# We use it to pause (sleep) before restarting after an error.
import time


# Define the main function that runs everything.
# When you run this file, Python calls this function at the bottom.
# The function is a container that holds all the steps of the program.
def main():
    """
    The main entry point. Runs the voice assistant loop forever.

    HOW IT WORKS
    ------------
    1. Loads configuration from config.yaml (API keys, settings).
    2. Runs the wake/speak/act loop until Ctrl+C is pressed.
    3. Each iteration: wake word → chime → record → transcribe →
       Claude → speak → act → back to sleep.
    """
    # ── Ensure we're in the right directory ──────────────────────
    # The config file and assets are relative to this script's
    # location, so we change to the desktop/ directory.
    # `os.path.abspath(__file__)` gets the FULL path to this script.
    # `os.path.dirname(...)` gets just the folder that contains it.
    # This way, it works no matter where you run it from.
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # Actually change the current working directory to that folder.
    # `os.chdir(...)` changes where the program thinks it "is" so that
    # relative paths (like "config.yaml") work correctly.
    os.chdir(script_dir)

    # ── Load configuration ───────────────────────────────────────
    # API keys and settings are stored in config.yaml (NOT
    # committed to git — you create it from config.example.yaml).
    # Call the `load_config` function (defined below) to read the
    # YAML file and return its contents as a dictionary.
    config = load_config()

    # Print a welcome banner to the terminal.
    # This calls the `print_banner` function (defined below) which
    # prints the Star Trek ASCII art logo in a box.
    print_banner()

    # ── Track conversation history (for context) ─────────────────
    # Claude remembers previous exchanges so you can have a
    # natural conversation (like "Open Safari" then "Search for
    # pizza places" — it knows the context).
    # Create an empty list that will store all the messages exchanged
    # with Claude. Each message is a dict with "role" and "content".
    conversation_history = []

    # ── MAIN LOOP ────────────────────────────────────────────────
    # This loop runs forever, processing one command at a time.
    # Press Ctrl+C at any time to exit gracefully.
    # `while True:` creates an infinite loop — it keeps running until
    # we explicitly break out of it or the program is killed.
    while True:
        # Try to run all the steps below. If ANYTHING goes wrong, we
        # catch the error instead of crashing. This makes the program
        # resilient — it keeps running even after mistakes.
        try:
            # `run_one_conversation_cycle` does everything from "wait
            # for the wake word" through "speak the reply and run any
            # actions." It's pulled out into its own function (below)
            # so this loop's job is just "run one cycle, and decide
            # whether to keep looping" — the details of what a cycle
            # involves live in one focused place instead of inline
            # here.
            keep_running = run_one_conversation_cycle(
                config, conversation_history
            )
            if not keep_running:
                # The wake word listener returned False, meaning it
                # hit an unrecoverable error (missing dependency,
                # bad AccessKey, etc.) rather than a normal Ctrl+C.
                # `break` exits the infinite while loop, ending the
                # program the same way a fatal error should.
                break

            # Keep conversation history manageable (last 10
            # exchanges max).
            # Check if the history has more than 20 entries (which is
            # 10 user + 10 assistant exchanges = 10 conversations).
            if len(conversation_history) > 20:
                # If it's too long, keep only the LAST 20 messages.
                # `[-20:]` is Python slice notation — it means "from
                # the 20th-from-last item to the end." This prevents
                # the list from growing forever and using too much memory.
                conversation_history = conversation_history[-20:]

        # If the user presses Ctrl+C, Python raises a KeyboardInterrupt.
        # This catches it so we can print a goodbye message instead of
        # showing a scary error traceback.
        except KeyboardInterrupt:
            # Print a blank line for clean formatting.
            print()
            # Print a friendly shutdown message to the terminal.
            print("  [main] Shutting down. Make it so... out.")
            # `break` exits the infinite while loop, ending the program.
            break

        # Catch ANY other unexpected error. This is a safety net so
        # the program doesn't crash on minor problems — it just logs
        # the error and restarts the loop.
        except Exception as e:
            # Print the error message so the developer knows something
            # went wrong but the program kept running.
            print(f"  [main] Unexpected error: {e}")
            # Import Python's built-in traceback module to print the
            # full error details (which file, which line, the call stack).
            import traceback
            # Print the full error traceback to help debug the issue.
            traceback.print_exc()
            # Tell the user we're restarting the loop.
            print("  [main] Restarting loop...")
            # Pause for 1 second before restarting. `time.sleep(1)`
            # makes the program wait for 1 second so we don't
            # immediately spam errors if something is broken.
            time.sleep(1)


def run_one_conversation_cycle(config, conversation_history):
    """
    Run exactly one wake -> listen -> think -> speak -> act cycle,
    mutating `conversation_history` in place as the exchange happens.

    PARAMETERS
    ----------
    config : dict
        App configuration (API keys, mode setting) loaded once at
        startup and reused for every cycle.
    conversation_history : list of dict
        The running list of {"role", "content"} exchanges so far.
        This function APPENDS to it directly (lists are mutable and
        shared by reference in Python, so changes here are visible
        to the caller's copy of the same list too) rather than
        returning a new list, since the caller needs to keep using
        the same list across every cycle of the main loop.

    RETURNS
    -------
    bool
        True to keep the main loop running (this is the normal case
        — even a cycle where the user said nothing understandable
        still returns True so we go back to listening). False only
        when the wake word listener itself reports a fatal setup
        problem, signaling the whole program should stop.
    """
    if not _listen_for_wake_word(config):
        return False

    audio_data = _record_user_speech()
    if audio_data is None:
        print("  [main] No speech detected. Going back to sleep.")
        return True

    user_text = _transcribe_speech(audio_data, config)
    if not user_text:
        print("  [main] Could not transcribe. Going back to sleep.")
        return True

    result = _ask_ai(user_text, config, conversation_history)
    if result is None:
        print("  [main] Claude did not respond. Going back to sleep.")
        return True

    spoken_text = result.get("spoken_text", "")
    actions = result.get("actions", [])
    _record_exchange(conversation_history, user_text, spoken_text)

    _speak_reply(spoken_text)
    _run_actions(actions, config)

    return True


def _listen_for_wake_word(config):
    """
    Block until the wake word "Computer" is heard.

    RETURNS
    -------
    bool
        True once the wake word is detected. False if the wake word
        listener hit a fatal setup problem (missing dependency,
        missing AccessKey, etc.) and the whole program should stop.
    """
    # Import the `wake_word` module from the `core` package here
    # (rather than at the top of the file) so that a machine missing
    # one of this module's optional dependencies only fails when
    # this specific feature is actually used, not at startup.
    from core import wake_word

    print()
    print("  ╔══════════════════════════════════════════════════╗")
    print("  ║       Say \"Computer\" to activate...           ║")
    print("  ╚══════════════════════════════════════════════════╝")
    print()

    return wake_word.wait_for_wake_word(config)


def _record_user_speech():
    """
    Play the acknowledgment chime, then record the user's voice
    until they stop speaking.

    RETURNS
    -------
    bytes or None
        Raw recorded audio, or None if no speech was detected.
    """
    # ====== PLAY CHIME ============================
    # Acknowledge the wake word with the classic Star Trek two-tone
    # computer chime.
    from core import audio
    audio.play_chime()

    # ====== LISTEN ============================
    # Record audio from the microphone until the user stops
    # speaking. `timeout_seconds=10` means if they don't speak
    # for 10 seconds, stop recording anyway. This returns the
    # raw audio data (as bytes) or None if nothing was heard.
    return audio.record_until_silence(timeout_seconds=10)


def _transcribe_speech(audio_data, config):
    """
    Convert recorded audio to text using the speech-to-text module.

    RETURNS
    -------
    str or None
        The transcribed text, or None/empty string if transcription
        failed.
    """
    from core import stt
    return stt.transcribe(audio_data, config)


def _ask_ai(user_text, config, conversation_history):
    """
    Send the transcribed text to the AI brain (Claude if online,
    Ollama/Llama if offline) and get back what to say and do.

    RETURNS
    -------
    dict or None
        {"spoken_text": str, "actions": list}, or None if every
        available AI backend failed to respond.
    """
    from core import ai
    return ai.process_with_ai(user_text, config, conversation_history)


def _record_exchange(conversation_history, user_text, spoken_text):
    """
    Append this turn's user message and assistant reply to the
    shared conversation history list so future turns have context.
    """
    conversation_history.append({
        "role": "user",
        "content": user_text
    })
    conversation_history.append({
        "role": "assistant",
        "content": f"RESPONSE: {spoken_text}"
    })


def _speak_reply(spoken_text):
    """Speak the AI's reply aloud, if there is any text to say."""
    if spoken_text:
        # Import the `tts` (Text To Speech) module from `core`.
        from core import tts
        tts.speak(spoken_text)


def _run_actions(actions, config):
    """Execute any actions the AI returned (open apps, search, etc.)."""
    if actions:
        # Import the `action_router` module from `core`. This module
        # decides WHICH action handler to call based on the action
        # name.
        from core import action_router
        action_router.execute_actions(actions, config)


# Define a function that loads configuration from a YAML file.
# YAML is a human-readable data format that uses indentation
# (like Python) to organize data into lists and dictionaries.
def load_config():
    """
    Load the configuration from config.yaml.

    RETURNS
    -------
    dict
        Configuration dictionary with API keys and settings.
        Returns an empty dict if config.yaml doesn't exist.

    CONFIG FILE
    -----------
    The app expects config.yaml in the desktop/ directory.
    It should contain:
        anthropic_api_key: "sk-ant-..."
        openai_api_key: "sk-..."
        porcupine_access_key: "your-key-..."
    """
    # Import the `yaml` module (from the PyYAML library) that can
    # read and write YAML files. This is a third-party library that
    # must be installed separately with `pip install pyyaml`.
    import yaml  # Requires PyYAML: pip install pyyaml

    # Define the config file name (it should be in the current directory,
    # which we changed to the desktop/ folder above).
    config_path = "config.yaml"
    # Check if the config file actually exists on disk.
    # `os.path.exists(config_path)` returns True if the file is there,
    # False if it's missing.
    if os.path.exists(config_path):
        # Open the config file in read mode ("r").
        # `with open(...) as f:` automatically closes the file when
        # the indented block ends (even if an error occurs).
        with open(config_path, "r") as f:
            # Parse the YAML file content into a Python dictionary.
            # `yaml.safe_load(f)` reads the file and converts it from
            # YAML text into Python data structures (dicts, lists, etc.).
            # `or {}` means if the file is empty (returns None), use an
            # empty dictionary instead.
            config = yaml.safe_load(f) or {}
            # Print a message confirming which config file was loaded.
            print(f"  [main] Loaded config from {config_path}")
            # Return the parsed configuration dictionary to the caller.
            return config
    # If the file does NOT exist...
    else:
        # Print a blank line for spacing.
        print()
        # Print a helpful error message in a box that tells the user
        # how to set up their config file.
        print("  ╔══════════════════════════════════════════════════╗")
        print("  ║  No config.yaml found!                         ║")
        # Print instructions to copy the example file.
        print("  ║                                                ║")
        print("  ║  Copy config.example.yaml to config.yaml       ║")
        print("  ║  and add your API keys:                        ║")
        print("  ║                                                ║")
        # List where to get each API key.
        print("  ║  1. Anthropic (Claude): console.anthropic.com  ║")
        print("  ║  2. OpenAI (Whisper): platform.openai.com      ║")
        print("  ║  3. Picovoice (wake word): console.picovoice.ai║")
        print("  ╚══════════════════════════════════════════════════╝")
        print()
        # Return an empty dictionary since we couldn't load any config.
        # The program will show the "missing API key" error later.
        return {}


# Define a function that prints the Star Trek-themed startup banner.
# It doesn't take any arguments or return any value — it just prints
# text to the terminal for visual flair.
def print_banner():
    """
    Print the startup banner with the Star Trek-inspired logo.
    """
    # Print a blank line at the top for spacing.
    print()
    # Print the top border of the banner box using Unicode characters.
    print("  ╔══════════════════════════════════════════════════╗")
    # Print a blank separator line inside the box.
    print("  ║                                                  ║")
    # Print the "MAKE IT SO" text as ASCII art using block characters.
    # Each line is a row of the large text logo. The █ and ║ characters
    # form the letters "MAKE IT SO" in a blocky font and the box border.
    print("  ║     ███╗   ███╗ █████╗ ██╗  ██╗███████╗         ║")
    print("  ║     ████╗ ████║██╔══██╗██║ ██╔╝██╔════╝         ║")
    print("  ║     ██╔████╔██║███████║█████╔╝ █████╗           ║")
    print("  ║     ██║╚██╔╝██║██╔══██║██╔═██╗ ██╔══╝           ║")
    print("  ║     ██║ ╚═╝ ██║██║  ██║██║  ██╗███████╗         ║")
    print("  ║     ╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝         ║")
    # Print a separator line.
    print("  ║                                                  ║")
    # Print "IT" in ASCII art (the word "IT" between "MAKE" and "SO").
    print("  ║         ██╗████████╗                         ║")
    print("  ║         ██║╚══██╔══╝                         ║")
    print("  ║         ██║   ██║                            ║")
    print("  ║         ██║   ██║                            ║")
    print("  ║         ██║   ██║                            ║")
    print("  ║         ╚═╝   ╚═╝                            ║")
    # Print a separator line.
    print("  ║                                                  ║")
    # Print the "Life Support" subtitle as small superscript text.
    # The ᴸⁱᶠᵉ ˢᵘᵖᵖᵒʳᵗ characters are Unicode modifier letters
    # that simulate small superscript text. This is just for fun.
    print("  ║           ᴸⁱᶠᵉ ˢᵘᵖᵖᵒʳᵗ                    ║")
    # Print a separator line.
    print("  ║                                                  ║")
    # Print the version and instruction text.
    print("  ║     Voice Assistant v1.0 — \"Computer\"           ║")
    # Print the main instruction: say "Computer" to start.
    print("  ║     Say \"Computer\" to begin                    ║")
    # Print the bottom border of the banner box.
    print("  ╚══════════════════════════════════════════════════╝")
    # Print a blank line after the box for spacing.
    print()


# This is a special Python idiom that checks if this file is being
# RUN directly (as opposed to being imported by another file).
# `__name__` is a special variable that Python sets to "__main__"
# when the file is run directly (e.g., `python make_it_so.py`).
# If the file is imported by another file, `__name__` is the module's
# name (e.g., "make_it_so"), so the code below won't run.
if __name__ == "__main__":
    # Call the main() function to start the voice assistant.
    # This is the actual entry point where the program begins.
    main()
