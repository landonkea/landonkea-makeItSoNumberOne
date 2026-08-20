# ───────────────────────────────────────────────────────────────────
# tests/test_journal_entry_plugin.py, tests for the journal_entry
# example plugin's logic (retry buffer, ack handling, append/speaker
# payload fields) -- see plugins/examples/journal_entry_plugin.py.
#
# A fake `paho.mqtt.client` module (not a real broker) is installed
# into sys.modules for the duration of each test, since this plugin
# imports paho INSIDE execute() (so it degrades gracefully if paho
# isn't installed at all -- see the ImportError branch). The fake
# Client's publish() synchronously invokes any registered ack callback
# by default, so tests exercising the "got an ack" path don't need a
# real 3-second wait; the "no ack ever arrives" tests shrink
# _ACK_WAIT_SECONDS instead of actually waiting the real default.
#
# HOW TO RUN
#   cd desktop
#   python3 -m unittest discover -s tests -v
# ───────────────────────────────────────────────────────────────────

import json
import os
import sys
import tempfile
import types
import unittest
import unittest.mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import plugins.examples.journal_entry_plugin as journal_plugin  # noqa: E402


class _FakeMqttClient:
    """Enough of paho.mqtt.client.Client's surface for this plugin.
    `ack_payload`, if set, is what publish() delivers back to any
    ack-topic callback registered via message_callback_add -- None
    means "never ack," for the no-confirmation-received tests.
    `connect_error`, if set, makes connect() raise, for the
    broker-unreachable tests."""

    instances = []

    def __init__(self, ack_payload=None, connect_error=None):
        self.ack_payload = ack_payload
        self.connect_error = connect_error
        self.published = []  # (topic, payload, qos)
        self._ack_callback = None
        self._ack_topic = None
        _FakeMqttClient.instances.append(self)

    def connect(self, host, port):
        if self.connect_error:
            raise self.connect_error

    def loop_start(self):
        pass

    def loop_stop(self):
        pass

    def disconnect(self):
        pass

    def subscribe(self, topic, qos=0):
        self._ack_topic = topic

    def message_callback_add(self, topic, callback):
        self._ack_callback = callback

    def message_callback_remove(self, topic):
        self._ack_callback = None

    def publish(self, topic, payload, qos=0):
        self.published.append((topic, payload, qos))
        if topic == self._ack_topic:
            return  # flushing pending entries publishes straight to the main topic, not itself an ack trigger
        if self._ack_callback and self.ack_payload is not None:
            fake_message = types.SimpleNamespace(payload=json.dumps(self.ack_payload))
            self._ack_callback(self, None, fake_message)


_DEFAULT_ACK = {"status": "ok", "entry_id": "abc123", "appended": False}


def _install_fake_paho(ack_payload=_DEFAULT_ACK, connect_error=None):
    # `import paho.mqtt.client` needs paho and paho.mqtt to be
    # importable too (Python resolves a dotted import's parent
    # packages first) -- paho isn't actually installed in this venv
    # (see requirements.txt's commented-out paho-mqtt line), so all
    # three levels need a stub in sys.modules, not just the leaf.
    #
    # ack_payload=None (passed explicitly, as opposed to just not
    # passing this kwarg at all) means "never ack" -- the default
    # argument above is a real dict, not None, specifically so those
    # two cases stay distinguishable.

    client_module = types.ModuleType("paho.mqtt.client")
    client_module.CallbackAPIVersion = types.SimpleNamespace(VERSION2="v2")
    client_module.Client = lambda **kwargs: _FakeMqttClient(ack_payload=ack_payload, connect_error=connect_error)

    mqtt_module = types.ModuleType("paho.mqtt")
    mqtt_module.client = client_module
    paho_module = types.ModuleType("paho")
    paho_module.mqtt = mqtt_module

    return {"paho": paho_module, "paho.mqtt": mqtt_module, "paho.mqtt.client": client_module}


