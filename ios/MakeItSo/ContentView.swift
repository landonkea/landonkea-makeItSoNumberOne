// ─── ContentView.swift ───────────────────────────────────────────────
// This file defines the main screen that users see when they open the
// Make It So app on their iPhone. It shows a "Say Computer" button, the
// current state of the assistant (listening, thinking, speaking), and
// displays whatever Claude says back to the user.
//
// The code uses SwiftUI — Apple's modern way to build user interfaces.
// Instead of manually arranging things, we describe WHAT we want on
// screen and SwiftUI figures out the details. When our "state variables"
// change, the screen automatically updates to match.
// ──────────────────────────────────────────────────────────────────────

// Import the SwiftUI framework — this gives us all the tools to build
// user interfaces: text labels, buttons, layouts, colors, and more.
// SwiftUI is Apple's newest UI toolkit, replacing the older UIKit.
import SwiftUI

// Define a structure called ContentView that follows the View protocol.
// In SwiftUI, a "View" is just something you can draw on screen. By
// making our struct conform to View (via the colon syntax), SwiftUI
// knows it can render this on the screen. Structs are lightweight
// data containers in Swift.
struct ContentView: View {
    // These are "state variables" — special properties that SwiftUI
    // watches for changes. When any of these change, SwiftUI
    // automatically redraws the parts of the screen that use them.
    // The `@State` attribute tells SwiftUI to manage the storage
    // for these and trigger UI updates when they change.

    // A string that shows what the assistant is currently doing.
    // It starts with a message telling the user to tap the button.
    // "private" means only this view can change or read it.
    @State private var assistantState = "Tap to say \"Computer\""

    // Stores the last text response from the AI. This gets shown on
    // screen so the user can read what the AI said (in addition to
    // hearing it spoken out loud). Starts empty because nothing has
    // been said yet.
    @State private var lastResponse = ""

    // Stores a description of the last action that was executed.
    // For example, if the AI told us to search the web, this would say
    // "Executing: search_web". Starts empty because no action ran yet.
    @State private var lastAction = ""

    // A true/false flag that tracks whether the assistant is currently
    // busy processing something. When true, we disable the button so
    // the user can't start another cycle while one is already running.
    // Starts false because nothing is happening yet.
    @State private var isProcessing = false

