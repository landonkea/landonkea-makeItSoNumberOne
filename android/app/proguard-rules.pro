# ───────────────────────────────────────────────────────────────────
# proguard-rules.pro — R8/ProGuard rules for release builds
# ───────────────────────────────────────────────────────────────────
# These rules run ONLY for the release build type (see
# app/build.gradle.kts -> buildTypes -> release -> isMinifyEnabled).
# R8 shrinks, obfuscates, and optimizes the app's code. Most Android
# libraries ship their own rules bundled in their AAR, so this file
# only needs project-specific exceptions.
#
# Uncomment lines in this file to add project-specific keep rules,
# and check out the AGP default rule file (proguard-android-optimize.txt)
# that this project also applies for the standard Android keep set.
# https://developer.android.com/build/shrink-code

# Keep classes accessed via JSON reflection or Picovoice's native/JNI
# bridge if minification ever breaks either of them at runtime:
#-keep class ai.picovoice.porcupine.** { *; }
#-keep class org.json.** { *; }
