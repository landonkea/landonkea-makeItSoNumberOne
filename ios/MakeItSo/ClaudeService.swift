// ─── ClaudeService.swift ─────────────────────────────────────────────
// This file contains all the code needed to talk to a Large Language
// Model (LLM) AI assistant from an iPhone app. It supports TWO modes:
//
//   ONLINE  mode: Claude API  (Anthropic), smarter, needs internet
//   OFFLINE mode: Ollama/Llama (local)   , free, runs on your machine
//
// The "mode" is read from the system environment variable AI_MODE.
//   - "auto"    : try online first, fall back to offline if it fails
//   - "online"  : only use Claude API, no fallback
//   - "offline" : only use local Ollama, no internet needed
//
// The code uses Apple's built-in networking (URLSession) so no
// external libraries are needed. We manually build JSON request bodies
// and parse JSON responses for both AI providers.
// ──────────────────────────────────────────────────────────────────────

// Import Apple's Foundation framework, this gives us access to basic
// types like String, URL, Data, JSONSerialization, and URLSession.
// We need these to make network requests and work with JSON data.
import Foundation

// Define a structure (like a simple data container) that holds the AI's
// response. A struct in Swift is a way to group related pieces of data
// together. This one holds the spoken text and any actions to execute.
struct ClaudeResult {
    // The text the AI says out loud (as a String of characters).
    let spokenText: String
    // A list (array) of actions the AI wants executed, like searching
    // the web or sending a text message.
    let actions: [ClaudeAction]
}

// Define a structure that represents a single action the AI wants us
// to perform. For example, "search_web" with a query parameter.
struct ClaudeAction {
    // What kind of action to perform (like "search_web", "send_sms").
    let actionType: String
    // A dictionary (key-value pairs) of extra information for the action.
    // For a web search, this might be ["query": "weather today"].
    // [String: String] means the keys are text and the values are text.
    let params: [String: String]
}

// ── Conversation history turn ────────────────────────────────────
// One remembered exchange, mirroring the desktop Python version's
// {"role": "user"/"assistant", "content": "..."} dict shape (see
// desktop/make_it_so.py's _record_exchange()). Codable so ContentView
// can persist an array of these to disk as JSON and reload it later.
struct ConversationTurn: Codable {
    // "user" or "assistant", who said this.
    let role: String
    // The text of that turn. For assistant turns this is stored as
    // "RESPONSE: <spokenText>" (matching the RESPONSE:/ACTIONS: prompt
    // format both providers are told to use), so a replayed turn still
    // looks like a normal assistant reply.
    let content: String
}

// Define the main class that handles talking to the AI brain.
// A class is like a blueprint for creating objects. This one is a
// "service", a reusable component that provides a specific feature
// (in this case, communicating with an LLM like Claude or Ollama).
class ClaudeService {
    // Create a single shared instance of this class that the whole app
    // can use. This is called the "singleton pattern", instead of
    // creating multiple copies, everyone shares one. We use `static`
    // to make it a type-level property (belongs to the class itself,
    // not to any specific instance). `shared` is the conventional name.
    static let shared = ClaudeService()

    // The API key (a secret password that lets us use Claude). Resolved
    // fresh via SettingsStore on every access (this is a computed
    // property, not a stored `let`) so a key the user just saved in
    // Settings (SettingsView.swift) takes effect on the very next
    // request, no app restart needed. SettingsStore itself prefers the
    // user's Keychain-saved value and falls back to the
    // ANTHROPIC_API_KEY environment variable when nothing is saved,
    // exactly like this property used to read the environment variable
    // directly. This is private so other parts of the app can't
    // accidentally read our secret key.
    private var apiKey: String {
        SettingsStore.getAnthropicApiKey()
    }

    // Read the AI mode from environment variable. This controls whether
    // we use the online Claude API, the offline Ollama, or auto-fallback.
    //   - "auto"    : try online first, fall back to offline on failure
    //   - "online"  : use Claude API only (fail if no internet)
    //   - "offline" : use local Ollama only (no internet needed)
    // Defaults to "auto" if the environment variable is not set.
    private let mode = ProcessInfo.processInfo.environment["AI_MODE"] ?? "auto"

