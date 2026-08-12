// ───────────────────────────────────────────────────────────────────
// ClaudeService.kt, talks to Claude (Online) or Ollama (Offline)
// ───────────────────────────────────────────────────────────────────
// This module sends the user's transcribed speech to either:
//   1. ONLINE mode  → Anthropic's Claude API (cloud, requires internet + API key)
//   2. OFFLINE mode → Ollama running on localhost:11434 (local, free, no internet needed)
//
// The "auto" mode tries ONLINE first, and if that fails, falls back to OFFLINE.
// This is the same dual-mode pattern used in the desktop Python version.
//
// It uses OkHttp for network requests and org.json for parsing
// responses. Both are standard Android libraries.
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
// Request represents a single HTTP request (URL, headers, body, everything needed to call an API).
import okhttp3.Request
// Response represents the HTTP response that comes back from a server after a Request is sent.
import okhttp3.Response
// toRequestBody() wraps a string as the body of an HTTP request so it can be sent over the network.
import okhttp3.RequestBody.Companion.toRequestBody
// JSONArray builds ordered lists in JSON format, like ["apple", "banana"].
import org.json.JSONArray
// JSONObject builds key-value objects in JSON format, like {"name": "Landon"}.
import org.json.JSONObject
// TimeUnit provides readable time constants like SECONDS, MINUTES, etc. for timeout settings.
import java.util.concurrent.TimeUnit

// ── Data class for the assistant's response ─────────────────────
// A "data class" is a Kotlin shortcut, it automatically creates
// toString(), equals(), hashCode(), and copy() methods for you.
// This one stores what the assistant says and what actions to take.
// It works identically whether the response came from Claude or Ollama.

// "data class" means Kotlin auto-generates useful boilerplate methods for this class.
data class ClaudeResult(
    // "val" means read-only (immutable). spokenText holds the sentence the assistant wants spoken aloud.
    val spokenText: String,
    // actions is a list of Action objects, each one is a command the assistant wants executed.
    val actions: List<Action>
)

// Action represents a single command from the assistant, like "search the web" or "open an app".
data class Action(
    // type tells us what KIND of action, e.g., "search_web", "open_app", "send_sms".
    val type: String,
    // params holds extra details as key-value pairs, e.g., {"query": "cats", "number": "555-1234"}.
    val params: Map<String, String>
)

// ── Conversation history turn ────────────────────────────────────
// One remembered exchange, mirroring the desktop Python version's
// {"role": "user"/"assistant", "content": "..."} dict shape (see
// desktop/make_it_so.py's _record_exchange()). Kept as its own small
// data class (rather than a raw Pair<String, String>) so call sites
// read as "role" / "content" instead of ".first" / ".second".
data class ConversationTurn(
    // "user" or "assistant", who said this.
    val role: String,
    // The text of that turn. For assistant turns this is stored as
    // "RESPONSE: <spokenText>" (matching the shared RESPONSE:/
    // ACTIONS: prompt format both providers are told to use), so a
    // replayed turn still looks like a normal assistant reply.
    val content: String
)

// "object" in Kotlin creates a singleton, exactly one instance exists for the entire app lifetime.
// ClaudeService groups all assistant-related functions together in one place,
// including both the online (Claude) and offline (Ollama) providers.
object ClaudeService {

    // ── The system prompt (same as the desktop version) ─────────
    // Tells the assistant to act like the Enterprise computer and respond
    // in the structured format we expect. Used by BOTH Claude and Ollama.
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
    // so the actual text doesn't have extra indentation when sent to the assistant.

    // ── Shared HTTP clients (created once, reused for every call) ─
    // WHAT: OkHttpClient is expensive to construct, each instance owns its own connection
    // pool (a cache of open TCP/TLS connections kept warm for reuse), a dispatcher thread
    // pool, and a DNS cache. HOW: because ClaudeService is a Kotlin "object" (singleton),
    // these "by lazy" properties are built exactly once, the first time each is touched, and
    // then reused for the lifetime of the app process, every call to processWithClaude() or
    // processWithOllama() reuses the same client instead of building a new one. WHY: building
    // a fresh OkHttpClient per request throws away that connection pool every time, so the
    // next request has to renegotiate a new TCP connection (and TLS handshake, for HTTPS)
    // from scratch instead of reusing a "keep-alive" connection already open to the same
    // host, wasted latency and CPU/battery on every single request. Two separate clients are
    // kept (rather than one shared one) because the two providers have deliberately different
    // timeout profiles below.

