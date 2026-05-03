# Buildplan: Ouroboros Real Agent Orchestration

Datum: 2026-05-03  
Eigenaar: Codex / Ouroboros cockpit  
Status: klaar voor implementatie  

## Probleem

De huidige `/codex`, `/roo`, `/claude` en `/ruflo` integratie is vooral een router:

- `/codex` start een headless CLI-run en geeft output terug.
- `/claude` kan een Claude Code prompt uitvoeren als auth klopt.
- `/ruflo` maakt swarm-state aan, maar voert nog geen betrouwbaar end-to-end ontwikkelwerk uit.
- `/roo` is grotendeels een Python tool-adapter of IDE-handoff.

Dat voelt alsof er "iets gebeurt", maar niet alsof er echte programmeer-agenten aan het werk gaan. Wat ontbreekt is een agent runtime: taken, planning, werkruimtes, toolgebruik, logs, status, retries, patch review, test runs, service control en UI feedback.

## Doelbeeld

Philip typt in de cockpit:

```text
/codex Maak een standalone UI voor de agent jobs, stop de oude backend als nodig, voeg tests toe en start de nieuwe backend.
```

Of:

```text
/ruflo Laat een swarm uitzoeken waarom de training-loop langzaam is en laat coder/tester agents de fix implementeren.
```

Daarna gebeurt echt dit:

1. Ouroboros maakt een agent job aan.
2. De job krijgt WintripAI, Ruflo, Roo en Codex context.
3. De gekozen agent of swarm maakt een plan.
4. Workers kunnen bestanden lezen, patches maken, commands draaien, tests starten, backend/frontend stoppen/starten en logs bekijken.
5. De cockpit toont live events, stdout/stderr, gewijzigde bestanden, testresultaten en eindstatus.
6. Bij completion staat er een bruikbaar resultaat: patch, commit-ready diff, gestart dev server, of concrete foutmelding.

## Architectuur

### 1. Agent Job Runtime

Nieuw modulepad:

```text
controller/agent_runtime/
  __init__.py
  models.py
  store.py
  orchestrator.py
  events.py
  workers.py
  tool_bridge.py
  service_control.py
  adapters/
    codex_cli.py
    claude_code.py
    ruflo_swarm.py
    roo_local.py
```

Taken worden persistent opgeslagen in:

```text
.secrets/agent_runtime/jobs.json
out/agent_runtime/<job_id>/
  prompt.md
  plan.md
  events.jsonl
  stdout.log
  stderr.log
  patch.diff
  result.json
```

Belangrijk: `.secrets` blijft lokaal en wordt niet gecommit.

### 2. Job Model

Elke taak krijgt een echt lifecycle-model:

```text
queued -> planning -> running -> testing -> waiting_for_human -> completed
                                      \-> failed
                                      \-> cancelled
```

Velden:

- `job_id`
- `agent`: `codex | claude | roo | ruflo | swarm`
- `task`
- `status`
- `created_at`, `started_at`, `finished_at`
- `workspace_root`
- `allowed_roots`
- `changed_files`
- `commands_run`
- `tests_run`
- `service_actions`
- `result_summary`
- `artifacts`

### 3. Tool Bridge

Agents krijgen niet alleen een prompt, maar een expliciete capability pack:

- `read_file(path)`
- `list_files(path)`
- `search_files(path, regex)`
- `write_file(path, content)`
- `apply_patch(patch)`
- `run_command(command, timeout)`
- `run_tests(selector)`
- `git_diff()`
- `git_status()`
- `start_backend(profile)`
- `stop_backend(profile)`
- `restart_backend(profile)`
- `start_frontend(profile)`
- `stop_frontend(profile)`
- `open_browser(url)`
- `screenshot_app(url)`
- `record_artifact(path)`

De bestaande `roo_tools.py`, `safe_shell.py`, `start_ouroboros_sandbox_allow.sh` en host bridge worden hergebruikt, maar krijgen een runtime-laag erboven.

