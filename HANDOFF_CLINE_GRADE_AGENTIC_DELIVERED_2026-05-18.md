# Handoff: Cline-Grade Agentic Power Delivered in Ouroboros

Datum: 2026-05-18
Branch: `codex/guided-behavioral-apprenticeship`
Voorganger: [HANDOFF_CLINE_AGENTIC_POWER_TAURI_UI_2026-05-17.md](HANDOFF_CLINE_AGENTIC_POWER_TAURI_UI_2026-05-17.md) + [CLAUDE_CODE_PROMPT_CLINE_TO_OUROBOROS_2026-05-17.md](CLAUDE_CODE_PROMPT_CLINE_TO_OUROBOROS_2026-05-17.md)

## Wat hier nieuw is

Vorige handoff beschreef het ontwerp. Deze handoff beschrijft de **opgeleverde** en **live geverifieerde** implementatie, plus een chat-hang fix die buiten de oorspronkelijke scope viel maar nodig bleek om de Agent Workspace te kunnen gebruiken.

## Geleverde modules

### Nieuwe backend modules (`controller/`)

| Module | Doel |
|---|---|
| `agentic_session_state.py` | Sessie/event schema + recursieve redaction. `make_session`, `make_event`, `compact_event_summary`, `compact_session_snapshot`, `merge_completion_into_session`, `session_log_path`. |
| `agentic_event_bus.py` | In-memory ring buffer (128 sessies × 512 events, env-tunbaar) + append-only JSONL onder `out/agentic_sessions/events.jsonl`. Per sessie: sequence-counter, cancellation flag, tool-summary derivation. Persistence schakelbaar via `WINTRIP_AGENTIC_EVENT_BUS_NO_PERSIST=1`. |
| `agentic_loop_guard.py` | Cline-stijl repeated-call detectie. Signature = `tool + sha256(canonical_args)`; ignored keys: `approval`, `task_progress`, `session_id`. Soft @ 3 (warning), hard @ 5 (block). Counters resetten bij andere signature. |
| `agentic_command_policy.py` | Shell-policy met fnmatch allow/deny. Defaults openen `git status*`, `ls*`, `pwd`, `python3 -m unittest*` etc., sluiten `rm -rf /*`, `dd if=*`, `curl * \| sh*` etc. Pipes/redirects/backticks → `requires_approval`. Multiline of ongesloten quotes → `deny`. |
| `agentic_file_context.py` | Per-sessie map van paden → laatste read/edit + mtime. `evaluate_path` retourneert `fresh \| stale \| missing \| unknown` voor stale-warnings. |
| `agentic_checkpoints.py` | Pre-mutation snapshot via `git status --porcelain` + HEAD; finalize berekent diff. Geen `git reset --hard`; restore alleen via diff-view. Degradeert naar `unavailable` zonder git. |

### Backend wiring (bestaande bestanden)

- **`controller/agentic_processor.py`** — `run()` accepteert nu `session_id`, `plan_mode` (`act`/`plan`), `conversation_id`. Registreert sessie op event bus en emit:
  `session_started` → `plan_built` → `tool_planned×N` → `tool_validated` → `tool_running` → `tool_completed`/`tool_blocked`/`tool_failed`/`tool_awaiting_approval` → optional `loop_warning`/`loop_blocked` → `memory_write` → `session_completed`/`session_failed`/`session_cancelled`.
  - Plan mode skipt `execute_plan` volledig.
  - Loop guard check vóór elke tool-dispatch.
  - Cancellation tussen stappen via `_bus_consume_cancellation`.
- **`controller/orchestrator.py`** — `agentic_process` accepteert nu en stuurt `session_id`/`plan_mode`/`conversation_id` door.
- **`controller/main.py`** — `CockpitChatRequest` heeft nieuwe `session_id`/`plan_mode` velden; doorgegeven naar agentic_process. Acht nieuwe routes onder `/api/ouroboros/agentic/*`:

