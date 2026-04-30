# WintripAI Architecture Context (for Autonomous AI Agents)

## System Overview
WintripAI is a local-first autonomous AI system utilizing an OODA (Observe, Orient, Decide, Act) loop.

- **Frontend:** native Tauri + React cockpit (`ouroboros_cockpit/`) for the Ouroboros agent command center.
    - The old static `WintripAI_IDE.html` is legacy. Preserve the Tauri cockpit as the primary UI.
    - The cockpit talks to the Python backend at `http://localhost:8010`, uses xterm.js for `/sandbox/shell`, and exposes local Ollama, Roo tools, 11D memory, loop control, model creation, tests, and API key management.
- **Backend:** Python FastAPI (`WintripAI/controller/`)
    - **Endpoints:** `main.py` processes commands from the SwiftUI App.
    - **Routing:** `router.py` parses intent and applies RAG enrichment.
    - **Cockpit middleware:** `controller/main.py` exposes `/api/cockpit/config`, `/api/cockpit/chat`, `/api/cockpit/api-keys`, and `/api/ouroboros/loop/*`.
    - **Provider routing:** `controller/multi_api_router.py` supports key-gated OpenAI, Anthropic, xAI, Google, and Mistral calls without fake success.
    - **API key storage:** `controller/api_key_store.py` stores provider keys locally in `.secrets/ouroboros_api_keys.json` or `WINTRIP_API_KEY_STORE`; responses never return raw secrets.

## Core Components
1.  **Hippocampus (Memory/RAG):**
    - Driven by ChromaDB in `/Users/philip/wintripai/wintrip_brain`. 
    - Database Name: `wintrip_knowledge`.
    - Architecture: Implements a "Tiered Search". Uses metadata field `type: "user_memory"` as absolute priority to prevent context-blindness vs general documentation.
2.  **Sandbox Executor:**
    - Shell execution for the cockpit and agent tools MUST route through `controller/safe_shell.py`.
    - Safe shell requires exact `Akkoord`, runs in `/workspace`, whitelists commands, and returns stdout/stderr/exit_code.
3.  **Wintrip Orchestrator (OODA Loop):**
    - Continuously runs tasks autonomously validating the result through the `Reflector` before concluding or retrying.
    - Built-in crash and infinite-loop protections.
4.  **Network Protocol:**
    - Tauri/React calls FastAPI through typed fetch wrappers. Native Rust only performs a lightweight backend health/config probe and never executes shell commands.
5.  **Roo and Trainer Perimeter:**
    - Roo semantics are mirrored by `controller/roo_tools.py` and exposed through `controller/agent_tools.py`.
    - Future LitGPT and Unsloth training integrations must be job-based, approval-gated, Docker-contained, and must write no fake fine-tune status.
    - Approved training data must come from 11D ChromaDB records or explicit `Akkoord` snapshots.

## Development Rules
1.  **Backend Changes:** Do not run/install persistent packages on the host machine. If modifying the OODA loop, write unit tests under `sandbox_tests/` that assert safe evaluation.
2.  **Frontend Changes:** You may not have access to compile the macOS App. Stick strictly to Swift/SwiftUI conventions. **Never use raw ObjC string mapping (`offsetBy`, `NSRange`)**. Use `safeTruncated(to:)`.
3.  **Do Not Touch Database Paths:** Leave `CHROMA_PERSIST_DIR` exactly as is.
4.  **Secrets:** Never commit `.secrets/`, API keys, ChromaDB binary state, `node_modules`, `dist`, or Rust `target`.

*Agent instruction: Always read this file before preparing a Pull Request.*
