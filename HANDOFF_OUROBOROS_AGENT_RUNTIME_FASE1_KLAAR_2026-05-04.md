# Handoff: Ouroboros Agent Runtime — Fase 1 vertical slice klaar

Datum: 2026-05-04
Werkmap: `/home/pwintri2/WintripAI`
Vorige handoff: `HANDOFF_OUROBOROS_REAL_AGENT_ORCHESTRATION_2026-05-03.md`
Buildplan: `BUILDPLAN_OUROBOROS_REAL_AGENT_ORCHESTRATION_2026-05-03.md`

## Status in één zin

`/codex <opdracht>` werkt nu echt: cockpit → backend (container) → host bridge → host-zijde Codex CLI. De Agent Jobs panel laat de job live verschijnen, events streamen, status loopt door van `running` naar `completed`/`failed`.

## Wat er live draait

- Host bridge: `python3 scripts/rclone_host_bridge.py` op `0.0.0.0:8766`. Token in `.secrets/rclone_bridge_token`.
- Backend: uvicorn binnen `wintrip-standalone-ui` container, op `0.0.0.0:8010`, met env:
  - `WINTRIP_RCLONE_BRIDGE_URL=http://host.docker.internal:8766`
  - `WINTRIP_RCLONE_BRIDGE_TOKEN_PATH=/workspace/.secrets/rclone_bridge_token`
  - sandbox-allow env zoals voorheen.
- Cockpit: vite dev server op `127.0.0.1:5173` (eigen proces buiten container).

Routes geregistreerd in OpenAPI:
- `POST /api/agent-runtime/jobs`
- `GET  /api/agent-runtime/jobs`
- `GET  /api/agent-runtime/jobs/{job_id}`
- `GET  /api/agent-runtime/jobs/{job_id}/events`
- `POST /api/agent-runtime/jobs/{job_id}/cancel`

## Wat in deze sessie is gebouwd

### Nieuwe module `controller/agent_runtime/`
- `models.py`: `JobRecord` dataclass + lifecycle vocabulaire (queued → planning → running → testing → waiting_for_human → completed/failed/cancelled). Phase 1 gebruikt queued/running/completed/failed/cancelled.
- `store.py`: persistente JSON-store onder `.secrets/agent_runtime/jobs.json`, artifacts onder `out/agent_runtime/<job_id>/`. Schrijft **in-place** (geen temp+rename), zie waarschuwing hieronder.
- `events.py`: append-only JSONL event log met paged reads.
- `orchestrator.py`: `AgentOrchestrator` met process-singleton (`get_orchestrator()`), submit/cancel/list/get/read_events. Vertaalt artifact-paths host↔container via `_resolve_artifact_path`.
- `adapters/codex_cli.py`: `CodexCliAdapter` start `codex exec` als subprocess, polled cancel/timeout, redact secrets, schrijft events.

### Wiring
- `controller/slash_agent_router.py`: `_run_codex_exec` delegeert nu naar de orchestrator (was inline subprocess + handmatige job-state JSON). Zoekt Codex CLI ook in `~/.windsurf`, `~/.vscode`, `~/.antigravity`, `~/.cursor` extension dirs.
- `controller/api/agent_runtime_routes.py`: FastAPI router met de 5 routes hierboven, in `controller/main.py` aangezet via `init_agent_runtime(app)`.
- `controller/agent_runtime/adapters/codex_cli.py`: `default_codex_env()` voegt dezelfde extension-bin paden toe.

### Cockpit (`ouroboros_cockpit/src/App.tsx`)
- Nieuwe types `AgentJob`, `AgentJobEvent`.
- State `agentJobs`, `selectedAgentJobId`, `agentJobEvents`.
- Refresh poll naar `/api/agent-runtime/jobs?limit=20` op de Main tab (5s tick).
- Aparte 2.5s poll naar `/api/agent-runtime/jobs/{id}/events` zodra een job geselecteerd is.
- Nieuwe panel "Agent Jobs" in de cockpit-grid: lijst met agent + status, klikbare rij om events live te zien, cancel-knop voor non-terminale jobs.
- `sendChat()`: na een slash-agent response met `job.job_id` direct selecteren en de jobs-lijst opnieuw ophalen — geen 5s wachten.
- Slash-prompt zonder `Akkoord`: gele pill onder de textarea wijst je naar het Akkoord veld.
- `api()` helper: errors als `HTTP <code>: <detail>` ipv `[object Object]`.
- TrainerPanel `createJob()`: client-side validatie van `base_model` zodat de "Failed to create job" 422-spam stopt.

