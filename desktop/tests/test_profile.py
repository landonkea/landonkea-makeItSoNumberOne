# ───────────────────────────────────────────────────────────────────
# tests/test_profile.py, tests for core/profile.py personalization
# ───────────────────────────────────────────────────────────────────
# WHY THESE TESTS EXIST
# ----------------------
# core/profile.py is the "who is talking to the assistant right now"
# personalization layer: per-profile name/preferred-apps/contacts,
# multi-profile loading (both the flat single-user shape and the
# wrapped multi-profile shape), nickname/alias resolution before
# action dispatch, and voice-driven profile switching. These tests
# cover all of that directly, without touching the real profile.yaml
# on disk.
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

from core import profile  # noqa: E402


class LoadProfilesTests(unittest.TestCase):
    def _write(self, content):
        f = tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        )
        f.write(content)
        f.close()
        self.addCleanup(os.unlink, f.name)
        return f.name

    def test_missing_file_returns_empty_store(self):
        store = profile.load_profiles(path="/nonexistent/profile.yaml")
        self.assertEqual(store, {"profiles": {}, "active": None})

    def test_flat_format_becomes_one_default_profile(self):
        path = self._write(
            "name: \"Landon\"\n"
            "preferred_apps:\n"
            "  email: \"Mail\"\n"
            "contacts:\n"
            "  mom: \"+15555550123\"\n"
        )
        store = profile.load_profiles(path=path)
        self.assertEqual(list(store["profiles"].keys()), ["default"])
        self.assertEqual(store["active"], "default")
        active = profile.get_active_profile(store)
        self.assertEqual(active["name"], "Landon")
        self.assertEqual(active["preferred_apps"]["email"], "Mail")
        self.assertEqual(active["contacts"]["mom"], "+15555550123")

    def test_multi_profile_format_with_explicit_active(self):
        path = self._write(
            "active_profile: guest\n"
            "profiles:\n"
            "  landon:\n"
            "    name: \"Landon\"\n"
            "  guest:\n"
            "    name: \"Guest\"\n"
        )
        store = profile.load_profiles(path=path)
        self.assertEqual(sorted(store["profiles"].keys()), ["guest", "landon"])
        self.assertEqual(store["active"], "guest")
        self.assertEqual(profile.get_active_profile(store)["name"], "Guest")

    def test_single_profile_in_wrapped_format_becomes_active_by_default(self):
        path = self._write(
            "profiles:\n"
            "  landon:\n"
            "    name: \"Landon\"\n"
        )
        store = profile.load_profiles(path=path)
        self.assertEqual(store["active"], "landon")

    def test_unknown_active_profile_is_ignored(self):
        path = self._write(
            "active_profile: nobody\n"
            "profiles:\n"
            "  landon:\n"
            "    name: \"Landon\"\n"
            "  guest:\n"
            "    name: \"Guest\"\n"
        )
        store = profile.load_profiles(path=path)
        # More than one profile exists and the named active isn't
        # valid, so no active profile is picked automatically.
        self.assertIsNone(store["active"])

    def test_malformed_profile_entry_is_skipped_not_fatal(self):
        path = self._write(
            "profiles:\n"
            "  landon:\n"
            "    name: \"Landon\"\n"
            "  broken: \"not a mapping\"\n"
        )
        store = profile.load_profiles(path=path)
        self.assertEqual(list(store["profiles"].keys()), ["landon"])

    def test_not_a_mapping_returns_empty_store(self):
        path = self._write("- just\n- a\n- list\n")
        store = profile.load_profiles(path=path)
        self.assertEqual(store, {"profiles": {}, "active": None})

    def test_empty_file_returns_empty_store(self):
        path = self._write("")
        store = profile.load_profiles(path=path)
        self.assertEqual(store, {"profiles": {}, "active": None})


class GetActiveProfileTests(unittest.TestCase):
    def test_none_store_returns_empty_profile(self):
        active = profile.get_active_profile(None)
        self.assertEqual(active["name"], "")
        self.assertEqual(active["contacts"], {})

    def test_no_active_set_returns_empty_profile(self):
        store = {"profiles": {"landon": {"name": "Landon"}}, "active": None}
        active = profile.get_active_profile(store)
        self.assertEqual(active["name"], "")


