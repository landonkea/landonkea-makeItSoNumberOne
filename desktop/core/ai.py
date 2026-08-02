# ── ai.py — AI Brain (Online via Claude + Offline via Ollama/Llama) ──
# This module is the "brain" of the voice assistant.
# TWO modes:
#   ONLINE:  Claude API (Anthropic) — smarter, needs internet
#   OFFLINE: Ollama + Llama (local) — free, runs on your own machine
# The `process_with_ai()` function tries online first. If it fails
# (no internet, no API key), it automatically falls back to offline.

# Import `json` so we can parse JSON text (a common data format used
# by web APIs) into Python dictionaries and lists.
import json
# Import `os` to build file paths that work on any operating system
# (used below to locate the shared system prompt file).
import os
# Import `re`, Python's regular expression module. A "regular
# expression" (regex) is a mini pattern-language for finding and
# extracting text that matches a shape — e.g. "everything after the
# word RESPONSE: up until the word ACTIONS:". We use it below to pull
# the two sections out of the AI's reply.
import re


# ── get_system_prompt() — Loads the Star Trek personality prompt ──
# This is the same across ALL platforms and ALL modes.
# Tells the AI to act like the Enterprise computer and respond in
# the structured format (RESPONSE: ... ACTIONS: ...).
def get_system_prompt():
    """
    Load the Star Trek computer system prompt from the shared file.
    """
    # Build the absolute path to shared/prompts/system_prompt.txt.
    # `__file__` is this script's own path. Each `os.path.dirname()`
    # call moves one folder up: core/ai.py -> core/ -> desktop/ ->
    # the repo root. We call dirname() three times because the
    # prompt file lives at <repo root>/shared/prompts/, three levels
    # above this file (core/ai.py). Building the path this way means
    # it still works no matter which folder the app is launched from.
    prompt_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))),
        "shared", "prompts", "system_prompt.txt"
    )
    try:
        with open(prompt_path, "r") as f:
            return f.read()
    except FileNotFoundError:
        # If the shared prompt file is missing (e.g. a stripped-down
        # deployment that only ships the desktop/ folder), fall back
        # to a minimal built-in prompt so the assistant still works,
        # just without its full Star Trek personality.
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

    PARAMETERS
    ----------
    user_text : str
        What the user said, already converted from speech to text.
    config : dict
        App configuration loaded from config.yaml (API keys, the
        "mode" setting: "auto", "online", or "offline").
    conversation_history : list of dict or None
        Previous exchanges, each like {"role": "user"/"assistant",
        "content": "..."}, so the AI can remember earlier turns.

    RETURNS
    -------
    dict or None
        {"spoken_text": str, "actions": list} on success, or None if
        every available AI backend failed.
    """
    # `.get("mode", "auto")` reads the "mode" setting from config, or
    # defaults to "auto" (try online, fall back to offline) if the
    # user hasn't set one.
    mode = config.get("mode", "auto")
    api_key = config.get("anthropic_api_key", "")

    # Only attempt the online path if the user allows it ("auto" or
    # "online") AND we actually have an API key to use — there's no
    # point calling Claude's API with an empty key, it would just
    # fail every time.
    if mode in ("auto", "online") and api_key:
        result = process_with_claude(user_text, config, conversation_history)
        # A non-None result means Claude answered successfully —
        # we're done, no need to try the offline model too.
        if result is not None:
            return result
        # If the user explicitly locked the mode to "online" (not
        # "auto"), we respect that choice and do NOT silently fall
        # back to a different AI — we'd rather report failure than
        # surprise the user with an offline answer they didn't ask
        # for.
        if mode == "online":
            print("  [ai] Online mode failed and mode is 'online'.")
            print("  [ai] No fallback attempted.")
            return None
        print("  [ai] Online AI failed — falling back to offline.")

    # Offline fallback (Ollama). We reach this line either because
    # mode is "offline" outright, or because "auto" mode's online
    # attempt above failed and fell through.
    print("  [ai] Using offline AI (Ollama)...")
    return process_with_ollama(user_text, config, conversation_history)


# ── process_with_claude() — Online: uses Anthropic's Claude API ──
def process_with_claude(user_text, config, conversation_history=None):
    """
    Send the conversation to Anthropic's Claude API and parse the
    structured RESPONSE/ACTIONS reply.

    Returns None (instead of raising an exception) on any failure —
    missing key, network error, bad HTTP status, empty reply — so
    that process_with_ai() can cleanly fall back to the offline model
    without needing a try/except of its own around this call.
    """
    api_key = config.get("anthropic_api_key", "")
    if not api_key:
        print("  [ai] No Anthropic API key found in config.yaml.")
        return None

    messages = _build_claude_messages(user_text, conversation_history)

    print("  [ai] Sending to Claude API...")
    try:
        # Imported here, not at the top of the file, so that a
        # machine without the `requests` library installed can still
        # import this whole module (and use the offline Ollama path)
        # without crashing at startup.
        import requests
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                # Anthropic authenticates requests using this custom
                # header instead of the more common "Authorization:
                # Bearer <key>" style some other APIs use.
                "x-api-key": api_key,
                # Anthropic versions its API by date so that older
                # integrations keep working even after the API
                # changes shape in the future — this pins us to a
                # known request/response format.
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
        full_response = _extract_claude_text(response.json())
        if not full_response:
            return None
        return _parse_response(full_response)
    except Exception as e:
        print(f"  [ai] Claude error: {e}")
        return None


def _build_claude_messages(user_text, conversation_history):
    """
    Turn conversation history + the new user message into the list
    of {"role", "content"} dicts Claude's Messages API expects.

    Splitting this out of process_with_claude() means the "shape my
    data for this API" logic can be read, and tested, independently
    of the "make the network call" logic.
    """
    messages = []
    if conversation_history:
        # Copy each earlier turn into Claude's expected message
        # shape. We rebuild the dict (rather than reusing it as-is)
        # so we only ever send the two fields Claude actually wants,
        # even if conversation_history entries carry extra keys.
        for msg in conversation_history:
            messages.append({"role": msg["role"], "content": msg["content"]})
    # The newest thing the user just said always goes last, since
    # the API reads the message list in chronological order.
    messages.append({"role": "user", "content": user_text})
    return messages


def _extract_claude_text(response_json):
    """
    Pull the assistant's plain-text reply out of Claude's response.

    Claude's API can return a LIST of "content blocks" (a message
    can mix text, tool calls, images, etc.) rather than one plain
    string. We only asked for text, so we scan the list and return
    the first block whose "type" is "text".
    """
    for block in response_json.get("content", []):
        if block.get("type") == "text":
            return block.get("text", "")
    return ""


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
    """
    Send the conversation to a locally-running Ollama server and
    parse its structured RESPONSE/ACTIONS reply.
    """
    if not _is_ollama_running():
        _print_ollama_missing_help()
        return None

    # The user can specify a model name in config.yaml, or we
    # default to "llama3.2" (good balance of speed and intelligence).
    model = config.get("ollama_model", "llama3.2")
    conversation_text = _build_ollama_prompt(user_text, conversation_history)

    print(f"  [ai] Sending to local Ollama (model: {model})...")
    try:
        import requests
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": model,
                "prompt": conversation_text,
                "system": get_system_prompt(),
                "stream": False,  # Wait for the full response instead
                                  # of Ollama streaming it back one
                                  # word at a time — simpler for us
                                  # to handle since we just need the
                                  # complete text before parsing it.
                "temperature": 0.7,
                # Limit response length to prevent the AI from
                # rambling (num_predict counts in "tokens" — small
                # chunks of text roughly 3/4 of a word each, so 512
                # tokens is roughly 380 words).
                "options": {
                    "num_predict": 512
                }
            },
            timeout=60  # Ollama can be slow on smaller computers,
                        # so we give it twice as long as the Claude
                        # request above (30s) before giving up.
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


def _is_ollama_running(timeout_seconds=2):
    """
    Check whether a local Ollama server is reachable.

    We do this by trying to connect to its API health-check
    endpoint. `urllib.request` is Python's built-in HTTP client — we
    use it here instead of `requests` because this check needs to
    run even if `requests` isn't installed yet (it's only imported,
    inside a try/except, further down for the real API call).
    """
    import urllib.request
    try:
        urllib.request.urlopen(
            "http://localhost:11434/api/tags", timeout=timeout_seconds
        )
        return True
    except Exception:
        # Any failure here — connection refused, DNS error, timeout —
        # means Ollama isn't running, and the exact reason doesn't
        # matter to the caller, so we collapse it all to False.
        return False


def _print_ollama_missing_help():
    """Print setup instructions when Ollama can't be reached."""
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


