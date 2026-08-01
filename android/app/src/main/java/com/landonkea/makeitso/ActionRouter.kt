// ───────────────────────────────────────────────────────────────────
// ActionRouter.kt — executes actions on Android
// ───────────────────────────────────────────────────────────────────
// After Claude returns action commands, this module routes each
// action to the appropriate handler.
//
// On Android, the available actions are more limited than desktop:
//   - open_app: Open another app on the phone
//   - search_web: Search the internet
//   - send_sms: Send a text message
//   - make_call: Make a phone call
//   - set_alarm: Set an alarm
// 
// Full system control (like typing, clicking, scrolling) is not
// possible on Android without root access.
// ───────────────────────────────────────────────────────────────────

// This line declares the package (namespace) this file belongs to, matching the folder structure.
package com.landonkea.makeitso

// ── Android system imports ────────────────────────────────────────
// These import Android classes for launching other apps, making calls, and opening URLs.

// Context provides access to Android system services (starting activities, checking package manager, etc.).
import android.content.Context
// Intent is a messaging object used to launch activities, services, or broadcast events (like opening a URL).
import android.content.Intent
// Uri represents a Uniform Resource Identifier — it can be a web URL (https://...), phone number (tel:...), etc.
import android.net.Uri

// "object" creates a singleton — exactly one ActionRouter instance exists for the entire app.
// It acts as a utility that takes an Action object and performs the corresponding Android operation.
object ActionRouter {

    // The main entry point: given an Action and an optional Context, execute the correct behavior.
    // "context" is nullable (Context? = null) because some callers might not provide it.
    fun execute(action: Action, context: Context? = null) {
        // "when" is Kotlin's version of a switch statement — it checks action.type against multiple cases.
        when (action.type) {

            // ── Search the web ────────────────────────────────
            // If Claude says action type is "search_web", open the browser with a DuckDuckGo search.
            "search_web" -> {
                // Get the "query" parameter from the action's params map. "?:" elvis returns if the key is missing.
                val query = action.params["query"] ?: return
                // Create an Intent that tells Android to open a URL in the browser.
                val intent = Intent(Intent.ACTION_VIEW).apply {
                    // Set the URL to a DuckDuckGo search with the user's query embedded in the URL.
                    data = Uri.parse("https://duckduckgo.com/?q=$query")
                    // FLAG_ACTIVITY_NEW_TASK starts the browser in a new task (a separate window/stack).
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK
                }
                // Launch the browser by passing the intent to the Android system.
                // "?." means this only runs if context is not null (safe call on nullable variable).
                context?.startActivity(intent)
            }
            // End of "search_web" case.

            // ── Open another app ──────────────────────────────
            // If Claude says action type is "open_app", launch another app by its package name.
            "open_app" -> {
                // Get the "name" parameter (the package name like "com.spotify.music"). Return if missing.
                val packageName = action.params["name"] ?: return
                // Ask the package manager for a launch Intent for the given package name.
                // getLaunchIntentForPackage returns null if the app is not installed.
                val intent = context?.packageManager?.getLaunchIntentForPackage(packageName)
                // Only try to launch if the intent is not null (the app exists on the device).
                if (intent != null) {
                    // Start the other app with the launch intent.
                    context.startActivity(intent)
                }
                // If intent is null (app not installed), we silently do nothing.
            }
            // End of "open_app" case.

            // ── Send an SMS ───────────────────────────────────
            // If Claude says action type is "send_sms", open the SMS app with a pre-filled message.
            "send_sms" -> {
                // Get the recipient's phone number from params. Default to empty string if missing.
                val number = action.params["number"] ?: ""
                // Get the message text from params. Default to empty string if missing.
                val message = action.params["message"] ?: ""
                // Create an Intent that opens the SMS/messaging app.
                val intent = Intent(Intent.ACTION_VIEW).apply {
                    // Set the URI to "sms:<phone number>" so Android knows to use the messaging app.
                    data = Uri.parse("sms:$number")
                    // Add the message text as an extra ("sms_body" is the standard key for SMS content).
                    putExtra("sms_body", message)
                    // Start in a new task (separate window stack) so the user can message then return.
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK
                }
                // Launch the SMS app with the pre-filled number and message.
                context?.startActivity(intent)
            }
            // End of "send_sms" case.

            // ── Make a phone call ─────────────────────────────
            // If Claude says action type is "make_call", open the phone dialer with a number.
            "make_call" -> {
                // Get the phone number from params. "?:" returns early if the number is missing.
                val number = action.params["number"] ?: return
                // Create an Intent that opens the phone dialer (not a direct call — just the dialer screen).
                val intent = Intent(Intent.ACTION_DIAL).apply {
                    // Set the URI to "tel:<phone number>" so the dialer pre-fills this number.
                    data = Uri.parse("tel:$number")
                    // Start in a new task so the dialer is a separate window from the assistant.
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK
                }
                // Launch the phone dialer with the pre-filled number.
                context?.startActivity(intent)
            }
            // End of "make_call" case.

            // ── Unknown action type ───────────────────────────
            // If Claude returns an action type we don't recognize, log it for debugging.
            else -> {
                // Print the unknown action type to the system console (Logcat) so we can see it during development.
                println("Unknown action type: ${action.type}")
            }
            // End of else/default case.
        }
        // End of when(action.type) block.
    }
    // End of execute() function.
}
// End of ActionRouter object.
