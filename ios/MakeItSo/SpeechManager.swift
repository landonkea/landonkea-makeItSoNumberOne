// ─── SpeechManager.swift ─────────────────────────────────────────────
// This file handles converting the user's spoken words into text (speech
// recognition). It uses SFSpeechRecognizer — Apple's built-in speech
// recognition engine, the same one that powers Siri.
//
// HOW IT WORKS:
//   1. We set up an audio engine that captures sound from the microphone.
//   2. We feed that audio into Apple's speech recognizer.
//   3. The recognizer sends back transcribed text as the user speaks.
//   4. When the user stops speaking (pauses), we return the final text.
//
// The recognition can happen on-device (offline) for basic accuracy, or
// use Apple's servers for better results. This code supports both.
//
// FUTURE ENHANCEMENT — OFFLINE VOSK STT:
//   Even though Apple's speech recognizer can work offline, a dedicated
//   offline engine like Vosk (https://alphacephei.com/vosk/) could be
//   added as an alternative for users who want:
//     - Complete privacy (no audio ever leaves the device)
//     - No dependency on Apple's servers at all
//     - Custom vocabulary for Star Trek commands
//   Vosk runs entirely on-device with small (~50MB) language model files.
//   To integrate it, you'd replace or augment the existing recognize()
//   function to call the Vosk Objective-C/Swift bindings instead of (or
//   as a fallback from) SFSpeechRecognizer.
// ──────────────────────────────────────────────────────────────────────

// Import Foundation — gives us basic Swift types and utilities like
// String, optional handling, and async support. We need this for the
// core language features used throughout this file.
import Foundation
// Import Speech — this gives us SFSpeechRecognizer and related classes
// for converting audio into text. This is Apple's speech recognition
// framework, separate from the audio capture framework (AVFoundation).
// On macOS (for testing/compilation), Speech is available but
// AVAudioSession (used for configuring microphone input) is not.
// We use `os(iOS)` to gate the full implementation.
#if os(iOS)
import Speech
#endif
// Import AVFoundation — this gives us AVAudioEngine, which we use to
// capture audio from the microphone and feed it to the speech recognizer.
// AVFoundation is Apple's main framework for working with audio/video.
import AVFoundation

// Define the SpeechManager class. It extends NSObject (a base class from
// Apple's Objective-C runtime). On iOS, it also conforms to the
// SFSpeechRecognizerDelegate protocol (added via extension below).
// Extending NSObject is required for delegate patterns in Apple's
// frameworks. The delegate protocol lets us receive events from the speech
// recognizer (like availability changes).
class SpeechManager: NSObject {
    // Create a single shared instance that the whole app uses (singleton
    // pattern). `static` means this property belongs to the class itself,
    // not to any instance. We use `shared` as a conventional name so other
    // code can access it as `SpeechManager.shared`.
    static let shared = SpeechManager()

    // ── iOS-only: Speech Recognition Properties ─────────────────
    // These properties use types from the Speech framework, which is
    // only available on Apple platforms that support speech recognition.
    // On macOS (for compilation testing), these are excluded.
    #if os(iOS)
    // Create the speech recognizer for US English. SFSpeechRecognizer is
    // Apple's class that converts audio to text. We specify "en-US" locale
    // so it expects American English. `private let` means it's a constant
    // that only this class can access. The `?` makes it optional because
    // not all devices support all locales.
    private let speechRecognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US"))
    // This object represents a recognition request — it buffers incoming
    // audio and sends it to the recognizer. It's optional because we only
    // create it when recognition is active. It starts nil (no request yet).
    private var recognitionRequest: SFSpeechAudioBufferRecognitionRequest?
    // This tracks the current recognition task — the actual in-progress
    // recognition operation. We need to keep a reference to it so we can
    // cancel it if needed. It's optional because there isn't always an
    // active task.
    private var recognitionTask: SFSpeechRecognitionTask?
    // The audio engine that captures microphone input. AVAudioEngine is
    // Apple's class for routing audio through a processing graph. We use
    // it to get raw audio from the mic and send it to the recognition
    // request. This is not optional because we always have the engine
    // ready (though it's not always running).
    private let audioEngine = AVAudioEngine()

