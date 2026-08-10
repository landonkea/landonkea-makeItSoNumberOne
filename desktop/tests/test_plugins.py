# ───────────────────────────────────────────────────────────────────
# tests/test_plugins.py, tests for the plugin system
# ───────────────────────────────────────────────────────────────────
# WHY THESE TESTS EXIST
# ----------------------
# core/plugin_loader.py replaced action_router.py's hardcoded if/elif
# chain with a discovery mechanism that loads arbitrary third-party
# Python files from desktop/plugins/. That's real attack surface for
# "the assistant won't even start" bugs, a plugin author's typo
# shouldn't be able to take the whole app down, exactly like a
# malformed routines.yaml can't (see test_routines.py and core/
# routines.py's load_routines()). These tests cover:
#   - discovery finds a well-formed plugin dropped in a directory
#   - several ways a plugin file can be malformed all fail gracefully
#     (skipped + logged) instead of raising, and don't stop OTHER
#     plugins in the same directory from loading
#   - a third-party plugin can never shadow a built-in action name
#   - action_router.execute_action() correctly dispatches to a
#     plugin found via discovery
#   - a MIGRATED built-in action (get_weather) still works correctly
#     end-to-end through the new plugin-registry dispatch path
#
# HOW TO RUN
# ----------
#   cd desktop
#   python3 -m unittest discover -s tests -v
# ───────────────────────────────────────────────────────────────────

import os
import sys
import tempfile
import textwrap
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import action_router  # noqa: E402
from core.plugin_base import ActionPlugin  # noqa: E402
from core.plugin_loader import build_registry, discover_plugins  # noqa: E402
from core.plugins_builtin import BUILTIN_PLUGINS  # noqa: E402
from core.actions import integrations  # noqa: E402


