// ───────────────────────────────────────────────────────────────────
// ClaudeService.kt — talks to Claude (Android)
// ───────────────────────────────────────────────────────────────────
// This module sends the user's transcribed speech to Claude
// (via Anthropic's API) and parses the response into spoken text
// and actions.
//
// It uses OkHttp for network requests and org.json for parsing
// the response. Both are standard Android libraries.
// ───────────────────────────────────────────────────────────────────

// This line declares the "package" (folder/namespace) this file belongs to.
// Packages keep code organized and prevent name conflicts with other apps.
package com.landonkea.makeitso

// ── Imports ───────────────────────────────────────────────────────
// Import statements bring in code from Android and third-party libraries so this file can use them.

// Dispatchers provides pre-built thread pools (e.g., IO for network, Main for UI updates).
import kotlinx.coroutines.Dispatchers
// withContext lets a coroutine switch which thread it runs on (e.g., background → main).
import kotlinx.coroutines.withContext
// toMediaType() converts a string like "application/json" into a MediaType object for HTTP headers.
import okhttp3.MediaType.Companion.toMediaType
// OkHttpClient is the core class for making HTTP requests (like a web browser inside your code).
import okhttp3.OkHttpClient
// Request represents a single HTTP request (URL, headers, body — everything needed to call an API).
import okhttp3.Request
// toRequestBody() wraps a string as the body of an HTTP request so it can be sent over the network.
import okhttp3.RequestBody.Companion.toRequestBody
// JSONArray builds ordered lists in JSON format, like ["apple", "banana"].
import org.json.JSONArray
// JSONObject builds key-value objects in JSON format, like {"name": "Landon"}.
import org.json.JSONObject
// TimeUnit provides readable time constants like SECONDS, MINUTES, etc. for timeout settings.
import java.util.concurrent.TimeUnit

// ── Data class for Claude's response ────────────────────────────
// A "data class" is a Kotlin shortcut — it automatically creates
// toString(), equals(), hashCode(), and copy() methods for you.
// This one stores what Claude says and what actions to take.

// "data class" means Kotlin auto-generates useful boilerplate methods for this class.
data class ClaudeResult(
    // "val" means read-only (immutable). spokenText holds the sentence Claude wants spoken aloud.
    val spokenText: String,
    // actions is a list of Action objects — each one is a command Claude wants executed.
    val actions: List<Action>
)

// Action represents a single command from Claude, like "search the web" or "open an app".
data class Action(
    // type tells us what KIND of action, e.g., "search_web", "open_app", "send_sms".
    val type: String,
    // params holds extra details as key-value pairs, e.g., {"query": "cats", "number": "555-1234"}.
    val params: Map<String, String>
)

// "object" in Kotlin creates a singleton — exactly one instance exists for the entire app lifetime.
// ClaudeService groups all Claude-related functions together in one place.
object ClaudeService {

    // ── The system prompt (same as the desktop version) ─────────
    // Tells Claude to act like the Enterprise computer and respond
    // in the structured format we expect.
    // "private" means only code inside ClaudeService can access this.
    // "val" means this value is set once and never changes (a constant).
    private val SYSTEM_PROMPT = """
        You are the computer from the USS Enterprise (NCC-1701-D).
        You are helpful, precise, and calm.
        
        OUTPUT FORMAT:
        RESPONSE: <what you say out loud>
        
        ACTIONS:
        - action: <type>
          params:
            <key>: <value>
    """.trimIndent()
    // .trimIndent() removes the leading whitespace from every line of the raw string,
    // so the actual text doesn't have extra indentation when sent to Claude.

