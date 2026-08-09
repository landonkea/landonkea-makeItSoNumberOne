# landonkea-makeItSoNumberOne — Design & Workflow

## High-Level Overview

```mermaid
graph TB
    subgraph "Shared"
        A[prompts] --> B[chime.wav]
    end

    subgraph "Desktop (Python)"
        C[make_it_so.py] --> D[core/ai.py]
        C --> E[core/action_router.py]
        C --> F[core/routines.py]
        D --> G[Claude/Ollama]
        E --> H[plugins/]
    end

    subgraph "Android (Kotlin)"
        I[MainActivity.kt] --> J[Speech Recognition]
        I --> K[TTS]
        I --> L[AI Processing]
    end

    subgraph "iOS (Swift)"
        M[ContentView.swift] --> N[SFSpeechRecognizer]
        M --> O[AVSpeechSynthesizer]
        M --> P[AI Processing]
    end

    A --> C
    A --> I
    A --> M
```

## Voice Loop (All Platforms)

```mermaid
flowchart TD
    A[Listen for wake word 'Computer'] --> B[Play chime]
    B --> C[Record user command]
    C --> D[Transcribe speech to text]
    D --> E[Send to AI with context]
    E --> F[Get response + actions]
    F --> G[Speak response]
    G --> H[Execute actions]
    H --> A
```

## Desktop Plugin System

```mermaid
flowchart TD
    A[Plugin loader] --> B[Scan plugins/ directory]
    B --> C{Valid plugin?}
    C -->|Yes| D[Register action]
    C -->|No| E[Log warning, skip]
    D --> F[Action available to AI]
    F --> G[User says command]
    G --> H[ActionRouter dispatches]
    H --> I[Plugin.execute runs]
```

## Security Layers (Desktop)

```mermaid
graph TB
    subgraph "run_command"
        A[Allowlist check] --> B{Allowed?}
        B -->|Yes| C[Execute immediately]
        B -->|No| D[Require confirmation]
        D --> E[Redact output]
    end

    subgraph "read_file"
        F[Path check] --> G{Denied path?}
        G -->|Yes| H[Reject]
        G -->|No| I[Read file]
    end
```

## File Relationships

| File | Purpose | Platform |
|------|---------|----------|
| `desktop/make_it_so.py` | Main voice loop | Desktop |
| `desktop/core/ai.py` | Claude/Ollama integration | Desktop |
| `desktop/core/action_router.py` | Action dispatch | Desktop |
| `desktop/core/routines.py` | Macro matching | Desktop |
| `desktop/plugins/` | User plugins | Desktop |
| `android/app/.../MainActivity.kt` | Android entry | Android |
| `ios/MakeItSo/ContentView.swift` | iOS entry | iOS |
| `shared/` | Chime + prompts | All |

## draw.io

[Open in draw.io](https://app.diagrams.net/#RVoice%20assistant%20architecture)
