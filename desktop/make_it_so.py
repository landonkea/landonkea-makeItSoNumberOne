#!/usr/bin/env python3
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

import os
import sys
import time


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
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    # ── Load configuration ───────────────────────────────────────
    # API keys and settings are stored in config.yaml (NOT
    # committed to git — you create it from config.example.yaml).
    config = load_config()

    # Print a welcome banner.
    print_banner()

    # ── Track conversation history (for context) ─────────────────
    # Claude remembers previous exchanges so you can have a
    # natural conversation (like "Open Safari" then "Search for
    # pizza places" — it knows the context).
    conversation_history = []

    # ── MAIN LOOP ────────────────────────────────────────────────
    # This loop runs forever, processing one command at a time.
    # Press Ctrl+C at any time to exit gracefully.
    while True:
        try:
            # ====== STEP 1 & 2: WAKE WORD ========================
            # Listen for "Computer" on the microphone. This blocks
            # (keeps running) until the word is detected.
            from core import wake_word

            print()
            print("  ╔══════════════════════════════════════════════════╗")
            print("  ║       Say \"Computer\" to activate...           ║")
            print("  ╚══════════════════════════════════════════════════╝")
            print()

            if not wake_word.wait_for_wake_word(config):
                # Wake word detection failed or was interrupted.
                break

            # ====== STEP 3: PLAY CHIME ============================
            # Acknowledge the wake word with the classic Star Trek
            # two-tone computer chime.
            from core import audio
            audio.play_chime()

            # ====== STEP 4 & 5: LISTEN & TRANSCRIBE ==============
            # Record the user's voice until they stop speaking,
            # then convert it to text using Whisper.
            from core import stt

            audio_data = audio.record_until_silence(timeout_seconds=10)
            if audio_data is None:
                print("  [main] No speech detected. Going back to sleep.")
                continue

            user_text = stt.transcribe(audio_data, config)
            if not user_text:
                print("  [main] Could not transcribe. Going back to sleep.")
                continue

            # ====== STEP 6: THINK (CLAUDE) =======================
            # Send the transcribed text to Claude, which processes
            # it and returns what to say and what to do.
            from core import ai

            result = ai.process_with_claude(
                user_text,
                config,
                conversation_history
            )

            if result is None:
                print("  [main] Claude did not respond. Going back to sleep.")
                continue

            spoken_text = result.get("spoken_text", "")
            actions = result.get("actions", [])

            # Add this exchange to the conversation history so
            # Claude remembers what was said before.
            conversation_history.append({
                "role": "user",
                "content": user_text
            })
            conversation_history.append({
                "role": "assistant",
                "content": f"RESPONSE: {spoken_text}"
            })

            # ====== STEP 7: SPEAK ================================
            # Speak Claude's response aloud using the system's
            # text-to-speech engine.
            if spoken_text:
                from core import tts
                tts.speak(spoken_text)

            # ====== STEP 8: ACT =================================
            # Execute any actions Claude returned (open apps,
            # search web, type text, etc.).
            if actions:
                from core import action_router
                action_router.execute_actions(actions, config)

            # Keep conversation history manageable (last 10
            # exchanges max).
            if len(conversation_history) > 20:
                conversation_history = conversation_history[-20:]

        except KeyboardInterrupt:
            # Ctrl+C pressed — exit gracefully.
            print()
            print("  [main] Shutting down. Make it so... out.")
            break

        except Exception as e:
            # Catch any unexpected error, show it, and keep going.
            print(f"  [main] Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            print("  [main] Restarting loop...")
            time.sleep(1)


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
    import yaml  # Requires PyYAML: pip install pyyaml

    config_path = "config.yaml"
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            config = yaml.safe_load(f) or {}
            print(f"  [main] Loaded config from {config_path}")
            return config
    else:
        print()
        print("  ╔══════════════════════════════════════════════════╗")
        print("  ║  No config.yaml found!                         ║")
        print("  ║                                                ║")
        print("  ║  Copy config.example.yaml to config.yaml       ║")
        print("  ║  and add your API keys:                        ║")
        print("  ║                                                ║")
        print("  ║  1. Anthropic (Claude): console.anthropic.com  ║")
        print("  ║  2. OpenAI (Whisper): platform.openai.com      ║")
        print("  ║  3. Picovoice (wake word): console.picovoice.ai║")
        print("  ╚══════════════════════════════════════════════════╝")
        print()
        return {}


def print_banner():
    """
    Print the startup banner with the Star Trek-inspired logo.
    """
    print()
    print("  ╔══════════════════════════════════════════════════╗")
    print("  ║                                                  ║")
    print("  ║     ███╗   ███╗ █████╗ ██╗  ██╗███████╗         ║")
    print("  ║     ████╗ ████║██╔══██╗██║ ██╔╝██╔════╝         ║")
    print("  ║     ██╔████╔██║███████║█████╔╝ █████╗           ║")
    print("  ║     ██║╚██╔╝██║██╔══██║██╔═██╗ ██╔══╝           ║")
    print("  ║     ██║ ╚═╝ ██║██║  ██║██║  ██╗███████╗         ║")
    print("  ║     ╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝         ║")
    print("  ║                                                  ║")
    print("  ║         ██╗████████╗                         ║")
    print("  ║         ██║╚══██╔══╝                         ║")
    print("  ║         ██║   ██║                            ║")
    print("  ║         ██║   ██║                            ║")
    print("  ║         ██║   ██║                            ║")
    print("  ║         ╚═╝   ╚═╝                            ║")
    print("  ║                                                  ║")
    print("  ║           ᴸⁱᶠᵉ ˢᵘᵖᵖᵒʳᵗ                    ║")
    print("  ║                                                  ║")
    print("  ║     Voice Assistant v1.0 — \"Computer\"           ║")
    print("  ║     Say \"Computer\" to begin                    ║")
    print("  ╚══════════════════════════════════════════════════╝")
    print()


if __name__ == "__main__":
    main()
