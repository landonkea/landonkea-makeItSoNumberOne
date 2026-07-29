# ── ai.py — AI Brain (Online via Claude + Offline via Ollama/Llama) ──
# This module is the "brain" of the voice assistant.
# TWO modes:
#   ONLINE:  Claude API (Anthropic) — smarter, needs internet
#   OFFLINE: Ollama + Llama (local) — free, runs on your own machine
# The `process_with_ai()` function tries online first. If it fails
# (no internet, no API key), it automatically falls back to offline.

import json
import os
import re


# ── get_system_prompt() — Loads the Star Trek personality prompt ──
# This is the same across ALL platforms and ALL modes.
# Tells the AI to act like the Enterprise computer and respond in
# the structured format (RESPONSE: ... ACTIONS: ...).
def get_system_prompt():
    """
    Load the Star Trek computer system prompt from the shared file.
    """
    prompt_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))),
        "shared", "prompts", "system_prompt.txt"
    )
    try:
        with open(prompt_path, "r") as f:
            return f.read()
    except FileNotFoundError:
        return (
            "You are the computer from the USS Enterprise. "
            "Respond helpfully and concisely. "
            "Format: RESPONSE: ... ACTIONS: ..."
        )


# ── process_with_ai() — Main entry point (used by make_it_so.py) ──
# Tries online first, falls back to offline if online fails.
def process_with_ai(user_text, config, conversation_history=None):
    """
    Try Claude (online) first, then Ollama (offline) if needed.
    """
    mode = config.get("mode", "auto")
    api_key = config.get("anthropic_api_key", "")

    # Try online if mode is "auto" or "online" AND we have a key.
    if mode in ("auto", "online") and api_key:
        result = process_with_claude(user_text, config, conversation_history)
        if result is not None:
            return result
        if mode == "online":
            print("  [ai] Online mode failed and mode is 'online'.")
            print("  [ai] No fallback attempted.")
            return None
        print("  [ai] Online AI failed — falling back to offline.")

    # Offline fallback (Ollama).
    print("  [ai] Using offline AI (Ollama)...")
    return process_with_ollama(user_text, config, conversation_history)


# ── process_with_claude() — Online: uses Anthropic's Claude API ──
# Same as the original process_with_claude() function.
def process_with_claude(user_text, config, conversation_history=None):
    api_key = config.get("anthropic_api_key", "")
    if not api_key:
        print("  [ai] No Anthropic API key found in config.yaml.")
        return None

    messages = []
    if conversation_history:
        for msg in conversation_history:
            messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_text})

    print("  [ai] Sending to Claude API...")
    try:
        import requests
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 1024,
                "system": get_system_prompt(),
                "messages": messages,
                "temperature": 0.7
            },
            timeout=30
        )
        if response.status_code != 200:
            print(f"  [ai] Claude error: {response.status_code}")
            return None
        full_response = ""
        for block in response.json().get("content", []):
            if block.get("type") == "text":
                full_response = block.get("text", "")
                break
        if not full_response:
            return None
        return _parse_response(full_response)
    except Exception as e:
        print(f"  [ai] Claude error: {e}")
        return None


