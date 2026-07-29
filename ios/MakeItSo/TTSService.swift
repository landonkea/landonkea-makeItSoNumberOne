// ───────────────────────────────────────────────────────────────────
// TTSService.swift — speaks text aloud (iOS)
// ───────────────────────────────────────────────────────────────────
// This module uses AVSpeechSynthesizer — Apple's built-in
// text-to-speech engine (same as VoiceOver). It works completely
// offline and supports many voices and languages.
//
// HOW IT WORKS
// ------------
// 1. Create an AVSpeechUtterance with the text to speak.
// 2. Set the voice (we use "Samantha" — clear and pleasant).
// 3. Speak it using AVSpeechSynthesizer.
// ───────────────────────────────────────────────────────────────────

import AVFoundation

class TTSService {
    // ── Singleton ──────────────────────────────────────────────
    static let shared = TTSService()

    // ── Properties ─────────────────────────────────────────────
    private let synthesizer = AVSpeechSynthesizer()

    // ── Speak text aloud ───────────────────────────────────────
    func speak(_ text: String) {
        guard !text.isEmpty else { return }

        // Create an utterance with the text.
        let utterance = AVSpeechUtterance(string: text)

        // Set the voice to a clear, pleasant voice.
        // "com.apple.ttsbundle.Samantha-compact" is the default
        // US English voice on iOS.
        utterance.voice = AVSpeechSynthesisVoice(language: "en-US")

        // Speaking rate. 0.5 is about normal speed (range 0.0-1.0).
        utterance.rate = 0.5

        // Pitch multiplier (1.0 is normal).
        utterance.pitchMultiplier = 1.0

        // Volume (0.0 to 1.0).
        utterance.volume = 1.0

        // Speak the utterance.
        synthesizer.speak(utterance)
    }

    // ── Stop speaking immediately ──────────────────────────────
    func stop() {
        synthesizer.stopSpeaking(at: .immediate)
    }
}
