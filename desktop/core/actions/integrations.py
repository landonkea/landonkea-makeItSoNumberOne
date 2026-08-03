# ───────────────────────────────────────────────────────────────────
# actions/integrations.py — real weather, calendar & reminders
# ───────────────────────────────────────────────────────────────────
# This is the LARGE-tier follow-up to the "add a weather/calendar/
# reminders action module" idea that earlier passes flagged as
# MEDIUM-but-deferred because it needed real API keys and credential
# handling. This module does the real thing:
#
#   - WEATHER:   two providers — Open-Meteo (free, no API key, the
#                default) and OpenWeatherMap (needs an API key, for
#                users who already have one / want its data).
#   - CALENDAR:  any standard .ics feed URL (Google/iCloud/Outlook/
#                Nextcloud all publish these for "secret address"
#                calendar sharing), with optional HTTP basic auth for
#                private feeds. No third-party SDK — a small RFC 5545
#                parser lives right here (see parse_ics_events below)
#                so we don't add a dependency for a handful of fields.
#   - REMINDERS: Todoist's REST API (add / list / complete a task),
#                since it's a real hosted to-do service with simple
#                API-token auth (no OAuth dance needed for a personal
#                assistant use case).
#
# CREDENTIAL HANDLING
# --------------------
# All of this reads from a new `integrations:` section of
# config.yaml (see config.example.yaml). Nothing here ever raises on
# a missing credential — every function checks what it needs up
# front and returns a clear, actionable error string (e.g. "Set
# integrations.reminders.todoist_api_token in config.yaml") instead
# of crashing or leaking a stack trace back through the assistant.
#
# WHY DESKTOP-ONLY
# -----------------
# Same reasoning as sleep_mode in core/ai.py: new action types are
# introduced via the JSON-format addendum that ONLY the desktop
# client's system prompt gets (see ai.py's _JSON_FORMAT_ADDENDUM).
# Android/iOS parse the shared RESPONSE:/ACTIONS: text format and
# have no equivalent addendum mechanism, so extending them to know
# about get_weather/get_calendar_events/etc. would mean hand-updating
# two more parsers (Kotlin + Swift) and their system prompts in
# lockstep — a separate, mobile-scoped pass, not part of this one.
# ───────────────────────────────────────────────────────────────────

from datetime import datetime, timedelta, timezone

# ── Provider endpoints ────────────────────────────────────────────
_OPEN_METEO_GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
_OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_OPENWEATHERMAP_URL = "https://api.openweathermap.org/data/2.5/weather"
_TODOIST_TASKS_URL = "https://api.todoist.com/rest/v2/tasks"

# WMO weather codes used by Open-Meteo's "weather_code" field, mapped
# to a short human-readable description. See:
# https://open-meteo.com/en/docs (WMO Weather interpretation codes).
WMO_WEATHER_CODES = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "depositing rime fog",
    51: "light drizzle",
    53: "moderate drizzle",
    55: "dense drizzle",
    56: "light freezing drizzle",
    57: "dense freezing drizzle",
    61: "slight rain",
    63: "moderate rain",
    65: "heavy rain",
    66: "light freezing rain",
    67: "heavy freezing rain",
    71: "slight snow fall",
    73: "moderate snow fall",
    75: "heavy snow fall",
    77: "snow grains",
    80: "slight rain showers",
    81: "moderate rain showers",
    82: "violent rain showers",
    85: "slight snow showers",
    86: "heavy snow showers",
    95: "thunderstorm",
    96: "thunderstorm with slight hail",
    99: "thunderstorm with heavy hail",
}


# ── Shared config helpers ──────────────────────────────────────────
def _get_integrations_config(config):
    """Pull the `integrations:` section out of the app config,
    defaulting to {} at every level so callers can safely chain
    .get() calls even when config.yaml has no integrations at all."""
    return (config or {}).get("integrations", {}) or {}


