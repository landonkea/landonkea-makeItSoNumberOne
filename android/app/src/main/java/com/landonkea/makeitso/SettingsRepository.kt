// ───────────────────────────────────────────────────────────────────
// SettingsRepository.kt — persists user-editable API keys securely
// ───────────────────────────────────────────────────────────────────
// Previously, the Anthropic API key and Picovoice access key were only
// available via BuildConfig fields (app/build.gradle.kts), meaning
// anyone who wasn't compiling the app themselves had no way to set
// their own keys — a real usability gap. This file backs a Settings
// screen (SettingsActivity.kt) that lets the user view/edit both keys
// at runtime, persisted with EncryptedSharedPreferences rather than
// plain SharedPreferences (which stores values as cleartext XML on
// disk — not appropriate for real API keys/secrets).
//
// EncryptedSharedPreferences wraps a normal SharedPreferences file but
// encrypts both keys and values using a "master key" that lives in the
// Android Keystore (hardware-backed on most devices), so the values on
// disk are unreadable without the device's keystore.
//
// If the user hasn't entered their own key (or clears it), everything
// falls back to the BuildConfig-injected value — preserving the
// existing build-time-injection option for anyone who prefers that
// (e.g. CI builds, or a maintainer who bakes in their own key).
// ───────────────────────────────────────────────────────────────────

package com.landonkea.makeitso

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey

object SettingsRepository {

    // Name of the encrypted preferences file on disk (under
    // /data/data/com.landonkea.makeitso/shared_prefs/).
    private const val PREFS_NAME = "make_it_so_secure_settings"

    // Keys within that preferences file.
    private const val KEY_ANTHROPIC_API_KEY = "anthropic_api_key"
    private const val KEY_PICOVOICE_ACCESS_KEY = "picovoice_access_key"

    // Builds (or opens) the EncryptedSharedPreferences instance. This is
    // intentionally NOT cached in a `by lazy` property: MasterKey.Builder
    // needs a Context, and holding on to a Context beyond the call that
    // needs it risks leaking whichever Activity happened to create it
    // first. Re-opening the file per call is cheap — SharedPreferences
    // itself is backed by an in-memory cache per (Context, file name)
    // pair that Android already keeps warm.
    private fun prefs(context: Context): SharedPreferences {
        val masterKey = MasterKey.Builder(context.applicationContext)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
        return EncryptedSharedPreferences.create(
            context.applicationContext,
            PREFS_NAME,
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
        )
    }

    // ── Anthropic API key ────────────────────────────────────────

    // Returns the user's stored key if they've set one, otherwise the
    // BuildConfig default (see build.gradle.kts -> ANTHROPIC_API_KEY).
    fun getAnthropicApiKey(context: Context): String =
        resolveKey(prefs(context).getString(KEY_ANTHROPIC_API_KEY, null), BuildConfig.ANTHROPIC_API_KEY)

    // True if the user has entered their own (non-blank) key, as opposed
    // to currently relying on the BuildConfig fallback.
    fun isAnthropicApiKeyUserSet(context: Context): Boolean =
        !prefs(context).getString(KEY_ANTHROPIC_API_KEY, null).isNullOrBlank()

    fun setAnthropicApiKey(context: Context, value: String) {
        prefs(context).edit().putString(KEY_ANTHROPIC_API_KEY, value.trim()).apply()
    }

    // Removes the user's override, reverting to the BuildConfig default.
    fun clearAnthropicApiKey(context: Context) {
        prefs(context).edit().remove(KEY_ANTHROPIC_API_KEY).apply()
    }

    // ── Picovoice access key ─────────────────────────────────────

    fun getPicovoiceAccessKey(context: Context): String =
        resolveKey(prefs(context).getString(KEY_PICOVOICE_ACCESS_KEY, null), BuildConfig.PICOVOICE_ACCESS_KEY)

    fun isPicovoiceAccessKeyUserSet(context: Context): Boolean =
        !prefs(context).getString(KEY_PICOVOICE_ACCESS_KEY, null).isNullOrBlank()

    fun setPicovoiceAccessKey(context: Context, value: String) {
        prefs(context).edit().putString(KEY_PICOVOICE_ACCESS_KEY, value.trim()).apply()
    }

    fun clearPicovoiceAccessKey(context: Context) {
        prefs(context).edit().remove(KEY_PICOVOICE_ACCESS_KEY).apply()
    }

    // ── Fallback logic (pure, unit-testable) ─────────────────────
    // EncryptedSharedPreferences itself needs the Android Keystore, which
    // doesn't exist in a plain JVM unit test (only on a device/emulator),
    // so this piece — "prefer what the user typed, unless it's empty" —
    // is pulled out into its own pure function with no Android
    // dependency, so SettingsRepositoryTest.kt can exercise it directly.
    internal fun resolveKey(stored: String?, buildConfigFallback: String): String =
        if (!stored.isNullOrBlank()) stored else buildConfigFallback
}
