// ─── SettingsStore.swift ────────────────────────────────────────────
// This file is the iOS equivalent of Android's SettingsRepository.kt.
// It lets the user view/edit their Anthropic API key and Picovoice
// access key at runtime instead of only ever getting them from the
// environment (see ClaudeService.swift's old `apiKey` property and
// ContentView.swift's startWakeWordDetection(), which used to read
// ProcessInfo.processInfo.environment[...] directly).
//
// Values are persisted using the Keychain Services API (Security
// framework) rather than UserDefaults, because UserDefaults stores a
// plain plist on disk — not appropriate for real API keys/secrets.
// The Keychain is Apple's OS-level secure storage, encrypted at rest
// and backed by the Secure Enclave on supported devices. This mirrors
// Android's choice of EncryptedSharedPreferences (backed by the
// Android Keystore) for the same reason.
//
// If the user hasn't entered their own key (or clears it), everything
// falls back to the existing environment-variable value — preserving
// the original "set it in the Xcode scheme" option for anyone who
// prefers that (e.g. local development, CI).
// ───────────────────────────────────────────────────────────────────

import Foundation
import Security

enum SettingsStore {

    // The Keychain "service" string groups all of this app's secrets
    // together, the same way Android's PREFS_NAME names one encrypted
    // preferences file. Each individual secret is then looked up by
    // its own "account" string within that service.
    private static let service = "com.landonkea.makeitso.settings"

    private static let anthropicAccount = "anthropic_api_key"
    private static let picovoiceAccount = "picovoice_access_key"

    // ── Anthropic API key ────────────────────────────────────────

    // Returns the user's stored key if they've set one, otherwise the
    // value from the ANTHROPIC_API_KEY environment variable (the iOS
    // equivalent of Android's BuildConfig.ANTHROPIC_API_KEY default).
    static func getAnthropicApiKey() -> String {
        resolveKey(stored: keychainGet(account: anthropicAccount), fallback: anthropicEnvFallback)
    }

    // True if the user has entered their own (non-blank) key, as
    // opposed to currently relying on the environment-variable fallback.
    static func isAnthropicApiKeyUserSet() -> Bool {
        !isBlank(keychainGet(account: anthropicAccount))
    }

    static func setAnthropicApiKey(_ value: String) {
        keychainSet(account: anthropicAccount, value: value.trimmingCharacters(in: .whitespacesAndNewlines))
    }

    // Removes the user's override, reverting to the environment-variable default.
    static func clearAnthropicApiKey() {
        keychainDelete(account: anthropicAccount)
    }

    // ── Picovoice access key ─────────────────────────────────────

    static func getPicovoiceAccessKey() -> String {
        resolveKey(stored: keychainGet(account: picovoiceAccount), fallback: picovoiceEnvFallback)
    }

    static func isPicovoiceAccessKeyUserSet() -> Bool {
        !isBlank(keychainGet(account: picovoiceAccount))
    }

    static func setPicovoiceAccessKey(_ value: String) {
        keychainSet(account: picovoiceAccount, value: value.trimmingCharacters(in: .whitespacesAndNewlines))
    }

    static func clearPicovoiceAccessKey() {
        keychainDelete(account: picovoiceAccount)
    }

    // ── Environment-variable fallbacks ─────────────────────────────
    // These are the same lookups ClaudeService.swift and ContentView.swift
    // used to perform directly before this file existed.
    private static var anthropicEnvFallback: String {
        ProcessInfo.processInfo.environment["ANTHROPIC_API_KEY"] ?? ""
    }

    private static var picovoiceEnvFallback: String {
        ProcessInfo.processInfo.environment["PICOVOICE_ACCESS_KEY"] ?? ""
    }

    // ── Fallback logic (pure, unit-testable) ─────────────────────
    // Keychain access needs a real (or simulated) Keychain, which — while it
    // does work under `swift test` on macOS — isn't necessary to exercise for
    // this one piece of logic: "prefer what the user typed, unless it's
    // empty/blank". Pulling it out into a pure function with no Security
    // framework dependency mirrors Android's SettingsRepository.resolveKey()
    // and lets SettingsStoreTests exercise it directly and cheaply.
    //
    // NOTE: this does NOT trim `stored` — trimming happens once, at write
    // time, in setAnthropicApiKey()/setPicovoiceAccessKey() above (matching
    // Android's contract exactly).
    static func resolveKey(stored: String?, fallback: String) -> String {
        guard let stored, !isBlank(stored) else { return fallback }
        return stored
    }

    private static func isBlank(_ value: String?) -> Bool {
        guard let value else { return true }
        return value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    // ── Keychain plumbing ──────────────────────────────────────────
    // Thin wrappers around the C-based Security framework APIs
    // (SecItemCopyMatching/SecItemAdd/SecItemUpdate/SecItemDelete).
    // Each secret is stored as a kSecClassGenericPassword item keyed
    // by (service, account).

    private static func keychainGet(account: String) -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]
        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        guard status == errSecSuccess, let data = result as? Data else {
            return nil
        }
        return String(data: data, encoding: .utf8)
    }

    private static func keychainSet(account: String, value: String) {
        let data = Data(value.utf8)
        let baseQuery: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account
        ]

        // Try updating an existing item first. If none exists yet
        // (errSecItemNotFound), add a new one instead.
        let updateStatus = SecItemUpdate(baseQuery as CFDictionary, [kSecValueData as String: data] as CFDictionary)
        if updateStatus == errSecItemNotFound {
            var addQuery = baseQuery
            addQuery[kSecValueData as String] = data
            SecItemAdd(addQuery as CFDictionary, nil)
        }
    }

    private static func keychainDelete(account: String) {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account
        ]
        SecItemDelete(query as CFDictionary)
    }
}
