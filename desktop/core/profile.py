# ───────────────────────────────────────────────────────────────────
# profile.py — personalization profiles (name, preferred apps,
# contact nicknames) with multi-profile support
# ───────────────────────────────────────────────────────────────────
# WHY THIS EXISTS
# ----------------
# Personal data (the user's name, which apps they mean by "my email",
# and nicknames like "Mom" -> a real phone number) doesn't belong in
# config.yaml (API keys/settings) or routines.yaml (canned action
# macros) — it's a third, distinct kind of local, personal, never-
# committed data. This module follows the exact same pattern as
# core/routines.py: a gitignored YAML file next to config.yaml, a
# tracked *.example.yaml template, and loader functions that treat a
# missing/malformed file as "no profiles configured" rather than a
# startup failure.
#
# FILE FORMAT (profile.yaml, next to config.yaml — see
# profile.example.yaml for a fuller worked example)
# --------------------------------------------------
#   active_profile: landon
#
#   profiles:
#     landon:
#       name: "Landon"
#       preferred_apps:
#         email: "Mail"
#         browser: "Safari"
#       contacts:
#         mom: "+15555550123"
#
# For backward-compat / the simplest possible single-user setup, a
# FLAT file with no "profiles:" wrapper (just name/preferred_apps/
# contacts at the top level) is also accepted and is treated as one
# profile named "default" — see _looks_flat() below.
#
# MULTI-PROFILE DESIGN — WHAT'S SHARED VS. PER-PROFILE
# -------------------------------------------------------
# Per-profile (this module): name, preferred_apps, contacts. This is
# personalization data that is meaningless — or actively wrong — if
# applied to the wrong person. Resolving "Mom" to a phone number for
# whoever is NOT the active profile would be a real (if low-stakes)
# privacy/correctness bug, not just a cosmetic mismatch.
#
# Deliberately SHARED across all profiles, not duplicated here:
#   - routines.yaml (core/routines.py): trigger-phrase macros like
#     "good morning" are a property of the DEVICE/household ("when
#     anyone says X, do Y"), not of a specific person. A guest profile
#     benefits from the same routines the primary user set up, and
#     routines don't contain another person's private data the way a
#     contact list does.
#   - conversation_history.json: short-term dialogue context for
#     Claude/Ollama. Splitting it per-profile would mean switching
#     profiles wipes conversational continuity for a shared session
#     ("what did I just ask you?" breaking after a profile switch),
#     which is a worse experience than the rare case of one profile's
#     recent turns being visible to the next speaker on the same
#     device in the same sitting. It's also already ephemeral/local
#     (gitignored, capped at 20 entries) rather than durable personal
#     data.
#   - config.yaml (API keys, mode, security settings): infrastructure
#     configuration, not personalization — every profile on the same
#     physical machine shares the same API keys and security policy.
#
# ACTIVE PROFILE SELECTION
# -------------------------
# 1. `active_profile:` in profile.yaml is the config-driven default.
# 2. A voice command ("switch to <name>'s profile") can override it
#    for the rest of the running session via switch_active_profile()
#    — see detect_profile_switch_request() for the phrases matched.
# A session-only switch is intentional: like config.yaml and
# routines.yaml, profile.yaml is treated as read-only at runtime, so
# a voice-triggered switch never silently rewrites the user's own
# YAML file (or clobbers their comments/formatting in it).
# ───────────────────────────────────────────────────────────────────

import os
import re

PROFILE_FILE = "profile.yaml"

# Params that identify a contact recipient across different actions
# (send_sms/make_call on Android & iOS both use "number" today — see
# ActionRouter.kt / ActionRouter.swift — but "to"/"contact"/
# "recipient" are included too so any future action, built-in or
# third-party plugin, that takes a contact-shaped param gets the same
# nickname resolution for free without this list needing to grow in
# lockstep with every new action).
CONTACT_PARAM_KEYS = {"number", "to", "contact", "recipient"}

# Actions whose "name" param is an app-category alias (e.g. "email")
# rather than a literal app name, resolvable via a profile's
# preferred_apps.
_APP_ALIAS_ACTIONS = {"open_app"}

_EMPTY_PROFILE = {"name": "", "preferred_apps": {}, "contacts": {}}


def _normalize(text):
    """
    Lowercase and strip everything except letters/digits/spaces, and
    collapse repeated whitespace — mirrors core/routines.py's
    _normalize() so "Mom", "mom!", and "MOM" all resolve the same
    contact, and "Landon", "landon's", "LANDON" all match the same
    profile.
    """
    if not isinstance(text, str):
        return ""
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _looks_flat(data):
    """
    True if `data` looks like a single flat profile (no "profiles:"
    wrapper) rather than a multi-profile file — i.e. it has none of
    the multi-profile top-level keys but does look like profile
    fields directly.
    """
    return "profiles" not in data and "active_profile" not in data