| Route | Methode | Doel |
|---|---|---|
| `/api/ouroboros/agentic/sessions` | GET | Lijst compacte sessie-snapshots (default limit=20) |
| `/api/ouroboros/agentic/sessions/{id}` | GET | Volledig sessie-record |
| `/api/ouroboros/agentic/sessions/{id}/events` | GET | Events met `since_sequence`, `limit`, `compact` query params |
| `/api/ouroboros/agentic/sessions/{id}/cancel` | POST | Vraag cancellation; AgenticProcessor consumeert tussen stappen |
| `/api/ouroboros/agentic/sessions/{id}/diff` | GET | Diff voor specifiek pad via git |
| `/api/ouroboros/agentic/sessions/{id}/files` | GET | File context tracker output voor sessie |
| `/api/ouroboros/agentic/policy/commands` | GET | Active allow/deny patronen + approval phrase |
| `/api/ouroboros/agentic/policy/commands/evaluate` | POST | Evaluatie van een specifiek commando met optionele user-rules |

### Tauri cockpit UI

- **`ouroboros_cockpit/src/components/AgentWorkspace.tsx`** (NIEUW) — Cline-grade 3-koloms layout:
  - **Links** sessions rail: status + plan_mode + tool_summary chips, klik om te selecteren.
  - **Midden** timeline: Plan/Act segmented control, approval banner als geblokkeerd, event-rijen met icoon/tool/status/duur en payload preview.
  - **Rechts** inspector: type/tool/status/duration/payload van geselecteerd event, plus memory_status / Brave evidence / blocked tools / files touched.
  - Polling: sessies elke 4s, events 1.8s.
  - Stop-knop POST naar `/cancel`.
- **`ouroboros_cockpit/src/App.tsx`** — `ActiveTab` uitgebreid met `agent-workspace`, default tab is nu deze, navItem als eerste, render-block routes naar `/api/cockpit/chat` met `session_id`+`plan_mode`.
- **`ouroboros_cockpit/src/types/index.ts`** — Types: `AgenticSessionSnapshot`, `AgenticEvent`, `AgenticSessionsResponse`, `AgenticEventsResponse`, `AgenticMemoryStatus`, `AgenticToolSummary`; nieuwe contract paths.
- **`ouroboros_cockpit/src/styles.css`** — ~430 regels `/* Agent Workspace */` styling, hergebruikt dark-theme palette, klassen `.agent-tone-good|warn|block|info|neutral`, `.agent-session-card`, `.agent-event`, `.agent-inspector-grid`, etc.

### Tests (nieuw)

- `sandbox_tests/test_agentic_session_state.py` — schema, redaction (keys + value-regex), event sequencing, merge-completion.
- `sandbox_tests/test_agentic_event_bus.py` — sequence, persistence redaction, tool-summary, cancellation, list-ordering, disable-persistence.
- `sandbox_tests/test_agentic_loop_guard.py` — signature normalisatie, soft @ 3, hard @ 5, reset bij andere args, sessie-isolatie.
- `sandbox_tests/test_agentic_command_policy.py` — empty/allow/unknown/deny/redirect/multiline/multi-segment/explain/merge.
- `sandbox_tests/test_agentic_file_context.py` — read/edit fresh/stale/missing/unknown + sessie isolatie.
- `sandbox_tests/test_agentic_checkpoints.py` — begin/finalize/diff/no-changes/non-git (vereist `git`).
- `sandbox_tests/test_agentic_processor_events.py` — emit-keten, plan mode skip execution, approval-block emit, loop guard blokkeert na 5 herhalingen.

## Pre-existing chat-hang fix (out-of-scope maar nodig)

Tijdens runtime smoke gaf `/api/cockpit/chat` 90s timeouts (zelfde symptoom dat de user al rapporteerde). Diagnose via py-spy:

```
cockpit_chat → _cockpit_chat_payload (async)
  → _rebuild_chat_context (SYNC op MainThread)
    → _cockpit_companion_lookup → _ouroboros_subliminal_lookup_and_feed
      → quantum_foam.subliminal_quantum_foam_feed
        → _maybe_hard_collapse_locked (binnen Lock!)
          → _persist_essence → record_trigger_action → get_or_create_collection
            → httpx → HANG op chromadb POST /collections
```

