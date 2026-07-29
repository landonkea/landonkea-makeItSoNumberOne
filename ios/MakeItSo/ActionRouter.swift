// ─── ActionRouter.swift ──────────────────────────────────────────────
// This file handles executing the "actions" that Claude returns in its
// response. When Claude says "search the web for weather" or "send a
// text message", it returns an action like "search_web" with parameters.
// This code takes those actions and actually performs them on the iPhone.
//
// On iOS, actions are limited because Apple doesn't let apps control the
// whole system (for security reasons). We can open other apps, search
// the web in Safari, or open the Messages app with pre-filled text, but
// we can't click buttons in other apps or control system settings.
// ──────────────────────────────────────────────────────────────────────

// Import the UIKit framework — this gives us access to the iPhone's app
// management system. UIApplication.shared lets us open URLs (which is
// how we launch Safari, Messages, Phone, and other apps on iOS).
// UIKit is the older iOS framework (SwiftUI is newer) but for opening
// other apps we still need UIKit's capabilities.
import UIKit

// Define the ActionRouter class. This is responsible for figuring out
// what type of action Claude requested and performing the appropriate
// operation on the iPhone. For example, a "search_web" action opens
// Safari with a search query, while a "send_sms" action opens Messages.
class ActionRouter {
    // Create a single shared instance that the whole app uses (singleton
    // pattern). `static` means this belongs to the class itself, not to
    // a specific instance. `shared` is the conventional name so other
    // code can access it as `ActionRouter.shared` from anywhere.
    static let shared = ActionRouter()

    // The main function that executes an action. It takes a ClaudeAction
    // object (which has an actionType string and a params dictionary)
    // and performs the appropriate iOS operation. This is called by
    // ContentView after Claude returns actions in its response.
    func execute(_ action: ClaudeAction) {
        // Use a switch statement to pick the right code based on the
        // action type. A switch is cleaner than multiple if-else chains
        // and makes it easy to add new action types later. Swift's switch
        // must be exhaustive — we handle every case including unknown ones.
        switch action.actionType {

        // Handle the "search_web" action — opens Safari to search for
        // something using DuckDuckGo (a privacy-focused search engine).
        case "search_web":
            // Try to get the search query from the parameters dictionary.
            // The `guard` statement checks if "query" exists in params.
            // If not, we exit the function early (return) because we
            // can't search without something to search for.
            guard let query = action.params["query"] else { return }
            // Convert the query string into a format safe for URLs.
            // Characters like spaces, ?, and & have special meanings in
            // URLs, so we need to "percent-encode" them. For example,
            // a space becomes "%20". The `?? query` means if encoding
            // fails for some reason, we use the original query as-is.
            let encodedQuery = query.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? query
            // Build a full URL string for DuckDuckGo search. We embed
            // the encoded query into the URL so Safari knows what to
            // search for. The `\()` syntax inserts the variable value
            // directly into the string (string interpolation).
            if let url = URL(string: "https://duckduckgo.com/?q=\(encodedQuery)") {
                // Open the URL using the system's default browser (Safari).
                // UIApplication.shared is the singleton that represents
                // the running app. `.open(url)` tells iOS to open the
                // URL, which launches Safari (or shows a browser tab).
                UIApplication.shared.open(url)
            }
            // Close the if block — if the URL was invalid (which
            // shouldn't happen since we constructed it carefully),
            // we just silently do nothing.

        // Handle the "open_app" action — tries to open another app on
        // the iPhone by using its URL scheme (like "twitter://").
        case "open_app":
            // Get the app name from the parameters. The guard ensures
            // we have a name to work with; if not, we return early
            // because we can't open an unnamed app.
            guard let appName = action.params["name"] else { return }
            // Convert the app name to a URL scheme by adding "://" at
            // the end and making it lowercase. App URL schemes are
            // case-sensitive and usually lowercase (e.g., "twitter",
            // "music", "tel"). The scheme is like a protocol that the
            // other app registers with iOS.
            let scheme = "\(appName.lowercased())://"
            // Try to create a URL from the scheme string. If the scheme
            // is valid (e.g., "twitter://"), we get a URL object. Then
            // check if iOS can open this URL — `canOpenURL` returns true
            // if an app on the device has registered this URL scheme.
            if let url = URL(string: scheme),
               UIApplication.shared.canOpenURL(url) {
                // Open the app. This tells iOS to launch the app that
                // registered this URL scheme. For example, opening
                // "twitter://" would launch the Twitter app if installed.
                UIApplication.shared.open(url)
            }
            // Close the if block — if no app is registered for this
            // scheme, we silently do nothing rather than showing an error.

        // Handle the "send_sms" action — opens the Messages app with
        // a pre-filled phone number and message text.
        case "send_sms":
            // Get both the phone number and message text from the
            // parameters. The guard checks both exist; if either is
            // missing, we return early because we need both to send SMS.
            guard let number = action.params["number"],
                  let message = action.params["message"] else { return }
            // Percent-encode the message text so it's safe for a URL.
            // Special characters in the message (like & or +) need to
            // be encoded so they don't break the URL format.
            let encoded = message.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? message
            // Build a special URL that opens Messages with a pre-filled
            // recipient and message. The "sms:" scheme tells iOS to open
            // Messages, and the "&body=" parameter pre-fills the text.
            // iOS recognizes this format and opens the Messages compose screen.
            if let url = URL(string: "sms:\(number)&body=\(encoded)") {
                // Open the Messages app with the composed message.
                // The user can then review and tap Send to actually
                // send it. We don't send automatically for safety.
                UIApplication.shared.open(url)
            }
            // Close the if block — if the URL is malformed, silently
            // do nothing instead of crashing.

        // Handle the "make_call" action — opens the Phone app with a
        // number ready to dial (but doesn't call automatically).
        case "make_call":
            // Get the phone number from the parameters. Guard ensures
            // we have a number; if not, we return early because we
            // can't call without a number to dial.
            guard let number = action.params["number"] else { return }
            // Build a "tel://" URL with the phone number. This is a
            // special URL scheme that iOS recognizes as a phone call
            // request. The "tel" stands for telephone. The number is
            // used as-is (should already be digits and dashes).
            if let url = URL(string: "tel://\(number)") {
                // Open the Phone app. On a real iPhone, this shows a
                // confirmation dialog asking if the user wants to call
                // the number. On an iPod or iPad without cellular, this
                // does nothing (no phone app available).
                UIApplication.shared.open(url)
            }
            // Close the if block — if the URL is invalid, silently
            // skip the call attempt.

        // Handle ANY action type that we don't recognize. The `default`
        // case catches everything that doesn't match the above cases.
        // This is required because Swift's switch must be exhaustive.
        default:
            // Print a warning to the debug console so developers know
            // Claude returned an action type that we don't handle yet.
            // This helps during development when adding new action types.
            print("Unknown action type: \(action.actionType)")
            // Close the default case.
        }
        // Close the switch statement.
    }
    // Close the execute function.
}
// Close the ActionRouter class.
