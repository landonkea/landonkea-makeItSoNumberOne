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

# Import `json` to persist conversation history to disk between runs
# (see save_conversation_history() / load_conversation_history()
# below) — history was previously in-memory only and lost every
# restart.
import json

# ── Conversation history persistence ──────────────────────────────
# Path to the file we save conversation history to after each
# exchange, and reload from on startup. Lives next to config.yaml in
# the desktop/ folder (main() already os.chdir()s here first), kept
# out of git the same way config.yaml is (see .gitignore) since it's
# local runtime state, not source code.
HISTORY_FILE = "conversation_history.json"


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
    # Load whatever history was saved from the last run (see
    # save_conversation_history() below) so context survives a
    # restart, instead of always starting from an empty list.
    conversation_history = load_conversation_history()

    # ── Load routines (trigger-phrase macros, see core/routines.py) ─
    # Loaded once at startup, same as config — routines.yaml is
    # optional local user data (like config.yaml), so a missing or
    # broken file just means "no routines," never a startup failure.
    from core import routines as routines_module
    routines = routines_module.load_routines()

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
                config, conversation_history, routines
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

            # Persist history to disk after every cycle (not just on
            # a clean shutdown) so a crash, force-quit, or power loss
            # between cycles doesn't lose the conversation the same
            # way an in-memory-only list would.
            save_conversation_history(conversation_history)

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


def run_one_conversation_cycle(config, conversation_history, routines=None):
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
    routines : dict or None
        Loaded from core.routines.load_routines() at startup — maps
        trigger phrase -> {"response", "actions"}. If what the user
        said matches a trigger phrase, we run that routine's canned
        actions directly and skip the AI round-trip entirely. None or
        {} (the common case — no routines.yaml) just means every
        request goes to the AI exactly as before this feature existed.

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

    matched_routine = _match_routine(user_text, routines)
    if matched_routine is not None:
        _run_routine(matched_routine, user_text, config, conversation_history)
        return True

    result = _ask_ai(user_text, config, conversation_history)
    if result is None:
        print("  [main] Claude did not respond. Going back to sleep.")
        return True

    spoken_text = result.get("spoken_text", "")
    actions = result.get("actions", [])
    _record_exchange(conversation_history, user_text, spoken_text)

    _speak_reply(spoken_text)
    action_results = _run_actions(actions, config)
    _handle_action_results(action_results, conversation_history)

    return True


def _match_routine(user_text, routines):
    """
    Check whether `user_text` invokes one of the loaded routines (see
    core/routines.py). Returns the matched routine dict, or None.
    """
    if not routines:
        return None
    from core import routines as routines_module
    return routines_module.match_routine(user_text, routines)


def _run_routine(routine, user_text, config, conversation_history):
    """
    Run a matched routine's canned action list directly — no AI
    round-trip. Speaks the routine's canned "response" (if any), runs
    its actions through the SAME action_router.execute_actions() the
    AI path uses, and records the exchange in conversation_history so
    a later AI turn still has full context of what just happened.
    """
    print(f"  [main] Matched routine — running "
          f"{len(routine['actions'])} canned action(s), no AI call.")
    spoken_text = routine.get("response", "")
    _record_exchange(conversation_history, user_text, spoken_text)
    _speak_reply(spoken_text)
    action_results = _run_actions(routine.get("actions", []), config)
    _handle_action_results(action_results, conversation_history)


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
    from core.actions import system

    # ── Honor an active sleep_mode (see core/actions/system.py) ──
    # If the user recently said "Computer, stop listening", skip
    # arming the wake-word mic listener entirely until the mute
    # window passes — this is the whole point of sleep_mode: actually
    # not listening, not just ignoring what's heard. We sleep for the
    # remaining duration in one shot (KeyboardInterrupt still breaks
    # out of a plain time.sleep() the same way it would break out of
    # wake_word.wait_for_wake_word(), so Ctrl+C keeps working during a
    # mute window too) rather than looping in small increments, since
    # there's nothing else this thread needs to be responsive to
    # while muted.
    if system.is_muted():
        remaining = system.mute_seconds_remaining()
        print(f"  [main] Sleep mode active — muted for "
              f"{int(remaining)} more second(s).")
        time.sleep(remaining)
        print("  [main] Sleep mode ended.")

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
    """
    Execute any actions the AI returned (open apps, search, etc.).

    RETURNS
    -------
    list of str
        One result message per action that ran, e.g. "Opened Safari"
        or (for a run_command that isn't allowlisted — see
        core/actions/system.py's SECURITY section) a "CONFIRMATION
        REQUIRED: ..." message. Empty list if there were no actions.
    """
    if not actions:
        return []
    # Import the `action_router` module from `core`. This module
    # decides WHICH action handler to call based on the action
    # name.
    from core import action_router
    return action_router.execute_actions(actions, config)


