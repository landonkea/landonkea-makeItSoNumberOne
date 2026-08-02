# ───────────────────────────────────────────────────────────────────
# actions/system.py — controls the computer (open apps, click, type)
# ───────────────────────────────────────────────────────────────────
# This module provides functions that Claude can use to control the
# computer — opening applications, typing text, pressing keyboard
# shortcuts, running commands, reading files, etc.
#
# These are the "hands" of the system — Claude thinks, and these
# functions do the physical work on the machine.
#
# PLATFORM SUPPORT
# ----------------
# - macOS: uses `open` command, AppleScript, and PyAutoGUI.
# - Windows: uses `start` command and PyAutoGUI.
# - Linux: uses `xdg-open` and PyAutoGUI.
#
# PyAutoGUI is a library that controls the mouse and keyboard.
# It must be installed: pip install pyautogui
# ───────────────────────────────────────────────────────────────────

# Import the `os` module — Python's standard toolkit for talking to
# the operating system (checking whether a file exists, expanding
# "~" into a home directory path, etc.).
import os
# Import the `platform` module. It answers questions like "what OS
# is this program running on?" — we use it below to pick the right
# command for opening apps on macOS vs. Windows vs. Linux.
import platform
# Import the `subprocess` module. It lets Python launch OTHER
# programs (like `open`, `start`, or a shell command) and wait for
# them to finish, the same way you'd type a command into a terminal.
# A "subprocess" is a separate running program that your Python
# program starts and manages, distinct from Python's own process.
import subprocess

# ── Platform detection ───────────────────────────────────────────
# We detect the OS once at module load time (the moment this file
# is first imported) so every function below can check the `SYSTEM`
# variable instead of calling platform.system() over and over.
# platform.system() returns "Darwin" for macOS (Apple's internal
# name for the OS, from the Darwin open-source core it's built on),
# "Windows" for Windows, and "Linux" for Linux.
SYSTEM = platform.system()


# ── Application launchers ────────────────────────────────────────
# Each OS has a different way to open an application by name.

def _open_app_macos(app_name):
    """
    Open an application on macOS.

    Uses the `open` command with the `-a` flag to open by app name.
    e.g. `open -a Safari` opens Safari.

    Also tries common non-standard paths if the simple name fails
    (some apps are in /Applications but not in the search path).
    """
    try:
        # First try: `open -a "AppName"` — works for most apps.
        # We pass the command as a LIST of separate strings (not one
        # combined string). subprocess treats each list item as its
        # own argument, so a space inside app_name (e.g. "App Store")
        # can't accidentally be misread as two separate arguments.
        subprocess.run(
            ["open", "-a", app_name],
            check=True,       # Raise an exception if `open` exits with
                               # a non-zero (failure) status code, so we
                               # can catch it below and try a fallback.
            timeout=10,        # Give up after 10 seconds so a hung
                               # command can't freeze the whole app.
            capture_output=True  # Swallow the command's own stdout/
                                 # stderr instead of printing it to our
                                 # terminal — we only care whether it
                                 # succeeded or failed.
        )
        return f"Opened {app_name}"
    except subprocess.CalledProcessError:
        # `open -a` failed — this usually means macOS's Launch
        # Services database doesn't know an app by that exact name
        # (e.g. it's a non-standard install). As a fallback, guess
        # the app is installed at the conventional path and open
        # that .app bundle directly by its file path instead of by
        # its registered name.
        app_path = f"/Applications/{app_name}.app"
        if os.path.exists(app_path):
            subprocess.run(["open", app_path], check=True, timeout=10)
            return f"Opened {app_name} from /Applications"
        return f"Could not find app: {app_name}"


def _open_app_windows(app_name):
    """
    Open an application on Windows.

    Uses `start` command which searches PATH and the Start Menu.
    """
    try:
        subprocess.run(
            ["start", app_name],
            check=True,
            timeout=10,
            shell=True,
            capture_output=True
        )
        return f"Opened {app_name}"
    except Exception as e:
        return f"Error opening {app_name}: {e}"


def _open_app_linux(app_name):
    """
    Open an application on Linux.

    Uses `xdg-open` which opens the default handler. For apps,
    tries the executable name directly.
    """
    try:
        subprocess.run(
            [app_name.lower()],
            check=True,
            timeout=10,
            capture_output=True
        )
        return f"Opened {app_name}"
    except FileNotFoundError:
        # Fallback: try running through the shell.
        try:
            subprocess.run(
                f"{app_name.lower()} &",
                check=True,
                timeout=10,
                shell=True
            )
            return f"Opened {app_name}"
        except Exception as e:
            return f"Could not open {app_name}: {e}"


