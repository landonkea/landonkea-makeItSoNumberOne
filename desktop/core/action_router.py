# ───────────────────────────────────────────────────────────────────
# action_router.py — executes Claude's action commands
# ───────────────────────────────────────────────────────────────────
# After Claude processes the user's request and returns action
# commands, this module routes each action to the right handler.
#
# For example, if Claude says:
#   - action: open_app
#     params:
#       name: Safari
#
# The router looks up "open_app" in a REGISTRY of ActionPlugin
# instances (core/plugin_base.py's ActionPlugin interface) and calls
# its execute() method.
#
# WHERE THE REGISTRY COMES FROM
# --------------------------------
# Every action is a plugin — there's no separate fast path for
# built-ins vs. third-party actions:
#   1. Built-in plugins (open_app, search_web, sleep_mode, the
#      weather/calendar/reminders integrations, etc.) come from
#      core/plugins_builtin.py's BUILTIN_PLUGINS list.
#   2. Third-party plugins are auto-discovered at import time from
#      the desktop/plugins/ directory (gitignored — see
#      desktop/plugins/examples/ for a template, and README.md's
#      "Writing a plugin" section for how to write your own) by
#      core/plugin_loader.py.
# A third-party plugin can never override a built-in action name —
# see plugin_loader.build_registry()/discover_plugins() for that
# collision handling, and for why a malformed plugin file is logged
# and skipped rather than crashing startup (same philosophy as
# routines.yaml — see core/routines.py).
#
# This is like the "transporter room" — it receives commands and
# routes them to the right department (system control, web search,
# file operations, etc.), it just does that via a lookup table now
# instead of a long if/elif chain.
# ───────────────────────────────────────────────────────────────────

import os

from .plugin_loader import build_registry
from .plugins_builtin import BUILTIN_PLUGINS

# desktop/core/action_router.py -> desktop/plugins. Resolved from
# this file's own location (not the process's current working
# directory) so the registry loads correctly regardless of where the
# assistant was launched from.
PLUGINS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "plugins"
)


def load_registry(plugins_dir=PLUGINS_DIR, builtin_plugins=None):
    """
    Build the {action_name: plugin_instance} registry used to
    dispatch actions. A thin wrapper around plugin_loader.
    build_registry() so callers (including tests) don't need to know
    about plugins_builtin.BUILTIN_PLUGINS directly, and so tests can
    point `plugins_dir` at a temporary directory instead of the real
    desktop/plugins/.
    """
    return build_registry(
        BUILTIN_PLUGINS if builtin_plugins is None else builtin_plugins,
        plugins_dir,
    )


# Built once at import time — mirrors routines.yaml being loaded once
# at startup rather than re-read on every request. Tests that need a
# custom registry (e.g. to exercise plugin discovery against a
# scratch directory) can call load_registry(...) themselves and pass
# the result straight into execute_action()/execute_actions() via the
# `registry` parameter instead of touching this module-level default.
REGISTRY = load_registry()