    // Store the URL for Claude's API (the web address we send requests
    // to). We force-unwrap with `!` because we know this URL is valid
    // (we typed it correctly in the code). If it were invalid, the app
    // would crash, that's intentional because a bad URL means the
    // app can't work at all. This URL points to Anthropic's message
    // endpoint that accepts our conversation text and returns a reply.
    private let apiURL = URL(string: "https://api.anthropic.com/v1/messages")!

    // Load the system prompt from the app bundle's Resources folder.
    // This is the same prompt text used by the desktop version.
    // We try to load from the file first; if it fails (e.g. during
    // development before resources are bundled), we fall back to a
    // hardcoded default so the app still works.
    private let systemPrompt: String = {
        // Try to find system_prompt.txt in the app's main bundle.
        if let path = Bundle.main.path(forResource: "system_prompt", ofType: "txt"),
           let content = try? String(contentsOfFile: path, encoding: .utf8) {
            // Successfully loaded from file, use it.
            return content
        }
        // Fallback hardcoded prompt if the file isn't available.
        return """
        You are the computer from the USS Enterprise (NCC-1701-D) in Star Trek: The Next Generation. You are helpful, precise, and calm. The user has addressed you by saying "Computer", so you are now active.

        Your job is to:
        1. Answer the user's question or fulfill their request.
        2. If they ask you to do something on the computer (open an app, search the web, type something, click something, check files, etc.), issue the appropriate action command.
        3. If you don't understand or can't do something, say so clearly.

        OUTPUT FORMAT, You MUST respond in this exact format:

        RESPONSE: <what you say out loud to the user, 1-3 sentences>

        ACTIONS:
        - action: <action_type>
          params:
            <key>: <value>
        - action: <action_type>
          params:
            <key>: <value>

        Valid action types:
        - open_app: Open an application (params: name)
        - search_web: Search the internet (params: query)
        - type_text: Type text at the cursor (params: text)
        - press_keys: Press keyboard shortcut (params: keys, list)
        - run_command: Run a shell command (params: command)
        - read_file: Read a file (params: path)
        - scroll: Scroll the screen (params: direction [up/down], amount [int])
        - click: Click at screen position (params: x, y)

        If no actions are needed, leave the ACTIONS section blank:
        ACTIONS:

        Keep responses short and Starfleet-professional. If the user says "thank you", respond with something like "You are welcome, Captain."

        Always respond in the format above. Never deviate from the format.
        """
    }()

    // Define the main function that sends text to the AI and gets a
    // response back. It takes a String (the user's spoken words) and
    // returns an optional ClaudeResult (either a valid result or nil
    // if something went wrong). The `async` keyword means this function
    // can pause and wait for network operations without freezing the
    // app's interface. The `->` arrow shows what type we return.
    //
    // DECISION LOGIC (matching the desktop Python version):
    //   mode = "online" → try Claude only, no fallback
    //   mode = "offline" → skip Claude, go straight to Ollama
    //   mode = "auto"   → try Claude first, fall back to Ollama on failure
    // `conversationHistory` is the bounded list of prior turns (see ConversationTurn above)
    // that the caller (ContentView) maintains across cycles, passing it in lets both providers
    // give context-aware replies (e.g. "open Safari" then "now search it" knows what "it"
    // refers to), matching the desktop Python version's conversation_history behavior. Defaults
    // to an empty array so existing call sites that don't pass one keep working unchanged.
    func process(_ userText: String, conversationHistory: [ConversationTurn] = []) async -> ClaudeResult? {
        // Check if the API key is empty (not set). `guard` is a Swift
        // keyword that checks a condition, if it fails, we MUST exit
        // the function (via return). The `!` means "not", so this
        // checks "if apiKey is NOT empty". If it IS empty, we would
        // normally return, BUT we also let "offline" mode proceed
        // (Ollama doesn't need an API key).
        // Only bail if mode is "online" (which requires a key).
        if apiKey.isEmpty && mode == "online" {
            // Print a message to the debug console so developers know
            // the API key is missing. This doesn't show to users, it's
            // only visible when running through Xcode.
            print("ANTHROPIC_API_KEY not set and mode is 'online'")
            // Return a fake response so the app doesn't crash.
            return ClaudeResult(
                spokenText: "Please add your Anthropic API key to use online mode, Captain.",
                actions: []
            )
        }

        // If mode is "offline", skip Claude entirely and go straight
        // to the local Ollama instance. This is useful for development
        // without internet access or to avoid API costs.
        if mode == "offline" {
            // Print a log message so we know we're using offline mode.
            print("AI mode is 'offline', calling Ollama directly.")
            // Call the Ollama function and return its result directly.
            return await processWithOllama(userText, conversationHistory: conversationHistory)
        }

        // ── ONLINE ATTEMPT (Claude API) ──────────────────────────
        // If we get here, mode is either "auto" or "online".
        // We try the Claude API first. If it fails AND mode is "auto",
        // we'll fall back to Ollama below.
        print("AI mode is '\(mode)', trying Claude API first.")

        // Try the online Claude call. If it succeeds, we return the
        // result immediately. If mode is "online" and it fails, we
        // return nil (no fallback allowed). If mode is "auto" and it
        // fails, we continue to the Ollama fallback below.
        if let result = await processWithClaude(userText, conversationHistory: conversationHistory) {
            // Claude returned a valid result, return it immediately.
            return result
        }

        // If we're here, the Claude call failed (returned nil).
        // If mode is "online", we're not allowed to fall back.
        if mode == "online" {
            // Log that online mode failed and we're not falling back.
            print("Claude failed and mode is 'online', no fallback.")
            // Return nil to indicate total failure.
            return nil
        }

        // ── OFFLINE FALLBACK (Ollama) ───────────────────────────
        // Mode must be "auto" since we already handled "online" and
        // "offline" above. Log the fallback for debugging.
        print("Claude failed, falling back to offline Ollama.")
        // Call the Ollama function and return whatever it gives us
        // (might be a valid result or nil if Ollama also fails).
        return await processWithOllama(userText, conversationHistory: conversationHistory)
    }

