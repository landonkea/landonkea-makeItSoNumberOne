// ─── ClaudeServiceParsingTests.swift ────────────────────────────────
// Tests for ClaudeService.swift's RESPONSE:/ACTIONS: text parsing.
//
// ClaudeService.process() itself needs URLSession, a real or mocked
// network, and the Keychain-backed SettingsStore, none of which belong
// in a plain unit test. What CAN be tested without any of that is the
// pure text parsing both processWithClaude() and processWithOllama()
// hand their raw reply text to: extractSpokenText(from:) pulls out
// what the assistant should say, extractActions(from:) pulls out the
// list of commands to run. Both were changed from `private` to
// default (internal) access specifically so this file, in the
// separate Tests target, can call them directly via `@testable
// import MakeItSo`, mirroring SettingsStoreTests' use of
// SettingsStore.resolveKey().
//
// These mirror android/app/src/test/java/com/landonkea/makeitso/
// ClaudeServiceParsingTest.kt, which tests the equivalent Kotlin
// parsing logic. NOTE: the two platforms' ACTIONS-splitting
// implementations differ (Swift's components(separatedBy:) vs.
// Kotlin's regex split), and only the Kotlin one had a bug where the
// first action in a list was silently dropped, this file's
// `firstActionInAListIsNotDropped` test confirms the same is NOT true
// here, on Swift's plain literal-substring split.
// ───────────────────────────────────────────────────────────────────

import XCTest
@testable import MakeItSo

final class ClaudeServiceExtractSpokenTextTests: XCTestCase {
    let service = ClaudeService()

    func testPullsTheTextAfterResponseUpToTheActionsMarker() {
        let fullText = "RESPONSE: Opening Safari.\n\nACTIONS:\n- action: open_app\n  params:\n    name: Safari"
        XCTAssertEqual(service.extractSpokenText(from: fullText), "Opening Safari.")
    }

    func testReturnsEverythingAfterResponseWhenThereIsNoActionsSection() {
        let fullText = "RESPONSE: Just talking, nothing to do."
        XCTAssertEqual(service.extractSpokenText(from: fullText), "Just talking, nothing to do.")
    }

    func testFallsBackToTheWholeTextWhenThereIsNoResponseMarkerAtAll() {
        let fullText = "The assistant ignored the format and just replied in plain text."
        XCTAssertEqual(service.extractSpokenText(from: fullText), fullText)
    }

    func testAMultiLineSpokenResponseIsCapturedInFull() {
        let fullText = "RESPONSE: Line one.\nLine two.\nLine three.\n\nACTIONS:\n- action: noop"
        let result = service.extractSpokenText(from: fullText)
        XCTAssertTrue(result.contains("Line one."))
        XCTAssertTrue(result.contains("Line two."))
        XCTAssertTrue(result.contains("Line three."))
    }
}

final class ClaudeServiceExtractActionsTests: XCTestCase {
    let service = ClaudeService()

    func testNoActionsSectionReturnsAnEmptyArray() {
        let fullText = "RESPONSE: Just chatting."
        XCTAssertTrue(service.extractActions(from: fullText).isEmpty)
    }

    func testASingleActionWithParamsIsParsed() {
        let fullText = """
        RESPONSE: Searching now.

        ACTIONS:
        - action: search_web
          params:
            query: dad jokes
        """

        let actions = service.extractActions(from: fullText)

        XCTAssertEqual(actions.count, 1)
        XCTAssertEqual(actions[0].actionType, "search_web")
        XCTAssertEqual(actions[0].params["query"], "dad jokes")
    }

    func testFirstActionInAListIsNotDropped() {
        // Regression guard: this exact class of bug (the first action in a
        // list silently disappearing) is what desktop/tests/test_ai_parsing.py
        // and android's ClaudeServiceParsingTest.kt both guard against, see
        // this file's header comment for why the Swift implementation was
        // never actually susceptible to it in the first place.
        let fullText = """
        RESPONSE: Doing two things.

        ACTIONS:
        - action: open_app
          params:
            name: Safari
        - action: search_web
          params:
            query: pizza
        """

        let actions = service.extractActions(from: fullText)

        XCTAssertEqual(actions.count, 2)
        XCTAssertEqual(actions[0].actionType, "open_app")
        XCTAssertEqual(actions[0].params["name"], "Safari")
        XCTAssertEqual(actions[1].actionType, "search_web")
        XCTAssertEqual(actions[1].params["query"], "pizza")
    }

    func testAnActionWithNoParamsSectionHasEmptyParams() {
        let fullText = """
        RESPONSE: Confirmed.

        ACTIONS:
        - action: confirm_command
        """

        let actions = service.extractActions(from: fullText)

        XCTAssertEqual(actions.count, 1)
        XCTAssertEqual(actions[0].actionType, "confirm_command")
        XCTAssertTrue(actions[0].params.isEmpty)
    }

    func testLinesBeforeParamsColonAreIgnored() {
        let fullText = """
        RESPONSE: Setting an alarm.

        ACTIONS:
        - action: set_alarm
          some stray comment line
          params:
            hour: 7
            minute: 30
        """

        let actions = service.extractActions(from: fullText)

        XCTAssertEqual(actions.count, 1)
        XCTAssertEqual(actions[0].params["hour"], "7")
        XCTAssertEqual(actions[0].params["minute"], "30")
        XCTAssertEqual(actions[0].params.count, 2)
    }

    func testAColonInsideAValueOnlySplitsOnTheFirstColon() {
        let fullText = """
        RESPONSE: Noted.

        ACTIONS:
        - action: open_app
          params:
            url: https://example.com
        """

        let actions = service.extractActions(from: fullText)

        XCTAssertEqual(actions[0].params["url"], "https://example.com")
    }
}
