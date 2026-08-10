# ───────────────────────────────────────────────────────────────────
# tests/test_config_validation.py, tests for make_it_so.py's
# config.yaml schema validation and conversation history persistence
# ───────────────────────────────────────────────────────────────────
# WHY THESE TESTS EXIST
# ----------------------
# load_config() used to silently return {} (or, on a YAML syntax
# error, crash outright) with no indication of WHICH key in
# config.yaml was the problem. validate_config() now checks every
# present key against CONFIG_SCHEMA and reports the exact dotted key
# name and what's wrong with it. These tests exercise that schema
# check directly (valid config, missing keys, which is fine, wrong
# top-level type, wrong nested type, bad "mode" choice, the bool-vs-
# int gotcha) without needing an actual config.yaml file on disk.
#
# A second test class covers conversation history persistence
# (save_conversation_history/load_conversation_history), which now
# round-trips history to a JSON file instead of losing it on every
# restart.
#
# HOW TO RUN
# ----------
#   cd desktop
#   python3 -m unittest discover -s tests -v
# ───────────────────────────────────────────────────────────────────

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import make_it_so  # noqa: E402  (import after sys.path fix, on purpose)


class ValidateConfigTests(unittest.TestCase):
    def test_empty_config_has_no_errors(self):
        self.assertEqual(make_it_so.validate_config({}), [])

    def test_fully_valid_config_has_no_errors(self):
        config = {
            "mode": "auto",
            "anthropic_api_key": "sk-ant-xxx",
            "tts": {"voice": "Samantha", "rate": 200},
            "settings": {
                "max_record_seconds": 10,
                "silence_timeout": 1.5,
                "max_history": 20,
            },
            "security": {
                "allowed_commands": ["ls", "pwd"],
                "command_confirmation_required": True,
            },
        }
        self.assertEqual(make_it_so.validate_config(config), [])

    def test_missing_keys_are_not_errors(self):
        # Nothing in the schema is mandatory, an empty/partial
        # config.yaml is valid, since every consumer has its own
        # sane default for an absent key.
        self.assertEqual(make_it_so.validate_config({"mode": "auto"}), [])

    def test_wrong_top_level_type_is_reported_by_name(self):
        errors = make_it_so.validate_config({"anthropic_api_key": 12345})
        self.assertEqual(len(errors), 1)
        self.assertIn("anthropic_api_key", errors[0])
        self.assertIn("str", errors[0])

    def test_invalid_mode_choice_is_reported(self):
        errors = make_it_so.validate_config({"mode": "turbo"})
        self.assertEqual(len(errors), 1)
        self.assertIn("mode", errors[0])
        self.assertIn("turbo", errors[0])

    def test_wrong_nested_type_is_reported_with_dotted_path(self):
        errors = make_it_so.validate_config({"tts": {"rate": "fast"}})
        self.assertEqual(len(errors), 1)
        self.assertIn("tts.rate", errors[0])

    def test_wrong_settings_type_reported_with_dotted_path(self):
        errors = make_it_so.validate_config(
            {"settings": {"max_history": "twenty"}}
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("settings.max_history", errors[0])

    def test_bool_does_not_silently_pass_as_int(self):
        # isinstance(True, int) is True in Python -- make sure a
        # bool value for an int-typed field is still flagged instead
        # of slipping through.
        errors = make_it_so.validate_config({"tts": {"rate": True}})
        self.assertEqual(len(errors), 1)
        self.assertIn("tts.rate", errors[0])

    def test_wrong_type_for_whole_nested_section_is_reported(self):
        errors = make_it_so.validate_config({"tts": "not a mapping"})
        self.assertEqual(len(errors), 1)
        self.assertIn("tts", errors[0])

    def test_multiple_errors_are_all_reported(self):
        errors = make_it_so.validate_config(
            {"mode": "bogus", "tts": {"rate": "fast"}}
        )
        self.assertEqual(len(errors), 2)

    def test_valid_integrations_section_has_no_errors(self):
        config = {
            "integrations": {
                "weather": {
                    "provider": "openweathermap",
                    "openweathermap_api_key": "abc123",
                    "default_location": "Boston",
                },
                "calendar": {
                    "ics_url": "https://example.com/cal.ics",
                    "ics_username": "alice",
                    "ics_password": "hunter2",
                },
                "reminders": {"todoist_api_token": "tok"},
            }
        }
        self.assertEqual(make_it_so.validate_config(config), [])

    def test_invalid_weather_provider_choice_is_reported(self):
        errors = make_it_so.validate_config(
            {"integrations": {"weather": {"provider": "carrier-pigeon"}}}
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("integrations.weather.provider", errors[0])

    def test_wrong_type_in_integrations_section_reported_with_dotted_path(self):
        errors = make_it_so.validate_config(
            {"integrations": {"reminders": {"todoist_api_token": 12345}}}
        )
        self.assertEqual(len(errors), 1)
        self.assertIn("integrations.reminders.todoist_api_token", errors[0])


class ConversationHistoryPersistenceTests(unittest.TestCase):
    def setUp(self):
        # Point HISTORY_FILE at a temp path for the duration of each
        # test so these tests never touch a real desktop/
        # conversation_history.json, and restore it afterward.
        self._original_history_file = make_it_so.HISTORY_FILE
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(path)  # start absent, like a fresh install
        self._temp_path = path
        make_it_so.HISTORY_FILE = path

    def tearDown(self):
        make_it_so.HISTORY_FILE = self._original_history_file
        if os.path.exists(self._temp_path):
            os.remove(self._temp_path)

    def test_load_with_no_file_returns_empty_list(self):
        self.assertEqual(make_it_so.load_conversation_history(), [])

    def test_save_then_load_round_trips(self):
        history = [
            {"role": "user", "content": "Open Safari"},
            {"role": "assistant", "content": "RESPONSE: Opening Safari."},
        ]
        make_it_so.save_conversation_history(history)
        loaded = make_it_so.load_conversation_history()
        self.assertEqual(loaded, history)

    def test_load_with_corrupt_json_returns_empty_list(self):
        with open(self._temp_path, "w") as f:
            f.write("{not valid json")
        self.assertEqual(make_it_so.load_conversation_history(), [])

    def test_load_with_non_list_json_returns_empty_list(self):
        with open(self._temp_path, "w") as f:
            f.write('{"not": "a list"}')
        self.assertEqual(make_it_so.load_conversation_history(), [])


if __name__ == "__main__":
    unittest.main()