    // This is the required property that every View must have. It
    // describes what to draw on screen. SwiftUI calls this whenever
    // it needs to render (or re-render) the screen. `some View` means
    // "this returns some type that conforms to the View protocol" —
    // we don't need to say exactly which type.
    var body: some View {
        // A vertical stack (VStack) arranges its children from top to
        // bottom, with 20 points of spacing between each child element.
        // The spacing adds breathing room between the title, button,
        // and text areas.
        VStack(spacing: 20) {
            // Create a text label with the Star Trek greeting emoji
            // and "Make It So". `.font(.largeTitle)` makes it big text,
            // like a heading. `.fontWeight(.bold)` makes it thick/dark.
            Text("🖖 Make It So")
                .font(.largeTitle)
                .fontWeight(.bold)

            // Create another text label showing the current assistant
            // state (listening, thinking, etc.). `.font(.body)` uses the
            // standard text size. `.foregroundColor(.secondary)` makes
            // it a slightly faded gray color instead of pure black.
            Text(assistantState)
                .font(.body)
                .foregroundColor(.secondary)

            // Create a button that the user can tap. The `action` closure
            // (the code inside { }) runs when the user taps the button.
            // The `label` closure (the second set of { }) defines what
            // the button looks like — in this case, another Text view.
            Button(action: {
                // Call the startAssistant function when the button is
                // tapped. This begins the whole wake → listen → think
                // → speak → act cycle.
                startAssistant()
                // Close the button's action closure.
            }) {
                // This is the label (what the button looks like). We
                // show different text depending on whether the assistant
                // is currently processing. The `? :` is a ternary operator
                // — if isProcessing is true, show the first text; if
                // false, show the second.
                Text(isProcessing ? "🔄 Processing..." : "🎤 Say \"Computer\"")
                    // Use headline font (slightly bigger than body but
                    // smaller than title) for the button text.
                    .font(.headline)
                    // Add padding (extra space) around the text inside
                    // the button so it doesn't touch the edges.
                    .padding()
                    // Make the button stretch to fill the available
                    // width (up to the screen edges minus padding).
                    .frame(maxWidth: .infinity)
                    // Set the background color: gray when processing
                    // (to look disabled/neutral), blue when ready.
                    .background(isProcessing ? Color.gray : Color.blue)
                    // Make the text color white so it contrasts well
                    // against the blue or gray background.
                    .foregroundColor(.white)
                    // Round the corners of the button for a modern look.
                    .cornerRadius(12)
                // Close the label closure.
            }
            // Disable the button when processing (so user can't tap
            // twice). `.disabled(true)` makes it un-tappable and dims it.
            .disabled(isProcessing)
            // Add horizontal padding (space on left and right sides)
            // so the button doesn't touch the screen edges.
            .padding(.horizontal)

            // Show the AI's response text only if it's not empty.
            // The `if` condition checks `!lastResponse.isEmpty` — the
            // "!" means "not", so this is "if lastResponse is NOT empty".
            if !lastResponse.isEmpty {
                // A vertical stack for the response section, aligned
                // to the left (leading edge) with 8 points between items.
                VStack(alignment: .leading, spacing: 8) {
                    // A small caption label saying "AI says:" to
                    // introduce the response text.
                    Text("AI says:")
                        // Use the smallest standard font size for a label.
                        .font(.caption)
                        // Make it gray to distinguish from the response.
                        .foregroundColor(.secondary)

                    // Show the actual response text from the AI.
                    Text(lastResponse)
                        // Use standard body font size for readability.
                        .font(.body)
                        // Add padding inside the box around the text.
                        .padding()
                        // Set a light gray background (systemGray6 is a
                        // very light gray that works in light and dark
                        // modes) to make the text look like it's in a
                        // speech bubble.
                        .background(Color(.systemGray6))
                        // Round the corners of the speech bubble box.
                        .cornerRadius(8)
                    // Close the response text modifier chain.
                }
                // Close the response VStack.
                // Add horizontal padding to match the button above.
                .padding(.horizontal)
            }
            // Close the if block for the response.

            // Show the last action text only if it's not empty.
            if !lastAction.isEmpty {
                // Display the action description in small gray text.
                Text("Action: \(lastAction)")
                    .font(.caption)
                    .foregroundColor(.secondary)
                    // Add horizontal padding to match everything else.
                    .padding(.horizontal)
            }
            // Close the if block for the action.

            // A spacer pushes everything above it toward the top of
            // the screen. It takes up any remaining space so the
            // content sits at the top rather than being centered.
            Spacer()
            // Close the spacer.
        }
        // Close the main VStack.
        // Add top padding of 60 points so the content doesn't sit
        // behind the iPhone's status bar (where the clock and battery
        // icon are at the top of the screen).
        .padding(.top, 60)
        // When the view first appears on screen (`.onAppear`), we call
        // a function to ask for microphone permission. This ensures
        // the permission dialog shows as soon as the app opens, rather
        // than surprising the user later when they try to speak.
        .onAppear {
            // Call the function that requests mic access from the user.
            requestMicrophonePermission()
            // Close the onAppear closure.
        }
        // Close the onAppear modifier.
    }
    // Close the body property.

    // A private function that starts the assistant cycle. It checks
    // that we're not already processing (to avoid starting a second
    // cycle), then sets isProcessing to true and kicks off the async
    // runAssistantCycle function.
    private func startAssistant() {
        // If we're already processing, exit immediately and do nothing.
        // `guard` checks that isProcessing is false (!isProcessing means
        // "is NOT processing"). If it's true, the guard fails and we return.
        guard !isProcessing else { return }
        // Set the flag to true so the button disables and the UI shows
        // "Processing..." This prevents double-taps and shows feedback.
        isProcessing = true

        // Run the assistant cycle as an asynchronous task. `Task` creates
        // a new async context that runs in the background while the UI
        // stays responsive. The `await` inside will pause without freezing.
        Task {
            // Call the async function that runs through the full wake →
            // listen → think → speak → act pipeline. We await it so the
            // code after it runs after the cycle completes.
            await runAssistantCycle()
            // Once the cycle finishes (or fails), reset the processing
            // flag to false so the user can tap the button again.
            isProcessing = false
            // Close the Task closure.
        }
        // Close the Task block.
    }
    // Close the startAssistant function.

