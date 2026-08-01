#!/usr/bin/env python3
# The line above is a "shebang" that tells the operating system to run
# this script with Python 3. On Linux and macOS, this lets you run the
# file directly (./build_pyinstaller.py) without typing "python" first.
# It's a standard convention for Python executable scripts.

# ───────────────────────────────────────────────────────────────────
# build_pyinstaller.py — builds standalone .exe/.app/.bin
# ───────────────────────────────────────────────────────────────────
# This script uses PyInstaller to package the entire voice
# assistant into a single executable file that works WITHOUT
# needing Python installed on the end user's computer.
#
# OUTPUT FILES
# ------------
# macOS:  dist/MakeItSo.app   (double-click to run)
# Windows: dist/MakeItSo.exe   (double-click to run)
# Linux:  dist/MakeItSo        (./MakeItSo to run)
#
# USAGE
# -----
#   pip install pyinstaller
#   python build_pyinstaller.py
#
# The finished executable will be in the desktop/dist/ folder.
# ───────────────────────────────────────────────────────────────────

# Import the `os` module to interact with the operating system.
# We need this to build file paths and check if files/folders exist.
import os

# Import the `sys` module for system-specific functions.
# We use `sys.exit(1)` to exit the script with an error code if
# something goes wrong during the build process.
import sys

# Import the `shutil` module for high-level file operations.
# "shutil" stands for "shell utilities." We use it to remove entire
# directories (like the old build/ and dist/ folders) with one command.
import shutil

# Import the `subprocess` module to run external programs.
# We use this to actually run the PyInstaller command-line tool from
# within our Python script. It's like typing a command in the terminal,
# but done programmatically.
import subprocess


