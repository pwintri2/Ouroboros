# HANDOFF: Fase 8 Agent Context + Standalone Cockpit

Datum: 2026-05-04
Werkruimte: `/home/pwintri2/WintripAI`
Status: klaar voor vervolgwerk

## Samenvatting

Deze sessie corrigeerde drie zichtbare problemen:

1. De echte Tauri standalone cockpit werd verward met de oude HTML/web UI.
2. Project Context gaf `--` of hing, omdat `/context/summary` te traag was in Docker en de file-tree/changed-files routecontracten niet robuust genoeg waren.
3. AgentS/OpenHands bestonden backend-side, maar waren niet zichtbaar in de cockpit.

De oude webserver op poort `3000` is uitgezet. De echte standalone Tauri cockpit draait nu via:

```text
systemd --user service: ouroboros-cockpit-standalone.service
native process: target/debug/ouroboros-cockpit
internal devUrl: http://127.0.0.1:1420/
backend: http://127.0.0.1:8010/
host bridge: http://127.0.0.1:8766/
```

Let op: `1420` blijft normaal zichtbaar, omdat Tauri dev mode Vite als interne webview-bron gebruikt. De gebruiker moet het native venster `Ouroboros Cockpit` gebruiken, niet de browser/HTML versie.

## Belangrijkste wijzigingen

### Grok en World Agent

- Natuurlijke prompts zoals `Kun je aan grok vragen ...` worden naar de World Agent gerouteerd in plaats van naar Ollama.
- De frontend action opent Grok met de vraag in de querystring, bijvoorbeeld `https://grok.com/?q=...`.
- Grok login/rate-limit wordt eerlijk als `login_required` of `rate_limited` gemeld; geen fake success.

Belangrijke bestanden:

- `controller/world_agent.py`
- `controller/main.py`
- `ouroboros_cockpit/src/App.tsx`

### Fase 8 basis

Nieuwe Fase 8 laag:

- `controller/fase8_agent.py`
- `controller/external_capabilities.py`

Endpoints:

- `GET /api/fase8/status`
- `GET /api/fase8/external-capabilities`
- `POST /api/fase8/plan`
- `POST /api/fase8/tools/dispatch`
- `POST /orchestrator/run`
- `GET /orchestrator/status/{task_id}`
- `POST /orchestrator/stop/{task_id}`

Tool schema's nu zichtbaar:

- `external_capabilities_status`
- `agent_runtime_submit`

### AgentS/OpenHands zichtbaar

De host bridge exposeert nu veilige capability-introspectie voor:

- `/home/pwintri2/AgentS`
- `/home/pwintri2/OpenHands`

Zonder secret-like files te lezen.

Live status tijdens overdracht:

```text
AgentS: available
OpenHands: available
via_bridge: true
```

Cockpit toont nu op Main een paneel `Agent Capabilities` met:

- AgentS status en entrypoints
- OpenHands status en entrypoints
- Roo status en tool count
- Codex job count
- Runtime tools
- Fase 8 tool schemas

### Project Context hersteld

`controller/project_context.py` is herschreven naar een snellere, veiligere aanpak:

- gebruikt git-tracked/untracked file lists waar mogelijk
- sluit zware/runtime/secret-like paden uit
- valt terug op veilige filesystem-walk
- gebruikt host bridge wanneer Docker geen `git` of snelle context heeft

Routes:

- `GET /context/summary`
- `GET /context/file_tree`
- `GET /context/file-tree`
- `GET /context/changed_files`
- `GET /context/changed-files`

Live verificatie tijdens overdracht:

```text
/context/summary: 0.139s
via_bridge: true
Total Files: 326
Changed Files: 19
Test Files: 50
```

## Verificatie

Gedraaid:

```bash
python3 -m py_compile controller/project_context.py scripts/rclone_host_bridge.py controller/api/trainer_pipeline_routes.py controller/main.py
python3 -m unittest sandbox_tests.test_tauri_backend_routes sandbox_tests.test_fase8_agent -v
docker exec -w /workspace wintrip-standalone-ui python3 -m unittest sandbox_tests.test_tauri_backend_routes sandbox_tests.test_fase8_agent -v
npm --prefix ouroboros_cockpit run build
cd ouroboros_cockpit/src-tauri && cargo check
```

Resultaten:

```text
Container tests: 23 tests OK
Host Fase 8 tests: OK, FastAPI route tests skipped on host because fastapi is not installed there
Frontend build: OK, known Vite chunk-size warning only
Cargo check: OK
```

Live smoke:

```text
/health: online
/context/summary: success, via_bridge=true
/api/fase8/external-capabilities: AgentS/OpenHands available
/api/agent-runtime/tools/status: online
/api/ouroboros/loop/status: completed, running=false
```

Frontend smoke via internal Tauri devUrl confirmed:

```text
PROJECT CONTEXT
Total Files 326
Changed Files 19
Test Files 50

AGENT CAPABILITIES
AgentS available
OpenHands available
Roo online
Codex jobs 6
Runtime tools read_file, write_file, apply_patch, run_command
Fase 8 tools external_capabilities_status, agent_runtime_submit
```

## Niet meenemen in commit

Niet gerelateerd aan deze codewijziging en bewust buiten de commit gehouden:

```text
wintrip_brain/*
Ouroboros_Grow.docx
Ouroboros_Grow.odt
Quantum Cognitive Corruption Nexus.docx
ZetaPlan.docx
.~lock.*.docx#
```

## Bekende beperkingen

- Codex in de cockpit is nog een slash-agent/job runner, niet volledig gelijkwaardig aan de Codex sessie in deze IDE.
- Roo is zichtbaar via adapter/tools; de VS Code Roo-extension zelf wordt niet rechtstreeks bestuurd.
- AgentS/OpenHands zijn nu capability-visible, maar nog niet als volledige veilige execution adapters ingebouwd.
- OpenHands `start_openhands.sh` moet niet blind door Ouroboros gestart worden; dat script kan Docker socket permissies aanpassen.
- Grok browserflow is afhankelijk van login/rate-limit bij Grok zelf. Er wordt geen sessiemateriaal opgeslagen of gebypasst.

## Aanbevolen volgende stappen

1. Maak Codex in de cockpit een echte persistente coding-agent:
   - job start
   - live events
   - patch/test loop
   - duidelijke changed-files/artifacts
   - stop/cancel

2. Voeg een Goal/Plan view toe voor Fase 8:
   - plan steps
   - current step
   - result per step
   - stop/retry controls

3. Maak AgentS/OpenHands adapters expliciet en veilig:
   - AgentS alleen in geisoleerde GUI sessie
   - OpenHands via V1 app-server/SDK, niet via directe low-level execute endpoints
   - alle schrijf/host-acties achter exact `Akkoord`

4. Breid tool-calling uit:
   - LLM JSON tool choice
   - deterministic fallback
   - tool choice logging in memory

5. Voeg cockpit tests toe die de zichtbaarheid van Agent Capabilities en Project Context borgen.

## Commit-scope

Deze handoff hoort samen met de codewijzigingen voor:

- Fase 8 runner/dispatcher/capabilities
- Grok frontend question URL
- Project Context bridge/fallback
- Agent Capabilities cockpit panel
- route/test contract fixes