def _handle_action_results(action_results, conversation_history):
    """
    Make sure the user and the AI both actually find out about
    anything an action reported back.

    WHY THIS EXISTS
    ----------------
    Action results (open_app's "Opened Safari", run_command's
    output, etc.) were previously only ever printed to the terminal
    for debugging — never spoken aloud, never added to
    conversation_history. That's fine for a simple "Opened Safari"
    confirmation, but it silently broke the run_command confirmation
    gate (see core/actions/system.py): if a command needs
    confirmation, the assistant MUST actually tell the user what
    it's about to run (spoken, not just printed to a terminal
    they're probably not looking at), and the AI needs that fact in
    its own conversation history so that when the user next says
    "Computer, confirm," it recognizes what's being confirmed and
    responds with the confirm_command action instead of guessing.
    This function fixes both gaps, deliberately kept narrow (it only
    speaks CONFIRMATION REQUIRED messages aloud, not every action's
    result, so a routine "Opened Safari" doesn't get read out loud
    on top of Claude's own spoken reply).
    """
    if not action_results:
        return

    from core import tts

    for result in action_results:
        if not result or result == "(no result)":
            continue
        # Record every action result so the AI has it as context on
        # the NEXT turn — most importantly so a pending
        # "CONFIRMATION REQUIRED: <command>" message is something
        # the AI can see and correctly react to when the user says
        # "confirm."
        conversation_history.append({
            "role": "assistant",
            "content": f"ACTION_RESULT: {result}"
        })
        # A pending confirmation is the one kind of action result the
        # user MUST hear — otherwise they'd have no way to know the
        # assistant is waiting on them before it runs a command.
        if result.startswith("CONFIRMATION REQUIRED"):
            tts.speak(result)


def load_conversation_history():
    """
    Load conversation history saved by a previous run, if any.

    RETURNS
    -------
    list of dict
        The saved {"role", "content"} exchanges, or an empty list if
        there's no history file yet, it's unreadable, or its content
        isn't the list shape we expect (any of these just means
        "start fresh" rather than a fatal error — history is a nice-
        to-have, not something worth crashing startup over).
    """
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r") as f:
            history = json.load(f)
        if not isinstance(history, list):
            print(f"  [main] {HISTORY_FILE} did not contain a list — "
                  f"starting with empty history.")
            return []
        print(f"  [main] Loaded {len(history)} prior message(s) from "
              f"{HISTORY_FILE}")
        return history
    except (json.JSONDecodeError, OSError) as e:
        print(f"  [main] Could not read {HISTORY_FILE} ({e}) — "
              f"starting with empty history.")
        return []


def save_conversation_history(conversation_history):
    """
    Write conversation history to disk so it survives a restart.

    Called after every conversation cycle (not just on shutdown) so
    a crash or force-quit doesn't lose everything since the last
    clean exit. Failures here are logged, not raised — losing the
    ability to persist history should never crash the assistant
    mid-conversation.
    """
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump(conversation_history, f, indent=2)
    except OSError as e:
        print(f"  [main] Could not save conversation history: {e}")


# ── Config schema ──────────────────────────────────────────────────
# Describes the TYPE (and, where relevant, allowed values) each
# config.yaml key is expected to have, IF it's present at all — no
# key here is strictly mandatory (every consumer already falls back
# sanely via .get() when a key is missing entirely, e.g. an empty
# API key just means "that provider is unavailable"). What this
# schema catches is a key that's present but WRONG-TYPED (e.g.
# `rate: "two hundred"` instead of `rate: 200`), which previously
# would silently pass load_config() and only blow up later, deep
# inside whichever module first tried to use it — often with a
# confusing error that doesn't obviously point back to config.yaml.
# Nested dicts (tts, settings, security) get their own sub-schema
# under "schema", checked recursively by validate_config() below.
CONFIG_SCHEMA = {
    "mode": {"type": str, "choices": ("auto", "online", "offline")},
    "anthropic_api_key": {"type": str},
    "openai_api_key": {"type": str},
    "porcupine_access_key": {"type": str},
    "ollama_model": {"type": str},
    "tts": {"type": dict, "schema": {
        "voice": {"type": str},
        "rate": {"type": int},
    }},
    "settings": {"type": dict, "schema": {
        "max_record_seconds": {"type": (int, float)},
        "silence_timeout": {"type": (int, float)},
        "max_history": {"type": int},
    }},
    "security": {"type": dict, "schema": {
        "allowed_commands": {"type": list},
        "command_confirmation_required": {"type": bool},
        "denied_read_paths": {"type": list},
        "denied_read_extensions": {"type": list},
    }},
}


