// ───────────────────────────────────────────────────────────────────
// MainActivity.kt — the app's main screen (Android)
// ───────────────────────────────────────────────────────────────────
// This is the first screen that shows when the user opens the app.
// It shows:
//   1. The current state of the assistant (listening/processing/idle)
//   2. A button to manually trigger the wake word detection
//   3. The assistant's spoken response (as text on screen)
//   4. Any actions that were executed
//
// The main logic (wake word → listen → think → speak → act) runs
// in a background coroutine so the UI stays responsive.
//
// The "think" step now supports DUAL MODE:
//   - ONLINE  → Claude API (cloud, requires internet + API key)
//   - OFFLINE → Ollama on localhost:11434 (local, free)
//   - AUTO    → try online first, fall back to offline if it fails
// ───────────────────────────────────────────────────────────────────

// This line declares the package (namespace) this file belongs to. It matches the folder structure.
package com.landonkea.makeitso

// ── Android system imports ────────────────────────────────────────
// These import built-in Android classes needed for permissions, TTS, and activity lifecycle.

// Manifest contains constant strings for Android permissions (like RECORD_AUDIO).
import android.Manifest
// Intent is a messaging object that Android uses to start activities and pass data between them.
import android.content.Intent
// PackageManager lets us check whether the user has granted certain permissions.
import android.content.pm.PackageManager
// Bundle is a key-value container used to pass data between activities and save/restore state.
import android.os.Bundle
// TextToSpeech is Android's built-in engine that speaks text aloud through the phone's speaker.
import android.speech.tts.TextToSpeech
// ComponentActivity is the base class for activities that use Jetpack Compose for their UI.
import androidx.activity.ComponentActivity
// setContent is a function that sets up the Compose UI tree for this activity.
import androidx.activity.compose.setContent
// Layout imports provide composable functions like Column, Spacer, and padding modifiers.
import androidx.compose.foundation.layout.*
// Material3 imports provide themed UI components like Button, Text, Card, and MaterialTheme.
import androidx.compose.material3.*
// Compose runtime imports provide state management tools like mutableStateOf and remember.
import androidx.compose.runtime.*
// Alignment provides alignment options for placing content inside containers.
import androidx.compose.ui.Alignment
// Modifier is the core Compose class for decorating and configuring composables (padding, size, etc.).
import androidx.compose.ui.Modifier
// dp (density-independent pixels) is a unit of measurement that scales correctly on different screens.
import androidx.compose.ui.unit.dp
// ActivityCompat provides backward-compatible versions of permission request methods.
import androidx.core.app.ActivityCompat
// ContextCompat provides backward-compatible methods for checking permissions.
import androidx.core.content.ContextCompat
// Coroutine imports provide the coroutine building blocks: launch, async, delay, and scopes.
import kotlinx.coroutines.*
// Locale represents a specific geographical/political region (e.g., US English for TTS voice).
import java.util.Locale
// BuildConfig is auto-generated from build.gradle.kts (holds API keys, etc.).
import com.landonkea.makeitso.BuildConfig
// JSONArray/JSONObject let us persist conversation history to a small JSON file on disk,
// the same format desktop's conversation_history.json uses (see loadConversationHistory()/
// saveConversationHistory() below).
import org.json.JSONArray
import org.json.JSONObject
// File lets us read/write conversationHistory.json in the app's private storage directory.
import java.io.File

// MainActivity is the entry point of the app — it's the screen that appears when the app launches.
// ComponentActivity is the standard base for Android activities using Jetpack Compose.
class MainActivity : ComponentActivity() {

    // ── State variables ─────────────────────────────────────────
    // These are displayed on the screen and update automatically
    // when changed (Jetpack Compose "recomposes" the UI).

    // mutableStateOf() creates a Compose state variable. When its value changes, the UI automatically re-draws.
    // assistantState shows the current status text displayed on screen (e.g., "Listening...").
    private var assistantState by mutableStateOf("Say \"Computer\" to start")

    // lastResponse stores the assistant's most recent spoken text so it can be shown on the screen.
    private var lastResponse by mutableStateOf("")

    // lastAction stores a description of the most recent action that was executed (shown in the UI).
    private var lastAction by mutableStateOf("")

    // CoroutineScope manages background work. Dispatchers.Default uses a thread pool for CPU work,
    // and SupervisorJob() means if one child coroutine fails, others keep running.
    private val scope = CoroutineScope(Dispatchers.Default + SupervisorJob())