    // ── processWithClaude(), Online: calls Anthropic's Claude API ──
    // This is the ORIGINAL logic extracted into its own function.
    // It sends the user's text to Claude over the internet and parses
    // the structured response (spoken text + actions).
    private func processWithClaude(
        _ userText: String,
        conversationHistory: [ConversationTurn]
    ) async -> ClaudeResult? {
        // Open a do-catch block for error handling. This lets us try
        // operations that might fail (like network calls or JSON parsing)
        // and catch any errors that occur. If anything inside the `do`
        // block throws an error, execution jumps to the `catch` block.
        do {
            // Create the list of messages to send to Claude. Each message
            // has a "role" (who's speaking, here "user" means the human)
            // and "content" (what they said). We put this inside an array
            // (square brackets) because Claude expects a list of messages
            // forming a conversation. `userText` is the transcribed speech.
            // Earlier turns from conversationHistory are replayed first
            // (oldest to newest, the order Claude's API requires), then
            // the user's brand-new utterance goes last.
            var messages: [[String: Any]] = conversationHistory.map {
                ["role": $0.role, "content": $0.content]
            }
            messages.append(["role": "user", "content": userText])

            // Build the full request body, a dictionary of all the
            // parameters Claude's API needs. [String: Any] means the
            // keys are strings and the values can be any type (string,
            // number, array, etc.).
            let body: [String: Any] = [
                // Which Claude model version to use. This is the specific
                // AI brain that will process our request. Different models
                // have different capabilities and speeds.
                "model": "claude-sonnet-4-20250514",
                // Maximum number of "tokens" (roughly words or parts of
                // words) in Claude's response. This limits how long the
                // reply can be so we don't get a never-ending response.
                "max_tokens": 1024,
                // The system prompt, our instructions to Claude about
                // how to behave and what format to use for the response.
                "system": systemPrompt,
                // The conversation messages (just the user's text for now).
                "messages": messages,
                // A "temperature" setting for creativity. 0.7 means some
                // creativity but not too random. 0 would be very predictable,
                // 1.0 would be very creative/random.
                "temperature": 0.7
            ]

            // Convert the body dictionary into actual JSON data (bytes)
            // that can be sent over the internet. JSONSerialization turns
            // Swift dictionaries into JSON format. `data(withJSONObject:)`
            // might fail (if the dictionary contains invalid types), so
            // we use `try` to catch any error.
            let jsonData = try JSONSerialization.data(withJSONObject: body)

            // Create a URLRequest, an object that represents an HTTP
            // request we'll send to the server. We give it the URL we
            // stored earlier (the Anthropic API endpoint).
            var request = URLRequest(url: apiURL)
            // Set the HTTP method to POST, this tells the server we're
            // sending data (not just asking to read something, which
            // would be GET). POST is used when we're creating something
            // or sending a message.
            request.httpMethod = "POST"
            // Add the API key to the request headers. "x-api-key" is the
            // standard header name Anthropic uses to receive the API key.
            // This is like showing a membership card to prove we're
            // allowed to use the service.
            request.setValue(apiKey, forHTTPHeaderField: "x-api-key")
            // Tell Anthropic which version of their API we're using.
            // This ensures compatibility, if Anthropic changes their
            // API in the future, our code still works because we specified
            // the version. "2023-06-01" is the version date.
            request.setValue("2023-06-01", forHTTPHeaderField: "anthropic-version")
            // Tell the server we're sending JSON data. "content-type" is
            // a standard HTTP header that describes what kind of data
            // is in the request body. "application/json" means JSON format.
            request.setValue("application/json", forHTTPHeaderField: "content-type")
            // Attach the JSON data to the request body, this is the
            // actual content we're sending to the server. Without this,
            // we'd be sending an empty request.
            request.httpBody = jsonData
            // Set a timeout of 30 seconds, if the server doesn't
            // respond within this time, the request fails automatically.
            // This prevents the app from hanging forever if the network
            // is slow or the server is down.
            request.timeoutInterval = 30

            // Send the request and wait for the response. URLSession is
            // Apple's networking system. `.shared` gives us the default
            // session. `.data(for:)` is an async function that sends the
            // request and returns both the raw data (bytes) and the HTTP
            // response (status code, headers, etc.). We use `try await`
            // because this is an async function that might fail.
            let (data, response) = try await URLSession.shared.data(for: request)

            // Check that we got a proper HTTP response with a 200 status
            // code (which means "OK" / success). `as?` tries to convert
            // the response to an HTTPURLResponse (which has status codes).
            // If the conversion fails or the status isn't 200, we return
            // nil (meaning "no result").
            guard let httpResponse = response as? HTTPURLResponse,
                  httpResponse.statusCode == 200 else {
                // Log the error for debugging, this tells us the API
                // didn't return a successful response.
                print("Claude API error")
                // Return nil to indicate we have no valid result.
                return nil
            }

            // Parse the JSON response data into a Swift dictionary.
            // `jsonObject(with:)` converts raw JSON bytes into a Swift
            // object. `as? [String: Any]` tries to cast it as a dictionary
            // with string keys and any-type values. If it fails, json
            // becomes nil and the guard catches it.
            let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
            // Extract the "content" array from the JSON. In Claude's API,
            // the response has a "content" field containing a list of
            // content blocks. Each block has a "type" and "text". We use
            // optional chaining (`as?`) and guard to safely unwrap this.
            guard let content = json?["content"] as? [[String: Any]],
                  // Get the first content block from the array.
                  let firstBlock = content.first,
                  // Extract the "text" string from the content block,
                  // this is Claude's actual written response.
                  let fullText = firstBlock["text"] as? String else {
                // If any of the above unwrappings fail, return nil,
                // we couldn't understand the response format.
                return nil
            }

            // Extract just the spoken text from the full response.
            // Claude returns a structured format with "RESPONSE:" and
            // "ACTIONS:" sections, this function parses out the spoken
            // part (what the AI says out loud).
            let spokenText = extractSpokenText(from: fullText)
            // Extract the list of actions from the full response.
            // Claude might say "I'll search for that" AND include a
            // "search_web" action, this function picks out the actions.
            let actions = extractActions(from: fullText)

            // Return a ClaudeResult containing both the spoken text
            // and the list of actions. This is the final result that
            // the app will use to speak to the user and perform tasks.
            return ClaudeResult(spokenText: spokenText, actions: actions)
        }
        // Close the do block and start the catch block, this runs if
        // any operation in the do block threw an error.
        catch {
            // Print the error description to the debug console so
            // developers can see what went wrong (network failure,
            // JSON parsing error, etc.).
            print("Claude API error: \(error)")
            // Return nil since we couldn't get a valid response.
            return nil
        }
    }

