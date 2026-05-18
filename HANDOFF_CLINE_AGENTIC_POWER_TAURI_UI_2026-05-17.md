# Handoff: Cline-Grade Agentic Power in Ouroboros + Tauri UI

Datum: 2026-05-17
Workspace: `/home/pwintri2/WintripAI`
Cline reference root: `/home/pwintri2/cline`
Target UI: `/home/pwintri2/WintripAI/ouroboros_cockpit`

## Doel

Verwerk de agentische eigenschappen van Cline in Ouroboros zodat het merkbaar voelt als een echte IDE-agent:

- plannen en uitvoeren als aparte modi
- zichtbare toolstappen met voortgang, status, output en fouten
- human-in-the-loop approvals met exact `Akkoord`
- diffs, checkpoints, herstel en task history
- terminal/output streaming en achtergrondtaken
- context tracking, stale-file waarschuwingen en compacte context
- model/provider keuze met fallback en rate-limit zichtbaarheid
- MCP/connectors/tools als inspecteerbare capabilities
- Tauri cockpit als bruikbare werkplek, niet alleen statusdashboard

"Volledige kracht van Cline" betekent hier: Cline-achtige bruikbaarheid, feedbackloops, safety, task state en UI-ergonomie binnen Ouroboros. Het betekent niet onbegrensde autonomie, consciousness, sentience, spirituele autoriteit of ongecontroleerde acties.

## Huidige status van Ouroboros

Belangrijke bestaande paden:

- `OUROBOROS_IDE_CONTEXT.md`: gedeelde runtime-context.
- `AGENTS.md`: guardrails, testcommando's en DoD.
- `controller/agentic_processor.py`: agentische planner/executor met guardrails, 11D pocket, provenance, approval gates.
- `controller/agent_tools.py`: toolregistry en schemas.
- `controller/tool_bridge.py`: approval-gated host/computer/tool bridge.
- `controller/slash_agent_router.py`: `/codex`, `/roo`, `/claude`, `/deepseek`, `/atlas`, `/ruflo`.
- `controller/persistent_memory_manager.py`: agentic session memory naar Chroma met recovery/fallback.
- `controller/agentic_strength.py`: deterministic strength contract voor bounded agentic runs.
- `controller/main.py`: FastAPI routes, cockpit chat, connectors, training, Chroma status.
- `controller/approval_resume.py`: pending approval flow.
- `controller/connector_catalog.py`: connector/tool enablement.
- `ouroboros_cockpit/src/App.tsx`: huidige React cockpit.
- `ouroboros_cockpit/src/styles.css`: huidige Tauri cockpit styling.
- `ouroboros_cockpit/src-tauri/src/main.rs`: native Tauri shell.

Recent opgelost:

- Agentic planner vult lege `self_training_plan` prompts weer aan.
- `self_training_plan` accepteert aliases zoals `query`, `goal`, `text`.
- Chroma corruption is lokaal gerepareerd.
- Agentic session writes vallen terug naar recovery Chroma of JSONL als primaire Chroma faalt.

Niet zomaar committen:

- `.secrets/`
- `wintrip_brain/`
- `data/chromadb/`
- uploads, caches, model artifacts en runtime backups

## Cline reference inventory

Cline checkout: `/home/pwintri2/cline`
Licentie: Apache-2.0. Als code of UI-structuren letterlijk worden overgenomen, behoud relevante notices/attribution. Voorkeur: vertaal patronen naar Ouroboros in plaats van blind kopieren.

Belangrijk: in deze Cline checkout is geen Tauri app gevonden. Cline gebruikt een React webview UI. Ouroboros heeft wel een Tauri cockpit. De opdracht is dus niet "Cline Tauri kopieren", maar "Cline webview/agent UX vertalen naar Ouroboros Tauri".

Bronpaden met relevante patronen:

- `/home/pwintri2/cline/README.md`
  - Cline capabilities: IDE/terminal agent, Plan/Act, tools met approval, checkpoints, rules/skills, multi-model, MCP/plugins, multi-agent teams, schedules, headless CLI.
- `/home/pwintri2/cline/src/core/task/index.ts`
  - centrale Task lifecycle, state, context, terminal, browser, hooks, checkpoint manager, stream handling.
- `/home/pwintri2/cline/src/core/task/ToolExecutor.ts`
  - canonical tool execution, validators, auto-approve, callbacks, UI events.