class JournalEntryPluginTests(unittest.TestCase):
    def setUp(self):
        _FakeMqttClient.instances = []
        self._tmpdir = tempfile.TemporaryDirectory()
        self._pending_path = os.path.join(self._tmpdir.name, "journal_pending.jsonl")
        self._orig_pending_path = journal_plugin._PENDING_PATH
        journal_plugin._PENDING_PATH = self._pending_path
        self._orig_ack_wait = journal_plugin._ACK_WAIT_SECONDS

    def tearDown(self):
        journal_plugin._PENDING_PATH = self._orig_pending_path
        journal_plugin._ACK_WAIT_SECONDS = self._orig_ack_wait
        self._tmpdir.cleanup()

    def test_no_text_is_a_clean_error_with_no_publish_attempt(self):
        plugin = journal_plugin.JournalEntryPlugin()
        result = plugin.execute({}, {})
        self.assertIn("No journal entry text was given", result)

    def test_publishes_at_qos_1_and_reports_success_on_ack(self):
        with self._fake_paho():
            plugin = journal_plugin.JournalEntryPlugin()
            result = plugin.execute({"text": "hello journal"}, {})

        client = _FakeMqttClient.instances[0]
        topic, payload, qos = client.published[0]
        self.assertEqual(topic, "soliloquy/journal")
        self.assertEqual(qos, 1)
        self.assertEqual(json.loads(payload)["text"], "hello journal")
        self.assertIn("Journal entry saved", result)

    def test_type_append_is_included_in_the_payload_and_reported_back(self):
        with self._fake_paho(ack_payload={"status": "ok", "entry_id": "x", "appended": True}):
            plugin = journal_plugin.JournalEntryPlugin()
            result = plugin.execute({"text": "also this", "type": "append"}, {})

        _, payload, _ = _FakeMqttClient.instances[0].published[0]
        self.assertEqual(json.loads(payload)["type"], "append")
        self.assertIn("Appended", result)

    def test_speaker_is_attached_from_config_when_identified(self):
        with self._fake_paho():
            plugin = journal_plugin.JournalEntryPlugin()
            plugin.execute({"text": "hi"}, {"_identified_speaker": "Landon"})

        _, payload, _ = _FakeMqttClient.instances[0].published[0]
        self.assertEqual(json.loads(payload)["speaker"], "Landon")

    def test_no_speaker_key_when_none_identified(self):
        with self._fake_paho():
            plugin = journal_plugin.JournalEntryPlugin()
            plugin.execute({"text": "hi"}, {})

        _, payload, _ = _FakeMqttClient.instances[0].published[0]
        self.assertNotIn("speaker", json.loads(payload))

    def test_reports_soliloquys_own_error_reason_from_a_failure_ack(self):
        with self._fake_paho(ack_payload={"status": "error", "reason": "message had no usable \"text\""}):
            plugin = journal_plugin.JournalEntryPlugin()
            result = plugin.execute({"text": "hi"}, {})

        self.assertIn("could not save", result)
        self.assertIn("no usable", result)

    def test_no_ack_within_the_timeout_says_so_but_does_not_crash(self):
        journal_plugin._ACK_WAIT_SECONDS = 0.05  # don't actually wait the real default
        with self._fake_paho(ack_payload=None):
            plugin = journal_plugin.JournalEntryPlugin()
            result = plugin.execute({"text": "hi"}, {})

        self.assertIn("no confirmation was received", result)

    def test_broker_unreachable_buffers_the_entry_locally(self):
        with self._fake_paho(connect_error=ConnectionRefusedError("no broker")):
            plugin = journal_plugin.JournalEntryPlugin()
            result = plugin.execute({"text": "buffer me"}, {})

        self.assertIn("Saved locally", result)
        self.assertTrue(os.path.exists(self._pending_path))
        with open(self._pending_path) as f:
            saved = json.loads(f.read().strip())
        self.assertEqual(saved["text"], "buffer me")

    def test_a_later_successful_call_flushes_the_pending_buffer(self):
        with self._fake_paho(connect_error=ConnectionRefusedError("no broker")):
            plugin = journal_plugin.JournalEntryPlugin()
            plugin.execute({"text": "buffered earlier"}, {})
        self.assertTrue(os.path.exists(self._pending_path))

        with self._fake_paho():
            result = plugin.execute({"text": "a new entry now that the broker is back"}, {})

        self.assertFalse(os.path.exists(self._pending_path))  # flushed and removed
        self.assertIn("previously buffered", result)
        client = _FakeMqttClient.instances[-1]
        published_texts = [json.loads(p)["text"] for _, p, _ in client.published if p.startswith("{")]
        self.assertIn("buffered earlier", published_texts)

    def _fake_paho(self, ack_payload=_DEFAULT_ACK, connect_error=None):
        fake_modules = _install_fake_paho(ack_payload=ack_payload, connect_error=connect_error)
        return unittest.mock.patch.dict(sys.modules, fake_modules)


if __name__ == "__main__":
    unittest.main()
