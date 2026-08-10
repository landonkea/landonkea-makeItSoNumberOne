# ───────────────────────────────────────────────────────────────────
# plugins_builtin.py, built-in actions, expressed as ActionPlugins
# ───────────────────────────────────────────────────────────────────
# Every action the assistant shipped with before the plugin system
# existed (open_app, search_web, sleep_mode, the weather/calendar/
# reminders integrations, etc.) is wired up here as a thin
# ActionPlugin wrapper around the real implementation, which still
# lives in actions/system.py, actions/web_actions.py and actions/
# integrations.py exactly as before, this file adds a uniform
# "shape" over those functions, it doesn't reimplement them.
#
# WHY MIGRATE THE BUILT-INS INSTEAD OF LEAVING THEM AS A SEPARATE
# FAST PATH
# -----------------------------------------------------------------
# If action_router.py special-cased "built-ins go through if/elif,
# third-party plugins go through the registry," the plugin interface
# would be an untested side door nobody but a hypothetical third
# party ever exercises. Routing EVERYTHING (built-in and third-party
# alike) through the same registry means the plugin abstraction is
# proven by the app's own core functionality every time the assistant
# runs, and a third-party plugin author can read this file as a set
# of real, working examples.
#
# WHAT DIDN'T MOVE HERE
# -----------------------
# Routine-matching (core/routines.py's load_routines()/match_routine())
# stays outside the plugin system entirely, it's not itself an
# action, it's what DECIDES to hand a canned list of actions to
# action_router.execute_actions() instead of asking the AI. That's
# core dispatch logic, not something a third party would plausibly
# want to replace by dropping a file in desktop/plugins/.
# ───────────────────────────────────────────────────────────────────

from . import actions
from .plugin_base import ActionPlugin


class OpenAppPlugin(ActionPlugin):
    action_name = "open_app"
    description = "Open an application by name."
    param_schema = {"name": "str, application name, e.g. \"Safari\""}

    def execute(self, params, config):
        return actions.system.open_app(params.get("name", ""))


class SearchWebPlugin(ActionPlugin):
    action_name = "search_web"
    description = "Search the web (DuckDuckGo Instant Answer API)."
    param_schema = {"query": "str, what to search for"}

    def execute(self, params, config):
        return actions.web_actions.search_web(params.get("query", ""), config)


class TypeTextPlugin(ActionPlugin):
    action_name = "type_text"
    description = "Type text at the current cursor position."
    param_schema = {"text": "str, text to type"}

    def execute(self, params, config):
        return actions.system.type_text(params.get("text", ""))


class PressKeysPlugin(ActionPlugin):
    action_name = "press_keys"
    description = "Press a keyboard shortcut."
    param_schema = {
        "keys": "list of str, or comma-separated str, e.g. \"command,space\""
    }

    def execute(self, params, config):
        keys = params.get("keys", "")
        if isinstance(keys, str):
            keys = [k.strip() for k in keys.split(",")]
        return actions.system.press_keys(keys)


class RunCommandPlugin(ActionPlugin):
    action_name = "run_command"
    description = "Run a shell command, subject to the allowlist/confirmation gate."
    param_schema = {"command": "str, shell command to run"}

    def execute(self, params, config):
        # `config` is read for security.allowed_commands /
        # security.command_confirmation_required, see actions/
        # system.py's SECURITY section.
        return actions.system.run_command(params.get("command", ""), config)


class ReadFilePlugin(ActionPlugin):
    action_name = "read_file"
    description = "Read a file's contents, subject to the denylist gate."
    param_schema = {"path": "str, file path"}

    def execute(self, params, config):
        # `config` is read for security.denied_read_paths /
        # security.denied_read_extensions.
        return actions.system.read_file(params.get("path", ""), config)


class ConfirmCommandPlugin(ActionPlugin):
    action_name = "confirm_command"
    description = (
        "Approve and run whatever run_command call is currently "
        "pending confirmation. Takes no params, see actions/system.py's "
        "confirm_pending_command() for why the command text is never "
        "re-supplied at confirmation time."
    )
    param_schema = {}

    def execute(self, params, config):
        return actions.system.confirm_pending_command()


class SleepModePlugin(ActionPlugin):
    action_name = "sleep_mode"
    description = "Mute wake-word listening for a while."
    param_schema = {"duration_seconds": "int/float, optional, defaults to 300"}

    def execute(self, params, config):
        return actions.system.enter_sleep_mode(
            params.get("duration_seconds", actions.system.DEFAULT_MUTE_SECONDS)
        )


class ScrollPlugin(ActionPlugin):
    action_name = "scroll"
    description = "Scroll the screen up or down."
    param_schema = {"direction": "\"up\" or \"down\"", "amount": "int, scroll clicks"}

    def execute(self, params, config):
        return actions.system.scroll(
            params.get("direction", "down"),
            int(params.get("amount", 1)),
        )


class ClickPlugin(ActionPlugin):
    action_name = "click"
    description = "Click at a specific screen position."
    param_schema = {"x": "int, pixel X", "y": "int, pixel Y"}

    def execute(self, params, config):
        return actions.system.click(int(params.get("x", 0)), int(params.get("y", 0)))


class GetWeatherPlugin(ActionPlugin):
    action_name = "get_weather"
    description = "Get current weather conditions for a location."
    param_schema = {
        "location": "str, optional, falls back to integrations.weather.default_location"
    }

    def execute(self, params, config):
        return actions.integrations.get_weather(params.get("location", ""), config)


class GetCalendarEventsPlugin(ActionPlugin):
    action_name = "get_calendar_events"
    description = "List upcoming events from the configured .ics calendar feed."
    param_schema = {"days": "int, optional, how many days ahead, defaults to 7"}

    def execute(self, params, config):
        return actions.integrations.get_calendar_events(
            config, int(params.get("days", 7))
        )


class AddReminderPlugin(ActionPlugin):
    action_name = "add_reminder"
    description = "Create a new Todoist reminder."
    param_schema = {"text": "str, reminder text"}

    def execute(self, params, config):
        return actions.integrations.add_reminder(params.get("text", ""), config)


class ListRemindersPlugin(ActionPlugin):
    action_name = "list_reminders"
    description = "List open (not-yet-completed) Todoist reminders."
    param_schema = {}

    def execute(self, params, config):
        return actions.integrations.list_reminders(config)


class CompleteReminderPlugin(ActionPlugin):
    action_name = "complete_reminder"
    description = "Mark the first open Todoist reminder matching a query as complete."
    param_schema = {"query": "str, text to match against open reminders"}

    def execute(self, params, config):
        return actions.integrations.complete_reminder(params.get("query", ""), config)


# The registry action_router.py loads at startup. Order doesn't
# matter (it's folded into a dict keyed by action_name), but it's
# kept in the same order as the old if/elif chain it replaces so a
# diff against the previous action_router.py is easy to eyeball.
BUILTIN_PLUGINS = [
    OpenAppPlugin(),
    SearchWebPlugin(),
    TypeTextPlugin(),
    PressKeysPlugin(),
    RunCommandPlugin(),
    ReadFilePlugin(),
    ConfirmCommandPlugin(),
    SleepModePlugin(),
    ScrollPlugin(),
    ClickPlugin(),
    GetWeatherPlugin(),
    GetCalendarEventsPlugin(),
    AddReminderPlugin(),
    ListRemindersPlugin(),
    CompleteReminderPlugin(),
]
