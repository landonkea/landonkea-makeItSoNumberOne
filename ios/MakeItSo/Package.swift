// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "MakeItSo",
    platforms: [
        .iOS(.v17),
        .macOS(.v14)
    ],
    products: [
        .executable(name: "MakeItSo", targets: ["MakeItSo"])
    ],
    dependencies: [
        // Porcupine wake word engine (Picovoice), detects the word
        // "Computer" hands-free without needing to tap a button.
        // This is the iOS SPM package. macOS is not supported by
        // this package, but we gate it with #if os(iOS) in our code.
        .package(url: "https://github.com/Picovoice/porcupine.git", from: "3.0.0")
    ],
    targets: [
        .executableTarget(
            name: "MakeItSo",
            dependencies: [
                // Add Porcupine as a dependency so we can import
                // it in WakeWordService.swift and use its wake word
                // detection capabilities.
                // This dependency is conditional on iOS because Porcupine
                // only supports iOS (its Package.swift specifies iOS 13+).
                // On macOS builds (for testing/compilation), the dependency
                // is excluded and WakeWordService falls back to a stub.
                .product(name: "Porcupine", package: "porcupine", condition: .when(platforms: [.iOS]))
            ],
            path: ".",
            exclude: [
                "MakeItSo.xcodeproj",
                "Package.swift",
                "Resources/Info.plist",
                "Tests"
            ],
            resources: [
                .process("Resources")
            ]
        ),
        // A separate, lower-risk build graph (see MakeItSo.xcodeproj's
        // build target, which has no test target of its own) that proves
        // SettingsStore.swift compiles standalone and exercises its pure
        // resolveKey() logic plus real Keychain round-trips. Run with
        // `swift test` from this directory.
        .testTarget(
            name: "MakeItSoTests",
            dependencies: ["MakeItSo"],
            path: "Tests/MakeItSoTests"
        )
    ]
)
