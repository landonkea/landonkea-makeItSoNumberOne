// ───────────────────────────────────────────────────────────────────
// ContentView.swift — the app's main screen (iOS)
// ───────────────────────────────────────────────────────────────────
// This is the main screen of the iOS voice assistant.
// It shows:
//   1. A "Say Computer" button (to trigger the wake word)
//   2. Current state (listening/processing/thinking/speaking)
//   3. Claude's spoken response displayed as text
//   4. Last action executed
//
// This uses SwiftUI — Apple's modern UI framework.
// ───────────────────────────────────────────────────────────────────

import SwiftUI

struct ContentView: View {
    // ── State variables that update the UI when changed ─────────
    // These are @State because SwiftUI watches them for changes
    // and redraws the screen automatically.

    // What the assistant is currently doing.
    @State private var assistantState = "Tap to say \"Computer\""

    // Claude's last spoken response (shown as text).
    @State private var lastResponse = ""

    // The last action that was executed.
    @State private var lastAction = ""

    // Whether the assistant is currently processing something.
    @State private var isProcessing = false

    var body: some View {
        VStack(spacing: 20) {
            // ── Title ───────────────────────────────────────────
            Text("🖖 Make It So")
                .font(.largeTitle)
                .fontWeight(.bold)

            // ── Current state ───────────────────────────────────
            Text(assistantState)
                .font(.body)
                .foregroundColor(.secondary)

            // ── Trigger button ──────────────────────────────────
            Button(action: {
                startAssistant()
            }) {
                Text(isProcessing ? "🔄 Processing..." : "🎤 Say \"Computer\"")
                    .font(.headline)
                    .padding()
                    .frame(maxWidth: .infinity)
                    .background(isProcessing ? Color.gray : Color.blue)
                    .foregroundColor(.white)
                    .cornerRadius(12)
            }
            .disabled(isProcessing)
            .padding(.horizontal)

            // ── Claude's response ───────────────────────────────
            if !lastResponse.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Claude says:")
                        .font(.caption)
                        .foregroundColor(.secondary)

                    Text(lastResponse)
                        .font(.body)
                        .padding()
                        .background(Color(.systemGray6))
                        .cornerRadius(8)
                }
                .padding(.horizontal)
            }

            // ── Last action ─────────────────────────────────────
            if !lastAction.isEmpty {
                Text("Action: \(lastAction)")
                    .font(.caption)
                    .foregroundColor(.secondary)
                    .padding(.horizontal)
            }

            Spacer()
        }
        .padding(.top, 60)
        .onAppear {
            // Request microphone permission when the app opens.
            requestMicrophonePermission()
        }
    }

    // ── Start the voice assistant ────────────────────────────────
    private func startAssistant() {
        guard !isProcessing else { return }
        isProcessing = true

        // Run the assistant cycle asynchronously.
        Task {
            await runAssistantCycle()
            isProcessing = false
        }
    }

    // ── The main cycle: wake → listen → think → speak → act ─────
    private func runAssistantCycle() async {
        // STEP 1: Wake word detection (simulated for now).
        await updateState("🎤 Listening for 'Computer'...")

        // On iOS, we use SFSpeechRecognizer for always-on listening.
        // For the initial version, the button tap acts as the
        // wake word trigger (Porcupine iOS SDK can be added later).

        // STEP 2: Play the acknowledgment chime (using AVFoundation).
        await updateState("🔺 'Computer' detected!")
        playChime()

        // STEP 3: Listen for the user's command.
        await updateState("🎧 Listening for your command...")
        guard let speechText = await SpeechManager.shared.recognize() else {
            await updateState("Could not hear you. Try again.")
            return
        }

        // STEP 4: Send to Claude.
        await updateState("🧠 Thinking...")
        guard let result = await ClaudeService.shared.process(speechText) else {
            await updateState("Claude did not respond.")
            return
        }

        // STEP 5: Speak Claude's response.
        await MainActor.run {
            lastResponse = result.spokenText
        }
        TTSService.shared.speak(result.spokenText)

        // STEP 6: Execute actions.
        if !result.actions.isEmpty {
            for action in result.actions {
                await MainActor.run {
                    lastAction = "Executing: \(action.actionType)"
                }
                ActionRouter.shared.execute(action)
            }
        }

        await updateState("✅ Complete. Say 'Computer' again.")
    }

    // ── Helper to update state on the main thread ────────────────
    @MainActor
    private func updateState(_ newState: String) {
        assistantState = newState
    }

    // ── Play the Star Trek chime ────────────────────────────────
    private func playChime() {
        // Use AVFoundation to play the chime sound.
        // The chime WAV file is bundled with the app.
        if let path = Bundle.main.path(forResource: "computer_chime", ofType: "wav") {
            let url = URL(fileURLWithPath: path)
            AudioManager.shared.playSound(url)
        }
    }

    // ── Request microphone permission ───────────────────────────
    private func requestMicrophonePermission() {
        // On iOS, the user must grant microphone access.
        // We request it when the app opens so it's ready when
        // the user wants to use it.
        AVAudioSession.sharedInstance().requestRecordPermission { granted in
            if !granted {
                Task { @MainActor in
                    self.assistantState = "⚠️ Microphone access needed"
                }
            }
        }
    }
}

// ── Simple audio manager for playing the chime ──────────────────
import AVFoundation

class AudioManager {
    static let shared = AudioManager()
    private var player: AVAudioPlayer?

    func playSound(_ url: URL) {
        do {
            player = try AVAudioPlayer(contentsOf: url)
            player?.play()
        } catch {
            print("Could not play chime: \(error)")
        }
    }
}