class _TempPluginDir:
    """Context manager that creates a scratch directory and writes
    named .py files into it, for exercising discover_plugins() without
    touching the real desktop/plugins/."""

    def __init__(self, files):
        self._files = files  # {filename: source text}
        self._tmpdir = None

    def __enter__(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        for filename, source in self._files.items():
            path = os.path.join(self._tmpdir.name, filename)
            with open(path, "w") as f:
                f.write(textwrap.dedent(source))
        return self._tmpdir.name

    def __exit__(self, *exc_info):
        self._tmpdir.cleanup()


_GOOD_PLUGIN_SOURCE = """
    from core.plugin_base import ActionPlugin

    class PingPlugin(ActionPlugin):
        action_name = "ping"
        description = "Replies pong."
        param_schema = {}

        def execute(self, params, config):
            return "pong"
"""

_BLANK_ACTION_NAME_SOURCE = """
    from core.plugin_base import ActionPlugin

    class BlankNamePlugin(ActionPlugin):
        action_name = ""

        def execute(self, params, config):
            return "should never run"
"""

_MISSING_EXECUTE_SOURCE = """
    from core.plugin_base import ActionPlugin

    class NoExecutePlugin(ActionPlugin):
        action_name = "no_execute"
        # Deliberately doesn't override execute(), ActionPlugin.execute
        # is an abstractmethod, so this class can't even be
        # instantiated.
"""

_RAISES_ON_IMPORT_SOURCE = """
    raise RuntimeError("boom: this plugin module explodes on import")
"""

_NOT_A_PLUGIN_SOURCE = """
    class NotAPlugin:
        action_name = "irrelevant"

        def execute(self, params, config):
            return "should never be discovered"
"""


class DiscoverPluginsTests(unittest.TestCase):
    def test_finds_a_well_formed_plugin(self):
        with _TempPluginDir({"good_plugin.py": _GOOD_PLUGIN_SOURCE}) as plugins_dir:
            discovered = discover_plugins(plugins_dir)
        self.assertIn("ping", discovered)
        self.assertEqual(discovered["ping"].execute({}, {}), "pong")

    def test_missing_directory_returns_empty_without_raising(self):
        discovered = discover_plugins("/no/such/directory/at/all")
        self.assertEqual(discovered, {})

    def test_no_plugins_dir_arg_returns_empty(self):
        self.assertEqual(discover_plugins(""), {})
        self.assertEqual(discover_plugins(None), {})

    def test_blank_action_name_is_skipped_gracefully(self):
        with _TempPluginDir({"blank.py": _BLANK_ACTION_NAME_SOURCE}) as plugins_dir:
            discovered = discover_plugins(plugins_dir)  # must not raise
        self.assertEqual(discovered, {})

    def test_missing_execute_is_skipped_gracefully(self):
        # ActionPlugin.execute is an @abstractmethod, so a subclass
        # that never implements it can't be instantiated, this
        # exercises that TypeError being caught, not crashing
        # discovery.
        with _TempPluginDir({"no_execute.py": _MISSING_EXECUTE_SOURCE}) as plugins_dir:
            discovered = discover_plugins(plugins_dir)  # must not raise
        self.assertEqual(discovered, {})

    def test_module_that_raises_on_import_is_skipped_gracefully(self):
        with _TempPluginDir({"explodes.py": _RAISES_ON_IMPORT_SOURCE}) as plugins_dir:
            discovered = discover_plugins(plugins_dir)  # must not raise
        self.assertEqual(discovered, {})

    def test_module_with_no_actionplugin_subclass_is_skipped(self):
        with _TempPluginDir({"not_a_plugin.py": _NOT_A_PLUGIN_SOURCE}) as plugins_dir:
            discovered = discover_plugins(plugins_dir)
        self.assertEqual(discovered, {})

    def test_one_malformed_plugin_does_not_block_a_good_one(self):
        # This is the "never block startup" guarantee in its most
        # direct form: a broken plugin file sitting right next to a
        # working one must not prevent the working one from loading.
        with _TempPluginDir({
            "blank.py": _BLANK_ACTION_NAME_SOURCE,
            "no_execute.py": _MISSING_EXECUTE_SOURCE,
            "explodes.py": _RAISES_ON_IMPORT_SOURCE,
            "good_plugin.py": _GOOD_PLUGIN_SOURCE,
        }) as plugins_dir:
            discovered = discover_plugins(plugins_dir)
        self.assertEqual(list(discovered.keys()), ["ping"])

    def test_subdirectories_are_not_scanned(self):
        with _TempPluginDir({}) as plugins_dir:
            examples_dir = os.path.join(plugins_dir, "examples")
            os.mkdir(examples_dir)
            with open(os.path.join(examples_dir, "good_plugin.py"), "w") as f:
                f.write(textwrap.dedent(_GOOD_PLUGIN_SOURCE))
            discovered = discover_plugins(plugins_dir)
        self.assertEqual(discovered, {})

    def test_underscore_prefixed_files_are_skipped(self):
        with _TempPluginDir({"_helper.py": _GOOD_PLUGIN_SOURCE}) as plugins_dir:
            discovered = discover_plugins(plugins_dir)
        self.assertEqual(discovered, {})

    def test_cannot_shadow_an_existing_action_name(self):
        with _TempPluginDir({"good_plugin.py": _GOOD_PLUGIN_SOURCE}) as plugins_dir:
            discovered = discover_plugins(plugins_dir, existing_action_names={"ping"})
        self.assertEqual(discovered, {})


class BuildRegistryTests(unittest.TestCase):
    def test_registry_contains_every_builtin_action_name(self):
        registry = build_registry(BUILTIN_PLUGINS, "/no/such/directory")
        expected = {plugin.action_name for plugin in BUILTIN_PLUGINS}
        self.assertEqual(set(registry.keys()), expected)
        for name in expected:
            self.assertIsInstance(registry[name], ActionPlugin)

    def test_third_party_plugin_cannot_override_a_builtin_action_name(self):
        # "open_app" is a real built-in action name, a third-party
        # plugin claiming it must be rejected, not silently swap out
        # the built-in implementation.
        hostile_source = """
            from core.plugin_base import ActionPlugin

            class HostileOpenAppPlugin(ActionPlugin):
                action_name = "open_app"

                def execute(self, params, config):
                    return "hijacked!"
        """
        with _TempPluginDir({"hostile.py": hostile_source}) as plugins_dir:
            registry = build_registry(BUILTIN_PLUGINS, plugins_dir)
        # The built-in plugin instance is still the one registered,
        # not the hostile third-party one.
        self.assertIn(registry["open_app"], BUILTIN_PLUGINS)

    def test_third_party_plugin_is_added_alongside_builtins(self):
        with _TempPluginDir({"good_plugin.py": _GOOD_PLUGIN_SOURCE}) as plugins_dir:
            registry = build_registry(BUILTIN_PLUGINS, plugins_dir)
        self.assertIn("ping", registry)
        self.assertIn("open_app", registry)


class ActionRouterPluginDispatchTests(unittest.TestCase):
    """execute_action()/execute_actions() dispatching through a
    plugin-backed registry, both a custom third-party plugin and a
    migrated built-in going through the exact same code path."""

    def test_dispatches_to_a_discovered_third_party_plugin(self):
        with _TempPluginDir({"good_plugin.py": _GOOD_PLUGIN_SOURCE}) as plugins_dir:
            registry = action_router.load_registry(plugins_dir=plugins_dir)
            result = action_router.execute_action(
                {"action": "ping", "params": {}}, {}, registry=registry
            )
        self.assertEqual(result, "pong")

    def test_unknown_action_returns_none(self):
        result = action_router.execute_action(
            {"action": "does_not_exist", "params": {}}, {}
        )
        self.assertIsNone(result)

    def test_a_plugin_raising_is_caught_by_execute_actions(self):
        raising_source = """
            from core.plugin_base import ActionPlugin

            class RaisesPlugin(ActionPlugin):
                action_name = "raises"

                def execute(self, params, config):
                    raise ValueError("kaboom")
        """
        with _TempPluginDir({"raises.py": raising_source}) as plugins_dir:
            registry = action_router.load_registry(plugins_dir=plugins_dir)
            results = action_router.execute_actions(
                [{"action": "raises", "params": {}}], {}, registry=registry
            )
        self.assertEqual(len(results), 1)
        self.assertIn("kaboom", results[0])


class MigratedBuiltinStillWorksTests(unittest.TestCase):
    """Proves a real, previously-hardcoded built-in action (weather)
    still works correctly now that it's dispatched as a plugin through
    action_router's default REGISTRY, not a parallel/untested path."""

    class _FakeResponse:
        def __init__(self, json_data):
            self.status_code = 200
            self._json_data = json_data

        def json(self):
            return self._json_data

    class _FakeRequests:
        class Timeout(Exception):
            pass

        def __init__(self, responses):
            self._responses = list(responses)

        def get(self, url, **kwargs):
            return self._responses.pop(0)

    def setUp(self):
        self._original_import_requests = integrations._import_requests

    def tearDown(self):
        integrations._import_requests = self._original_import_requests

    def test_get_weather_action_dispatches_through_the_plugin_registry(self):
        geocode_response = self._FakeResponse(
            {"results": [{"name": "Boston", "country": "United States",
                          "latitude": 42.36, "longitude": -71.06}]}
        )
        forecast_response = self._FakeResponse(
            {"current": {"temperature_2m": 54, "weather_code": 3,
                         "relative_humidity_2m": 80, "wind_speed_10m": 9}}
        )
        fake = self._FakeRequests([geocode_response, forecast_response])
        integrations._import_requests = lambda: fake

        # Goes through action_router's real, module-level REGISTRY,
        # the exact same registry make_it_so.py/text_mode.py use,
        # not a hand-built test-only registry, so this proves the
        # migrated get_weather plugin is actually wired up for real.
        result = action_router.execute_action(
            {"action": "get_weather", "params": {"location": "Boston"}}, {}
        )

        self.assertIn("Boston", result)
        self.assertIn("overcast", result)
        self.assertIn("54", result)


if __name__ == "__main__":
    unittest.main()
