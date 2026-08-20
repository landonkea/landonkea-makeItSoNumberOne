# ───────────────────────────────────────────────────────────────────
# journal_entry_plugin.py, publishes a journal entry to Soliloquy
# ───────────────────────────────────────────────────────────────────
# Lets you say "Computer, journal entry: ..." and have it saved as a
# real entry in landonkea-soliloquy (a separate app -- see that repo's
# README for what it does). Publishes JSON over MQTT to the topic
# Soliloquy's mqtt_bridge.py listens on; Soliloquy does the actual
# saving (this plugin doesn't talk to Soliloquy's database or API
# directly -- MQTT is the only coupling between the two apps, so
# either can run without the other).
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
#
# WHAT THIS DOES BEYOND "PUBLISH ONE MESSAGE" (see
# landonkea-soliloquy's FEATURE_IDEAS.md items 1-5, all live now on
# both sides of this bridge):
#   - QoS 1, not the default QoS 0 -- Mosquitto only durably queues a
#     message for an offline subscriber (Soliloquy asleep, Docker not
#     up yet) at QoS>=1; at QoS 0 it's dropped the instant it can't be
#     delivered immediately, no matter how Soliloquy's own subscriber
#     session is configured.
#   - Waits briefly for Soliloquy's ack (soliloquy/journal/ack) so the
#     spoken confirmation reflects what ACTUALLY happened ("saved" vs.
#     a real failure reason), not just "the publish call didn't
#     raise."
#   - A local retry buffer (journal_pending.jsonl, next to this
#     project's desktop/ root, gitignored) for when the BROKER itself
#     is unreachable (not just Soliloquy, e.g. Mosquitto's container
#     is down, or a network problem) -- something QoS/durable sessions
#     can't help with, since those only take effect once a connection
#     to the broker actually exists. Every call to execute() first
#     tries to flush anything sitting in that buffer before handling
#     the new entry, so a previously-failed entry gets retried the
#     next time this action runs, not lost.
#   - type: "append" (see param_schema) merges into the day's most
#     recent entry instead of always creating a new one -- "also, one
#     more thing" a minute later.
#   - speaker: attached automatically when config["_identified_speaker"]
#     is set (see make_it_so.py, which runs core/voice_id.py's
#     identify() right after recording and stashes the result there
#     for whichever action ends up running this turn).
# ───────────────────────────────────────────────────────────────────

import json
import os
import time

# This relative import works because desktop/ is on sys.path (both
# make_it_so.py and text_mode.py add it before importing anything
# from core/), the same way core/action_router.py itself imports
# plugin_base.
from core.plugin_base import ActionPlugin

_PENDING_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "journal_pending.jsonl")
_ACK_WAIT_SECONDS = 3


class JournalEntryPlugin(ActionPlugin):
    action_name = "journal_entry"
    description = "Save a journal entry to Soliloquy over MQTT, or append to today's most recent one."
    param_schema = {
        "text": "str, what to save, transcribed from what the user said",
        "type": (
            'optional, "new" (default) or "append" -- use "append" when the user is clearly '
            'adding to something they just said (e.g. "also, one more thing...") rather than '
            "starting a new, unrelated entry"
        ),
    }

    def execute(self, params: dict, config: dict) -> str:
        text = (params.get("text") or "").strip()
        if not text:
            return "No journal entry text was given -- nothing to save."

        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            return "`paho-mqtt` library required. Run: pip install paho-mqtt"

        journal_cfg = (config.get("integrations", {}) or {}).get("journal", {}) or {}
        host = journal_cfg.get("mqtt_host", "localhost")
        port = journal_cfg.get("mqtt_port", 1883)
        topic = journal_cfg.get("mqtt_topic", "soliloquy/journal")
        entry_type = params.get("type") or "new"
        # See make_it_so.py's _record_user_speech()/main loop --
        # best-effort, real content only when voice_id has an enrolled
        # profile confident enough to name; config.get() so this still
        # works fine (no speaker attached) if that wiring isn't there.
        speaker = config.get("_identified_speaker")

        payload = {"text": text, "type": entry_type}
        if speaker:
            payload["speaker"] = speaker

        try:
            client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
            client.connect(host, port)
            client.loop_start()
        except Exception as exc:
            # Broker itself unreachable (not just Soliloquy) -- buffer
            # this entry locally and try again next time this action
            # runs, rather than losing it. See this file's own module
            # docstring for why QoS/durable sessions alone can't cover
            # this specific failure mode.
            self._buffer_pending(payload)
            return (
                f"Could not reach the MQTT broker at {host}:{port} -- {exc}. "
                "Saved locally and will retry automatically next time."
            )

        try:
            flushed = self._flush_pending(client, topic)
            ack = self._publish_and_wait_for_ack(client, topic, payload)
        finally:
            client.loop_stop()
            client.disconnect()

        return self._describe_result(ack, entry_type, flushed)

    def _publish_and_wait_for_ack(self, client, topic: str, payload: dict):
        ack_topic = f"{topic}/ack"
        received = {}

        def on_ack(client, userdata, message):
            try:
                received["ack"] = json.loads(message.payload)
            except json.JSONDecodeError:
                pass

        client.subscribe(ack_topic, qos=1)
        client.message_callback_add(ack_topic, on_ack)
        client.publish(topic, json.dumps(payload), qos=1)

        deadline = time.monotonic() + _ACK_WAIT_SECONDS
        while "ack" not in received and time.monotonic() < deadline:
            time.sleep(0.1)

        client.message_callback_remove(ack_topic)
        return received.get("ack")

    def _describe_result(self, ack, entry_type: str, flushed: int) -> str:
        flushed_note = f" ({flushed} previously buffered entr{'y' if flushed == 1 else 'ies'} also delivered.)" if flushed else ""

        if ack is None:
            return (
                "Journal entry sent, but no confirmation was received from Soliloquy within "
                f"{_ACK_WAIT_SECONDS}s -- it may still have been saved." + flushed_note
            )
        if ack.get("status") == "ok":
            verb = "Appended to today's journal entry" if ack.get("appended") else "Journal entry saved"
            return f"{verb}." + flushed_note
        return f"Soliloquy could not save the journal entry: {ack.get('reason', 'unknown reason')}." + flushed_note

    # ── Local retry buffer (broker-unreachable case) ─────────────────

    def _buffer_pending(self, payload: dict) -> None:
        with open(_PENDING_PATH, "a") as f:
            f.write(json.dumps(payload) + "\n")

    def _flush_pending(self, client, topic: str) -> int:
        """Publishes (QoS 1) anything left over from a previous
        broker-unreachable failure. Best-effort: if THIS call's
        publish somehow fails too, the file is left untouched rather
        than risking dropping entries that were never actually
        confirmed to have gone out."""
        if not os.path.exists(_PENDING_PATH):
            return 0

        with open(_PENDING_PATH) as f:
            lines = [line for line in f.read().splitlines() if line.strip()]
        if not lines:
            return 0

        try:
            for line in lines:
                client.publish(topic, line, qos=1)
        except Exception:
            return 0  # left on disk, try again next time

        os.remove(_PENDING_PATH)
        return len(lines)
