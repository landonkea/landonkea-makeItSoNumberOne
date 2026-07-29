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
# The router calls `actions.system.open_app("Safari")`.
#
# This is like the "transporter room" — it receives commands and
# routes them to the right department (system control, web search,
# file operations, etc.).
# ───────────────────────────────────────────────────────────────────

from . import actions


def execute_action(action_dict, config):
    """
    Execute a single action returned by Claude.

    PARAMETERS
    ----------
    action_dict : dict
        An action from Claude's response, e.g.:
        {"action": "open_app", "params": {"name": "Safari"}}
    config : dict
        The app configuration (API keys, settings).

    RETURNS
    -------
    str or None
        A result message (e.g. "Done" or error description).
        None if the action type is unknown.
    """
    action_type = action_dict.get("action", "")
    params = action_dict.get("params", {})

    print(f"  [router] Executing action: {action_type}")
    if params:
        print(f"  [router] Params: {params}")

    # ── Route to the correct handler based on action type ─────

    if action_type == "open_app":
        return actions.system.open_app(params.get("name", ""))

    elif action_type == "search_web":
        return actions.web_actions.search_web(
            params.get("query", ""),
            config
        )

    elif action_type == "type_text":
        return actions.system.type_text(params.get("text", ""))

    elif action_type == "press_keys":
        keys = params.get("keys", "")
        # Keys can be a string like "command,space" or a list.
        if isinstance(keys, str):
            keys = [k.strip() for k in keys.split(",")]
        return actions.system.press_keys(keys)

    elif action_type == "run_command":
        return actions.system.run_command(params.get("command", ""))

    elif action_type == "read_file":
        return actions.system.read_file(params.get("path", ""))

    elif action_type == "scroll":
        return actions.system.scroll(
            params.get("direction", "down"),
            int(params.get("amount", 1))
        )

    elif action_type == "click":
        return actions.system.click(
            int(params.get("x", 0)),
            int(params.get("y", 0))
        )

    else:
        print(f"  [router] Unknown action type: \"{action_type}\"")
        return None


def execute_actions(action_list, config):
    """
    Execute a list of actions returned by Claude.

    PARAMETERS
    ----------
    action_list : list of dict
        List of action dictionaries to execute in order.
    config : dict
        The app configuration.

    RETURNS
    -------
    list of str
        Results from each action (success/error messages).
    """
    if not action_list:
        print("  [router] No actions to execute")
        return []

    print(f"  [router] Executing {len(action_list)} action(s)...")
    results = []

    for i, action in enumerate(action_list):
        print(f"  [router] Action {i+1}/{len(action_list)}:")
        result = execute_action(action, config)
        if result:
            results.append(result)
            print(f"  [router]   -> Result: {result}")
        else:
            results.append("(no result)")

    return results
