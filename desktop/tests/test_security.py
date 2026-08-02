# ───────────────────────────────────────────────────────────────────
# tests/test_security.py — tests for the run_command / read_file
# security gates in core/actions/system.py
# ───────────────────────────────────────────────────────────────────
# WHY THESE TESTS EXIST
# ----------------------
# run_command and read_file are the two actions that can do real
# damage if Claude/Ollama is ever tricked (e.g. via a prompt-injected
# web search result) into asking for something dangerous. These
# tests exercise the safeguards added around them: the read-path
# denylist, the command allowlist + confirmation gate, and the
# output redaction pass. See core/actions/system.py's SECURITY
# section for the full explanation of why each one exists.
#
# HOW TO RUN
# ----------
#   cd desktop
#   python3 -m unittest discover -s tests -v
#
# (Uses only Python's built-in `unittest` — no pytest or other test
# framework needs to be installed.)
# ───────────────────────────────────────────────────────────────────

import os
import sys
import tempfile
import unittest

# Make sure `desktop/` (the parent of this `tests/` folder) is on
# sys.path, so `import core.actions.system` works no matter what
# directory this test file happens to be run from.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.actions import system  # noqa: E402  (import after sys.path fix, on purpose)


class ReadFileDenylistTests(unittest.TestCase):
    """Tests for read_file()'s path-based denylist."""

    def test_denied_path_is_rejected(self):
        # ~/.ssh/id_rsa is inside the default denied-path prefix
        # "~/.ssh/" — read_file should refuse it outright, whether or
        # not the file actually exists on this machine.
        result = system.read_file("~/.ssh/id_rsa")
        self.assertIn("Access denied", result)
        # It should also never have gotten as far as actually trying
        # to open the file — a "File not found" message would mean
        # the denylist check was skipped instead of firing.
        self.assertNotIn("File not found", result)

    def test_denied_extension_is_rejected(self):
        # A .pem file OUTSIDE any denied directory should still be
        # denied purely because of its extension.
        result = system.read_file("/tmp/some_random_cert.pem")
        self.assertIn("Access denied", result)

    def test_path_traversal_into_denied_dir_is_rejected(self):
        # "~/Desktop/../.ssh/id_rsa" doesn't literally start with the
        # denylist prefix as TEXT, but it resolves to exactly that
        # protected location — the denylist check must catch this by
        # resolving the absolute path first, not just string-prefix
        # matching the raw input.
        result = system.read_file("~/Desktop/../.ssh/id_rsa")
        self.assertIn("Access denied", result)

    def test_allowed_path_succeeds(self):
        # A plain temp file with no sensitive name/extension/location
        # should read normally, proving the denylist isn't blocking
        # everything indiscriminately.
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False
        ) as f:
            f.write("hello from a normal, non-sensitive file")
            temp_path = f.name

        try:
            result = system.read_file(temp_path)
            self.assertEqual(result, "hello from a normal, non-sensitive file")
        finally:
            os.remove(temp_path)


class RunCommandConfirmationTests(unittest.TestCase):
    """Tests for run_command()'s allowlist + confirmation gate."""

    def setUp(self):
        # Reset the module-level pending-confirmation state before
        # each test so tests can't leak state into one another (e.g.
        # a command left pending by one test accidentally getting
        # "confirmed" by an unrelated later test).
        system._pending_confirmation = {"command": None, "requested_at": 0.0}
        # Use a temp file as a side-effect marker for the
        # non-allowlisted command below, cleaned up after each test.
        self.marker_fd, self.marker_path = tempfile.mkstemp()
        os.close(self.marker_fd)
        os.remove(self.marker_path)  # start absent; command creates it

    def tearDown(self):
        if os.path.exists(self.marker_path):
            os.remove(self.marker_path)

    def test_allowlisted_command_runs_immediately(self):
        # "pwd" is in the default allowlist, so it should run right
        # away with no confirmation step and no pending state left
        # behind.
        result = system.run_command("pwd")
        self.assertNotIn("CONFIRMATION REQUIRED", result)
        self.assertIsNone(system._pending_confirmation["command"])

    def test_unconfirmed_dangerous_command_does_not_execute(self):
        # "touch" is NOT on the default allowlist, and
        # command_confirmation_required defaults to True even with no
        # config passed at all — so this must NOT actually run yet.
        command = f"touch {self.marker_path}"
        result = system.run_command(command)  # no config -> defaults apply

        self.assertIn("CONFIRMATION REQUIRED", result)
        self.assertFalse(
            os.path.exists(self.marker_path),
            "run_command executed a non-allowlisted command without "
            "confirmation — the safety gate did not hold it back.",
        )
        # The command should now be sitting in the pending slot,
        # ready for confirm_pending_command() to pick up.
        self.assertEqual(system._pending_confirmation["command"], command)

    def test_confirmed_command_executes(self):
        command = f"touch {self.marker_path}"
        pending_result = system.run_command(command)
        self.assertIn("CONFIRMATION REQUIRED", pending_result)
        self.assertFalse(os.path.exists(self.marker_path))

        # Now simulate the user saying "Computer, confirm" — the
        # router calls confirm_pending_command() with NO params.
        system.confirm_pending_command()

        self.assertTrue(
            os.path.exists(self.marker_path),
            "confirm_pending_command() should have run the "
            "previously-held command.",
        )

    def test_confirm_with_nothing_pending_is_a_no_op(self):
        result = system.confirm_pending_command()
        self.assertIn("no pending command", result.lower())

    def test_confirmation_not_required_runs_immediately(self):
        # An explicit opt-out (config says confirmation isn't
        # required) should behave like the OLD, unguarded run_command
        # — run right away, no pending state.
        config = {"security": {"command_confirmation_required": False}}
        command = f"touch {self.marker_path}"
        system.run_command(command, config)
        self.assertTrue(os.path.exists(self.marker_path))
        self.assertIsNone(system._pending_confirmation["command"])

    def test_custom_allowlist_from_config_is_honored(self):
        # A command not in the DEFAULT allowlist should still run
        # immediately if the user's config.yaml explicitly added it.
        config = {"security": {"allowed_commands": ["touch"]}}
        command = f"touch {self.marker_path}"
        result = system.run_command(command, config)
        self.assertNotIn("CONFIRMATION REQUIRED", result)
        self.assertTrue(os.path.exists(self.marker_path))


class OutputRedactionTests(unittest.TestCase):
    """Tests for redact_secrets() and its use inside run_command()."""

    def test_redact_secrets_catches_fake_api_key(self):
        fake_key = "sk-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        text = f"Your API key is {fake_key} — keep it secret."
        redacted = system.redact_secrets(text)
        self.assertNotIn(fake_key, redacted)
        self.assertIn("[REDACTED", redacted)

    def test_redact_secrets_catches_long_hex_token(self):
        fake_token = "a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718"
        redacted = system.redact_secrets(f"token={fake_token}")
        self.assertNotIn(fake_token, redacted)

    def test_redact_secrets_leaves_normal_text_alone(self):
        text = "Downloaded 3 files to /tmp, all good."
        self.assertEqual(system.redact_secrets(text), text)

    def test_run_command_output_is_redacted_end_to_end(self):
        # "echo" is on the default allowlist, so this runs
        # immediately — good, because it lets us test the FULL path
        # (allowlisted command -> subprocess -> truncate -> redact)
        # in one shot rather than just unit-testing redact_secrets()
        # in isolation.
        fake_key = "sk-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        result = system.run_command(f"echo {fake_key}")
        self.assertNotIn(fake_key, result)
        self.assertIn("[REDACTED", result)


if __name__ == "__main__":
    unittest.main()