class ResolveContactAndAppTests(unittest.TestCase):
    def setUp(self):
        self.profile = {
            "name": "Landon",
            "preferred_apps": {"email": "Mail", "browser": "Safari"},
            "contacts": {"mom": "+15555550123", "the boss": "+15555559999"},
        }

    def test_resolve_contact_exact(self):
        self.assertEqual(
            profile.resolve_contact(self.profile, "Mom"), "+15555550123"
        )

    def test_resolve_contact_is_case_and_punctuation_insensitive(self):
        self.assertEqual(
            profile.resolve_contact(self.profile, "MOM!"), "+15555550123"
        )

    def test_resolve_contact_multi_word_nickname(self):
        self.assertEqual(
            profile.resolve_contact(self.profile, "the Boss"), "+15555559999"
        )

    def test_resolve_contact_unknown_returns_none(self):
        self.assertIsNone(profile.resolve_contact(self.profile, "Dad"))

    def test_resolve_preferred_app(self):
        self.assertEqual(
            profile.resolve_preferred_app(self.profile, "email"), "Mail"
        )

    def test_resolve_preferred_app_unknown_returns_none(self):
        self.assertIsNone(profile.resolve_preferred_app(self.profile, "music"))


class ResolveActionParamsTests(unittest.TestCase):
    def setUp(self):
        self.profile = {
            "name": "Landon",
            "preferred_apps": {"email": "Mail"},
            "contacts": {"mom": "+15555550123"},
        }

    def test_resolves_contact_nickname_in_number_param(self):
        action = {"action": "send_sms", "params": {"number": "Mom", "text": "hi"}}
        resolved = profile.resolve_action_params(action, self.profile)
        self.assertEqual(resolved["params"]["number"], "+15555550123")
        self.assertEqual(resolved["params"]["text"], "hi")

    def test_resolves_app_alias_only_for_open_app(self):
        action = {"action": "open_app", "params": {"name": "email"}}
        resolved = profile.resolve_action_params(action, self.profile)
        self.assertEqual(resolved["params"]["name"], "Mail")

    def test_does_not_resolve_app_alias_for_other_actions(self):
        action = {"action": "search_web", "params": {"name": "email"}}
        resolved = profile.resolve_action_params(action, self.profile)
        self.assertEqual(resolved["params"]["name"], "email")

    def test_unresolvable_value_is_left_alone(self):
        action = {"action": "send_sms", "params": {"number": "+15555551234"}}
        resolved = profile.resolve_action_params(action, self.profile)
        self.assertEqual(resolved["params"]["number"], "+15555551234")

    def test_no_profile_returns_action_unchanged(self):
        action = {"action": "send_sms", "params": {"number": "Mom"}}
        resolved = profile.resolve_action_params(action, None)
        self.assertIs(resolved, action)

    def test_original_action_dict_is_not_mutated(self):
        action = {"action": "send_sms", "params": {"number": "Mom"}}
        profile.resolve_action_params(action, self.profile)
        self.assertEqual(action["params"]["number"], "Mom")


class ProfileSwitchDetectionTests(unittest.TestCase):
    def test_switch_to_x_profile_phrase(self):
        self.assertEqual(
            profile.detect_profile_switch_request("switch to Landon's profile"),
            "Landon",
        )

    def test_switch_profile_to_x_phrase(self):
        self.assertEqual(
            profile.detect_profile_switch_request("switch profile to guest"),
            "guest",
        )

    def test_non_switch_phrase_returns_none(self):
        self.assertIsNone(
            profile.detect_profile_switch_request("what's the weather today")
        )

    def test_empty_text_returns_none(self):
        self.assertIsNone(profile.detect_profile_switch_request(""))


class SwitchActiveProfileTests(unittest.TestCase):
    def setUp(self):
        self.store = {
            "profiles": {
                "landon": {"name": "Landon"},
                "guest": {"name": "Guest"},
            },
            "active": "landon",
        }

    def test_switch_by_key(self):
        matched = profile.switch_active_profile(self.store, "guest")
        self.assertEqual(matched, "guest")
        self.assertEqual(self.store["active"], "guest")

    def test_switch_by_display_name(self):
        matched = profile.switch_active_profile(self.store, "Guest")
        self.assertEqual(matched, "guest")
        self.assertEqual(self.store["active"], "guest")

    def test_switch_to_unknown_profile_returns_none_and_leaves_store_unchanged(self):
        matched = profile.switch_active_profile(self.store, "nobody")
        self.assertIsNone(matched)
        self.assertEqual(self.store["active"], "landon")

    def test_switch_with_no_profiles_returns_none(self):
        store = {"profiles": {}, "active": None}
        matched = profile.switch_active_profile(store, "guest")
        self.assertIsNone(matched)


if __name__ == "__main__":
    unittest.main()
