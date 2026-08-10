# ───────────────────────────────────────────────────────────────────
# tests/test_integrations.py, tests for actions/integrations.py
# ───────────────────────────────────────────────────────────────────
# WHY THESE TESTS EXIST
# ----------------------
# actions/integrations.py is the LARGE-tier weather/calendar/
# reminders module: real network calls to three providers
# (Open-Meteo, OpenWeatherMap, Todoist) plus a hand-rolled .ics
# parser, all gated behind config.yaml credentials that may or may
# not be present. These tests cover:
#   - missing-credential paths return a clear, actionable string
#     instead of raising (every action here is voice-facing, a
#     traceback is not something to speak out loud)
#   - the happy path for each provider, using a fake `requests`
#     module (no real network access, no real API keys needed to run
#     the suite)
#   - HTTP-error / timeout handling for each provider
#   - the .ics parser directly: line unfolding, all-day vs timed
#     events, escaped text, and the "upcoming in next N days" filter
#
# HOW TO RUN
# ----------
#   cd desktop
#   python3 -m unittest discover -s tests -v
# ───────────────────────────────────────────────────────────────────

import os
import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.actions import integrations  # noqa: E402


# ── Fakes ──────────────────────────────────────────────────────────
class _FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json_data = json_data
        self.text = text

    def json(self):
        return self._json_data


