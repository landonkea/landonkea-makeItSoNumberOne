# ───────────────────────────────────────────────────────────────────
# tests/test_ollama.py, tests for core/ai.py's Ollama/local-LLM
# fallback: model listing, pull-if-missing, and offline degradation.
# ───────────────────────────────────────────────────────────────────
# WHY THESE TESTS EXIST
# ----------------------
# core/ai.py's offline path talks to a locally-running Ollama server
# over HTTP. These tests cover the model-management layer added on
# top of the original "just call /api/generate" fallback:
#   - list_ollama_models(), GET /api/tags happy path + failure paths
#   - is_model_available(), exact match and the ":latest" tag
#     equivalence Ollama itself applies
#   - pull_model() / ensure_model_available(), triggering
#     POST /api/pull when a configured model isn't present yet
#   - process_with_ollama()'s end-to-end degradation when Ollama
#     isn't running at all (connection refused / unreachable), and
#     its ollama_auto_pull config-driven pull-before-generate flow
#
# Follows the same fake-`requests` mocking pattern as
# tests/test_integrations.py: core/ai.py imports `requests` lazily
# via _import_requests(), which tests monkeypatch to inject a fake
# module instead of touching the real network.
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


# ── Fakes (same shape as tests/test_integrations.py's) ────────────
class _FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json_data = json_data

    def json(self):
        return self._json_data


