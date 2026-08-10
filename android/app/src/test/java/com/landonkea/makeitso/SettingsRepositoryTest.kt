// ───────────────────────────────────────────────────────────────────
// SettingsRepositoryTest.kt, JVM unit tests for the fallback logic
// ───────────────────────────────────────────────────────────────────
// EncryptedSharedPreferences itself needs the Android Keystore, which
// only exists on a real device/emulator, so it can't be exercised from
// a plain JVM unit test. What CAN be tested without any Android
// dependency is the "prefer the user's saved value, otherwise fall
// back to the BuildConfig default" decision, pulled out into
// SettingsRepository.resolveKey() specifically so it's testable here.
// ───────────────────────────────────────────────────────────────────

package com.landonkea.makeitso

import org.junit.Assert.assertEquals
import org.junit.Test

class SettingsRepositoryTest {

    @Test
    fun `uses the user-saved value when present`() {
        assertEquals(
            "user-entered-key",
            SettingsRepository.resolveKey("user-entered-key", "buildconfig-default")
        )
    }

    @Test
    fun `falls back to the BuildConfig default when nothing is stored`() {
        assertEquals(
            "buildconfig-default",
            SettingsRepository.resolveKey(null, "buildconfig-default")
        )
    }

    @Test
    fun `falls back to the BuildConfig default when the stored value is empty`() {
        assertEquals(
            "buildconfig-default",
            SettingsRepository.resolveKey("", "buildconfig-default")
        )
    }

    @Test
    fun `falls back to the BuildConfig default when the stored value is blank whitespace`() {
        assertEquals(
            "buildconfig-default",
            SettingsRepository.resolveKey("   ", "buildconfig-default")
        )
    }

    @Test
    fun `does not trim or otherwise alter a valid stored value`() {
        // resolveKey itself should not mutate the value, trimming happens at write time in
        // setAnthropicApiKey()/setPicovoiceAccessKey(), not at read time here.
        assertEquals(
            " key-with-surrounding-space ",
            SettingsRepository.resolveKey(" key-with-surrounding-space ", "buildconfig-default")
        )
    }
}
