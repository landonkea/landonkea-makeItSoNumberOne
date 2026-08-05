// ─── SettingsView.swift ─────────────────────────────────────────────
// SwiftUI screen that lets the user view/edit their Anthropic API key
// and Picovoice access key at runtime, backed by SettingsStore's
// Keychain-based storage. This is the iOS equivalent of Android's
// SettingsActivity.kt/SettingsScreen — same two labeled secret-entry
// fields (masked with a show/hide toggle), each with Save + "Use
// default" (reset) actions and a "Status: using your saved key / using
// built-in default" line.
//
// Presented from ContentView as a sheet, reached via a gear-icon
// toolbar button — the iOS equivalent of Android's gear button that
// launches SettingsActivity.
// ───────────────────────────────────────────────────────────────────

import SwiftUI

// A single labeled secret-entry section: a masked text field plus
// Save/Use-default buttons and a status line. Reused for both the
// Anthropic and Picovoice keys below — mirrors Android's ApiKeyField.
private struct ApiKeyField: View {
    let title: String
    let helperText: String
    @Binding var value: String
    let isUserSet: Bool
    let onSave: () -> Void
    let onReset: () -> Void

    @State private var visible = false

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.headline)
            Text(helperText)
                .font(.caption)
                .foregroundColor(.secondary)
            Text(isUserSet ? "Status: using your saved key" : "Status: using built-in default")
                .font(.caption2)
                .foregroundColor(.secondary)

            HStack {
                Group {
                    if visible {
                        TextField(title, text: $value)
                    } else {
                        SecureField(title, text: $value)
                    }
                }
                #if canImport(UIKit)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled(true)
                #endif
                .textFieldStyle(.roundedBorder)

                Button(visible ? "Hide" : "Show") {
                    visible.toggle()
                }
                .buttonStyle(.borderless)
            }

            HStack {
                Button("Save", action: onSave)
                    .buttonStyle(.borderedProminent)
                Button("Use default", action: onReset)
                    .buttonStyle(.bordered)
            }
        }
        .padding()
        #if canImport(UIKit)
        .background(Color(.secondarySystemGroupedBackground))
        #else
        .background(Color.gray.opacity(0.1))
        #endif
        .cornerRadius(12)
    }
}

struct SettingsView: View {
    @Environment(\.dismiss) private var dismiss

    @State private var anthropicKey: String
    @State private var picovoiceKey: String

    // Bumped after every save/reset so the status lines above re-read
    // SettingsStore's isXUserSet() instead of showing stale state from
    // first render — mirrors Android's `statusVersion` remember-state.
    @State private var statusVersion = 0

    init() {
        _anthropicKey = State(initialValue: SettingsStore.getAnthropicApiKey())
        _picovoiceKey = State(initialValue: SettingsStore.getPicovoiceAccessKey())
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    Text(
                        "Keys you enter here are stored securely in the device Keychain and " +
                        "override the built-in defaults. Leave a field on \"built-in default\" " +
                        "to keep using whatever was baked in at build time."
                    )
                    .font(.subheadline)

                    ApiKeyField(
                        title: "Anthropic API Key",
                        helperText: "Used to talk to Claude (api.anthropic.com). Takes effect on your next request.",
                        value: $anthropicKey,
                        isUserSet: SettingsStore.isAnthropicApiKeyUserSet(),
                        onSave: {
                            SettingsStore.setAnthropicApiKey(anthropicKey)
                            statusVersion += 1
                        },
                        onReset: {
                            SettingsStore.clearAnthropicApiKey()
                            anthropicKey = ""
                            statusVersion += 1
                        }
                    )
                    .id("anthropic-\(statusVersion)")

                    ApiKeyField(
                        title: "Picovoice Access Key",
                        helperText: "Used for on-device \"Computer\" wake word detection. Restart the app for wake word to pick it up.",
                        value: $picovoiceKey,
                        isUserSet: SettingsStore.isPicovoiceAccessKeyUserSet(),
                        onSave: {
                            SettingsStore.setPicovoiceAccessKey(picovoiceKey)
                            statusVersion += 1
                        },
                        onReset: {
                            SettingsStore.clearPicovoiceAccessKey()
                            picovoiceKey = ""
                            statusVersion += 1
                        }
                    )
                    .id("picovoice-\(statusVersion)")
                }
                .padding()
            }
            .navigationTitle("Settings")
            #if canImport(UIKit)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") { dismiss() }
                }
            }
        }
    }
}
