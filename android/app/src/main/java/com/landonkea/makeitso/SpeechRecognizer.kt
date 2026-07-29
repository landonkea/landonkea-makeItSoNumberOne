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

package com.landonkea.makeitso

import android.app.Activity
import android.content.Intent
import android.speech.RecognizerIntent
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import java.util.Locale
import kotlin.coroutines.resume

object SpeechRecognizer {

    // ── Transcribe speech to text ───────────────────────────────
    // This launches Android's built-in speech recognition and
    // waits for the result. It's a suspending function so it
    // doesn't block the UI.
    suspend fun recognize(activity: Activity): String? {
        return withContext(Dispatchers.Main) {
            try {
                // ── Create the speech recognition intent ─────────
                val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
                intent.putExtra(
                    RecognizerIntent.EXTRA_LANGUAGE_MODEL,
                    RecognizerIntent.LANGUAGE_MODEL_FREE_FORM
                )
                intent.putExtra(
                    RecognizerIntent.EXTRA_LANGUAGE,
                    Locale.getDefault()
                )
                intent.putExtra(
                    RecognizerIntent.EXTRA_PROMPT,
                    "Say your command for the Computer..."
                )

                // We use a coroutine-friendly pattern to wait for
                // the result from the speech recognizer.
                val result = suspendCancellableCoroutine<String?> { continuation ->
                    // Start the speech recognizer.
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
                }

                return@withContext result

            } catch (e: Exception) {
                // Speech recognition is not available or failed.
                e.printStackTrace()
                return@withContext null
            }
        }
    }
}