    // ── Process user text through Claude ───────────────────────
    // "suspend" means this function is a coroutine — it can pause without blocking the UI thread.
    // It takes the user's speech text and returns a ClaudeResult, or null if something fails.
    suspend fun process(userText: String): ClaudeResult? {
        // withContext(Dispatchers.IO) switches execution to a background thread pool meant for I/O
        // (network requests, file reads, etc.). The code inside the braces runs on that background thread.
        return withContext(Dispatchers.IO) {
            // try-catch is error handling: if anything in "try" throws an exception, we jump to "catch"
            // instead of crashing the app. This makes the app more robust.
            try {
                // ── Build the API request ───────────────────────
                // OkHttpClient.Builder() uses the Builder pattern — we chain method calls to configure the client.
                val client = OkHttpClient.Builder()
                    // connectTimeout: how long to wait (30 seconds) for the initial connection to the server.
                    .connectTimeout(30, TimeUnit.SECONDS)
                    // readTimeout: how long to wait (30 seconds) for data to arrive after connecting.
                    .readTimeout(30, TimeUnit.SECONDS)
                    // build() finalizes the configuration and creates the OkHttpClient object.
                    .build()

                // The URL for Claude's messages API endpoint (the address we send HTTP requests to).
                val url = "https://api.anthropic.com/v1/messages"

                // Build the JSON payload as a JSONObject. "apply" lets us call put() repeatedly
                // on the same object without writing "payload.put()" each time.
                val payload = JSONObject().apply {
                    // "model" specifies which Claude version to use. This string is the exact model ID.
                    put("model", "claude-sonnet-4-20250514")
                    // "max_tokens" limits how many tokens (roughly ¾ of a word) Claude can generate in its reply.
                    put("max_tokens", 1024)
                    // "system" sends the system prompt that sets Claude's personality and output format.
                    put("system", SYSTEM_PROMPT)

                    // "messages" is an array of conversation turns (each turn is a JSON object with role + content).
                    put("messages", JSONArray().apply {
                        // Add one message object to the array — the user's current utterance.
                        put(JSONObject().apply {
                            // "role": "user" tells Claude this message comes from the human speaking.
                            put("role", "user")
                            // "content": the actual transcribed text the user said.
                            put("content", userText)
                        })
                    })

                    // "temperature" controls randomness: 0.0 = same output every time, 1.0 = very creative.
                    // 0.7 gives a good balance between predictable and creative responses.
                    put("temperature", 0.7)
                }

                // Build the actual HTTP request object (the network message we'll send to Anthropic).
                val request = Request.Builder()
                    // Set the destination URL for this request.
                    .url(url)
                    // Add an HTTP header with our secret API key so Anthropic knows who we are.
                    // BuildConfig.ANTHROPIC_API_KEY is generated from BuildConfig during compilation.
                    .addHeader("x-api-key", BuildConfig.ANTHROPIC_API_KEY)
                    // Tell the server which version of the Anthropic API we expect to talk to.
                    .addHeader("anthropic-version", "2023-06-01")
                    // Declare that our request body contains JSON (so the server knows how to parse it).
                    .addHeader("Content-Type", "application/json")
                    // Set the HTTP method to POST and attach our JSON payload as the request body.
                    // toString() turns JSONObject into a string, toRequestBody() wraps it for HTTP.
                    .post(payload.toString().toRequestBody("application/json".toMediaType()))
                    // build() creates the final Request object from all the configuration above.
                    .build()

                // ── Execute the request ─────────────────────────
                // client.newCall(request).execute() actually sends the HTTP request and blocks until we get a response.
                val response = client.newCall(request).execute()
                // Check if the server returned a success status code (200–299 range).
                if (!response.isSuccessful) {
                    // If the request failed (e.g., 400 Bad Request or 500 Server Error), return null.
                    return@withContext null
                }

                // Extract the response body as a string. The "?:" elvis operator returns null if body is null.
                val body = response.body?.string() ?: return@withContext null
                // Parse the JSON string into a JSONObject so we can access its fields programmatically.
                val json = JSONObject(body)

                // ── Parse the response ─────────────────────────
                // Get the "content" array from Claude's response. Content holds one or more text blocks.
                val content = json.getJSONArray("content")
                // If content is empty, Claude didn't return any text — nothing to process, return null.
                if (content.length() == 0) return@withContext null

                // Get the first (and usually only) text block from the content array.
                val textBlock = content.getJSONObject(0)
                // Extract the actual text string from the "text" field of the text block.
                val fullText = textBlock.getString("text")

                // Parse the structured text to find what Claude wants to SAY (the spoken response part).
                val spokenText = extractSpokenText(fullText)
                // Parse the structured text to find what Claude wants us to DO (the action commands).
                val actions = extractActions(fullText)

                // Return both the spoken text and the parsed actions packaged together in a ClaudeResult.
                return@withContext ClaudeResult(spokenText, actions)

            } catch (e: Exception) {
                // If ANY error happened above (network failure, bad JSON, timeout, etc.), catch it here.
                // Print the full error details to Logcat (Android's console) so we can debug later.
                e.printStackTrace()
                // Return null to signal to the caller that processing failed.
                return@withContext null
            }
        }
        // End of withContext(Dispatchers.IO) — execution switches back to the original thread here.
    }
    // End of the process() function.

