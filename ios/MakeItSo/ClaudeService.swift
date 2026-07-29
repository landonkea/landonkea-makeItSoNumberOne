// ───────────────────────────────────────────────────────────────────
// ClaudeService.swift — talks to Claude (iOS)
// ───────────────────────────────────────────────────────────────────
// This module sends the user's transcribed speech to Claude
// (via Anthropic's API) and parses the response.
//
// It uses URLSession (Apple's built-in networking) so no extra
// libraries are needed. The JSON parsing uses Apple's built-in
// JSONSerialization.
//
// The system prompt is the same as the desktop version — Claude
// acts as the Enterprise computer and responds in the structured
// format we expect.
// ───────────────────────────────────────────────────────────────────

import Foundation

// ── Data structures for Claude's response ──────────────────────
struct ClaudeResult {
    let spokenText: String
    let actions: [ClaudeAction]
}

struct ClaudeAction {
    let actionType: String
    let params: [String: String]
}

class ClaudeService {
    // ── Singleton ──────────────────────────────────────────────
    static let shared = ClaudeService()

    // ── API configuration ──────────────────────────────────────
    // IMPORTANT: In production, load the API key from a secure
    // source (like Keychain) — DO NOT hardcode it here.
    // For now, we use a placeholder that the user replaces.
    private let apiKey = ProcessInfo.processInfo.environment["ANTHROPIC_API_KEY"] ?? ""
    private let apiURL = URL(string: "https://api.anthropic.com/v1/messages")!

    // ── System prompt (same as desktop) ─────────────────────────
    private let systemPrompt = """
        You are the computer from the USS Enterprise (NCC-1701-D).
        You are helpful, precise, and calm.
        
        OUTPUT FORMAT:
        RESPONSE: <what you say out loud>
        
        ACTIONS:
        - action: <type>
          params:
            <key>: <value>
    """

    // ── Process user text through Claude ───────────────────────
    func process(_ userText: String) async -> ClaudeResult? {
        guard !apiKey.isEmpty else {
            print("ANTHROPIC_API_KEY not set")
            // Return a placeholder response for demonstration.
            return ClaudeResult(
                spokenText: "I am configured and ready, Captain. Please add your Anthropic API key to the environment variables.",
                actions: []
            )
        }

        do {
            // ── Build the JSON payload ─────────────────────────
            let messages: [[String: Any]] = [
                ["role": "user", "content": userText]
            ]

            let body: [String: Any] = [
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 1024,
                "system": systemPrompt,
                "messages": messages,
                "temperature": 0.7
            ]

            let jsonData = try JSONSerialization.data(withJSONObject: body)

            // ── Build the HTTP request ─────────────────────────
            var request = URLRequest(url: apiURL)
            request.httpMethod = "POST"
            request.setValue(apiKey, forHTTPHeaderField: "x-api-key")
            request.setValue("2023-06-01", forHTTPHeaderField: "anthropic-version")
            request.setValue("application/json", forHTTPHeaderField: "content-type")
            request.httpBody = jsonData
            request.timeoutInterval = 30

            // ── Send the request ───────────────────────────────
            let (data, response) = try await URLSession.shared.data(for: request)

            guard let httpResponse = response as? HTTPURLResponse,
                  httpResponse.statusCode == 200 else {
                print("Claude API error")
                return nil
            }

            // ── Parse the response ─────────────────────────────
            let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
            guard let content = json?["content"] as? [[String: Any]],
                  let firstBlock = content.first,
                  let fullText = firstBlock["text"] as? String else {
                return nil
            }

            // Parse the structured response.
            let spokenText = extractSpokenText(from: fullText)
            let actions = extractActions(from: fullText)

            return ClaudeResult(spokenText: spokenText, actions: actions)

        } catch {
            print("Claude service error: \(error)")
            return nil
        }
    }

    // ── Extract spoken text ────────────────────────────────────
    private func extractSpokenText(from fullText: String) -> String {
        // Look for "RESPONSE:" followed by text until "ACTIONS:".
        if let range = fullText.range(of: "RESPONSE:") {
            let afterResponse = fullText[range.upperBound...]
            if let actionsRange = afterResponse.range(of: "ACTIONS:") {
                return String(afterResponse[..<actionsRange.lowerBound]).trimmingCharacters(in: .whitespacesAndNewlines)
            }
            return String(afterResponse).trimmingCharacters(in: .whitespacesAndNewlines)
        }
        return fullText
    }

    // ── Extract actions ───────────────────────────────────────
    private func extractActions(from fullText: String) -> [ClaudeAction] {
        var actions: [ClaudeAction] = []

        // Find the ACTIONS: section.
        guard let actionsRange = fullText.range(of: "ACTIONS:") else {
            return actions
        }

        let actionsText = fullText[actionsRange.upperBound...].trimmingCharacters(in: .whitespacesAndNewlines)

        // Split by action blocks (lines starting with "- action:").
        let blocks = actionsText.components(separatedBy: "- action:")
        for block in blocks.dropFirst() { // Skip first (before first action).
            let lines = block.trimmingCharacters(in: .whitespacesAndNewlines)
                .components(separatedBy: "\n")

            guard let firstLine = lines.first?.trimmingCharacters(in: .whitespaces) else {
                continue
            }

            // Parse parameters.
            var params: [String: String] = [:]
            var inParams = false
            for line in lines.dropFirst() {
                let trimmed = line.trimmingCharacters(in: .whitespaces)
                if trimmed == "params:" {
                    inParams = true
                } else if inParams, let colonIndex = trimmed.firstIndex(of: ":") {
                    let key = String(trimmed[..<colonIndex]).trimmingCharacters(in: .whitespaces)
                    let value = String(trimmed[trimmed.index(after: colonIndex)...]).trimmingCharacters(in: .whitespaces)
                    params[key] = value
                }
            }

            actions.append(ClaudeAction(actionType: firstLine, params: params))
        }

        return actions
    }
}
