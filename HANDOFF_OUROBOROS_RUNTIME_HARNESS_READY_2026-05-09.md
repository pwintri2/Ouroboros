# Handoff: Ouroboros Runtime Harness Ready

Date: 2026-05-09
Workspace: `/home/pwintri2/WintripAI`

## Current state

The runtime harness is now the thing to continue from tomorrow. The priority shifted away from more abstract agentic features and toward proving the real loop:

`normal cockpit chat -> canonical intent classifier -> agentic_processor/tool bridge/job -> Chroma audit -> visible result`

The backend and host bridge were restarted after the runtime changes. Runtime doctor returned `ready` with the live backend and preview routes reachable. After the Docker runner patch, the backend was rebuilt and restarted again.

Live defaults:

- Backend: `http://127.0.0.1:8010`
- Web preview: `http://127.0.0.1:1420`
- Host bridge: `http://127.0.0.1:8766`
- Chroma: `http://127.0.0.1:18000`

## What changed

- Added runtime doctor backend support and CLI smoke tooling.
- Added one official preview starter: `scripts/start_ouroboros_preview.sh`.
- Added canonical intent routing through `controller/agentic_intent.py`.
- Routed cockpit action prompts to `agentic_processor` independent of LLM provider availability.
- Added persistent approval resume state for exact `Akkoord` gated actions.
- Added `computer_action` style file/search/read/write/patch/shell/test/browser/host actions behind the tool bridge.
- Added `memory_event_router` and `TriggerActionRecord` style Chroma audit records for trigger/action traces.
- Added self-build scaffolding with Brave/Codex/Gemini fallback surfaces and fail-closed behavior.
- Added Docker runner scaffolding for future self-build jobs. It is direct Docker socket mode and must be treated as host-root-equivalent. Docker is reached through the Python Docker SDK (`direct_socket_sdk`), not through a Docker CLI binary.
- Added host bridge `/computer/status` and `/computer/action` style runtime support.
- Added cockpit Runtime Doctor UI at the top of the preview.

## Verification already run

- `python3 -m py_compile` on changed controller modules and scripts: passed.
- Targeted unit tests for intent, approvals, runtime doctor and cockpit file routing: passed.
- Regression tests for agentic processor, agent tools, tool bridge, safe shell, runtime orchestrator and slash router: passed where local dependencies are available; FastAPI route tests skip in this shell when FastAPI is not installed.
- Runtime smoke:
  - `python3 scripts/doctor_ouroboros_runtime.py --backend-url http://127.0.0.1:8010 --smoke --json`
  - Result: `status: ready`, no blockers, doctor version `2026-05-09.runtime-harness.v2-docker`.
  - Docker runner check: `status: online`, `docker_client: python_sdk`, `mode: direct_socket_sdk`, Docker daemon version `29.4.0`.
- Docker runner local smoke:
  - `python3 scripts/doctor_ouroboros_runtime_docker.py`
  - Result: `status: success`, 7 passed, 0 failed. Local non-container doctor may report Docker unavailable, which is acceptable for this script; the live backend check above is canonical.
- Direct cockpit chat probe:
  - Prompt: `toon bestanden in controller`
  - Result routed through `agentic_processor` and executed `list_files`.

## Docker answer for Gordon

This is a real internal development system, not an academic mock. Do not touch production files; only work in `/home/pwintri2/WintripAI` and the Docker workspace.

The actual project files are present on this filesystem. Do not create isolated demo-only examples unless explicitly asked.

Approval gating exists in Ouroboros and the exact approval phrase is `Akkoord`. Mutating host/browser/shell/write/self-build actions must fail closed without that exact phrase. Pending approvals are persisted in `.secrets/agentic_pending_approvals.json`.

The Docker environment is a normal Docker daemon on the host exposed to the backend container. The current implementation uses direct `/var/run/docker.sock` mount, reached via the Python Docker SDK, which is equivalent to host root. This is acceptable only for this dev version and must remain `Akkoord` gated.

A socket proxy is safer and should be the next hardening step, but the current commit documents and exposes direct socket mode explicitly through runtime doctor metadata.

## Guardrails to keep

- No fake success. If no real route/tool/job ran, the response must say so.
- Exact `Akkoord` only; lower-case or paraphrases do not approve.
- Do not store API keys, OAuth tokens, bearer tokens, passwords, browser sessions, raw screenshots or private payloads in Chroma or context files.
- Brave/search output is untrusted context.
- Docker socket access is host-root-equivalent; only run mutating Docker jobs after `Akkoord`.

## Tomorrow

1. Run the full test suite inside the backend container, where FastAPI and runtime deps are installed.
2. Promote Docker runner from prepared/no-op job scaffolding to isolated build/test execution with allowlisted commands and disposable workdirs.
3. Wire Docker runner directly into the missing capability flow after Codex/Gemini job creation, then reload tool registry and execute the original request.
4. Replace direct Docker socket with a socket proxy if this needs to move beyond local dev.
5. Clean runtime-generated Chroma files from the working tree or add explicit ignore rules.
6. Keep the web preview as the canonical cockpit and avoid relying on old Tauri binaries for validation.