def _import_requests():
    """Import `requests` lazily so a missing install produces a
    friendly error message instead of crashing the app at startup —
    same reasoning as web_actions.search_web()."""
    import requests
    return requests


# ── WEATHER ─────────────────────────────────────────────────────
def get_weather(location, config):
    """
    Get current weather conditions for a location.

    PARAMETERS
    ----------
    location : str
        City/place name (e.g. "Boston" or "Paris, France"). Falls
        back to integrations.weather.default_location if empty.
    config : dict
        App configuration, read for integrations.weather.*.

    RETURNS
    -------
    str
        A one-line human-readable weather summary, or an error
        message explaining what's missing/wrong.
    """
    weather_cfg = _get_integrations_config(config).get("weather", {}) or {}
    location = (location or weather_cfg.get("default_location", "")).strip()
    if not location:
        return (
            "No location provided, and no integrations.weather."
            "default_location is set in config.yaml"
        )

    try:
        requests = _import_requests()
    except ImportError:
        return "`requests` library required. Run: pip install requests"

    provider = weather_cfg.get("provider", "open-meteo")
    try:
        if provider == "openweathermap":
            api_key = weather_cfg.get("openweathermap_api_key", "")
            if not api_key:
                return (
                    "Weather provider is 'openweathermap' but "
                    "integrations.weather.openweathermap_api_key is "
                    "not set in config.yaml"
                )
            return _get_weather_openweathermap(requests, location, api_key)
        return _get_weather_open_meteo(requests, location)
    except requests.Timeout:
        return "Weather request timed out"
    except Exception as e:
        return f"Weather error: {e}"


def _get_weather_open_meteo(requests, location):
    """Geocode `location` then fetch current conditions, both via
    Open-Meteo's free, no-API-key-required APIs."""
    geo_resp = requests.get(
        _OPEN_METEO_GEOCODE_URL,
        params={"name": location, "count": 1},
        timeout=10,
    )
    if geo_resp.status_code != 200:
        return f"Weather lookup failed (HTTP {geo_resp.status_code})"

    results = (geo_resp.json() or {}).get("results") or []
    if not results:
        return f"Could not find location: {location}"

    place = results[0]
    forecast_resp = requests.get(
        _OPEN_METEO_FORECAST_URL,
        params={
            "latitude": place["latitude"],
            "longitude": place["longitude"],
            "current": (
                "temperature_2m,weather_code,wind_speed_10m,"
                "relative_humidity_2m"
            ),
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
        },
        timeout=10,
    )
    if forecast_resp.status_code != 200:
        return f"Weather request failed (HTTP {forecast_resp.status_code})"

    current = (forecast_resp.json() or {}).get("current", {}) or {}
    name = place.get("name", location)
    country = place.get("country", "")
    return _format_weather_summary(
        place_label=f"{name}, {country}" if country else name,
        condition=WMO_WEATHER_CODES.get(current.get("weather_code"), "unknown conditions"),
        temp_f=current.get("temperature_2m"),
        humidity_pct=current.get("relative_humidity_2m"),
        wind_mph=current.get("wind_speed_10m"),
    )


def _get_weather_openweathermap(requests, location, api_key):
    """Fetch current conditions from OpenWeatherMap's free tier."""
    resp = requests.get(
        _OPENWEATHERMAP_URL,
        params={"q": location, "appid": api_key, "units": "imperial"},
        timeout=10,
    )
    if resp.status_code == 401:
        return (
            "OpenWeatherMap rejected the API key (HTTP 401) — check "
            "integrations.weather.openweathermap_api_key"
        )
    if resp.status_code != 200:
        return f"Weather request failed (HTTP {resp.status_code})"

    data = resp.json() or {}
    weather_list = data.get("weather") or [{}]
    main = data.get("main", {}) or {}
    return _format_weather_summary(
        place_label=data.get("name", location),
        condition=weather_list[0].get("description", "unknown conditions"),
        temp_f=main.get("temp"),
        humidity_pct=main.get("humidity"),
        wind_mph=(data.get("wind") or {}).get("speed"),
    )