    // The main async function that orchestrates the entire assistant
    // workflow: wake word detection → chime → listen → think → speak
    // → act. It's marked `async` because it uses await for operations
    // that take time (speech recognition, network requests).
    //
    // The "think" step (step 4) calls ClaudeService.process() which
    // internally handles the online/offline logic:
    //   - ONLINE: sends text to Claude API (needs internet)
    //   - OFFLINE: sends text to local Ollama (runs on your machine)
    //   - AUTO: tries online first, falls back to offline on failure
    // This is transparent to the ContentView — it just calls process()
    // and gets back a result regardless of which AI provider was used.
    private func runAssistantCycle() async {
        // STEP 1: Show that we're waiting for the wake word "Computer".
        // The await here means the UI updates before we continue.
        await updateState("🎤 Listening for 'Computer'...")

        // On a real iPhone, we'd use SFSpeechRecognizer to continuously
        // listen for the wake word. For this first version, the button
        // tap IS the wake word trigger — tapping the button is like
        // saying "Computer". A dedicated wake word engine (like Porcupine
        // from Picovoice) can be added later for hands-free activation.

        // STEP 2: Play the acknowledgment chime (the Star Trek sound).
        // Before we listen for the actual command, we show detected state
        // so the user knows the wake word was recognized.
        await updateState("🔺 'Computer' detected!")
        // Play the Star Trek chime sound from the app's bundled audio file.
        playChime()

        // STEP 3: Listen for the user's spoken command.
        // Show that we're now listening for what the user wants to do.
        await updateState("🎧 Listening for your command...")
        // Call SpeechManager to start recording and transcribing speech.
        // The `await` pauses until the user stops speaking and we have
        // the transcribed text. `guard let` unwraps the optional — if
        // recognition failed (returned nil), we show an error and exit.
        guard let speechText = await SpeechManager.shared.recognize() else {
            // Show a message telling the user we couldn't hear them.
            await updateState("Could not hear you. Try again.")
            // Exit the function — we can't proceed without user input.
            return
        }
        // Close the guard else block.

        // STEP 4: Send the transcribed text to the AI for processing.
        // This calls ClaudeService.process() which handles the online/
        // offline decision internally:
        //   - Tries Claude API first (online, needs internet + API key)
        //   - Falls back to Ollama offline if mode is "auto" and Claude fails
        //   - Uses Ollama directly if mode is "offline"
        // Show a thinking indicator while we wait for the AI's reply.
        await updateState("🧠 Thinking...")
        // Call ClaudeService to process the text. The `await` pauses
        // while the network request (or local Ollama call) completes.
        // If it returns nil, something went wrong with both providers.
        guard let result = await ClaudeService.shared.process(speechText) else {
            // Show an error message if we couldn't get a valid response.
            await updateState("AI did not respond. Check your connection or Ollama.")
            // Exit — we can't proceed without a valid response.
            return
        }
        // Close the guard else block.

        // STEP 5: Speak the AI's response out loud using text-to-speech.
        // We must update UI properties on the main thread (UIKit/SwiftUI
        // requirement). `MainActor.run` ensures the code inside runs on
        // the main thread where UI changes are safe.
        await MainActor.run {
            // Store the AI's spoken text in our state variable so it
            // appears on screen for the user to read.
            lastResponse = result.spokenText
            // Close the MainActor closure.
        }
        // Use the text-to-speech service to actually speak the AI's
        // response out loud through the iPhone's speaker.
        TTSService.shared.speak(result.spokenText)

        // STEP 6: Execute any actions the AI requested.
        // Check if there are any actions to perform. Actions might be
        // things like opening Safari or sending a text message. If
        // the array is empty, we skip this step entirely.
        if !result.actions.isEmpty {
            // Loop through each action the AI returned. `for action in`
            // iterates over the array, giving us one ClaudeAction at a time.
            for action in result.actions {
                // Update the UI to show which action we're executing.
                // Again, we use MainActor.run because we're modifying
                // a @State property that triggers UI updates.
                await MainActor.run {
                    // Display the action type (like "search_web") so the
                    // user can see what the assistant is doing.
                    lastAction = "Executing: \(action.actionType)"
                    // Close the MainActor closure.
                }
                // Execute the action using ActionRouter. This might open
                // Safari, send a text, call someone, etc., depending on
                // what the AI told us to do.
                ActionRouter.shared.execute(action)
                // Continue to the next action in the list (if any).
            }
            // Close the for loop.
        }
        // Close the if block.

        // Update the state to show that everything completed successfully
        // and the user can start again by saying "Computer".
        await updateState("✅ Complete. Say 'Computer' again.")
        // Close the function — the cycle is finished.
    }
    // Close the runAssistantCycle function.

