// ───────────────────────────────────────────────────────────────────
// SpeechManager.swift — converts speech to text (iOS)
// ───────────────────────────────────────────────────────────────────
// This module uses SFSpeechRecognizer — Apple's built-in speech
// recognition engine (same engine as Siri). It works offline and
// on-device for basic recognition, or uses Apple's servers for
// better accuracy.
//
// HOW IT WORKS
// ------------
// 1. SFSpeechRecognizer is initialized with the device's locale.
// 2. An SFSpeechAudioBufferRecognitionRequest is created to stream
//    audio from the microphone.
// 3. The recognitionTask callback receives transcribed text as the
//    user speaks.
// 4. We wait until the user stops speaking, then return the final
//    transcription.
// ───────────────────────────────────────────────────────────────────

import Foundation
import Speech
import AVFoundation

class SpeechManager: NSObject, SFSpeechRecognizerDelegate {
    // ── Singleton ───────────────────────────────────────────────
    // We use the singleton pattern so there's only one instance
    // of the speech recognizer shared across the app.
    static let shared = SpeechManager()

    // ── Properties ──────────────────────────────────────────────
    private let speechRecognizer = SFSpeechRecognizer(locale: Locale(identifier: "en-US"))
    private var recognitionRequest: SFSpeechAudioBufferRecognitionRequest?
    private var recognitionTask: SFSpeechRecognitionTask?
    private let audioEngine = AVAudioEngine()

    // ── Recognize speech from the microphone ────────────────────
    // This is an ASYNC function — it waits for the user to speak
    // and returns the transcribed text.
    func recognize() async -> String? {
        // Check if speech recognition is available on this device.
        guard let recognizer = speechRecognizer, recognizer.isAvailable else {
            print("Speech recognition not available on this device.")
            return nil
        }

        // Request authorization (if not already granted).
        let authorized = await SFSpeechRecognizer.requestAuthorizationAsync()
        guard authorized else {
            print("Speech recognition not authorized.")
            return nil
        }

        return await withCheckedContinuation { continuation in
            // Set up the audio session for recording.
            let audioSession = AVAudioSession.sharedInstance()
            do {
                try audioSession.setCategory(.record, mode: .default)
                try audioSession.setActive(true, options: .notifyOthersOnDeactivation)
            } catch {
                print("Audio session error: \(error)")
                continuation.resume(returning: nil)
                return
            }

            // Create the recognition request.
            recognitionRequest = SFSpeechAudioBufferRecognitionRequest()
            guard let recognitionRequest = recognitionRequest else {
                continuation.resume(returning: nil)
                return
            }

            // Configure the request for partial results (so we
            // can see text as the user speaks).
            recognitionRequest.shouldReportPartialResults = true

            // Start recognition.
            var finalText: String?
            recognitionTask = recognizer.recognitionTask(
                with: recognitionRequest
            ) { result, error in
                if let result = result {
                    // Update with the latest transcription.
                    finalText = result.bestTranscription.formattedString
                }

                if error != nil || (result?.isFinal ?? false) {
                    // Recognition finished or errored.
                    // Stop the audio engine and clean up.
                    self.audioEngine.stop()
                    self.audioEngine.inputNode.removeTap(onBus: 0)
                    self.recognitionRequest = nil
                    self.recognitionTask = nil

                    // Resume the continuation with the result.
                    continuation.resume(returning: finalText)
                }
            }

            // Configure the microphone input.
            let recordingFormat = self.audioEngine.inputNode.outputFormat(forBus: 0)
            self.audioEngine.inputNode.installTap(
                onBus: 0,
                bufferSize: 1024,
                format: recordingFormat
            ) { buffer, _ in
                self.recognitionRequest?.append(buffer)
            }

            // Start the audio engine.
            self.audioEngine.prepare()
            do {
                try self.audioEngine.start()
            } catch {
                print("Audio engine couldn't start: \(error)")
                continuation.resume(returning: nil)
            }
        }
    }
}

// ── Async extension for SFSpeechRecognizer authorization ───────
extension SFSpeechRecognizer {
    static func requestAuthorizationAsync() async -> Bool {
        await withCheckedContinuation { continuation in
            requestAuthorization { status in
                continuation.resume(returning: status == .authorized)
            }
        }
    }
}