# ── process_with_ollama() — Offline: uses Ollama + Llama on your PC ──
# Ollama is a FREE program that runs AI models locally on your
# computer. It exposes an HTTP API at http://localhost:11434.
#
# HOW TO SET UP:
#   1. Download Ollama from: https://ollama.ai
#   2. Install it (it's a normal app installer)
#   3. Open Terminal and run: ollama pull llama3.2
#      (this downloads a ~2GB model — takes a few minutes)
#   4. That's it! The model runs on your computer, 100% free.
#
# The code below calls Ollama's API the same way it calls Claude's
# API — just a different URL and JSON format.
def process_with_ollama(user_text, config, conversation_history=None):
    # ── Check that Ollama is actually installed and running ────
    # We do this by trying to connect to its API. If it fails,
    # we give the user clear setup instructions.
    import urllib.request
    try:
        # Try to reach Ollama's API health check endpoint.
        urllib.request.urlopen("http://localhost:11434/api/tags",
                                timeout=2)
    except Exception:
        print()
        print("  ╔══════════════════════════════════════════════════╗")
        print("  ║  Ollama not found!                             ║")
        print("  ║                                                ║")
        print("  ║  To use offline AI mode:                       ║")
        print("  ║  1. Download from: https://ollama.ai            ║")
        print("  ║  2. Install it (just like any app)             ║")
        print("  ║  3. Run: ollama pull llama3.2                  ║")
        print("  ║                                                ║")
        print("  ║  Or set mode to 'online' in config.yaml        ║")
        print("  ║  and add your Anthropic API key.               ║")
        print("  ╚══════════════════════════════════════════════════╝")
        print()
        return None

    # ── Pick which model to use ──────────────────────────────
    # The user can specify a modelname in config.yaml, or we
    # default to "llama3.2" (good balance of speed and intelligence).
    model = config.get("ollama_model", "llama3.2")

    # Build the conversation text. Ollama's API takes a single
    # "prompt" string (not separate messages like Claude).
    # We format it to include conversation history.
    conversation_text = ""
    if conversation_history:
        # Add previous exchanges so the AI remembers context.
        for msg in conversation_history:
            role = msg["role"].capitalize()  # "User" or "Assistant"
            conversation_text += f"{role}: {msg['content']}\n\n"
    # Add the new user message.
    conversation_text += f"User: {user_text}\n\nAssistant:"

    print(f"  [ai] Sending to local Ollama (model: {model})...")

    try:
        import requests
        # Send a POST request to Ollama's generate endpoint.
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": model,
                "prompt": conversation_text,
                "system": get_system_prompt(),
                "stream": False,  # Wait for the full response.
                "temperature": 0.7,
                # Limit response length to prevent the AI from
                # rambling (256 tokens is ~200 words).
                "options": {
                    "num_predict": 512
                }
            },
            timeout=60  # Ollama can be slow on smaller computers.
        )

        if response.status_code != 200:
            print(f"  [ai] Ollama error: {response.status_code}")
            return None

        # Parse the response. Ollama returns:
        # {"model": "...", "response": "...", "done": true}
        result = response.json()
        full_response = result.get("response", "").strip()

        if not full_response:
            print("  [ai] Ollama returned empty response.")
            return None

        print(f"  [ai] Ollama response received ({len(full_response)} chars)")

        # Parse the structured response (same format as Claude).
        return _parse_response(full_response)

    except Exception as e:
        print(f"  [ai] Ollama error: {e}")
        return None


# ── _parse_response() — Extracts spoken text + actions ───────────
# Shared by both online and offline modes.
# Claude and Ollama both respond in the same format:
#   RESPONSE: <spoken text>
#   ACTIONS:
#   - action: open_app
#     params:
#       name: Safari
def _parse_response(full_text):
    spoken_text = ""
    actions = []

    # Extract the RESPONSE section.
    response_match = re.search(
        r"RESPONSE:\s*(.+?)(?=\n\s*ACTIONS:|\Z)",
        full_text, re.DOTALL
    )
    if response_match:
        spoken_text = response_match.group(1).strip()

    # Extract the ACTIONS section.
    actions_match = re.search(
        r"ACTIONS:\s*(.+)",
        full_text, re.DOTALL
    )
    if actions_match:
        actions_text = actions_match.group(1).strip()
        actions = _parse_actions(actions_text)

    return {
        "spoken_text": spoken_text,
        "actions": actions
    }


# ── _parse_actions() — Parses the YAML-like action blocks ────────
def _parse_actions(actions_text):
    actions = []
    action_blocks = re.split(r"\n\s*-\s+action:", actions_text)

    for block in action_blocks:
        block = block.strip()
        if not block:
            continue

        lines = block.split("\n")
        action_name = lines[0].strip()

        params = {}
        params_match = re.search(r"params:\s*(.+)", block, re.DOTALL)
        if params_match:
            params_text = params_match.group(1).strip()
            for line in params_text.split("\n"):
                line = line.strip()
                if ":" in line:
                    key, value = line.split(":", 1)
                    params[key.strip()] = value.strip()

        actions.append({"action": action_name, "params": params})

    return actions
