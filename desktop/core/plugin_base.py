# ───────────────────────────────────────────────────────────────────
# plugin_base.py — the ActionPlugin interface
# ───────────────────────────────────────────────────────────────────
# Every action the assistant can run (built-in or third-party) is a
# small class that implements this interface. action_router.py builds
# a {action_name: plugin_instance} registry out of:
#   1. The built-in plugins in core/plugins_builtin.py (open_app,
#      search_web, get_weather, sleep_mode, etc. — see that file).
#   2. Any third-party plugins auto-discovered from desktop/plugins/
#      at startup (see core/plugin_loader.py).
# and dispatches each action by looking it up in that registry — no
# hardcoded if/elif chain of action names anywhere anymore.
#
# WHY A CLASS (NOT JUST A FUNCTION)
# ----------------------------------
# A plain function could do the "execute" part, but bundling the
# action's NAME and a PARAMETER SCHEMA onto the same object as its
# handler means a plugin is fully self-describing — plugin_loader.py
# can validate it (does it declare a name? is execute() callable?)
# without any separate registration step, and a future "list what
# actions are available" feature (or the AI system prompt itself)
# could introspect param_schema instead of that being hand-maintained
# prose in ai.py.
#
# WRITING YOUR OWN PLUGIN
# -------------------------
# See desktop/plugins/examples/hello_world_plugin.py for a fully
# worked template, and the "Writing a plugin" section of README.md.
# ───────────────────────────────────────────────────────────────────

from abc import ABC, abstractmethod


class ActionPlugin(ABC):
    """
    Base class for one voice-assistant action.

    Subclass this and set:
      - `action_name` (required): the string Claude's ACTIONS block
        uses to invoke this plugin, e.g. "open_app". Must be unique —
        a third-party plugin can never override a built-in action
        name, and two third-party plugins can't claim the same name
        either (see plugin_loader.py's discover_plugins()).
      - `description` (optional): one line describing what the
        action does — for humans reading plugin listings/docs.
      - `param_schema` (optional): a dict of {param_name:
        human-readable description} documenting what `params` keys
        `execute()` expects. Informal (not enforced/validated) — it's
        documentation, not a JSON Schema validator.

    Then implement `execute()`.
    """

    action_name: str = ""
    description: str = ""
    param_schema: dict = {}

    @abstractmethod
    def execute(self, params: dict, config: dict) -> str:
        """
        Run the action and return a result message.

        PARAMETERS
        ----------
        params : dict
            The action's parameters, e.g. {"name": "Safari"} for an
            open_app action. Same shape as the `params` field of the
            action dict Claude/a routine produced — always a dict,
            possibly empty, never None.
        config : dict
            The app's full configuration (config.yaml contents), in
            case the action needs API keys / settings. Plugins that
            don't need it can just ignore the parameter.

        RETURNS
        -------
        str
            A human-readable result, spoken/shown back to the user.
            NEVER raise for an expected/foreseeable error condition
            (bad params, missing config, a network failure, etc.) —
            return a clear message describing what went wrong instead,
            the same convention every built-in action in this codebase
            follows. action_router.py DOES catch unexpected exceptions
            around every plugin call so one buggy plugin can't abort a
            whole batch of actions, but relying on that is a last
            resort, not the normal error-handling path.
        """
        raise NotImplementedError
