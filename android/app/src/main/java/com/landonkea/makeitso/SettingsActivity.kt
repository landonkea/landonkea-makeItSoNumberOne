// ───────────────────────────────────────────────────────────────────
// SettingsActivity.kt — lets the user view/edit API keys at runtime
// ───────────────────────────────────────────────────────────────────
// Launched from MainActivity's gear icon. Shows two fields (Anthropic
// API key, Picovoice access key), each with a "Save" and a "Use
// default" (reverts to the BuildConfig-injected value) action, backed
// by SettingsRepository's EncryptedSharedPreferences storage.
//
// Uses the same Jetpack Compose + Material3 + MakeItSoTheme setup as
// MainActivity.kt so the app looks consistent across screens.
// ───────────────────────────────────────────────────────────────────

package com.landonkea.makeitso

import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp

class SettingsActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MakeItSoTheme {
                SettingsScreen(
                    initialAnthropicKey = SettingsRepository.getAnthropicApiKey(this),
                    initialPicovoiceKey = SettingsRepository.getPicovoiceAccessKey(this),
                    isAnthropicUserSet = { SettingsRepository.isAnthropicApiKeyUserSet(this) },
                    isPicovoiceUserSet = { SettingsRepository.isPicovoiceAccessKeyUserSet(this) },
                    onSaveAnthropic = { value ->
                        SettingsRepository.setAnthropicApiKey(this, value)
                        Toast.makeText(this, "Anthropic API key saved", Toast.LENGTH_SHORT).show()
                    },
                    onResetAnthropic = {
                        SettingsRepository.clearAnthropicApiKey(this)
                        Toast.makeText(this, "Reverted to built-in default", Toast.LENGTH_SHORT).show()
                    },
                    onSavePicovoice = { value ->
                        SettingsRepository.setPicovoiceAccessKey(this, value)
                        Toast.makeText(
                            this,
                            "Picovoice key saved (restart app for wake word to pick it up)",
                            Toast.LENGTH_LONG
                        ).show()
                    },
                    onResetPicovoice = {
                        SettingsRepository.clearPicovoiceAccessKey(this)
                        Toast.makeText(this, "Reverted to built-in default", Toast.LENGTH_SHORT).show()
                    },
                    onBack = { finish() }
                )
            }
        }
    }
}

// A single labeled secret-entry section: a password-style text field plus Save/Use-default
// buttons. Reused for both the Anthropic and Picovoice keys below.
@Composable
private fun ApiKeyField(
    title: String,
    helperText: String,
    value: String,
    onValueChange: (String) -> Unit,
    isUserSet: Boolean,
    onSave: () -> Unit,
    onReset: () -> Unit
) {
    var visible by remember { mutableStateOf(false) }

    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(text = title, style = MaterialTheme.typography.titleMedium)
            Spacer(modifier = Modifier.height(4.dp))
            Text(text = helperText, style = MaterialTheme.typography.bodySmall)
            Spacer(modifier = Modifier.height(4.dp))
            Text(
                text = if (isUserSet) "Status: using your saved key" else "Status: using built-in default",
                style = MaterialTheme.typography.labelSmall
            )
            Spacer(modifier = Modifier.height(8.dp))

            OutlinedTextField(
                value = value,
                onValueChange = onValueChange,
                label = { Text(title) },
                singleLine = true,
                visualTransformation = if (visible) VisualTransformation.None else PasswordVisualTransformation(),
                trailingIcon = {
                    TextButton(onClick = { visible = !visible }) {
                        Text(if (visible) "Hide" else "Show")
                    }
                },
                modifier = Modifier.fillMaxWidth()
            )

            Spacer(modifier = Modifier.height(8.dp))

            Row {
                Button(onClick = onSave) {
                    Text("Save")
                }
                Spacer(modifier = Modifier.width(8.dp))
                OutlinedButton(onClick = onReset) {
                    Text("Use default")
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(
    initialAnthropicKey: String,
    initialPicovoiceKey: String,
    isAnthropicUserSet: () -> Boolean,
    isPicovoiceUserSet: () -> Boolean,
    onSaveAnthropic: (String) -> Unit,
    onResetAnthropic: () -> Unit,
    onSavePicovoice: (String) -> Unit,
    onResetPicovoice: () -> Unit,
    onBack: () -> Unit
) {
    var anthropicKey by remember { mutableStateOf(initialAnthropicKey) }
    var picovoiceKey by remember { mutableStateOf(initialPicovoiceKey) }
    // Bumped after every save/reset so the "Status: ..." line re-reads the
    // repository instead of showing stale state from first composition.
    var statusVersion by remember { mutableIntStateOf(0) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Settings") },
                navigationIcon = {
                    TextButton(onClick = onBack) {
                        Text("← Back")
                    }
                }
            )
        }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp)
                .verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            Text(
                text = "Keys you enter here are stored encrypted on this device and override " +
                    "the build-time defaults. Leave a field on \"built-in default\" to keep " +
                    "using whatever was baked in at build time.",
                style = MaterialTheme.typography.bodyMedium
            )

            key(statusVersion) {
                ApiKeyField(
                    title = "Anthropic API Key",
                    helperText = "Used to talk to Claude (api.anthropic.com). Takes effect on your next request.",
                    value = anthropicKey,
                    onValueChange = { anthropicKey = it },
                    isUserSet = isAnthropicUserSet(),
                    onSave = {
                        onSaveAnthropic(anthropicKey)
                        statusVersion++
                    },
                    onReset = {
                        onResetAnthropic()
                        anthropicKey = ""
                        statusVersion++
                    }
                )
            }

            key(statusVersion) {
                ApiKeyField(
                    title = "Picovoice Access Key",
                    helperText = "Used for on-device \"Computer\" wake word detection. Restart the app after changing this.",
                    value = picovoiceKey,
                    onValueChange = { picovoiceKey = it },
                    isUserSet = isPicovoiceUserSet(),
                    onSave = {
                        onSavePicovoice(picovoiceKey)
                        statusVersion++
                    },
                    onReset = {
                        onResetPicovoice()
                        picovoiceKey = ""
                        statusVersion++
                    }
                )
            }
        }
    }
}
