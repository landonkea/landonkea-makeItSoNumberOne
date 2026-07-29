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

import os
import platform
import subprocess

# ── Platform detection ───────────────────────────────────────────
# We detect the OS once at module load time so every function can
# check it without re-detecting.
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
        subprocess.run(
            ["open", "-a", app_name],
            check=True,
            timeout=10,
            capture_output=True
        )
        return f"Opened {app_name}"
    except subprocess.CalledProcessError:
        # Second try: Look in /Applications/ directly.
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
        import pyautogui
        # Add a small delay between characters to simulate human
        # typing speed (0.05 seconds = 20 chars per second).
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
        # Convert key names to match PyAutoGUI's format.
        # PyAutoGUI expects things like "cmd", "ctrl", "shift".
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
            check=True,
            timeout=15,
            shell=True,           # Allows pipes, redirects, etc.
            capture_output=True,  # Capture both stdout and stderr.
            text=True             # Return strings, not bytes.
        )
        output = result.stdout.strip()
        if output:
            print(f"  [system] Output: {output[:200]}")
            return output[:500]  # Limit output to 500 chars.
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
        # Expand ~ to the user's home directory.
        expanded_path = os.path.expanduser(path)
        with open(expanded_path, "r") as f:
            content = f.read()
        print(f"  [system] File read ({len(content)} chars)")
        return content[:1000]  # Limit to 1000 chars.
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
        # PyAutoGUI scroll() takes positive for up, negative for down.
        clicks = amount * 3  # Multiply for smoother scrolling.
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