Plus tweede deadlock: `_living_chat_echo` (synchroon vanuit `_with_cockpit_self_context`) doet `quantum_foam.status()` die op dezelfde Lock wacht die Thread 78 vasthoudt tijdens de hangende Chroma-call.

Twee threads tegelijk op identieke Chroma POST → chromadb client connection-pool / interne lock issue. Het hele uvicorn async event loop bevroor mee waardoor zelfs `/health` doodliep.

**Fix (3 lagen, geen quantum_foam wijziging):**

1. **`controller/main.py`** — `_rebuild_chat_context` is nu `async`; beide callsites awaiten. Nieuwe `_bounded_companion_lookup` wrapt subliminal lookup in `asyncio.to_thread + asyncio.wait_for(5s)` met nette timeout-payload als fallback.
2. **`controller/main.py`** — `_living_chat_echo` gebruikt `ThreadPoolExecutor(max_workers=1) + future.result(timeout=3s)` via nieuwe inner `_living_chat_echo_inner`; geeft compacte timeout-payload bij overschrijding.
3. **`controller/chroma_runtime.py`** — `chroma_client()` installeert httpx Timeout (default 8s, override met `WINTRIP_CHROMA_HTTP_TIMEOUT`) op de chromadb HttpClient via best-effort attribuut-injectie op `_session`, `_client`, `_api`, `_server`, `_async_client` + geneste `session`/`client`. Robust tegen chromadb upgrades door try/except per nested attribuut. Eindeloos hangen op Chroma POST is daarmee uitgesloten.

De ware root-cause (Chroma `create_collection` synchroon binnen een Lock in `_persist_essence`) zit nog in `ouroboros_esoteric/quantum_foam.py:2039`. Mijn fix bound dak op de zichtbare gevolgen. Toekomstig werk: verplaats `_persist_essence` werk **buiten** de Lock of maak het async.

## Verificatie

### Test resultaten

```
focused regression (109 tests, agentic_* + agent_tools + persistent_memory + chroma_runtime + approval_resume + persistent_memory_ooda)
  → OK in 36.2s
cd ouroboros_cockpit && npm run build
  → built in ~1.9s, 0 TypeScript errors
```

Volledige `python3 -m unittest discover sandbox_tests` heeft 8 pre-existing failures in `test_stream_daemon` (test-pollution in discover, slagen geïsoleerd), `test_living_runtime.test_agent_type_2_soulbook_is_loaded_from_markdown` en `test_nexus_status_truthful.test_summary_starts_degraded_with_no_events`. Reproduceren zonder mijn modules.

### Runtime smoke (live, na restart `docker restart wintripai-ouroboros-backend-1`)

```
GET  /health                                              200, "online", 133 memories
GET  /api/ouroboros/agentic/sessions                      200, empty list
GET  /api/ouroboros/agentic/policy/commands               200, 15 allow / 17 deny patterns
POST /api/cockpit/chat  {prompt:"hoi"}                    200 in 18s (was: 90s timeout)
POST /api/cockpit/chat  {plan_mode:"plan", session_id}    200 in 52s, route=agentic_processor, status=planned
GET  /api/ouroboros/agentic/sessions                      200, 1 sessie zichtbaar
GET  /api/ouroboros/agentic/sessions/<id>/events?compact  6 events: session_started → plan_built
                                                          → tool_planned×2 → memory_write
                                                          → session_completed
```

Plan-mode skipt tools (geen `tool_running`/`tool_completed` events), zoals ontworpen.

## Operationele aandachtspunten