# Define a function called "execute_action" that takes two arguments:
# "action_dict" (a dictionary describing what to do) and "config"
# (the app's settings). This function runs ONE action and returns
# a message about whether it succeeded or failed.
def execute_action(action_dict, config, registry=None, profile=None):
    """
    Execute a single action returned by Claude.

    PARAMETERS
    ----------
    action_dict : dict
        An action from Claude's response, e.g.:
        {"action": "open_app", "params": {"name": "Safari"}}
    config : dict
        The app configuration (API keys, settings).
    registry : dict, optional
        {action_name: plugin_instance} to dispatch through. Defaults
        to the module-level REGISTRY (built-ins + whatever was
        discovered in desktop/plugins/ at import time). Tests pass
        their own registry here to exercise a specific plugin set
        without touching the real one.
    profile : dict, optional
        The active personalization profile (see core/profile.py:
        get_active_profile()). If given, contact nicknames and
        preferred-app aliases in `action_dict`'s params are resolved
        against it BEFORE dispatch (e.g. an action with
        params={"number": "Mom"} becomes params={"number": "+1..."}).
        None (the default) skips resolution entirely, e.g. for
        callers/tests that don't use profiles.

    RETURNS
    -------
    str or None
        A result message (e.g. "Done" or error description).
        None if the action type is unknown.
    """
    registry = REGISTRY if registry is None else registry

    if profile:
        from . import profile as profile_module
        action_dict = profile_module.resolve_action_params(action_dict, profile)

    # Extract the "action" field from the action dictionary (e.g.,
    # "open_app", "search_web"). .get() returns an empty string if
    # the key doesn't exist, which prevents a KeyError crash.
    action_type = action_dict.get("action", "")
    # Extract the "params" field from the action dictionary (e.g.,
    # {"name": "Safari"}). If there are no params, default to an
    # empty dictionary so we can still call .get() on it safely.
    params = action_dict.get("params", {})

    # Print a log message showing which action we're about to run
    # (so the user can see what Claude instructed the computer to do).
    print(f"  [router] Executing action: {action_type}")
    # Check if there are any parameters for this action.
    if params:
        # Print the parameters so the user knows the details
        # (e.g., which app to open, what text to type).
        print(f"  [router] Params: {params}")

    # ── Route to the correct handler via the plugin registry ──────
    plugin = registry.get(action_type)
    if plugin is None:
        # If none of the registered plugins matched, we don't know
        # what this action is. Print a warning showing the unknown
        # action type so the developer knows to add support for it
        # (or the user knows their third-party plugin didn't load —
        # check the "[plugins]" startup log lines).
        print(f"  [router] Unknown action type: \"{action_type}\"")
        return None

    return plugin.execute(params, config)


# Define a function called "execute_actions" (plural) that takes
# two arguments: "action_list" (a list of action dictionaries) and
# "config". This function runs MULTIPLE actions in sequence (one
# after another) and returns all the results as a list.
def execute_actions(action_list, config, registry=None, profile=None):
    """
    Execute a list of actions returned by Claude.

    PARAMETERS
    ----------
    action_list : list of dict
        List of action dictionaries to execute in order.
    config : dict
        The app configuration.
    registry : dict, optional
        See execute_action() — defaults to the module-level REGISTRY.
    profile : dict, optional
        See execute_action() — the active personalization profile
        used to resolve contact nicknames / preferred-app aliases in
        each action's params before dispatch.

    RETURNS
    -------
    list of str
        Results from each action (success/error messages).
    """
    # Check if the action list is empty or None. An empty list
    # means Claude didn't have any actions for us to run.
    if not action_list:
        # Print a message saying there's nothing to do.
        print("  [router] No actions to execute")
        # Return an empty list (no results because no actions ran).
        return []

    # Print how many actions we're about to run (useful for
    # debugging and user feedback).
    print(f"  [router] Executing {len(action_list)} action(s)...")
    # Create an empty list called "results" to store the result
    # message from each action as we run them.
    results = []

    # Loop through each action in the action list. enumerate()
    # gives us both the position number (i) and the action itself.
    for i, action in enumerate(action_list):
        # Print which action number we're on out of the total
        # (e.g., "Action 2/5:"). This helps track progress.
        print(f"  [router] Action {i+1}/{len(action_list)}:")
        # Call execute_action() to run this single action, passing
        # the action dict and the config. Store whatever it returns.
        #
        # This is wrapped in try/except because params come from
        # Claude's text response, not validated user input. E.g. a
        # "scroll" action with amount="a lot" instead of a number
        # would raise ValueError inside int(). Without this guard,
        # one malformed action would raise an uncaught exception and
        # abort the ENTIRE batch, silently skipping every action
        # after it. Catching it here means one bad action just
        # reports an error while the rest of the list still runs.
        # This also covers a third-party plugin's execute() raising
        # an unexpected exception — same "one bad action doesn't
        # sink the batch" guarantee applies to plugins as to any
        # built-in action.
        try:
            result = execute_action(action, config, registry=registry, profile=profile)
        except Exception as e:
            print(f"  [router]   -> Action failed: {e}")
            result = f"Error: {e}"
        # Check if the result is truthy (not None, not empty string).
        if result:
            # Add the result message to our results list.
            results.append(result)
            # Print the result so the user can see what happened.
            print(f"  [router]   -> Result: {result}")
        # If the result was falsy (None or empty), handle that case.
        else:
            # Add a placeholder string "(no result)" so the results
            # list still has one entry per action for consistency.
            results.append("(no result)")

    # Return the full list of result messages to the caller.
    return results
