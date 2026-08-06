# ───────────────────────────────────────────────────────────────────
# journal_entry_plugin.py — publishes a journal entry to Soliloquy
# ───────────────────────────────────────────────────────────────────
# Lets you say "Computer, journal entry: ..." and have it saved as a
# real entry in landonkea-soliloquy (a separate app -- see that repo's
# README for what it does). Publishes {"text": "..."} as JSON over
# MQTT to the topic Soliloquy's mqtt_bridge.py listens on; Soliloquy
# does the actual saving (this plugin doesn't talk to Soliloquy's
# database or API directly -- MQTT is the only coupling between the
# two apps, so either can run without the other).
#
# To try it out:
#
#   cp desktop/plugins/examples/journal_entry_plugin.py desktop/plugins/
#
# (desktop/plugins/*.py is gitignored -- see .gitignore -- everything
# EXCEPT this examples/ folder, which is the documented template.)
#
# Also needs, in config.yaml:
#
#   integrations:
#     journal:
#       mqtt_host: localhost   # optional, defaults to localhost
#       mqtt_port: 1883        # optional, defaults to 1883
#       mqtt_topic: soliloquy/journal   # optional, defaults to this
#
# and `pip install paho-mqtt` (see desktop/requirements.txt).
#
# For Claude to actually emit a journal_entry action when you say
# "Computer, journal entry: ...", this action also needs to be
# documented in core/ai.py's _JSON_FORMAT_ADDENDUM -- see that file;
# this plugin alone (without that documentation) would work fine if
# invoked via a routines.yaml entry, but Claude wouldn't spontaneously
# know to use it from a spoken request.
# ───────────────────────────────────────────────────────────────────

import json

# This relative import works because desktop/ is on sys.path (both
# make_it_so.py and text_mode.py add it before importing anything
# from core/), the same way core/action_router.py itself imports
# plugin_base.
from core.plugin_base import ActionPlugin


class JournalEntryPlugin(ActionPlugin):
    action_name = "journal_entry"
    description = "Save a journal entry to Soliloquy over MQTT."
    param_schema = {"text": "str — what to save, transcribed from what the user said"}

    def execute(self, params: dict, config: dict) -> str:
        text = (params.get("text") or "").strip()
        if not text:
            return "No journal entry text was given -- nothing to save."

        try:
            import paho.mqtt.publish as mqtt_publish
        except ImportError:
            return "`paho-mqtt` library required. Run: pip install paho-mqtt"

        journal_cfg = (config.get("integrations", {}) or {}).get("journal", {}) or {}
        host = journal_cfg.get("mqtt_host", "localhost")
        port = journal_cfg.get("mqtt_port", 1883)
        topic = journal_cfg.get("mqtt_topic", "soliloquy/journal")

        try:
            mqtt_publish.single(topic, json.dumps({"text": text}), hostname=host, port=port)
        except Exception as exc:
            # Never let a network/broker problem raise out of execute()
            # -- report it back to the user instead (same pattern as
            # get_weather()/get_calendar_events() in
            # core/actions/integrations.py for the built-in plugins).
            return f"Could not reach the Soliloquy MQTT broker at {host}:{port} -- {exc}"

        return "Journal entry saved."