- `/home/pwintri2/cline/src/core/task/tools/autoApprove.ts`
  - auto-approve matrix per tooltype en workspace/external path.
- `/home/pwintri2/cline/src/core/task/loop-detection.ts`
  - repeated identical tool call detection.
- `/home/pwintri2/cline/src/core/context/context-management/ContextManager.ts`
  - context compaction, context telemetry, saved context history.
- `/home/pwintri2/cline/src/core/context/context-tracking/FileContextTracker.ts`
  - file watchers, stale context, user edits vs agent edits.
- `/home/pwintri2/cline/src/integrations/checkpoints/CheckpointTracker.ts`
  - shadow git checkpoints, diff, restore, lock handling.
- `/home/pwintri2/cline/src/core/permissions/CommandPermissionController.ts`
  - shell command permission parsing, allow/deny, redirects/operators.
- `/home/pwintri2/cline/src/core/hooks/*`
  - PreToolUse/PostToolUse style hooks, cancellation, streamed hook output.
- `/home/pwintri2/cline/src/core/prompts/system-prompt/*`
  - composable prompt components for tools, Plan/Act, task progress, skills, MCP.
- `/home/pwintri2/cline/webview-ui/src/components/chat/*`
  - chat rows, command output, thinking, diff edit row, browser row, slash menu.
- `/home/pwintri2/cline/webview-ui/src/components/common/CheckpointControls.tsx`
  - checkpoint controls pattern.
- `/home/pwintri2/cline/webview-ui/src/components/history/*`
  - task history UX.
- `/home/pwintri2/cline/webview-ui/src/components/settings/*`
  - provider/model settings, reasoning effort, sliders.
- `/home/pwintri2/cline/webview-ui/src/components/worktrees/*`
  - worktree UI patterns.
- `/home/pwintri2/cline/webview-ui/src/components/mcp/*`
  - MCP UI patterns.
- `/home/pwintri2/cline/sdk`, `/home/pwintri2/cline/evals`, `/home/pwintri2/cline/testing-platform`
  - SDK/eval patterns to imitate for regression checks.

## Feature Matrix: Cline Pattern to Ouroboros Implementation

1. Task lifecycle and session state
   - Cline source: `src/core/task/index.ts`, `TaskState.ts`, `message-state.ts`
   - Ouroboros target: add or extend `controller/agentic_session_state.py`, `controller/agentic_processor.py`, `controller/main.py`
   - Result: every agentic request gets a durable `session_id`, timeline events, status, active tool, duration, model, provider, plan, approvals, memory_status and agentic_strength.

2. Plan/Act mode
   - Cline source: `system-prompt/components/act_vs_plan_mode.ts`, controller state toggles.
   - Ouroboros target: cockpit chat request fields and `/api/cockpit/chat`; UI segmented control.
   - Result: Plan mode explores and proposes; Act mode executes with gates. Strict Plan mode must never mutate.

3. Tool execution and validation
   - Cline source: `ToolExecutor.ts`, `ToolValidator.ts`, tool prompt specs.
   - Ouroboros target: `controller/agent_tools.py`, `controller/tool_bridge.py`, `controller/agentic_processor.py`.
   - Result: each tool call emits a normalized event: `planned`, `awaiting_approval`, `running`, `completed`, `blocked`, `failed`.

4. Approval and auto-approval
   - Cline source: `tools/autoApprove.ts`.
   - Ouroboros target: `approval_resume.py`, `tool_bridge.py`, `connector_catalog.py`, cockpit UI.
   - Result: read-only tools can be allowed; writes/private/browser/system actions require exact `Akkoord` unless an explicit local safe auto-approve setting says otherwise. Default remains conservative.

5. Loop detection
   - Cline source: `loop-detection.ts`.
   - Ouroboros target: deterministic helper, likely `controller/agentic_loop_guard.py`, used by `AgenticProcessor.execute_plan`.
   - Result: repeated identical tool calls get a warning at soft threshold and block/escalate at hard threshold.

6. File context tracking
   - Cline source: `FileContextTracker.ts`.
   - Ouroboros target: `controller/file_context_tracker.py` plus UI warning state.
   - Result: when the agent read/edited a file and user changes it later, the next edit must warn that context is stale and reread before patching.

