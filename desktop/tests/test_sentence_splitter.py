# ───────────────────────────────────────────────────────────────────
# tests/test_sentence_splitter.py, incremental sentence-boundary
# detection tests (see core/sentence_splitter.py)
# ───────────────────────────────────────────────────────────────────
# WHY THESE TESTS EXIST
# ----------------------
# SentenceSplitter is the piece that lets streaming TTS start
# speaking sentence 1 while sentence 2 is still being generated
# (see core/ai.py's process_with_claude_streaming() and core/tts.py's
# SpeechQueue). It has to (a) recognize real sentence endings, (b)
# NOT be fooled by abbreviations/decimals/ellipses, and (c) handle
# text arriving in arbitrary-sized chunks, including a chunk boundary
# landing in the middle of a would-be sentence end, or even in the
# middle of an abbreviation. These tests cover both split_sentences()
# (whole-string convenience) and feed()/flush() (the actual streaming
# API) directly.
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

from core.sentence_splitter import SentenceSplitter, split_sentences  # noqa: E402


class SplitSentencesTests(unittest.TestCase):
    def test_simple_two_sentences(self):
        self.assertEqual(
            split_sentences("Hello there. How are you?"),
            ["Hello there.", "How are you?"],
        )

    def test_exclamation_and_question(self):
        self.assertEqual(
            split_sentences("Engage! Where to, Captain?"),
            ["Engage!", "Where to, Captain?"],
        )

    def test_single_sentence_no_trailing_punctuation(self):
        self.assertEqual(split_sentences("Course laid in"), ["Course laid in"])

    def test_empty_string(self):
        self.assertEqual(split_sentences(""), [])

    def test_does_not_split_on_abbreviation(self):
        self.assertEqual(
            split_sentences("Dr. Crusher is in sickbay. Report immediately."),
            ["Dr. Crusher is in sickbay.", "Report immediately."],
        )

    def test_does_not_split_on_decimal_number(self):
        self.assertEqual(
            split_sentences("Warp 3.14 is our max speed. Engaging now."),
            ["Warp 3.14 is our max speed.", "Engaging now."],
        )

    def test_does_not_split_on_multi_period_abbreviation(self):
        self.assertEqual(
            split_sentences("Bring extra supplies, e.g. tricorders. Understood."),
            ["Bring extra supplies, e.g. tricorders.", "Understood."],
        )

    def test_collapses_ellipsis_run_into_a_single_boundary(self):
        # "..." followed by a space is a confirmed boundary (an
        # ellipsis run collapses to one decision based on what
        # follows its LAST character), it does NOT glue this
        # sentence to the next one.
        self.assertEqual(
            split_sentences("Well... this is unexpected. Indeed."),
            ["Well...", "this is unexpected.", "Indeed."],
        )

    def test_collapses_interrobang_run(self):
        self.assertEqual(
            split_sentences("What?! You can't be serious. I am."),
            ["What?!", "You can't be serious.", "I am."],
        )

    def test_extra_whitespace_between_sentences_is_trimmed(self):
        self.assertEqual(
            split_sentences("First one.   Second one."),
            ["First one.", "Second one."],
        )


class IncrementalFeedTests(unittest.TestCase):
    def test_sentence_only_released_once_boundary_confirmed(self):
        splitter = SentenceSplitter()
        # A period followed by nothing yet (could be a decimal in
        # progress) must NOT be released.
        self.assertEqual(splitter.feed("The reading is 3"), [])
        self.assertEqual(splitter.feed("."), [])
        # Still ambiguous, no lookahead yet.
        self.assertEqual(splitter.feed("14"), [])
        # Now it's clear this was a decimal, not a sentence end, and
        # a real sentence boundary follows.
        self.assertEqual(
            splitter.feed(" percent. Confirmed."), ["The reading is 3.14 percent."]
        )
        self.assertEqual(splitter.flush(), ["Confirmed."])

    def test_feeding_one_character_at_a_time(self):
        splitter = SentenceSplitter()
        text = "Hello. Goodbye."
        results = []
        for ch in text:
            results.extend(splitter.feed(ch))
        results.extend(splitter.flush())
        self.assertEqual(results, ["Hello.", "Goodbye."])

    def test_abbreviation_split_across_chunk_boundary(self):
        splitter = SentenceSplitter()
        out = []
        out.extend(splitter.feed("Meet Dr"))
        out.extend(splitter.feed(". Crusher now. Go."))
        out.extend(splitter.flush())
        self.assertEqual(out, ["Meet Dr. Crusher now.", "Go."])

    def test_flush_returns_remaining_unfinished_text(self):
        splitter = SentenceSplitter()
        self.assertEqual(splitter.feed("No terminal punctuation here"), [])
        self.assertEqual(
            splitter.flush(), ["No terminal punctuation here"]
        )

    def test_flush_with_nothing_left_returns_empty_list(self):
        splitter = SentenceSplitter()
        splitter.feed("Complete sentence.")
        # First feed already released nothing since no trailing text
        # follows the period yet.
        self.assertEqual(splitter.flush(), ["Complete sentence."])
        self.assertEqual(splitter.flush(), [])

    def test_empty_chunk_is_a_no_op(self):
        splitter = SentenceSplitter()
        self.assertEqual(splitter.feed(""), [])
        # A trailing period with nothing after it yet is still
        # ambiguous (could be followed by more text that turns it
        # into a decimal/abbreviation), not released until flush().
        self.assertEqual(splitter.feed("Hi there."), [])
        self.assertEqual(splitter.flush(), ["Hi there."])

    def test_multiple_sentences_in_a_single_chunk(self):
        splitter = SentenceSplitter()
        out = splitter.feed("One. Two. Three.")
        self.assertEqual(out, ["One.", "Two."])
        self.assertEqual(splitter.flush(), ["Three."])


if __name__ == "__main__":
    unittest.main()
