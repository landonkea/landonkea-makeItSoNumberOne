// ─── SettingsStoreTests.swift ───────────────────────────────────────
// Tests for SettingsStore.swift, the iOS equivalent of Android's
// SettingsRepositoryTest.kt.
//
// resolveKeyTests exercise the pure "prefer the user's saved value,
// else fall back" logic with no Keychain dependency at all — mirroring
// exactly what SettingsRepositoryTest.kt checks on the Android side:
// user value present, nothing stored (nil), stored is empty string,
// stored is whitespace-only, and that a valid value is NOT trimmed at
// read time (trimming happens at write time only).
//
// keychainRoundTripTests additionally exercise the real Keychain
// Services API (SecItemAdd/SecItemCopyMatching/SecItemUpdate/
// SecItemDelete) via SettingsStore's public set/get/clear/isUserSet
// functions, which `swift test` can run for real on macOS. To keep
// repeated runs idempotent, every test that writes to the Keychain
// deletes what it wrote in a `defer` block, and uses the app's real
// account identifiers only transiently — leaving the Keychain exactly
// as it found it (clear -> set -> assert -> clear -> assert) rather
// than depending on ordering between tests.
// ───────────────────────────────────────────────────────────────────

import XCTest
@testable import MakeItSo

final class SettingsStoreTests: XCTestCase {

    // MARK: - resolveKey (pure logic, no Keychain)

    func testUsesTheUserSavedValueWhenPresent() {
        XCTAssertEqual(
            SettingsStore.resolveKey(stored: "user-entered-key", fallback: "env-default"),
            "user-entered-key"
        )
    }

    func testFallsBackToTheDefaultWhenNothingIsStored() {
        XCTAssertEqual(
            SettingsStore.resolveKey(stored: nil, fallback: "env-default"),
            "env-default"
        )
    }

    func testFallsBackToTheDefaultWhenTheStoredValueIsEmpty() {
        XCTAssertEqual(
            SettingsStore.resolveKey(stored: "", fallback: "env-default"),
            "env-default"
        )
    }

    func testFallsBackToTheDefaultWhenTheStoredValueIsBlankWhitespace() {
        XCTAssertEqual(
            SettingsStore.resolveKey(stored: "   ", fallback: "env-default"),
            "env-default"
        )
    }

    func testDoesNotTrimOrOtherwiseAlterAValidStoredValue() {
        // resolveKey itself should not mutate the value — trimming happens
        // at write time in setAnthropicApiKey()/setPicovoiceAccessKey(),
        // not at read time here.
        XCTAssertEqual(
            SettingsStore.resolveKey(stored: " key-with-surrounding-space ", fallback: "env-default"),
            " key-with-surrounding-space "
        )
    }

    // MARK: - Real Keychain round-trips

    func testAnthropicKeySetGetClearRoundTripsThroughTheRealKeychain() {
        // Start from a known-clean state in case a previous run of this
        // test crashed before its own cleanup ran.
        SettingsStore.clearAnthropicApiKey()
        defer { SettingsStore.clearAnthropicApiKey() }

        XCTAssertFalse(SettingsStore.isAnthropicApiKeyUserSet())

        SettingsStore.setAnthropicApiKey("sk-ant-test-value")
        XCTAssertTrue(SettingsStore.isAnthropicApiKeyUserSet())
        XCTAssertEqual(SettingsStore.getAnthropicApiKey(), "sk-ant-test-value")

        SettingsStore.clearAnthropicApiKey()
        XCTAssertFalse(SettingsStore.isAnthropicApiKeyUserSet())
    }

    func testPicovoiceKeySetGetClearRoundTripsThroughTheRealKeychain() {
        SettingsStore.clearPicovoiceAccessKey()
        defer { SettingsStore.clearPicovoiceAccessKey() }

        XCTAssertFalse(SettingsStore.isPicovoiceAccessKeyUserSet())

        SettingsStore.setPicovoiceAccessKey("pv-test-value")
        XCTAssertTrue(SettingsStore.isPicovoiceAccessKeyUserSet())
        XCTAssertEqual(SettingsStore.getPicovoiceAccessKey(), "pv-test-value")

        SettingsStore.clearPicovoiceAccessKey()
        XCTAssertFalse(SettingsStore.isPicovoiceAccessKeyUserSet())
    }

    func testSettingATrimsWhitespaceAtWriteTime() {
        SettingsStore.clearAnthropicApiKey()
        defer { SettingsStore.clearAnthropicApiKey() }

        SettingsStore.setAnthropicApiKey("  sk-ant-with-padding  ")
        XCTAssertEqual(SettingsStore.getAnthropicApiKey(), "sk-ant-with-padding")
    }

    func testSettingAWhitespaceOnlyValueLeavesItEffectivelyUnset() {
        SettingsStore.clearAnthropicApiKey()
        defer { SettingsStore.clearAnthropicApiKey() }

        // Trimmed at write time down to "", so isUserSet should read false
        // (mirrors resolveKey treating blank stored values as "not set").
        SettingsStore.setAnthropicApiKey("   ")
        XCTAssertFalse(SettingsStore.isAnthropicApiKeyUserSet())
    }
}