### Tests
- `sandbox_tests/test_agent_runtime_store.py` — 9 tests (store + event log).
- `sandbox_tests/test_agent_runtime_orchestrator.py` — 7 tests (create/submit/cancel/exception/adapter-registry).
- `sandbox_tests/test_agent_runtime_api.py` — 6 FastAPI route tests (host skipt zonder fastapi; draait wel binnen container).
- `sandbox_tests/test_slash_agent_router.py` — bestaande 7 tests, "running not blocking forever" herschreven tegen de nieuwe orchestrator.

Alle 23 hosttests zijn groen.

## De grootste les van deze sessie: fakeowner mount caching

`wintrip-standalone-ui` mount `/workspace` via Docker Desktop's `fakeowner` overlay. Die overlay cached files **op inode**. Editors die schrijven via temp+rename (de standaard van Edit/Write tools) maken een nieuwe inode → de container blijft de oude versie zien terwijl de host de nieuwe heeft.

Symptoom dat we hebben gehad:
- Host `controller/main.py` had `init_agent_runtime(app)` (md5 X, 84541 bytes).
- Container `/workspace/controller/main.py` had die regel niet (md5 Y, 84517 bytes).
- Sentinel-bestand werkte wel (toonde dat de mount op zich live is, maar bestaande inodes worden gepind).

**Workaround die werkt**: rewrite in-place (open in `wb` mode op hetzelfde pad, schrijf bytes terug). Inode blijft hetzelfde, container ziet meteen de nieuwe content.

```bash
python3 -c "p='controller/main.py'; d=open(p,'rb').read(); open(p,'wb').write(d)"
```

Daarom is `JobStore._save_payload` gewijzigd naar in-place truncate+write (zie commentaar in [`controller/agent_runtime/store.py`](controller/agent_runtime/store.py)) — anders zou jobs.json elke save een nieuwe inode krijgen en zou de container nooit job-updates van de host zien.

## Restart commando

```bash
nohup python3 /home/pwintri2/WintripAI/scripts/rclone_host_bridge.py \
  > /home/pwintri2/WintripAI/artifacts/rclone_host_bridge.log 2>&1 &

WINTRIP_RCLONE_BRIDGE_HOST_IP=host.docker.internal \
  bash /home/pwintri2/WintripAI/start_ouroboros_sandbox_allow.sh
```

Belangrijk: `WINTRIP_RCLONE_BRIDGE_HOST_IP=host.docker.internal` is nodig op Docker Desktop op Linux — `172.17.0.1` (de default in het start script) werkt **niet** vanuit de container, ook al is dat de docker0 IP. Reden: Docker Desktop draait een eigen netnamespace.

## Verifiëren dat alles werkt

```bash
# host bridge
ss -tlnp | grep 8766                                      # moet luisteren
curl -s -H "X-Ouroboros-Bridge-Token: $(cat .secrets/rclone_bridge_token)" \
  http://127.0.0.1:8766/status                            # verwacht: rclone status JSON

# backend in container
docker exec wintrip-standalone-ui python3 -c "
import urllib.request, json
with urllib.request.urlopen('http://127.0.0.1:8010/api/agent-runtime/jobs') as r:
    print(json.loads(r.read())['count'])
"                                                         # verwacht een getal, geen 404

# tests
python3 -m unittest sandbox_tests.test_agent_runtime_store \
  sandbox_tests.test_agent_runtime_orchestrator \
  sandbox_tests.test_slash_agent_router                   # 23 tests OK
```

