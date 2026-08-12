// ───────────────────────────────────────────────────────────────────
// ClaudeServiceParsingTest.kt, JVM unit tests for ClaudeService's
// text-shaping logic
// ───────────────────────────────────────────────────────────────────
// ClaudeService.process() itself needs OkHttp, coroutines, and either
// a real network or a real Ollama server, none of which belong in a
// plain JVM unit test. What CAN be tested without any of that is the
// pure text parsing built on top of the shared RESPONSE:/ACTIONS:
// format both providers are told to reply in: extractSpokenText() and
// extractActions() turn that raw text into a ClaudeResult, and
// buildOllamaPrompt() turns conversation history into Ollama's flat
// prompt string. All three were made "internal" (see ClaudeService.kt)
// specifically so they're reachable here, same reasoning as
// SettingsRepositoryTest's use of resolveKey().
// ───────────────────────────────────────────────────────────────────

package com.landonkea.makeitso

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class ClaudeServiceExtractSpokenTextTest {

    @Test
    fun `pulls the text after RESPONSE up to the ACTIONS marker`() {
        val fullText = "RESPONSE: Opening Safari.\n\nACTIONS:\n- action: open_app\n  params:\n    name: Safari"
        assertEquals("Opening Safari.", ClaudeService.extractSpokenText(fullText))
    }

    @Test
    fun `returns everything after RESPONSE when there is no ACTIONS section`() {
        val fullText = "RESPONSE: Just talking, nothing to do."
        assertEquals("Just talking, nothing to do.", ClaudeService.extractSpokenText(fullText))
    }

    @Test
    fun `falls back to the whole text when there is no RESPONSE marker at all`() {
        val fullText = "The assistant ignored the format and just replied in plain text."
        assertEquals(fullText, ClaudeService.extractSpokenText(fullText))
    }

    @Test
    fun `a multi-line spoken response is captured in full`() {
        val fullText = "RESPONSE: Line one.\nLine two.\nLine three.\n\nACTIONS:\n- action: noop"
        val result = ClaudeService.extractSpokenText(fullText)
        assertTrue(result.contains("Line one."))
        assertTrue(result.contains("Line two."))
        assertTrue(result.contains("Line three."))
    }
}

class ClaudeServiceExtractActionsTest {

    @Test
    fun `no ACTIONS section returns an empty list`() {
        val fullText = "RESPONSE: Just chatting."
        assertEquals(emptyList<Action>(), ClaudeService.extractActions(fullText))
    }

    @Test
    fun `a single action with params is parsed`() {
        val fullText = """
            RESPONSE: Searching now.

            ACTIONS:
            - action: search_web
              params:
                query: dad jokes
        """.trimIndent()

        val actions = ClaudeService.extractActions(fullText)

        assertEquals(1, actions.size)
        assertEquals("search_web", actions[0].type)
        assertEquals("dad jokes", actions[0].params["query"])
    }

    @Test
    fun `multiple actions are all parsed, first one is not dropped`() {
        // This is the same class of bug the desktop parser's test suite guards against
        // (see desktop/tests/test_ai_parsing.py): the FIRST action in the list must come
        // through just as reliably as any later one.
        val fullText = """
            RESPONSE: Doing two things.

            ACTIONS:
            - action: open_app
              params:
                name: Safari
            - action: search_web
              params:
                query: pizza
        """.trimIndent()

        val actions = ClaudeService.extractActions(fullText)

        assertEquals(2, actions.size)
        assertEquals("open_app", actions[0].type)
        assertEquals("Safari", actions[0].params["name"])
        assertEquals("search_web", actions[1].type)
        assertEquals("pizza", actions[1].params["query"])
    }

    @Test
    fun `an action with no params section has an empty params map`() {
        val fullText = """
            RESPONSE: Confirmed.

            ACTIONS:
            - action: confirm_command
        """.trimIndent()

        val actions = ClaudeService.extractActions(fullText)

        assertEquals(1, actions.size)
        assertEquals("confirm_command", actions[0].type)
        assertTrue(actions[0].params.isEmpty())
    }

    @Test
    fun `lines before params colon are ignored`() {
        val fullText = """
            RESPONSE: Setting an alarm.

            ACTIONS:
            - action: set_alarm
              some stray comment line
              params:
                hour: 7
                minute: 30
        """.trimIndent()

        val actions = ClaudeService.extractActions(fullText)

        assertEquals(1, actions.size)
        assertEquals("7", actions[0].params["hour"])
        assertEquals("30", actions[0].params["minute"])
        assertEquals(2, actions[0].params.size)
    }
}

class ClaudeServiceBuildOllamaPromptTest {

    @Test
    fun `no history produces just the user turn`() {
        val prompt = ClaudeService.buildOllamaPrompt("Computer, hello", emptyList())
        assertEquals("User: Computer, hello\n\nAssistant:", prompt)
    }

    @Test
    fun `history turns are replayed with capitalized role labels`() {
        val history = listOf(
            ConversationTurn("user", "Computer, hello"),
            ConversationTurn("assistant", "RESPONSE: Hello, Captain.")
        )
        val prompt = ClaudeService.buildOllamaPrompt("What's next?", history)

        assertEquals(
            "User: Computer, hello\n\nAssistant: RESPONSE: Hello, Captain.\n\nUser: What's next?\n\nAssistant:",
            prompt
        )
    }

    @Test
    fun `prompt always ends with the Assistant cue and nothing after it`() {
        val prompt = ClaudeService.buildOllamaPrompt("engage", emptyList())
        assertTrue(prompt.endsWith("Assistant:"))
    }
}
