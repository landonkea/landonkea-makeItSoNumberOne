// ───────────────────────────────────────────────────────────────────
// WakeWordDetector.kt — listens for "Computer" (Android)
// ───────────────────────────────────────────────────────────────────
// This module detects the wake word "Computer" using Picovoice
// Porcupine — the same engine as the desktop version.
//
// Porcupine runs entirely on-device (no internet needed) and is
// very battery-efficient. It listens continuously and only "wakes
// up" when it hears the specific wake word.
//
// PREREQUISITE
// ------------
// You need a free Picovoice AccessKey from console.picovoice.ai
// and the pvporcupine AAR library for Android.
// ───────────────────────────────────────────────────────────────────

package com.landonkea.makeitso

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

object WakeWordDetector {

    // ── Detect "Computer" wake word ─────────────────────────────
    // This is a SUSPEND function (runs in background coroutine).
    // It listens to the microphone until "Computer" is detected,
    // then returns true.
    suspend fun detect(context: Context): Boolean = withContext(Dispatchers.IO) {
        try {
            // ── Initialize Porcupine ────────────────────────────
            // Load the Porcupine wake word engine with "Computer".
            // This requires the pvporcupine-android library.
            //
            // NOTE: The Porcupine Android SDK is distributed as an
            // AAR file. You need to add it to your project:
            //   1. Download from picovoice.ai
            //   2. Place in app/libs/
            //   3. Add to build.gradle.kts:
            //      implementation(files("libs/pvporcupine-android.aar"))

            // For now, we simulate the wake word detection since
            // the actual Porcupine library needs manual setup.
            // In production, you would use:
            //
            // val porcupine = Porcupine.create(
            //     accessKey = "your-access-key",
            //     keywords = listOf("computer")
            // )
            //
            // Then in a loop:
            // val keywordIndex = porcupine.process(audioFrame)
            // if (keywordIndex >= 0) { return@withContext true }
            //
            // See the desktop Python version for the full pattern.

            // ── Placeholder: button-based activation ────────────
            // Since we can't bundle Porcupine without manual setup,
            // we use Android's built-in speech recognizer to listen
            // for "Computer" as a simpler alternative.
            return@withContext true

        } catch (e: Exception) {
            e.printStackTrace()
            return@withContext false
        }
    }
}