def _type_name(expected_type):
    """Human-readable name for a validate_config() 'type' entry,
    which is either a single type (e.g. `str`) or a tuple of
    acceptable types (e.g. `(int, float)`)."""
    if isinstance(expected_type, tuple):
        return "/".join(t.__name__ for t in expected_type)
    return expected_type.__name__


def validate_config(config, schema=None, path_prefix=""):
    """
    Check `config` against CONFIG_SCHEMA and return a list of
    human-readable error strings, one per problem found — each one
    names the EXACT key (dotted path, e.g. "settings.max_history")
    that's missing its expected type or holds an invalid value, so a
    malformed config.yaml can be fixed without guessing which line
    is wrong.

    Every schema key is OPTIONAL — this only flags keys that ARE
    present but wrong-typed or hold an unrecognized value (e.g. a
    "mode" that isn't "auto"/"online"/"offline"), not keys that are
    simply absent.

    RETURNS
    -------
    list of str
        Empty list if `config` is valid (or empty).
    """
    if schema is None:
        schema = CONFIG_SCHEMA

    if not isinstance(config, dict):
        return [f"'{path_prefix or 'config.yaml'}' should be a mapping "
                f"(key: value pairs), got {type(config).__name__}"]

    errors = []
    for key, rule in schema.items():
        if key not in config:
            continue  # absent is fine — nothing here is mandatory.
        value = config[key]
        full_key = f"{path_prefix}{key}"
        expected_type = rule["type"]

        # isinstance(True, int) is True in Python, which would let a
        # boolean silently pass an `int`-typed field (e.g. "rate:
        # true") — explicitly reject that unless bool actually IS the
        # expected type.
        type_ok = isinstance(value, expected_type) and not (
            isinstance(value, bool) and expected_type is not bool
        )
        if not type_ok:
            errors.append(
                f"'{full_key}' should be {_type_name(expected_type)}, "
                f"got {type(value).__name__} ({value!r})"
            )
            continue

        choices = rule.get("choices")
        if choices and value not in choices:
            errors.append(
                f"'{full_key}' must be one of {choices}, got {value!r}"
            )

        nested_schema = rule.get("schema")
        if nested_schema:
            errors.extend(validate_config(
                value, nested_schema, path_prefix=f"{full_key}."
            ))

    return errors


def _print_config_validation_errors(errors):
    """Print each config.yaml schema problem on its own line, in a
    banner so it's hard to miss among the rest of startup's output."""
    print()
    print("  ╔══════════════════════════════════════════════════╗")
    print("  ║  config.yaml has invalid value(s):              ║")
    print("  ║                                                ║")
    for error in errors:
        print(f"  ║  - {error}")
    print("  ║                                                ║")
    print("  ║  Fix the value(s) above, or remove the key to  ║")
    print("  ║  use its default. Continuing with config.yaml  ║")
    print("  ║  as-is otherwise.                              ║")
    print("  ╚══════════════════════════════════════════════════╝")
    print()


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
        Returns an empty dict if config.yaml doesn't exist OR if it
        exists but isn't valid YAML at all (a syntax error) — in
        both cases we print exactly what's wrong and let startup
        continue with defaults rather than crashing outright.

    CONFIG FILE
    -----------
    The app expects config.yaml in the desktop/ directory.
    It should contain:
        anthropic_api_key: "sk-ant-..."
        openai_api_key: "sk-..."
        porcupine_access_key: "your-key-..."

    Every key it contains that IS present is checked against
    CONFIG_SCHEMA above — a wrong-typed value (e.g. `rate: "fast"`
    instead of a number) is reported by name, not just discovered
    later as a mysterious crash somewhere else in the app.
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
            # This can raise yaml.YAMLError on a genuine syntax error
            # (mismatched indentation, an unterminated quote, etc.) —
            # caught below so a typo in config.yaml can't crash the
            # whole program before it even gets to print a banner.
            try:
                config = yaml.safe_load(f)
            except yaml.YAMLError as e:
                print()
                print("  ╔══════════════════════════════════════════════════╗")
                print("  ║  config.yaml is not valid YAML!                 ║")
                print("  ║                                                ║")
                for line in str(e).splitlines():
                    print(f"  ║  {line}")
                print("  ║                                                ║")
                print("  ║  Fix the syntax error above, or check it       ║")
                print("  ║  against config.example.yaml.                  ║")
                print("  ╚══════════════════════════════════════════════════╝")
                print()
                return {}
            # `or {}` means if the file is empty (returns None), use an
            # empty dictionary instead.
            config = config or {}
            # Print a message confirming which config file was loaded.
            print(f"  [main] Loaded config from {config_path}")

            # Schema check — report any wrong-typed/invalid value by
            # its exact dotted key name (see CONFIG_SCHEMA above).
            errors = validate_config(config)
            if errors:
                _print_config_validation_errors(errors)

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
