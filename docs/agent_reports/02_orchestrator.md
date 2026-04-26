# Agent Report 02 - Orchestrator

Project: Resonant Ouroboros Proto 1.1 - Fase 2.5 Goose-like Standalone UI
Role: Orchestrator
Scope: UI architecture and backend API contract only
Branch context: `codex/fase2-awake-keeper`
Decision inherited from Planner: Swift/xcrun unavailable, build Python/customtkinter fallback

## Role Boundary

This report does not implement code, launch the app, restart Docker, package a build, or run a final validation command.

The Orchestrator handoff defines the architecture Builder should implement and the contract Tester should validate. All runtime integration must remain Docker-first and must talk to the already running Fase 2 backend on `http://localhost:7861`.

## System Architecture

The standalone UI should live in a new folder:

```text
goose_like_ui/
  README.md
  requirements.txt
  run_goose_like_ui.sh
  goose_like_ui.py
```

Recommended Python components:

- `customtkinter` for the standalone desktop shell.
- `requests` for HTTP calls to the backend.
- `threading` or `concurrent.futures.ThreadPoolExecutor` for non-blocking chat/control calls.
- `queue.Queue` for safely moving worker-thread responses back to the UI loop.
- `tkinter.scrolledtext` or `customtkinter.CTkTextbox` for markdown-ish chat rendering.
- No direct shell calls from the UI.

The UI should be a thin local client. It should not talk directly to Ollama. The full stack request path should be:

```text
customtkinter UI
  -> http://localhost:7861/chat
  -> existing Awake Keeper backend
  -> memory/context/browser/Ollama orchestration
  -> http://localhost:7861/chat response
  -> customtkinter UI
```

## Backend API Contract

Base URL:

```text
http://localhost:7861
```

All endpoints return JSON and should be safe for repeated local UI polling.

### `GET /status`

Purpose: live sidebar status and Safe Mode indicator.

Expected response:

```json
{
  "ok": true,
  "safe_mode": true,
  "awake": true,
  "hz": 7.83,
  "mood": "calm-focused",
  "iterations": 42,
  "current_topic": "psychological safety",
  "last_action": "Incorporated knowledge seed",
  "queue_size": 3,
  "model": "llama2-uncensored:latest",
  "ollama": {
    "reachable": true,
    "base_url": "http://host.docker.internal:11434"
  },
  "memory": {
    "records": 128,
    "last_record_id": "mem_20260427_001",
    "last_source": "AGI Kennis.txt"
  },
  "updated_at": "2026-04-27T12:00:00+02:00"
}
```

Failure response:

```json
{
  "ok": false,
  "safe_mode": true,
  "error": "backend_unavailable",
  "message": "Awake Keeper status could not be read"
}
```

Notes for Builder:

- If a field is not available in the current backend, provide a stable fallback value rather than omitting it.
- `safe_mode` must default to `true`.
- `last_action` should be short enough for sidebar display.

### `POST /chat`

Purpose: main Goose-like chat. This endpoint is the only chat path the UI uses.

Request:

```json
{
  "message": "What did you learn from the latest memory seeds?",
  "conversation_id": "local-ui-default",
  "include_memory": true,
  "include_browser": true,
  "empathy_context": true,
  "metadata": {
    "client": "goose_like_ui",
    "safe_mode": true
  }
}
```

Success response:

```json
{
  "ok": true,
  "conversation_id": "local-ui-default",
  "message_id": "chat_20260427_001",
  "role": "assistant",
  "content": "A concise markdown-capable answer from the Awake Keeper stack.",
  "hz": 7.83,
  "mood": "calm-focused",
  "sources": [
    {
      "label": "AGI Kennis.txt",
      "kind": "memory",
      "record_id": "mem_20260427_001",
      "summary": "Seeded topic on psychological safety"
    }
  ],
  "actions": [
    {
      "id": "browse_more",
      "label": "Browse more",
      "kind": "control",
      "payload": {
        "action": "manual_paeu_step"
      }
    }
  ],
  "updated_at": "2026-04-27T12:00:00+02:00"
}
```

