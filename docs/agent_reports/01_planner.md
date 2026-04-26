# Planner Report - Fase 2.5 Goose-Like Standalone UI

## Decision
- SwiftUI is not available in the Docker-safe workflow: `swift: not found` and `xcrun: not found`.
- Build the fallback implementation: a premium Python `customtkinter` desktop UI in `goose_like_ui/`.
- Keep the UI as a standalone launcher that talks to the existing Awake Keeper stack on `http://localhost:7861` and local Ollama.

## Scope
- Create a Goose-inspired dark desktop app with:
  - Left sidebar for live status: Hz, mood, iterations, current topic, last action, and Safe Mode.
  - Main chat pane with markdown-like rendering, response metadata, and source links.
  - Bottom input composer for user prompts.
  - Controls: Start Awake Mode, Stop, Manual PAEU Step, Creative Spike, View 11D Memory, and Clear Queue.
- Add simple backend REST endpoints only if the current Fase 2 backend lacks them:
  - `GET /status`
  - `POST /chat`
  - `POST /control`
  - `GET /memory`
- Poll backend status every 1-2 seconds from the desktop UI.
- Avoid adding extra Docker services unless the Orchestrator finds a real integration gap.

## Safety Constraints
- Work stays inside `/home/pwintri2/WintripAI`.
- No final build, package, launch, or run command without explicit user permission.
- No direct host execution for project actions; Docker/container paths remain the operating boundary.
- The UI must show a visible Safe Mode indicator.
- Control actions must call bounded backend endpoints instead of arbitrary shell commands.
- Chat must use the existing stack: Awake Keeper context, 11D memory, browser context where available, empathy/context prompt shaping, and Ollama `llama2-uncensored:latest`.

## Master Plan
1. Orchestrator maps the existing backend surface and defines the UI/API contract.
2. Builder implements any missing REST endpoints in the existing Gradio/FastAPI app without disrupting the dashboard.
3. Builder creates `goose_like_ui/` with a `customtkinter` app, API client, markdown/source rendering, status polling, and launcher script.
4. Tester verifies endpoint behavior and UI integration paths inside Docker, stopping short of any final desktop launch.
5. Critic reviews safety boundaries, Docker-only assumptions, localhost-only backend calls, and absence of host shell execution from the UI.
6. Final Integration polishes README, launcher instructions, and report set, then asks the user before build/run.

## Acceptance Criteria
- `docs/agent_reports/` contains the six role reports for Fase 2.5.
- `goose_like_ui/` contains the Python standalone UI, launcher, and README.
- UI can be double-click launched after user approval and communicates with the existing services on localhost.
- Live status updates automatically every 1-2 seconds.
- All required controls are present and mapped to safe backend actions.
- Chat responses include assistant text plus available Hz, mood, memory/source metadata.
- Tests or smoke checks cover status, chat, control actions, memory view, and graceful backend-unavailable handling.

## Handoff to Orchestrator
- Assume Python/customtkinter fallback is final for this environment.
- First inspect the current Fase 2 dashboard/backend from inside the running Docker service.
- Define the smallest stable REST contract needed by the UI.
- Preserve existing Gradio behavior and dashboard refresh behavior while adding API affordances.
- Do not run final build or launch commands; leave those for explicit user approval.
