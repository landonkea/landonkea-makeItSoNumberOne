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

    // Holds the WakeWordService instance that listens for "Computer"
    // in the background. When the wake word is detected, it triggers
    // the full assistant cycle automatically. This is optional because
    // wake word detection only works when a PICOVOICE_ACCESS_KEY
    // environment variable is set. If no key is provided, we fall back
    // to button-only mode and this stays nil.
    @State private var wakeWordService: WakeWordService?

    // Holds a reference to the background Task that runs the wake word
    // detection loop. We keep a reference so we can cancel the task
    // when the view disappears (to stop listening and free system
    // resources). The task is created in onAppear and cancelled in
    // onDisappear. It's optional (Task?) because we create it lazily.
    @State private var wakeWordTask: Task<Void, Never>?

    // Bounded list of prior {role, content} turns, mirroring desktop's conversation_history
    // (see desktop/make_it_so.py) so Claude/Ollama on iOS get the same "remembers the last few
    // exchanges" context desktop already has. Loaded from disk in onAppear and appended to
    // after every completed cycle in runAssistantCycle() via recordExchange(). @State so a
    // reassignment (e.g. trimming) still triggers SwiftUI to keep the value around across
    // re-renders — we never actually display it, but @State is also just the simplest way to
    // keep a mutable value alive for the lifetime of this view.
    @State private var conversationHistory: [ConversationTurn] = []

    // Matches desktop's default (see desktop/config.example.yaml's settings.max_history: 20) —
    // 20 entries = 10 user + 10 assistant turns. Kept as a simple constant here since iOS has
    // no equivalent settings file yet.
    private let maxHistoryTurns = 20

    // Where conversation history is persisted between launches — the app's Documents
    // directory, which (unlike the bundle) is writable and private to this app.
    private var historyFileURL: URL {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("conversation_history.json")
    }

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
                        // Set a light gray background (using systemGray6 on iOS
                        // or a cross-platform equivalent) to make the text
                        // look like it's in a speech bubble.
                        #if canImport(UIKit)
                        .background(Color(.systemGray6))
                        #else
                        .background(Color.gray.opacity(0.15))
                        #endif
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
        // a function to ask for microphone permission and start the
        // wake word detection loop. This ensures the permission dialog
        // shows as soon as the app opens, rather than surprising the
        // user later when they try to speak.
        .onAppear {
            // Load whatever conversation history was saved from a previous launch, if any, so
            // context survives an app restart instead of always starting from an empty array
            // (see loadConversationHistory() below, and desktop's identical behavior).
            conversationHistory = loadConversationHistory()
            // Call the function that requests mic access from the user.
            requestMicrophonePermission()
            // Start the background wake word detection loop. If a
            // PICOVOICE_ACCESS_KEY is set in the environment, this
            // creates a WakeWordService and begins listening for
            // "Computer". If no key is set, the button remains the
            // only way to trigger the assistant.
            startWakeWordDetection()
            // Close the onAppear closure.
        }
        // Close the onAppear modifier.
        // When the view disappears (e.g., app goes to background or
        // user navigates away), we stop the wake word detection loop.
        // This is important because running the microphone continuously
        // in the background would drain the battery and potentially
        // violate App Store guidelines. We cancel the background task
        // and release the PorcupineManager to free system resources.
        .onDisappear {
            // Stop the wake word detection loop and release audio
            // resources. This cancels the background task and calls
            // destroy() on the WakeWordService to stop the microphone.
            stopWakeWordDetection()
            // Close the onDisappear closure.
        }
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

        // Stop wake word detection to avoid audio session conflicts.
        // Both Porcupine (wake word engine) and SpeechManager (speech
        // recognition) need exclusive access to the microphone. If we
        // leave wake word running while the assistant starts listening
        // for commands, the two audio engines would conflict (both
        // trying to capture from the mic). We stop wake word here so
        // SpeechManager can use the mic cleanly.
        stopWakeWordDetection()

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

            // Restart wake word detection after the assistant finishes
            // its cycle. This enables continuous hands-free operation:
            // the user says "Computer" once, gives a command, hears the
            // AI's response, then can say "Computer" again immediately
            // without tapping the button. If no PICOVOICE_ACCESS_KEY is
            // set, this is a no-op (the startWakeWordDetection function
            // checks for the key and returns early if not available).
            startWakeWordDetection()
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
        updateState("🎤 Listening for 'Computer'...")

        // On a real iPhone, we'd use SFSpeechRecognizer to continuously
        // listen for the wake word. For this first version, the button
        // tap IS the wake word trigger — tapping the button is like
        // saying "Computer". A dedicated wake word engine (like Porcupine
        // from Picovoice) can be added later for hands-free activation.

        // STEP 2: Play the acknowledgment chime (the Star Trek sound).
        // Before we listen for the actual command, we show detected state
        // so the user knows the wake word was recognized.
        updateState("🔺 'Computer' detected!")
        // Play the Star Trek chime sound from the app's bundled audio file.
        playChime()

        // STEP 3: Listen for the user's spoken command.
        // Show that we're now listening for what the user wants to do.
        updateState("🎧 Listening for your command...")
        // Call SpeechManager to start recording and transcribing speech.
        // The `await` pauses until the user stops speaking and we have
        // the transcribed text. `guard let` unwraps the optional — if
        // recognition failed (returned nil), we show an error and exit.
        guard let speechText = await SpeechManager.shared.recognize() else {
            // Show a message telling the user we couldn't hear them.
            updateState("Could not hear you. Try again.")
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
        updateState("🧠 Thinking...")
        // Call ClaudeService to process the text. The `await` pauses
        // while the network request (or local Ollama call) completes.
        // If it returns nil, something went wrong with both providers.
        guard let result = await ClaudeService.shared.process(
            speechText, conversationHistory: conversationHistory
        ) else {
            // Show an error message if we couldn't get a valid response.
            updateState("AI did not respond. Check your connection or Ollama.")
            // Exit — we can't proceed without a valid response.
            return
        }
        // Close the guard else block.

        // Record this exchange in conversation history BEFORE speaking/acting, mirroring
        // desktop's _record_exchange() — so even if a later step fails, the turn we already
        // got a response for is remembered on the next cycle. Runs on the main actor since it
        // mutates the @State conversationHistory property.
        await MainActor.run {
            recordExchange(userText: speechText, spokenText: result.spokenText)
        }

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
        updateState("✅ Complete. Say 'Computer' again.")
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

    // ── Record this turn in conversation history, then persist it ─
    // Appends the user's speech and the assistant's spoken reply to conversationHistory (in the
    // same {role, content} shape ClaudeService expects back), trims it to the last
    // maxHistoryTurns entries, and saves it to disk immediately — mirroring desktop's
    // per-cycle save_conversation_history() call so a crash or force-quit between cycles
    // doesn't lose the conversation. Must run on the main actor since it mutates the @State
    // conversationHistory property (see the MainActor.run call site above).
    @MainActor
    private func recordExchange(userText: String, spokenText: String) {
        conversationHistory.append(ConversationTurn(role: "user", content: userText))
        // Assistant turns are stored as "RESPONSE: <spokenText>" to match the RESPONSE:/ACTIONS:
        // format the shared system prompt asks for — a replayed assistant turn then looks
        // exactly like a normal reply would, instead of a bare, format-less sentence.
        conversationHistory.append(ConversationTurn(role: "assistant", content: "RESPONSE: \(spokenText)"))
        // Keep only the most recent maxHistoryTurns entries.
        if conversationHistory.count > maxHistoryTurns {
            conversationHistory = Array(conversationHistory.suffix(maxHistoryTurns))
        }
        saveConversationHistory(conversationHistory)
    }
    // Close the recordExchange function.

    // ── Load conversation history saved by a previous launch, if any ─
    // Returns an empty array (rather than throwing) for every failure case — missing file,
    // unreadable file, corrupt JSON — since history is a nice-to-have, not something worth
    // crashing startup over. Mirrors desktop's load_conversation_history().
    private func loadConversationHistory() -> [ConversationTurn] {
        guard let data = try? Data(contentsOf: historyFileURL) else {
            return []
        }
        guard let turns = try? JSONDecoder().decode([ConversationTurn].self, from: data) else {
            print("Could not decode \(historyFileURL.lastPathComponent) — starting with empty history.")
            return []
        }
        return turns
    }
    // Close the loadConversationHistory function.

    // ── Persist conversation history to disk ──────────────────────
    // Writes the current history as JSON — the exact shape loadConversationHistory() above
    // reads back. Failures are logged, not raised: losing the ability to persist history
    // should never crash the assistant mid-conversation.
    private func saveConversationHistory(_ history: [ConversationTurn]) {
        do {
            let data = try JSONEncoder().encode(history)
            try data.write(to: historyFileURL, options: .atomic)
        } catch {
            print("Could not save conversation history: \(error)")
        }
    }
    // Close the saveConversationHistory function.

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

    // ── Wake Word Detection ─────────────────────────────────────────
    // The following two functions manage the background wake word
    // detection loop. When active, Porcupine listens for "Computer"
    // through the microphone. When detected, it automatically triggers
    // the full assistant cycle (play chime → listen → think → speak
    // → act). The user can also tap the button as a fallback.
    //
    // PREREQUISITE: Set PICOVOICE_ACCESS_KEY in Xcode scheme:
    //   Edit Scheme → Run → Arguments → Environment Variables
    //   Name: PICOVOICE_ACCESS_KEY
    //   Value: (your key from https://console.picovoice.ai/)

    // A private function that starts the background wake word detection
    // loop. It reads the PICOVOICE_ACCESS_KEY from environment variables,
    // creates a WakeWordService, and enters an infinite loop that awaits
    // detection. When "Computer" is heard, it plays the chime and runs
    // the full assistant cycle. After the cycle completes, the loop
    // automatically restarts detection for continuous hands-free use.
    //
    // If no PICOVOICE_ACCESS_KEY is set, this function prints a message
    // and returns immediately — the assistant works via button only.
    private func startWakeWordDetection() {
        // Read the Picovoice access key from the environment. This key
        // is set in the Xcode scheme's environment variables. If it's
        // not set, we skip wake word detection entirely and fall back
        // to button-only mode. The `?? ""` handles the case where the
        // environment variable doesn't exist at all.
        let accessKey = ProcessInfo.processInfo.environment["PICOVOICE_ACCESS_KEY"] ?? ""

        // If the key is empty (not set), we can't use Porcupine at all.
        // Print a message to the console so developers know why wake
        // word isn't working, then return early without starting the
        // detection loop. The app still works via the button.
        guard !accessKey.isEmpty else {
            // Log that wake word is disabled so developers remember to
            // set the environment variable in the Xcode scheme.
            print("PICOVOICE_ACCESS_KEY not set — wake word detection disabled. Set it in Edit Scheme → Run → Arguments → Environment Variables.")
            // Exit the function — no detection loop to start.
            return
        }

        // Create a WakeWordService instance with the access key. This
        // doesn't start listening yet — it just stores the key for later
        // use. The actual detection begins when detect() is called below.
        // We store the service as a state variable so we can access it
        // from other methods (like stopWakeWordDetection).
        wakeWordService = WakeWordService(accessKey: accessKey)

        // Update the assistant state to show that wake word detection
        // is active. The user sees this message and knows they can just
        // say "Computer" instead of tapping the button. We use async
        // update because assistantState is a @State property.
        Task { @MainActor in
            assistantState = "🎤 Listening for 'Computer'..."
        }

        // Create a background Task that runs the detection loop. The
        // Task is a Swift concurrency construct that runs asynchronously
        // on a background thread. We store a reference to it in the
        // wakeWordTask state variable so we can cancel it later (in
        // stopWakeWordDetection or if the view disappears).
        //
        // We don't use [weak self] here because ContentView is a SwiftUI
        // View struct. SwiftUI ensures the view's storage remains valid
        // for the duration it's displayed. When the view disappears,
        // onDisappear cancels this task, breaking the reference cycle.
        wakeWordTask = Task {
            // Enter the main detection loop. We use a while loop with a
            // Task.isCancelled check so the loop exits cleanly when the
            // task is cancelled (e.g., from onDisappear or button press).
            // The loop runs indefinitely until cancelled — each iteration
            // waits for a wake word, processes it, then loops back.
            while !Task.isCancelled {
                // Wait for the "Computer" wake word. The detect() function
                // pauses here until Porcupine hears the keyword (or an
                // error occurs). It returns true if "Computer" was detected,
                // false if there was an error (mic denied, etc.).
                //
                // If the WakeWordService was destroyed (wakeWordService set
                // to nil), detect() is called on nil and returns false,
                // causing the loop to continue harmlessly. The service is
                // recreated on the next startWakeWordDetection call.
                let detected = await wakeWordService?.detect() ?? false

                // If the wake word was detected AND we're not already
                // processing a previous command, start the assistant cycle.
                // The isProcessing check prevents overlapping cycles if
                // the user also tapped the button simultaneously.
                if detected && !isProcessing {
                    // Set the processing flag to prevent concurrent cycles.
                    // This disables the button and shows "Processing..."
                    // on screen so the user knows the assistant is busy.
                    await MainActor.run { isProcessing = true }

                    // Run the full assistant cycle: listen for command →
                    // send to AI → speak response → execute actions.
                    // We reuse the existing runAssistantCycle to keep
                    // the flow consistent between button and wake word.
                    // NOTE: We do NOT call playChime() here — we used to,
                    // but runAssistantCycle() already plays the chime at
                    // its own STEP 2 ("'Computer' detected!"), so calling
                    // it here too made the chime play twice on every
                    // wake-word trigger. runAssistantCycle handles the
                    // whole "detected → chime → listen for command" flow
                    // regardless of whether the button or the wake word
                    // triggered it.
                    await runAssistantCycle()

                    // Reset the processing flag so the user can trigger
                    // another cycle (via wake word or button).
                    await MainActor.run { isProcessing = false }

                    // After the cycle finishes, the loop continues to the
                    // next iteration, calling service.detect() again to
                    // wait for the next "Computer". This gives continuous
                    // hands-free operation without needing to tap.
                }
                // If detect() returned false (error) or we're already
                // processing, the loop just continues to the next
                // detect() call, effectively retrying indefinitely.
            }
            // Close the while loop — the task was cancelled or the view
            // was dismissed, so we stop detecting.
        }
        // Close the Task initializer.
    }

    // A private function that stops the wake word detection loop and
    // releases all associated resources. Call this when:
    //   - The user taps the button (to free the mic for speech recognition)
    //   - The view disappears (to avoid background battery drain)
    //   - The app enters the background (App Store compliance)
    //
    // This function is safe to call multiple times — subsequent calls
    // are no-ops once the task is cancelled and the service is destroyed.
    private func stopWakeWordDetection() {
        // Cancel the wake word detection Task. This sets the cancellation
        // flag on the task, which the while loop checks via
        // Task.isCancelled. The loop exits cleanly on its next iteration.
        // If wakeWordTask is nil (never started or already stopped),
        // the optional chaining does nothing.
        wakeWordTask?.cancel()
        // Release the task reference. Setting to nil allows ARC to
        // deallocate the task object. We also set the service to nil
        // below, so both references are cleaned up together.
        wakeWordTask = nil

        // Destroy the WakeWordService instance. This stops the
        // PorcupineManager's audio capture and releases the microphone.
        // Calling destroy() is important because Porcupine holds the
        // audio session, and we need to release it before SpeechManager
        // (speech recognition) can use the mic.
        wakeWordService?.destroy()
        // Release the service reference. Setting to nil allows ARC to
        // deallocate the service and its PorcupineManager. Service is
        // now nil until startWakeWordDetection is called again.
        wakeWordService = nil
    }

    // A function that asks the user for permission to use the microphone.
    // iOS requires explicit user permission before any app can access
    // the microphone. We call this when the app first opens so it's
    // ready when the user wants to speak.
    // On macOS (for testing), microphone permission is handled differently
    // or may not be needed, so we provide a stub.
    private func requestMicrophonePermission() {
        #if canImport(UIKit)
        // Request microphone access. iOS 17+ uses AVAudioApplication;
        // the system shows a dialog asking "Allow Make It So to access
        // the microphone?" The closure runs after the user answers,
        // receiving a `granted` boolean (true if they said yes).
        AVAudioApplication.requestRecordPermission { granted in
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
        #else
        // On non-iOS platforms, microphone permission is not applicable.
        // We assume access is available and don't show a permission dialog.
        print("requestMicrophonePermission() skipped — not on iOS.")
        #endif
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
