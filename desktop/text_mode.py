#!/usr/bin/env python3
# ───────────────────────────────────────────────────────────────────
# text_mode.py — text-only entry point for Make It So Number One
# ───────────────────────────────────────────────────────────────────
# make_it_so.py's main loop needs a real microphone (pyaudio) and a
# wake-word engine (pvporcupine) — hardware that doesn't exist inside
# a typical Docker container. Rather than pretend that works, this
# module runs the SAME brain — core/routines.py's macro matching,
# core/ai.py's Claude/Ollama calls, and core/action_router.py's
# action execution — driven by stdin/stdout text instead of a mic and
# speaker. Nothing here imports audio.py, stt.py, tts.py, or
# wake_word.py, so it never touches pyaudio/pvporcupine at all.
#
# WHY THIS IS USEFUL (not just a container that "starts")
# ---------------------------------------------------------
#   - Exercise routines.yaml macros without saying anything out loud.
#   - Scripted/CI smoke-testing of the AI pipeline end to end.
#   - Headless/server use (e.g. inside this Docker container) where
#     voice I/O was never available anyway.
#   - Local development without a microphone hooked up.
#
# USAGE
# -----
#   Interactive:
#       python text_mode.py
#
#   Scripted / piped (reads lines until EOF):
#       echo "focus time" | python text_mode.py
#       python text_mode.py < commands.txt
#
#   Type "exit" or "quit" (or send EOF / Ctrl+D) to stop.
# ───────────────────────────────────────────────────────────────────

import json
import os
import sys

# make_it_so.py already has robust, tested config loading + schema
# validation + history persistence — reuse it instead of duplicating
# it here. Importing make_it_so does NOT start its voice loop (that
# only runs under `if __name__ == "__main__"`), so this is safe.
import make_it_so

HISTORY_FILE = make_it_so.HISTORY_FILE
EXIT_WORDS = {"exit", "quit", ":q"}


def main():
    # Same as make_it_so.main(): work relative to desktop/ so
    # config.yaml / routines.yaml / conversation_history.json are
    # found regardless of the caller's own working directory.
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    config = make_it_so.load_config()

    print("=" * 60)
    print("  Make It So Number One — TEXT MODE")
    print("  (no microphone/speaker — type a message and press Enter)")
    print("  Type 'exit' or 'quit' to stop.")
    print("=" * 60)

    conversation_history = make_it_so.load_conversation_history()

    from core import routines as routines_module
    routines = routines_module.load_routines()

    interactive = sys.stdin.isatty()

    while True:
        if interactive:
            try:
                user_text = input("\nyou> ").strip()
            except EOFError:
                break
        else:
            line = sys.stdin.readline()
            if line == "":
                break
            user_text = line.strip()

        if not user_text:
            continue
        if user_text.lower() in EXIT_WORDS:
            break

        run_one_text_cycle(user_text, config, conversation_history, routines)

        if len(conversation_history) > 20:
            conversation_history = conversation_history[-20:]
        make_it_so.save_conversation_history(conversation_history)

    print("\n[text_mode] Shutting down. Make it so... out.")


def run_one_text_cycle(user_text, config, conversation_history, routines):
    """
    Run exactly one turn through the same routines -> AI ->
    action_router pipeline make_it_so.py's voice loop uses, printing
    the results to stdout instead of speaking them aloud.
    """
    matched_routine = None
    if routines:
        from core import routines as routines_module
        matched_routine = routines_module.match_routine(user_text, routines)

    if matched_routine is not None:
        print(f"[text_mode] Matched routine — running "
              f"{len(matched_routine['actions'])} canned action(s), "
              f"no AI call.")
        spoken_text = matched_routine.get("response", "")
        _record_exchange(conversation_history, user_text, spoken_text)
        _print_reply(spoken_text)
        action_results = _run_actions(matched_routine.get("actions", []), config)
        _handle_action_results(action_results, conversation_history)
        return

    from core import ai
    result = ai.process_with_ai(user_text, config, conversation_history)
    if result is None:
        print("[text_mode] No AI backend responded (no API key / no "
              "Ollama running). Nothing to say.")
        return

    spoken_text = result.get("spoken_text", "")
    actions = result.get("actions", [])
    _record_exchange(conversation_history, user_text, spoken_text)
    _print_reply(spoken_text)
    action_results = _run_actions(actions, config)
    _handle_action_results(action_results, conversation_history)


def _print_reply(spoken_text):
    if spoken_text:
        print(f"computer> {spoken_text}")


def _run_actions(actions, config):
    if not actions:
        return []
    from core import action_router
    return action_router.execute_actions(actions, config)


def _record_exchange(conversation_history, user_text, spoken_text):
    conversation_history.append({"role": "user", "content": user_text})
    conversation_history.append({
        "role": "assistant", "content": f"RESPONSE: {spoken_text}"
    })


def _handle_action_results(action_results, conversation_history):
    """Print every action result and record it in history, same idea
    as make_it_so.py's _handle_action_results — except everything
    just prints (there's no speaker to hold back for), not just
    CONFIRMATION REQUIRED messages."""
    if not action_results:
        return
    for result in action_results:
        if not result or result == "(no result)":
            continue
        conversation_history.append({
            "role": "assistant", "content": f"ACTION_RESULT: {result}"
        })
        print(f"[text_mode] {result}")


if __name__ == "__main__":
    main()