    // The main function that listens to the microphone and returns the
    // transcribed text. It's `async` because it waits for the user to
    // speak before returning. It returns an optional String (nil if
    // recognition failed). The `->` arrow indicates the return type.
    func recognize() async -> String? {
        // Check that the speech recognizer exists AND is available on
        // this device. `guard let` unwraps the optional — if speechRecognizer
        // is nil or not available, we enter the else body and return nil.
        // `.isAvailable` checks if the recognizer can currently process audio
        // (it might be disabled by parental controls or other restrictions).
        guard let recognizer = speechRecognizer, recognizer.isAvailable else {
            // Print a message explaining why recognition won't work.
            print("Speech recognition not available on this device.")
            // Return nil to indicate failure — the caller will handle it.
            return nil
        }
        // Close the guard else block.

        // Ask for user authorization if we haven't already. iOS requires
        // the user to explicitly allow speech recognition. This function
        // (which we defined as an extension below) shows the permission
        // dialog if needed and returns true if authorized. The `await`
        // pauses until the user responds to the dialog.
        let authorized = await SFSpeechRecognizer.requestAuthorizationAsync()
        // If the user denied permission, we can't recognize speech.
        guard authorized else {
            // Log the denial for debugging purposes.
            print("Speech recognition not authorized.")
            // Return nil — without permission, we can't listen.
            return nil
        }
        // Close the guard else block.

        // Use `withCheckedContinuation` to bridge the old callback-based
        // speech recognition API with Swift's modern async/await pattern.
        // This creates a way to "pause" this async function and "resume"
        // it later when the recognition finishes. The closure receives a
        // `continuation` object that we call `.resume()` on when done.
        return await withCheckedContinuation { continuation in
            // Get the shared audio session (the system-wide audio manager).
            // This controls how audio input/output behaves on the device.
            let audioSession = AVAudioSession.sharedInstance()
            // Try to configure the audio session — this might fail if
            // another app is using the microphone (like a phone call).
            do {
                // Set the audio session category to `.record` — this tells
                // iOS we want to capture audio (not play it). `.default`
                // mode means standard recording settings. This is different
                // from `.playback` which is for playing sounds out loud.
                try audioSession.setCategory(.record, mode: .default)
                // Activate the audio session. `.notifyOthersOnDeactivation`
                // tells iOS to let other apps know we're taking over the
                // microphone. This ensures phone calls, music, etc. pause.
                try audioSession.setActive(true, options: .notifyOthersOnDeactivation)
                // Close the do block — no errors so far.
            }
            // Catch any errors from configuring the audio session.
            catch {
                // Print the error so we can debug audio session issues.
                print("Audio session error: \(error)")
                // Resume the continuation with nil (failure) so the async
                // function returns nil to the caller.
                continuation.resume(returning: nil)
                // Exit the function early since audio setup failed.
                return
            }
            // Close the catch block.

            // Create a new recognition request. This object receives audio
            // buffers and streams them to Apple's recognition engine. It's
            // audio-buffer-based because we're feeding live mic audio.
            recognitionRequest = SFSpeechAudioBufferRecognitionRequest()
            // Unwrap the newly created request. Even though we just set it,
            // we use guard to safely unwrap it (defensive programming).
            guard let recognitionRequest = recognitionRequest else {
                // If for some reason the request is nil, resume with nil.
                continuation.resume(returning: nil)
                // Exit the function — we can't proceed without a request.
                return
            }
            // Close the guard else block.

            // Configure the request to report partial (in-progress) results.
            // When true, the recognizer gives us updates as the user speaks,
            // not just the final result. This lets us show live transcription
            // if we wanted to. For now, we only use the final result.
            recognitionRequest.shouldReportPartialResults = true

            // Create a variable to hold the final transcribed text. It's a
            // `var` (mutable) because it gets updated as recognition runs.
            // Starts as nil because we haven't received any text yet.
            var finalText: String?
            // Start the recognition task. This tells the recognizer to start
            // listening to the request's audio. The closure is called
            // repeatedly as the user speaks, providing partial results.
            recognitionTask = recognizer.recognitionTask(
                // Pass in the recognition request that receives audio buffers.
                with: recognitionRequest
                // The closure receives either a result (transcribed text) or
                // an error. Both are optionals — one might be nil.
            ) { result, error in
                // If we got a result (transcription), store the best version.
                // SFSpeechRecognitionResult contains multiple possible
                // transcriptions — `bestTranscription` is the most likely one.
                // `.formattedString` gives us the actual text string.
                if let result = result {
                    // Update our finalText variable with the latest and best
                    // transcription. As the user speaks more, this overwrites
                    // the previous version with a more complete one.
                    finalText = result.bestTranscription.formattedString
                }
                // Close the if block.

                // Check if there was an error OR the result is final (user
                // stopped speaking). The `??` (nil-coalescing) means "use
                // the value if not nil, otherwise use false". So if result
                // is nil, `isFinal` defaults to false, and the condition
                // only triggers if there's an actual error.
                if error != nil || (result?.isFinal ?? false) {
                    // Stop the audio engine — this stops capturing mic audio.
                    self.audioEngine.stop()
                    // Remove the "tap" (audio processing hook) from the mic
                    // input node. Bus 0 is the microphone input bus. This
                    // cleanup prevents memory leaks and frees the microphone.
                    self.audioEngine.inputNode.removeTap(onBus: 0)
                    // Release the recognition request — it's no longer needed
                    // since recognition is done. Setting to nil helps ARC
                    // (Automatic Reference Counting) free memory.
                    self.recognitionRequest = nil
                    // Release the recognition task reference. Also helps
                    // memory management by letting ARC clean up.
                    self.recognitionTask = nil

                    // Resume the continuation with the final transcribed text.
                    // This un-pauses the async function and returns the text
                    // to whoever called `recognize()`. If recognition failed
                    // (finalText is nil), the caller gets nil.
                    continuation.resume(returning: finalText)
                }
                // Close the if block that checks for completion/error.
            }
            // Close the recognitionTask closure.

            // Get the audio format (sample rate, channel count, etc.) that
            // the microphone is using. `inputNode` is the mic input, and
            // `outputFormat(forBus: 0)` tells us what format the audio data
            // comes in. We need this to configure our audio tap correctly.
            let recordingFormat = self.audioEngine.inputNode.outputFormat(forBus: 0)
            // Install a "tap" on the audio engine's input node. A tap is a
            // hook that receives chunks of audio data as they come in. We
            // forward these chunks to the speech recognizer.
            self.audioEngine.inputNode.installTap(
                // Bus 0 — the main microphone input channel.
                onBus: 0,
                // Buffer size — how much audio to capture at once. 1024
                // samples is a good balance between responsiveness and
                // performance. Smaller = more frequent updates, larger =
                // less CPU usage but more lag.
                bufferSize: 1024,
                // The audio format we're using (from the line above).
                format: recordingFormat
                // The closure receives each buffer of audio data. The second
                // parameter `_` (underscore) is the timestamp, which we ignore.
            ) { buffer, _ in
                // Append the audio buffer to the recognition request. This
                // feeds the mic audio into Apple's speech recognition engine.
                // The engine processes it and sends back transcribed text via
                // the recognitionTask closure above.
                self.recognitionRequest?.append(buffer)
                // Close the tap closure.
            }
            // Close the installTap function call.

            // Prepare the audio engine — this pre-allocates resources and
            // gets the engine ready to start. It doesn't start capturing
            // yet; that happens when we call .start(). Preparation reduces
            // the delay ("latency") when starting.
            self.audioEngine.prepare()
            // Try to start the audio engine. This actually begins capturing
            // audio from the microphone and feeding it through the tap we
            // installed above. It might fail (e.g., mic is already in use).
            do {
                // Start the engine — audio starts flowing to the recognizer.
                try self.audioEngine.start()
                // Close the do block on success.
            }
            // Catch any startup errors.
            catch {
                // Log what went wrong for debugging purposes.
                print("Audio engine couldn't start: \(error)")
                // Resume the continuation with nil (failure) so the caller
                // gets nil instead of hanging forever waiting for speech.
                continuation.resume(returning: nil)
            }
            // Close the catch block.
        }
        // Close the withCheckedContinuation block — this is where the
        // function "pauses" until continuation.resume() is called above.
    }
    // Close the recognize function.
    #else
    // ── macOS stub implementation ───────────────────────────────
    // On platforms without the Speech framework, we provide a stub
    // that returns a dummy command so the rest of the app compiles
    // and can be tested for syntax and logic errors.
    func recognize() async -> String? {
        // Log that speech is not available on this platform.
        print("SpeechManager.recognize() not available on this platform.")
        // Return a test string so the caller doesn't get nil.
        return "test command"
    }
    #endif
}

