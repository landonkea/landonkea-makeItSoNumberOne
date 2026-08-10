# ───────────────────────────────────────────────────────────────────
# tts.py, Text-to-Speech using system commands
# ───────────────────────────────────────────────────────────────────
# This module converts Claude's text responses into spoken audio.
#
# On macOS we use the built-in `say` command (comes with every Mac).
# On Linux we try `espeak` or `festival` (may need install).
# On Windows we use the built-in SAPI via PowerShell.
#
# The goal is to use ZERO external Python libraries for TTS so the
# final executable stays small and portable. Each OS has a built-in
# way to speak text.
# ───────────────────────────────────────────────────────────────────

# Import the "os" module so we can interact with the operating
# system (like running commands or checking file paths). We don't
# directly use it in this file, but it's imported for consistency
# with the other modules in the project.
import os
# Import the "platform" module, which tells us what operating
# system the user is running (macOS, Windows, or Linux). This is
# essential because each OS uses a different command to speak text.
import platform
# Import "subprocess", which lets Python run external commands
# (like opening a program or running a terminal command). We use
# this to run the system's text-to-speech program.
import subprocess
# Import "tempfile" for creating temporary files. We don't use it
# directly here, but it's available if we ever need to save audio
# to a temporary file before playing it.
import tempfile
# "queue" and "threading" back SpeechQueue below, which plays queued
# sentences on a dedicated background thread so streaming TTS can
# hand off sentences one at a time as they're generated, while a
# single worker speaks them strictly in order.
import queue
import threading


# A private sentinel object used to tell SpeechQueue's worker thread
# "there's nothing more coming, stop." A plain string like "" won't
# do, it could collide with a legitimate (if useless) queued item,
# so we use a unique object() whose only property that matters is
# that it's `is`-comparable and nothing else will ever equal it.
_STOP = object()


class SpeechQueue:
    """
    Plays sentences of text aloud strictly in the order they were
    enqueued, one at a time, on a single background worker thread.

    WHY THIS EXISTS
    ----------------
    Streaming TTS hands sentences to us one at a time as soon as each
    one is ready (see core/ai.py's streaming Claude path), but the
    AI might finish generating sentence 2 before sentence 1 has
    finished being spoken. This class is the thing that guarantees:
      - sentences are always spoken in the order they were enqueued
        (never out of order, no matter how fast/slow they arrive),
      - only one sentence plays at a time (no overlapping audio),
      - and there's no gap-causing round-trip back to whatever
        produced the text, the moment one sentence finishes, the
        next one (if already queued) starts immediately.

    A single background thread pulling from a queue.Queue gives us
    all three for free: queue.Queue is already FIFO and thread-safe,
    and because only one worker thread ever calls speak_fn, two
    sentences physically cannot play at once.

    `speak_fn` defaults to this module's speak() (which really talks
    to the OS), but tests inject a fake no-audio function instead so
    the ordering/queueing logic can be verified without a speaker.
    """

    def __init__(self, speak_fn=None):
        self._speak_fn = speak_fn or speak
        self._queue = queue.Queue()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._started = False

    def start(self):
        """Start the background worker thread. Safe to call once;
        enqueue() also calls this automatically if needed."""
        if not self._started:
            self._started = True
            self._thread.start()

    def enqueue(self, text):
        """Add a sentence to be spoken. Returns immediately, the
        actual speaking happens on the worker thread. Blank/empty
        text is silently ignored (nothing useful to speak)."""
        if not text or not text.strip():
            return
        self.start()
        self._queue.put(text)

    def wait_done(self):
        """Block until every sentence enqueued so far has finished
        being spoken (does NOT stop the worker, more can still be
        enqueued afterward)."""
        self._queue.join()

    def close(self, timeout=30):
        """Wait for everything queued to finish speaking, then stop
        the worker thread. Call this once no more sentences for this
        turn will be enqueued."""
        if not self._started:
            return
        self.wait_done()
        self._queue.put(_STOP)
        self._thread.join(timeout=timeout)

    def _worker(self):
        while True:
            item = self._queue.get()
            try:
                if item is _STOP:
                    return
                try:
                    self._speak_fn(item)
                except Exception as e:
                    # A single bad sentence (e.g. a transient TTS
                    # engine hiccup) shouldn't take down the rest of
                    # the queue, log it and keep going.
                    print(f"  [tts] Error speaking queued sentence: {e}")
            finally:
                self._queue.task_done()