### 4. Host Bridge V2

De huidige `scripts/rclone_host_bridge.py` is te smal en te veel rclone-gekleurd. Maak een aparte host bridge:

```text
scripts/ouroboros_host_agent_bridge.py
```

Endpoints:

- `GET /agent-runtime/status`
- `POST /agent-runtime/jobs`
- `GET /agent-runtime/jobs`
- `GET /agent-runtime/jobs/{job_id}`
- `POST /agent-runtime/jobs/{job_id}/cancel`
- `GET /agent-runtime/jobs/{job_id}/events`
- `POST /agent-runtime/tools/run`
- `POST /agent-runtime/services/restart`

De oude rclone bridge kan blijven bestaan, maar `/agents/command` verhuist uiteindelijk naar deze runtime bridge.

### 5. Adapters

#### Codex Adapter

Doel: Codex laten werken zoals deze sessie: lezen, patchen, testen, rapporteren.

Implementatie:

- Start `codex exec` als achtergrondjob.
- Gebruik `--cd /home/pwintri2/WintripAI`.
- Voeg roots toe:
  - `/home/pwintri2/ruflo`
  - `/home/pwintri2/Roo`
  - `/home/pwintri2/Codex`
- Geef een duidelijke system prompt mee met:
  - taak
  - contextbestanden
  - bestaande dirty worktree respecteren
  - tests draaien
  - gewijzigde files rapporteren
- Stream stdout/stderr naar `events.jsonl`.
- Parse eindantwoord en `git diff --name-only`.
- Laat langlopende taken als job doorlopen; de chat wacht niet.

#### Claude Code Adapter

Doel: Claude Code als echte code-worker gebruiken.

Implementatie:

- Start `claude -p <prompt> --permission-mode acceptEdits --output-format json`.
- Voeg dezelfde context en roots toe.
- Parse JSON-resultaat.
- Sla cost/usage/result op.
- Bij login nodig: return `login_required` met browser/CLI-instructie.

#### Ruflo Swarm Adapter

Doel: Ruflo niet alleen laten initialiseren, maar laten coordineren.

Implementatie:

1. Maak een Ruflo swarm job.
2. Spawn rollen:
   - coordinator
   - architect
   - coder
   - tester
   - reviewer
3. Vertaal de Ruflo taak naar concrete worker subtaken.
4. Laat subtaken uitvoeren door Claude Code of Codex workers, niet alleen door Ruflo-state.
5. Verzamel output in een gezamenlijke job.
6. Laat reviewer/tester de diff valideren.

Belangrijk: Ruflo is coordinator; echte file edits komen via worker adapters.

#### Roo Adapter

Doel: Roo moet niet alleen handoff zijn, maar direct nuttige lokale acties doen.

Implementatie:

- Hou de bestaande `roo_tools.py` als lokale adapter.
- Voeg een `roo plan` mode toe:
  - opdracht analyseren
  - benodigde files zoeken
  - patch voorstellen
  - patch toepassen indien approval/preapproval actief is
- Als een echte Roo CLI/API beschikbaar is, voeg `RooCliAdapter` toe.
- Tot die tijd is Roo de betrouwbare tool-worker voor file/search/patch/command.

### 6. Slash Commands Worden Job Starters

Huidig:

```text
/codex <task> -> direct CLI-call
```

Nieuw:

```text
/codex <task>  -> create job(agent=codex)
/claude <task> -> create job(agent=claude)
/roo <task>    -> create job(agent=roo)
/ruflo <task>  -> create job(agent=ruflo_swarm)
/agents        -> catalog + live job status
/jobs          -> laatste jobs
/job <id>      -> detail + logs
/cancel <id>   -> cancel
```

De chat krijgt meteen antwoord:

```text
Job gestart: agent_20260503_...
Status: running
Volg live in Agent Jobs.
```

### 7. Cockpit UI