    // ── processWithOllama(), Offline: calls local Ollama/Llama ─────
    // Ollama is a FREE program that runs AI models locally on your
    // computer. It exposes an HTTP API at http://localhost:11434.
    //
    // HOW TO SET UP:
    //   1. Download Ollama from: https://ollama.ai
    //   2. Install it (it's a normal app installer)
    //   3. Open Terminal and run: ollama pull llama3.2
    //      (this downloads a ~2GB model, takes a few minutes)
    //   4. Keep Ollama running in the background
    //   5. Set AI_MODE=offline in the scheme's environment variables
    //
    // The Ollama API is simpler than Claude's, we send a POST with
    // a "prompt" string and get back {"response": "..."}.
    // This function works the same way as processWithClaude, it sends
    // user text to the AI and returns structured ClaudeResult.
    private func processWithOllama(
        _ userText: String,
        conversationHistory: [ConversationTurn]
    ) async -> ClaudeResult? {
        // ── Build the conversation prompt ──────────────────────
        // Ollama's API takes a single "prompt" string (not separate
        // messages like Claude). We format it with "User:" and
        // "Assistant:" markers so the model understands the roles.
        // The "\n\n" adds a blank line between the user message and
        // the "Assistant:" prefix that tells the model to start
        // generating its reply. Earlier turns from conversationHistory
        // are flattened into this same script format first, mirroring
        // desktop/core/ai.py's _build_ollama_prompt().
        var promptText = ""
        for turn in conversationHistory {
            let roleLabel = turn.role.prefix(1).uppercased() + turn.role.dropFirst()
            promptText += "\(roleLabel): \(turn.content)\n\n"
        }
        promptText += "User: \(userText)\n\nAssistant:"

        // ── Build the JSON request body ────────────────────────
        // This dictionary will be serialized to JSON and sent to
        // Ollama's generate endpoint. The keys match the Ollama
        // HTTP API specification.
        let body: [String: Any] = [
            // Which model to use. "llama3.2" is a good balance of
            // speed and intelligence that runs well on most laptops.
            // Advanced users can change this to any model they've
            // pulled with `ollama pull <model>`.
            "model": "llama3.2",
            // The formatted conversation text we built above.
            // Ollama uses this single string as its input.
            "prompt": promptText,
            // The system prompt that defines the AI's personality.
            // This is sent as a separate field in Ollama's API.
            "system": systemPrompt,
            // Disable streaming, we want Ollama to generate the
            // complete response before returning. If set to true,
            // Ollama would send chunks of text as it generates them,
            // which requires more complex parsing.
            "stream": false,
            // A dictionary of additional generation options that
            // control how the model behaves.
            "options": [
                // Maximum number of tokens (words/parts of words) to
                // generate. 512 tokens is about 400 words, enough for
                // a useful response without letting the AI ramble.
                "num_predict": 512
            ]
        ]

        // ── Send the HTTP request ──────────────────────────────
        // Wrap everything in a do-catch to handle network errors,
        // JSON parsing errors, and connection refused errors (which
        // happen when Ollama isn't running).
        do {
            // Create the URL for Ollama's generate endpoint.
            // Ollama runs on localhost (this iPhone/iPad, actually
            // on the same computer when running in the simulator).
            // Port 11434 is the default port that Ollama listens on.
            let ollamaURL = URL(string: "http://localhost:11434/api/generate")!

            // Create a URLRequest for the Ollama endpoint.
            var request = URLRequest(url: ollamaURL)
            // Set the HTTP method to POST, we're sending data to
            // the server (the prompt) and expecting a response back.
            request.httpMethod = "POST"
            // Tell the server we're sending JSON data in the body.
            // This is a standard HTTP header that lets the server
            // know how to interpret our request.
            request.setValue("application/json", forHTTPHeaderField: "content-type")
            // Serialize the body dictionary to JSON bytes.
            // `try` because JSONSerialization can throw an error if
            // the dictionary contains unsupported types.
            request.httpBody = try JSONSerialization.data(withJSONObject: body)
            // Set a timeout of 60 seconds, Ollama can be slow on
            // smaller machines, especially the first time a model
            // is loaded. We give it twice as long as Claude's timeout.
            request.timeoutInterval = 60

            // Log that we're about to call Ollama (useful for debugging
            // to see which AI provider is being used).
            print("Calling Ollama at http://localhost:11434/api/generate")

            // Send the request and wait for the response asynchronously.
            // `try await` because this is both a throwing and async call.
            let (data, response) = try await URLSession.shared.data(for: request)

            // Check that we got a valid HTTP response with a 200 status.
            // A non-200 response means something went wrong on Ollama's
            // side (e.g., the model doesn't exist).
            guard let httpResponse = response as? HTTPURLResponse,
                  httpResponse.statusCode == 200 else {
                // Log the error status code for debugging.
                print("Ollama returned error status")
                // Return nil, we couldn't get a valid response.
                return nil
            }

            // ── Parse the response JSON ────────────────────────
            // Convert the raw response data bytes into a Swift dictionary.
            // Ollama returns a JSON object like:
            //   {"model": "llama3.2", "response": "...", "done": true}
            guard let json = try JSONSerialization.jsonObject(with: data)
                    as? [String: Any],
                  // Extract the "response" field, this is the text the
                  // AI generated. It's a plain string (not a complex
                  // structure like Claude's content blocks).
                  let fullText = json["response"] as? String else {
                // If we couldn't parse the JSON or the response field
                // is missing, log a message and return nil.
                print("Could not parse Ollama response JSON")
                return nil
            }

            // ── Extract structured data from the response ──────
            // The Ollama model was given the same system prompt as
            // Claude, so its response should follow the same format:
            //   RESPONSE: <spoken text>
            //   ACTIONS:
            //   - action: <type>
            //     params:
            //       <key>: <value>
            // We reuse the same helper functions that processWithClaude
            // uses to extract spoken text and actions.
            let spokenText = extractSpokenText(from: fullText)
            let actions = extractActions(from: fullText)

            // Log success for debugging purposes.
            print("Ollama response received (\(fullText.count) chars)")

            // Return a ClaudeResult containing the spoken text and
            // any actions the AI wants us to execute.
            return ClaudeResult(spokenText: spokenText, actions: actions)
        }
        // Close the do block and catch any errors that occurred during
        // the network request or JSON parsing.
        catch {
            // Log the error for debugging. Common errors include:
            //   - "Connection refused" (Ollama not running)
            //   - "Could not connect to the server" (no network)
            //   - JSON parsing errors (bad response format)
            print("Ollama error: \(error)")
            // Return nil to indicate that the Ollama call failed.
            return nil
        }
    }

