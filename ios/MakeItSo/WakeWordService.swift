// ─── WakeWordService.swift ─────────────────────────────────────────────
// This file provides hands-free wake word detection for the "Computer"
// keyword using Picovoice's Porcupine engine. Porcupine runs entirely
// on-device (no internet needed, no audio leaves the phone), detects
// the wake word in real time, and calls back when it's heard.
//
// Porcupine is a lightweight, on-device wake word engine that can run
// continuously with minimal battery impact. We use the built-in
// "Computer" keyword that comes with the free Picovoice Console account.
//
// HOW TO GET A PICOVOICE ACCESS KEY:
//   1. Go to https://console.picovoice.ai/
//   2. Sign up for a free account
//   3. Create an AccessKey in the console
//   4. Set the environment variable PICOVOICE_ACCESS_KEY in Xcode:
//      Edit Scheme → Run → Arguments → Environment Variables
//      Name: PICOVOICE_ACCESS_KEY   Value: <your key>
//
// USAGE:
//   let service = WakeWordService(accessKey: "...")
//   let heard = await service.detect()  // Blocks until "Computer" or error
//   service.destroy()                    // Clean up audio resources
// ──────────────────────────────────────────────────────────────────────

// Import Foundation for basic types like String, optional handling, and
// async support. We need this for the core language features.
import Foundation
// Import AVFoundation for audio session management. Even though Porcupine
// handles its own audio capture, we need AVFoundation types for basic
// audio functionality. This import is available on both iOS and macOS.
import AVFoundation

// On iOS only, import the Porcupine framework for wake word detection.
// The Porcupine SPM package only supports iOS (not macOS), so we gate
// all Porcupine-specific code with #if os(iOS). On macOS (for compilation
// testing), we provide a stub that always returns false.
#if os(iOS)
import Porcupine
#endif

// Define the WakeWordService class that wraps Porcupine's wake word
// detection in a simple async/await interface. Users create one instance,
// call detect() to wait for the wake word, and destroy() to clean up.
class WakeWordService {
    // Store the PorcupineManager instance that handles audio capture and
    // wake word detection. This is only available on iOS because the
    // Porcupine framework only supports iOS. On other platforms (macOS
    // for testing), we define a typealias stub instead.
    #if os(iOS)
    private var porcupineManager: PorcupineManager?
    #endif

    // Store the Picovoice access key that authenticates us to use the
    // Porcupine engine. This key is obtained from the Picovoice Console
    // at https://console.picovoice.ai/ and must be set as an environment
    // variable in the Xcode scheme. It's a constant (let) because we only
    // set it once during initialization and never change it.
    private let accessKey: String

    // Initialize the service with a Picovoice access key. The key is
    // required to use the Porcupine wake word engine. Without a valid
    // key, the detect() function will return false (detection skipped).
    // The accessKey is stored as a property so we can use it each time
    // detect() creates a new PorcupineManager instance.
    init(accessKey: String) {
        // Store the access key for later use by the PorcupineManager.
        // The key is a string that looks like a random character sequence
        // (e.g., "PICo..."). It's like a password that proves we have
        // a Picovoice account and are allowed to use the engine.
        self.accessKey = accessKey
    }

