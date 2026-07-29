// ───────────────────────────────────────────────────────────────────
// MakeItSoApp.swift — the app's entry point (iOS)
// ───────────────────────────────────────────────────────────────────
// This is the SwiftUI @main entry point — it's called when the app
// launches. It sets up the ContentView and wires everything
// together. This is the iOS equivalent of Android's MainActivity.
//
// The app lifecycle is simple:
//   1. App launches → MakeItSoApp runs
//   2. ContentView shows the main screen
//   3. User interacts with the assistant
// ───────────────────────────────────────────────────────────────────

import SwiftUI

@main
struct MakeItSoApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}
