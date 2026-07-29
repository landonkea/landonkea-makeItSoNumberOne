// ─── ClaudeService.swift ─────────────────────────────────────────────
// This file contains all the code needed to talk to Claude (Anthropic's
// AI assistant) from an iPhone app. It sends the user's spoken words to
// Claude over the internet and gets back both a spoken reply and any
// actions Claude wants to execute (like "search the web" or "send a text").
//
// The code uses Apple's built-in networking tools (URLSession) so we
// don't need any extra libraries. We manually build the JSON that the
// Anthropic API expects and manually parse the response JSON.
// ──────────────────────────────────────────────────────────────────────

// Import Apple's Foundation framework — this gives us access to basic
// types like String, URL, Data, JSONSerialization, and URLSession.
// We need these to make network requests and work with JSON data.
import Foundation

// Define a structure (like a simple data container) that holds Claude's
// response. A struct in Swift is a way to group related pieces of data
// together. This one holds the text Claude speaks and any actions it
// wants to perform.
struct ClaudeResult {
    // The text that Claude says out loud (as a String of characters).
    let spokenText: String
    // A list (array) of actions Claude wants executed, like searching
    // the web or sending a text message.
    let actions: [ClaudeAction]
}

// Define a structure that represents a single action Claude wants us
// to perform. For example, "search_web" with a query parameter.
struct ClaudeAction {
    // What kind of action to perform (like "search_web", "send_sms").
    let actionType: String
    // A dictionary (key-value pairs) of extra information for the action.
    // For a web search, this might be ["query": "weather today"].
    // [String: String] means the keys are text and the values are text.
    let params: [String: String]
}

// Define the main class that handles talking to Claude.
// A class is like a blueprint for creating objects. This one is a
// "service" — a reusable component that provides a specific feature
// (in this case, communicating with Claude's API).
class ClaudeService {
    // Create a single shared instance of this class that the whole app
    // can use. This is called the "singleton pattern" — instead of
    // creating multiple copies, everyone shares one. We use `static`
    // to make it a type-level property (belongs to the class itself,
    // not to any specific instance). `shared` is the conventional name.
    static let shared = ClaudeService()

    // Store the API key (a secret password that lets us use Claude).
    // We read it from the device's environment variables (like a
    // system-wide settings dictionary). ProcessInfo.processInfo gives
    // us information about the running app, and .environment gives us
    // the system environment variables. The ?? "" means "if there's no
    // key, use an empty string instead of crashing". This is private
    // so other parts of the app can't accidentally read our secret key.
    private let apiKey = ProcessInfo.processInfo.environment["ANTHROPIC_API_KEY"] ?? ""
    // Store the URL for Claude's API (the web address we send requests
    // to). We force-unwrap with `!` because we know this URL is valid
    // (we typed it correctly in the code). If it were invalid, the app
    // would crash — that's intentional because a bad URL means the
    // app can't work at all. This URL points to Anthropic's message
    // endpoint that accepts our conversation text and returns a reply.
    private let apiURL = URL(string: "https://api.anthropic.com/v1/messages")!

    // Store the "system prompt" — a set of instructions that tells
    // Claude how to behave. This is a multi-line string (triple quotes).
    // We tell Claude to act like the computer from Star Trek's USS
    // Enterprise, to be helpful and calm, and we describe the exact
    // format we want its response to follow. The system prompt is
    // sent with every request so Claude remembers its role.
    private let systemPrompt = """
        You are the computer from the USS Enterprise (NCC-1701-D).
        You are helpful, precise, and calm.
        
        OUTPUT FORMAT:
        RESPONSE: <what you say out loud>
        
        ACTIONS:
        - action: <type>
          params:
            <key>: <value>
    """

