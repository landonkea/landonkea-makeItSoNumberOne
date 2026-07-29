// ───────────────────────────────────────────────────────────────────
// ActionRouter.swift — executes actions on iOS
// ───────────────────────────────────────────────────────────────────
// After Claude returns action commands, this module routes each
// action to the appropriate handler.
//
// On iOS, the available actions are more limited than desktop due
// to Apple's sandbox restrictions:
//   - search_web: Open Safari with a search query
//   - open_app: Open another app (via URL scheme or deep link)
//   - send_sms: Open Messages with pre-filled text
//   - make_call: Open Phone with a number
//
// Full system control is not possible on iOS without jailbreaking.
// ───────────────────────────────────────────────────────────────────

import UIKit

class ActionRouter {
    // ── Singleton ──────────────────────────────────────────────
    static let shared = ActionRouter()

    // ── Execute an action returned by Claude ───────────────────
    func execute(_ action: ClaudeAction) {
        switch action.actionType {

        case "search_web":
            // Open Safari with a search query.
            guard let query = action.params["query"] else { return }
            let encodedQuery = query.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? query
            if let url = URL(string: "https://duckduckgo.com/?q=\(encodedQuery)") {
                UIApplication.shared.open(url)
            }

        case "open_app":
            // Open another app. On iOS, this usually requires
            // a URL scheme (like "twitter://" or "music://").
            guard let appName = action.params["name"] else { return }
            // Try to open by URL scheme (lowercased).
            let scheme = "\(appName.lowercased())://"
            if let url = URL(string: scheme),
               UIApplication.shared.canOpenURL(url) {
                UIApplication.shared.open(url)
            }

        case "send_sms":
            // Open Messages with a pre-filled message.
            guard let number = action.params["number"],
                  let message = action.params["message"] else { return }
            let encoded = message.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? message
            if let url = URL(string: "sms:\(number)&body=\(encoded)") {
                UIApplication.shared.open(url)
            }

        case "make_call":
            // Open Phone with a number (not dialed automatically).
            guard let number = action.params["number"] else { return }
            if let url = URL(string: "tel://\(number)") {
                UIApplication.shared.open(url)
            }

        default:
            print("Unknown action type: \(action.actionType)")
        }
    }
}