    // ── extractSpokenText(), Gets the "RESPONSE:" portion ─────────
    // Define a private helper function that extracts just the spoken
    // text part from the AI's full structured response. Private means
    // only this class can use it, other code doesn't need to know
    // about this internal parsing logic. It takes the full text string
    // and returns just the spoken portion.
    private func extractSpokenText(from fullText: String) -> String {
        // Search for the "RESPONSE:" marker in the text. `.range(of:)`
        // finds where the word "RESPONSE:" appears in the string. If
        // it finds it, we get a range (start and end positions). If
        // not, we get nil and skip to the else.
        if let range = fullText.range(of: "RESPONSE:") {
            // Get everything in the string AFTER the "RESPONSE:" marker.
            // `range.upperBound` is the position right after "RESPONSE:"
            // so `fullText[range.upperBound...]` gives us all the text
            // that comes after it. This is a substring (a slice of the
            // original string).
            let afterResponse = fullText[range.upperBound...]
            // Search for the "ACTIONS:" marker inside the text that
            // comes after "RESPONSE:". We do this because the spoken
            // text is the part between "RESPONSE:" and "ACTIONS:".
            if let actionsRange = afterResponse.range(of: "ACTIONS:") {
                // Extract everything from after "RESPONSE:" up to (but
                // not including) "ACTIONS:". `..<actionsRange.lowerBound`
                // means "everything before the start of ACTIONS:".
                // Then convert it to a regular String and trim whitespace
                // (spaces, newlines) from both ends.
                return String(afterResponse[..<actionsRange.lowerBound]).trimmingCharacters(in: .whitespacesAndNewlines)
            }
            // Close the inner if block, if "ACTIONS:" wasn't found,
            // just return everything after "RESPONSE:" (trimmed), since
            // there are no actions to separate it from.
            return String(afterResponse).trimmingCharacters(in: .whitespacesAndNewlines)
        }
        // Close the outer if block, if "RESPONSE:" wasn't found at
        // all, return the original full text unchanged (we don't know
        // how to parse it, so just use it as-is).
        return fullText
    }