class _FakeRequests:
    """Stand-in for the `requests` module. Queues canned responses per
    call (in call order) and records every call made so tests can
    assert on the URL/JSON actually sent. A queued value of
    ConnectionError simulates Ollama not running at all."""

    class ConnectionError(Exception):
        pass

    class Timeout(Exception):
        pass

    def __init__(self, responses=None):
        self._responses = list(responses or [])
        self.calls = []

    def _next(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        if not self._responses:
            raise AssertionError("FakeRequests ran out of queued responses")
        result = self._responses.pop(0)
        if result is ConnectionRefusedError:
            raise self.ConnectionError("simulated connection refused")
        if result is TimeoutError:
            raise self.Timeout("simulated timeout")
        return result

    def get(self, url, **kwargs):
        return self._next("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self._next("POST", url, **kwargs)


class OllamaTestCase(unittest.TestCase):
    """Patches both core.ai._import_requests (for the `requests`-based
    calls) and core.ai._is_ollama_running (for the urllib-based
    reachability check used by process_with_ollama), and restores
    both afterward."""

    def setUp(self):
        self._orig_import_requests = ai._import_requests
        self._orig_is_running = ai._is_ollama_running

    def tearDown(self):
        ai._import_requests = self._orig_import_requests
        ai._is_ollama_running = self._orig_is_running

    def _patch_requests(self, fake):
        ai._import_requests = lambda: fake

    def _patch_ollama_running(self, running):
        ai._is_ollama_running = lambda *a, **kw: running


# ── list_ollama_models() ───────────────────────────────────────────
class ListOllamaModelsTests(OllamaTestCase):
    def test_happy_path_returns_model_names(self):
        fake = _FakeRequests([_FakeResponse(json_data={"models": [
            {"name": "llama3.2:latest", "size": 123},
            {"name": "mistral:latest", "size": 456},
        ]})])
        self._patch_requests(fake)

        result = ai.list_ollama_models()

        self.assertEqual(result, ["llama3.2:latest", "mistral:latest"])
        self.assertEqual(fake.calls[0]["url"], "http://localhost:11434/api/tags")

    def test_empty_model_list(self):
        fake = _FakeRequests([_FakeResponse(json_data={"models": []})])
        self._patch_requests(fake)
        self.assertEqual(ai.list_ollama_models(), [])

    def test_entries_without_a_name_are_skipped(self):
        fake = _FakeRequests([_FakeResponse(json_data={"models": [
            {"size": 123},  # malformed / no "name" key
            {"name": "llama3.2:latest"},
        ]})])
        self._patch_requests(fake)
        self.assertEqual(ai.list_ollama_models(), ["llama3.2:latest"])

    def test_http_error_returns_empty_list_not_raise(self):
        fake = _FakeRequests([_FakeResponse(status_code=500)])
        self._patch_requests(fake)
        self.assertEqual(ai.list_ollama_models(), [])

    def test_connection_refused_returns_empty_list_not_raise(self):
        fake = _FakeRequests([ConnectionRefusedError])
        self._patch_requests(fake)
        self.assertEqual(ai.list_ollama_models(), [])


# ── is_model_available() ───────────────────────────────────────────
class IsModelAvailableTests(OllamaTestCase):
    def test_exact_match(self):
        fake = _FakeRequests([_FakeResponse(json_data={"models": [
            {"name": "llama3.2:1b"},
        ]})])
        self._patch_requests(fake)
        self.assertTrue(ai.is_model_available("llama3.2:1b"))

    def test_bare_name_matches_latest_tag(self):
        fake = _FakeRequests([_FakeResponse(json_data={"models": [
            {"name": "llama3.2:latest"},
        ]})])
        self._patch_requests(fake)
        self.assertTrue(ai.is_model_available("llama3.2"))

    def test_latest_tag_matches_bare_name(self):
        fake = _FakeRequests([_FakeResponse(json_data={"models": [
            {"name": "llama3.2"},
        ]})])
        self._patch_requests(fake)
        self.assertTrue(ai.is_model_available("llama3.2:latest"))

    def test_not_available(self):
        fake = _FakeRequests([_FakeResponse(json_data={"models": [
            {"name": "mistral:latest"},
        ]})])
        self._patch_requests(fake)
        self.assertFalse(ai.is_model_available("llama3.2"))


# ── pull_model() / ensure_model_available() ────────────────────────
class PullModelTests(OllamaTestCase):
    def test_pull_success(self):
        fake = _FakeRequests([_FakeResponse(json_data={"status": "success"})])
        self._patch_requests(fake)

        result = ai.pull_model("llama3.2")

        self.assertTrue(result)
        self.assertEqual(fake.calls[0]["url"], "http://localhost:11434/api/pull")
        self.assertEqual(fake.calls[0]["json"], {"name": "llama3.2", "stream": False})

    def test_pull_reports_http_error(self):
        fake = _FakeRequests([_FakeResponse(status_code=500)])
        self._patch_requests(fake)
        self.assertFalse(ai.pull_model("llama3.2"))

    def test_pull_reports_status_error(self):
        fake = _FakeRequests([_FakeResponse(json_data={
            "status": "error: model not found"
        })])
        self._patch_requests(fake)
        self.assertFalse(ai.pull_model("nonexistent-model"))

    def test_pull_handles_network_failure(self):
        fake = _FakeRequests([ConnectionRefusedError])
        self._patch_requests(fake)
        self.assertFalse(ai.pull_model("llama3.2"))


class EnsureModelAvailableTests(OllamaTestCase):
    def test_already_available_skips_pull(self):
        fake = _FakeRequests([_FakeResponse(json_data={"models": [
            {"name": "llama3.2:latest"},
        ]})])
        self._patch_requests(fake)

        result = ai.ensure_model_available("llama3.2")

        self.assertTrue(result)
        # Only the /api/tags check should have happened, no pull.
        self.assertEqual(len(fake.calls), 1)
        self.assertEqual(fake.calls[0]["url"], "http://localhost:11434/api/tags")

    def test_missing_model_triggers_pull(self):
        fake = _FakeRequests([
            _FakeResponse(json_data={"models": []}),        # /api/tags
            _FakeResponse(json_data={"status": "success"}),  # /api/pull
        ])
        self._patch_requests(fake)

        result = ai.ensure_model_available("llama3.2")

        self.assertTrue(result)
        self.assertEqual(len(fake.calls), 2)
        self.assertEqual(fake.calls[1]["url"], "http://localhost:11434/api/pull")

    def test_missing_model_pull_failure_propagates(self):
        fake = _FakeRequests([
            _FakeResponse(json_data={"models": []}),
            _FakeResponse(status_code=500),
        ])
        self._patch_requests(fake)
        self.assertFalse(ai.ensure_model_available("llama3.2"))


# ── get_model_capabilities() ────────────────────────────────────────
class GetModelCapabilitiesTests(unittest.TestCase):
    def test_known_model_with_tag(self):
        info = ai.get_model_capabilities("llama3.2:1b")
        self.assertEqual(info["size_class"], "small")
        self.assertEqual(info["context_window"], 128000)

    def test_known_model_base_name_fallback(self):
        # "llama3.1:70b" isn't an exact table entry, but "llama3.1" is.
        info = ai.get_model_capabilities("llama3.1:70b")
        self.assertEqual(info["size_class"], "large")

    def test_unknown_model_gets_conservative_default(self):
        info = ai.get_model_capabilities("some-totally-custom-model")
        self.assertEqual(info, ai._DEFAULT_MODEL_CAPABILITIES)

    def test_config_override_wins(self):
        info = ai.get_model_capabilities(
            "llama3.2", config={"ollama_context_window": 4096}
        )
        self.assertEqual(info["context_window"], 4096)

    def test_invalid_config_override_is_ignored(self):
        info = ai.get_model_capabilities(
            "llama3.2", config={"ollama_context_window": "not a number"}
        )
        self.assertEqual(info["context_window"], 128000)


# ── process_with_ollama() end-to-end degradation ───────────────────
class ProcessWithOllamaTests(OllamaTestCase):
    def test_ollama_not_running_returns_none(self):
        self._patch_ollama_running(False)
        fake = _FakeRequests([])  # no HTTP calls should happen at all
        self._patch_requests(fake)

        result = ai.process_with_ollama("hello", {})

        self.assertIsNone(result)
        self.assertEqual(fake.calls, [])

    def test_configured_model_missing_no_auto_pull_still_attempts_generate(self):
        # Default behavior (ollama_auto_pull unset/false): warn, but
        # don't block the request on a multi-minute pull, try the
        # generate call anyway.
        self._patch_ollama_running(True)
        fake = _FakeRequests([
            _FakeResponse(json_data={"models": []}),  # is_model_available check
            _FakeResponse(json_data={  # /api/generate
                "response": '{"response": "Hi there.", "actions": []}'
            }),
        ])
        self._patch_requests(fake)

        result = ai.process_with_ollama("hello", {"ollama_model": "llama3.2"})

        self.assertEqual(result["spoken_text"], "Hi there.")
        self.assertEqual(fake.calls[-1]["url"], "http://localhost:11434/api/generate")

    def test_auto_pull_pulls_missing_model_before_generating(self):
        self._patch_ollama_running(True)
        fake = _FakeRequests([
            _FakeResponse(json_data={"models": []}),          # is_model_available
            _FakeResponse(json_data={"status": "success"}),   # pull_model
            _FakeResponse(json_data={                          # /api/generate
                "response": '{"response": "Ready.", "actions": []}'
            }),
        ])
        self._patch_requests(fake)

        result = ai.process_with_ollama(
            "hello", {"ollama_model": "llama3.2", "ollama_auto_pull": True}
        )

        self.assertEqual(result["spoken_text"], "Ready.")
        urls = [c["url"] for c in fake.calls]
        self.assertEqual(urls, [
            "http://localhost:11434/api/tags",
            "http://localhost:11434/api/pull",
            "http://localhost:11434/api/generate",
        ])

    def test_auto_pull_failure_gives_up_without_generating(self):
        self._patch_ollama_running(True)
        fake = _FakeRequests([
            _FakeResponse(json_data={"models": []}),   # is_model_available
            _FakeResponse(status_code=500),             # pull_model fails
        ])
        self._patch_requests(fake)

        result = ai.process_with_ollama(
            "hello", {"ollama_model": "llama3.2", "ollama_auto_pull": True}
        )

        self.assertIsNone(result)
        # No /api/generate call should have been attempted.
        urls = [c["url"] for c in fake.calls]
        self.assertNotIn("http://localhost:11434/api/generate", urls)

    def test_generate_http_error_returns_none(self):
        self._patch_ollama_running(True)
        fake = _FakeRequests([
            _FakeResponse(json_data={"models": [{"name": "llama3.2:latest"}]}),
            _FakeResponse(status_code=500),
        ])
        self._patch_requests(fake)

        result = ai.process_with_ollama("hello", {"ollama_model": "llama3.2"})
        self.assertIsNone(result)

    def test_generate_empty_response_returns_none(self):
        self._patch_ollama_running(True)
        fake = _FakeRequests([
            _FakeResponse(json_data={"models": [{"name": "llama3.2:latest"}]}),
            _FakeResponse(json_data={"response": "  "}),
        ])
        self._patch_requests(fake)

        result = ai.process_with_ollama("hello", {"ollama_model": "llama3.2"})
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