    // Listen for the "Computer" wake word and return true if detected.
    // This function:
    //   1. Creates a PorcupineManager with the built-in "Computer" keyword
    //   2. Starts audio capture through the device microphone
    //   3. Waits for Porcupine to detect the wake word
    //   4. Returns true when "Computer" is heard, false on error
    //
    // The function is async because it pauses until the wake word is
    // detected (or an error occurs). It returns Bool — true means we
    // heard "Computer", false means something went wrong (mic permission
    // denied, invalid access key, etc.).
    //
    // Each call creates a fresh PorcupineManager instance. This is
    // intentional — it ensures clean audio session setup each time and
    // avoids stale state from previous detection cycles. The previous
    // manager (if any) is destroyed at the start of this function.
    func detect() async -> Bool {
        // On iOS only, implement the actual Porcupine detection logic.
        // The Porcupine framework is not available on macOS, so we fall
        // back to the stub below.
        #if os(iOS)
        // Clean up any existing PorcupineManager before creating a new one.
        // This stops any ongoing audio capture and releases the microphone
        // so the new manager can start fresh. Without this, we'd have
        // stale audio state from the previous detection cycle.
        destroy()

        // Use Swift's withCheckedContinuation to bridge Porcupine's
        // callback-based API to Swift's modern async/await pattern.
        // The function "pauses" here and "resumes" when the wake word
        // is detected or an error occurs. The continuation object is
        // like a bookmark — we call .resume() on it to return control.
        return await withCheckedContinuation { continuation in
            // Wrap all Porcupine setup in a do-catch block because
            // PorcupineManager initializer and start() can throw errors
            // (invalid access key, microphone unavailable, etc.).
            do {
                // Create a PorcupineManager instance with the built-in
                // "Computer" keyword. This initializes Porcupine's audio
                // processing pipeline (loading the keyword model, preparing
                // the audio engine, etc.). It does NOT start capturing
                // audio yet — that happens when we call .start() below.
                //
                // PorcupineManager takes four parameters:
                //   1. accessKey — our Picovoice account key for auth
                //   2. keywords — an array of keywords to detect. We use
                //      [.computer] which is the built-in "Computer" keyword
                //   3. onDetection — callback when a keyword is heard
                //   4. errorHandler — callback if an error occurs
                let manager = try PorcupineManager(
                    accessKey: accessKey,
                    keywords: [PorcupineBuiltInKeyword.computer],
                    onDetection: { _ in
                        // The wake word was detected! Resume the
                        // continuation with true to unblock detect().
                        // The parameter (underscore) is the keyword index
                        // — since we only have one keyword, it's always 0.
                        continuation.resume(returning: true)
                    },
                    errorHandler: { error in
                        // An error occurred during detection (mic denied,
                        // audio session interrupted, etc.). Log it and
                        // resume with false so the caller knows detection
                        // failed and can decide whether to retry.
                        print("Porcupine error: \(error.localizedDescription)")
                        continuation.resume(returning: false)
                    }
                )

                // Store a strong reference to the manager so it doesn't
                // get deallocated while we're waiting for detection. The
                // old manager (if any) was already destroyed above via
                // destroy(), so this assignment is clean.
                porcupineManager = manager

                // Start audio capture and wake word detection. This
                // configures the audio session for recording, starts the
                // microphone, and begins feeding audio into Porcupine's
                // detection pipeline. The .start() call is synchronous
                // but audio processing happens on a background thread.
                try manager.start()
            } catch {
                // If PorcupineManager initialization or start() threw an
                // error (common: invalid access key, mic unavailable),
                // log it and resume with false so detect() returns.
                print("Failed to start Porcupine: \(error.localizedDescription)")
                continuation.resume(returning: false)
            }
        }
        #else
        // On non-iOS platforms (macOS for compilation testing), Porcupine
        // is not available. We print a message and return false so the
        // calling code knows wake word detection isn't supported here.
        print("WakeWordService.detect() not available on this platform.")
        return false
        #endif
    }

    // Clean up Porcupine resources — stop audio capture and release the
    // PorcupineManager instance. Call this when you're done detecting
    // (e.g., after detecting "Computer" and starting speech recognition)
    // to free the microphone for other uses (like SpeechManager).
    //
    // This is safe to call multiple times — subsequent calls are no-ops
    // once the manager is already stopped and set to nil.
    func destroy() {
        // On iOS, stop the PorcupineManager and release the reference.
        // On other platforms, there's nothing to clean up.
        #if os(iOS)
        // Stop the audio engine and detection. This tells Porcupine to
        // stop capturing audio from the microphone, deactivate the audio
        // session, and release any audio resources it was using.
        porcupineManager?.stop()
        // Release the manager instance. Setting to nil lets Swift's ARC
        // (Automatic Reference Counting) deallocate the manager and all
        // its associated memory (audio buffers, keyword models, etc.).
        porcupineManager = nil
        #endif
    }
}