def open_app(app_name):
    """
    Open an application by name on any platform.

    PARAMETERS
    ----------
    app_name : str
        The name of the application (e.g. "Safari", "Spotify").

    RETURNS
    -------
    str
        Success or error message.
    """
    if not app_name:
        return "No app name provided"

    print(f"  [system] Opening application: {app_name}")

    if SYSTEM == "Darwin":
        return _open_app_macos(app_name)
    elif SYSTEM == "Windows":
        return _open_app_windows(app_name)
    elif SYSTEM == "Linux":
        return _open_app_linux(app_name)
    else:
        return f"Unsupported OS: {SYSTEM}"


# ── Typing (requires PyAutoGUI) ──────────────────────────────────

def type_text(text):
    """
    Type text at the current cursor position.

    PARAMETERS
    ----------
    text : str
        The text to type.

    RETURNS
    -------
    str
        Success or error message.

    NOTE
    ----
    This uses PyAutoGUI, which must be installed.
    PyAutoGUI simulates keyboard input — it literally types the
    keys as if someone was pressing them on the keyboard.
    """
    if not text:
        return "No text provided"

    print(f"  [system] Typing text ({len(text)} chars)")

    try:
        # PyAutoGUI is imported HERE, inside the function, instead of
        # at the top of the file. If it imported at the top and
        # PyAutoGUI wasn't installed, the whole module (and therefore
        # the whole app) would crash on startup with an ImportError.
        # Importing inside a try/except lets us catch that specific
        # failure and return a friendly "please install it" message
        # instead, while every OTHER function in this file keeps
        # working normally.
        import pyautogui
        # `pyautogui.write()` simulates real keystrokes — it's as if
        # a human were pressing each key on the keyboard one at a
        # time. `interval=0.05` adds a 0.05-second pause between each
        # character (20 characters/second) so it looks and behaves
        # like human typing rather than an instant paste, which some
        # applications' text fields don't handle well.
        pyautogui.write(text, interval=0.05)
        return f"Typed {len(text)} characters"
    except ImportError:
        return "PyAutoGUI not installed. Run: pip install pyautogui"
    except Exception as e:
        return f"Typing error: {e}"


# ── Keyboard shortcuts ───────────────────────────────────────────

def press_keys(keys):
    """
    Press a keyboard shortcut (e.g. Command+Space, Ctrl+C).

    PARAMETERS
    ----------
    keys : list of str
        The keys to press, e.g. ["command", "space"] or ["ctrl", "c"].

    RETURNS
    -------
    str
        Success or error message.

    EXAMPLE
    -------
    To open Spotlight on Mac: press_keys(["command", "space"])
    To copy: press_keys(["ctrl", "c"]) on Windows/Linux
    """
    if not keys:
        return "No keys provided"

    print(f"  [system] Pressing keys: {keys}")

    try:
        import pyautogui
        # `pyautogui.hotkey()` presses several keys together, in
        # order, then releases them in reverse order — exactly like
        # holding Command and tapping Space for Spotlight. The `*`
        # in `*keys` is Python's "unpacking" syntax: it takes a list
        # like ["command", "space"] and spreads it into two separate
        # arguments, `hotkey("command", "space")`, because hotkey()
        # expects each key as its own argument rather than one list.
        # PyAutoGUI's built-in key-name table already recognizes
        # names like "command", "ctrl", and "shift" as-is, so no
        # extra translation step is needed here.
        pyautogui.hotkey(*keys)
        return f"Pressed: {'+'.join(keys)}"
    except ImportError:
        return "PyAutoGUI not installed. Run: pip install pyautogui"
    except Exception as e:
        return f"Key press error: {e}"


# ── Shell commands ───────────────────────────────────────────────