    // claudeClient: talks to Anthropic's cloud API over the internet.
    private val claudeClient: OkHttpClient by lazy {
        OkHttpClient.Builder()
            // connectTimeout: how long to wait for the initial connection to the server.
            .connectTimeout(30, TimeUnit.SECONDS)
            // readTimeout: how long to wait for data once connected. Kept generous since
            // Claude's response can take a while to generate for longer answers.
            .readTimeout(30, TimeUnit.SECONDS)
            // writeTimeout: how long to wait while sending our request body to the server.
            .writeTimeout(30, TimeUnit.SECONDS)
            .build()
    }

    // ollamaClient: talks to a local Ollama server on the same machine.
    private val ollamaClient: OkHttpClient by lazy {
        OkHttpClient.Builder()
            // connectTimeout: short, because it's local, if Ollama isn't running, fail fast.
            .connectTimeout(10, TimeUnit.SECONDS)
            // readTimeout: generous, because local LLMs can be slow on CPU-only machines.
            .readTimeout(60, TimeUnit.SECONDS)
            // writeTimeout: matches connectTimeout, our request bodies are small local calls.
            .writeTimeout(10, TimeUnit.SECONDS)
            .build()
    }

    // ── Main entry point: process user text with auto-fallback ──
    // "suspend" means this function is a coroutine, it can pause without blocking the UI thread.
    // It takes the user's speech text and an optional mode string ("auto", "online", or "offline").
    // `conversationHistory` is the bounded list of prior turns (see ConversationTurn above) that
    // the caller (MainActivity) maintains across cycles, passing it in lets both providers give
    // context-aware replies (e.g. "open Safari" then "now search it" knows what "it" refers to),
    // matching the desktop Python version's conversation_history behavior. Defaults to an empty
    // list so existing callers that don't pass one keep working exactly as before.
    // `apiKey` is the Anthropic API key to send with the request. Defaults to the
    // BuildConfig-injected value (see app/build.gradle.kts -> ANTHROPIC_API_KEY) for backward
    // compatibility, but MainActivity always passes the resolved value from
    // SettingsRepository.getAnthropicApiKey(), the user's saved key if they've set one,
    // otherwise that same BuildConfig default, so a key change in Settings takes effect
    // immediately without needing to touch this default.
    // Returns a ClaudeResult, or null if ALL providers fail.
    suspend fun process(
        userText: String,
        mode: String = "auto",
        conversationHistory: List<ConversationTurn> = emptyList(),
        apiKey: String = BuildConfig.ANTHROPIC_API_KEY
    ): ClaudeResult? {
        // withContext(Dispatchers.IO) switches execution to a background thread pool meant for I/O
        // (network requests, file reads, etc.). The code inside the braces runs on that background thread.
        return withContext(Dispatchers.IO) {
            // ── Try online (Claude API) first ──────────────────
            // If mode is "auto" or "online", attempt the cloud-based Claude API call.
            if (mode == "auto" || mode == "online") {
                // Call the private function that handles the Claude API request.
                val onlineResult = processWithClaude(userText, conversationHistory, apiKey)
                // If the online call succeeded (result is not null)...
                if (onlineResult != null) {
                    // ...return the Claude result immediately, no need to try offline.
                    return@withContext onlineResult
                }
                // If online returned null, we fall through to the offline attempt below.
                // This fallback is only triggered if mode was "auto" (not explicitly "online").
            }

            // ── Fall back to offline (Ollama) ──────────────────
            // If mode is "auto" (and online failed) or mode is explicitly "offline"...
            if (mode == "auto" || mode == "offline") {
                // ...try the local Ollama instance running on the same machine.
                return@withContext processWithOllama(userText, conversationHistory)
                // processWithOllama will return null if the local server is unreachable or fails.
            }

            // If mode was "online" and it failed, we reach here and return null.
            // If mode was something unexpected, we also return null as a safety net.
            return@withContext null
        }
        // End of withContext(Dispatchers.IO), execution switches back to the original thread here.
    }
    // End of process(), the dual-mode entry point.

