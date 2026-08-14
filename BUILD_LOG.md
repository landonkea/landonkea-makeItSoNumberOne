# BUILD_LOG.md

How this repo went from an empty folder to what's on disk right now, and the exact
commands to get back here from scratch. If this repo, GitHub history included,
vanished tomorrow, this is the document that gets you back to a working
`make-it-so` in one sitting with no guesswork.

Two things this file is not: a feature changelog (git log already does that
better) and a tutorial on Kotlin or Swift. It's a rebuild script written in
prose, aimed at "I have a blank machine and this markdown file, go."

## 1. What actually happened, in order

The commit history is short (41 commits, three weeks, one branch that
matters — `main`) and tells a pretty linear story:

1. **`76a440e` — initial release.** Desktop (Python), Android (Kotlin), and iOS
   (Swift) all landed in the same commit: wake word → chime → listen →
   transcribe → ask Claude → speak → act, on all three platforms at once. No
   tests, no CI, no README beyond a stub.
2. **`0b043b5` → `d9ed672` → `3abf572` — comment pass, merged into main as
   v1.1.0.** Every line across all sixteen source files at the time got a
   beginner-friendly comment. This is why the codebase reads like it has a
   teacher looking over your shoulder; that's intentional, not filler. (No
   git tag was ever pushed for this — the version number lives only in the
   merge commit message, `3abf572`.)
3. **`9528046` → `49f06e4` → `3a4e57f` — offline mode, merged into main as
   v1.2.0.** Vosk (speech-to-text) and Ollama (local LLM) added as a
   no-internet fallback on all three platforms, config-selectable via
   `mode: online|offline|auto`. Same story here: `3a4e57f`'s commit message
   says v1.2.0, but there's no `git tag` to match it.
4. **`0a441a4` through `1dd49b7` — iOS caught up.** The iOS target didn't
   actually have a working Xcode project until this stretch: `xcodegen`
   entered here (`project.yml` became the source of truth, `.xcodeproj` a
   generated artifact), the Porcupine wake-word API got fixed for Swift, and
   shared assets got wired into the iOS bundle.
5. **`2d270fc`, `fb2eb67`, `9ce8a64` — first README and first CI.** Real bugs
   fixed alongside the docs, Android build flavors added, and
   `.github/workflows/ci.yml` showed up covering all three platforms
   (Python compile-check + tests, Kotlin compile, iOS simulator build).
6. **`2f8fe31` → `dbeebcd` — the maturity stretch (Aug 2–12).** This is most of
   the repo's actual engineering: single-responsibility refactors on
   desktop and Android, a real prompt-injection defense for `run_command`/
   `read_file` (`af6c9b2`), routines.yaml macros and bounded conversation
   history, a plugin system replacing desktop's action if/elif chain
   (`b3a24cc`), real weather/calendar/reminders integrations, Ollama model
   management, in-app settings screens on Android and iOS, streaming TTS and
   personalization profiles, a text-mode Docker image for desktop CI, and
   finally a real desktop test suite (252 tests) plus enough Android/iOS
   tests to catch and fix a genuine action-parsing bug on Android
   (`dbeebcd`).
7. **`58399db`, `cda3fdd` — CI attribution gate.** A workflow that fails any
   commit or file carrying AI-tool attribution, because this is meant to
   read as one person's work, which it is.

Two platform-specific repos exist too — `landonkea-makeitso-desktop`,
`-android`, `-ios` — split out of this monorepo with `git-filter-repo` so
each platform's history is available standalone. This repo, the monorepo, is
the canonical source; the split repos are read-only mirrors.

## 2. Rebuilding from absolute zero

Everything below assumes a blank machine: no repo, no Android Studio, no
Xcode, nothing installed beyond an OS. Each step is a real command, not a
description of one. Run desktop's steps on Linux/macOS/Windows, Android's on
any OS with the Android SDK, iOS's on a Mac only, Xcode has no other option.