def _format_weather_summary(place_label, condition, temp_f, humidity_pct, wind_mph):
    """Build the one-line "Boston: overcast, 54°F, 80% humidity, wind
    9 mph" summary shared by both weather providers."""
    parts = [f"{place_label}: {condition}"]
    if temp_f is not None:
        parts.append(f"{round(temp_f)}°F")
    if humidity_pct is not None:
        parts.append(f"{round(humidity_pct)}% humidity")
    if wind_mph is not None:
        parts.append(f"wind {round(wind_mph)} mph")
    return ", ".join(parts)


# ── CALENDAR ────────────────────────────────────────────────────
def get_calendar_events(config, days=7):
    """
    Fetch upcoming events from a configured .ics calendar feed.

    PARAMETERS
    ----------
    config : dict
        App configuration, read for integrations.calendar.*.
    days : int
        How many days ahead (from today) to include. Defaults to 7.

    RETURNS
    -------
    str
        A newline-separated list of upcoming events, "No events
        found..." if the feed has none in range, or an error message.
    """
    calendar_cfg = _get_integrations_config(config).get("calendar", {}) or {}
    ics_url = calendar_cfg.get("ics_url", "")
    if not ics_url:
        return (
            "No calendar configured. Set integrations.calendar.ics_url "
            "in config.yaml to a .ics feed URL (Google/iCloud/Outlook/"
            "Nextcloud all have a 'secret address' .ics export option)."
        )

    try:
        requests = _import_requests()
    except ImportError:
        return "`requests` library required. Run: pip install requests"

    username = calendar_cfg.get("ics_username", "")
    password = calendar_cfg.get("ics_password", "")
    auth = (username, password) if (username or password) else None

    try:
        resp = requests.get(ics_url, timeout=15, auth=auth)
        if resp.status_code != 200:
            return f"Calendar fetch failed (HTTP {resp.status_code})"
        events = parse_ics_events(resp.text)
    except requests.Timeout:
        return "Calendar request timed out"
    except Exception as e:
        return f"Calendar error: {e}"

    upcoming = _filter_upcoming_events(events, days)
    return _format_calendar_events(upcoming, days)


def _unfold_ics_lines(ics_text):
    """RFC 5545 "folds" long lines by breaking them across multiple
    physical lines, where every continuation line starts with a
    single space or tab. Undo that so each logical property is back
    on one line before we try to parse it."""
    raw_lines = ics_text.replace("\r\n", "\n").split("\n")
    unfolded = []
    for line in raw_lines:
        if line.startswith(" ") or line.startswith("\t"):
            if unfolded:
                unfolded[-1] += line[1:]
        else:
            unfolded.append(line)
    return unfolded


def _unescape_ics_text(value):
    """Undo RFC 5545's text-value escaping (\\n, \\,, \\;, \\\\)."""
    return (
        value.replace("\\n", " ")
        .replace("\\N", " ")
        .replace("\\,", ",")
        .replace("\\;", ";")
        .replace("\\\\", "\\")
    )


def _parse_ics_datetime(prop, value):
    """
    Parse one DTSTART/DTEND property into a (datetime, is_all_day)
    pair. Handles the three shapes real feeds actually use:
      - DTSTART;VALUE=DATE:20260401              (all-day event)
      - DTSTART:20260401T090000Z                 (UTC)
      - DTSTART;TZID=America/New_York:20260401T090000  (local/naive)

    Returns (None, False) for a value we can't parse rather than
    raising, so one malformed event doesn't break the whole feed.
    """
    value = value.strip()
    is_all_day = "VALUE=DATE" in prop.upper() and "VALUE=DATE-TIME" not in prop.upper()
    try:
        if is_all_day or (len(value) == 8 and "T" not in value):
            return datetime.strptime(value, "%Y%m%d"), True
        if value.endswith("Z"):
            dt = datetime.strptime(value, "%Y%m%dT%H%M%SZ")
            return dt.replace(tzinfo=timezone.utc), False
        return datetime.strptime(value, "%Y%m%dT%H%M%S"), False
    except ValueError:
        return None, False