    // Text-to-Speech engine instance. "var" means it can change (initialized in onCreate, null when destroyed).
    // "?" means it can be null (the TTS engine might not be available or isn't initialized yet).
    private var tts: TextToSpeech? = null

    // ── Re-entrancy guard ────────────────────────────────────────
    // Holds a reference to the currently running assistant-cycle coroutine (a "Job" is
    // Kotlin's handle for a coroutine that lets you check if it's still running, or cancel it).
    // WHY THIS EXISTS: without this guard, if the user taps the "Say 'Computer'" button twice
    // quickly, startAssistant() would launch a SECOND runAssistantCycle() coroutine while the
    // first one is still mid-flight. Both copies would then fight over the same microphone
    // (wakeWordDetector and SpeechRecognizer both talk to the single physical mic), and worse,
    // SpeechRecognizer always uses the same hardcoded requestCode (2000) for every recognition
    // request — so the second cycle would silently overwrite the first cycle's pending listener
    // in that map, leaving the first cycle's coroutine suspended forever waiting for a result
    // that will never arrive (a permanent "leak" of that coroutine). Tracking the Job lets us
    // simply ignore a new tap while a cycle is already running, which avoids all of that.
    private var assistantJob: Job? = null

    // ── Conversation history ────────────────────────────────────
    // Bounded list of prior {role, content} turns, mirroring desktop's conversation_history
    // (see desktop/make_it_so.py) so Claude/Ollama on Android get the same "remembers the last
    // few exchanges" context desktop already has. Loaded from disk in onCreate() and appended
    // to after every completed cycle in runAssistantCycle(); MAX_HISTORY_TURNS caps growth the
    // same way desktop trims to the last 20 entries.
    private var conversationHistory: MutableList<ConversationTurn> = mutableListOf()

    // ── Conversation history file ────────────────────────────────
    // Lives in the app's private files directory (filesDir) — not accessible to other apps,
    // and automatically cleared if the user uninstalls the app. Computed lazily since filesDir
    // isn't available until the Activity/Context exists.
    private val historyFile: File by lazy {
        File(filesDir, "conversation_history.json")
    }

    // ── Config values ──────────────────────────────────────────
    // The operating mode for the assistant:
    //   "auto"    → try Claude API online first, fall back to Ollama offline if it fails
    //   "online"  → use Claude API only (fail if no internet)
    //   "offline" → use Ollama locally only (fail if Ollama isn't running)
    // This can be loaded from a config file or shared preferences in the future.
    // For now it's hardcoded to "auto" to give the best user experience.
    private val assistantMode = "auto"

    // ── Max conversation history length ──────────────────────────
    // Matches desktop's default (see desktop/config.example.yaml's settings.max_history: 20) —
    // 20 entries = 10 user + 10 assistant turns. Kept as a simple constant here since Android
    // has no equivalent settings file yet (see conversationHistory above).
    private val maxHistoryTurns = 20

    // ── Picovoice Access Key ────────────────────────────────────
    // Reads the Porcupine wake word key from a system property first
    // (useful for testing), then falls back to BuildConfig (set in
    // app/build.gradle.kts -> PICOVOICE_ACCESS_KEY).
    private val picovoiceAccessKey: String by lazy {
        System.getProperty("picovoice.access.key") ?: BuildConfig.PICOVOICE_ACCESS_KEY
    }

    // ── Wake word detector ──────────────────────────────────────
    // Created lazily (on first access) so we don't block onCreate
    // with Porcupine model loading. The detector manages its own
    // AudioRecord and Porcupine lifecycle internally.
    //
    // We spell this out as a named `Lazy<WakeWordDetector>` object (instead of the shorter
    // "by lazy { ... }" property syntax) so that onDestroy() can later ask
    // "has this actually been created yet?" via wakeWordDetectorLazy.isInitialized() WITHOUT
    // forcing creation just to check. With the shorthand "by lazy" syntax there is no way to
    // peek at a member property from outside without triggering it on first read.
    private val wakeWordDetectorLazy: Lazy<WakeWordDetector> = lazy {
        WakeWordDetector(this, picovoiceAccessKey)
    }
    // "by wakeWordDetectorLazy" delegates reads of wakeWordDetector to the Lazy object above —
    // the first read runs the initializer block and caches the result; every later read just
    // returns the cached WakeWordDetector instance.
    private val wakeWordDetector: WakeWordDetector by wakeWordDetectorLazy

