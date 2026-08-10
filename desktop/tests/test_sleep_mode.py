# ───────────────────────────────────────────────────────────────────
# tests/test_sleep_mode.py, tests for the sleep_mode ("stop
# listening"/mute) action
# ───────────────────────────────────────────────────────────────────
# WHY THESE TESTS EXIST
# ----------------------
# sleep_mode lets the user say "Computer, stop listening" to mute
# wake-word listening for a while. The mute-tracking logic
# (core/actions/system.py's enter_sleep_mode/is_muted/
# mute_seconds_remaining) is deliberately kept free of any audio/mic
# dependency specifically so it CAN be unit tested without touching
# real hardware, these tests exercise that logic directly, plus the
# action_router.py wiring that connects the "sleep_mode" action type
# to it.
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

from core import action_router  # noqa: E402
from core.actions import system  # noqa: E402


class SleepModeTests(unittest.TestCase):
    def setUp(self):
        # Reset mute state before each test so tests can't leak into
        # one another.
        system._mute_until = 0.0

    def test_not_muted_by_default(self):
        self.assertFalse(system.is_muted())
        self.assertEqual(system.mute_seconds_remaining(), 0.0)

    def test_enter_sleep_mode_mutes_for_requested_duration(self):
        system.enter_sleep_mode(30)
        self.assertTrue(system.is_muted())
        remaining = system.mute_seconds_remaining()
        # Should be very close to 30 (allow scheduling slack).
        self.assertGreater(remaining, 29)
        self.assertLessEqual(remaining, 30)

    def test_enter_sleep_mode_returns_spoken_confirmation(self):
        message = system.enter_sleep_mode(45)
        self.assertIn("45 second", message)

    def test_enter_sleep_mode_minutes_phrasing(self):
        message = system.enter_sleep_mode(120)
        self.assertIn("2 minute", message)

    def test_non_positive_duration_falls_back_to_default(self):
        system.enter_sleep_mode(0)
        remaining = system.mute_seconds_remaining()
        self.assertGreater(remaining, system.DEFAULT_MUTE_SECONDS - 1)

    def test_invalid_duration_falls_back_to_default(self):
        system.enter_sleep_mode("not a number")
        remaining = system.mute_seconds_remaining()
        self.assertGreater(remaining, system.DEFAULT_MUTE_SECONDS - 1)

    def test_mute_expires_after_duration(self):
        system.enter_sleep_mode(-999)  # invalid -> falls back to default > 0
        # Directly set an already-past mute deadline to simulate time
        # having passed, rather than actually sleeping in a test.
        system._mute_until = 0.0
        self.assertFalse(system.is_muted())
        self.assertEqual(system.mute_seconds_remaining(), 0.0)


class SleepModeRouterTests(unittest.TestCase):
    """Tests that action_router.py correctly wires the "sleep_mode"
    action type through to system.enter_sleep_mode()."""

    def setUp(self):
        system._mute_until = 0.0

    def test_router_dispatches_sleep_mode_action(self):
        result = action_router.execute_action(
            {"action": "sleep_mode", "params": {"duration_seconds": 20}}, {}
        )
        self.assertIn("20 second", result)
        self.assertTrue(system.is_muted())

    def test_router_sleep_mode_defaults_without_params(self):
        result = action_router.execute_action(
            {"action": "sleep_mode", "params": {}}, {}
        )
        self.assertIsNotNone(result)
        self.assertTrue(system.is_muted())


if __name__ == "__main__":
    unittest.main()