    // A helper function that updates the assistantState on the main
    // thread. The @MainActor attribute means this function always runs
    // on the main thread, which is important because assistantState is
    // a @State property and SwiftUI requires UI changes on the main thread.
    @MainActor
    private func updateState(_ newState: String) {
        // Set the assistant state string to the new value. This triggers
        // a UI update because it's a @State property.
        assistantState = newState
        // Close the assignment.
    }
    // Close the updateState function.

    // A function that plays the Star Trek computer chime sound effect.
    // This uses AVFoundation (Apple's audio framework) to play a WAV
    // file that's bundled inside the app.
    private func playChime() {
        // Try to find the "computer_chime.wav" file in the app's bundle
        // (the collection of files packaged with the app). `Bundle.main`
        // refers to the app's own resources. If the file exists, we get
        // its file path as a String. If not, we get nil.
        if let path = Bundle.main.path(forResource: "computer_chime", ofType: "wav") {
            // Convert the file path string into a URL object (a standard
            // way to reference file locations in iOS/macOS).
            let url = URL(fileURLWithPath: path)
            // Use the shared AudioManager to load and play the sound file.
            AudioManager.shared.playSound(url)
            // Close the if body.
        }
        // Close the if statement — if the file wasn't found, we silently
        // skip playing the chime (better than crashing).
    }
    // Close the playChime function.

    // A function that asks the user for permission to use the microphone.
    // iOS requires explicit user permission before any app can access
    // the microphone. We call this when the app first opens so it's
    // ready when the user wants to speak.
    private func requestMicrophonePermission() {
        // Get the shared audio session (the system's audio manager) and
        // call requestRecordPermission. The system shows a dialog asking
        // "Allow Make It So to access the microphone?" The closure runs
        // after the user answers, receiving a `granted` boolean (true if
        // they said yes, false if no).
        AVAudioSession.sharedInstance().requestRecordPermission { granted in
            // If the user denied permission (granted is false), we need
            // to update the UI to show a warning.
            if !granted {
                // Use Task with @MainActor to safely update the state
                // from this background closure (AVAudioSession callbacks
                // don't run on the main thread by default).
                Task { @MainActor in
                    // Update the state to show a warning icon and message
                    // so the user knows they need to enable mic access
                    // in Settings to use the app.
                    self.assistantState = "⚠️ Microphone access needed"
                    // Close the Task closure.
                }
                // Close the Task block.
            }
            // Close the if block — if granted is true, we don't need to
            // do anything because the mic will work when needed.
        }
        // Close the requestRecordPermission call.
    }
    // Close the requestMicrophonePermission function.
}
// Close the ContentView struct.

// ─── AudioManager ────────────────────────────────────────────────────
// A simple helper class that manages playing sound effects (like the
// Star Trek chime). We import AVFoundation here to get AVAudioPlayer.
import AVFoundation

// Define a class that handles playing audio files. It's a separate class
// (not inside ContentView) because audio playback is a general-purpose
// feature that other parts of the app might use too.
class AudioManager {
    // A single shared instance that the whole app uses (singleton pattern).
    // Instead of creating multiple AudioManager objects, we have one that
    // everyone shares. This prevents multiple sounds playing at once.
    static let shared = AudioManager()
    // A private variable that holds the current audio player. It's an
    // optional (AVAudioPlayer?) because there might not be a sound
    // currently loaded/playing. `private` so other code doesn't mess
    // with it. AVAudioPlayer is Apple's class for playing audio files.
    private var player: AVAudioPlayer?

    // A function that plays a sound from a given file URL. It takes the
    // URL of the audio file and attempts to load and play it.
    func playSound(_ url: URL) {
        // The do-catch block handles errors that might occur when loading
        // the audio file (like if it's corrupted or missing).
        do {
            // Create an AVAudioPlayer with the file URL. This loads the
            // audio data into memory and prepares it for playback.
            // `try` because this can throw an error if the file is invalid.
            player = try AVAudioPlayer(contentsOf: url)
            // Start playing the sound. `.play()` is asynchronous — it
            // plays in the background while the app continues running.
            player?.play()
            // Close the do block.
        }
        // Catch any errors that occurred during audio loading/playback.
        catch {
            // Print the error to the console for debugging purposes.
            // This helps developers know if a sound file is missing
            // or corrupted without crashing the app.
            print("Could not play chime: \(error)")
            // Close the catch body.
        }
        // Close the catch block.
    }
    // Close the playSound function.
}
// Close the AudioManager class.
