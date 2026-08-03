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
//   - set_alarm: Set an alarm (params: hour, minute, message — all optional;
//     with no params, opens the clock app's "set alarm" screen)
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
// AlarmClock provides the well-known Intent actions/extras for asking the device's default
// clock/alarm app to set an alarm, without us needing our own alarm-scheduling code or the
// SET_ALARM permission (ACTION_SET_ALARM is a "broadcast intent" any app can send).
import android.provider.AlarmClock

// "object" creates a singleton — exactly one ActionRouter instance exists for the entire app.
// It acts as a utility that takes an Action object and performs the corresponding Android operation.
object ActionRouter {

    // The main entry point: given an Action and an optional Context, execute the correct behavior.
    // "context" is nullable (Context? = null) because some callers might not provide it.
    // This function's ONLY job is to look at the action type and hand off to the matching
    // single-purpose handler function below — it does no work itself. Splitting each case out
    // into its own named function (executeSearchWeb, executeOpenApp, ...) means each function
    // has exactly one responsibility, which makes each one easy to read and test in isolation.
    fun execute(action: Action, context: Context? = null) {
        // "when" is Kotlin's version of a switch statement — it checks action.type against multiple cases.
        when (action.type) {
            // Each branch below just forwards to a dedicated handler function, passing the
            // context and the params map it needs to do its one job.
            "search_web" -> executeSearchWeb(context, action.params)
            "open_app" -> executeOpenApp(context, action.params)
            "send_sms" -> executeSendSms(context, action.params)
            "make_call" -> executeMakeCall(context, action.params)
            "set_alarm" -> executeSetAlarm(context, action.params)

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

    // ── Search the web ────────────────────────────────────────
    // If Claude says action type is "search_web", open the browser with a DuckDuckGo search.
    // "private" means this helper is only meant to be called from inside ActionRouter.
    private fun executeSearchWeb(context: Context?, params: Map<String, String>) {
        // Get the "query" parameter from the action's params map. "?:" elvis returns if the key is missing.
        val query = params["query"] ?: return
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
    // End of executeSearchWeb().

    // ── Open another app ──────────────────────────────────────
    // If Claude says action type is "open_app", launch another app by its package name.
    private fun executeOpenApp(context: Context?, params: Map<String, String>) {
        // Get the "name" parameter (the package name like "com.spotify.music"). Return if missing.
        val packageName = params["name"] ?: return
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
    // End of executeOpenApp().

    // ── Send an SMS ────────────────────────────────────────────
    // If Claude says action type is "send_sms", open the SMS app with a pre-filled message.
    private fun executeSendSms(context: Context?, params: Map<String, String>) {
        // Get the recipient's phone number from params. Default to empty string if missing.
        val number = params["number"] ?: ""
        // Get the message text from params. Default to empty string if missing.
        val message = params["message"] ?: ""
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
    // End of executeSendSms().

    // ── Make a phone call ──────────────────────────────────────
    // If Claude says action type is "make_call", open the phone dialer with a number.
    private fun executeMakeCall(context: Context?, params: Map<String, String>) {
        // Get the phone number from params. "?:" returns early if the number is missing.
        val number = params["number"] ?: return
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
    // End of executeMakeCall().

    // ── Set an alarm ───────────────────────────────────────────
    // If Claude says action type is "set_alarm", ask the device's default clock app to set
    // one via the standard AlarmClock.ACTION_SET_ALARM broadcast intent. This does NOT require
    // the SET_ALARM permission in the manifest (any app is allowed to send this intent — it's
    // the clock app itself, not us, that actually schedules the alarm), and it hands the user
    // a normal system alarm-confirmation UI rather than silently scheduling something in the
    // background.
    private fun executeSetAlarm(context: Context?, params: Map<String, String>) {
        // "hour" and "minute" are optional — if Claude doesn't supply them (or supplies a
        // non-numeric value), toIntOrNull() returns null and we fall through to just opening
        // the clock app's own "set alarm" screen instead of crashing on a bad params map.
        val hour = params["hour"]?.toIntOrNull()
        val minute = params["minute"]?.toIntOrNull()
        // Optional label shown on the alarm, e.g. "Wake up".
        val message = params["message"] ?: ""

        val intent = Intent(AlarmClock.ACTION_SET_ALARM).apply {
            if (hour != null) putExtra(AlarmClock.EXTRA_HOUR, hour)
            if (minute != null) putExtra(AlarmClock.EXTRA_MINUTES, minute)
            if (message.isNotEmpty()) putExtra(AlarmClock.EXTRA_MESSAGE, message)
            // SKIP_UI lets the alarm be created without the clock app popping up a
            // confirmation screen first — but only when we actually have a time to set;
            // with no hour/minute at all we WANT the UI so the user can pick a time.
            if (hour != null) putExtra(AlarmClock.EXTRA_SKIP_UI, true)
            flags = Intent.FLAG_ACTIVITY_NEW_TASK
        }
        // Only launch if some app on the device can actually handle ACTION_SET_ALARM
        // (resolveActivity returns null otherwise) — avoids a crash on a device/emulator
        // with no clock app installed.
        if (context?.packageManager?.let { intent.resolveActivity(it) } != null) {
            context.startActivity(intent)
        }
    }
    // End of executeSetAlarm().
}
// End of ActionRouter object.
