# ───────────────────────────────────────────────────────────────────
# tests/test_ai_parsing.py — tests for core/ai.py's response parser
# ───────────────────────────────────────────────────────────────────
# WHY THESE TESTS EXIST
# ----------------------
# core/ai.py's _parse_response() used to rely on a hand-rolled regex
# to split the AI's "RESPONSE: ... ACTIONS: ..." text reply into
# spoken text + a list of actions. That parser had a real bug (the
# first action in a list could be silently dropped — see git
# history). This pass switches the desktop client to ask the model
# for strict JSON instead and parse it with json.loads(), which
# structurally can't have a "first item is different from the rest"
# bug the way a regex-based splitter can. These tests cover: the new
# JSON happy path (including the multi-action case that used to
# trigger the old bug), a markdown-fenced JSON reply, and the legacy
# text-format fallback for models that ignore the JSON instruction.
#
# HOW TO RUN
# ----------
#   cd desktop
#   python3 -m unittest discover -s tests -v
# ───────────────────────────────────────────────────────────────────

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import ai  # noqa: E402  (import after sys.path fix, on purpose)


class ParseResponseJsonTests(unittest.TestCase):
    """Tests for the primary JSON parsing path."""

    def test_simple_response_no_actions(self):
        text = '{"response": "Hello, Captain.", "actions": []}'
        result = ai._parse_response(text)
        self.assertEqual(result["spoken_text"], "Hello, Captain.")
        self.assertEqual(result["actions"], [])

    def test_multiple_actions_first_one_is_not_dropped(self):
        # This is the exact shape of bug the old regex parser had:
        # the FIRST action in the list must come through just as
        # reliably as any later one.
        text = (
            '{"response": "Opening Safari and searching.", '
            '"actions": ['
            '{"action": "open_app", "params": {"name": "Safari"}}, '
            '{"action": "search_web", "params": {"query": "pizza"}}'
            ']}'
        )
        result = ai._parse_response(text)
        self.assertEqual(len(result["actions"]), 2)
        self.assertEqual(result["actions"][0]["action"], "open_app")
        self.assertEqual(result["actions"][0]["params"], {"name": "Safari"})
        self.assertEqual(result["actions"][1]["action"], "search_web")
        self.assertEqual(result["actions"][1]["params"], {"query": "pizza"})

    def test_action_with_no_params_defaults_to_empty_dict(self):
        text = '{"response": "Confirmed.", "actions": [{"action": "confirm_command"}]}'
        result = ai._parse_response(text)
        self.assertEqual(result["actions"], [{"action": "confirm_command", "params": {}}])

    def test_action_missing_action_key_is_skipped(self):
        text = (
            '{"response": "Hmm.", "actions": '
            '[{"params": {"name": "Safari"}}, '
            '{"action": "open_app", "params": {"name": "Safari"}}]}'
        )
        result = ai._parse_response(text)
        self.assertEqual(len(result["actions"]), 1)
        self.assertEqual(result["actions"][0]["action"], "open_app")

    def test_missing_actions_key_defaults_to_empty_list(self):
        text = '{"response": "Just talking, no actions."}'
        result = ai._parse_response(text)
        self.assertEqual(result["actions"], [])

    def test_markdown_fenced_json_is_still_parsed(self):
        text = (
            "```json\n"
            '{"response": "Done.", "actions": '
            '[{"action": "open_app", "params": {"name": "Mail"}}]}'
            "\n```"
        )
        result = ai._parse_response(text)
        self.assertEqual(result["spoken_text"], "Done.")
        self.assertEqual(result["actions"][0]["action"], "open_app")

    def test_non_dict_json_falls_back_to_legacy(self):
        # A bare JSON array/string is technically valid JSON, but not
        # the {"response", "actions"} object shape we asked for — it
        # should fall through to the legacy parser (which will just
        # treat the whole thing as ordinary text with no actions,
        # since it has no RESPONSE:/ACTIONS: markers either).
        text = '["not", "the", "right", "shape"]'
        result = ai._parse_response(text)
        self.assertEqual(result["actions"], [])


class ParseResponseLegacyFallbackTests(unittest.TestCase):
    """Tests for the legacy RESPONSE:/ACTIONS: fallback parser, used
    only when a reply isn't valid JSON."""

    def test_legacy_format_still_works_as_fallback(self):
        text = (
            "RESPONSE: Opening Safari.\n\n"
            "ACTIONS:\n"
            "- action: open_app\n"
            "  params:\n"
            "    name: Safari\n"
        )
        result = ai._parse_response(text)
        self.assertEqual(result["spoken_text"], "Opening Safari.")
        self.assertEqual(len(result["actions"]), 1)
        self.assertEqual(result["actions"][0]["action"], "open_app")
        self.assertEqual(result["actions"][0]["params"], {"name": "Safari"})

    def test_legacy_multiple_actions_first_one_not_dropped(self):
        # Regression check for the original bug this whole pass is
        # named after, still verified on the fallback path.
        text = (
            "RESPONSE: Doing two things.\n\n"
            "ACTIONS:\n"
            "- action: open_app\n"
            "  params:\n"
            "    name: Safari\n"
            "- action: search_web\n"
            "  params:\n"
            "    query: pizza\n"
        )
        result = ai._parse_response(text)
        self.assertEqual(len(result["actions"]), 2)
        self.assertEqual(result["actions"][0]["action"], "open_app")
        self.assertEqual(result["actions"][1]["action"], "search_web")


class GetSystemPromptTests(unittest.TestCase):
    """Sanity checks that the JSON format instructions are actually
    present in what gets sent to the model."""

    def test_system_prompt_instructs_json_output(self):
        prompt = ai.get_system_prompt()
        self.assertIn("json.loads()", prompt)
        self.assertIn('"response"', prompt)
        self.assertIn('"actions"', prompt)

    def test_system_prompt_mentions_sleep_mode(self):
        prompt = ai.get_system_prompt()
        self.assertIn("sleep_mode", prompt)


if __name__ == "__main__":
    unittest.main()
