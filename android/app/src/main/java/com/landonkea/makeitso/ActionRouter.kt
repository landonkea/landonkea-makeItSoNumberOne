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

package com.landonkea.makeitso

import android.content.Context
import android.content.Intent
import android.net.Uri

object ActionRouter {

    fun execute(action: Action, context: Context? = null) {
        when (action.type) {

            "search_web" -> {
                // Open the web browser with a search query.
                val query = action.params["query"] ?: return
                val intent = Intent(Intent.ACTION_VIEW).apply {
                    data = Uri.parse("https://duckduckgo.com/?q=$query")
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK
                }
                context?.startActivity(intent)
            }

            "open_app" -> {
                // Open another app on the phone.
                val packageName = action.params["name"] ?: return
                val intent = context?.packageManager?.getLaunchIntentForPackage(packageName)
                if (intent != null) {
                    context.startActivity(intent)
                }
            }

            "send_sms" -> {
                // Open the SMS app with a pre-filled message.
                val number = action.params["number"] ?: ""
                val message = action.params["message"] ?: ""
                val intent = Intent(Intent.ACTION_VIEW).apply {
                    data = Uri.parse("sms:$number")
                    putExtra("sms_body", message)
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK
                }
                context?.startActivity(intent)
            }

            "make_call" -> {
                // Open the phone dialer with a number.
                val number = action.params["number"] ?: return
                val intent = Intent(Intent.ACTION_DIAL).apply {
                    data = Uri.parse("tel:$number")
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK
                }
                context?.startActivity(intent)
            }

            // Unknown action type — just log it.
            else -> {
                println("Unknown action type: ${action.type}")
            }
        }
    }
}