7. Checkpoints and diffs
   - Cline source: `CheckpointTracker.ts`, `CheckpointControls.tsx`, `DiffEditRow.tsx`.
   - Ouroboros target: local shadow checkpoint module, probably `controller/agentic_checkpoints.py`; UI diff/checkpoint panel.
   - Result: before mutating tools, create snapshot; after completion, show changed files and diff summary; allow explicit restore only after `Akkoord`.

8. Terminal streaming and background commands
   - Cline source: terminal integrations and command output rows.
   - Ouroboros target: existing xterm in `ouroboros_cockpit`, backend job/events route.
   - Result: command output streams into the task timeline; long-running jobs remain visible, cancelable, and resumable.

9. Browser/web/search capability
   - Cline source: browser rows, `BrowserSession`, `UrlContentFetcher`, web_fetch/search prompt tools.
   - Ouroboros target: existing Brave, browser_research, chatgpt_browser adapters.
   - Result: Brave Search should be surfaced as first-class evidence with result count, source URLs, memory action, and why it was or was not used.

10. MCP/connectors/tools
   - Cline source: MCP services and MCP UI.
   - Ouroboros target: `connector_catalog.py`, `agent_tools.py`, cockpit connectors tab.
   - Result: connectors become actual task tools with visible enablement, required credentials, approval policy and last error.

11. Rules, skills and project instructions
   - Cline source: `.clinerules`, rules/skills prompt components.
   - Ouroboros target: `AGENTS.md`, `OUROBOROS_IDE_CONTEXT.md`, optional `.ouroboros/rules`.
   - Result: Agentic Core loads rules into planning context with explicit source provenance.

12. Multi-agent work
   - Cline source: README multi-agent teams, subagent tool prompts, Kanban concept.
   - Ouroboros target: existing slash agents and agent architecture routes.
   - Result: UI shows agent jobs, dependencies, statuses, outputs and handoffs, not just raw slash output.

13. Model/provider handling
   - Cline source: settings model pickers and provider refreshers.
   - Ouroboros target: provider/model config in backend and cockpit.
   - Result: OpenAI, Google, local Ollama, OpenRouter etc. show model availability, rate-limit/fallback hints, and selected model per task role.

14. Task history and resume
   - Cline source: history components, saved task messages.
   - Ouroboros target: server-side JSONL/Chroma session index plus cockpit history panel.
   - Result: previous task can be reopened with timeline, memory status, changed files and final answer.

15. Hooks
   - Cline source: `src/core/hooks/*`.
   - Ouroboros target: bounded local hook system for `PrePlan`, `PreTool`, `PostTool`, `PreMemoryWrite`, `PostRun`.
   - Result: hooks can block or annotate, but cannot bypass approval or run dangerous actions in learning loops.

## Suggested Architecture

Add a small explicit session layer instead of stuffing more fields into ad hoc chat payloads:

- `controller/agentic_session_state.py`
  - dataclasses or pydantic-compatible dict helpers for sessions/events.
  - redaction before persistence.
  - JSONL session log under `out/agentic_sessions/`, no secrets.
- `controller/agentic_event_bus.py`
  - append/read events by `session_id`.
  - compact latest session status.
  - optional SSE/WebSocket later, polling is fine first.
- `controller/agentic_loop_guard.py`
  - repeated tool signature detection.
- `controller/agentic_file_context.py`
  - tracked read/edit paths and stale warnings.
- `controller/agentic_checkpoints.py`
  - shadow git snapshots or safe git diff snapshot metadata.
  - must not run destructive restore without `Akkoord`.
- Extend `controller/main.py`
  - `GET /api/ouroboros/agentic/sessions`
  - `GET /api/ouroboros/agentic/sessions/{session_id}`
  - `GET /api/ouroboros/agentic/sessions/{session_id}/events`
  - `POST /api/ouroboros/agentic/sessions/{session_id}/approve`
  - `POST /api/ouroboros/agentic/sessions/{session_id}/cancel`
  - `POST /api/ouroboros/agentic/sessions/{session_id}/checkpoint`
  - `GET /api/ouroboros/agentic/sessions/{session_id}/diff`

For the first pass, avoid a complex WebSocket stack. Polling every 1-2 seconds from the Tauri UI is enough if events are rich.

## Tauri UI Requirements

Target files:

- `ouroboros_cockpit/src/App.tsx`
- `ouroboros_cockpit/src/styles.css`
- `ouroboros_cockpit/src/types/index.ts`
- `ouroboros_cockpit/src-tauri/src/main.rs` only if native capability is required.

