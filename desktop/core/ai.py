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
# Import `re`, Python's regular expression module. Only used now as
# a LEGACY fallback parser — see _parse_response_legacy() below — for
# the old hand-rolled "RESPONSE: ... ACTIONS: ..." text format, in
# case a model ever ignores the JSON instruction in the system
# prompt and replies in the old shape anyway.
import re

# Pure sentence-boundary logic used by the streaming Claude path
# below (see process_with_claude_streaming()) to hand complete
# sentences to a caller-supplied callback as soon as each one is
# ready, instead of waiting for the whole reply to finish.
from core.sentence_splitter import SentenceSplitter


# ── get_system_prompt() — Loads the Star Trek personality prompt ──
# This is the same across ALL platforms and ALL modes.
# Tells the AI to act like the Enterprise computer and respond in
# the structured format (RESPONSE: ... ACTIONS: ...).
# ── JSON output format override ───────────────────────────────────
# shared/prompts/system_prompt.txt is loaded (unmodified) by ALL
# THREE platforms — desktop, Android's ClaudeService.kt, and iOS's
# ClaudeService.swift, which bundles the same file as a resource and
# falls back to an inline copy of the same RESPONSE:/ACTIONS: text
# format if the bundled copy is missing. That means we can't change
# the shared file's output-format instructions here without also
# updating both mobile parsers in lockstep — out of scope for this
# pass (see the desktop-only decision explained in the project
# notes). Instead, desktop appends this addendum to the shared
# prompt, which explicitly tells the model to IGNORE the shared
# file's RESPONSE:/ACTIONS: text format and reply with strict JSON
# instead. Only desktop's own _parse_response() below expects that
# JSON shape, so Android/iOS (which never see this addendum) are
# completely unaffected.
_JSON_FORMAT_ADDENDUM = """

IMPORTANT — OUTPUT FORMAT OVERRIDE FOR THIS CLIENT:
Ignore the "RESPONSE:" / "ACTIONS:" text format described above.
Instead, reply with ONLY a single JSON object, no markdown code
fences, no commentary before or after it, in exactly this shape:

{"response": "<what you say out loud, 1-3 sentences>", "actions": [{"action": "<action_type>", "params": {"<key>": "<value>"}}]}

Rules:
- "response" is always a string (use "" if you have nothing to say).
- "actions" is always an array (use [] if no actions are needed).
- Every array entry needs both "action" (a string) and "params" (an
  object, possibly empty: {}).
- Output must be valid JSON — a machine parses it with json.loads(),
  not a human, so it must parse on the first try.

This desktop client also supports SEVEN additional action types not
listed above:

- "sleep_mode" (params: duration_seconds, optional — defaults to 300
  if omitted). Use it when the user asks you to stop listening for a
  while — e.g. "Computer, stop listening", "go to sleep", "mute
  yourself", "leave me alone for 10 minutes". Respond with the
  sleep_mode action AND a short spoken acknowledgement in "response"
  (e.g. "Entering sleep mode.").
- "get_weather" (params: location, optional — uses the user's
  configured default location if omitted). Use it when the user asks
  about current weather conditions anywhere.
- "get_calendar_events" (params: days, optional int — defaults to 7).
  Use it when the user asks what's on their calendar / schedule /
  upcoming events.
- "add_reminder" (params: text — what to be reminded of). Use it when
  the user asks you to remind them of something or add a to-do.
- "list_reminders" (no params). Use it when the user asks what their
  reminders/to-dos are.
- "complete_reminder" (params: query — text that identifies which
  reminder, e.g. the words the user used to describe it). Use it when
  the user says a reminder is done / to check it off / to complete it.
- "journal_entry" (params: text — what to save, transcribed from what
  the user said). Use it when the user says something like "Computer,
  journal entry: ..." or asks you to log/save/record a journal entry
  or a thought. Requires the journal_entry plugin to be active (see
  desktop/plugins/examples/journal_entry_plugin.py) -- if it's not
  installed, this action's result will say so.

Each of these returns its result as plain text that you should relay
back to the user conversationally in a FUTURE turn (once you see the
action's result in the conversation) — for the turn where you ISSUE
the action itself, just acknowledge briefly in "response" (e.g. "Let
me check.", "One moment.", "Adding that now.").
"""


