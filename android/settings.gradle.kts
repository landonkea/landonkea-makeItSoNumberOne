# ───────────────────────────────────────────────────────────────────
# settings.gradle.kts — tells Gradle what modules to build
# ───────────────────────────────────────────────────────────────────
# This project only has one module: "app" (the Android app).
# If we add libraries later (like a shared Kotlin module), we'd
# add them here too.
# ───────────────────────────────────────────────────────────────────

pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolution {
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "MakeItSo"
include(":app")