Build a "Cline-grade Agent Workspace" inside the existing cockpit:

- Left rail: active sessions, recent tasks, running jobs.
- Center: chat/task timeline with rows for user, plan, thinking, tool call, command output, diff, browser/search evidence, approval needed, completion.
- Right inspector: selected event details, tool args redacted, stdout/stderr, memory_status, provenance, agentic_strength.
- Top controls: provider/model picker, Plan/Act segmented control, approval input, stop/cancel, checkpoint.
- Tool surfaces:
  - command output with xterm when relevant
  - file diff summary and changed files
  - Brave/web evidence with source list
  - memory writes with collection/status
  - approval queue with exact required phrase
- Keep it dense and work-focused. No landing page, no decorative hero, no nested cards.

Make the impact visible in the first screen:

- If a user asks "zoek Office 365 en leer dit", the UI should show memory_search, brave_search, self_training_plan, memory write, and Chroma status.
- If a tool is blocked, show why and what exact approval/action is needed.
- If a model hits rate limit, show provider/model, retry/fallback option, and task status instead of silent failure.
- If no Brave result was used, show "Brave not used" with reason.

## Implementation Order

1. Inventory and contract
   - Confirm current dirty tree with `git status -sb`.
   - Read AGENTS, OUROBOROS_IDE_CONTEXT and the Cline source paths above.
   - Define session/event schema and tests before UI changes.

2. Backend event layer
   - Add session/event persistence with redaction.
   - Emit events from `AgenticProcessor.plan`, `execute_plan`, `_validate_step`, `_dispatch_tool`, `save_agentic_session`.
   - Include session event IDs in cockpit responses.

3. Loop and permission hardening
   - Port Cline-style repeated call detection.
   - Add command permission parsing inspired by Cline, but keep existing `Akkoord` gates.
   - Add tests for repeated tool call block and command policy.

4. Checkpoints and file context
   - Implement pre-mutation snapshot metadata.
   - Track read/edit paths and stale warnings.
   - First pass can be diff-only; restore can be approval-gated follow-up.

5. Tauri UI
   - Add active task timeline and inspector.
   - Show Plan/Act, approval queue, tool progress and diffs.
   - Reuse existing icons and compact cockpit styling.

6. Models/connectors/evidence
   - Surface provider/model status and rate-limit errors.
   - Make Brave Search usage visible in the trace.
   - Link connector/tool enablement to execution blocks.

7. Tests and smoke checks
   - Python unit tests for session events, approvals, loop detection, persistence redaction.
   - Frontend build: `cd ouroboros_cockpit && npm run build`.
   - Tauri compile if feasible: `cd ouroboros_cockpit && npm run tauri -- build` or dev smoke.
   - Sandbox tests:
     - `python3 -m unittest sandbox_tests.test_agentic_processor sandbox_tests.test_agent_tools`
     - `python3 -m unittest sandbox_tests.test_persistent_memory_manager tests.test_persistent_memory_ooda`
     - broader `python3 -m unittest discover sandbox_tests` when time allows.

8. Runtime validation
   - Restart backend.
   - Verify `/health`.
   - Run a live fake or safe agentic request and confirm events appear in the UI/backend.

## Non-Negotiable Guardrails

- Do not store API keys, OAuth tokens, bearer tokens, passwords or browser session material in memory, Chroma, JSONL or docs.
- Do not mutate `/home/pwintri2/cline`; use it as read-only reference.
- Do not commit Chroma/vector-store payloads, uploads, caches or `.secrets`.
- Do not bypass `Akkoord` for mutating/private/browser/system tools.
- Do not implement or claim consciousness, sentience, divinity, omniscience or autonomous personhood.
- Learning remains Guided Behavioral Apprenticeship: scenario, demonstration, learner attempt, critic score, reflection, distilled memory rule, tests and audit logs.
- No fake success. If a tool did not run, UI/backend must say so.
- Preserve unrelated user changes in the dirty tree.

## Definition of Done

A user should be able to open the Tauri cockpit and run an agentic task, then see:

- plan vs act state
- active model/provider and fallback/rate-limit status
- each tool step, arguments redacted, result status and duration
- approval blocks with exact next action
- command/browser/search evidence when used
- file changes and checkpoint/diff summary for mutations
- memory writes and Chroma status
- task history and resumable session state
- test evidence in the final report

The result should feel materially closer to Cline: not more mystical, but more useful, visible, controlled and capable.

