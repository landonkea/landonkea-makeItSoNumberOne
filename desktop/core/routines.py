# ───────────────────────────────────────────────────────────────────
# routines.py — local trigger-phrase macros (no AI round-trip)
# ───────────────────────────────────────────────────────────────────
# A "routine" maps a trigger phrase (e.g. "good morning") to a canned
# list of actions — the exact same {"action": ..., "params": {...}}
# shape Claude's JSON responses already produce, so we can hand a
# matched routine's action list straight to action_router.
# execute_actions() with no changes to that module at all.
#
# WHY THIS EXISTS
# ----------------
# Some commands are the same every single time ("good morning" always
# opens Mail and checks the weather) — paying for an AI round-trip
# (cost, latency, and a chance the model phrases the action slightly
# differently each time) to run the exact same steps is wasted effort.
# routines.yaml lets the user hard-code these as instant, offline,
# free, deterministic macros. Anything NOT matched here still goes to
# Claude/Ollama exactly as before — this is a fast path, not a
# replacement for the AI brain.
#
# FILE FORMAT (routines.yaml, next to config.yaml)
# --------------------------------------------------
#   good morning:
#     response: "Good morning. Bringing up your briefing."
#     actions:
#       - action: open_app
#         params:
#           name: "Mail"
#
# See routines.example.yaml for a fuller example. The file is
# entirely optional — no routines.yaml means no routines match, ever,
# and every request goes to the AI exactly like before this feature
# existed.
# ───────────────────────────────────────────────────────────────────

import os
import re

ROUTINES_FILE = "routines.yaml"


def load_routines(path=ROUTINES_FILE):
    """
    Load routines.yaml into a dict of {trigger_phrase: routine_dict}.

    RETURNS
    -------
    dict
        Maps each LOWERCASED trigger phrase to
        {"response": str, "actions": list of dict}. Empty dict if the
        file doesn't exist, is empty, isn't valid YAML, or isn't
        shaped the way we expect — a broken/missing routines.yaml
        should never prevent the assistant from starting or from
        handling normal (non-routine) requests.
    """
    if not os.path.exists(path):
        return {}

    try:
        import yaml
        with open(path, "r") as f:
            data = yaml.safe_load(f)
    except Exception as e:
        print(f"  [routines] Could not read {path}: {e}")
        return {}

    if not isinstance(data, dict):
        if data is not None:
            print(f"  [routines] {path} should be a mapping of trigger "
                  f"phrase -> routine — ignoring it.")
        return {}

    routines = {}
    for trigger, body in data.items():
        if not isinstance(trigger, str) or not trigger.strip():
            continue
        parsed = _parse_one_routine(trigger, body)
        if parsed is not None:
            routines[trigger.strip().lower()] = parsed

    if routines:
        print(f"  [routines] Loaded {len(routines)} routine(s) from {path}")
    return routines


def _parse_one_routine(trigger, body):
    """
    Validate and normalize a single routine entry.

    RETURNS
    -------
    dict or None
        {"response": str, "actions": list of dict}, or None if `body`
        isn't shaped like a usable routine (logged, not raised — one
        malformed routine shouldn't take down every other routine or
        crash startup).
    """
    if not isinstance(body, dict):
        print(f"  [routines] Routine \"{trigger}\" is malformed "
              f"(expected a mapping) — skipping it.")
        return None

    response = body.get("response", "")
    if not isinstance(response, str):
        response = str(response)

    raw_actions = body.get("actions", [])
    if not isinstance(raw_actions, list):
        print(f"  [routines] Routine \"{trigger}\" has a non-list "
              f"\"actions\" — treating it as having none.")
        raw_actions = []

    actions = []
    for entry in raw_actions:
        if not isinstance(entry, dict):
            continue
        action_name = entry.get("action")
        if not action_name:
            continue
        params = entry.get("params", {})
        if not isinstance(params, dict):
            params = {}
        actions.append({"action": action_name, "params": params})

    return {"response": response.strip(), "actions": actions}


def _normalize(text):
    """
    Lowercase and strip everything except letters/digits/spaces, and
    collapse repeated whitespace — so "Good Morning!" and "good
    morning" (or "good   morning") both compare equal.
    """
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def match_routine(user_text, routines):
    """
    Check whether `user_text` invokes one of the loaded `routines`.

    A routine matches when its trigger phrase appears as a WHOLE-WORD
    substring of the (normalized) user text — e.g. trigger "good
    morning" matches "computer, good morning" and "good morning
    computer" but NOT "goodness morning" (no partial-word matches).
    This is deliberately simple (no fuzzy matching, no AI involved) so
    routine behavior is 100% predictable — the whole point of a
    routine is that it does the SAME thing every time, unlike Claude's
    responses which can vary.

    If more than one routine's trigger matches, the LONGEST trigger
    phrase wins (e.g. "good morning" vs. "morning" both matching
    "good morning everyone" should prefer the more specific one).

    PARAMETERS
    ----------
    user_text : str
        The transcribed thing the user said.
    routines : dict
        Loaded from load_routines() — {trigger_phrase: routine_dict}.

    RETURNS
    -------
    dict or None
        The matched routine ({"response", "actions"}), or None if no
        trigger phrase matches (or `routines` is empty).
    """
    if not routines or not user_text:
        return None

    normalized_text = _normalize(user_text)
    if not normalized_text:
        return None

    best_match = None
    best_length = -1
    for trigger, routine in routines.items():
        normalized_trigger = _normalize(trigger)
        if not normalized_trigger:
            continue
        pattern = r"\b" + re.escape(normalized_trigger) + r"\b"
        if re.search(pattern, normalized_text):
            if len(normalized_trigger) > best_length:
                best_match = routine
                best_length = len(normalized_trigger)

    return best_match