    // ── Activity lifecycle ──────────────────────────────────────
    // onCreate() is called when Android first creates the activity (the app starts or resumes).
    override fun onCreate(savedInstanceState: Bundle?) {
        // Always call the parent class's onCreate first — it sets up the activity framework.
        super.onCreate(savedInstanceState)

        // Request microphone permission from the user (required on Android 6.0+ for audio recording).
        requestMicrophonePermission()

        // Load whatever conversation history was saved from a previous run, if any, so context
        // survives an app restart instead of always starting from an empty list (see
        // loadConversationHistory() below, and desktop's identical load-on-startup behavior).
        conversationHistory = loadConversationHistory()

        // Initialize the Text-to-Speech engine. The lambda (callback) runs when TTS is ready.
        tts = TextToSpeech(this) { status ->
            // If TTS initialized successfully (status == SUCCESS), configure its language.
            if (status == TextToSpeech.SUCCESS) {
                // Set the TTS language to US English so it speaks with an American accent.
                tts?.language = Locale.US
            }
            // If TTS failed to initialize, tts will remain null and we just won't have speech output.
        }

        // Set up the Compose UI — this tells Android that the UI is defined by Compose functions.
        setContent {
            // Apply the app's custom color theme to everything inside.
            MakeItSoTheme {
                // Render the main screen layout, passing in the state, response, and action text.
                MakeItSoScreen(
                    // Current status text to display (e.g., "Listening...").
                    state = assistantState,
                    // The assistant's last spoken response text.
                    response = lastResponse,
                    // Description of the last executed action.
                    action = lastAction,
                    // Callback function: when the user taps the button, start the assistant cycle.
                    onStartListening = { startAssistant() }
                )
            }
        }
    }
    // End of onCreate().

    // Called when the activity is being destroyed (user presses back, system kills app, etc.).
    override fun onDestroy() {
        // Cancel ALL coroutines running under scope — stops background work cleanly.
        scope.cancel()
        // Stop any TTS speech that is currently playing.
        tts?.stop()
        // Release all TTS resources (the engine, audio focus, etc.).
        tts?.shutdown()
        // wakeWordDetector is created lazily (see the property declaration above), which means
        // the object isn't actually built until the FIRST time something reads it. If the user
        // closes the app without ever tapping "Say 'Computer'" (so wakeWordDetector.detect()
        // was never called), then simply writing "wakeWordDetector.destroy()" here would itself
        // trigger that first read — creating a brand-new Porcupine engine (loading its native
        // model files) for the sole purpose of immediately destroying it again. That's wasted
        // work during shutdown. isInitialized() on the Lazy object lets us check whether it was
        // already built WITHOUT triggering creation, so we only clean up what actually exists.
        if (wakeWordDetectorLazy.isInitialized()) {
            wakeWordDetector.destroy()
        }
        // Always call the parent class's onDestroy for proper cleanup.
        super.onDestroy()
    }
    // End of onDestroy().