def run_command(command):
    """
    Run a shell command and return its output.

    PARAMETERS
    ----------
    command : str
        The shell command to execute (e.g. "ls -la", "dir").

    RETURNS
    -------
    str
        The command output (stdout) or error message.

    ⚠️  SECURITY NOTE
    This is powerful but dangerous — it runs ANY command the user
    asks for. Claude is instructed only to run safe commands, but
    be aware of what you ask for.
    """
    if not command:
        return "No command provided"

    print(f"  [system] Running command: {command}")

    try:
        result = subprocess.run(
            command,
            check=True,      # Raise subprocess.CalledProcessError if
                              # the command exits with a non-zero
                              # status (the standard way programs
                              # signal "something went wrong").
            timeout=15,
            # `shell=True` runs the command through the system shell
            # (e.g. bash) instead of running it as a single program
            # directly. That's what lets a command string like
            # "ls -la | grep txt" use a pipe (|) — the pipe symbol is
            # a shell feature, not something subprocess understands
            # on its own. The tradeoff is that shell=True is the
            # classic shell-injection risk if `command` ever came
            # from an untrusted source, which is why the security
            # note above exists.
            shell=True,
            capture_output=True,  # Capture both stdout and stderr
                                  # instead of letting the command
                                  # print straight to our terminal, so
                                  # we can inspect and return the text.
            text=True             # Decode the captured output as a
                                  # regular Python string instead of
                                  # raw bytes, so we can slice/print it
                                  # without an extra decoding step.
        )
        output = result.stdout.strip()
        if output:
            print(f"  [system] Output: {output[:200]}")
            return output[:500]  # Limit output to 500 chars so a
                                  # command that prints megabytes of
                                  # text can't blow up the response
                                  # we send back to the user/AI.
        return "(command completed with no output)"
    except subprocess.TimeoutExpired:
        return "Command timed out (15 seconds)"
    except subprocess.CalledProcessError as e:
        return f"Command failed: {e.stderr[:200]}"
    except Exception as e:
        return f"Command error: {e}"


# ── File reading ─────────────────────────────────────────────────

def read_file(path):
    """
    Read the contents of a file on the computer.

    PARAMETERS
    ----------
    path : str
        The path to the file (e.g. "/Users/name/Desktop/notes.txt").

    RETURNS
    -------
    str
        The file contents or error message.
    """
    if not path:
        return "No file path provided"

    print(f"  [system] Reading file: {path}")

    try:
        # Expand ~ to the user's home directory. Voice commands like
        # "read ~/Desktop/notes.txt" contain a literal tilde
        # character, but the operating system's file functions don't
        # understand "~" as shorthand — only shells do that
        # expansion for you normally. os.path.expanduser() does that
        # substitution ourselves before opening the file.
        expanded_path = os.path.expanduser(path)
        # `with open(...) as f:` opens the file using a "context
        # manager" — a with-block automatically closes the file for
        # us once the block ends, even if an error happens partway
        # through reading it. This avoids leaking an open file handle.
        with open(expanded_path, "r") as f:
            content = f.read()
        print(f"  [system] File read ({len(content)} chars)")
        return content[:1000]  # Limit to 1000 chars so a huge file
                                # doesn't overwhelm the AI's response.
    except FileNotFoundError:
        return f"File not found: {path}"
    except PermissionError:
        return f"Permission denied: {path}"
    except Exception as e:
        return f"Error reading file: {e}"


# ── Scrolling ────────────────────────────────────────────────────

def scroll(direction="down", amount=1):
    """
    Scroll the screen up or down.

    PARAMETERS
    ----------
    direction : str
        "up" or "down".
    amount : int
        How many "scroll clicks" (each is about 3 lines of text).

    RETURNS
    -------
    str
        Success or error message.
    """
    print(f"  [system] Scrolling {direction} ({amount} clicks)")

    try:
        import pyautogui
        # PyAutoGUI's scroll() function takes ONE signed number:
        # positive scrolls up, negative scrolls down. Our own
        # `direction` parameter is a friendlier "up"/"down" string,
        # so we translate it into that signed number here.
        clicks = amount * 3  # Multiply by 3 so each "click" the
                              # caller asks for moves roughly a
                              # paragraph instead of a single line —
                              # a single PyAutoGUI scroll unit is
                              # quite small on most systems.
        if direction.lower() == "down":
            pyautogui.scroll(-clicks)
        else:
            pyautogui.scroll(clicks)
        return f"Scrolled {direction} {amount} clicks"
    except ImportError:
        return "PyAutoGUI required. Run: pip install pyautogui"
    except Exception as e:
        return f"Scroll error: {e}"


# ── Mouse clicking ───────────────────────────────────────────────

def click(x, y):
    """
    Click at a specific screen position (x, y coordinates).

    PARAMETERS
    ----------
    x : int
        Horizontal pixel position (0 = left edge of screen).
    y : int
        Vertical pixel position (0 = top edge of screen).

    RETURNS
    -------
    str
        Success or error message.

    NOTE
    ----
    You can find screen coordinates by running a screen ruler app
    or by using Claude to find them programmatically.
    """
    print(f"  [system] Clicking at ({x}, {y})")

    try:
        import pyautogui
        pyautogui.click(x, y)
        return f"Clicked at ({x}, {y})"
    except ImportError:
        return "PyAutoGUI required. Run: pip install pyautogui"
    except Exception as e:
        return f"Click error: {e}"