### 2.0 Tooling every platform needs

```bash
# Git, obviously, and the language toolchains this repo is written in.
git --version    # >= 2.30
python3 --version  # >= 3.11 for desktop
```

### 2.1 Recreate the repo shell

```bash
mkdir make-it-so-number-one && cd make-it-so-number-one
git init -b main
mkdir -p desktop/core desktop/tests desktop/assets desktop/plugins/examples \
         android/app/src/main/java/com/landonkea/makeitso \
         android/app/src/test/java/com/landonkea/makeitso \
         android/gradle/wrapper \
         ios/MakeItSo/Resources ios/MakeItSo/Tests/MakeItSoTests \
         shared/sounds shared/prompts \
         scripts docs .github/workflows
```

At this point you're recreating file *contents*, not just structure. The
fastest zero-manual-input path is cloning the actual repo (below); the
directory layout above is what you'd be aiming to reproduce if starting from
truly nothing, e.g. rewriting from this document alone with no source handy.

```bash
# The real, fast way to get every file back if the remote still exists:
git clone git@github.com:landonkea/landonkea-makeItSoNumberOne.git
```

### 2.2 Desktop (Python) — build tooling and run

```bash
cd desktop

# System dependency: pyaudio compiles a C extension against PortAudio.
# Debian/Ubuntu:
sudo apt-get update && sudo apt-get install -y portaudio19-dev
# macOS:
brew install portaudio
# Windows: prebuilt pyaudio wheels on PyPI already bundle PortAudio,
# no separate install needed.

python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

pip install -r requirements.txt
cp config.example.yaml config.yaml
# Fill in anthropic_api_key, openai_api_key, porcupine_access_key in
# config.yaml — see README.md's "Platform setup" section for where each
# key comes from. Offline-only setups can skip anthropic/openai and set
# mode: "offline" instead, but porcupine_access_key is required either way.

cp routines.example.yaml routines.yaml       # optional, macros
cp profile.example.yaml profile.yaml         # optional, personalization

python make_it_so.py     # voice mode, needs a real mic/speaker
# or, no audio hardware / headless:
python text_mode.py      # typed stdin/stdout REPL, same brain

# Run the test suite (252 tests):
python -m unittest discover -s tests -v

# Package a standalone binary (no Python needed to run it after this):
pip install pyinstaller
python build_pyinstaller.py
# → dist/MakeItSo.app (macOS) / dist/MakeItSo.exe (Windows) / dist/MakeItSo (Linux)

# Same thing, but for a specific CI build channel (debug/beta/release,
# see .github/workflows/build-channels.yml). Changes the output
# filename (MakeItSo-debug / MakeItSo-beta / MakeItSo) and, on macOS,
# skips wrapping debug builds in a .app so the terminal stays attached
# for reading stack traces:
python build_pyinstaller.py --channel debug
# → dist/MakeItSo-debug  (no .app wrapper — debug skips --windowed on macOS)
```

Offline mode additionally needs:

```bash
# Ollama, the local LLM runtime:
curl -fsSL https://ollama.ai/install.sh | sh   # macOS/Linux; Windows: installer from ollama.ai
ollama pull llama3.2

# Vosk, offline speech-to-text — download a model and unzip it here:
# https://alphacephei.com/vosk/models  →  desktop/models/vosk-model-small-en-us-0.15/
```

Desktop in Docker (text mode only, no audio hardware in a container):

```bash
cd ..   # repo root — the Dockerfile is built with root as context
cp .env.example .env
# fill in ANTHROPIC_API_KEY (and/or OPENAI_API_KEY) in .env
docker compose run --rm desktop
```

### 2.3 Android (Kotlin) — build tooling and run

