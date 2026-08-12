# ───────────────────────────────────────────────────────────────────
# tests/test_claude_api.py, tests for core/ai.py's online (Claude)
# path: request shaping, response extraction, and both the plain and
# streaming HTTP calls.
# ───────────────────────────────────────────────────────────────────
# WHY THESE TESTS EXIST
# ----------------------
# core/ai.py's Ollama fallback and _parse_response() JSON parsing
# already had test coverage (test_ollama.py, test_ai_parsing.py), but
# the primary AI call, process_with_claude() and its streaming
# sibling process_with_claude_streaming(), talk directly to
# Anthropic's Messages API and had none. These tests cover the
# request-shaping helpers (_build_claude_messages,
# _extract_claude_text) directly, then process_with_claude()'s
# missing-key/success/HTTP-error/network-exception paths, then
# process_with_claude_streaming()'s SSE event handling, including a
# connection that drops mid-stream after some sentences already went
# out through on_sentence().
#
# Follows the same fake-`requests` mocking pattern as
# tests/test_ollama.py and tests/test_integrations.py: core/ai.py
# imports `requests` lazily via _import_requests(), which tests
# monkeypatch to inject a fake module instead of touching the real
# network.
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

from core import ai  # noqa: E402


# ── _build_claude_messages() ────────────────────────────────────────
class BuildClaudeMessagesTests(unittest.TestCase):
    def test_no_history_is_just_the_new_user_message(self):
        messages = ai._build_claude_messages("Set a course for Risa", None)
        self.assertEqual(messages, [{"role": "user", "content": "Set a course for Risa"}])

    def test_history_is_carried_forward_in_order(self):
        history = [
            {"role": "user", "content": "Computer, hello"},
            {"role": "assistant", "content": "Hello, Captain."},
        ]
        messages = ai._build_claude_messages("What's next?", history)
        self.assertEqual(len(messages), 3)
        self.assertEqual(messages[0], {"role": "user", "content": "Computer, hello"})
        self.assertEqual(messages[1], {"role": "assistant", "content": "Hello, Captain."})
        self.assertEqual(messages[2], {"role": "user", "content": "What's next?"})

    def test_extra_keys_on_history_entries_are_dropped(self):
        history = [{"role": "user", "content": "hi", "timestamp": 12345}]
        messages = ai._build_claude_messages("again", history)
        self.assertEqual(messages[0], {"role": "user", "content": "hi"})


# ── _extract_claude_text() ──────────────────────────────────────────
class ExtractClaudeTextTests(unittest.TestCase):
    def test_returns_the_first_text_block(self):
        response_json = {"content": [{"type": "text", "text": "Aye, Captain."}]}
        self.assertEqual(ai._extract_claude_text(response_json), "Aye, Captain.")

    def test_skips_non_text_blocks_to_find_the_text_one(self):
        response_json = {"content": [
            {"type": "tool_use", "id": "x"},
            {"type": "text", "text": "Engaging."},
        ]}
        self.assertEqual(ai._extract_claude_text(response_json), "Engaging.")

    def test_no_content_key_returns_empty_string(self):
        self.assertEqual(ai._extract_claude_text({}), "")

    def test_no_text_block_returns_empty_string(self):
        response_json = {"content": [{"type": "tool_use", "id": "x"}]}
        self.assertEqual(ai._extract_claude_text(response_json), "")


# ── shared fakes for the HTTP-calling tests ─────────────────────────
class _FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json_data = json_data

    def json(self):
        return self._json_data


class _FakeRequests:
    """Stand-in for the `requests` module, same shape as the fakes in
    test_ollama.py/test_integrations.py. Queues one canned response
    (or an exception class to raise) and records the call made."""

    def __init__(self, response=None, raises=None):
        self._response = response
        self._raises = raises
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append({"url": url, **kwargs})
        if self._raises:
            raise self._raises("simulated network failure")
        return self._response


class ClaudeApiTestCase(unittest.TestCase):
    def setUp(self):
        self._orig_import_requests = ai._import_requests

    def tearDown(self):
        ai._import_requests = self._orig_import_requests

    def _patch_requests(self, fake):
        ai._import_requests = lambda: fake


