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

# Import the "actions" module from the same folder (the dot "."
# means "current package"). The actions module contains all the
# actual handler functions like open_app, search_web, type_text,
# etc. This import makes them available as actions.system, etc.
from . import actions


# Define a function called "execute_action" that takes two arguments:
# "action_dict" (a dictionary describing what to do) and "config"
# (the app's settings). This function runs ONE action and returns
# a message about whether it succeeded or failed.
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

    # ── Route to the correct handler based on action type ─────
    # Each "if/elif" checks the action_type string and calls the
    # correct handler function from the actions module.

    # Check if the action is "open_app" (launch a program).
    if action_type == "open_app":
        # Call the open_app function in actions.system, passing the
        # app name from params. If "name" is missing, use "".
        return actions.system.open_app(params.get("name", ""))

    # Otherwise, check if the action is "search_web" (search Google).
    elif action_type == "search_web":
        # Call the search_web function in actions.web_actions,
        # passing the search query and the full config (for API keys).
        return actions.web_actions.search_web(
            params.get("query", ""),
            config
        )

    # Otherwise, check if the action is "type_text" (type out text).
    elif action_type == "type_text":
        # Call the type_text function with the text to type.
        return actions.system.type_text(params.get("text", ""))

    # Otherwise, check if the action is "press_keys" (keyboard combo).
    elif action_type == "press_keys":
        # Get the keys parameter (e.g., "command,space" or a list).
        keys = params.get("keys", "")
        # Keys can be a string like "command,space" or a list.
        # Check if keys is a string (text) rather than a list.
        if isinstance(keys, str):
            # Split the string by commas and remove extra spaces
            # around each key name. This turns "a, b, c" into
            # ["a", "b", "c"].
            keys = [k.strip() for k in keys.split(",")]
        # Call the press_keys function with the list of key names.
        return actions.system.press_keys(keys)

    # Otherwise, check if the action is "run_command" (run terminal).
    elif action_type == "run_command":
        # Call the run_command function with the command string.
        return actions.system.run_command(params.get("command", ""))

    # Otherwise, check if the action is "read_file" (read a file).
    elif action_type == "read_file":
        # Call the read_file function with the file path.
        return actions.system.read_file(params.get("path", ""))

    # Otherwise, check if the action is "scroll" (scroll up/down).
    elif action_type == "scroll":
        # Call the scroll function with direction (up/down) and
        # amount (how many steps). Convert "amount" to an integer
        # using int() since params always stores strings.
        return actions.system.scroll(
            params.get("direction", "down"),
            int(params.get("amount", 1))
        )

    # Otherwise, check if the action is "click" (mouse click).
    elif action_type == "click":
        # Call the click function with x and y coordinates.
        # Convert both to integers because mouse coordinates are
        # always whole numbers (pixels on screen).
        return actions.system.click(
            int(params.get("x", 0)),
            int(params.get("y", 0))
        )

    # If none of the above action types matched, we don't know
    # what this action is. This is the "catch-all" else block.
    else:
        # Print a warning showing the unknown action type so the
        # developer knows to add support for it in the future.
        print(f"  [router] Unknown action type: \"{action_type}\"")
        # Return None since we couldn't execute the action.
        return None


# Define a function called "execute_actions" (plural) that takes
# two arguments: "action_list" (a list of action dictionaries) and
# "config". This function runs MULTIPLE actions in sequence (one
# after another) and returns all the results as a list.
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
        result = execute_action(action, config)
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