End-to-end smoke test (cockpit als browser):
```bash
docker exec wintrip-standalone-ui python3 -c "
import urllib.request, json
body = json.dumps({'provider':'ollama','model':'llama3.2:latest',
                   'prompt':'/codex echo hello','approval':'Akkoord'}).encode()
req = urllib.request.Request('http://127.0.0.1:8010/api/cockpit/chat',
                             data=body, headers={'Content-Type':'application/json'})
print(json.loads(urllib.request.urlopen(req, timeout=30).read()))
"
# verwacht: status=running, route=slash_agent, via_bridge=True, job.job_id ingevuld
```

## Wat er nog NIET zit (bewust uitgesteld naar Fase 2+)

- **Direct `/api/agent-runtime/jobs` POST in de container** roteert NIET via de bridge. Als je via curl een job maakt op de container API faalt die met "codex not found" omdat de container zelf geen Codex CLI heeft. De chat-route (`/api/cockpit/chat` met `/codex ...`) werkt wel omdat slash_agent_router de bridge prefereert.
- **Claude / Roo / Ruflo adapters in de runtime**: nog steeds via de oude slash-router code paths. Claude+Ruflo gaan via dezelfde host bridge. Roo blijft IDE-handoff of lokale tool-adapter.
- **Tool bridge** (`tool_bridge.py`): file/patch/test API voor adapters. Nog niet aangevangen.
- **Service control** (`service_control.py`): backend/frontend stop/start/restart vanuit een agent. Nog niet aangevangen.
- **Cockpit polish**: diff preview, "rerun tests" knop, "commit selected" knop, restart-backend knop. Alleen list/cancel/events zijn er nu.
- **Ruflo swarm adapter**: Ruflo coordineert wel state, maar spawnt nog geen echte Codex/Claude worker jobs via de orchestrator.

## Bekende eigenaardigheden

- **Browser extension noise**: in normale Chrome zag je `Uncaught (in promise) Error: Could not establish connection. Receiving end does not exist.` Dat komt uit een browser extension's `content_script.js`, niet uit de cockpit. In incognito is hij weg.
- **Curl van host naar `127.0.0.1:8010` time-out soms**: de backend bind 0.0.0.0:8010 in de container, port 8010 is gemapt op de host, maar Docker Desktop's port-proxy hangt soms. Doet er weinig toe — de browser verbindt via de docker bridge en werkt vlot. Als debug nodig is: `docker exec wintrip-standalone-ui python3 -c "import urllib.request; ..."`.
- **Trainer panel `Failed to create job`**: pre-existing 422 die we client-side hebben afgevangen. Echte fix (server-side default voor `base_model` of betere error response) zit niet in deze handoff.

## Aanbevolen volgende stap

1. Fase 2 starten: `tool_bridge.py` en `service_control.py`. Daarmee krijgen agents een veilige API om files te lezen/wijzigen, tests te draaien, en backend/frontend te (her)starten — wat voor Philip de "echt programmeer-agent" ervaring afmaakt.
2. Of: ingeval je eerst een veilige check wilt of dit Fase 1 echt productie-stabiel is, een commit + integration round trip (cockpit start een job, observeert events, slaagt of faalt zichtbaar) en dan pas Fase 2.

## Bestanden in deze handoff verandering

Nieuw:
- `controller/agent_runtime/__init__.py`
- `controller/agent_runtime/models.py`
- `controller/agent_runtime/events.py`
- `controller/agent_runtime/store.py`
- `controller/agent_runtime/orchestrator.py`
- `controller/agent_runtime/adapters/__init__.py`
- `controller/agent_runtime/adapters/codex_cli.py`
- `controller/api/agent_runtime_routes.py`
- `sandbox_tests/test_agent_runtime_store.py`
- `sandbox_tests/test_agent_runtime_orchestrator.py`
- `sandbox_tests/test_agent_runtime_api.py`

Aangepast:
- `controller/slash_agent_router.py` (delegeert naar orchestrator, ruimt ~190 regels op)
- `controller/main.py` (mount `init_agent_runtime`)
- `ouroboros_cockpit/src/App.tsx` (Agent Jobs panel + slash-feedback + error-helper)
- `sandbox_tests/test_slash_agent_router.py` (test herschreven tegen nieuwe runtime)

Niets is gecommit. De buildplan + de oude handoff staan ook nog untracked. Stage selectief.