Voeg een echte Agent Jobs sectie toe.

Views:

- Job list
- Job detail
- Live event log
- Changed files
- Diff preview
- Commands run
- Test results
- Service status
- Buttons:
  - cancel
  - rerun tests
  - apply suggested patch
  - restart backend
  - restart frontend
  - commit selected changes

De chat blijft de ingang, maar niet de enige feedbackplek.

### 8. Service Control

Maak service-profielen:

```text
backend_sandbox_allow:
  start: ./start_ouroboros_sandbox_allow.sh
  health: http://localhost:8010/health
  logs: artifacts/backend_sandbox_allow.log

cockpit_vite:
  start: npm run dev -- --host 127.0.0.1 --port 5173
  cwd: ouroboros_cockpit
  health: http://localhost:5173
  logs: artifacts/ouroboros_cockpit_vite.log
```

Agents mogen dan gericht:

- status checken
- stoppen
- starten
- herstarten
- logs lezen

### 9. Browser Login En Menselijke Sessies

Voor Claude/Codex/Google/Microsoft:

- Geen tokens in logs of memory.
- Als login nodig is, maakt de adapter een `login_required` event.
- Cockpit opent browser of toont CLI-opdracht.
- Daarna kan de job opnieuw starten of verdergaan.

Voorbeeld:

```json
{
  "status": "waiting_for_human",
  "reason": "Claude Code login required",
  "frontend_action": {
    "type": "open_url",
    "url": "https://claude.ai/login"
  }
}
```

### 10. Git En Dirty Worktree

Agents mogen werken in een dirty worktree, maar moeten registreren:

- welke files al dirty waren
- welke files zij wijzigen
- welke tests zij draaiden
- welke files ze bewust niet aanraken

Commit-flow:

- `/commit` of UI-button maakt commit van geselecteerde files.
- Nooit automatisch runtime DB's, token files, `.secrets`, grote checkouts of logs committen.

## Implementatiefases

### Fase 1: Runtime Fundament

Doel: `/codex` en `/claude` worden echte achtergrondjobs.

Taken:

1. Maak `controller/agent_runtime/models.py`.
2. Maak `controller/agent_runtime/store.py`.
3. Maak `controller/agent_runtime/events.py`.
4. Maak `controller/agent_runtime/orchestrator.py`.
5. Verplaats Codex job-logica uit `slash_agent_router.py` naar `adapters/codex_cli.py`.
6. Voeg API routes toe:
   - `POST /api/agent-runtime/jobs`
   - `GET /api/agent-runtime/jobs`
   - `GET /api/agent-runtime/jobs/{job_id}`
   - `GET /api/agent-runtime/jobs/{job_id}/events`
   - `POST /api/agent-runtime/jobs/{job_id}/cancel`
7. Laat slash commands jobs aanmaken.

Acceptatie:

- `/codex wijzig README en draai test X` geeft direct `job_id`.
- Job loopt door op host.
- Cockpit kan jobstatus ophalen.
- Backend blijft responsive.

### Fase 2: Tool Bridge En Service Control

Doel: agents kunnen echt bouwen, testen en services beheren.

Taken:

1. Maak `tool_bridge.py`.
2. Hergebruik `roo_tools.py` voor file/patch/search.
3. Voeg `service_control.py` toe.
4. Voeg service-profielen toe in `artifacts/ouroboros_services.json`.
5. Maak endpoints voor tool/service acties.
6. Voeg tests toe voor command allowlist, patch, service restart en log read.

Acceptatie:

- Agent kan backend restart aanvragen.
- Agent kan frontend dev server starten.
- Agent kan tests draaien en output opslaan.
- Geen secrets in event logs.

### Fase 3: Cockpit Agent Jobs UI

Doel: je ziet agents echt werken.

Taken:

1. Voeg Agent Jobs paneel toe in `ouroboros_cockpit/src/App.tsx`.
2. Poll `/api/agent-runtime/jobs`.
3. Toon live events.
4. Toon changed files en diff.
5. Voeg job actions toe:
   - cancel
   - rerun tests
   - restart backend
   - commit selected

Acceptatie:

- Een langlopende Codex/Claude taak is zichtbaar.
- Je ziet stdout/stderr/testresultaten zonder devtools.
- UI blijft bruikbaar terwijl jobs lopen.

### Fase 4: Ruflo Swarm Echt Maken

Doel: `/ruflo` gebruikt echte swarm-rollen en worker execution.

Taken:

1. Maak `adapters/ruflo_swarm.py`.
2. Laat Ruflo coordinator plan maken.
3. Split subtaken naar worker jobs.
4. Laat coder/tester/reviewer jobs parallel of sequentieel draaien.
5. Voeg merge/review stap toe.

Acceptatie:

- `/ruflo bouw X` maakt minimaal coordinator + coder + tester jobs.
- Coder wijzigt files.
- Tester draait tests.
- Reviewer vat risico's samen.

### Fase 5: Roo Als Directe Build Worker

Doel: `/roo` wordt niet alleen handoff, maar kan kleine wijzigingen zelf doen.

Taken:

1. Maak Roo planner bovenop `roo_tools`.
2. Voeg patch-generation flow toe.
3. Laat Roo tests draaien.
4. Maak Roo-resultaat consistent met Codex/Claude jobs.

Acceptatie:

- `/roo voeg test toe voor X` zoekt file, maakt patch, draait test.
- Geen IDE-handoff tenzij taak te groot is of echte Roo CLI nodig is.

### Fase 6: Autonomie-Profielen

Doel: dezelfde runtime kan voorzichtig of vrij werken.

Profielen:

- `observe`: alleen lezen, plannen, status.
- `edit`: files wijzigen, tests draaien.
- `operate`: backend/frontend stop/start/restart.
- `swarm`: meerdere worker jobs.
- `sandbox_full`: edit + operate + swarm, met secret-redaction en git-exclude regels.

In sandbox mag standaard:

```text
WINTRIP_AGENT_AUTONOMY=sandbox_full
WINTRIP_SANDBOX_PREAPPROVED=1
```

Maar secrets blijven altijd uitgesloten van logs en memory.

## Tests

Nieuwe tests:

```text
sandbox_tests/test_agent_runtime_store.py
sandbox_tests/test_agent_runtime_orchestrator.py
sandbox_tests/test_agent_runtime_services.py
sandbox_tests/test_agent_runtime_api.py
sandbox_tests/test_agent_runtime_cockpit.py
sandbox_tests/test_ruflo_swarm_adapter.py
```

Belangrijkste scenario's:

- job aanmaken
- job events schrijven
- Codex mock-job wordt completed
- langlopende job blijft backend niet blokkeren
- cancel stopt proces
- service restart schrijft event
- secrets worden geredact
- dirty worktree baseline wordt opgeslagen
- slash command maakt job in plaats van blocking call

## Eerste Vertical Slice

De kleinste nuttige implementatie:

1. Agent runtime store.
2. Codex adapter als achtergrondjob.
3. `/api/agent-runtime/jobs`.
4. `/codex` maakt job.
5. Cockpit toont job list + detail.
6. Service control alleen voor backend restart.
7. Tests groen.

Daarmee is het systeem meteen zichtbaar meer "echt": Codex gaat werken, de chat blijft vrij, en jij ziet in de UI wat er gebeurt.

## Waarom Dit Nu De Juiste Stap Is

De huidige integratie heeft genoeg losse onderdelen: Codex CLI, Claude CLI, Roo tools, Ruflo, host bridge, cockpit, service scripts. Het probleem is niet nog een extra knop. Het probleem is dat er geen gezamenlijke runtime is die werk vasthoudt, volgt en afmaakt.

Deze build maakt Ouroboros van slash-command demo naar lokaal agentisch ontwikkelsysteem.