def _build_ollama_prompt(user_text, conversation_history):
    """
    Flatten conversation history + the new user message into the
    single text "prompt" string Ollama's /api/generate endpoint
    expects.

    Unlike Claude's API (which takes a structured list of separate
    messages), Ollama's generate endpoint just wants one long block
    of text, formatted like a script — "User: ...", "Assistant:
    ...", back and forth — that the model continues from.
    """
    conversation_text = ""
    if conversation_history:
        for msg in conversation_history:
            role = msg["role"].capitalize()  # "User" or "Assistant"
            conversation_text += f"{role}: {msg['content']}\n\n"
    # End the prompt with "Assistant:" and nothing after it — this is
    # the model's cue that it should continue the text FROM this
    # point, i.e. write the assistant's reply next.
    conversation_text += f"User: {user_text}\n\nAssistant:"
    return conversation_text


# ── _parse_response() — Extracts spoken text + actions ───────────
# Shared by both online and offline modes.
# Claude and Ollama both respond in the same format:
#   RESPONSE: <spoken text>
#   ACTIONS:
#   - action: open_app
#     params:
#       name: Safari
def _parse_response(full_text):
    """
    Split the AI's raw reply into the spoken-aloud text and the list
    of structured actions to run.

    HOW IT WORKS
    ------------
    Both Claude and Ollama are instructed (via the system prompt) to
    reply in a fixed text layout with two labeled sections. We use
    regular expressions — a pattern-matching mini-language for text —
    to pull each section out, then hand the ACTIONS section to
    `_parse_actions()` for further parsing.
    """
    spoken_text = ""
    actions = []

    # This pattern reads as: starting right after "RESPONSE:" (and
    # any following whitespace), capture everything — `.+?` — up
    # until either the literal text "ACTIONS:" on its own line, or
    # the end of the string (`\Z`). The `?` after `.+` makes the
    # match "non-greedy," meaning it grabs as LITTLE text as possible
    # while still satisfying the pattern — without it, `.+` would
    # greedily swallow the entire rest of the string, including the
    # ACTIONS section, before backtracking. `re.DOTALL` makes `.`
    # match newline characters too, since the response text can span
    # multiple lines.
    response_match = re.search(
        r"RESPONSE:\s*(.+?)(?=\n\s*ACTIONS:|\Z)",
        full_text, re.DOTALL
    )
    if response_match:
        # `.group(1)` returns just the parenthesized "capture group"
        # from the pattern above (the spoken text itself), not the
        # literal "RESPONSE:" label that matched alongside it.
        spoken_text = response_match.group(1).strip()

    # Everything after "ACTIONS:" to the end of the text is the
    # actions block, which _parse_actions() will break down further.
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
    """
    Parse the ACTIONS section's YAML-like list into a list of dicts
    like {"action": "open_app", "params": {"name": "Safari"}}.

    The AI doesn't return real machine-readable JSON here — it
    returns YAML-flavored text because that's easier for a language
    model to produce reliably. Rather than pulling in a full YAML
    parser for this one narrow shape, we split the text ourselves
    with a regular expression.
    """
    actions = []
    # Split the whole ACTIONS block wherever a new "- action:" line
    # begins. `re.split()` with a capturing-free pattern here removes
    # the matched separator text from the result, leaving each
    # action's own name + params text as one chunk in the resulting
    # list.
    #
    # BUG FIX: the pattern used to be `r"\n\s*-\s+action:"`, which
    # only matched a "- action:" marker that has a newline BEFORE
    # it. That's true for the second action onward, but the very
    # FIRST "- action:" in the text has nothing before it (no
    # preceding newline to match), so it was never split off — the
    # first action's name ended up being the literal string
    # "- action: open_app" instead of just "open_app", which meant
    # the first action Claude/Ollama requested each turn could never
    # match a handler in action_router.py and was silently dropped
    # as an "Unknown action type." Adding `(?:\A|\n)` — "the very
    # start of the string, OR a newline" — makes the very first
    # occurrence match too, so every action (including the first)
    # gets its "- action:" marker stripped consistently. `\A` means
    # "start of string" (unlike `^`, it isn't affected by
    # re.MULTILINE, though we don't use that flag here anyway).
    action_blocks = re.split(r"(?:\A|\n)\s*-\s+action:", actions_text)

    for block in action_blocks:
        action = _parse_one_action_block(block)
        if action is not None:
            actions.append(action)

    return actions


def _parse_one_action_block(block):
    """
    Parse a single action's text chunk (action name + optional
    "params:" section) into {"action": ..., "params": {...}}.

    Returns None for an empty chunk (e.g. the leading fragment
    before the first "- action:" that re.split() always produces).
    """
    block = block.strip()
    if not block:
        return None

    # The action name is whatever's on the first line of this chunk
    # (re.split already stripped the "- action:" label itself off
    # the front, so what's left starts with the action's name, e.g.
    # "open_app").
    lines = block.split("\n")
    action_name = lines[0].strip()

    params = {}
    # Look for a "params:" section anywhere in the remaining text and
    # capture everything after it.
    params_match = re.search(r"params:\s*(.+)", block, re.DOTALL)
    if params_match:
        params_text = params_match.group(1).strip()
        # Each param line looks like "name: Safari" — split on the
        # FIRST colon only (`split(":", 1)`) so a value that itself
        # contains a colon (e.g. a URL like "http://example.com")
        # doesn't get chopped up incorrectly.
        for line in params_text.split("\n"):
            line = line.strip()
            if ":" in line:
                key, value = line.split(":", 1)
                params[key.strip()] = value.strip()

    return {"action": action_name, "params": params}