def _apply_ics_property_line(event, line):
    """Parse one unfolded ICS property line (e.g.
    "DTSTART;VALUE=DATE:20260401") into `event`, mutating it in
    place. Ignores any property we don't care about."""
    if ":" not in line:
        return
    prop, value = line.split(":", 1)
    prop_name = prop.split(";")[0].strip().upper()

    if prop_name == "SUMMARY":
        event["summary"] = _unescape_ics_text(value)
    elif prop_name == "LOCATION":
        event["location"] = _unescape_ics_text(value)
    elif prop_name == "DTSTART":
        event["start"], event["all_day"] = _parse_ics_datetime(prop, value)
    elif prop_name == "DTEND":
        event["end"], _ = _parse_ics_datetime(prop, value)


def parse_ics_events(ics_text):
    """
    Parse the VEVENT blocks out of raw .ics text.

    This is a deliberately minimal RFC 5545 parser — just enough to
    read SUMMARY/LOCATION/DTSTART/DTEND out of real calendar exports
    (Google, iCloud, Outlook, Nextcloud all use this shape) without
    pulling in a third-party icalendar dependency for five fields.

    RETURNS
    -------
    list of dict
        Each dict has "summary", "location" (both may be absent),
        "start"/"end" (datetime or None) and "all_day" (bool).
    """
    events = []
    current = None
    for line in _unfold_ics_lines(ics_text):
        stripped = line.strip()
        if stripped == "BEGIN:VEVENT":
            current = {"all_day": False}
        elif stripped == "END:VEVENT":
            if current is not None:
                events.append(current)
            current = None
        elif current is not None:
            _apply_ics_property_line(current, line)
    return events


def _as_naive(dt):
    """Strip tzinfo (after any conversion the caller already did) so
    we can compare aware and naive datetimes uniformly — this module
    only ever compares within a single feed's own "now", never across
    timezone-sensitive boundaries, so naive comparison is sufficient."""
    return dt.replace(tzinfo=None) if getattr(dt, "tzinfo", None) else dt


def _filter_upcoming_events(events, days, now=None):
    """Return events starting between the start of today and `days`
    days from now, sorted by start time. `now` is injectable so tests
    don't depend on wall-clock time."""
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    horizon = today_start + timedelta(days=days)

    upcoming = [
        ev for ev in events
        if ev.get("start") is not None
        and today_start <= _as_naive(ev["start"]) <= horizon
    ]
    upcoming.sort(key=lambda ev: _as_naive(ev["start"]))
    return upcoming


def _format_calendar_events(events, days):
    if not events:
        return f"No events found in the next {days} day(s)."

    lines = [f"Upcoming events (next {days} day(s)):"]
    for ev in events:
        start = ev.get("start")
        label = (
            start.strftime("%a %b %d (all day)")
            if ev.get("all_day")
            else start.strftime("%a %b %d %I:%M %p")
        )
        summary = ev.get("summary", "(untitled event)")
        line = f"- {label}: {summary}"
        if ev.get("location"):
            line += f" @ {ev['location']}"
        lines.append(line)
    return "\n".join(lines)


# ── REMINDERS (Todoist) ────────────────────────────────────────
def _get_todoist_token(config):
    reminders_cfg = _get_integrations_config(config).get("reminders", {}) or {}
    return reminders_cfg.get("todoist_api_token", "")


def _todoist_headers(token):
    return {"Authorization": f"Bearer {token}"}


def _no_reminders_configured_message():
    return (
        "Reminders not configured. Set integrations.reminders."
        "todoist_api_token in config.yaml (create one at Todoist -> "
        "Settings -> Integrations -> Developer)."
    )


