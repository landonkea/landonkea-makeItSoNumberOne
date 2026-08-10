# ───────────────────────────────────────────────────────────────────
# sentence_splitter.py, incremental sentence-boundary detection
# ───────────────────────────────────────────────────────────────────
# This module exists to let streaming TTS start speaking the FIRST
# sentence of an AI reply while later sentences are still being
# generated, instead of waiting for the whole response to finish.
#
# It has to work on a STREAM of text arriving in arbitrary-sized
# chunks (sometimes a few characters, sometimes a whole word), and it
# must not mistake things like "Dr. Smith", "e.g.", "3.14", or "..."
# for sentence endings. Every character of every chunk fed in is
# eventually returned to the caller, either as part of a completed
# sentence, or (for whatever's left over at the very end) via
# flush(), so no words are ever lost, delayed forever, or duplicated.
#
# This file is pure logic, no I/O, no audio, no network, on purpose,
# so it's trivial to unit test (see tests/test_sentence_splitter.py).
# ───────────────────────────────────────────────────────────────────

# Common abbreviations that end in a period but do NOT end a
# sentence. Checked case-insensitively against the word immediately
# before a candidate '.', so "Dr." matches "dr" here even though the
# text has a capital D.
#
# NOTE: multi-period abbreviations like "e.g.", "i.e.", "a.m.", "U.S."
# don't need entries here, they're handled by the "single letter
# before the period" rule below, since "e.g." is really the two
# one-letter tokens "e" and "g" each followed by a period with no
# space in between the first period and "g".
_ABBREVIATIONS = {
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc",
    "approx", "no", "co", "inc", "ltd", "gen", "col", "capt", "cmdr",
    "lt", "sgt", "rev", "hon", "esq", "fig", "vol", "univ", "dept",
    "misc", "ave", "blvd", "rd", "apt", "mt", "ft",
}

_SENTENCE_END_CHARS = (".", "!", "?")


class SentenceSplitter:
    """
    Feed it text as it arrives (in any size chunks) and it hands back
    complete sentences as soon as it's confident a sentence has
    actually ended, buffering whatever's ambiguous until either more
    text arrives to resolve it, or flush() is called at end-of-stream.

    USAGE
    -----
        splitter = SentenceSplitter()
        for chunk in stream:
            for sentence in splitter.feed(chunk):
                speak(sentence)
        for sentence in splitter.flush():   # whatever's left over
            speak(sentence)
    """

    def __init__(self):
        self._buffer = ""

    def feed(self, chunk):
        """
        Add a new chunk of streamed text. Returns a list (possibly
        empty) of newly-completed sentences.
        """
        if not chunk:
            return []
        self._buffer += chunk
        return self._extract_ready_sentences()

    def flush(self):
        """
        Call once at the end of the stream. Returns a list containing
        whatever text is left in the buffer as a final "sentence"
        (even if it doesn't end in punctuation), or an empty list if
        nothing is left.
        """
        remaining = self._buffer.strip()
        self._buffer = ""
        if remaining:
            return [remaining]
        return []

    def _extract_ready_sentences(self):
        sentences = []
        while True:
            split_at = self._find_next_split()
            if split_at is None:
                break
            sentence = self._buffer[:split_at].strip()
            self._buffer = self._buffer[split_at:].lstrip()
            if sentence:
                sentences.append(sentence)
        return sentences

    def _find_next_split(self):
        """
        Scan the current buffer for the earliest position we can be
        CONFIDENT is a sentence boundary. Returns the buffer index to
        split at (i.e. the sentence is buffer[:index]), or None if no
        confirmed boundary exists yet (either there isn't one, or we
        don't have enough lookahead yet to be sure).
        """
        buf = self._buffer
        n = len(buf)
        i = 0
        while i < n:
            if buf[i] not in _SENTENCE_END_CHARS:
                i += 1
                continue

            # Collapse a run of terminal punctuation ("...", "?!",
            # "!?!") into a single boundary decision, based on what
            # follows the LAST character of the run.
            j = i
            while j + 1 < n and buf[j + 1] in _SENTENCE_END_CHARS:
                j += 1

            if j + 1 >= n:
                # We're at the end of everything we've received so
                # far and don't know what comes next, could be a
                # space (real boundary) or a digit/letter (decimal
                # number, abbreviation). Wait for more text.
                return None

            after = buf[j + 1]
            if not after.isspace():
                # Punctuation immediately followed by a non-space
                # character: "3.14", "U.S.", "e.g.rest", not a
                # sentence boundary. Keep scanning past it.
                i = j + 1
                continue

            if self._is_abbreviation_before(buf, i):
                i = j + 1
                continue

            return j + 1  # Split right after the punctuation run.
        return None

    @staticmethod
    def _is_abbreviation_before(buf, punct_index):
        """
        True if the word/letter immediately before buf[punct_index]
        (no space in between) looks like an abbreviation rather than
        the end of a sentence.
        """
        start = punct_index
        while start > 0 and buf[start - 1].isalpha():
            start -= 1
        token = buf[start:punct_index]
        if not token:
            return False
        if len(token) == 1:
            # A single letter right before a period is almost always
            # an initial ("J. R. R. Tolkien") or the first/second
            # letter of a multi-period abbreviation ("e.g.", "U.S."),
            # not the end of a sentence.
            return True
        return token.lower() in _ABBREVIATIONS


def split_sentences(text):
    """
    Pure convenience function: split a COMPLETE string (not a stream)
    into a list of sentences. Equivalent to feeding the whole string
    into a SentenceSplitter and then flushing it, used by the
    non-streaming fallback path and by tests that don't care about
    incremental chunking.
    """
    splitter = SentenceSplitter()
    sentences = splitter.feed(text)
    sentences.extend(splitter.flush())
    return sentences