    // Define the main function that sends text to Claude and gets a
    // response back. It takes a String (the user's spoken words) and
    // returns an optional ClaudeResult (either a valid result or nil
    // if something went wrong). The `async` keyword means this function
    // can pause and wait for network operations without freezing the
    // app's interface. The `->` arrow shows what type we return.
    func process(_ userText: String) async -> ClaudeResult? {
        // Check if the API key is empty (not set). `guard` is a Swift
        // keyword that checks a condition — if it fails, we MUST exit
        // the function (via return). The `!` means "not" — so this
        // checks "if apiKey is NOT empty". If it IS empty, we enter
        // the else block (actually the guard body) and return early.
        guard !apiKey.isEmpty else {
            // Print a message to the debug console so developers know
            // the API key is missing. This doesn't show to users — it's
            // only visible when running through Xcode.
            print("ANTHROPIC_API_KEY not set")
            // Since we don't have a real API key, return a fake response
            // so the app doesn't crash. We create a ClaudeResult with
            // a friendly message telling the user to set up their key
            // and an empty list of actions (no actions to perform).
            return ClaudeResult(
                spokenText: "I am configured and ready, Captain. Please add your Anthropic API key to the environment variables.",
                actions: []
            )
        }
        // Close the else block for the key check.

        // Open a do-catch block for error handling. This lets us try
        // operations that might fail (like network calls or JSON parsing)
        // and catch any errors that occur. If anything inside the `do`
        // block throws an error, execution jumps to the `catch` block.
        do {
            // Create the list of messages to send to Claude. Each message
            // has a "role" (who's speaking — here "user" means the human)
            // and "content" (what they said). We put this inside an array
            // (square brackets) because Claude expects a list of messages
            // forming a conversation. `userText` is the transcribed speech.
            let messages: [[String: Any]] = [
                ["role": "user", "content": userText]
            ]
            // Close the messages array.

            // Build the full request body — a dictionary of all the
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
                // The system prompt — our instructions to Claude about
                // how to behave and what format to use for the response.
                "system": systemPrompt,
                // The conversation messages (just the user's text for now).
                "messages": messages,
                // A "temperature" setting for creativity. 0.7 means some
                // creativity but not too random. 0 would be very predictable,
                // 1.0 would be very creative/random.
                "temperature": 0.7
            ]
            // Close the body dictionary.

            // Convert the body dictionary into actual JSON data (bytes)
            // that can be sent over the internet. JSONSerialization turns
            // Swift dictionaries into JSON format. `data(withJSONObject:)`
            // might fail (if the dictionary contains invalid types), so
            // we use `try` to catch any error.
            let jsonData = try JSONSerialization.data(withJSONObject: body)

            // Create a URLRequest — an object that represents an HTTP
            // request we'll send to the server. We give it the URL we
            // stored earlier (the Anthropic API endpoint).
            var request = URLRequest(url: apiURL)
            // Set the HTTP method to POST — this tells the server we're
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
            // This ensures compatibility — if Anthropic changes their
            // API in the future, our code still works because we specified
            // the version. "2023-06-01" is the version date.
            request.setValue("2023-06-01", forHTTPHeaderField: "anthropic-version")
            // Tell the server we're sending JSON data. "content-type" is
            // a standard HTTP header that describes what kind of data
            // is in the request body. "application/json" means JSON format.
            request.setValue("application/json", forHTTPHeaderField: "content-type")
            // Attach the JSON data to the request body — this is the
            // actual content we're sending to the server. Without this,
            // we'd be sending an empty request.
            request.httpBody = jsonData
            // Set a timeout of 30 seconds — if the server doesn't
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
            // If the conversion fails or the status isn't 200, we enter
            // the else body and return nil (meaning "no result").
            guard let httpResponse = response as? HTTPURLResponse,
                  httpResponse.statusCode == 200 else {
                // Log the error for debugging — this tells us the API
                // didn't return a successful response.
                print("Claude API error")
                // Return nil to indicate we have no valid result.
                return nil
            }
            // Close the guard else block.

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
                  // Extract the "text" string from the content block —
                  // this is Claude's actual written response.
                  let fullText = firstBlock["text"] as? String else {
                // If any of the above unwrappings fail, return nil —
                // we couldn't understand the response format.
                return nil
            }
            // Close the guard else block.

            // Extract just the spoken text from the full response.
            // Claude returns a structured format with "RESPONSE:" and
            // "ACTIONS:" sections — this function parses out the spoken
            // part (what Claude says out loud).
            let spokenText = extractSpokenText(from: fullText)
            // Extract the list of actions from the full response.
            // Claude might say "I'll search for that" AND include a
            // "search_web" action — this function picks out the actions.
            let actions = extractActions(from: fullText)

            // Return a ClaudeResult containing both the spoken text
            // and the list of actions. This is the final result that
            // the app will use to speak to the user and perform tasks.
            return ClaudeResult(spokenText: spokenText, actions: actions)
            // No explicit close needed — the return ends execution here.
        }
        // Close the do block and start the catch block — this runs if
        // any operation in the do block threw an error.
        catch {
            // Print the error description to the debug console so
            // developers can see what went wrong (network failure,
            // JSON parsing error, etc.).
            print("Claude service error: \(error)")
            // Return nil since we couldn't get a valid response.
            return nil
        }
        // Close the catch block.
    }
    // Close the process function.

    // Define a private helper function that extracts just the spoken
    // text part from Claude's full structured response. Private means
    // only this class can use it — other code doesn't need to know
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
            // Close the inner if block — if "ACTIONS:" wasn't found,
            // just return everything after "RESPONSE:" (trimmed), since
            // there are no actions to separate it from.
            return String(afterResponse).trimmingCharacters(in: .whitespacesAndNewlines)
        }
        // Close the outer if block — if "RESPONSE:" wasn't found at
        // all, return the original full text unchanged (we don't know
        // how to parse it, so just use it as-is).
        return fullText
    }
    // Close the extractSpokenText function.

    // Define a private helper function that extracts the list of
    // actions from Claude's full structured response. It returns an
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
            // Return the empty actions array — no actions available.
            return actions
        }
        // Close the guard else block.

        // Extract everything after "ACTIONS:" and remove surrounding
        // whitespace. This gives us the raw text that describes the
        // actions Claude wants us to perform.
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

            // Get the first line of the block — this should be the
            // action type (like "search_web" or "send_sms"). We trim
            // any extra whitespace from it. `lines.first` returns an
            // optional (might be nil if the block is empty).
            guard let firstLine = lines.first?.trimmingCharacters(in: .whitespaces) else {
                // If there's no first line, skip this block and move
                // to the next one (continue the for loop).
                continue
            }
            // Close the guard else block.

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
                // Check if this line says "params:" — if so, the
                // following lines contain the parameter key-value pairs.
                // We toggle our flag to true to start collecting params.
                if trimmed == "params:" {
                    // Set the flag to true — subsequent lines should be
                    // treated as parameter key-value pairs.
                    inParams = true
                }
                // If we're inside the params section AND the line
                // contains a colon (which separates keys from values).
                // `firstIndex(of:)` finds the first colon in the line.
                else if inParams, let colonIndex = trimmed.firstIndex(of: ":") {
                    // Extract the key — everything before the colon.
                    // `..<colonIndex` means "up to but not including
                    // the colon". Trim whitespace in case there are
                    // spaces around the colon.
                    let key = String(trimmed[..<colonIndex]).trimmingCharacters(in: .whitespaces)
                    // Extract the value — everything after the colon.
                    // `index(after: colonIndex)` skips past the colon
                    // character itself. Trim whitespace here too.
                    let value = String(trimmed[trimmed.index(after: colonIndex)...]).trimmingCharacters(in: .whitespaces)
                    // Store the key-value pair in our params dictionary.
                    // Now other code can look up "query" and get "weather today".
                    params[key] = value
                }
                // Close the else-if block — if we're not in the params
                // section or the line doesn't have a colon, we just
                // skip it (it's probably empty or irrelevant).
            }
            // Close the for line loop.

            // Add a new ClaudeAction to our list, using the first line
            // as the action type and all the parsed key-value pairs as
            // the parameters. This appends it to the end of the array.
            actions.append(ClaudeAction(actionType: firstLine, params: params))
        }
        // Close the for block loop.

        // Return the array of actions we found. If no actions were
        // parsed, this will be an empty array (not nil), which is
        // easier for other code to handle without optional checking.
        return actions
    }
    // Close the extractActions function.
}
// Close the ClaudeService class.
