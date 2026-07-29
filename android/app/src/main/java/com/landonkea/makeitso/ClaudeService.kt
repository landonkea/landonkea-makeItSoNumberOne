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

package com.landonkea.makeitso

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.TimeUnit

// ── Data class for Claude's response ────────────────────────────
// This holds the structured response from Claude:
//   - spokenText: what to say aloud
//   - actions: what to do (open apps, search, etc.)
data class ClaudeResult(
    val spokenText: String,
    val actions: List<Action>
)

data class Action(
    val type: String,
    val params: Map<String, String>
)

object ClaudeService {

    // ── The system prompt (same as the desktop version) ─────────
    // Tells Claude to act like the Enterprise computer and respond
    // in the structured format we expect.
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

    // ── Process user text through Claude ───────────────────────
    suspend fun process(userText: String): ClaudeResult? {
        return withContext(Dispatchers.IO) {
            try {
                // ── Build the API request ───────────────────────
                val client = OkHttpClient.Builder()
                    .connectTimeout(30, TimeUnit.SECONDS)
                    .readTimeout(30, TimeUnit.SECONDS)
                    .build()

                // Claude's messages API endpoint.
                val url = "https://api.anthropic.com/v1/messages"

                // Build the JSON payload.
                val payload = JSONObject().apply {
                    put("model", "claude-sonnet-4-20250514")
                    put("max_tokens", 1024)
                    put("system", SYSTEM_PROMPT)

                    // Messages array.
                    put("messages", JSONArray().apply {
                        put(JSONObject().apply {
                            put("role", "user")
                            put("content", userText)
                        })
                    })

                    put("temperature", 0.7)
                }

                // Build the HTTP request.
                val request = Request.Builder()
                    .url(url)
                    .addHeader("x-api-key", BuildConfig.ANTHROPIC_API_KEY)
                    .addHeader("anthropic-version", "2023-06-01")
                    .addHeader("Content-Type", "application/json")
                    .post(payload.toString().toRequestBody("application/json".toMediaType()))
                    .build()

                // ── Execute the request ─────────────────────────
                val response = client.newCall(request).execute()
                if (!response.isSuccessful) {
                    return@withContext null
                }

                val body = response.body?.string() ?: return@withContext null
                val json = JSONObject(body)

                // ── Parse the response ─────────────────────────
                val content = json.getJSONArray("content")
                if (content.length() == 0) return@withContext null

                val textBlock = content.getJSONObject(0)
                val fullText = textBlock.getString("text")

                // Parse the structured response format.
                val spokenText = extractSpokenText(fullText)
                val actions = extractActions(fullText)

                return@withContext ClaudeResult(spokenText, actions)

            } catch (e: Exception) {
                e.printStackTrace()
                return@withContext null
            }
        }
    }

    // ── Extract the spoken response from Claude's format ───────
    private fun extractSpokenText(fullText: String): String {
        val responseRegex = Regex("RESPONSE:\\s*(.+?)(?=\\n\\s*ACTIONS:|\\z)", RegexOption.DOT_MATCHES_ALL)
        val match = responseRegex.find(fullText)
        return match?.groupValues?.getOrNull(1)?.trim() ?: fullText
    }

    // ── Extract actions from Claude's format ───────────────────
    private fun extractActions(fullText: String): List<Action> {
        val actions = mutableListOf<Action>()
        val actionsRegex = Regex("ACTIONS:\\s*(.+)", RegexOption.DOT_MATCHES_ALL)
        val match = actionsRegex.find(fullText)

        if (match != null) {
            val actionsText = match.groupValues[1].trim()
            // Split by action blocks.
            val blocks = actionsText.split("\n\\s*-\\s+action:".toRegex())
            for (block in blocks.drop(1)) {  // Skip the first split (before any action).
                val lines = block.trim().split("\n")
                val actionType = lines.firstOrNull()?.trim() ?: continue

                val params = mutableMapOf<String, String>()
                var inParams = false
                for (line in lines.drop(1)) {
                    val trimmed = line.trim()
                    if (trimmed == "params:") {
                        inParams = true
                    } else if (inParams && trimmed.contains(":")) {
                        val parts = trimmed.split(":", limit = 2)
                        params[parts[0].trim()] = parts[1].trim()
                    }
                }

                actions.add(Action(actionType, params))
            }
        }

        return actions
    }
}
