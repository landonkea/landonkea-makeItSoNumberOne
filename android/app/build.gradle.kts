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
    // Future: if we want to bundle an embedded LLM, we'd add a
    // dependency like `org.pytorch:pytorch_android:2.1.0` here.
}