Failure response:

```json
{
  "ok": false,
  "conversation_id": "local-ui-default",
  "error": "chat_failed",
  "message": "Chat request could not be completed",
  "hz": 0,
  "mood": "offline",
  "sources": [],
  "actions": []
}
```

Notes for Builder:

- The backend should assemble empathy/context/memory/browser prompt context.
- The backend may degrade gracefully if browser context is unavailable.
- The UI should render `content` as markdown-like text, then render compact source chips and optional action buttons.
- Chat calls must run off the UI thread.

### `POST /control`

Purpose: all sidebar controls and chat response action buttons.

Request:

```json
{
  "action": "start_awake_mode",
  "value": null,
  "metadata": {
    "client": "goose_like_ui",
    "safe_mode": true
  }
}
```

Allowed actions:

- `start_awake_mode`
- `stop_awake_mode`
- `manual_paeu_step`
- `creative_spike`
- `clear_queue`

Success response:

```json
{
  "ok": true,
  "action": "start_awake_mode",
  "accepted": true,
  "safe_mode": true,
  "status": {
    "awake": true,
    "hz": 7.83,
    "mood": "calm-focused",
    "iterations": 43,
    "current_topic": "empathy",
    "last_action": "Awake mode started",
    "queue_size": 0
  },
  "message": "Awake mode started"
}
```

Failure response:

```json
{
  "ok": false,
  "action": "creative_spike",
  "accepted": false,
  "safe_mode": true,
  "error": "control_rejected",
  "message": "Action is not available in safe mode"
}
```

Control semantics:

- `start_awake_mode`: start or resume the awake loop if the backend supports it.
- `stop_awake_mode`: pause/stop loop activity without killing containers or processes.
- `manual_paeu_step`: run one safe PAEU iteration.
- `creative_spike`: request a temporary high-Hz creative mode in memory/chat generation, capped by backend safety rules.
- `clear_queue`: clear pending work queue only; do not delete persistent 11D memory.

### `GET /memory`

Purpose: View 11D Memory panel/modal.

Query parameters:

- `limit`: integer, default `50`, maximum `200`.
- `offset`: integer, default `0`.
- `topic`: optional string filter.

Expected response:

```json
{
  "ok": true,
  "count": 50,
  "total": 128,
  "records": [
    {
      "record_id": "mem_20260427_001",
      "kind": "seed_knowledge",
      "topic": "psychological safety",
      "source": "AGI Kennis.txt",
      "hz": 7.83,
      "mood": "calm-focused",
      "fidelity": 0.94,
      "summary": "Seeded principles for safer dialogue and consentful assistance",
      "created_at": "2026-04-27T12:00:00+02:00"
    }
  ]
}
```

Failure response:

```json
{
  "ok": false,
  "error": "memory_unavailable",
  "message": "11D memory could not be read",
  "records": []
}
```

## Polling Cadence

The UI should poll `GET /status` every 1.5 seconds.

Cadence rules:

- Normal state: every 1.5 seconds.
- Chat request in flight: continue polling every 2.0 seconds to keep the UI responsive.
- Backend unavailable: back off to every 3.0 seconds and show Offline/Safe Mode.
- After a successful `/control` response: refresh status immediately once, then resume cadence.
- Memory modal open: refresh `/memory` every 5.0 seconds or on manual refresh.

The UI must avoid overlapping status polls. If a status request is still in flight, skip the next scheduled poll.

## UI Layout

The desktop window should be resizable with a minimum size around `1040x680`.

Recommended structure:

```text
+-----------------------------------------------------------+
| Sidebar                    | Main chat                     |
|                            |                               |
| Safe Mode indicator        | Header/status line            |
| Hz / Mood / Iterations     | Chat transcript               |
| Topic / Last action        | Assistant markdown + sources  |
|                            |                               |
| Start Awake Mode           |                               |
| Stop                       |                               |
| Manual PAEU Step           | Bottom input + Send           |
| Creative Spike             |                               |
| View 11D Memory            |                               |
| Clear Queue                |                               |
+-----------------------------------------------------------+
```

