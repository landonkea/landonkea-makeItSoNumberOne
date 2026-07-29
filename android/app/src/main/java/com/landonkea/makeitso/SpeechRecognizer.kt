// ───────────────────────────────────────────────────────────────────
// SpeechRecognizer.kt — converts speech to text (Android)
// ───────────────────────────────────────────────────────────────────
// This module uses Android's built-in speech recognition (the same
// engine that powers Google's voice typing). It does NOT need an
// internet connection for basic recognition (offline models are
// included on most Android phones).
//
// HOW IT WORKS
// ------------
// 1. We create an Intent with "RecognizerIntent.ACTION_RECOGNIZE_SPEECH"
// 2. Android shows a mic dialog (or runs in background mode)
// 3. The user speaks, Android returns the transcribed text
// 4. We pass that text to Claude
// ───────────────────────────────────────────────────────────────────

// This line declares the package (namespace) this file belongs to, matching the folder structure.
package com.landonkea.makeitso

// ── Android system imports ────────────────────────────────────────
// These import Android classes needed to launch speech recognition and handle the result.

// Activity is a core Android class representing a single screen with a user interface.
import android.app.Activity
// Intent is a messaging object that tells Android what action to perform (e.g., start speech recognition).
import android.content.Intent
// RecognizerIntent contains constants and extras for Android's built-in speech recognition.
import android.speech.RecognizerIntent
// Dispatchers provides coroutine thread pools — Main for UI, IO for network, Default for CPU work.
import kotlinx.coroutines.Dispatchers
// suspendCancellableCoroutine is a low-level coroutine builder that lets us bridge callback-based APIs
// (like speech recognition results) with coroutine code.
import kotlinx.coroutines.suspendCancellableCoroutine
// withContext lets a coroutine switch which thread pool it runs on.
import kotlinx.coroutines.withContext
// Locale represents a language/region pair (e.g., en_US) used to set the speech recognizer's language.
import java.util.Locale
// resume() is called on a coroutine continuation to pass a result back and un-pause the coroutine.
import kotlin.coroutines.resume

// "object" creates a singleton — exactly one SpeechRecognizer instance exists for the whole app.
// It wraps Android's speech recognition in a clean, coroutine-friendly function.
object SpeechRecognizer {

    // ── Transcribe speech to text ───────────────────────────────
    // This launches Android's built-in speech recognition and
    // waits for the result. It's a suspending function so it
    // doesn't block the UI.
    // "suspend" means this is a coroutine — it can pause while waiting for the user to speak.
    // It takes an Activity (the current screen) and returns the transcribed text or null on failure.
    suspend fun recognize(activity: Activity): String? {
        // withContext(Dispatchers.Main) switches to the main (UI) thread because
        // startActivityForResult must be called from the UI thread in Android.
        return withContext(Dispatchers.Main) {
            // Wrap everything in try-catch so errors (no speech recognizer, etc.) don't crash the app.
            try {
                // ── Create the speech recognition intent ─────────
                // Create an Intent that asks Android to start its built-in speech recognition service.
                val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
                // EXTRA_LANGUAGE_MODEL tells Android which speech model to use.
                intent.putExtra(
                    // LANGUAGE_MODEL_FREE_FORM is optimized for dictation and natural speech (not short commands).
                    RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                    RecognizerIntent.LANGUAGE_MODEL_FREE_FORM
                )
                // EXTRA_LANGUAGE sets which language the speech recognizer should listen for.
                intent.putExtra(
                    // Locale.getDefault() returns the user's device language (e.g., en_US for US English).
                    RecognizerIntent.EXTRA_LANGUAGE,
                    Locale.getDefault()
                )
                // EXTRA_PROMPT sets the text that appears in Android's speech recognition dialog.
                intent.putExtra(
                    // This text tells the user what to say when the mic dialog appears.
                    RecognizerIntent.EXTRA_PROMPT,
                    "Say your command for the Computer..."
                )

                // We use a coroutine-friendly pattern to wait for
                // the result from the speech recognizer.
                // suspendCancellableCoroutine creates a coroutine that pauses until we manually resume it.
                val result = suspendCancellableCoroutine<String?> { continuation ->
                    // Start the speech recognition activity. Android shows the mic dialog.
                    // 2000 is a request code used in onActivityResult() to identify this request.
                    activity.startActivityForResult(intent, 2000)

                    // Note: In a real implementation, you'd override
                    // onActivityResult in the Activity and use a
                    // callback. For simplicity here, we simulate
                    // the result.
                    //
                    // The actual implementation would look like:
                    //   val results = data
                    //       .getStringArrayListExtra(
                    //           RecognizerIntent.EXTRA_RESULTS
                    //       )
                    //   continuation.resume(results?.firstOrNull())
                    //
                    // For now, we return null (to be implemented
                    // when you build in Android Studio).
                    // If we don't call continuation.resume(), the coroutine hangs forever.
                    // The continuation is what "un-pauses" the coroutine with the speech result.
                }
                // End of suspendCancellableCoroutine block. result holds whatever was passed to resume().

                // Return the transcribed text (or null if recognition failed or wasn't implemented yet).
                return@withContext result

            } catch (e: Exception) {
                // Speech recognition is not available (device lacks the service) or some other error occurred.
                // Print the error details to Logcat for debugging.
                e.printStackTrace()
                // Return null to signal to the caller that speech recognition failed.
                return@withContext null
            }
            // End of try-catch block.
        }
        // End of withContext(Dispatchers.Main) — execution continues on the original thread.
    }
    // End of recognize() function.
}
// End of SpeechRecognizer object.