- **Backend restart nodig** na pull: `docker restart wintripai-ouroboros-backend-1`. Het workspace is gemount (`.:/workspace`), dus geen rebuild.
- **Default tab van cockpit is nu `agent-workspace`** in plaats van `chat`. Wie de oude chat-view wil, klikt op tab 2.
- **Eerste chat-request blijft traag** (~18s) door subliminal-lookup retry binnen 5s timeout. Toekomstige requests onder een seconde zodra de Chroma-state hot is.
- **JSONL log groeit** in `out/agentic_sessions/events.jsonl`. Geen rotation; periodiek archiveren of `WINTRIP_AGENTIC_EVENT_BUS_NO_PERSIST=1` als snel-uit knop.
- **Env knoppen:**
  - `WINTRIP_AGENTIC_MAX_SESSIONS` (default 128)
  - `WINTRIP_AGENTIC_MAX_EVENTS` (default 512)
  - `WINTRIP_AGENTIC_SESSION_LOG` (default `out/agentic_sessions/events.jsonl`)
  - `WINTRIP_AGENTIC_EVENT_BUS_NO_PERSIST` (1/true/yes/on om JSONL-writes te skippen)
  - `WINTRIP_AGENTIC_LOOP_SOFT` (default 3) / `WINTRIP_AGENTIC_LOOP_HARD` (default 5)
  - `WINTRIP_CHROMA_HTTP_TIMEOUT` (default 8s, range 0.5-60)

## Guardrails gerespecteerd

- Geen secrets in nieuwe modules, UI of JSONL; alles via `redact()` vóór bus en disk.
- `Akkoord` is enige approval-poort; `_validate_step` en `tool_bridge` firewall onaangetast.
- Geen wijzigingen aan `/home/pwintri2/cline` (alleen-lezen referentie).
- Geen commit van `wintrip_brain/`, `data/chromadb/`, `.secrets/`, uploads of caches.
- Geen consciousness/sentience-claims; UI-labels operationeel ("Tool gepland", "Sessie klaar", "Wacht op Akkoord").
- Plan mode = read-only: zet status `planned`, runt geen tools.
- Cancel emit alleen `session_cancelled`; geen `git reset` of hard restore.

## Wat een volgende sessie kan oppakken

1. **Echte fix in `ouroboros_esoteric/quantum_foam.py:2039`**: `_persist_essence` synchrone Chroma-call buiten `_maybe_hard_collapse_locked` Lock plaatsen, of via threadpool met timeout. Mijn bound dak voorkomt freeze, maar de underlying race blijft.
2. **Shadow-git checkpoints**: `agentic_checkpoints.py` doet nu alleen diff-metadata. Echte shadow git zoals Cline (zie `/home/pwintri2/cline/src/integrations/checkpoints/CheckpointTracker.ts`) zou restore mogelijk maken zonder de live worktree te raken.
3. **File context tracker push**: nu is staleness pull-based (mtime check on `evaluate_path`). Met `watchdog` of inotify zou de UI realtime stale-warnings krijgen.
4. **Approval inline in Agent Workspace**: UI banner toont nu `tool_awaiting_approval`. Volgende stap: een approval-textinput in de timeline zelf zodat de gebruiker Akkoord direct kan invullen zonder naar de sidebar te navigeren.
5. **Resume/Replay van sessies**: alle events staan in JSONL. Een `/api/ouroboros/agentic/sessions/{id}/replay` endpoint kan een afgesloten sessie reconstrueren in de UI.

## Referenties

- Brief: [HANDOFF_CLINE_AGENTIC_POWER_TAURI_UI_2026-05-17.md](HANDOFF_CLINE_AGENTIC_POWER_TAURI_UI_2026-05-17.md)
- Run-prompt: [CLAUDE_CODE_PROMPT_CLINE_TO_OUROBOROS_2026-05-17.md](CLAUDE_CODE_PROMPT_CLINE_TO_OUROBOROS_2026-05-17.md)
- Cline reference (alleen-lezen): `/home/pwintri2/cline`
- AGENTS.md guardrails: [AGENTS.md](AGENTS.md)
- Shared runtime context: [OUROBOROS_IDE_CONTEXT.md](OUROBOROS_IDE_CONTEXT.md)
