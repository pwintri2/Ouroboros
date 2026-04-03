# WintripAI Architecture Context (for Autonomous AI Agents)

## System Overview
WintripAI is a local-first autonomous AI system utilizing an OODA (Observe, Orient, Decide, Act) loop.

- **Frontend:** macOS application built with SwiftUI (`WintripApp/`)
    - Uses SwiftData for persistence. String variables are mapped via `safeUpdate()` and global string extensions to prevent `NSRangeExceptions` during truncation.
- **Backend:** Python FastAPI (`WintripAI/controller/`)
    - **Endpoints:** `main.py` processes commands from the SwiftUI App.
    - **Routing:** `router.py` parses intent and applies RAG enrichment.

## Core Components
1.  **Hippocampus (Memory/RAG):**
    - Driven by ChromaDB in `/Users/philip/wintripai/wintrip_brain`. 
    - Database Name: `wintrip_knowledge`.
    - Architecture: Implements a "Tiered Search". Uses metadata field `type: "user_memory"` as absolute priority to prevent context-blindness vs general documentation.
2.  **Sandbox Executor:**
    - Python execution requires Docker. **Any LLM generated code MUST be executed within `controller/sandbox.py` using standard/ephemeral Docker containers.** 
    - Avoid direct OS interactions via Python's `os` or `subprocess` executed locally; it must route through `SandboxExecutor`.
3.  **Wintrip Orchestrator (OODA Loop):**
    - Continuously runs tasks autonomously validating the result through the `Reflector` before concluding or retrying.
    - Built-in crash and infinite-loop protections.
4.  **Network Protocol:**
    - SwiftUI uses a `NetworkManager` class to POST/GET from FastAPI. All frontend calls must be strictly typed and decode JSON with safe Optionals for missing fields.

## Development Rules
1.  **Backend Changes:** Do not run/install persistent packages on the host machine. If modifying the OODA loop, write unit tests under `sandbox_tests/` that assert safe evaluation.
2.  **Frontend Changes:** You may not have access to compile the macOS App. Stick strictly to Swift/SwiftUI conventions. **Never use raw ObjC string mapping (`offsetBy`, `NSRange`)**. Use `safeTruncated(to:)`.
3.  **Do Not Touch Database Paths:** Leave `CHROMA_PERSIST_DIR` exactly as is.

*Agent instruction: Always read this file before preparing a Pull Request.*