    // ── Online provider: talk to Claude via Anthropic API ──────
    // This is the original implementation, extracted into its own private function.
    // It sends the user text to Anthropic's cloud API and parses the structured response.
    // "private" means only other functions inside ClaudeService can call this.
    // "suspend" means it's a coroutine and can be paused.
    private suspend fun processWithClaude(
        userText: String,
        conversationHistory: List<ConversationTurn>,
        apiKey: String
    ): ClaudeResult? {
        // withContext(Dispatchers.IO) runs the network code on a background I/O thread.
        return withContext(Dispatchers.IO) {
            // try-catch is error handling: if anything in "try" throws an exception, we jump to "catch"
            // instead of crashing the app. This makes the app more robust.
            try {
                // ── Build the API request ──────────────────────
                // Reuse the shared claudeClient (built once, lazily, above) instead of
                // constructing a new OkHttpClient here, see the comment on claudeClient
                // for why a fresh client per call would be wasteful.
                val client = claudeClient

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
                    // Earlier turns from conversationHistory come first (oldest to newest, the
                    // order Claude's API requires), then the user's brand-new utterance last.
                    put("messages", JSONArray().apply {
                        // Replay each prior turn in its original role/content shape.
                        for (turn in conversationHistory) {
                            put(JSONObject().apply {
                                put("role", turn.role)
                                put("content", turn.content)
                            })
                        }
                        // Add one message object to the array, the user's current utterance.
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
                    // Resolved by the caller (see process()'s apiKey parameter doc above), either
                    // the user's saved Settings key or the BuildConfig-injected default.
                    .addHeader("x-api-key", apiKey)
                    // Tell the server which version of the Anthropic API we expect to talk to.
                    .addHeader("anthropic-version", "2023-06-01")
                    // Declare that our request body contains JSON (so the server knows how to parse it).
                    .addHeader("Content-Type", "application/json")
                    // Set the HTTP method to POST and attach our JSON payload as the request body.
                    // toString() turns JSONObject into a string, toRequestBody() wraps it for HTTP.
                    .post(payload.toString().toRequestBody("application/json".toMediaType()))
                    // build() creates the final Request object from all the configuration above.
                    .build()

                // ── Execute the request and parse the response ──
                // client.newCall(request).execute() actually sends the HTTP request and blocks until we get a response.
                val response = client.newCall(request).execute()
                // buildResultFromResponse() does all the shared work of checking success, reading
                // the body, and parsing it into a ClaudeResult, see its comment below for why
                // this logic is shared between the Claude and Ollama providers instead of
                // duplicated. We only need to tell it HOW to pull the raw generated text out of
                // Claude's specific JSON shape, via this lambda (an inline, unnamed function).
                return@withContext buildResultFromResponse(response) { json ->
                    // Get the "content" array from Claude's response. Content holds one or more text blocks.
                    val content = json.getJSONArray("content")
                    // If content is empty, Claude didn't return any text, nothing to process, signal null.
                    if (content.length() == 0) {
                        null
                    } else {
                        // Get the first (and usually only) text block, and its "text" field.
                        content.getJSONObject(0).getString("text")
                    }
                }

            } catch (e: Exception) {
                // If ANY error happened above (network failure, bad JSON, timeout, etc.), catch it here.
                // Print the full error details to Logcat (Android's console) so we can debug later.
                e.printStackTrace()
                // Return null to signal to the caller that processing failed.
                // The caller (process()) will then try the offline fallback if mode is "auto".
                return@withContext null
            }
        }
        // End of withContext(Dispatchers.IO).
    }
    // End of processWithClaude(), the online provider.

    // ── Offline provider: talk to Ollama on localhost ──────────
    // This function calls a local Ollama server at http://localhost:11434/api/generate.
    // Ollama must be running on the same machine (e.g., a laptop serving the Android emulator).
    // It uses the "llama3.2" model and sends the same system prompt + user text.
    // "private" means only other functions inside ClaudeService can call this.
    // "suspend" means it's a coroutine and can be paused.
    private suspend fun processWithOllama(
        userText: String,
        conversationHistory: List<ConversationTurn>
    ): ClaudeResult? {
        // withContext(Dispatchers.IO) runs the network code on a background I/O thread.
        return withContext(Dispatchers.IO) {
            // try-catch is error handling: if anything in "try" throws an exception, we jump to "catch"
            // instead of crashing the app.
            try {
                // ── Build the API request ──────────────────────
                // Reuse the shared ollamaClient (built once, lazily, above) instead of
                // constructing a new OkHttpClient here, see the comment on ollamaClient
                // for why a fresh client per call would be wasteful.
                val client = ollamaClient

                // The URL for Ollama's generate API endpoint (local server, no internet needed).
                val url = "http://localhost:11434/api/generate"

                // Build the JSON payload as a JSONObject. "apply" lets us call put() repeatedly.
                val payload = JSONObject().apply {
                    // "model" specifies which Ollama model to use. "llama3.2" is the default local model.
                    // The user must have this model downloaded via `ollama pull llama3.2`.
                    put("model", "llama3.2")
                    // "prompt" is the main text input from the user, prefixed with any earlier
                    // turns (see buildOllamaPrompt() below) so Ollama's single-string prompt
                    // format still carries conversation context, the same way Claude's
                    // structured "messages" array does above.
                    put("prompt", buildOllamaPrompt(userText, conversationHistory))
                    // "system" sends the system prompt that sets the assistant's personality and output format.
                    // In Ollama's API, "system" is a top-level field (not part of messages).
                    put("system", SYSTEM_PROMPT)
                    // "stream": false tells Ollama to wait for the complete response before returning.
                    // When streaming is true, Ollama sends tokens one by one (more complex to handle).
                    put("stream", false)
                    // "options" is a JSON object for model-specific settings like token limits.
                    put("options", JSONObject().apply {
                        // "num_predict" limits how many tokens the model can generate in its reply.
                        // 512 is roughly 400 words, enough for a concise voice assistant response.
                        put("num_predict", 512)
                    })
                }

                // Build the actual HTTP request object (the network message we'll send to Ollama).
                val request = Request.Builder()
                    // Set the destination URL for this request (local Ollama server).
                    .url(url)
                    // Declare that our request body contains JSON (so Ollama knows how to parse it).
                    .addHeader("Content-Type", "application/json")
                    // Set the HTTP method to POST and attach our JSON payload as the request body.
                    .post(payload.toString().toRequestBody("application/json".toMediaType()))
                    // build() creates the final Request object from all the configuration above.
                    .build()

                // ── Execute the request and parse the response ──
                // client.newCall(request).execute() sends the HTTP request and blocks until we get a response.
                val response = client.newCall(request).execute()
                // buildResultFromResponse() (shared with processWithClaude() above) handles checking
                // success, reading the body, and building the final ClaudeResult. We only supply the
                // Ollama-specific detail: Ollama's /api/generate returns a JSON object with a
                // "response" field containing the full text generated by the model, a different
                // shape from Claude's "content" array, which is why this lambda differs from the one
                // in processWithClaude() even though everything else about handling the response is
                // identical.
                return@withContext buildResultFromResponse(response) { json -> json.getString("response") }

            } catch (e: Exception) {
                // If ANY error happened above (connection refused, timeout, bad JSON, etc.), catch it here.
                // Print the full error details to Logcat (Android's console) so we can debug later.
                e.printStackTrace()
                // Return null to signal to the caller that the offline provider also failed.
                return@withContext null
            }
        }
        // End of withContext(Dispatchers.IO).
    }
    // End of processWithOllama(), the offline provider.

    // ── Build Ollama's single-string prompt from history + new text ─
    // Ollama's /api/generate endpoint (unlike Claude's Messages API) takes ONE flat text
    // string rather than a structured list of role-tagged messages, so earlier turns have to be
    // flattened into that same "User: ...\n\nAssistant: ..." script format before the new
    // utterance, mirroring desktop/core/ai.py's _build_ollama_prompt().
    // "internal" (rather than "private") so tests in this module can call it directly, the
    // same reasoning as SettingsRepository.resolveKey(): this is pure text-shaping logic with
    // no Android/network dependency, so it's worth exercising on its own instead of only ever
    // indirectly through a full processWithOllama() network call.
    internal fun buildOllamaPrompt(userText: String, conversationHistory: List<ConversationTurn>): String {
        val builder = StringBuilder()
        for (turn in conversationHistory) {
            // Capitalize "user"/"assistant" into "User"/"Assistant" to match the script format.
            val roleLabel = turn.role.replaceFirstChar { it.uppercase() }
            builder.append(roleLabel).append(": ").append(turn.content).append("\n\n")
        }
        // End the prompt with "Assistant:" and nothing after it, the model's cue to continue
        // the text FROM this point, i.e. generate the assistant's reply next.
        builder.append("User: ").append(userText).append("\n\nAssistant:")
        return builder.toString()
    }
    // End of buildOllamaPrompt().

    // ── Shared response handling for both providers ─────────────
    // Both processWithClaude() and processWithOllama() need to do the exact same three things
    // once they have an HTTP response in hand: (1) make sure the server said "success", closing
    // the response if not (to avoid leaking the underlying network connection, see the comment
    // at the call sites), (2) read and JSON-parse the response body, and (3) pull the assistant's
    // raw generated text out of that JSON and split it into spoken text + actions. The ONLY thing
    // that differs between the two providers is WHERE in the JSON that raw text lives, Claude
    // nests it inside a "content" array, Ollama puts it directly in a "response" field. Rather than
    // duplicate steps 1–3 in both functions, this shared helper takes a lambda ("extractFullText")
    // that knows how to pull the text out of that provider's specific JSON shape, and does
    // everything else itself.
    private fun buildResultFromResponse(
        response: Response,
        extractFullText: (JSONObject) -> String?
    ): ClaudeResult? {
        // Check if the server returned a success status code (200–299 range).
        if (!response.isSuccessful) {
            // If the request failed (e.g., 400 Bad Request, 500 Server Error, Ollama not running),
            // close the response body before returning, otherwise this leaks the underlying
            // connection/stream since nothing else ever reads or closes it.
            response.close()
            return null
        }
        // Extract the response body as a string. The "?:" elvis operator returns null if body is null.
        val body = response.body?.string() ?: return null
        // Parse the JSON string into a JSONObject so we can access its fields programmatically.
        val json = JSONObject(body)
        // Ask the caller-supplied lambda to pull the raw generated text out of this provider's
        // JSON shape. It returns null if there was no usable text (e.g. Claude's content array
        // was empty), in which case we bail out early just like the original code did.
        val fullText = extractFullText(json) ?: return null
        // Parse the structured text to find what the assistant wants to SAY (the spoken response part).
        val spokenText = extractSpokenText(fullText)
        // Parse the structured text to find what the assistant wants us to DO (the action commands).
        val actions = extractActions(fullText)
        // Return both the spoken text and the parsed actions packaged together in a ClaudeResult.
        return ClaudeResult(spokenText, actions)
    }
    // End of buildResultFromResponse().

    // ── Extract the spoken response from the assistant's format ─
    // This function searches for "RESPONSE:" in the output and grabs whatever text follows it.
    // It works identically whether the text came from Claude or Ollama (same prompt → same format).
    // "internal" so tests can exercise this parsing directly, see the comment on
    // buildOllamaPrompt() above for why.
    internal fun extractSpokenText(fullText: String): String {
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

    // ── Extract actions from the assistant's format ─────────────
    // This function looks for "ACTIONS:" in the response and parses each "- action:" block.
    // It works identically whether the text came from Claude or Ollama (same prompt → same format).
    // Its ONLY job is: find the ACTIONS section, split it into per-action chunks of text ("blocks"),
    // and hand each block to parseActionBlock() to turn into an Action object. The actual line-by-line
    // parsing logic lives in parseActionBlock so this function stays focused on the splitting step.
    // "internal" so tests can exercise this parsing directly, see the comment on
    // buildOllamaPrompt() above for why.
    internal fun extractActions(fullText: String): List<Action> {
        // Create an empty mutable list that we'll fill with Action objects as we parse them.
        val actions = mutableListOf<Action>()
        // Define a regex that finds "ACTIONS:" and then captures everything that follows it.
        val actionsRegex = Regex("ACTIONS:\\s*(.+)", RegexOption.DOT_MATCHES_ALL)
        // Try to find the actions section within the full text response.
        val match = actionsRegex.find(fullText)

        // Only process if we actually found the ACTIONS: section in the assistant's output.
        if (match != null) {
            // Extract the captured text (everything after "ACTIONS:") and trim surrounding whitespace.
            val actionsText = match.groupValues[1].trim()
            // Split the actions text into individual action blocks by looking for lines starting
            // with "- action:". A bare split() here would silently swallow the FIRST action: the
            // real text always starts immediately with "- action:" (no blank preamble line before
            // it), so the delimiter regex, which requires a "\n" before the "-", never matches at
            // the very start of the string, and the first action's whole block ends up stuck in
            // blocks[0] instead of being split out on its own. Prepending a throwaway leading
            // newline gives that first "- action:" something to match against too, so it's
            // stripped out just like every later one, and blocks[0] becomes the empty string we
            // actually meant to drop below.
            val blocks = ("\n" + actionsText).split("\n\\s*-\\s+action:".toRegex())
            // Loop through each block, skipping the first one (empty, the sentinel prefix added above).
            // mapNotNull runs parseActionBlock on every block and keeps only the non-null results,
            // so a malformed block (no action type) is silently dropped instead of crashing.
            actions.addAll(blocks.drop(1).mapNotNull { block -> parseActionBlock(block) })
        }
        // If no match was found, actions list stays empty, the caller will handle that.

        // Return the list of parsed actions (may be empty if none were found or parsing failed).
        return actions
    }
    // End of extractActions().

    // ── Parse one "- action:" block into an Action object ───────
    // Takes the raw text of a single action block (everything between one "- action:" marker
    // and the next) and turns it into an Action. Returns null if the block doesn't even have
    // an action type line, so the caller can skip it.
    private fun parseActionBlock(block: String): Action? {
        // Split the current action block into separate lines for parsing.
        val lines = block.trim().split("\n")
        // The first line of the block is the action type string. If it's null, this block is empty, skip it.
        val actionType = lines.firstOrNull()?.trim() ?: return null

        // Delegate to a second helper that reads just the "params:" section into a map.
        val params = parseActionParams(lines.drop(1))

        // Create a new Action object from the parsed type and params.
        return Action(actionType, params)
    }
    // End of parseActionBlock().

    // ── Parse the "params:" section of an action block ──────────
    // Takes the lines that follow the action-type line and pulls out any "key: value" pairs
    // that appear after a line containing exactly "params:". Lines before "params:" (or without
    // a colon) are ignored.
    private fun parseActionParams(lines: List<String>): Map<String, String> {
        // Create an empty map to hold the action's parameters (key-value pairs like query=cats).
        val params = mutableMapOf<String, String>()
        // Boolean flag to track whether we've entered the "params:" section of this block.
        var inParams = false
        // Loop through every line that could contain a parameter.
        for (line in lines) {
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
        // End of the parameter-parsing loop.

        // Return whatever key-value pairs we found (may be empty if there was no params: section).
        return params
    }
    // End of parseActionParams().
}
// End of ClaudeService object.