// ─── iOS-only: Delegate + Async Extensions ───────────────────────────
// These extensions require the Speech framework, so they're only
// compiled on iOS.
#if os(iOS)

// Add SFSpeechRecognizerDelegate conformance to SpeechManager.
// This lets us receive events from the speech recognizer, like
// availability changes.
extension SpeechManager: SFSpeechRecognizerDelegate {
}

// ─── Async Extension ─────────────────────────────────────────────────
// Add a new static function to SFSpeechRecognizer (Apple's class) that
// wraps the old callback-based authorization request in a modern async
// function. This makes it easier to use with async/await throughout our code.
extension SFSpeechRecognizer {
    // Define a new static function (called on the class itself, not an
    // instance) that returns a boolean (true if authorized, false if not).
    // The `async` keyword means it can pause while waiting for the user.
    static func requestAuthorizationAsync() async -> Bool {
        // Use `withCheckedContinuation` to bridge the callback-based
        // `requestAuthorization` API to the async/await pattern. The
        // function pauses here until we call continuation.resume().
        await withCheckedContinuation { continuation in
            // Call Apple's existing authorization request method. It shows
            // a dialog to the user asking "Allow this app to use speech
            // recognition?" The closure runs after the user responds.
            requestAuthorization { status in
                // Resume the continuation, passing true only if the user
                // granted authorization (status == .authorized). If they
                // denied or restricted it, we return false.
                continuation.resume(returning: status == .authorized)
                // Close the authorization closure.
            }
            // Close the requestAuthorization call.
        }
        // Close the withCheckedContinuation block.
    }
    // Close the requestAuthorizationAsync function.
}
// Close the extension block.

#endif