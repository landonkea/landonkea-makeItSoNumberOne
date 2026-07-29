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
            # ====== STEP 1 & 2: WAKE WORD ========================
            # Listen for "Computer" on the microphone. This blocks
            # (keeps running) until the word is detected.
            # Import the `wake_word` module from the `core` package.
            # `from core import wake_word` loads the file
            # core/wake_word.py so we can use its functions.
            from core import wake_word

            # Print a blank line to separate this cycle from the last.
            print()
            # Print the top of a box telling the user to say "Computer".
            # The box is made of Unicode box-drawing characters.
            print("  ╔══════════════════════════════════════════════════╗")
            # Print the instruction text inside the box.
            print("  ║       Say \"Computer\" to activate...           ║")
            # Print the bottom of the box.
            print("  ╚══════════════════════════════════════════════════╝")
            # Print a blank line after the box for spacing.
            print()

            # Call the `wait_for_wake_word` function and check if it
            # returns False (meaning something went wrong or the user
            # wants to quit). The function blocks (waits) until the
            # wake word is heard or an error occurs.
            if not wake_word.wait_for_wake_word(config):
                # If the function returned False, break out of the
                # infinite while loop. `break` means "exit the loop
                # immediately."
                break

            # ====== STEP 3: PLAY CHIME ============================
            # Acknowledge the wake word with the classic Star Trek
            # two-tone computer chime.
            # Import the `audio` module from the `core` package.
            # This module handles playing sounds and recording audio.
            from core import audio
            # Call the `play_chime` function which plays the Star Trek
            # chime WAV file through the computer's speakers.
            audio.play_chime()

            # ====== STEP 4 & 5: LISTEN & TRANSCRIBE ==============
            # Record the user's voice until they stop speaking,
            # then convert it to text using Whisper.
            # Import the `stt` (Speech To Text) module from `core`.
            from core import stt

            # Record audio from the microphone until the user stops
            # speaking. `timeout_seconds=10` means if they don't speak
            # for 10 seconds, stop recording anyway. This returns the
            # raw audio data (as bytes) or None if nothing was heard.
            audio_data = audio.record_until_silence(timeout_seconds=10)
            # Check if no audio was captured (they didn't say anything).
            # `is None` checks if the variable equals Python's None
            # (which means "no value").
            if audio_data is None:
                # Print a message saying we're going back to sleep mode.
                print("  [main] No speech detected. Going back to sleep.")
                # `continue` means "skip the rest of this loop cycle and
                # start the next iteration from the top." Goes back to
                # listening for "Computer."
                continue

            # Send the audio data to Whisper (OpenAI's speech-to-text)
            # and get back the transcribed text. The `transcribe`
            # function takes the audio bytes and the config (for the
            # API key) and returns a string of what was said.
            user_text = stt.transcribe(audio_data, config)
            # Check if transcription failed (returned None or empty string).
            # `not user_text` is True for None, empty string "", or False.
            if not user_text:
                # Print a message so the user knows transcription failed.
                print("  [main] Could not transcribe. Going back to sleep.")
                # Skip to the next loop iteration (go back to sleep).
                continue

            # ====== STEP 6: THINK (CLAUDE) =======================
            # Send the transcribed text to Claude, which processes
            # it and returns what to say and what to do.
            # Import the `ai` module from `core` — this is our brain.
            from core import ai

            # Call `process_with_claude` passing the user's text, the
            # config (for API keys), and the conversation history so
            # Claude remembers what was said before.
            result = ai.process_with_claude(
                user_text,
                config,
                conversation_history
            )

            # Check if Claude returned None (meaning the API call failed).
            # We can't continue without a response from Claude.
            if result is None:
                # Print the error message and return to sleep mode.
                print("  [main] Claude did not respond. Going back to sleep.")
                # Skip to the next loop iteration.
                continue

            # Extract the spoken text from Claude's response.
            # `.get("spoken_text", "")` gets the value for that key,
            # or returns empty string if the key is missing.
            spoken_text = result.get("spoken_text", "")
            # Extract the list of actions from Claude's response.
            # If there are no actions, we get an empty list.
            actions = result.get("actions", [])

            # Add this exchange to the conversation history so
            # Claude remembers what was said before.
            # `append` adds one item to the end of the list.
            # First, add the user's message.
            conversation_history.append({
                "role": "user",
                "content": user_text
            })
            # Then, add Claude's response message.
            conversation_history.append({
                "role": "assistant",
                "content": f"RESPONSE: {spoken_text}"
            })

            # ====== STEP 7: SPEAK ================================
            # Speak Claude's response aloud using the system's
            # text-to-speech engine.
            # Check if there IS spoken text to say (not empty).
            # If it's empty, we skip speaking.
            if spoken_text:
                # Import the `tts` (Text To Speech) module from `core`.
                from core import tts
                # Call the `speak` function to read the text aloud
                # through the computer's speakers.
                tts.speak(spoken_text)

            # ====== STEP 8: ACT =================================
            # Execute any actions Claude returned (open apps,
            # search web, type text, etc.).
            # Check if there are any actions to perform.
            # A non-empty list is "truthy" (treated as True) in Python.
            if actions:
                # Import the `action_router` module from `core`.
                # This module decides WHICH action handler to call
                # based on the action name.
                from core import action_router
                # Call `execute_actions` to run all the actions.
                # It loops through each action and runs the right
                # handler (like open_app, search_web, etc.).
                action_router.execute_actions(actions, config)

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
