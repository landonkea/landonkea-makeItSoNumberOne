# ───────────────────────────────────────────────────────────────────
# tests/test_routines.py — tests for local routines.yaml macros
# ───────────────────────────────────────────────────────────────────
# WHY THESE TESTS EXIST
# ----------------------
# core/routines.py is the local "trigger phrase -> canned actions"
# macro engine (see that module's docstring for the full rationale).
# These tests exercise both halves of it directly:
#   1. load_routines() — parsing/validating routines.yaml's shape,
#      including malformed entries that should be skipped rather than
#      crashing the whole load.
#   2. match_routine() — the phrase-matching logic (whole-word
#      substring match, case/punctuation insensitivity, and the
#      "longest trigger wins" tie-break), all WITHOUT needing a real
#      routines.yaml file on disk.
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

from core import routines  # noqa: E402


class MatchRoutineTests(unittest.TestCase):
    def setUp(self):
        self.routines = {
            "good morning": {
                "response": "Good morning.",
                "actions": [{"action": "open_app", "params": {"name": "Mail"}}],
            },
            "morning": {
                "response": "Morning.",
                "actions": [],
            },
        }

    def test_exact_trigger_matches(self):
        result = routines.match_routine("good morning", self.routines)
        self.assertIsNotNone(result)
        self.assertEqual(result["response"], "Good morning.")

    def test_trigger_matches_as_substring(self):
        result = routines.match_routine(
            "Computer, good morning to you", self.routines
        )
        self.assertEqual(result["response"], "Good morning.")

    def test_case_and_punctuation_insensitive(self):
        result = routines.match_routine("GOOD MORNING!!", self.routines)
        self.assertEqual(result["response"], "Good morning.")

    def test_no_match_returns_none(self):
        self.assertIsNone(routines.match_routine("what time is it", self.routines))

    def test_empty_routines_returns_none(self):
        self.assertIsNone(routines.match_routine("good morning", {}))
        self.assertIsNone(routines.match_routine("good morning", None))

    def test_no_partial_word_match(self):
        # "morning" should NOT match inside "mourning" (whole-word
        # boundary, not a raw substring check).
        self.assertIsNone(
            routines.match_routine("I am in mourning today", self.routines)
        )

    def test_longest_trigger_wins_on_overlap(self):
        # Both "morning" and "good morning" match this text — the
        # more specific ("good morning") should win.
        result = routines.match_routine("say good morning please", self.routines)
        self.assertEqual(result["response"], "Good morning.")


class LoadRoutinesTests(unittest.TestCase):
    def _write_and_load(self, yaml_text):
        with tempfile.NamedTemporaryFile(
            "w", suffix=".yaml", delete=False
        ) as f:
            f.write(yaml_text)
            path = f.name
        try:
            return routines.load_routines(path)
        finally:
            os.remove(path)

    def test_missing_file_returns_empty_dict(self):
        self.assertEqual(routines.load_routines("/no/such/file.yaml"), {})

    def test_valid_routine_parses(self):
        result = self._write_and_load(
            "good morning:\n"
            "  response: \"Morning!\"\n"
            "  actions:\n"
            "    - action: open_app\n"
            "      params:\n"
            "        name: Mail\n"
        )
        self.assertIn("good morning", result)
        self.assertEqual(result["good morning"]["response"], "Morning!")
        self.assertEqual(
            result["good morning"]["actions"],
            [{"action": "open_app", "params": {"name": "Mail"}}],
        )

    def test_trigger_key_is_lowercased(self):
        result = self._write_and_load(
            "Good Morning:\n"
            "  response: \"hi\"\n"
        )
        self.assertIn("good morning", result)
        self.assertNotIn("Good Morning", result)

    def test_malformed_routine_is_skipped_not_fatal(self):
        result = self._write_and_load(
            "good morning: \"not a mapping\"\n"
            "valid one:\n"
            "  response: \"hi\"\n"
            "  actions: []\n"
        )
        self.assertNotIn("good morning", result)
        self.assertIn("valid one", result)

    def test_action_missing_name_is_dropped(self):
        result = self._write_and_load(
            "trigger:\n"
            "  response: \"hi\"\n"
            "  actions:\n"
            "    - params:\n"
            "        name: Mail\n"
            "    - action: open_app\n"
            "      params:\n"
            "        name: Safari\n"
        )
        self.assertEqual(
            result["trigger"]["actions"],
            [{"action": "open_app", "params": {"name": "Safari"}}],
        )

    def test_empty_file_returns_empty_dict(self):
        self.assertEqual(self._write_and_load(""), {})

    def test_non_mapping_top_level_returns_empty_dict(self):
        self.assertEqual(self._write_and_load("- just\n- a\n- list\n"), {})


if __name__ == "__main__":
    unittest.main()