def get_system_prompt():
    """
    Load the Star Trek computer system prompt from the shared file,
    with the JSON output-format addendum appended (see
    _JSON_FORMAT_ADDENDUM above for why the addendum lives here
    instead of in the shared file itself).
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
            base_prompt = f.read()
    except FileNotFoundError:
        # If the shared prompt file is missing (e.g. a stripped-down
        # deployment that only ships the desktop/ folder), fall back
        # to a minimal built-in prompt so the assistant still works,
        # just without its full Star Trek personality.
        base_prompt = "You are the computer from the USS Enterprise."
    return base_prompt + _JSON_FORMAT_ADDENDUM


# ── process_with_ai() — Main entry point (used by make_it_so.py) ──
# Tries online first, falls back to offline if online fails.
def process_with_ai(user_text, config, conversation_history=None,
                     on_sentence=None):
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
    on_sentence : callable or None
        Optional callback: on_sentence(sentence_text). When provided
        AND the online Claude path is used, it's called once per
        COMPLETE sentence of the spoken reply as soon as that
        sentence is ready — while the rest of the reply may still be
        generating — so a caller can start speaking it immediately
        (see core/tts.py's SpeechQueue). If the result dict's
        "streamed" key comes back True, every sentence of
        "spoken_text" has already been delivered via on_sentence and
        the caller should NOT speak spoken_text again itself.
        Ignored (never called) for the offline Ollama path, which
        doesn't support streaming — see process_with_ollama().

    RETURNS
    -------
    dict or None
        {"spoken_text": str, "actions": list, "streamed": bool} on
        success, or None if every available AI backend failed.
        "streamed" is always present; it's False whenever
        on_sentence wasn't used (no callback given, or the offline
        path was used).
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
        if on_sentence is not None:
            result = process_with_claude_streaming(
                user_text, config, conversation_history, on_sentence
            )
        else:
            result = process_with_claude(user_text, config, conversation_history)
        # A non-None result means Claude answered successfully —
        # we're done, no need to try the offline model too.
        if result is not None:
            result.setdefault("streamed", False)
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
    # attempt above failed and fell through. Ollama has no streaming
    # support here (see process_with_ollama()'s "stream": False), so
    # on_sentence is never called for this path — the caller falls
    # back to speaking the whole "spoken_text" itself once we return,
    # exactly like before streaming TTS existed.
    print("  [ai] Using offline AI (Ollama)...")
    result = process_with_ollama(user_text, config, conversation_history)
    if result is not None:
        result.setdefault("streamed", False)
    return result


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
        requests = _import_requests()
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


# ── process_with_claude_streaming() — streaming TTS entry point ──
def process_with_claude_streaming(user_text, config, conversation_history=None,
                                   on_sentence=None):
    """
    Like process_with_claude(), but reads Claude's reply as an SSE
    (server-sent events) stream and calls on_sentence(text) for each
    complete sentence of the "response" field as soon as it's ready
    — instead of waiting for the whole JSON reply, actions and all,
    to finish generating first.

    WHY THIS IS SAFE TO STREAM
    ---------------------------
    The system prompt (_JSON_FORMAT_ADDENDUM) always asks the model
    for {"response": "<spoken text>", "actions": [...]} with
    "response" first. _JSONResponseFieldExtractor below watches the
    raw text stream for that field's string value character by
    character (handling JSON escapes) and hands decoded characters to
    a SentenceSplitter, which only releases a sentence once it's sure
    where it ends (see core/sentence_splitter.py) — abbreviations,
    decimals, etc. This means on_sentence() sees the same sentences
    a full-text parse would produce, just earlier.

    Once the stream finishes, we still run the FULL buffered reply
    through the normal _parse_response() so "actions" (which arrive
    LAST in the JSON and can't be acted on until they're complete
    anyway) come back exactly as they would from the non-streaming
    path.

    RETURNS
    -------
    dict or None
        Same shape as process_with_claude(), plus "streamed": True.
        Returns None ONLY if the request failed before ANY text
        streamed back (bad key, network error, non-200 status) — at
        that point nothing has been spoken yet, so the caller can
        safely retry with the plain non-streaming path. If the
        connection drops PARTWAY through, we do not return None
        (some sentences may already have been spoken via
        on_sentence — losing that result would leave the caller with
        no record of what the user already heard), we instead return
        best-effort results from whatever text arrived.
    """
    api_key = config.get("anthropic_api_key", "")
    if not api_key:
        print("  [ai] No Anthropic API key found in config.yaml.")
        return None
    if on_sentence is None:
        # Nobody wants sentences as they arrive — the plain
        # non-streaming call is simpler and behaves identically for
        # the final result.
        return process_with_claude(user_text, config, conversation_history)

    messages = _build_claude_messages(user_text, conversation_history)
    print("  [ai] Sending to Claude API (streaming)...")

    field_extractor = _JSONResponseFieldExtractor("response")
    splitter = SentenceSplitter()
    full_text_parts = []
    any_text_received = False

    try:
        requests = _import_requests()
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
                "temperature": 0.7,
                "stream": True
            },
            timeout=30,
            stream=True
        )
        try:
            if response.status_code != 200:
                print(f"  [ai] Claude error: {response.status_code}")
                return None

            for raw_line in response.iter_lines(decode_unicode=True):
                if not raw_line or not raw_line.startswith("data:"):
                    continue
                payload = raw_line[len("data:"):].strip()
                if not payload:
                    continue
                try:
                    event = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if event.get("type") != "content_block_delta":
                    continue
                delta = event.get("delta", {})
                if delta.get("type") != "text_delta":
                    continue
                text_piece = delta.get("text", "")
                if not text_piece:
                    continue
                any_text_received = True
                full_text_parts.append(text_piece)
                new_field_text = field_extractor.feed(text_piece)
                if new_field_text:
                    for sentence in splitter.feed(new_field_text):
                        on_sentence(sentence)
        finally:
            response.close()

        for sentence in splitter.flush():
            on_sentence(sentence)

    except Exception as e:
        print(f"  [ai] Claude streaming error: {e}")
        if not any_text_received:
            # Nothing was ever spoken — safe for the caller to retry
            # with the ordinary non-streaming path instead.
            return None
        # Some sentences may already have been spoken. Fall through
        # and do our best with whatever text we did get, rather than
        # discarding it.

    full_response = "".join(full_text_parts)
    if not full_response:
        return None
    result = _parse_response(full_response)
    result["streamed"] = True
    return result


class _JSONResponseFieldExtractor:
    """
    Incrementally pulls the decoded string VALUE of one field (by
    default "response") out of a streaming JSON object shaped like
    {"response": "text...", "actions": [...]} — without needing the
    whole JSON object to have arrived yet.

    This is deliberately narrow — not a general JSON streaming
    parser — it only needs to handle the exact shape our system
    prompt asks the model for: a flat object with a "response"
    string field. It DOES fully handle JSON string escapes (\\",
    \\\\, \\n, \\t, \\uXXXX, etc.) since Claude's replies routinely
    contain escaped quotes.
    """

    _SEEK_KEY = "seek_key"
    _SEEK_COLON = "seek_colon"
    _SEEK_QUOTE = "seek_quote"
    _IN_STRING = "in_string"
    _DONE = "done"

    _SIMPLE_ESCAPES = {
        '"': '"', "\\": "\\", "/": "/", "n": "\n",
        "t": "\t", "r": "\r", "b": "\b", "f": "\f",
    }

    def __init__(self, field_name="response"):
        self._needle = f'"{field_name}"'
        self._scan_tail = ""
        self._state = self._SEEK_KEY
        self._pending_escape = False
        self._unicode_digits = None

    def feed(self, chunk):
        """
        Feed a chunk of raw streamed JSON text. Returns a string of
        any newly-decoded characters of the target field's value
        (possibly "" if this chunk didn't complete any).
        """
        out = []
        for ch in chunk:
            if self._state == self._DONE:
                break
            if self._state == self._SEEK_KEY:
                self._scan_tail += ch
                if len(self._scan_tail) > len(self._needle):
                    self._scan_tail = self._scan_tail[-len(self._needle):]
                if self._scan_tail == self._needle:
                    self._state = self._SEEK_COLON
                    self._scan_tail = ""
            elif self._state == self._SEEK_COLON:
                if ch == ":":
                    self._state = self._SEEK_QUOTE
            elif self._state == self._SEEK_QUOTE:
                if ch == '"':
                    self._state = self._IN_STRING
                # Any whitespace between ':' and the opening quote is
                # simply skipped; anything else would mean the field
                # isn't a string, which shouldn't happen given our
                # system prompt — we just stay in this state rather
                # than crashing.
            elif self._state == self._IN_STRING:
                decoded = self._consume_string_char(ch)
                if decoded is not None:
                    out.append(decoded)
        return "".join(out)

    def _consume_string_char(self, ch):
        if self._unicode_digits is not None:
            self._unicode_digits += ch
            if len(self._unicode_digits) == 4:
                digits = self._unicode_digits
                self._unicode_digits = None
                try:
                    return chr(int(digits, 16))
                except ValueError:
                    return None
            return None

        if self._pending_escape:
            self._pending_escape = False
            if ch in self._SIMPLE_ESCAPES:
                return self._SIMPLE_ESCAPES[ch]
            if ch == "u":
                self._unicode_digits = ""
                return None
            # Unknown escape sequence — emit the character literally
            # rather than silently dropping it.
            return ch

        if ch == "\\":
            self._pending_escape = True
            return None
        if ch == '"':
            # Unescaped quote ends the string value.
            self._state = self._DONE
            return None
        return ch


def _import_requests():
    """
    Imported lazily (not at module load time) so a machine without
    the `requests` library installed can still import this whole
    module — e.g. to use _is_ollama_running()'s urllib-based
    reachability check — without crashing at startup. Split into its
    own function (mirroring core/actions/integrations.py's pattern)
    so tests can monkeypatch just this one function to inject a fake
    `requests` module instead of touching the real network.
    """
    import requests
    return requests


_OLLAMA_BASE_URL = "http://localhost:11434"


# ── Model capability hints ────────────────────────────────────────
# Deliberately NOT a full capability-detection system — just a small,
# config-overridable lookup table so callers can make a reasonable
# guess about context-window size (and whether a model is a "small,
# fast" or "larger, smarter" one) without querying anything extra.
# Unknown models fall back to a conservative default rather than
# guessing wrong.
_KNOWN_MODEL_CAPABILITIES = {
    "llama3.2:1b": {"context_window": 128000, "size_class": "small"},
    "llama3.2": {"context_window": 128000, "size_class": "small"},
    "llama3.1": {"context_window": 128000, "size_class": "large"},
    "llama3": {"context_window": 8192, "size_class": "medium"},
    "mistral": {"context_window": 32000, "size_class": "medium"},
    "phi3": {"context_window": 128000, "size_class": "small"},
    "qwen2.5": {"context_window": 128000, "size_class": "medium"},
    "gemma2": {"context_window": 8192, "size_class": "medium"},
}
_DEFAULT_MODEL_CAPABILITIES = {"context_window": 8192, "size_class": "unknown"}


def get_model_capabilities(model, config=None):
    """
    Return a {"context_window": int, "size_class": str} hint for
    `model`, used only for logging / lightweight prompt tuning — not
    a claim about the model's real capabilities.

    Lookup order: an explicit `ollama_context_window` override in
    config.yaml, then an exact match on the model's full name
    (including tag, e.g. "llama3.2:1b"), then a match on just the
    name before any ":tag", then a generic default for anything we
    don't recognize.
    """
    config = config or {}
    base_name = model.split(":")[0]
    info = dict(
        _KNOWN_MODEL_CAPABILITIES.get(
            model,
            _KNOWN_MODEL_CAPABILITIES.get(base_name, _DEFAULT_MODEL_CAPABILITIES),
        )
    )
    override = config.get("ollama_context_window")
    if isinstance(override, int) and override > 0:
        info["context_window"] = override
    return info


# ── Model listing / pulling ───────────────────────────────────────
def list_ollama_models(timeout_seconds=5):
    """
    Return the list of model names currently available in the local
    Ollama installation — the same information `ollama list` shows —
    by calling Ollama's REST API GET /api/tags.

    Returns [] (never raises) on any failure: Ollama not running,
    network error, unexpected JSON shape. Callers can treat "no
    models" and "couldn't check" the same way without extra
    try/except of their own.
    """
    try:
        requests = _import_requests()
        response = requests.get(
            f"{_OLLAMA_BASE_URL}/api/tags", timeout=timeout_seconds
        )
        if response.status_code != 200:
            print(f"  [ai] Ollama /api/tags error: {response.status_code}")
            return []
        data = response.json()
        models = data.get("models", [])
        return [m["name"] for m in models if isinstance(m, dict) and m.get("name")]
    except Exception as e:
        print(f"  [ai] Could not list local Ollama models: {e}")
        return []


def is_model_available(model, timeout_seconds=5):
    """
    Check whether `model` is already pulled locally.

    Ollama tags an untagged name to ":latest" internally, so
    "llama3.2" and "llama3.2:latest" refer to the same local model —
    we treat those as equivalent instead of requiring an exact string
    match, which would otherwise report a false "not available" for
    the (very common) case of a config value with no explicit tag.
    """
    available = list_ollama_models(timeout_seconds=timeout_seconds)
    if model in available:
        return True
    if ":" not in model and f"{model}:latest" in available:
        return True
    if model.endswith(":latest") and model[: -len(":latest")] in available:
        return True
    return False


def pull_model(model, timeout_seconds=1800):
    """
    Trigger `ollama pull <model>` via Ollama's REST API
    (POST /api/pull).

    This can take anywhere from a few seconds to many minutes
    depending on the model's size and the connection speed — larger
    models are several GB — so we print clear before/after feedback
    rather than blocking silently. The request itself blocks until
    the pull finishes (stream: False) since we have no caller today
    that needs incremental progress; `timeout_seconds` defaults to
    30 minutes to give big models room to finish.

    Returns True on success, False on any failure (bad status,
    reported error, network problem, timeout).
    """
    print(f"  [ai] Model '{model}' not found locally — pulling it now.")
    print("  [ai] This can take several minutes for larger models. "
          "Please be patient...")
    try:
        requests = _import_requests()
        response = requests.post(
            f"{_OLLAMA_BASE_URL}/api/pull",
            json={"name": model, "stream": False},
            timeout=timeout_seconds,
        )
        if response.status_code != 200:
            print(f"  [ai] Ollama pull error: {response.status_code}")
            return False
        result = response.json()
        status = str(result.get("status", ""))
        if "error" in status.lower():
            print(f"  [ai] Ollama pull failed: {status}")
            return False
        print(f"  [ai] Model '{model}' pulled successfully.")
        return True
    except Exception as e:
        print(f"  [ai] Ollama pull error: {e}")
        return False


def ensure_model_available(model, timeout_seconds=5, pull_timeout_seconds=1800):
    """
    Make sure `model` is available locally, pulling it via
    pull_model() if it isn't yet.

    Returns True if the model is (now) available, False if it
    couldn't be confirmed available and the pull attempt also failed.
    """
    if is_model_available(model, timeout_seconds=timeout_seconds):
        return True
    return pull_model(model, timeout_seconds=pull_timeout_seconds)


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

    if not is_model_available(model):
        if config.get("ollama_auto_pull", False):
            # Opt-in only: a pull can take many minutes, which would
            # otherwise silently stall the voice assistant the first
            # time someone speaks to it after changing ollama_model.
            # We already know the model is missing (just checked
            # above), so pull directly rather than going through
            # ensure_model_available() and re-checking availability a
            # second time.
            if not pull_model(model):
                print(f"  [ai] Could not make model '{model}' available "
                      "— giving up on this offline request.")
                return None
        else:
            print(f"  [ai] Configured Ollama model '{model}' isn't "
                  "pulled locally yet.")
            print(f"  [ai]   Run: ollama pull {model}")
            print("  [ai]   (or set ollama_auto_pull: true in config.yaml "
                  "to pull it automatically next time)")
            # Fall through and try anyway — Ollama may still know how
            # to resolve the name (e.g. a registry alias), and if not
            # it'll fail with a clear error from the API itself below.

    capabilities = get_model_capabilities(model, config)
    conversation_text = _build_ollama_prompt(user_text, conversation_history)

    print(f"  [ai] Sending to local Ollama (model: {model}, "
          f"~{capabilities['size_class']}, "
          f"context window ~{capabilities['context_window']} tokens)...")
    try:
        requests = _import_requests()
        response = requests.post(
            f"{_OLLAMA_BASE_URL}/api/generate",
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
#
# The system prompt (see _JSON_FORMAT_ADDENDUM above) instructs the
# model to reply with a single strict JSON object:
#   {"response": "<spoken text>",
#    "actions": [{"action": "open_app", "params": {"name": "Safari"}}]}
#
# We parse that with json.loads() — no hand-rolled pattern matching,
# no ambiguity about where one field ends and the next begins. This
# also structurally fixes the whole CLASS of bug the old regex parser
# had (see git history: the first action in a list could be silently
# dropped because of an off-by-one in the "- action:" splitting
# regex) — a JSON array has no such "first item is different from the
# rest" edge case to get wrong.
#
# _parse_response_legacy() below is kept ONLY as a fallback for the
# rare case a model ignores the JSON instruction and replies in the
# old "RESPONSE: ... ACTIONS: ..." text shape anyway (this can happen
# with small/local Ollama models that don't follow instructions as
# reliably as Claude does) — better to still get a usable reply than
# to return nothing.
def _parse_response(full_text):
    """
    Split the AI's raw reply into the spoken-aloud text and the list
    of structured actions to run.

    Tries strict JSON first (the format the system prompt asks for).
    Falls back to the legacy "RESPONSE:/ACTIONS:" text parser only if
    the reply isn't valid JSON in the expected shape.
    """
    parsed = _parse_response_json(full_text)
    if parsed is not None:
        return parsed
    print("  [ai] Reply wasn't valid JSON — falling back to legacy "
          "RESPONSE:/ACTIONS: text parser.")
    return _parse_response_legacy(full_text)


def _strip_markdown_code_fence(text):
    """
    Strip a surrounding ```json ... ``` or ``` ... ``` code fence, if
    present, so json.loads() can parse the content inside it.

    Some models wrap JSON output in a markdown fence out of habit
    even when told not to — this is a cheap, safe thing to tolerate
    before giving up and falling back to the legacy parser.
    """
    text = text.strip()
    if not text.startswith("```"):
        return text
    # Drop the opening fence line (```json or just ```).
    text = text.split("\n", 1)[1] if "\n" in text else ""
    # Drop a trailing fence line, if present.
    if text.rstrip().endswith("```"):
        text = text.rstrip()[:-3]
    return text.strip()


def _parse_response_json(full_text):
    """
    Try to parse `full_text` as the strict JSON shape the system
    prompt asks for: {"response": str, "actions": [{"action": str,
    "params": dict}, ...]}.

    Returns the parsed {"spoken_text", "actions"} dict on success, or
    None if `full_text` isn't valid JSON in that shape (letting the
    caller fall back to the legacy text parser instead of crashing).
    """
    candidate = _strip_markdown_code_fence(full_text)
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return None

    # A bare JSON string/number/list (technically valid JSON, but not
    # the object shape we asked for) isn't usable either.
    if not isinstance(data, dict):
        return None

    spoken_text = data.get("response", "")
    if not isinstance(spoken_text, str):
        spoken_text = str(spoken_text)

    raw_actions = data.get("actions", [])
    actions = []
    if isinstance(raw_actions, list):
        for entry in raw_actions:
            # Skip any array entry that isn't itself an object, or
            # has no "action" name — malformed individual actions
            # shouldn't take down the whole response.
            if not isinstance(entry, dict):
                continue
            action_name = entry.get("action")
            if not action_name:
                continue
            params = entry.get("params", {})
            if not isinstance(params, dict):
                params = {}
            actions.append({"action": action_name, "params": params})

    return {"spoken_text": spoken_text.strip(), "actions": actions}


# ── _parse_response_legacy() — old YAML-like text format ─────────
# Kept only as a fallback — see _parse_response()'s docstring above.
def _parse_response_legacy(full_text):
    """
    Split the AI's raw reply into the spoken-aloud text and the list
    of structured actions to run, using the OLD "RESPONSE: ...
    ACTIONS: ..." text layout. Only used when _parse_response_json()
    couldn't parse the reply as JSON.
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
        spoken_text = response_match.group(1).strip()

    # Everything after "ACTIONS:" to the end of the text is the
    # actions block, which _parse_actions_legacy() breaks down
    # further.
    actions_match = re.search(
        r"ACTIONS:\s*(.+)",
        full_text, re.DOTALL
    )
    if actions_match:
        actions_text = actions_match.group(1).strip()
        actions = _parse_actions_legacy(actions_text)

    return {
        "spoken_text": spoken_text,
        "actions": actions
    }


def _parse_actions_legacy(actions_text):
    """
    Parse the legacy ACTIONS section's YAML-like list into a list of
    dicts like {"action": "open_app", "params": {"name": "Safari"}}.
    """
    actions = []
    # Split the whole ACTIONS block wherever a new "- action:" line
    # begins. `(?:\A|\n)` — "the very start of the string, OR a
    # newline" — makes sure the very FIRST "- action:" splits off
    # too, not just later ones (a bug that used to silently drop the
    # first action of every response — see git history).
    action_blocks = re.split(r"(?:\A|\n)\s*-\s+action:", actions_text)

    for block in action_blocks:
        action = _parse_one_action_block_legacy(block)
        if action is not None:
            actions.append(action)

    return actions


def _parse_one_action_block_legacy(block):
    """
    Parse a single legacy action's text chunk (action name + optional
    "params:" section) into {"action": ..., "params": {...}}.

    Returns None for an empty chunk (e.g. the leading fragment
    before the first "- action:" that re.split() always produces).
    """
    block = block.strip()
    if not block:
        return None

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

    return {"action": action_name, "params": params}
