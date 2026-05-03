# Handoff: Ouroboros Real Agent Orchestration

Datum: 2026-05-03  
Werkmap: `/home/pwintri2/WintripAI`  
Buildplan: `BUILDPLAN_OUROBOROS_REAL_AGENT_ORCHESTRATION_2026-05-03.md`

## Samenvatting

Philip wil dat `/codex`, `/roo`, `/claude` en `/ruflo` niet alleen een CLI-call of handoff doen, maar echte programmeer-agenten worden: taken aannemen, code aanpassen, tests draaien, backend/frontend stoppen en starten, een standalone UI bouwen en live voortgang tonen.

Het huidige systeem heeft al losse bouwstenen:

- `controller/slash_agent_router.py` routeert slash commands.
- `scripts/rclone_host_bridge.py` kan host-agent commands aanroepen.
- `controller/roo_tools.py` kan lokaal lezen, zoeken, patchen en commands draaien.
- `controller/ouroboros_self_context.py` geeft gedeelde systeemcontext.
- `ouroboros_cockpit/src/App.tsx` toont slash buttons en chat-output.

Wat ontbreekt is een echte agent runtime met jobs, events, logs, status, cancellation, service-control en UI job board.

## Belangrijkste Besluit

Slash commands moeten job starters worden, niet de uitvoeringsruntime zelf.

Nieuw gedrag:

```text
/codex <taak>  -> maakt agent job aan
/claude <taak> -> maakt agent job aan
/roo <taak>    -> maakt agent job aan
/ruflo <taak>  -> maakt swarm job aan
/jobs          -> toont live jobs
/job <id>      -> toont detail/events
/cancel <id>   -> stopt job
```

## Eerste Vertical Slice

Begin niet met de hele swarm. Bouw eerst dit:

1. Maak `controller/agent_runtime/`.
2. Voeg persistent job store toe in `.secrets/agent_runtime/jobs.json`.
3. Voeg event logs toe in `out/agent_runtime/<job_id>/events.jsonl`.
4. Verplaats Codex execution uit `slash_agent_router.py` naar `controller/agent_runtime/adapters/codex_cli.py`.
5. Laat `/codex <taak>` een achtergrondjob starten en direct `job_id` teruggeven.
6. Voeg API routes toe:
   - `POST /api/agent-runtime/jobs`
   - `GET /api/agent-runtime/jobs`
   - `GET /api/agent-runtime/jobs/{job_id}`
   - `GET /api/agent-runtime/jobs/{job_id}/events`
   - `POST /api/agent-runtime/jobs/{job_id}/cancel`
7. Voeg een eenvoudig Agent Jobs paneel toe in de cockpit.

Acceptatie voor deze eerste slice:

- `/codex Antwoord alleen met test` geeft meteen een `job_id`.
- De backend blijft responsive.
- Jobstatus wordt `queued -> running -> completed`.
- `stdout.log`, `stderr.log`, `events.jsonl` en `result.json` worden geschreven.
- Cockpit kan jobstatus en events tonen.
- Bestaande tests blijven groen.

## Daarna

### Fase 2: Tool Bridge

Voeg `tool_bridge.py` toe bovenop `roo_tools.py` en `safe_shell.py`:

- read/list/search
- apply patch
- run command
- run tests
- git status/diff

### Fase 3: Service Control

Voeg `service_control.py` toe met profielen:

- `backend_sandbox_allow`
- `cockpit_vite`

Agents kunnen dan backend/frontend status checken, herstarten en logs lezen.

### Fase 4: Claude Adapter

Maak `adapters/claude_code.py`:

- gebruikt `claude -p`
- parse JSON output
- schrijft events
- geeft `login_required` als auth ontbreekt

### Fase 5: Ruflo Swarm

Maak `adapters/ruflo_swarm.py`:

- Ruflo maakt plan en rollen.
- Subtaken worden echte Codex/Claude/Roo jobs.
- Reviewer/tester jobs verzamelen eindresultaat.

### Fase 6: Roo Worker

Maak Roo meer dan handoff:

- plan kleine taak
- zoek files
- maak patch
- draai tests
- rapporteer diff

## Niet Vergeten

- Geen `.secrets`, tokens, OAuth, bearer strings of browser sessions loggen.
- Geen runtime DB's committen:
  - `wintrip_brain/*.sqlite3`
  - `controller/wintrip_brain/*.sqlite3`
- Grote lokale checkouts zoals `litgpt/` en `unsloth/` niet automatisch committen.
- Respecteer bestaande dirty worktree.
- Bij commit selectief stagen.

## Huidige Git Status

Het buildplan is nog untracked:

```text
BUILDPLAN_OUROBOROS_REAL_AGENT_ORCHESTRATION_2026-05-03.md
```

Deze handoff is ook nieuw en moet mee als de agent-runtime planning gecommit wordt:

```text
HANDOFF_OUROBOROS_REAL_AGENT_ORCHESTRATION_2026-05-03.md
```

## Aanbevolen Volgende Opdracht

```text
Implementeer Fase 1 uit BUILDPLAN_OUROBOROS_REAL_AGENT_ORCHESTRATION_2026-05-03.md: maak controller/agent_runtime, bouw een Codex background job adapter, voeg /api/agent-runtime/jobs routes toe, laat /codex jobs starten en voeg gerichte tests toe.
```

## Verificatie Na Fase 1

Draai minimaal:

```bash
python3 -m py_compile controller/slash_agent_router.py controller/main.py
python3 -m unittest sandbox_tests.test_slash_agent_router sandbox_tests.test_tauri_backend_routes -v
docker exec -w /workspace wintrip-standalone-ui python3 -m unittest sandbox_tests.test_slash_agent_router sandbox_tests.test_tauri_backend_routes -v
```

Voeg nieuwe tests toe voor de agent runtime store/orchestrator zodra de module bestaat.
