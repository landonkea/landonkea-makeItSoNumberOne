# Make It So

A cross-platform, Star Trek–themed voice assistant. Say **"Computer"** to wake it up, then
ask it to do something — open an app, search the web, control your system — and it talks
back and takes the action.

The same idea is implemented natively three times, once per platform:

| Platform | Language | Entry point |
|---|---|---|
| `desktop/` | Python | `desktop/make_it_so.py` |
| `android/` | Kotlin (Jetpack Compose) | `android/app/src/main/java/com/landonkea/makeitso/MainActivity.kt` |
| `ios/` | Swift (SwiftUI) | `ios/MakeItSo/ContentView.swift` |

Shared assets (the wake chime sound and the system prompt sent to Claude) live in `shared/`
and are copied into each platform's build.

## How it works

Every platform runs the same loop:

1. **Wake word** — listen for "Computer" using [Porcupine](https://picovoice.ai/) (on-device,
   offline wake-word detection).
2. **Chime** — play the two-tone Star Trek acknowledgment sound.
3. **Listen** — record the user's command from the microphone.
4. **Transcribe** — convert speech to text (Whisper on desktop, native platform speech
   recognition on Android/iOS).
5. **Think** — send the text to Claude (with recent conversation history for context) and get
   back what to say plus a list of actions to run.
6. **Speak** — read Claude's response aloud via text-to-speech.
7. **Act** — execute the returned actions (open an app, search the web, control the system,
   etc.), then go back to listening for the wake word.

Desktop additionally supports a fully **offline** mode: Ollama (a local LLM) in place of
Claude, and Vosk in place of Whisper, so the assistant can run with no API keys and no
internet connection.

## Platform setup

### Desktop (Python)

Requires Python 3 and a working microphone/speakers.

```bash
cd desktop
pip install -r requirements.txt
cp config.example.yaml config.yaml
# edit config.yaml and fill in your API keys (see below)
python make_it_so.py
```

`config.yaml` is where all secrets live and is **gitignored** — it is never committed.
`config.example.yaml` is the tracked template; copy it and fill in the keys you need:

- `anthropic_api_key` — from [console.anthropic.com](https://console.anthropic.com) (Claude, online mode)
- `openai_api_key` — from [platform.openai.com](https://platform.openai.com) (Whisper STT, online mode)
- `porcupine_access_key` — from [console.picovoice.ai](https://console.picovoice.ai) (wake word, required in every mode)

Set `mode: "online"`, `"offline"`, or `"auto"` (tries online first, falls back to offline) in
`config.yaml`. Offline mode needs [Ollama](https://ollama.ai) running locally
(`ollama pull llama3.2`) and a [Vosk](https://alphacephei.com/vosk/models) model downloaded
to `desktop/models/`.

To build a standalone binary (`.exe` / `.app`) instead of running from source:

```bash
python build_pyinstaller.py
```

### Android (Kotlin)

Requires Android Studio / the Android SDK (`compileSdk 36`, `minSdk 26`).

1. Open `android/` in Android Studio.
2. Set your API keys — currently read from `buildConfigField` placeholders in
   `android/app/build.gradle.kts` (`ANTHROPIC_API_KEY`, `PICOVOICE_ACCESS_KEY`). Replace the
   placeholder strings there, or wire them up via `local.properties` (gitignored) and a
   `local.properties`-reading block in Gradle if you don't want real keys sitting in a
   tracked file.
3. Build and run on a device or emulator.

Debug and release build types are defined in `android/app/build.gradle.kts`: `debug` uses an
`.debug` application-ID suffix so it can be installed side by side with a release build, and
`release` enables R8 minification/resource shrinking. There is currently **no release signing
config** committed (and there shouldn't be — that needs a real keystore and Play Console
credentials the repo doesn't have), so `assembleRelease` produces an unsigned APK; add a
`signingConfigs` block with your own keystore before publishing.

### iOS (Swift)

Requires Xcode and a Mac.

1. Open `ios/MakeItSo/MakeItSo.xcodeproj` in Xcode.
2. Set `ANTHROPIC_API_KEY` and `PICOVOICE_ACCESS_KEY` as environment variables on the
   `MakeItSo` scheme (Product → Scheme → Edit Scheme → Run → Arguments → Environment
   Variables) — the app reads them via `ProcessInfo.processInfo.environment`, so no keys are
   ever hardcoded or committed.
3. Build and run on a simulator or device (scheme: `MakeItSo`, using Xcode's standard Debug /
   Release configurations — there's no separate staging configuration, which is appropriate
   for a single-developer personal app).

There's also a `Package.swift` alongside the Xcode project; it compiles the same sources under
`swift build` on macOS (using `#if os(iOS)` stubs) as a quick way to typecheck the code without
opening Xcode.

## Tests / verification

There are no automated test suites in this repo yet. What's verifiable without hardware/API
keys:

- **Desktop**: `python3 -m py_compile make_it_so.py core/*.py core/actions/*.py build_pyinstaller.py` — passes, no syntax errors.
- **Android**: `./gradlew compileDebugKotlin` and `compileReleaseKotlin` — pass. A full
  `assembleDebug`/`assembleRelease` needs a JDK 17 toolchain (this project targets Java 17);
  it isn't buildable end-to-end with a newer JDK.
- **iOS**: `xcodebuild -scheme MakeItSo -sdk iphonesimulator -configuration Debug build` — full
  simulator build succeeds.

None of the three apps can be *run* in a headless environment — they all need a real
microphone, speakers, and (for Android/iOS) a device or simulator.

## Secrets

No API keys, tokens, or credential files are committed anywhere in this repo. Desktop reads
secrets from `config.yaml` (gitignored), Android from `BuildConfig` placeholders you fill in
locally, and iOS from scheme-level environment variables. If you're setting this up for
yourself, get your own keys from Anthropic, OpenAI, and Picovoice — none are shared here.
