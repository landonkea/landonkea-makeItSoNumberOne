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
// 2. Set the voice to the device's default voice for US English
//    (on most iPhones this is "Samantha", but it can differ if the
//    user changed their system voice settings — we don't hardcode
//    a specific voice identifier, we just ask for "en-US" and let
//    iOS pick whatever voice is installed for that language).
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

        // Ask iOS for whatever voice it has installed for the "en-US"
        // (US English) language. We don't hardcode a specific voice
        // identifier — iOS picks the system default, which is usually
        // "Samantha" out of the box but can be a different voice if the
        // user changed it in Settings > Accessibility > Spoken Content.
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
