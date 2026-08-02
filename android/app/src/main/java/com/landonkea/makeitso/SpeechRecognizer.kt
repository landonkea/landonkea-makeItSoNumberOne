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
//
// COROUTINE BRIDGE
// ----------------
// Android's speech recognition is callback-based (onActivityResult).
// We bridge this to coroutines using CompletableDeferred:
//   1. recognize() stores a CompletableDeferred in pendingRequests
//   2. It starts the recognition intent
//   3. When onActivityResult fires, handleResult() completes the deferred
//   4. recognize() resumes with the transcribed text
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
// withContext lets a coroutine switch which thread pool it runs on.
import kotlinx.coroutines.withContext
// Locale represents a language/region pair (e.g., en_US) used to set the speech recognizer's language.
import java.util.Locale
// CompletableDeferred is a one-shot value carrier that can be completed from outside a coroutine,
// used to bridge callback-based APIs (like onActivityResult) with coroutine code.
import kotlinx.coroutines.CompletableDeferred
// ConcurrentHashMap is a thread-safe map used to store pending recognition requests
// by their request code so onActivityResult can find and complete them.
import java.util.concurrent.ConcurrentHashMap

// "object" creates a singleton — exactly one SpeechRecognizer instance exists for the whole app.
// It wraps Android's speech recognition in a clean, coroutine-friendly function.
object SpeechRecognizer {

    // ── Pending request storage ────────────────────────────────────
    // This map bridges the callback-based onActivityResult to coroutines.
    // Key:   the request code (e.g., 2000) used in startActivityForResult
    // Value: a CompletableDeferred that will be completed when the result arrives
    // ConcurrentHashMap ensures thread safety since onActivityResult runs on the main thread
    // and the coroutine might be on a different thread.
    private val pendingRequests = ConcurrentHashMap<Int, CompletableDeferred<String?>>()

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
                // Build the Intent that tells Android what kind of speech recognition to run.
                // Extracted into its own function since "configure the recognition request" and
                // "bridge the callback-based result to a coroutine" (below) are two separate jobs.
                val intent = buildSpeechRecognitionIntent()

                // ── Create a one-shot bridge to the coroutine ────
                // CompletableDeferred is like a "promise" that can be
                // fulfilled exactly once from any thread. We store it
                // in the pendingRequests map so onActivityResult can
                // find it later and call .complete() with the result.
                val requestCode = 2000
                val deferred = CompletableDeferred<String?>()
                // Store the deferred in the map before starting the activity,
                // so there's no race condition between onActivityResult and this code.
                pendingRequests[requestCode] = deferred

                // Start the speech recognition activity. Android shows the mic dialog.
                activity.startActivityForResult(intent, requestCode)

                // Await the result. This suspends the coroutine until
                // handleResult() is called from onActivityResult.
                // If the activity is destroyed (e.g., user presses back),
                // the deferred will be cancelled and this throws.
                val result = deferred.await()

                // Remove the request from the map to avoid memory leaks.
                pendingRequests.remove(requestCode)

                // Return the transcribed text (or null if recognition failed).
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

    // ── Build the speech recognition Intent ──────────────────────
    // This function's ONLY job is to construct and configure the Intent that requests speech
    // recognition from Android — it does not start anything or wait for a result, which keeps
    // it separate from the coroutine-bridging logic in recognize() above.
    private fun buildSpeechRecognitionIntent(): Intent {
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
        // Return the fully configured intent, ready to be passed to startActivityForResult().
        return intent
    }
    // End of buildSpeechRecognitionIntent().

    // ── Handle the activity result ───────────────────────────────
    // This function should be called from the Activity's onActivityResult():
    //
    //   override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
    //       super.onActivityResult(requestCode, resultCode, data)
    //       SpeechRecognizer.handleResult(requestCode, resultCode, data)
    //   }
    //
    // It extracts the transcribed speech from the result Intent and
    // completes the pending CompletableDeferred, which un-pauses the
    // coroutine waiting in recognize().
    //
    // Parameters:
    //   requestCode: The code passed to startActivityForResult (should be 2000).
    //   resultCode:  Activity.RESULT_OK if recognition succeeded, RESULT_CANCELED if user backed out.
    //   data:        The Intent containing the transcribed speech results.
    fun handleResult(requestCode: Int, resultCode: Int, data: Intent?) {
        // Look up the pending deferred for this request code.
        val deferred = pendingRequests[requestCode] ?: return

        // Check if recognition was successful (user spoke and the recognizer got a result).
        if (resultCode == Activity.RESULT_OK && data != null) {
            // Extract the list of transcribed results from the Intent.
            // EXTRA_RESULTS is an ArrayList<String> sorted by confidence (best first).
            val results = data.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)
            // Get the most confident transcription, or null if the list is empty.
            val text = results?.firstOrNull()
            // Complete the deferred with the transcribed text (could be null if empty result).
            // This un-pauses the coroutine waiting in recognize().
            deferred.complete(text)
        } else {
            // Recognition was cancelled or failed (user pressed back, mic error, etc.).
            // Complete with null to signal to the caller that nothing was transcribed.
            deferred.complete(null)
        }
        // Clean up: remove the request from the map to prevent memory leaks.
        pendingRequests.remove(requestCode)
    }
    // End of handleResult().
}
// End of SpeechRecognizer object.