    // ── Handle activity results (from speech recognition) ────────
    // This is called by Android when an activity that we started with
    // startActivityForResult() finishes (e.g., the speech recognition dialog).
    // We delegate to SpeechRecognizer.handleResult() which bridges the
    // result back to the coroutine that launched the recognizer.
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        // Always call the parent implementation first for standard Android behavior.
        super.onActivityResult(requestCode, resultCode, data)
        // Delegate to SpeechRecognizer which extracts the transcribed text
        // from the result and completes the pending coroutine.
        SpeechRecognizer.handleResult(requestCode, resultCode, data)
    }
    // End of onActivityResult().

    // ── Start the voice assistant ────────────────────────────────
    // This function launches the main assistant cycle in a background coroutine.
    private fun startAssistant() {
        // Re-entrancy guard: "isActive" on a Job is true only while that coroutine is still
        // running. If assistantJob is non-null AND still active, a cycle is already in
        // progress (e.g. the user double-tapped the button), so we ignore this extra tap
        // instead of starting a second overlapping cycle that would fight the first one for
        // the microphone. See the assistantJob property comment above for why that matters.
        if (assistantJob?.isActive == true) {
            return
        }
        // scope.launch starts a new coroutine that runs on the scope's dispatcher (Default thread pool)
        // and returns a Job handle for it, which we save so the guard above can check it next time.
        // This keeps the main UI thread free so the screen stays responsive.
        assistantJob = scope.launch {
            // Call the main assistant cycle function (which is a suspend function).
            runAssistantCycle()
        }
    }
    // End of startAssistant().

    // ── The main cycle: wake → listen → think → speak → act ─────
    // "suspend" means this function can be paused without blocking the thread.
    // This function's ONLY job is to run the six steps of one assistant interaction IN ORDER
    // and stop early if any step fails. Each step's actual work lives in its own small,
    // single-purpose function below (waitForWakeWord, listenForCommand, etc.) — that keeps this
    // orchestrating function readable as a simple top-to-bottom story, and makes each step easy
    // to understand (and fix) on its own.
    //
    // The "think" step now uses dual-mode processing:
    //   - Tries Claude API online first (requires internet + API key)
    //   - Falls back to Ollama on localhost:11434 if online fails
    //   - Mode is controlled by the assistantMode config variable
    private suspend fun runAssistantCycle() {
        // Wrap everything in try-catch so any unexpected error shows a message instead of crashing.
        try {
            // STEP 1: Wait for the wake word "Computer". Returns early (via the elvis "?:")
            // if it wasn't heard, so the rest of the cycle never runs.
            waitForWakeWord() ?: return

            // STEP 2: Play the Star Trek acknowledgment chime so the user knows they were heard.
            assistantState = "🔺 'Computer' detected!"
            playChime()

            // STEP 3: Listen for the user's spoken command. Returns early if nothing was heard.
            val speechText = listenForCommand() ?: return

            // STEP 4: Send the transcribed text to the assistant (Claude/Ollama) for processing.
            // Returns early if every provider failed.
            val result = thinkAboutCommand(speechText) ?: return

            // Record this exchange in conversation history BEFORE speaking/acting, mirroring
            // desktop's _record_exchange() — so even if a later step throws, the turn we already
            // got a response for is remembered on the next cycle.
            recordExchange(speechText, result.spokenText)

            // STEP 5: Speak the assistant's response aloud and show it on screen.
            speakResponse(result)

            // STEP 6: Execute any actions the assistant requested (open app, search web, etc.).
            executeActions(result.actions)

            // Done! Go back to waiting for the next wake word.
            assistantState = "✅ Complete. Say 'Computer' again."

        } catch (e: Exception) {
            // If ANY exception was thrown during Steps 1-6, show the error message on screen.
            assistantState = "Error: ${e.message}"
        }
        // End of try-catch block.
    }
    // End of runAssistantCycle().

    // ── Step 1: wait for the wake word ───────────────────────────
    // Updates the UI, then blocks (suspends) until wakeWordDetector hears "Computer" or gives
    // up. Returns Unit (a non-null placeholder value) on success so the caller can use
    // "?: return" to bail out on failure, or null if the wake word was never detected.
    private suspend fun waitForWakeWord(): Unit? {
        // Update the UI text to show we're listening for the wake word.
        assistantState = "🎤 Listening for 'Computer'..."
        // Call wakeWordDetector.detect() which listens for "Computer" and returns true/false.
        val wakeWordDetected = wakeWordDetector.detect()
        // If the wake word was NOT detected within the listening window...
        if (!wakeWordDetected) {
            // ...tell the user and signal failure to the caller.
            assistantState = "Wake word not detected. Try again."
            return null
        }
        // Signal success. Unit is Kotlin's "no meaningful value, but not null" type.
        return Unit
    }
    // End of waitForWakeWord().

    // ── Step 3: listen for the user's spoken command ─────────────
    // Updates the UI, then blocks until Android's speech recognizer returns transcribed text
    // (or null if nothing could be understood).
    private suspend fun listenForCommand(): String? {
        // Update the UI to show we're now listening for the actual command.
        assistantState = "🎧 Listening for your command..."
        // Call SpeechRecognizer.recognize() which returns transcribed text or null.
        val speechText = SpeechRecognizer.recognize(this)
        // If speech recognition failed or the user didn't say anything...
        if (speechText == null) {
            // ...show an error message so the caller's "?: return" bails out with the UI updated.
            assistantState = "Could not hear you. Try again."
        }
        return speechText
    }
    // End of listenForCommand().

    // ── Step 4: send the command to the assistant for processing ─
    // Updates the UI, then blocks until ClaudeService returns a result (or null if every
    // provider — online Claude and offline Ollama — failed).
    private suspend fun thinkAboutCommand(speechText: String): ClaudeResult? {
        // Update the UI to show the assistant is thinking.
        assistantState = "🧠 Thinking..."
        // Call ClaudeService.process() which sends the text to the configured provider.
        // The mode parameter controls the behavior:
        //   "auto"    → try Claude API online first, fall back to Ollama offline
        //   "online"  → use Claude API only
        //   "offline" → use Ollama locally only
        // The assistantMode is loaded from config (hardcoded to "auto" for now).
        // conversationHistory is passed through so the provider can see prior turns — see
        // ClaudeService.process()'s doc comment for how each provider uses it.
        val result = ClaudeService.process(speechText, assistantMode, conversationHistory)
        // If the assistant didn't respond (null means all providers failed)...
        if (result == null) {
            // ...show an error so the caller's "?: return" bails out with the UI updated.
            assistantState = "Assistant did not respond. Check network or start Ollama."
        }
        return result
    }
    // End of thinkAboutCommand().

    // ── Record this turn in conversation history, then persist it ─
    // Appends the user's speech and the assistant's spoken reply to conversationHistory (in the
    // same {role, content} shape ClaudeService expects back), trims it to the last
    // maxHistoryTurns entries, and saves it to disk immediately — mirroring desktop's
    // per-cycle save_conversation_history() call so a crash or force-quit between cycles
    // doesn't lose the conversation.
    private fun recordExchange(userText: String, spokenText: String) {
        conversationHistory.add(ConversationTurn("user", userText))
        // Assistant turns are stored as "RESPONSE: <spokenText>" to match the RESPONSE:/ACTIONS:
        // format the shared system prompt asks for — a replayed assistant turn then looks
        // exactly like a normal reply would, instead of a bare, format-less sentence.
        conversationHistory.add(ConversationTurn("assistant", "RESPONSE: $spokenText"))
        // Keep only the most recent maxHistoryTurns entries (list.takeLast() returns a new
        // list, so we reassign rather than mutate the old list "in place" from the front).
        if (conversationHistory.size > maxHistoryTurns) {
            conversationHistory = conversationHistory.takeLast(maxHistoryTurns).toMutableList()
        }
        saveConversationHistory(conversationHistory)
    }
    // End of recordExchange().

    // ── Load conversation history saved by a previous run, if any ─
    // Returns an empty list (rather than throwing) for every failure case — missing file,
    // unreadable file, corrupt JSON — since history is a nice-to-have, not something worth
    // crashing startup over. Mirrors desktop's load_conversation_history().
    private fun loadConversationHistory(): MutableList<ConversationTurn> {
        if (!historyFile.exists()) {
            return mutableListOf()
        }
        return try {
            val jsonArray = JSONArray(historyFile.readText())
            val turns = mutableListOf<ConversationTurn>()
            for (i in 0 until jsonArray.length()) {
                val entry = jsonArray.getJSONObject(i)
                turns.add(ConversationTurn(entry.getString("role"), entry.getString("content")))
            }
            turns
        } catch (e: Exception) {
            // Corrupt/unreadable history file — log and start fresh rather than crash.
            e.printStackTrace()
            mutableListOf()
        }
    }
    // End of loadConversationHistory().

    // ── Persist conversation history to disk ──────────────────────
    // Writes the current history as a JSON array of {"role", "content"} objects — the exact
    // shape loadConversationHistory() above reads back. Failures are logged, not raised: losing
    // the ability to persist history should never crash the assistant mid-conversation.
    private fun saveConversationHistory(history: List<ConversationTurn>) {
        try {
            val jsonArray = JSONArray()
            for (turn in history) {
                jsonArray.put(JSONObject().apply {
                    put("role", turn.role)
                    put("content", turn.content)
                })
            }
            historyFile.writeText(jsonArray.toString())
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }
    // End of saveConversationHistory().

    // ── Step 5: speak the assistant's response aloud ─────────────
    // Saves the response text to state (so Compose redraws the screen with it) and hands the
    // text to the Text-to-Speech engine so it's read aloud through the phone's speaker.
    private fun speakResponse(result: ClaudeResult) {
        // Save the spoken text to lastResponse so it appears on screen.
        lastResponse = result.spokenText
        // Use TTS to speak the text aloud. QUEUE_FLUSH means stop any current speech and start this one.
        tts?.speak(result.spokenText, TextToSpeech.QUEUE_FLUSH, null, null)
    }
    // End of speakResponse().

    // ── Step 6: execute any actions the assistant requested ──────
    // Loops through every Action the assistant asked for (there may be zero) and routes each
    // one to ActionRouter, updating the on-screen "last action" label as it goes.
    private fun executeActions(actions: List<Action>) {
        // Loop through each action in the list and execute them one by one.
        for (action in actions) {
            // Update the UI to show which action is being executed right now.
            lastAction = "Executing: ${action.type}"
            // Call ActionRouter.execute() to perform the action (open app, search web, etc.).
            // BUG FIX: "this" (the MainActivity itself, which IS a Context) must be passed
            // here. ActionRouter.execute()'s context parameter defaults to null when omitted,
            // and every branch inside ActionRouter only acts via a null-safe "context?.startActivity(...)"
            // call — so without passing "this", every single action (open_app, search_web,
            // send_sms, make_call) was silently doing NOTHING: the null-safe call short-circuits
            // and startActivity is never actually invoked. Passing "this" gives ActionRouter a
            // real Context so it can actually launch the browser, dialer, SMS app, etc.
            ActionRouter.execute(action, this)
        }
        // End of action loop. If actions was empty, this loop simply does nothing.
    }
    // End of executeActions().

    // ── Play the Star Trek chime ─────────────────────────────────
    // On Android, we use the device's media player. The chime is
    // stored in res/raw/computer_chime.wav (generated during build).
    private fun playChime() {
        // Wrap in try-catch in case the chime file doesn't exist yet.
        try {
            // MediaPlayer.create() loads the audio file from res/raw/ and prepares it for playback.
            val mediaPlayer = android.media.MediaPlayer.create(
                // "this" is the MainActivity context (needed to access resources).
                this,
                // R.raw.computer_chime is the generated resource ID for the chime WAV file.
                R.raw.computer_chime
            )
            // Start playing the chime audio through the phone's speaker.
            mediaPlayer?.start()
            // Set a listener: when the chime finishes playing, release the MediaPlayer resources.
            mediaPlayer?.setOnCompletionListener { it.release() }
        } catch (e: Exception) {
            // Chime file doesn't exist yet — that's OK, we'll
            // generate it later once the desktop version is done.
        }
        // End of try-catch.
    }
    // End of playChime().

    // ── Request microphone permission ───────────────────────────
    // On Android 6.0+ (API 23), dangerous permissions must be requested at runtime, not just at install time.
    private fun requestMicrophonePermission() {
        // Check if the RECORD_AUDIO permission has already been granted by the user.
        if (ContextCompat.checkSelfPermission(
                // "this" is the MainActivity context.
                this,
                // RECORD_AUDIO is the permission string for recording audio from the microphone.
                Manifest.permission.RECORD_AUDIO
                // Return value: PERMISSION_GRANTED (0) or PERMISSION_DENIED (-1).
            ) != PackageManager.PERMISSION_GRANTED
        ) {
            // If permission is NOT yet granted, show the system dialog asking the user to allow it.
            ActivityCompat.requestPermissions(
                // "this" is the MainActivity (needed to show the dialog).
                this,
                // An array of permissions to request (just RECORD_AUDIO in this case).
                arrayOf(Manifest.permission.RECORD_AUDIO),
                // 1001 is a request code — it's used in onRequestPermissionsResult() to identify which request this was.
                1001
            )
            // Android will show a system dialog; the result comes back via onRequestPermissionsResult().
        }
        // If permission is already granted, we do nothing — the app can already use the mic.
    }
    // End of requestMicrophonePermission().
}
// End of MainActivity class.

