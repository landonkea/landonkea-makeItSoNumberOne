# ───────────────────────────────────────────────────────────────────
# ai.py — Talks to Claude (the brain of the whole system)
# ───────────────────────────────────────────────────────────────────
# This module sends the user's transcribed speech to Claude (via
# Anthropic's API) and parses the response into:
#   1. What to SAY aloud (text response).
#   2. What to DO (actions like opening apps, searching, etc.).
#
# Claude is the "computer" from Star Trek — it receives the user's
# request, thinks about it, and responds with both spoken words
# and actions to execute on the machine.
#
# PREREQUISITE
# ------------
# You need an Anthropic API key. Get one at console.anthropic.com.
# Put it in config.yaml:
#   anthropic_api_key: "sk-ant-..."
# ───────────────────────────────────────────────────────────────────

import json
import os
import re


def get_system_prompt():
    """
    Load the Star Trek computer system prompt from the shared file.

    This prompt tells Claude HOW to behave (as the Enterprise
    computer) and what FORMAT to respond in (RESPONSE: ... ACTIONS:
    ...).

    RETURNS
    -------
    str
        The full system prompt text.
    """
    # The prompt lives in the shared/ folder at the project root.
    prompt_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))),
        "shared",
        "prompts",
        "system_prompt.txt"
    )

    try:
        with open(prompt_path, "r") as f:
            return f.read()
    except FileNotFoundError:
        # Fallback prompt in case the file is missing.
        return (
            "You are the computer from the USS Enterprise. "
            "Respond helpfully and concisely. "
            "Format: RESPONSE: ... ACTIONS: ..."
        )


def process_with_claude(user_text, config, conversation_history=None):
    """
    Send the user's request to Claude and get back the response.

    PARAMETERS
    ----------
    user_text : str
        What the user said (transcribed from speech-to-text).
    config : dict
        Configuration dictionary. Must contain "anthropic_api_key".
    conversation_history : list or None
        Previous messages for context (maintains conversation flow).
        If None, starts a new conversation.

    RETURNS
    -------
    dict or None
        Parsed response with keys:
            "spoken_text" : str  — What to say out loud.
            "actions" : list     — Actions to execute (each is a
                                   dict with "action" and "params").
        Returns None if the API call failed.
    """
    api_key = config.get("anthropic_api_key", "")
    if not api_key:
        print()
        print("  ╔══════════════════════════════════════════════════╗")
        print("  ║  Missing Anthropic API Key!                    ║")
        print("  ║                                                ║")
        print("  ║  Add to desktop/config.yaml:                   ║")
        print("  ║     anthropic_api_key: \"sk-ant-...\"           ║")
        print("  ║                                                ║")
        print("  ║  Get one at: https://console.anthropic.com/    ║")
        print("  ╚══════════════════════════════════════════════════╝")
        print()
        return None

    # ── Build the conversation messages ──────────────────────────
    # We send Claude:
    #   1. A SYSTEM prompt (tells it how to behave).
    #   2. A list of USER and ASSISTANT messages (the conversation
    #      history so far).
    #   3. The new USER message (what the user just said).
    messages = []

    # Add any previous conversation for context.
    if conversation_history:
        for msg in conversation_history:
            messages.append({
                "role": msg["role"],      # "user" or "assistant"
                "content": msg["content"] # The text they said.
            })

    # Add the new user message.
    messages.append({
        "role": "user",
        "content": user_text
    })

    # ── Call the Anthropic API ────────────────────────────────────
    print("  [ai] Sending to Claude...")
    print(f"  [ai] Request: \"{user_text}\"")

    try:
        import requests

        # Anthropic's messages API endpoint.
        url = "https://api.anthropic.com/v1/messages"

        # Build the request payload.
        payload = {
            "model": "claude-sonnet-4-20250514",  # Claude Sonnet
                                                     # (fast, smart,
                                                     # cheaper than
                                                     # Opus).
            "max_tokens": 1024,     # Maximum response length.
            "system": get_system_prompt(),  # The Star Trek prompt.
            "messages": messages,
            "temperature": 0.7       # 0.0 = very predictable,
                                     # 1.0 = very creative.
        }

        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=30
        )

        if response.status_code != 200:
            print(f"  [ai] Claude API error: {response.status_code}")
            print(f"  [ai] Response: {response.text}")
            return None

        # ── Parse the response ───────────────────────────────────
        result = response.json()

        # Claude's response text is in the "content" array (first
        # item's "text" field).
        full_response = ""
        for block in result.get("content", []):
            if block.get("type") == "text":
                full_response = block.get("text", "")
                break

        if not full_response:
            print("  [ai] Claude returned empty response.")
            return None

        print(f"  [ai] Response received ({len(full_response)} chars)")

        # ── Parse structured response ────────────────────────────
        # Claude responds in the format:
        #   RESPONSE: <spoken text>
        #
        #   ACTIONS:
        #   - action: open_app
        #     params:
        #       name: Messages
        #   - action: search_web
        #     params:
        #       query: weather today
        #
        # We need to extract the spoken text and the actions list.
        return _parse_claude_response(full_response)

    except ImportError:
        print("  [ai] `requests` library not installed.")
        print("  Run: pip install requests")
        return None
    except Exception as e:
        print(f"  [ai] Error communicating with Claude: {e}")
        return None