def add_reminder(text, config):
    """Create a new Todoist task from `text`. Returns a confirmation
    or an error string explaining what's missing/wrong."""
    if not text:
        return "No reminder text provided"

    token = _get_todoist_token(config)
    if not token:
        return _no_reminders_configured_message()

    try:
        requests = _import_requests()
    except ImportError:
        return "`requests` library required. Run: pip install requests"

    try:
        resp = requests.post(
            _TODOIST_TASKS_URL,
            headers=_todoist_headers(token),
            json={"content": text},
            timeout=10,
        )
        if resp.status_code == 401:
            return (
                "Todoist rejected the API token (HTTP 401) — check "
                "integrations.reminders.todoist_api_token"
            )
        if resp.status_code not in (200, 204):
            return f"Failed to add reminder (HTTP {resp.status_code})"
        data = resp.json() or {}
        return f"Reminder added: {data.get('content', text)}"
    except requests.Timeout:
        return "Reminder request timed out"
    except Exception as e:
        return f"Reminder error: {e}"


def list_reminders(config):
    """List open (not-yet-completed) Todoist tasks."""
    token = _get_todoist_token(config)
    if not token:
        return _no_reminders_configured_message()

    try:
        requests = _import_requests()
    except ImportError:
        return "`requests` library required. Run: pip install requests"

    try:
        tasks = _fetch_open_todoist_tasks(requests, token)
        if isinstance(tasks, str):
            return tasks  # error message from the fetch helper
        return _format_reminder_list(tasks)
    except requests.Timeout:
        return "Reminder request timed out"
    except Exception as e:
        return f"Reminder error: {e}"


def complete_reminder(query, config):
    """Find the first open Todoist task whose text contains `query`
    (case-insensitive) and mark it complete. Voice-friendly: the user
    says what the reminder was about rather than an opaque task ID."""
    if not query:
        return "No reminder text provided to match"

    token = _get_todoist_token(config)
    if not token:
        return _no_reminders_configured_message()

    try:
        requests = _import_requests()
    except ImportError:
        return "`requests` library required. Run: pip install requests"

    try:
        tasks = _fetch_open_todoist_tasks(requests, token)
        if isinstance(tasks, str):
            return tasks  # error message from the fetch helper

        match = _find_matching_task(tasks, query)
        if match is None:
            return f"No open reminder matching '{query}' found."

        close_resp = requests.post(
            f"{_TODOIST_TASKS_URL}/{match['id']}/close",
            headers=_todoist_headers(token),
            timeout=10,
        )
        if close_resp.status_code not in (200, 204):
            return f"Failed to complete reminder (HTTP {close_resp.status_code})"
        return f"Completed reminder: {match.get('content', query)}"
    except requests.Timeout:
        return "Reminder request timed out"
    except Exception as e:
        return f"Reminder error: {e}"


def _fetch_open_todoist_tasks(requests, token):
    """Shared GET-all-open-tasks call used by list_reminders() and
    complete_reminder(). Returns the parsed list on success, or an
    error message string on failure (same "str means error" contract
    used elsewhere in this module, e.g. web_actions._fetch_
    duckduckgo_results)."""
    resp = requests.get(
        _TODOIST_TASKS_URL, headers=_todoist_headers(token), timeout=10
    )
    if resp.status_code == 401:
        return (
            "Todoist rejected the API token (HTTP 401) — check "
            "integrations.reminders.todoist_api_token"
        )
    if resp.status_code != 200:
        return f"Failed to fetch reminders (HTTP {resp.status_code})"
    return resp.json() or []


def _format_reminder_list(tasks):
    if not tasks:
        return "No open reminders."
    lines = ["Open reminders:"]
    for task in tasks:
        lines.append(f"- {task.get('content', '(untitled)')}")
    return "\n".join(lines)


def _find_matching_task(tasks, query):
    query_lower = query.lower()
    for task in tasks:
        if query_lower in (task.get("content") or "").lower():
            return task
    return None