Visual direction:

- Dark modern Goose-inspired layout.
- Quiet, premium, tool-like interface; no marketing landing screen.
- Left sidebar uses compact status blocks and clear controls.
- Main chat uses distinct user/assistant message surfaces.
- Sources render as small subdued chips below assistant answers.
- Optional chat action buttons render under the relevant assistant message.
- Safe Mode indicator must always be visible in the sidebar.

## UI Control Mapping

| UI control | API call | Expected UI behavior |
| --- | --- | --- |
| Start Awake Mode | `POST /control` with `action=start_awake_mode` | Disable button while request is in flight, append small system message, refresh status |
| Stop | `POST /control` with `action=stop_awake_mode` | Pause backend loop only; never stop Docker/container |
| Manual PAEU Step | `POST /control` with `action=manual_paeu_step` | Show progress state, append result summary if returned, refresh status |
| Creative Spike | `POST /control` with `action=creative_spike` | Request temporary high-Hz mode; display backend acceptance/rejection |
| View 11D Memory | `GET /memory` | Open modal/panel with searchable memory rows |
| Clear Queue | `POST /control` with `action=clear_queue` | Clear pending queue only after backend acceptance |
| Send chat | `POST /chat` | Add user bubble immediately, show assistant typing state, replace with response |
| Chat action: Browse more | `POST /control` or `POST /chat` depending action payload | Execute only allowed local API actions |
| Chat action: Apply this code | No direct execution | Copy/show text only; never run code or shell commands |

## Safe Mode Rules

Safe Mode is a product requirement, not a decoration.

Rules:

- UI never runs shell commands.
- UI never starts, stops, restarts, builds, or packages Docker services.
- UI never calls host Docker, `flatpak-spawn`, `xcrun`, `swift`, `open`, or app launch commands.
- UI only communicates over local HTTP to `http://localhost:7861`.
- UI does not call Ollama directly; backend owns model access and safety gates.
- `safe_mode=true` is included in `/chat` and `/control` metadata.
- `creative_spike` must be a bounded backend request, not an unbounded loop.
- `clear_queue` must not delete persistent memory files or records.
- Chat response action buttons must be allowlisted and mapped to local API calls only.
- Backend errors must be shown clearly without retry storms.
- Offline mode keeps the app usable for status visibility and prevents unsafe controls from firing repeatedly.

## Backend Integration Notes

Builder should add lightweight REST endpoints to the existing Fase 2 FastAPI/Gradio process if they do not already exist.

Implementation preference:

- Reuse existing Awake Keeper runtime state and memory functions.
- Mount or register FastAPI routes in the same process serving Gradio on port `7861`.
- Keep Gradio dashboard behavior intact.
- Do not add a second backend service unless absolutely necessary.
- Do not require a compose change unless a new dependency is needed inside the existing `ouroboros` container.

If the backend cannot run full chat orchestration yet, `/chat` may initially use the strongest existing local response path, but the response shape must remain stable so the UI can be tested.

## Tester Contract

Tester should validate:

- `GET /status` returns JSON with `ok`, `safe_mode`, `hz`, `mood`, `iterations`, `current_topic`, and `last_action`.
- `POST /control` accepts all five allowed actions and rejects unknown actions.
- `GET /memory` returns stable `records` array shape.
- `POST /chat` returns assistant `content`, `sources`, `hz`, and `mood`.
- UI can start without backend and show offline/safe state.
- UI remains responsive during slow chat responses.
- Polling does not create overlapping request storms.
- No UI code invokes shell commands.

## Handoff To Builder

Builder should implement:

1. `goose_like_ui/` Python/customtkinter app and launcher script.
2. Minimal backend REST endpoints if absent: `/status`, `/chat`, `/control`, `/memory`.
3. README with Docker-first run instructions and a clear note that final launch/build requires explicit user permission.
4. Clean state handling for offline, typing, request-in-flight, and backend error states.

## Changed Files

- `docs/agent_reports/02_orchestrator.md`