# ── process_with_claude() ───────────────────────────────────────────
class ProcessWithClaudeTests(ClaudeApiTestCase):
    def test_missing_api_key_returns_none_without_calling_out(self):
        fake = _FakeRequests()
        self._patch_requests(fake)

        result = ai.process_with_claude("hello", {})

        self.assertIsNone(result)
        self.assertEqual(fake.calls, [])

    def test_happy_path_returns_parsed_response(self):
        body = {"content": [{
            "type": "text",
            "text": '{"response": "Course laid in.", "actions": []}',
        }]}
        fake = _FakeRequests(response=_FakeResponse(json_data=body))
        self._patch_requests(fake)

        result = ai.process_with_claude(
            "set a course", {"anthropic_api_key": "sk-ant-fake"}
        )

        self.assertEqual(result["spoken_text"], "Course laid in.")
        self.assertEqual(result["actions"], [])

    def test_sends_the_api_key_and_user_message_to_the_right_endpoint(self):
        body = {"content": [{"type": "text", "text": '{"response": "ok"}'}]}
        fake = _FakeRequests(response=_FakeResponse(json_data=body))
        self._patch_requests(fake)

        ai.process_with_claude("engage", {"anthropic_api_key": "sk-ant-fake"})

        call = fake.calls[0]
        self.assertEqual(call["url"], "https://api.anthropic.com/v1/messages")
        self.assertEqual(call["headers"]["x-api-key"], "sk-ant-fake")
        self.assertEqual(call["json"]["messages"][-1], {"role": "user", "content": "engage"})

    def test_non_200_status_returns_none(self):
        fake = _FakeRequests(response=_FakeResponse(status_code=500))
        self._patch_requests(fake)

        result = ai.process_with_claude("hello", {"anthropic_api_key": "sk-ant-fake"})

        self.assertIsNone(result)

    def test_empty_reply_text_returns_none(self):
        body = {"content": [{"type": "text", "text": ""}]}
        fake = _FakeRequests(response=_FakeResponse(json_data=body))
        self._patch_requests(fake)

        result = ai.process_with_claude("hello", {"anthropic_api_key": "sk-ant-fake"})

        self.assertIsNone(result)

    def test_network_exception_is_caught_and_returns_none(self):
        fake = _FakeRequests(raises=ConnectionError)
        self._patch_requests(fake)

        result = ai.process_with_claude("hello", {"anthropic_api_key": "sk-ant-fake"})

        self.assertIsNone(result)


# ── process_with_claude_streaming() ─────────────────────────────────
class _FakeStreamResponse:
    """Stand-in for a `requests` streaming response: status_code plus
    an SSE-shaped iter_lines() generator, and a close() the code under
    test is expected to always call."""

    def __init__(self, status_code=200, lines=None, raise_during_iteration=None):
        self.status_code = status_code
        self._lines = lines or []
        self._raise_during_iteration = raise_during_iteration
        self.closed = False

    def iter_lines(self, decode_unicode=True):
        for line in self._lines:
            yield line
        if self._raise_during_iteration:
            raise self._raise_during_iteration("dropped mid-stream")

    def close(self):
        self.closed = True


def _sse_text_delta(text):
    return 'data: {"type": "content_block_delta", "delta": {"type": "text_delta", "text": %s}}' % (
        __import__("json").dumps(text)
    )


