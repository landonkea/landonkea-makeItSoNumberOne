# ───────────────────────────────────────────────────────────────────
# tests/test_speech_queue.py, tests for core/tts.py's SpeechQueue
# ───────────────────────────────────────────────────────────────────
# WHY THESE TESTS EXIST
# ----------------------
# SpeechQueue is what makes streaming TTS actually sound right: it
# guarantees sentences are spoken in the order they were enqueued
# (never out of order, no matter how fast/slow the AI produces them),
# one at a time (no overlapping audio), on a single background
# thread. These tests inject a fake, no-audio speak_fn (a tiny sleep
# to simulate real speech taking non-zero time, recording call order)
# so the ordering/queueing/threading contract can be verified without
# touching any real audio device.
#
# HOW TO RUN
# ----------
#   cd desktop
#   python3 -m unittest discover -s tests -v
# ───────────────────────────────────────────────────────────────────

import os
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.tts import SpeechQueue  # noqa: E402


class SpeechQueueOrderingTests(unittest.TestCase):
    def test_sentences_are_spoken_in_enqueue_order(self):
        spoken = []
        lock = threading.Lock()

        def fake_speak(text):
            # Deliberately variable "speak time" so a naive
            # implementation that didn't serialize properly would be
            # likely to reorder things.
            time.sleep(0.01 if len(text) % 2 == 0 else 0.02)
            with lock:
                spoken.append(text)

        queue = SpeechQueue(speak_fn=fake_speak)
        queue.enqueue("First sentence.")
        queue.enqueue("Second one.")
        queue.enqueue("Third and final.")
        queue.close()

        self.assertEqual(
            spoken, ["First sentence.", "Second one.", "Third and final."]
        )

    def test_only_one_sentence_speaks_at_a_time(self):
        concurrent_count = {"current": 0, "max": 0}
        lock = threading.Lock()

        def fake_speak(text):
            with lock:
                concurrent_count["current"] += 1
                concurrent_count["max"] = max(
                    concurrent_count["max"], concurrent_count["current"]
                )
            time.sleep(0.01)
            with lock:
                concurrent_count["current"] -= 1

        queue = SpeechQueue(speak_fn=fake_speak)
        for i in range(5):
            queue.enqueue(f"Sentence {i}.")
        queue.close()

        self.assertEqual(concurrent_count["max"], 1)

    def test_blank_and_empty_text_is_ignored(self):
        spoken = []
        queue = SpeechQueue(speak_fn=lambda t: spoken.append(t))
        queue.enqueue("")
        queue.enqueue("   ")
        queue.enqueue("Real sentence.")
        queue.close()
        self.assertEqual(spoken, ["Real sentence."])

    def test_wait_done_blocks_until_current_queue_drains(self):
        spoken = []

        def fake_speak(text):
            time.sleep(0.01)
            spoken.append(text)

        queue = SpeechQueue(speak_fn=fake_speak)
        queue.enqueue("One.")
        queue.enqueue("Two.")
        queue.wait_done()
        self.assertEqual(spoken, ["One.", "Two."])
        # The worker is still alive after wait_done(), more can be
        # enqueued afterward.
        queue.enqueue("Three.")
        queue.close()
        self.assertEqual(spoken, ["One.", "Two.", "Three."])

    def test_a_failing_sentence_does_not_stop_the_rest(self):
        spoken = []

        def flaky_speak(text):
            if text == "Bad one.":
                raise RuntimeError("simulated TTS engine hiccup")
            spoken.append(text)

        queue = SpeechQueue(speak_fn=flaky_speak)
        queue.enqueue("Good one.")
        queue.enqueue("Bad one.")
        queue.enqueue("Also good.")
        queue.close()

        self.assertEqual(spoken, ["Good one.", "Also good."])

    def test_close_with_nothing_ever_enqueued_is_a_harmless_no_op(self):
        queue = SpeechQueue(speak_fn=lambda t: None)
        # Never called enqueue(), the worker thread was never even
        # started. close() must not hang or raise.
        queue.close()

    def test_default_speak_fn_is_the_module_level_speak(self):
        import core.tts as tts_module

        queue = SpeechQueue()
        self.assertIs(queue._speak_fn, tts_module.speak)


if __name__ == "__main__":
    unittest.main()
