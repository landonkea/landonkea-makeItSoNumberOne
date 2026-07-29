# ───────────────────────────────────────────────────────────────────
# tts.py — Text-to-Speech using system commands
# ───────────────────────────────────────────────────────────────────
# This module converts Claude's text responses into spoken audio.
#
# On macOS we use the built-in `say` command (comes with every Mac).
# On Linux we try `espeak` or `festival` (may need install).
# On Windows we use the built-in SAPI via PowerShell.
#
# The goal is to use ZERO external Python libraries for TTS so the
# final executable stays small and portable. Each OS has a built-in
# way to speak text.
# ───────────────────────────────────────────────────────────────────

import os
import platform
import subprocess
import tempfile


def speak(text):
    """
    Speak the given text aloud using the system's built-in TTS.

    PARAMETERS
    ----------
    text : str
        The text to speak aloud (Claude's response).

    HOW IT WORKS
    ------------
    1. Detects the operating system.
    2. Uses the OS-native speech command:
       - macOS: `say "text"` (built-in, voices available)
       - Linux: `espeak "text"` (may need `sudo apt install espeak`)
       - Windows: PowerShell SAPI (built-in)
    3. Runs the command and waits for it to finish.
    """
    if not text or not text.strip():
        return  # Nothing to say.

    text = text.strip()

    # Detect the operating system.
    system = platform.system()

    try:
        if system == "Darwin":
            # ── macOS: `say` command ─────────────────────────────
            # The `say` command has been part of macOS since the
            # beginning. It uses the built-in TTS voices.
            # Voice "Samantha" is clear and pleasant.
            subprocess.run(
                ["say", "-v", "Samantha", text],
                check=True,
                timeout=30
            )

        elif system == "Linux":
            # ── Linux: try `espeak`, fall back to `spd-say` ──────
            # espeak is the most common Linux TTS. On Raspberry Pi
            # install it with: sudo apt install espeak
            try:
                subprocess.run(
                    ["espeak", text],
                    check=True,
                    timeout=30
                )
            except FileNotFoundError:
                # espeak not installed — try speech-dispatcher.
                try:
                    subprocess.run(
                        ["spd-say", text],
                        check=True,
                        timeout=30
                    )
                except FileNotFoundError:
                    print("  [tts] No TTS found. Install espeak:")
                    print("    sudo apt install espeak")

        elif system == "Windows":
            # ── Windows: PowerShell SAPI ─────────────────────────
            # Windows has a built-in SAPI (Speech API) that can be
            # accessed via PowerShell. No extra install needed.
            ps_script = (
                f'Add-Type -AssemblyName System.Speech; '
                f'$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; '
                f'$s.Speak("{text.replace(\'"\', \'\\"\')}")'
            )
            subprocess.run(
                ["powershell", "-Command", ps_script],
                check=True,
                timeout=30
            )

        else:
            print(f"  [tts] Unknown OS: {system}. Cannot speak.")

    except subprocess.TimeoutExpired:
        print("  [tts] Speech timed out (took too long).")
    except Exception as e:
        print(f"  [tts] Error during speech: {e}")