class ProcessWithClaudeStreamingTests(ClaudeApiTestCase):
    def test_no_on_sentence_callback_falls_back_to_non_streaming(self):
        body = {"content": [{"type": "text", "text": '{"response": "ok"}'}]}
        fake = _FakeRequests(response=_FakeResponse(json_data=body))
        self._patch_requests(fake)

        result = ai.process_with_claude_streaming(
            "hello", {"anthropic_api_key": "sk-ant-fake"}, on_sentence=None
        )

        self.assertEqual(result["spoken_text"], "ok")
        # Went through the non-streaming POST, not a `stream=True` one.
        self.assertNotIn("stream", fake.calls[0].get("json", {}))

    def test_missing_api_key_returns_none(self):
        fake = _FakeRequests()
        self._patch_requests(fake)

        result = ai.process_with_claude_streaming(
            "hello", {}, on_sentence=lambda s: None
        )

        self.assertIsNone(result)
        self.assertEqual(fake.calls, [])

    def test_streams_sentences_as_they_complete_and_returns_full_result(self):
        lines = [
            _sse_text_delta('{"response": "Engaging'),
            _sse_text_delta(" warp drive."),
            _sse_text_delta(' Course is set.", "actions": []}'),
        ]
        response = _FakeStreamResponse(status_code=200, lines=lines)
        fake = _FakeRequests(response=response)
        self._patch_requests(fake)

        sentences = []
        result = ai.process_with_claude_streaming(
            "engage", {"anthropic_api_key": "sk-ant-fake"},
            on_sentence=lambda s: sentences.append(s)
        )

        self.assertEqual(sentences, ["Engaging warp drive.", "Course is set."])
        self.assertEqual(result["spoken_text"], "Engaging warp drive. Course is set.")
        self.assertEqual(result["actions"], [])
        self.assertTrue(result["streamed"])
        self.assertTrue(response.closed)
        self.assertTrue(fake.calls[0]["json"]["stream"])
        self.assertTrue(fake.calls[0]["stream"])

    def test_non_200_status_returns_none_and_closes_response(self):
        response = _FakeStreamResponse(status_code=500)
        fake = _FakeRequests(response=response)
        self._patch_requests(fake)

        result = ai.process_with_claude_streaming(
            "hello", {"anthropic_api_key": "sk-ant-fake"},
            on_sentence=lambda s: None
        )

        self.assertIsNone(result)
        self.assertTrue(response.closed)

    def test_connection_drop_before_any_text_returns_none(self):
        response = _FakeStreamResponse(
            status_code=200, lines=[], raise_during_iteration=ConnectionError
        )
        fake = _FakeRequests(response=response)
        self._patch_requests(fake)

        result = ai.process_with_claude_streaming(
            "hello", {"anthropic_api_key": "sk-ant-fake"},
            on_sentence=lambda s: None
        )

        self.assertIsNone(result)

    def test_connection_drop_after_partial_text_returns_best_effort_result(self):
        lines = [_sse_text_delta('{"response": "Partial reply before drop.')]
        response = _FakeStreamResponse(
            status_code=200, lines=lines, raise_during_iteration=ConnectionError
        )
        fake = _FakeRequests(response=response)
        self._patch_requests(fake)

        sentences = []
        result = ai.process_with_claude_streaming(
            "hello", {"anthropic_api_key": "sk-ant-fake"},
            on_sentence=lambda s: sentences.append(s)
        )

        # The connection dropped mid-JSON (no closing quote/brace), so
        # _parse_response() falls back to treating the raw buffered
        # text as the spoken reply, best-effort is still non-None.
        self.assertIsNotNone(result)
        self.assertTrue(result["streamed"])

    def test_non_text_delta_events_are_ignored(self):
        lines = [
            'data: {"type": "message_start"}',
            _sse_text_delta('{"response": "ok"}'),
            'data: {"type": "content_block_stop"}',
        ]
        response = _FakeStreamResponse(status_code=200, lines=lines)
        fake = _FakeRequests(response=response)
        self._patch_requests(fake)

        result = ai.process_with_claude_streaming(
            "hello", {"anthropic_api_key": "sk-ant-fake"},
            on_sentence=lambda s: None
        )

        self.assertEqual(result["spoken_text"], "ok")

    def test_malformed_json_line_is_skipped_without_raising(self):
        lines = [
            "data: not valid json",
            _sse_text_delta('{"response": "still ok"}'),
        ]
        response = _FakeStreamResponse(status_code=200, lines=lines)
        fake = _FakeRequests(response=response)
        self._patch_requests(fake)

        result = ai.process_with_claude_streaming(
            "hello", {"anthropic_api_key": "sk-ant-fake"},
            on_sentence=lambda s: None
        )

        self.assertEqual(result["spoken_text"], "still ok")

    def test_non_data_lines_are_skipped(self):
        lines = [
            "",
            ": comment",
            _sse_text_delta('{"response": "fine"}'),
        ]
        response = _FakeStreamResponse(status_code=200, lines=lines)
        fake = _FakeRequests(response=response)
        self._patch_requests(fake)

        result = ai.process_with_claude_streaming(
            "hello", {"anthropic_api_key": "sk-ant-fake"},
            on_sentence=lambda s: None
        )

        self.assertEqual(result["spoken_text"], "fine")


if __name__ == "__main__":
    unittest.main()
