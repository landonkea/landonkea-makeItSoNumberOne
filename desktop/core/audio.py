# ───────────────────────────────────────────────────────────────────
# audio.py, microphone recording and sound playback
# ───────────────────────────────────────────────────────────────────
# This is the audio engine for Make It So Number One.
# It handles:
#   1. Generating the Star Trek TNG computer chime (WAV file)
#   2. Playing the chime (to acknowledge "Computer" was heard)
#   3. Recording audio from the microphone (for speech-to-text after
#      the wake word is detected)
#
# The chime is generated with pure Python (no extra libraries needed
# for that part). Recording and playback require the `pyaudio`
# library, which we will bundle in the final executable.
# ───────────────────────────────────────────────────────────────────

import wave
import math
import struct
import os
import time

# ── Audio constants ──────────────────────────────────────────────
# These are the shared settings for ALL audio in this app.
SAMPLE_RATE = 22050   # Number of audio samples per second (22050 Hz
                      # is good enough for voice and simple chimes).
CHANNELS = 1          # Mono audio (one channel, simpler, smaller).
SAMPLE_WIDTH = 2      # 16-bit audio (2 bytes per sample, standard
                      # quality for voice).
SILENCE_THRESHOLD = 500   # Amplitude level below which we consider
                          # it "silence" (used to detect when the
                          # user stops speaking).

# ── Chime generation (pure Python, zero dependencies) ────────────
# The Star Trek TNG computer acknowledgment is a short two-tone
# descending chime:
#   Tone 1: A5 (880 Hz) for 150 milliseconds
#   Tone 2: D5 (587 Hz) for 150 milliseconds
#   Gap between them: 50 milliseconds
# We generate this as raw PCM samples and save it to a .wav file.


def _generate_sine_wave(frequency_hz, duration_ms, volume=0.5):
    """
    Generate a sine wave as a list of 16-bit PCM samples.

    PARAMETERS
    ----------
    frequency_hz : float
        How high-pitched the tone is (e.g. 880 for A5).
    duration_ms : int
        How long the tone lasts in milliseconds.
    volume : float
        How loud (0.0 = silent, 1.0 = max).

    RETURNS
    -------
    list of int
        16-bit signed integer samples (-32768 to 32767) that can be
        written directly into a WAV file.

    HOW IT WORKS
    ------------
    A sine wave is the smoothest kind of sound wave, it sounds like
    a pure musical note. The formula is:
        sample = sin(2 * pi * frequency * current_time) * max_amplitude
    where `current_time` increases by 1/SAMPLE_RATE each sample.
    """
    # Calculate how many samples we need for the given duration.
    num_samples = int(SAMPLE_RATE * duration_ms / 1000)
    # The maximum 16-bit amplitude (half of 65536, since it's signed).
    max_amp = int(volume * 32767)
    samples = []
    for i in range(num_samples):
        # `t` is the time in seconds at this sample point.
        t = i / SAMPLE_RATE
        # Generate the sine wave value at this point in time.
        value = math.sin(2 * math.pi * frequency_hz * t)
        # Scale to 16-bit range and convert to integer.
        sample = int(value * max_amp)
        samples.append(sample)
    return samples


def _generate_silence(duration_ms):
    """
    Generate silent samples (all zeros) for a given duration.

    PARAMETERS
    ----------
    duration_ms : int
        How long the silence lasts in milliseconds.

    RETURNS
    -------
    list of int
        All zeros, these represent silence.
    """
    num_samples = int(SAMPLE_RATE * duration_ms / 1000)
    return [0] * num_samples


def generate_chime(output_path):
    """
    Generate the Star Trek TNG computer acknowledgment chime and
    save it as a WAV file at `output_path`.

    The chime sounds like:
        "DING-ding" (two descending tones)
    - First tone: A5 (880 Hz), the higher, attention-getting note
    - Brief silence
    - Second tone: D5 (587 Hz), the lower, confirming note

    This plays automatically when the wake word "Computer" is
    detected, just like on the Enterprise.
    """
    # Build the chime from individual pieces.
    samples = []
    # Tone 1: A5 (880 Hz) for 150ms, the "attention" note.
    samples.extend(_generate_sine_wave(880, 150, volume=0.5))
    # Brief gap of silence (50ms), separates the two notes.
    samples.extend(_generate_silence(50))
    # Tone 2: D5 (587 Hz) for 120ms, the "acknowledged" note.
    samples.extend(_generate_sine_wave(587, 120, volume=0.4))

    # Write the WAV file using Python's built-in `wave` module.
    # No extra libraries needed!
    with wave.open(output_path, "w") as wf:
        # Set the WAV file parameters (matching our constants).
        wf.setnchannels(CHANNELS)     # Mono.
        wf.setsampwidth(SAMPLE_WIDTH) # 16-bit.
        wf.setframerate(SAMPLE_RATE)  # 22050 Hz.
        # Pack each sample as a 16-bit signed integer (`<h` means
        # little-endian short, which is standard for WAV files).
        for sample in samples:
            wf.writeframes(struct.pack("<h", sample))

    print(f"  [audio] Chime saved to {output_path}")


