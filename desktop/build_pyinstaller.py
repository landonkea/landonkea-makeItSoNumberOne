#!/usr/bin/env python3
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

import os
import sys
import shutil
import subprocess


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
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # ── Check PyInstaller is installed ───────────────────────────
    try:
        import PyInstaller
    except ImportError:
        print()
        print("  ╔══════════════════════════════════════════════════╗")
        print("  ║  PyInstaller not installed!                    ║")
        print("  ║                                                ║")
        print("  ║  Run:  pip install pyinstaller                  ║")
        print("  ╚══════════════════════════════════════════════════╝")
        print()
        sys.exit(1)

    print("  [build] Starting PyInstaller build...")
    print(f"  [build] Source: {script_dir}")

    # ── Clean previous builds ────────────────────────────────────
    # Remove old dist/ and build/ folders so we start fresh.
    for folder in ["dist", "build"]:
        path = os.path.join(script_dir, folder)
        if os.path.exists(path):
            print(f"  [build] Removing old {folder}/...")
            shutil.rmtree(path)

    # ── Remove old .spec file ────────────────────────────────────
    spec_path = os.path.join(script_dir, "make_it_so.spec")
    if os.path.exists(spec_path):
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
    # The chime WAV is generated at runtime, but we include assets.
    assets_dir = os.path.join(script_dir, "assets")
    prompt_dir = os.path.join(
        os.path.dirname(script_dir),
        "shared",
        "prompts"
    )

    cmd = [
        "pyinstaller",
        "--onefile",
        "--name", "MakeItSo",
        "--distpath", os.path.join(script_dir, "dist"),
        "--workpath", os.path.join(script_dir, "build"),
        "--specpath", script_dir,
        "--noconfirm",
        "--clean",
    ]

    # Include the shared system prompt if it exists.
    prompt_file = os.path.join(prompt_dir, "system_prompt.txt")
    if os.path.exists(prompt_file):
        cmd.append("--add-data")
        cmd.append(f"{prompt_file}:shared/prompts/")

    # Include the assets directory (for the chime WAV).
    if os.path.exists(assets_dir):
        cmd.append("--add-data")
        cmd.append(f"{assets_dir}:assets/")

    # Platform-specific options.
    import platform
    if platform.system() == "Darwin":
        # macOS: use .app bundle.
        cmd.append("--windowed")
        cmd.append("--icon")
        cmd.append(os.path.join(assets_dir, "icon.icns"))

    # The main script to bundle.
    cmd.append(os.path.join(script_dir, "make_it_so.py"))

    # ── Run PyInstaller ──────────────────────────────────────────
    print(f"  [build] Running: {' '.join(cmd)}")
    print()

    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"  [build] Build failed: {e}")
        sys.exit(1)

    # ── Done ────────────────────────────────────────────────────
    print()
    print("  ╔══════════════════════════════════════════════════╗")
    print("  ║  ✅  BUILD COMPLETE!                           ║")
    print("  ║                                                ║")
    if platform.system() == "Darwin":
        print("  ║  Your app is at:                                ║")
        print(f"  ║  desktop/dist/MakeItSo.app              ║")
    elif platform.system() == "Windows":
        print("  ║  Your app is at:                                ║")
        print(f"  ║  desktop/dist/MakeItSo.exe              ║")
    else:
        print("  ║  Your app is at:                                ║")
        print(f"  ║  desktop/dist/MakeItSo                  ║")
    print("  ║                                                ║")
    print("  ║  Share this with anyone — no Python needed!    ║")
    print("  ╚══════════════════════════════════════════════════╝")
    print()


if __name__ == "__main__":
    build()