// ── Compose UI ─────────────────────────────────────────────────
// This is the actual screen layout using Jetpack Compose.

// @Composable marks a function as a UI-building block that can be composed into a screen.
// MakeItSoTheme wraps the app content in a Material Design color theme.
@Composable
fun MakeItSoTheme(content: @Composable () -> Unit) {
    // MaterialTheme() applies Material Design styling (colors, typography, shapes) to everything inside.
    MaterialTheme(
        // lightColorScheme() defines a set of colors for the "light" theme (as opposed to dark mode).
        colorScheme = lightColorScheme(
            // primary is the main brand color used for buttons, links, and active elements (deep indigo-blue).
            primary = androidx.compose.ui.graphics.Color(0xFF1A237E),
            // secondary is an accent color used for less prominent elements (slightly lighter indigo).
            secondary = androidx.compose.ui.graphics.Color(0xFF283593)
        )
    ) {
        // Call the content lambda — this renders whatever composables are nested inside MakeItSoTheme.
        content()
    }
    // End of MaterialTheme block.
}
// End of MakeItSoTheme.

// MakeItSoScreen is the actual UI layout — a column of text, buttons, and cards centered on screen.
@Composable
fun MakeItSoScreen(
    // state: the current status text to display (e.g., "Listening for 'Computer'...").
    state: String,
    // response: the assistant's last spoken response (shown in a card).
    response: String,
    // action: description of the last action executed.
    action: String,
    // onStartListening: a callback function invoked when the user taps the "Say 'Computer'" button.
    onStartListening: () -> Unit
) {
    // Column arranges its children vertically, one on top of another (like a vertical flexbox).
    Column(
        // Modifier decorates the Column — fillMaxSize() makes it take up the entire screen.
        modifier = Modifier
            .fillMaxSize()
            // Add 24dp of padding on all sides so content doesn't touch the screen edges.
            .padding(24.dp),
        // Center children horizontally within the column.
        horizontalAlignment = Alignment.CenterHorizontally,
        // Center children vertically within the column.
        verticalArrangement = Arrangement.Center
    ) {
        // ── Title ─────────────────────────────────────────────
        // Text() renders a string on screen with the given style.
        Text(
            // The app title displayed at the top of the screen.
            text = "🖖 Make It So",
            // headlineLarge is a large, bold text style from the Material Design typography system.
            style = MaterialTheme.typography.headlineLarge
        )

        // Spacer adds an empty gap of 16dp between the title and the next element.
        Spacer(modifier = Modifier.height(16.dp))

        // ── Current state ─────────────────────────────────────
        // Display the current status of the assistant (listening, thinking, etc.).
        Text(
            // The state string (e.g., "🎤 Listening for 'Computer'...").
            text = state,
            // bodyLarge is the standard paragraph text style.
            style = MaterialTheme.typography.bodyLarge
        )

        // Add 24dp of space before the button.
        Spacer(modifier = Modifier.height(24.dp))

        // ── Start button ──────────────────────────────────────
        // Button() is a Material Design raised button that the user can tap.
        Button(onClick = onStartListening) {
            // The text label displayed inside the button.
            Text("Say 'Computer'")
        }

        // Add 24dp of space before the assistant's response card.
        Spacer(modifier = Modifier.height(24.dp))

        // ── Assistant's last response ─────────────────────────
        // Only show the response card if there IS a response to show.
        if (response.isNotEmpty()) {
            // Card() is a Material Design elevated container with rounded corners.
            Card(
                // Make the card stretch to fill the full width of the column.
                modifier = Modifier.fillMaxWidth()
            ) {
                // Label above the response text.
                Text(
                    // Descriptive label for what this card contains.
                    text = "Assistant says:",
                    // labelMedium is a small, uppercase-style label text.
                    style = MaterialTheme.typography.labelMedium,
                    // Add 8dp padding on the top and left so text isn't flush against the card edge.
                    modifier = Modifier.padding(top = 8.dp, start = 8.dp)
                )
                // The actual response text from the assistant.
                Text(
                    // The assistant's spoken response text.
                    text = response,
                    // bodyMedium is the standard body text size.
                    style = MaterialTheme.typography.bodyMedium,
                    // 8dp padding on all sides for readability inside the card.
                    modifier = Modifier.padding(8.dp)
                )
            }
            // End of Card.
        }
        // End of response check.

        // Add 8dp of space before the action text.
        Spacer(modifier = Modifier.height(8.dp))

        // ── Last action executed ──────────────────────────────
        // Only show the action text if there IS an action to display.
        if (action.isNotEmpty()) {
            Text(
                // The action description (e.g., "Executing: search_web").
                text = "Action: $action",
                // bodySmall is a smaller, secondary text style.
                style = MaterialTheme.typography.bodySmall
            )
        }
        // End of action check.
    }
    // End of Column.
}
// End of MakeItSoScreen.