# Define a function called "speak" that takes one argument: "text",
# which is the string of words we want the computer to say aloud.
def speak(text):
    """
    Speak the given text aloud using the system's built-in TTS.

    PARAMETERS
    ----------
    text : str
        The text to speak aloud (Claude's response).

    HOW IT WORKS
    ------------
    1. Detects the operating system.
    2. Uses the OS-native speech command:
       - macOS: `say "text"` (built-in, voices available)
       - Linux: `espeak "text"` (may need `sudo apt install espeak`)
       - Windows: PowerShell SAPI (built-in)
    3. Runs the command and waits for it to finish.
    """
    # Check if "text" is empty or only contains spaces/whitespace.
    # "not text" is True if text is None or an empty string.
    # ".strip()" removes spaces from both ends, so "   " becomes "".
    if not text or not text.strip():
        # If there's nothing to say, exit the function immediately
        # using "return" (with no value). This prevents us from
        # trying to speak an empty string.
        return  # Nothing to say.

    # Remove any leading or trailing whitespace from the text
    # (extra spaces at the beginning or end) and save the result
    # back into the "text" variable.
    text = text.strip()

    # Detect the operating system. platform.system() returns a
    # string like "Darwin" (macOS), "Linux", or "Windows". We
    # store this in "system" to decide which command to run.
    system = platform.system()

    # Use a try/except block so that if the speech command fails
    # (e.g., the program isn't installed), we catch the error
    # instead of crashing the whole assistant.
    try:
        # Check if the system is macOS (Apple calls it "Darwin"
        # internally, named after Charles Darwin).
        if system == "Darwin":
            _speak_macos(text)
        elif system == "Linux":
            _speak_linux(text)
        elif system == "Windows":
            _speak_windows(text)
        else:
            # If we get here, the OS wasn't macOS, Linux, or Windows.
            # Print an error message showing what OS was detected
            # (so the user can tell us about it for future support).
            print(f"  [tts] Unknown OS: {system}. Cannot speak.")

    # If the subprocess took longer than 30 seconds, Python raises
    # subprocess.TimeoutExpired. We catch it here to handle it.
    except subprocess.TimeoutExpired:
        # Tell the user the speech was taking too long and we
        # cancelled it so the program doesn't hang forever.
        print("  [tts] Speech timed out (took too long).")
    # Catch any other unexpected errors (e.g., text has special
    # characters that break the command, permissions issues, etc.).
    except Exception as e:
        # Print the error message so the user knows what happened
        # and can report it for debugging.
        print(f"  [tts] Error during speech: {e}")


def _speak_macos(text):
    """
    Speak text aloud on macOS using the built-in `say` command.

    The `say` command has been part of macOS since the beginning.
    It uses the built-in TTS voices. Voice "Samantha" is clear and
    pleasant. subprocess.run() runs a command in the terminal, we
    pass a list: ["say", "-v", "Samantha", text]. This is equivalent
    to typing in Terminal:
        say -v Samantha "Hello world"
    """
    subprocess.run(
        ["say", "-v", "Samantha", text],
        check=True,   # Raise an error if the command fails.
        timeout=30    # Stop if it takes longer than 30 secs.
    )


def _speak_linux(text):
    """
    Speak text aloud on Linux, trying `espeak` first and falling
    back to speech-dispatcher's `spd-say` if espeak isn't installed.

    espeak is the most common Linux TTS. On Raspberry Pi install it
    with: sudo apt install espeak
    """
    try:
        # Run "espeak" with the text as an argument.
        subprocess.run(
            ["espeak", text],
            check=True,   # Raise error if espeak fails.
            timeout=30    # Stop after 30 seconds.
        )
    # If "espeak" is not installed, Python raises FileNotFoundError
    # (the executable wasn't found on the system's PATH).
    except FileNotFoundError:
        # espeak not installed, try speech-dispatcher's "spd-say"
        # command as a fallback.
        try:
            subprocess.run(
                ["spd-say", text],
                check=True,   # Raise error if it fails.
                timeout=30    # Stop after 30 seconds.
            )
        # If neither espeak nor spd-say are installed, catch the
        # FileNotFoundError again.
        except FileNotFoundError:
            # Print a helpful message telling the user to install
            # espeak so speech will work.
            print("  [tts] No TTS found. Install espeak:")
            print("    sudo apt install espeak")


def _speak_windows(text):
    """
    Speak text aloud on Windows using the built-in SAPI (Speech API)
    via a PowerShell one-liner. No extra install needed.

    The PowerShell script:
    1. Loads the System.Speech library (Add-Type).
    2. Creates a SpeechSynthesizer object.
    3. Calls .Speak() with the text.

    NOTE: PowerShell's escape character is the backtick (`), not a
    backslash, inside a double-quoted string, a literal " must
    become `" (or ""). Using a backslash here (as you would in
    Python or C) does NOT escape anything in PowerShell, so a
    spoken response containing a quote character would have broken
    the command. `.replace()` swaps every literal double-quote in
    the text for a backtick followed by a double-quote so
    PowerShell treats it as a normal character inside the string
    instead of ending the string early.
    """
    ps_script = (
        f'Add-Type -AssemblyName System.Speech; '
        f'$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; '
        f'$s.Speak("{text.replace(chr(34), chr(96) + chr(34))}")'
    )
    # Run the PowerShell command. "powershell" is the program,
    # "-Command" tells it to run a script string.
    subprocess.run(
        ["powershell", "-Command", ps_script],
        check=True,   # Raise error if PowerShell fails.
        timeout=30    # Stop after 30 seconds.
    )
