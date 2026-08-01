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
// and the pvporcupine AAR library for Android (already added to
// build.gradle.kts as a Maven Central dependency).
//
// ACCESS KEY SETUP
// ----------------
// 1. Go to https://console.picovoice.ai/ and sign up for free
// 2. Copy your AccessKey (starts with "tB/M/..." or similar)
// 3. Set it in app/build.gradle.kts -> PICOVOICE_ACCESS_KEY
//    OR pass it as a system property: -Dpicovoice.access.key=...
//
// The free tier allows unlimited wake word detection on-device.
// ───────────────────────────────────────────────────────────────────

// This line declares the package (namespace) this file belongs to.
package com.landonkea.makeitso

// ── Android system imports ────────────────────────────────────────
// Context gives access to the app's resources and assets — Porcupine
// needs it to load its native model from the APK.
import android.content.Context
// AudioRecord is the Android API for capturing raw audio frames
// from the microphone. We use it to feed PCM data to Porcupine.
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder

// ── Coroutine imports ─────────────────────────────────────────────
// Dispatchers provides thread pools — IO for audio capture work.
import kotlinx.coroutines.Dispatchers
// withContext lets us switch which coroutine dispatcher we run on.
import kotlinx.coroutines.withContext
// isActive lets us check whether the coroutine has been cancelled
// (e.g. the activity was destroyed) so we can stop reading the mic.
import kotlinx.coroutines.isActive

// ── Picovoice Porcupine import ────────────────────────────────────
// Porcupine is the on-device wake word detection engine.
// The library is provided by the porcupine-android AAR dependency.
import ai.picovoice.porcupine.Porcupine
// BuiltInKeyword lists the pre-built wake words that ship with
// Porcupine — we use "COMPUTER" (matching the desktop version).
import ai.picovoice.porcupine.Porcupine.BuiltInKeyword

// ── Callback interface ────────────────────────────────────────────
// Activities or fragments can implement this interface to receive
// wake word detection events asynchronously.
interface WakeWordCallback {
    // Called when "Computer" is detected (keywordIndex >= 0).
    fun onWakeWordDetected()
    // Called if Porcupine initialization or audio capture fails.
    fun onError(error: String)
}

