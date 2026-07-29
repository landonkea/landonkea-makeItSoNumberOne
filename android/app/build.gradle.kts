# ───────────────────────────────────────────────────────────────────
# App module build file — what dependencies the app needs
# ───────────────────────────────────────────────────────────────────
# This file tells Gradle:
#   1. What version of Android SDK to compile against
#   2. What libraries (dependencies) the app uses
#   3. What minimum Android version to support
# ───────────────────────────────────────────────────────────────────

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.landonkea.makeitso"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.landonkea.makeitso"
        minSdk = 26
        targetSdk = 34
        versionCode = 1
        versionName = "1.0.0"
    }

    buildFeatures {
        compose = true
    }

    composeOptions {
        kotlinCompilerExtensionVersion = "1.5.5"
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
}
