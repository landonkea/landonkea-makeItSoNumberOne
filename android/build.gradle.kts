# ───────────────────────────────────────────────────────────────────
# Root build file — declares the build plugins used
# ───────────────────────────────────────────────────────────────────
# The Android Gradle Plugin compiles the Kotlin code and packages
# it into an .apk file you can install on your phone.
# ───────────────────────────────────────────────────────────────────

plugins {
    id("com.android.application") version "8.2.0" apply false
    id("org.jetbrains.kotlin.android") version "1.9.20" apply false
}
