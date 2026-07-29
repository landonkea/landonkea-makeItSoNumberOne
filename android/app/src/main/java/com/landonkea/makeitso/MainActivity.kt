// ───────────────────────────────────────────────────────────────────
// MainActivity.kt — the app's main screen (Android)
// ───────────────────────────────────────────────────────────────────
// This is the first screen that shows when the user opens the app.
// It shows:
//   1. The current state of the assistant (listening/processing/idle)
//   2. A button to manually trigger the wake word detection
//   3. Claude's spoken response (as text on screen)
//   4. Any actions that were executed
//
// The main logic (wake word → listen → Claude → speak → act) runs
// in a background coroutine so the UI stays responsive.
// ───────────────────────────────────────────────────────────────────

package com.landonkea.makeitso

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import android.speech.tts.TextToSpeech
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import kotlinx.coroutines.*
import java.util.Locale

class MainActivity : ComponentActivity() {

    // ── State variables ─────────────────────────────────────────
    // These are displayed on the screen and update automatically
    // when changed (Jetpack Compose "recomposes" the UI).

    // What is the assistant doing right now?
    private var assistantState by mutableStateOf("Say \"Computer\" to start")

    // Claude's last spoken response (shown as text).
    private var lastResponse by mutableStateOf("")

    // The last action that was executed.
    private var lastAction by mutableStateOf("")

    // Controls the background work (can be cancelled).
    private val scope = CoroutineScope(Dispatchers.Default + SupervisorJob())

    // Text-to-Speech engine (Android's built-in TTS).
    private var tts: TextToSpeech? = null

    // ── Activity lifecycle ──────────────────────────────────────
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Request microphone permission (required on Android 6+).
        requestMicrophonePermission()

        // Initialize the Text-to-Speech engine.
        tts = TextToSpeech(this) { status ->
            if (status == TextToSpeech.SUCCESS) {
                tts?.language = Locale.US
            }
        }

        // Set up the Compose UI (the screen layout).
        setContent {
            MakeItSoTheme {
                MakeItSoScreen(
                    state = assistantState,
                    response = lastResponse,
                    action = lastAction,
                    onStartListening = { startAssistant() }
                )
            }
        }
    }

    // Called when the app is destroyed (user closes it).
    override fun onDestroy() {
        // Stop the background work so it doesn't keep running.
        scope.cancel()
        // Release the TTS engine.
        tts?.stop()
        tts?.shutdown()
        super.onDestroy()
    }

    // ── Start the voice assistant ────────────────────────────────
    private fun startAssistant() {
        // Run in a background coroutine (not on the UI thread,
        // because mic and network access are slow).
        scope.launch {
            runAssistantCycle()
        }
    }

    // ── The main cycle: wake → listen → think → speak → act ─────
    private suspend fun runAssistantCycle() {
        try {
            // STEP 1: Wait for the wake word "Computer".
            assistantState = "🎤 Listening for 'Computer'..."
            val wakeWordDetected = WakeWordDetector.detect(this)
            if (!wakeWordDetected) {
                assistantState = "Wake word not detected. Try again."
                return
            }

            // STEP 2: Play the Star Trek acknowledgment chime.
            assistantState = "🔺 'Computer' detected!"
            playChime()

            // STEP 3: Listen for the user's command.
            assistantState = "🎧 Listening for your command..."
            val speechText = SpeechRecognizer.recognize(this)
            if (speechText == null) {
                assistantState = "Could not hear you. Try again."
                return
            }

            // STEP 4: Send to Claude for processing.
            assistantState = "🧠 Thinking..."
            val result = ClaudeService.process(speechText)
            if (result == null) {
                assistantState = "Claude did not respond."
                return
            }

            // STEP 5: Speak Claude's response aloud.
            lastResponse = result.spokenText
            tts?.speak(result.spokenText, TextToSpeech.QUEUE_FLUSH, null, null)

            // STEP 6: Execute any actions Claude requested.
            if (result.actions.isNotEmpty()) {
                for (action in result.actions) {
                    lastAction = "Executing: ${action.action}"
                    ActionRouter.execute(action)
                }
            }

            // Done! Go back to waiting.
            assistantState = "✅ Complete. Say 'Computer' again."

        } catch (e: Exception) {
            assistantState = "Error: ${e.message}"
        }
    }

    // ── Play the Star Trek chime ─────────────────────────────────
    // On Android, we use the device's media player. The chime is
    // stored in res/raw/computer_chime.wav (generated during build).
    private fun playChime() {
        try {
            val mediaPlayer = android.media.MediaPlayer.create(
                this,
                R.raw.computer_chime
            )
            mediaPlayer?.start()
            // Release resources when done playing.
            mediaPlayer?.setOnCompletionListener { it.release() }
        } catch (e: Exception) {
            // Chime file doesn't exist yet — that's OK, we'll
            // generate it later once the desktop version is done.
        }
    }

    // ── Request microphone permission ───────────────────────────
    private fun requestMicrophonePermission() {
        if (ContextCompat.checkSelfPermission(
                this, Manifest.permission.RECORD_AUDIO
            ) != PackageManager.PERMISSION_GRANTED
        ) {
            ActivityCompat.requestPermissions(
                this,
                arrayOf(Manifest.permission.RECORD_AUDIO),
                1001  // Request code (any number, used for tracking).
            )
        }
    }
}

// ── Compose UI ─────────────────────────────────────────────────
// This is the actual screen layout using Jetpack Compose.

@Composable
fun MakeItSoTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = lightColorScheme(
            primary = androidx.compose.ui.graphics.Color(0xFF1A237E),
            secondary = androidx.compose.ui.graphics.Color(0xFF283593)
        )
    ) {
        content()
    }
}

@Composable
fun MakeItSoScreen(
    state: String,
    response: String,
    action: String,
    onStartListening: () -> Unit
) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        // Title
        Text(
            text = "🖖 Make It So",
            style = MaterialTheme.typography.headlineLarge
        )

        Spacer(modifier = Modifier.height(16.dp))

        // Current state
        Text(
            text = state,
            style = MaterialTheme.typography.bodyLarge
        )

        Spacer(modifier = Modifier.height(24.dp))

        // Start button
        Button(onClick = onStartListening) {
            Text("Say 'Computer'")
        }

        Spacer(modifier = Modifier.height(24.dp))

        // Claude's last response
        if (response.isNotEmpty()) {
            Card(
                modifier = Modifier.fillMaxWidth()
            ) {
                Text(
                    text = "Claude says:",
                    style = MaterialTheme.typography.labelMedium,
                    modifier = Modifier.padding(top = 8.dp, start = 8.dp)
                )
                Text(
                    text = response,
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.padding(8.dp)
                )
            }
        }

        Spacer(modifier = Modifier.height(8.dp))

        // Last action executed
        if (action.isNotEmpty()) {
            Text(
                text = "Action: $action",
                style = MaterialTheme.typography.bodySmall
            )
        }
    }
}