# ── Platform-specific audio playback ─────────────────────────────
# We try to use built-in OS commands first (no install needed).
# If those fail, we fall back to PyAudio (which the user must have
# installed during development, bundled in the final .exe).

def _play_sound_osx(file_path):
    """
    Play a WAV file on macOS using `afplay` (built-in command).

    `afplay` comes with every Mac, no installation required. It
    plays audio files from the command line and returns when done.
    """
    os.system(f"afplay \"{file_path}\"")


def _play_sound_linux(file_path):
    """
    Play a WAV file on Linux using `aplay` (part of ALSA).

    `aplay` comes with almost every Linux distribution. On Raspberry
    Pi OS and Debian it's pre-installed.
    """
    os.system(f"aplay \"{file_path}\"")


def _play_sound_windows(file_path):
    """
    Play a WAV file on Windows using `start` (built-in).

    On Windows, `start` opens the file with the default program,
    which for .wav files is usually Windows Media Player or the
    system sounds player.
    """
    os.system(f"start \"\" \"{file_path}\"")


# ── Public playback function ─────────────────────────────────────

def play_chime():
    """
    Play the Star Trek computer acknowledgment chime.

    This function:
    1. Checks if the chime WAV file exists; if not, generates it.
    2. Determines the current OS (macOS, Linux, Windows).
    3. Plays the chime using the appropriate method.

    The chime plays when "Computer" is detected, it's the same
    "I hear you" sound as the Enterprise computer.
    """
    # The chime file lives next to this Python file, in the assets
    # folder at the desktop project root.
    chime_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "assets",
        "computer_chime.wav"
    )

    # Generate the chime file if it doesn't already exist.
    if not os.path.exists(chime_path):
        print("  [audio] Generating chime file for the first time...")
        # Make sure the assets directory exists.
        os.makedirs(os.path.dirname(chime_path), exist_ok=True)
        generate_chime(chime_path)

    # Detect platform and use the appropriate playback method.
    import platform
    system = platform.system()

    if system == "Darwin":
        # macOS (Darwin is Apple's internal name for macOS).
        _play_sound_osx(chime_path)
    elif system == "Linux":
        _play_sound_linux(chime_path)
    elif system == "Windows":
        _play_sound_windows(chime_path)
    else:
        print(f"  [audio] Unknown OS: {system}. Cannot play chime.")


# ── Microphone recording ─────────────────────────────────────────
# We use `pyaudio` for microphone access because it works on all
# platforms. PyAudio is a library that lets Python read from your
# computer's microphone.

def list_microphones():
    """
    Print all available microphone devices.

    This is useful for debugging, it shows you which microphones
    the system can see (built-in mic, USB mic, Bluetooth headset,
    etc.). Run this if the app can't hear you.
    """
    try:
        import pyaudio
        p = pyaudio.PyAudio()
        print("  [audio] Available microphone devices:")
        for i in range(p.get_device_count()):
            dev = p.get_device_info_by_index(i)
            # Only show devices that can RECORD (input channels > 0).
            if dev["maxInputChannels"] > 0:
                print(f"    {i}: {dev['name']}")
        p.terminate()
    except ImportError:
        print("  [audio] PyAudio not installed. Cannot list mics.")
        print("  Install with: pip install pyaudio")