def _parse_claude_response(full_text):
    """
    Parse Claude's structured response into spoken text + actions.

    PARAMETERS
    ----------
    full_text : str
        The raw text from Claude in the format:
        RESPONSE: ...
        ACTIONS:
        - action: ...
          params: ...

    RETURNS
    -------
    dict
        {
            "spoken_text": str,       # What to speak aloud.
            "actions": list of dict   # Actions to execute.
        }
    """
    spoken_text = ""
    actions = []

    # ── Extract the RESPONSE section ─────────────────────────────
    # Look for "RESPONSE:" followed by text, up to "ACTIONS:" or
    # end of string.
    response_match = re.search(
        r"RESPONSE:\s*(.+?)(?=\n\s*ACTIONS:|\Z)",
        full_text,
        re.DOTALL
    )
    if response_match:
        spoken_text = response_match.group(1).strip()

    # ── Extract the ACTIONS section ──────────────────────────────
    # Look for "ACTIONS:" followed by YAML-like action blocks.
    actions_match = re.search(
        r"ACTIONS:\s*(.+)",
        full_text,
        re.DOTALL
    )
    if actions_match:
        actions_text = actions_match.group(1).strip()
        actions = _parse_actions_yaml(actions_text)

    return {
        "spoken_text": spoken_text,
        "actions": actions
    }


def _parse_actions_yaml(actions_text):
    """
    Parse the YAML-like action list from Claude's response.

    Claude responds with action blocks like:
        - action: open_app
          params:
            name: Safari

    This function extracts each action as a dictionary.

    PARAMETERS
    ----------
    actions_text : str
        The raw text after "ACTIONS:" in Claude's response.

    RETURNS
    -------
    list of dict
        Each dict has "action" (str) and "params" (dict).
    """
    actions = []

    # Split by lines starting with "- action:" (each dash marks
    # the beginning of a new action).
    action_blocks = re.split(r"\n\s*-\s+action:", actions_text)

    for block in action_blocks:
        block = block.strip()
        if not block:
            continue

        # The action name is the first line after "- action:".
        lines = block.split("\n")
        action_name = lines[0].strip()

        # Extract parameters from the "params:" section.
        params = {}
        params_match = re.search(r"params:\s*(.+)", block, re.DOTALL)
        if params_match:
            params_text = params_match.group(1).strip()
            # Parse key: value pairs (one per line, indented).
            for line in params_text.split("\n"):
                line = line.strip()
                if ":" in line:
                    key, value = line.split(":", 1)
                    key = key.strip()
                    value = value.strip()
                    params[key] = value

        actions.append({
            "action": action_name,
            "params": params
        })

    return actions
