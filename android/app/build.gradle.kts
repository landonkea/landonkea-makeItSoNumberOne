plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
}

android {
    namespace = "com.landonkea.makeitso"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.landonkea.makeitso"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "1.0.0"
        buildConfigField("String", "ANTHROPIC_API_KEY", "\"YOUR_API_KEY_HERE\"")
        buildConfigField("String", "PICOVOICE_ACCESS_KEY", "\"YOUR_PICOVOICE_KEY\"")
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    // ── Build types (debug vs release) ─────────────────────────
    // No buildTypes were defined before, which meant every build
    // used AGP's implicit defaults (release: minified+shrunk but
    // unsigned; debug: unminified, auto-signed with the debug key).
    // Making both explicit here documents that behavior and lets
    // debug + release builds install side by side on one device.
    buildTypes {
        release {
            // Shrinks and obfuscates code with R8, and strips unused
            // resources — smaller APK, harder to reverse-engineer.
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
            // NOTE: there is no signingConfig here. Without one,
            // `assembleRelease` produces an unsigned APK that can't
            // be installed as-is — it needs a release keystore
            // (signingConfigs { create("release") { ... } }) before
            // it can be signed and published. Setting that up needs
            // a real keystore/Play Console credentials, which is
            // out of scope for this pass.
        }
        debug {
            // Suffixing the debug applicationId lets a debug build
            // be installed alongside a signed release build of the
            // same app on the same device instead of overwriting it.
            applicationIdSuffix = ".debug"
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    // ── Jetpack Compose (modern UI framework) ─────────────────
    val composeBom = platform("androidx.compose:compose-bom:2023.10.01")
    implementation(composeBom)
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.activity:activity-compose:1.8.1")

    // ── Core Android ──────────────────────────────────────────
    implementation("androidx.core:core-ktx:1.12.0")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.6.2")

    // ── HTTP client (for Claude API calls) ────────────────────
    implementation("com.squareup.okhttp3:okhttp:4.12.0")

    // ── JSON parsing (for API responses) ─────────────────────
    implementation("org.json:json:20231013")

    // ── Secure settings storage (EncryptedSharedPreferences) ──
    // Backs SettingsRepository.kt — lets the user enter their own
    // Anthropic/Picovoice keys at runtime instead of only via
    // BuildConfig, encrypted at rest with an Android Keystore-backed
    // master key (unlike plain SharedPreferences, which stores values
    // as cleartext XML on disk).
    implementation("androidx.security:security-crypto:1.1.0-alpha06")

    // ── Wake word detection (Picovoice Porcupine) ─────────────
    // Enables on-device "Computer" wake word detection.
    // Requires a free access key from https://console.picovoice.ai/
    // and setting PICOVOICE_ACCESS_KEY (BuildConfig or system property).
    // Falls back to button activation if the key is empty.
    implementation("ai.picovoice:porcupine-android:3.0.2")

    // ── Offline mode (Ollama) ──────────────────────────────────
    // No additional dependencies needed for offline mode — it reuses
    // the same OkHttp client and JSON parser that the online mode uses.
    // The only requirement is that Ollama is running on localhost:11434
    // with the "llama3.2" model pulled. This is all handled at runtime
    // by ClaudeService.processWithOllama() using standard HTTP calls.
    //
    // ── On-device LLM (MediaPipe GenAI) ─────────────────────────
    // Backs LocalModelService.kt's LlmInference usage. This was missing
    // before, LocalModelService.kt imported com.google.mediapipe classes
    // with no matching dependency declared, breaking the Android build.
    implementation("com.google.mediapipe:tasks-genai:0.10.27")

    // ── Unit tests (JVM, no Android device/emulator needed) ───
    // Backs SettingsRepositoryTest.kt — EncryptedSharedPreferences itself
    // needs the Android Keystore (unavailable in a plain JVM unit test),
    // so SettingsRepository's fallback logic is split into a pure
    // resolveKey() function that these tests exercise directly.
    testImplementation("junit:junit:4.13.2")
}