def record_until_silence(timeout_seconds=10):
    """
    Record audio from the microphone until the user stops speaking
    (or until a timeout is reached).

    PARAMETERS
    ----------
    timeout_seconds : int
        Maximum recording time. Prevents infinite recording if the
        background is noisy.

    RETURNS
    -------
    bytes or None
        Raw PCM audio data (16-bit, 22050 Hz, mono) that can be
        sent to the speech-to-text engine.
        Returns None if no speech was detected.

    HOW IT WORKS
    ------------
    1. Opens the microphone and starts recording in chunks.
    2. For each chunk, checks if the audio level is above the
       silence threshold (meaning someone is speaking).
    3. Once speech starts, keeps recording until we hear silence
       for 1.5 continuous seconds.
    4. Returns the audio bytes (omitting leading/trailing silence).
    """
    try:
        import pyaudio
    except ImportError:
        print("  [audio] PyAudio not installed. Install with:")
        print("    pip install pyaudio")
        print("  On macOS you may also need: brew install portaudio")
        return None

    # ── Audio recording settings ──────────────────────────────
    CHUNK = 1024       # Number of frames per buffer (smaller =
                       # lower latency, larger = more efficient).
    FORMAT = pyaudio.paInt16   # 16-bit integer format (matches
                               # our SAMPLE_WIDTH = 2).
    RATE = SAMPLE_RATE          # 22050 Hz (same as our audio
                                # constants).
    SILENCE_LIMIT_SECONDS = 1.5 # How long of silence means the
                                # user is done speaking.

    # ── Initialize PyAudio ────────────────────────────────────
    # PyAudio is the library that gives Python access to the
    # computer's audio hardware. `PyAudio()` creates the top-level
    # object that manages that connection; we'll ask it to open a
    # microphone "stream" (a live, ongoing feed of audio data) next.
    p = pyaudio.PyAudio()

    # Open the microphone stream.
    # `input=True` means we're recording (not playing).
    stream = p.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=RATE,
        input=True,
        frames_per_buffer=CHUNK
    )

    print("  [audio] Listening... (speak now)")
    print(f"  [audio] Will stop after {SILENCE_LIMIT_SECONDS}s of silence"
          f" or {timeout_seconds}s total.")

    try:
        frames = _record_chunks_until_silence(
            stream, CHUNK, RATE, timeout_seconds, SILENCE_LIMIT_SECONDS
        )
    finally:
        # ── Clean up ──────────────────────────────────────────
        # This runs whether recording finished normally or raised an
        # exception, so we never leave the microphone hardware
        # "held open" by a crashed recording, that would block any
        # later attempt to record again until the whole app restarts.
        stream.stop_stream()
        stream.close()
        p.terminate()

    if not frames:
        print("  [audio] No speech detected.")
        return None

    # Combine all audio chunks into one big byte string.
    audio_data = b"".join(frames)
    duration = len(frames) * CHUNK / RATE
    print(f"  [audio] Recorded {len(audio_data)} bytes ({duration:.1f}s)")

    return audio_data


def _chunk_loudness(chunk_bytes):
    """
    Measure how loud one chunk of raw audio is.

    PARAMETERS
    ----------
    chunk_bytes : bytes
        One chunk of raw 16-bit PCM audio samples.

    RETURNS
    -------
    float
        The RMS (Root Mean Square) amplitude of the chunk, a
        single number representing how loud it is. 0 means silence;
        larger numbers mean louder sound. RMS is the standard way to
        measure audio loudness because it accounts for every sample
        in the chunk (unlike, say, just taking the single loudest
        sample), and squaring each value before averaging makes
        loud and quiet moments cancel out less than they would with
        a simple average, which matters because a raw sine wave's
        positive and negative halves would otherwise average toward
        zero even during loud speech.
    """
    # Convert the raw bytes back into a tuple of individual 16-bit
    # signed numbers (same unpacking technique used elsewhere in
    # this codebase for reading PCM audio).
    samples = struct.unpack_from(
        "<" + "h" * (len(chunk_bytes) // 2), chunk_bytes
    )
    if not samples:
        return 0
    # RMS formula: square every sample (so negative and positive
    # values both count as "loud" instead of cancelling out), take
    # the average of those squares, then take the square root to
    # bring the result back to a normal amplitude scale.
    return math.sqrt(sum(s * s for s in samples) / len(samples))


def _record_chunks_until_silence(
    stream, chunk_size, rate, timeout_seconds, silence_limit_seconds
):
    """
    Read audio chunks from an open microphone stream until the user
    has spoken and then gone quiet for `silence_limit_seconds`, or
    until `timeout_seconds` total have elapsed.

    RETURNS
    -------
    list of bytes
        The recorded chunks (including the leading silence right
        before speech started, and the trailing pause that signaled
        the user was done, trimming those isn't necessary for
        speech-to-text accuracy). Empty list if no speech was ever
        detected.
    """
    frames = []          # Stores all the audio chunks we record.
    has_started = False  # Has the user started speaking yet?
    silence_chunks = 0   # How many consecutive silent chunks.
    max_chunks = int(timeout_seconds * rate / chunk_size)
    total_chunks = 0

    while total_chunks < max_chunks:
        # Read one chunk of audio from the microphone.
        # `exception_on_overflow=False` tells PyAudio not to raise an
        # error if our program reads chunks slightly slower than the
        # microphone produces them (a common hiccup under system
        # load), we'd rather silently drop a few audio samples than
        # crash the whole recording.
        data = stream.read(chunk_size, exception_on_overflow=False)
        total_chunks += 1

        rms = _chunk_loudness(data)

        if rms > SILENCE_THRESHOLD:
            # The user is speaking (this chunk is loud enough).
            if not has_started:
                print("  [audio] Speech detected!")
                has_started = True
            # Reset the silence counter, the user is still talking.
            silence_chunks = 0
            frames.append(data)
        else:
            # This chunk is quiet.
            if has_started:
                # We've heard speech before, so this is a pause.
                silence_chunks += 1
                frames.append(data)
                # Check if the pause is long enough to stop.
                silence_seconds = silence_chunks * chunk_size / rate
                if silence_seconds >= silence_limit_seconds:
                    print("  [audio] Silence detected, stopping.")
                    break
            # If we haven't started yet, just discard silent chunks.

    return frames