def load_profiles(path=PROFILE_FILE):
    """
    Load profile.yaml into a profile "store".

    RETURNS
    -------
    dict
        {"profiles": {profile_name: {"name", "preferred_apps",
        "contacts"}}, "active": str or None}. Empty profiles + None
        active if the file doesn't exist, is empty, isn't valid YAML,
        or isn't shaped the way we expect — a broken/missing
        profile.yaml should never prevent the assistant from starting
        (same philosophy as routines.yaml).
    """
    empty_store = {"profiles": {}, "active": None}

    if not os.path.exists(path):
        return empty_store

    try:
        import yaml
        with open(path, "r") as f:
            data = yaml.safe_load(f)
    except Exception as e:
        print(f"  [profile] Could not read {path}: {e}")
        return empty_store

    if data is None:
        return empty_store

    if not isinstance(data, dict):
        print(f"  [profile] {path} should be a mapping — ignoring it.")
        return empty_store

    if _looks_flat(data):
        # Simplest single-user setup: no "profiles:" wrapper at all.
        parsed = _parse_one_profile("default", data)
        profiles = {"default": parsed} if parsed else {}
        active = "default" if profiles else None
        if profiles:
            print(f"  [profile] Loaded 1 profile (flat format) from {path}")
        return {"profiles": profiles, "active": active}

    raw_profiles = data.get("profiles", {})
    if not isinstance(raw_profiles, dict):
        print(f"  [profile] {path}'s \"profiles\" should be a mapping — "
              f"ignoring it.")
        raw_profiles = {}

    profiles = {}
    for name, body in raw_profiles.items():
        if not isinstance(name, str) or not name.strip():
            continue
        parsed = _parse_one_profile(name, body)
        if parsed is not None:
            profiles[name.strip().lower()] = parsed

    active = data.get("active_profile")
    if not isinstance(active, str) or not active.strip():
        active = None
    else:
        active = active.strip().lower()

    if active is not None and active not in profiles:
        print(f"  [profile] active_profile \"{active}\" in {path} has no "
              f"matching entry under \"profiles\" — ignoring it.")
        active = None

    if active is None and profiles:
        # No explicit active_profile — fall back to the only profile
        # if there's exactly one, so a single-profile multi-profile-
        # shaped file still "just works" without extra config.
        if len(profiles) == 1:
            active = next(iter(profiles))

    if profiles:
        print(f"  [profile] Loaded {len(profiles)} profile(s) from {path}"
              + (f" (active: {active})" if active else ""))

    return {"profiles": profiles, "active": active}


def _parse_one_profile(name, body):
    """
    Validate and normalize a single profile entry.

    RETURNS
    -------
    dict or None
        {"name": str, "preferred_apps": dict, "contacts": dict}, or
        None if `body` isn't shaped like a usable profile (logged,
        not raised — one malformed profile shouldn't crash startup or
        take down every other profile).
    """
    if not isinstance(body, dict):
        print(f"  [profile] Profile \"{name}\" is malformed (expected a "
              f"mapping) — skipping it.")
        return None

    display_name = body.get("name", name)
    if not isinstance(display_name, str):
        display_name = str(display_name)

    preferred_apps = body.get("preferred_apps", {})
    if not isinstance(preferred_apps, dict):
        print(f"  [profile] Profile \"{name}\" has a non-mapping "
              f"\"preferred_apps\" — ignoring it.")
        preferred_apps = {}
    normalized_apps = {}
    for category, app_name in preferred_apps.items():
        key = _normalize(category)
        if key and isinstance(app_name, str) and app_name.strip():
            normalized_apps[key] = app_name.strip()

    contacts = body.get("contacts", {})
    if not isinstance(contacts, dict):
        print(f"  [profile] Profile \"{name}\" has a non-mapping "
              f"\"contacts\" — ignoring it.")
        contacts = {}
    normalized_contacts = {}
    for nickname, identifier in contacts.items():
        key = _normalize(nickname)
        if key and isinstance(identifier, str) and identifier.strip():
            normalized_contacts[key] = identifier.strip()

    return {
        "name": display_name.strip(),
        "preferred_apps": normalized_apps,
        "contacts": normalized_contacts,
    }


def get_active_profile(store):
    """
    Return the active profile dict from `store` (as returned by
    load_profiles()), or a harmless empty profile
    ({"name": "", "preferred_apps": {}, "contacts": {}}) if none is
    configured/active — so callers never need a None-check before
    reading profile["contacts"] etc.
    """
    if not store:
        return dict(_EMPTY_PROFILE)
    active = store.get("active")
    profiles = store.get("profiles", {})
    if active and active in profiles:
        return profiles[active]
    return dict(_EMPTY_PROFILE)


def list_profile_names(store):
    """Sorted list of configured profile names (the internal keys)."""
    if not store:
        return []
    return sorted(store.get("profiles", {}).keys())


def resolve_contact(profile, nickname):
    """
    Resolve a nickname (e.g. "Mom") to its stored contact identifier
    (e.g. a phone number) using `profile`'s contacts.

    RETURNS
    -------
    str or None
        The resolved identifier, or None if `nickname` doesn't match
        any configured contact for this profile (in which case the
        caller should leave the original value alone — it might
        already be a real number/handle Claude filled in itself).
    """
    if not profile or not nickname:
        return None
    key = _normalize(nickname)
    if not key:
        return None
    return profile.get("contacts", {}).get(key)