// WakeWordDetector is now a CLASS (not a singleton object) because
// each instance holds its own Porcupine engine handle.
class WakeWordDetector(
    // The Android Context (application/activity) — Porcupine's Builder
    // needs it to load the native model bundled in the APK.
    private val context: Context,
    // The Picovoice Access Key from console.picovoice.ai.
    // If empty, the detector falls back to button-based activation
    // (detect() returns true immediately).
    private val picovoiceAccessKey: String
) {

    // ── Porcupine engine instance ──────────────────────────────────
    // This is the wake word detection engine. It's created during
    // init (see below) and released in destroy(). It's nullable so
    // we can handle the case where the access key is empty or
    // Porcupine fails to initialize.
    private var porcupine: Porcupine? = null

    // ── Initialization block ───────────────────────────────────────
    // Runs when the class is instantiated (constructor is called).
    // We create the Porcupine engine here so it's ready to detect.
    init {
        // Only try to initialize Porcupine if we have an access key.
        if (picovoiceAccessKey.isNotEmpty()) {
            try {
                // Porcupine 3.x uses a Builder pattern. We configure it
                // with our access key and the built-in "computer"
                // keyword, then build() loads the native engine.
                porcupine = Porcupine.Builder()
                    // The API key from console.picovoice.ai.
                    .setAccessKey(picovoiceAccessKey)
                    // The wake word to listen for. COMPUTER is one of
                    // the built-in keywords that ships with the
                    // library (no custom PPn model file needed).
                    .setKeyword(BuiltInKeyword.COMPUTER)
                    // Requires a Context to load the native model
                    // files from the APK's assets.
                    .build(context)
            } catch (e: Exception) {
                // If Porcupine fails to init (bad key, no native libs,
                // etc.), we log the error and fall back to button mode.
                e.printStackTrace()
            }
        }
        // If picovoiceAccessKey is empty, porcupine stays null and
        // detect() will fall back to returning true immediately.
    }

    // ── Cleanup ────────────────────────────────────────────────────
    // Releases the Porcupine engine's native resources.
    // Call this from your activity's onDestroy() or when you no
    // longer need wake word detection.
    fun destroy() {
        // delete() releases Porcupine's native memory (model, etc.).
        porcupine?.delete()
        // Null out the reference so it can't be used accidentally.
        porcupine = null
    }

    // ── Wake word detection ────────────────────────────────────────
    // This is a SUSPEND function (runs on a background thread via
    // Dispatchers.IO). It listens to the microphone until "Computer"
    // is detected, then returns true.
    //
    // If no Porcupine engine is available (no access key or init
    // failed), it immediately returns true (button-based fallback).
    suspend fun detect(): Boolean = withContext(Dispatchers.IO) {
        // ── Check if Porcupine is ready ────────────────────────────
        val engine = porcupine
        // If Porcupine is null (no key or init failed), fall back to
        // button-based activation: return true immediately so the
        // UI button still works as a manual trigger.
        if (engine == null) {
            return@withContext true
        }

        // ── Real Porcupine wake word detection ─────────────────────
        // Declared outside the try block (and nullable) so the
        // `finally` below can always reach it to release the mic,
        // even if construction or reading throws partway through.
        var audioRecord: AudioRecord? = null
        try {
            // Porcupine records at 16 kHz (sampleRate = 16000).
            val sampleRate = engine.sampleRate
            // Each audio frame is a fixed number of PCM samples.
            val frameLength = engine.frameLength
            // Buffer to hold one frame of 16-bit PCM audio samples.
            val buffer = ShortArray(frameLength)

            // Calculate the minimum buffer size Android's AudioRecord
            // needs for stable capture at this sample rate/format.
            val minBufferSize = AudioRecord.getMinBufferSize(
                sampleRate,
                AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT
            )
            // Use at least frameLength * 2 bytes (one frame of shorts)
            // but honor the platform's minimum if it's larger.
            val bufferSize = maxOf(frameLength * 2, minBufferSize)

            // ── Create the AudioRecord instance ────────────────────
            // This opens the device's microphone for raw PCM capture.
            val record = AudioRecord(
                // MIC is the built-in phone microphone.
                MediaRecorder.AudioSource.MIC,
                // Must match Porcupine's sample rate (16000 Hz).
                sampleRate,
                // Porcupine expects mono audio (single channel).
                AudioFormat.CHANNEL_IN_MONO,
                // Porcupine expects 16-bit signed little-endian PCM.
                AudioFormat.ENCODING_PCM_16BIT,
                // Total buffer size in bytes (2 bytes per sample).
                bufferSize
            )
            audioRecord = record

            // ── Start capturing audio from the microphone ──────────
            record.startRecording()

            // ── Read and process audio frames in a loop ────────────
            // audioRecord.read() fills the buffer with PCM samples
            // and returns the number of shorts read (or negative on
            // error). We keep reading until Porcupine finds the
            // wake word. `isActive` is also checked so that if the
            // activity is destroyed (coroutine cancelled) while we're
            // mid-read, we stop promptly instead of holding the mic
            // open until a wake word or read error eventually occurs.
            while (isActive && record.read(buffer, 0, buffer.size) >= 0) {
                // Pass the audio frame to Porcupine. It returns the
                // index of the detected keyword (0 for the first
                // keyword in the set) or -1 if no keyword found.
                val keywordIndex = engine.process(buffer)
                // If keywordIndex >= 0, "Computer" was detected!
                if (keywordIndex >= 0) {
                    // Return true — wake word was spoken. The mic is
                    // released in `finally` below either way.
                    return@withContext true
                }
            }

            // Loop exited without detection (cancelled or read error).
            return@withContext false

        } catch (e: Exception) {
            // Log the error to Logcat for debugging.
            e.printStackTrace()
            // Return false so the caller knows detection failed.
            return@withContext false
        } finally {
            // Always stop and release the microphone here — whether
            // we returned true, false, or hit an exception above.
            // Previously this cleanup only ran on the "happy paths",
            // so an exception mid-read (or cancellation) would leak
            // the AudioRecord and leave the mic locked.
            audioRecord?.let {
                try {
                    it.stop()
                } catch (e: Exception) {
                    // stop() throws if recording never actually
                    // started — safe to ignore, we're releasing anyway.
                }
                it.release()
            }
        }
    }
}