    // ── extractActions(), Gets the "ACTIONS:" portion ─────────────
    // Define a private helper function that extracts the list of
    // actions from the AI's full structured response. It returns an
    // array of ClaudeAction objects. If no actions are found, it
    // returns an empty array instead of nil.
    private func extractActions(from fullText: String) -> [ClaudeAction] {
        // Create an empty array that will hold any actions we find.
        // We'll add to this as we parse the response text.
        var actions: [ClaudeAction] = []

        // Search for the "ACTIONS:" marker in the text. If it's not
        // found, there are no actions to parse, so we exit early and
        // return the empty array. `guard let` is like "if we can find
        // the range, continue; otherwise, return early".
        guard let actionsRange = fullText.range(of: "ACTIONS:") else {
            // Return the empty actions array, no actions available.
            return actions
        }

        // Extract everything after "ACTIONS:" and remove surrounding
        // whitespace. This gives us the raw text that describes the
        // actions the AI wants us to perform.
        let actionsText = fullText[actionsRange.upperBound...].trimmingCharacters(in: .whitespacesAndNewlines)

        // Split the actions text into separate blocks by looking for
        // lines that start with "- action:". Each block represents one
        // action. `components(separatedBy:)` splits a string into an
        // array, using the given string as the divider.
        let blocks = actionsText.components(separatedBy: "- action:")
        // Loop through each block, skipping the first one (`.dropFirst()`).
        // The first block is everything before the first "- action:" marker,
        // which is usually empty or just whitespace.
        for block in blocks.dropFirst() {
            // Split the block into individual lines by breaking at
            // newline characters (\n). First we trim whitespace from
            // the block as a whole, then split it into an array of lines.
            let lines = block.trimmingCharacters(in: .whitespacesAndNewlines)
                .components(separatedBy: "\n")

            // Get the first line of the block, this should be the
            // action type (like "search_web" or "send_sms"). We trim
            // any extra whitespace from it. `lines.first` returns an
            // optional (might be nil if the block is empty).
            guard let firstLine = lines.first?.trimmingCharacters(in: .whitespaces) else {
                // If there's no first line, skip this block and move
                // to the next one (continue the for loop).
                continue
            }

            // Create an empty dictionary to hold the action's parameters.
            // Parameters are key-value pairs that provide extra info,
            // like a search query or a phone number.
            var params: [String: String] = [:]
            // Create a flag that tracks whether we're currently inside
            // the "params:" section of the action block. We start with
            // false because we haven't reached it yet.
            var inParams = false
            // Loop through each line of the block (skipping the first
            // line since that's the action type we already handled).
            for line in lines.dropFirst() {
                // Remove leading/trailing whitespace from the current
                // line so we can check its content cleanly.
                let trimmed = line.trimmingCharacters(in: .whitespaces)
                // Check if this line says "params:", if so, the
                // following lines contain the parameter key-value pairs.
                // We toggle our flag to true to start collecting params.
                if trimmed == "params:" {
                    // Set the flag to true, subsequent lines should be
                    // treated as parameter key-value pairs.
                    inParams = true
                }
                // If we're inside the params section AND the line
                // contains a colon (which separates keys from values).
                // `firstIndex(of:)` finds the first colon in the line.
                else if inParams, let colonIndex = trimmed.firstIndex(of: ":") {
                    // Extract the key, everything before the colon.
                    // `..<colonIndex` means "up to but not including
                    // the colon". Trim whitespace in case there are
                    // spaces around the colon.
                    let key = String(trimmed[..<colonIndex]).trimmingCharacters(in: .whitespaces)
                    // Extract the value, everything after the colon.
                    // `index(after: colonIndex)` skips past the colon
                    // character itself. Trim whitespace here too.
                    let value = String(trimmed[trimmed.index(after: colonIndex)...]).trimmingCharacters(in: .whitespaces)
                    // Store the key-value pair in our params dictionary.
                    // Now other code can look up "query" and get "weather today".
                    params[key] = value
                }
            }

            // Add a new ClaudeAction to our list, using the first line
            // as the action type and all the parsed key-value pairs as
            // the parameters. This appends it to the end of the array.
            actions.append(ClaudeAction(actionType: firstLine, params: params))
        }

        // Return the array of actions we found. If no actions were
        // parsed, this will be an empty array (not nil), which is
        // easier for other code to handle without optional checking.
        return actions
    }
}