    // ── Extract the spoken response from Claude's format ───────
    // This function searches for "RESPONSE:" in Claude's output and grabs whatever text follows it.
    private fun extractSpokenText(fullText: String): String {
        // Define a regular expression (pattern) that finds "RESPONSE:" followed by any text,
        // stopping when it hits "ACTIONS:" on a new line or the end of the string.
        // DOT_MATCHES_ALL lets the dot (.) match newline characters too.
        val responseRegex = Regex("RESPONSE:\\s*(.+?)(?=\\n\\s*ACTIONS:|\\z)", RegexOption.DOT_MATCHES_ALL)
        // Search the full text for a substring that matches the pattern above.
        val match = responseRegex.find(fullText)
        // If a match was found, get the captured group (the spoken text), trim whitespace, and return it.
        // If no match was found (?), return the entire original text as a fallback.
        return match?.groupValues?.getOrNull(1)?.trim() ?: fullText
    }
    // End of extractSpokenText().

    // ── Extract actions from Claude's format ───────────────────
    // This function looks for "ACTIONS:" in Claude's response and parses each "- action:" block.
    private fun extractActions(fullText: String): List<Action> {
        // Create an empty mutable list that we'll fill with Action objects as we parse them.
        val actions = mutableListOf<Action>()
        // Define a regex that finds "ACTIONS:" and then captures everything that follows it.
        val actionsRegex = Regex("ACTIONS:\\s*(.+)", RegexOption.DOT_MATCHES_ALL)
        // Try to find the actions section within the full text response.
        val match = actionsRegex.find(fullText)

        // Only process if we actually found the ACTIONS: section in Claude's output.
        if (match != null) {
            // Extract the captured text (everything after "ACTIONS:") and trim surrounding whitespace.
            val actionsText = match.groupValues[1].trim()
            // Split the actions text into individual action blocks by looking for lines starting with "- action:".
            val blocks = actionsText.split("\n\\s*-\\s+action:".toRegex())
            // Loop through each block, skipping the first one (which is text before any "- action:").
            for (block in blocks.drop(1)) {
                // Split the current action block into separate lines for parsing.
                val lines = block.trim().split("\n")
                // The first line of the block is the action type string. If it's null, skip this block.
                val actionType = lines.firstOrNull()?.trim() ?: continue

                // Create an empty map to hold the action's parameters (key-value pairs like query=cats).
                val params = mutableMapOf<String, String>()
                // Boolean flag to track whether we've entered the "params:" section of this block.
                var inParams = false
                // Loop through all lines after the first one (the action type line).
                for (line in lines.drop(1)) {
                    // Remove leading/trailing whitespace from the current line.
                    val trimmed = line.trim()
                    // If the line is exactly "params:", switch into parameter-parsing mode.
                    if (trimmed == "params:") {
                        inParams = true
                    // If we're inside params and the line has a colon, it's a key: value pair.
                    } else if (inParams && trimmed.contains(":")) {
                        // Split the line at the first colon into exactly two parts (key and value).
                        val parts = trimmed.split(":", limit = 2)
                        // Store the key-value pair in the params map (trimming whitespace from both).
                        params[parts[0].trim()] = parts[1].trim()
                    }
                    // If we're not in params or the line has no colon, we ignore it.
                }
                // End of parameter-parsing loop.

                // Create a new Action object from the parsed type and params, and add it to our list.
                actions.add(Action(actionType, params))
            }
            // End of block-processing loop.
        }
        // If no match was found, actions list stays empty — the caller will handle that.

        // Return the list of parsed actions (may be empty if none were found or parsing failed).
        return actions
    }
    // End of extractActions().
}
// End of ClaudeService object.