# Define a function named `build` that handles the entire PyInstaller
# build process. Functions are reusable blocks of code that you can
# "call" (run) whenever you need that behavior.
def build():
    """
    Build the standalone executable using PyInstaller.

    HOW IT WORKS
    ------------
    1. PyInstaller analyzes the Python code to find ALL libraries
       and files it needs.
    2. It bundles everything into one folder (or one file with
       --onefile) that contains the app + Python runtime + all
       dependencies.
    3. The result is a portable executable — NO install needed.
    """
    # ── Get the script's directory ───────────────────────────────
    # `os.path.abspath(__file__)` gets the full absolute path to this
    # script file (e.g., /Users/.../desktop/build_pyinstaller.py).
    # `os.path.dirname(...)` gets just the directory part
    # (e.g., /Users/.../desktop/). We store this in `script_dir` so
    # we can reference other files relative to this location.
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # ── Check PyInstaller is installed ───────────────────────────
    # Try to import PyInstaller. If it's not installed, this will
    # raise an ImportError, which we catch below.
    try:
        # Attempt to import the PyInstaller module.
        # If this succeeds, we know PyInstaller is installed and
        # available on the system.
        import PyInstaller
    # If the import fails, catch the ImportError so we can show a
    # helpful message instead of a scary traceback.
    except ImportError:
        # Print a blank line for spacing.
        print()
        # Print the top border of an error message box.
        print("  ╔══════════════════════════════════════════════════╗")
        # Print the error message telling the user what's missing.
        print("  ║  PyInstaller not installed!                    ║")
        # Print an empty separator line.
        print("  ║                                                ║")
        # Print the fix: the pip install command.
        print("  ║  Run:  pip install pyinstaller                  ║")
        # Print the bottom border of the box.
        print("  ╚══════════════════════════════════════════════════╝")
        # Print a blank line after the box.
        print()
        # Exit the script with an error code (1 means "something went
        # wrong"). This stops the build process immediately.
        sys.exit(1)

    # Print a message saying the build has started.
    print("  [build] Starting PyInstaller build...")
    # Print the source directory so the user can verify we're building
    # from the right place.
    print(f"  [build] Source: {script_dir}")

    # ── Clean previous builds ────────────────────────────────────
    # Remove old dist/ and build/ folders so we start fresh.
    # Loop through a list of folder names ["dist", "build"] that
    # PyInstaller creates during the build process.
    for folder in ["dist", "build"]:
        # Construct the full path to the folder by joining the script
        # directory with the folder name (e.g., /path/desktop/dist).
        path = os.path.join(script_dir, folder)
        # Check if the folder actually exists on the filesystem.
        # `os.path.exists(path)` returns True if it exists, False otherwise.
        if os.path.exists(path):
            # Print a message saying we're removing the old folder.
            print(f"  [build] Removing old {folder}/...")
            # Remove the entire folder and ALL its contents recursively.
            # `shutil.rmtree(path)` deletes the folder and everything
            # inside it. "rmtree" = "remove tree" (a tree of files/folders).
            shutil.rmtree(path)

    # ── Remove old .spec file ────────────────────────────────────
    # Construct the path to the PyInstaller .spec file.
    # The .spec file is a configuration file that PyInstaller generates
    # during the build. We remove it to ensure a clean build.
    spec_path = os.path.join(script_dir, "make_it_so.spec")
    # Check if the .spec file exists from a previous build.
    if os.path.exists(spec_path):
        # Delete the old .spec file so it doesn't interfere with the
        # new build. We want PyInstaller to generate a fresh one.
        os.remove(spec_path)

    # ── Build command ────────────────────────────────────────────
    # These are the PyInstaller flags:
    #   --onefile         = Single executable (not a folder).
    #   --name "..."      = Name of the output executable.
    #   --add-data        = Include extra files (chime WAV, prompt).
    #   --distpath        = Where to put the finished executable.
    #   --workpath        = Where to put temporary build files.
    #   --specpath        = Where to put the .spec file.
    #   --noconfirm       = Overwrite without asking.
    #   --clean           = Clean cache before building.
    #
    # On macOS we also add:
    #   --windowed        = No terminal window (runs in background).
    #   --icon            = App icon (optional, can add later).

    # Paths to extra files we need to bundle.
    # Build the path to the assets directory (icons, sounds, etc.).
    assets_dir = os.path.join(script_dir, "assets")
    # Build the path to the shared prompts directory.
    # We go up one directory from script_dir (using os.path.dirname)
    # to get to the project root, then down into shared/prompts/.
    prompt_dir = os.path.join(
        os.path.dirname(script_dir),
        "shared",
        "prompts"
    )

    # Start building the command as a list of strings.
    # Each element in the list is one "word" in the command.
    # We use a list instead of a string to avoid issues with spaces
    # and special characters in file paths.
    cmd = [
        "pyinstaller",                                    # The tool to run.
        "--onefile",                                      # Single .exe/.app file.
        "--name", "MakeItSo",                             # Name of the output.
        "--distpath", os.path.join(script_dir, "dist"),   # Output folder.
        "--workpath", os.path.join(script_dir, "build"),  # Temp build folder.
        "--specpath", script_dir,                          # .spec file location.
        "--noconfirm",                                    # Don't ask to overwrite.
        "--clean",                                        # Clean cache first.
    ]

    # Include the shared system prompt if it exists.
    # Build the full path to the system_prompt.txt file.
    prompt_file = os.path.join(prompt_dir, "system_prompt.txt")
    # Check if the prompt file actually exists before trying to add it.
    if os.path.exists(prompt_file):
        # Add the --add-data flag to the command. This tells PyInstaller
        # to bundle a file that the app needs at runtime (like the prompt).
        cmd.append("--add-data")
        # Specify which file to add and where it should appear inside
        # the bundle. The format is "source:destination". On Windows,
        # the separator is a semicolon (;) instead of colon (:).
        cmd.append(f"{prompt_file}:shared/prompts/")

    # Include the assets directory (for the chime WAV and icons).
    # Check if the assets folder exists.
    if os.path.exists(assets_dir):
        # Add the --add-data flag for the assets folder.
        cmd.append("--add-data")
        # Bundle the assets folder into the app bundle, placing it at
        # "assets/" inside the executable.
        cmd.append(f"{assets_dir}:assets/")

    # Platform-specific options.
    # Import Python's `platform` module to detect the operating system.
    import platform
    # Check if the operating system is macOS.
    # `platform.system()` returns "Darwin" for macOS.
    if platform.system() == "Darwin":
        # Add --windowed flag so the app runs without a terminal window.
        # This makes it behave like a normal Mac app (you can double-click
        # it from Finder without a terminal popping up).
        cmd.append("--windowed")
        # Add the --icon flag to set the app's icon, but only if an
        # icon file actually exists. PyInstaller errors out (and the
        # whole build fails) if you point --icon at a path that isn't
        # there, and there's currently no icon.icns checked into
        # assets/ — so skip the flag instead of breaking the build.
        icon_path = os.path.join(assets_dir, "icon.icns")
        if os.path.exists(icon_path):
            cmd.append("--icon")
            # Point to the .icns icon file in the assets directory.
            cmd.append(icon_path)
        else:
            print(f"  [build] No icon.icns found in {assets_dir} — "
                  f"building without a custom icon.")

    # The main Python script to bundle into the executable.
    # This is the entry point that runs when the user launches the app.
    cmd.append(os.path.join(script_dir, "make_it_so.py"))

    # ── Run PyInstaller ──────────────────────────────────────────
    # Print the full command for debugging purposes.
    # `' '.join(cmd)` turns the list into a space-separated string.
    print(f"  [build] Running: {' '.join(cmd)}")
    # Print a blank line before the build output.
    print()

    # Try to run the PyInstaller command and catch errors.
    try:
        # Run the command using subprocess.run().
        # `check=True` means Python will raise an error if the command
        # returns a non-zero exit code (indicating failure).
        subprocess.run(cmd, check=True)
    # If the command fails (returns error code), catch the exception.
    except subprocess.CalledProcessError as e:
        # Print the error message so the user knows what failed.
        print(f"  [build] Build failed: {e}")
        # Exit the script with an error code to signal failure.
        sys.exit(1)

    # ── Done ────────────────────────────────────────────────────
    # Print a blank line for spacing.
    print()
    # Print the top of a success message box.
    print("  ╔══════════════════════════════════════════════════╗")
    # Print a success message with a checkmark emoji.
    print("  ║  ✅  BUILD COMPLETE!                           ║")
    # Print a separator line.
    print("  ║                                                ║")
    # Check the platform again to show the correct output path format.
    if platform.system() == "Darwin":
        # macOS: the output is a .app bundle.
        print("  ║  Your app is at:                                ║")
        # Print the relative path to the macOS app.
        print(f"  ║  desktop/dist/MakeItSo.app              ║")
    elif platform.system() == "Windows":
        # Windows: the output is a .exe file.
        print("  ║  Your app is at:                                ║")
        # Print the relative path to the Windows executable.
        print(f"  ║  desktop/dist/MakeItSo.exe              ║")
    else:
        # Linux: the output is an executable binary with no extension.
        print("  ║  Your app is at:                                ║")
        # Print the relative path to the Linux binary.
        print(f"  ║  desktop/dist/MakeItSo                  ║")
    # Print a separator line.
    print("  ║                                                ║")
    # Print a note that the app is portable (no Python needed).
    print("  ║  Share this with anyone — no Python needed!    ║")
    # Print the bottom border of the success box.
    print("  ╚══════════════════════════════════════════════════╝")
    # Print a blank line at the end for clean formatting.
    print()


# This special Python check runs only when this file is executed directly
# (not when imported). `__name__` is set to "__main__" when the script
# is run with `python build_pyinstaller.py`.
if __name__ == "__main__":
    # Call the build() function to start the PyInstaller build process.
    # This is the entry point that kicks everything off.
    build()