def resolve_preferred_app(profile, category):
    """
    Resolve an app-category alias (e.g. "email") to the profile's
    preferred app for that category (e.g. "Mail").

    RETURNS
    -------
    str or None
        The preferred app name, or None if `category` doesn't match a
        configured preferred_apps entry for this profile.
    """
    if not profile or not category:
        return None
    key = _normalize(category)
    if not key:
        return None
    return profile.get("preferred_apps", {}).get(key)


def resolve_action_params(action_dict, profile):
    """
    Return a COPY of `action_dict` with any contact-nickname or
    preferred-app-alias params resolved against `profile`, leaving
    everything else untouched.

    This is the desktop-side "resolve a nickname before it reaches
    the action" hook: it runs in action_router.execute_action() right
    before dispatch, so any action whose params look like a contact
    reference (see CONTACT_PARAM_KEYS) or an open_app alias gets a
    chance to be resolved deterministically from the active profile
    — deterministically, rather than relying on the AI to have
    correctly transcribed a phone number from a system-prompt hint,
    which matters because a wrong digit here means a text/call goes
    to the wrong person.

    NOTE ON MOBILE (Android/iOS): send_sms/make_call only exist as
    actions on Android/iOS today (see ActionRouter.kt/.swift) — the
    desktop app has no telephony and doesn't dispatch those actions
    itself. Android and iOS each run their own on-device Claude
    client (ClaudeService.kt/.swift) with no shared runtime state
    with desktop, so this resolver can only cover actions the DESKTOP
    app dispatches (open_app today; any future desktop action taking
    a contact-shaped param automatically, e.g. if telephony/SMS ever
    gets a desktop-side plugin). True cross-platform coverage needs
    an equivalent lookup on each mobile platform, reading its own
    local contacts/nickname data — a per-platform resolution, by
    design, not a bug: a phone's contact list already lives on the
    phone.
    """
    if not profile:
        return action_dict

    action_type = action_dict.get("action", "")
    params = action_dict.get("params", {})
    if not isinstance(params, dict) or not params:
        return action_dict

    new_params = dict(params)
    changed = False

    for key, value in params.items():
        if not isinstance(value, str):
            continue
        if key in CONTACT_PARAM_KEYS:
            resolved = resolve_contact(profile, value)
            if resolved:
                new_params[key] = resolved
                changed = True
        elif action_type in _APP_ALIAS_ACTIONS and key == "name":
            resolved = resolve_preferred_app(profile, value)
            if resolved:
                new_params[key] = resolved
                changed = True

    if not changed:
        return action_dict
    return {**action_dict, "params": new_params}


# ── Voice-driven profile switching ──────────────────────────────────
_SWITCH_PATTERNS = [
    # "switch profile to landon" / "switch profiles to landon"
    re.compile(r"switch\s+(?:the\s+)?profiles?\s+to\s+(.+)", re.IGNORECASE),
    # "switch to landon's profile" / "switch to landon profile"
    re.compile(r"switch\s+to\s+(.+?)(?:'s)?\s+profile\b", re.IGNORECASE),
]


def detect_profile_switch_request(user_text):
    """
    Check whether `user_text` is asking to switch the active profile,
    e.g. "Computer, switch to Landon's profile" or "switch profile to
    guest".

    This is deliberately a plain regex match (no AI round-trip) —
    same rationale as core/routines.py's trigger matching: switching
    "who the assistant is personalizing itself for" should be
    instant, offline, and 100% predictable, not dependent on the AI
    correctly inferring intent.

    RETURNS
    -------
    str or None
        The raw candidate name/phrase the user said (NOT yet matched
        against configured profiles — pass it to
        switch_active_profile()), or None if `user_text` doesn't look
        like a switch request at all.
    """
    if not user_text:
        return None
    for pattern in _SWITCH_PATTERNS:
        match = pattern.search(user_text)
        if match:
            candidate = match.group(1).strip()
            if candidate:
                return candidate
    return None


def switch_active_profile(store, candidate):
    """
    Try to switch `store`'s active profile to whichever configured
    profile `candidate` (a raw name/phrase, e.g. from
    detect_profile_switch_request()) refers to.

    Matches against both the profile's internal key (e.g. "landon")
    and its display "name" field (e.g. "Landon"), normalized the same
    way contacts/apps are, so "switch to Landon's profile" matches a
    profile keyed "landon" with name: "Landon" either way.

    Mutates `store["active"]` IN PLACE on a successful match (mirrors
    conversation_history being mutated in place elsewhere in this
    codebase) so callers holding a reference to the same store dict
    see the switch immediately, and returns the matched profile name.

    RETURNS
    -------
    str or None
        The internal name of the profile now active, or None if
        `candidate` didn't match any configured profile (store is
        left unchanged in that case).
    """
    if not store or not candidate:
        return None

    profiles = store.get("profiles", {})
    if not profiles:
        return None

    target = _normalize(candidate)
    if not target:
        return None

    for key, profile in profiles.items():
        if _normalize(key) == target or _normalize(profile.get("name", "")) == target:
            store["active"] = key
            return key

    return None