```bash
# Requires the Android SDK. The command-line-tools-only path (no Android
# Studio GUI needed for a from-scratch, scriptable rebuild):
#   1. Download "Command line tools" from developer.android.com/studio
#   2. sdkmanager --install "platform-tools" "platforms;android-36" \
#        "build-tools;36.0.0"

cd android
chmod +x gradlew

# API keys: android/app/build.gradle.kts has BuildConfig placeholders
# (ANTHROPIC_API_KEY, PICOVOICE_ACCESS_KEY). Replace the placeholder
# strings directly, or read them from a gitignored local.properties —
# either way, real keys never get committed.

# Compile-check both build types:
./gradlew compileDebugKotlin compileReleaseKotlin

# Run the JVM unit tests:
./gradlew testDebugUnitTest

# Build an installable debug APK:
./gradlew assembleDebug
# → app/build/outputs/apk/debug/app-debug.apk

# Release APK (unsigned — no keystore is committed to this repo on
# purpose; add a signingConfigs block with your own keystore before
# distributing a release build):
./gradlew assembleRelease
# → app/build/outputs/apk/release/app-release-unsigned.apk
```

Install onto a connected device/emulator with `adb install
app/build/outputs/apk/debug/app-debug.apk`, or open `android/` in Android
Studio and hit Run if you'd rather use the IDE than the command line.

### 2.4 iOS (Swift) — build tooling and run

Mac + Xcode only; there's no way around that for an iOS build.

```bash
xcode-select --install     # Xcode command-line tools, if not already present
brew install xcodegen      # generates the .xcodeproj from project.yml

cd ios/MakeItSo
xcodegen generate          # reads project.yml, writes MakeItSo.xcodeproj

# API keys: set as environment variables on the MakeItSo scheme
# (Product → Scheme → Edit Scheme → Run → Arguments → Environment
# Variables in Xcode), or via `xcodebuild ... OTHER_SWIFT_FLAGS=...`
# for a scripted build — the app reads them through
# ProcessInfo.processInfo.environment, never hardcoded.

# Build for the simulator (no signing needed, no device required):
xcodebuild -scheme MakeItSo -sdk iphonesimulator build

# Run the Swift Package test suite (19 tests, independent of the Xcode
# project — this is what actually exercises ClaudeService's parsing):
swift test

# To install on a real device you need Apple Developer signing, which
# this repo intentionally does not ship (no certificates, no
# provisioning profile). Open the project in Xcode, pick your own team
# under Signing & Capabilities, and run to a connected device from there.
```

### 2.5 Shared assets

`shared/sounds/computer_chime.wav` and `shared/prompts/system_prompt.txt` are
the two files every platform reads from a `shared/` copy at build time
(desktop via `--add-data` in `build_pyinstaller.py`, Android/iOS via
resources checked into their own trees, copied from here). If rebuilding
from nothing without the original files, the chime is a two-tone
Star-Trek-style acknowledgment sound and the system prompt is the
instruction block that tells Claude/Ollama the `RESPONSE:`/`ACTIONS:` output
format and the full action list — both need to exist before any platform's
"Think" step will produce output the "Act" step can parse.

### 2.6 Verify everything at once

```bash
# From repo root, after 2.2-2.4 above:
scripts/run_all_tests.sh
# writes a combined pass/fail report to test-results/latest.md
```

## 3. What "zero manual input" doesn't cover

Two things in this repo are deliberately impossible to automate, and that's
correct, not a gap:

- **API keys.** `anthropic_api_key`, `openai_api_key`, and
  `porcupine_access_key` all come from accounts a human has to create
  (console.anthropic.com, platform.openai.com, console.picovoice.ai). No
  script can generate these; the repo is built to run with placeholders and
  fail clearly if a feature needing a real key gets exercised without one.
- **Signing.** Android's `assembleRelease` produces an unsigned APK, and iOS
  needs a real Apple Developer team selected in Xcode before it'll install
  on a device. Neither a keystore nor a provisioning profile is, or should
  be, checked into this repo. See `.github/workflows/build-channels.yml`
  for how the CI build-channel workflows produce unsigned artifacts a human
  signs and distributes afterward.