class _FakeRequests:
    """Stand-in for the `requests` module. Queues canned responses
    per call (in call order) and records every call made so tests can
    assert on the URL/params/headers actually sent."""

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
        if result is TimeoutError:
            raise self.Timeout("simulated timeout")
        return result

    def get(self, url, **kwargs):
        return self._next("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self._next("POST", url, **kwargs)


def _patch_requests(monkeypatch_target, fake):
    """integrations.py imports `requests` lazily inside each function
    (see _import_requests()). Patch it at the point of import by
    replacing core.actions.integrations._import_requests."""
    integrations._import_requests = lambda: fake


class IntegrationsTestCase(unittest.TestCase):
    def setUp(self):
        self._original_import_requests = integrations._import_requests

    def tearDown(self):
        integrations._import_requests = self._original_import_requests


# ── WEATHER ────────────────────────────────────────────────────────
class WeatherTests(IntegrationsTestCase):
    def test_no_location_and_no_default_is_an_error(self):
        result = integrations.get_weather("", {})
        self.assertIn("No location provided", result)

    def test_open_meteo_happy_path_uses_default_location(self):
        fake = _FakeRequests([
            _FakeResponse(json_data={"results": [
                {"latitude": 42.3, "longitude": -71.05, "name": "Boston", "country": "United States"}
            ]}),
            _FakeResponse(json_data={"current": {
                "temperature_2m": 54.3, "weather_code": 3,
                "wind_speed_10m": 8.7, "relative_humidity_2m": 80,
            }}),
        ])
        _patch_requests(self, fake)
        config = {"integrations": {"weather": {"default_location": "Boston"}}}

        result = integrations.get_weather("", config)

        self.assertIn("Boston, United States", result)
        self.assertIn("overcast", result)
        self.assertIn("54°F", result)
        self.assertIn("80% humidity", result)
        self.assertIn("wind 9 mph", result)
        self.assertEqual(len(fake.calls), 2)

    def test_open_meteo_location_not_found(self):
        fake = _FakeRequests([_FakeResponse(json_data={"results": []})])
        _patch_requests(self, fake)
        result = integrations.get_weather("Nowhereville", {})
        self.assertIn("Could not find location", result)

    def test_open_meteo_geocode_http_error(self):
        fake = _FakeRequests([_FakeResponse(status_code=500)])
        _patch_requests(self, fake)
        result = integrations.get_weather("Boston", {})
        self.assertIn("HTTP 500", result)

    def test_open_meteo_timeout(self):
        fake = _FakeRequests([TimeoutError])
        _patch_requests(self, fake)
        result = integrations.get_weather("Boston", {})
        self.assertIn("timed out", result)

    def test_openweathermap_requires_api_key(self):
        config = {"integrations": {"weather": {"provider": "openweathermap"}}}
        result = integrations.get_weather("Paris", config)
        self.assertIn("openweathermap_api_key", result)

    def test_openweathermap_happy_path(self):
        fake = _FakeRequests([_FakeResponse(json_data={
            "name": "Paris",
            "weather": [{"description": "light rain"}],
            "main": {"temp": 60.1, "humidity": 70},
            "wind": {"speed": 5.4},
        })])
        _patch_requests(self, fake)
        config = {"integrations": {"weather": {
            "provider": "openweathermap", "openweathermap_api_key": "abc123",
        }}}

        result = integrations.get_weather("Paris", config)

        self.assertIn("Paris", result)
        self.assertIn("light rain", result)
        self.assertIn("60°F", result)
        self.assertEqual(fake.calls[0]["params"]["appid"], "abc123")

    def test_openweathermap_bad_key(self):
        fake = _FakeRequests([_FakeResponse(status_code=401)])
        _patch_requests(self, fake)
        config = {"integrations": {"weather": {
            "provider": "openweathermap", "openweathermap_api_key": "bad",
        }}}
        result = integrations.get_weather("Paris", config)
        self.assertIn("401", result)


# ── CALENDAR (network layer) ─────────────────────────────────────
class CalendarNetworkTests(IntegrationsTestCase):
    def test_no_ics_url_is_an_error(self):
        result = integrations.get_calendar_events({})
        self.assertIn("ics_url", result)

    def test_http_error_is_reported(self):
        fake = _FakeRequests([_FakeResponse(status_code=404)])
        _patch_requests(self, fake)
        config = {"integrations": {"calendar": {"ics_url": "https://example.com/cal.ics"}}}
        result = integrations.get_calendar_events(config)
        self.assertIn("HTTP 404", result)

    def test_basic_auth_used_when_credentials_configured(self):
        fake = _FakeRequests([_FakeResponse(text="")])
        _patch_requests(self, fake)
        config = {"integrations": {"calendar": {
            "ics_url": "https://example.com/cal.ics",
            "ics_username": "alice", "ics_password": "hunter2",
        }}}
        integrations.get_calendar_events(config)
        self.assertEqual(fake.calls[0]["auth"], ("alice", "hunter2"))

    def test_no_auth_when_credentials_absent(self):
        fake = _FakeRequests([_FakeResponse(text="")])
        _patch_requests(self, fake)
        config = {"integrations": {"calendar": {"ics_url": "https://example.com/cal.ics"}}}
        integrations.get_calendar_events(config)
        self.assertIsNone(fake.calls[0]["auth"])


# ── CALENDAR (.ics parsing) ───────────────────────────────────────
_SAMPLE_ICS = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
SUMMARY:Team sync
DTSTART:20260805T140000Z
DTEND:20260805T150000Z
LOCATION:Conference Room A
END:VEVENT
BEGIN:VEVENT
SUMMARY:Company holiday
DTSTART;VALUE=DATE:20260810
DTEND;VALUE=DATE:20260811
END:VEVENT
BEGIN:VEVENT
SUMMARY:A very long event title that had to be\\n folded across
 multiple physical lines by the calendar server
DTSTART:20260806T090000Z
END:VEVENT
END:VCALENDAR
"""


class IcsParsingTests(unittest.TestCase):
    def test_parses_timed_event(self):
        events = integrations.parse_ics_events(_SAMPLE_ICS)
        timed = next(e for e in events if e["summary"] == "Team sync")
        self.assertEqual(
            timed["start"], datetime(2026, 8, 5, 14, 0, 0, tzinfo=timezone.utc)
        )
        self.assertEqual(timed["location"], "Conference Room A")
        self.assertFalse(timed["all_day"])

    def test_parses_all_day_event(self):
        events = integrations.parse_ics_events(_SAMPLE_ICS)
        holiday = next(e for e in events if e["summary"] == "Company holiday")
        self.assertEqual(holiday["start"], datetime(2026, 8, 10))
        self.assertTrue(holiday["all_day"])

    def test_unfolds_and_unescapes_multiline_summary(self):
        events = integrations.parse_ics_events(_SAMPLE_ICS)
        folded = next(e for e in events if "very long event" in e["summary"])
        # The escaped "\n" and the line-fold both collapse to spaces.
        self.assertNotIn("\\n", folded["summary"])
        self.assertIn("folded acrossmultiple physical lines", folded["summary"])

    def test_empty_text_returns_no_events(self):
        self.assertEqual(integrations.parse_ics_events(""), [])

    def test_malformed_datetime_does_not_raise(self):
        text = (
            "BEGIN:VEVENT\nSUMMARY:Bad date\nDTSTART:not-a-date\n"
            "END:VEVENT\n"
        )
        events = integrations.parse_ics_events(text)
        self.assertEqual(events[0]["start"], None)


class FilterUpcomingEventsTests(unittest.TestCase):
    def test_filters_to_window_and_sorts(self):
        now = datetime(2026, 8, 1, 12, 0, 0)
        events = [
            {"summary": "too late", "start": datetime(2026, 8, 20), "all_day": True},
            {"summary": "second", "start": datetime(2026, 8, 3, 9, 0), "all_day": False},
            {"summary": "first", "start": datetime(2026, 8, 2, 9, 0), "all_day": False},
            {"summary": "in the past", "start": datetime(2026, 7, 1), "all_day": True},
        ]
        result = integrations._filter_upcoming_events(events, days=7, now=now)
        self.assertEqual([e["summary"] for e in result], ["first", "second"])

    def test_no_events_message(self):
        result = integrations._format_calendar_events([], 7)
        self.assertIn("No events found", result)
        self.assertIn("7", result)


# ── REMINDERS ──────────────────────────────────────────────────────
class ReminderTests(IntegrationsTestCase):
    def test_add_reminder_requires_token(self):
        result = integrations.add_reminder("buy milk", {})
        self.assertIn("todoist_api_token", result)

    def test_add_reminder_requires_text(self):
        config = {"integrations": {"reminders": {"todoist_api_token": "tok"}}}
        result = integrations.add_reminder("", config)
        self.assertIn("No reminder text", result)

    def test_add_reminder_happy_path(self):
        fake = _FakeRequests([_FakeResponse(json_data={"content": "buy milk", "id": "1"})])
        _patch_requests(self, fake)
        config = {"integrations": {"reminders": {"todoist_api_token": "tok"}}}

        result = integrations.add_reminder("buy milk", config)

        self.assertIn("Reminder added: buy milk", result)
        self.assertEqual(fake.calls[0]["headers"]["Authorization"], "Bearer tok")
        self.assertEqual(fake.calls[0]["json"], {"content": "buy milk"})

    def test_add_reminder_bad_token(self):
        fake = _FakeRequests([_FakeResponse(status_code=401)])
        _patch_requests(self, fake)
        config = {"integrations": {"reminders": {"todoist_api_token": "bad"}}}
        result = integrations.add_reminder("buy milk", config)
        self.assertIn("401", result)

    def test_list_reminders_requires_token(self):
        result = integrations.list_reminders({})
        self.assertIn("todoist_api_token", result)

    def test_list_reminders_empty(self):
        fake = _FakeRequests([_FakeResponse(json_data=[])])
        _patch_requests(self, fake)
        config = {"integrations": {"reminders": {"todoist_api_token": "tok"}}}
        result = integrations.list_reminders(config)
        self.assertIn("No open reminders", result)

    def test_list_reminders_formats_tasks(self):
        fake = _FakeRequests([_FakeResponse(json_data=[
            {"id": "1", "content": "buy milk"},
            {"id": "2", "content": "walk the dog"},
        ])])
        _patch_requests(self, fake)
        config = {"integrations": {"reminders": {"todoist_api_token": "tok"}}}
        result = integrations.list_reminders(config)
        self.assertIn("buy milk", result)
        self.assertIn("walk the dog", result)

    def test_complete_reminder_requires_query(self):
        config = {"integrations": {"reminders": {"todoist_api_token": "tok"}}}
        result = integrations.complete_reminder("", config)
        self.assertIn("No reminder text provided to match", result)

    def test_complete_reminder_no_match(self):
        fake = _FakeRequests([_FakeResponse(json_data=[{"id": "1", "content": "buy milk"}])])
        _patch_requests(self, fake)
        config = {"integrations": {"reminders": {"todoist_api_token": "tok"}}}
        result = integrations.complete_reminder("walk the dog", config)
        self.assertIn("No open reminder matching", result)

    def test_complete_reminder_matches_and_closes(self):
        fake = _FakeRequests([
            _FakeResponse(json_data=[
                {"id": "1", "content": "buy milk"},
                {"id": "2", "content": "walk the dog"},
            ]),
            _FakeResponse(status_code=204),
        ])
        _patch_requests(self, fake)
        config = {"integrations": {"reminders": {"todoist_api_token": "tok"}}}

        result = integrations.complete_reminder("milk", config)

        self.assertIn("Completed reminder: buy milk", result)
        self.assertEqual(fake.calls[1]["url"], integrations._TODOIST_TASKS_URL + "/1/close")

    def test_complete_reminder_is_case_insensitive(self):
        fake = _FakeRequests([
            _FakeResponse(json_data=[{"id": "1", "content": "Buy Milk"}]),
            _FakeResponse(status_code=204),
        ])
        _patch_requests(self, fake)
        config = {"integrations": {"reminders": {"todoist_api_token": "tok"}}}
        result = integrations.complete_reminder("milk", config)
        self.assertIn("Completed reminder", result)


if __name__ == "__main__":
    unittest.main()
