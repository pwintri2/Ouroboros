# Handoff Fase 9 — Truthful Subsystems & Codex Integration — 2026-05-05

## Status

Branch: `feature/esoteric-ouroboros-architecture`

Laatste afgeronde werkstroom:

- Codex is nu een eigen subsysteem in Ouroboros met capability inventory, runtime adapter, slash-subcommands, API routes en cockpit panel.
- Codex job default timeout 240s → 1800s op alle submit-paden (oud → SIGTERM mid-refactor).
- Status contracts module geeft één gedeelde ladder (`missing → detected → configured → available → running → online → degraded → blocked → error`).
- Ω Nexus heeft echt event ingestion + summary + recompute endpoints; orchestrator voedt hem bij `job_created` en `job_finished`.
- Living Ouroboros: 5 ontbrekende helpers (`build_runtime_snapshot`, `_runtime_metadata`, `_runtime_signal_summary`, `_attention_markers`, `_next_runtime_question`) toegevoegd; `mode` (`speaking`/`running`/`idle`/`degraded`/`error`) is nu eerlijk afgeleid van `_last_output_at` en `_last_tick_at`; `events()` + `output()` methods.
- World heeft `/dependencies` en `/health` met expliciete classificatie.
- AgentS (`controller/agent_runtime/adapters/agents_cli.py`) en OpenHands (`controller/agent_runtime/adapters/openhands_adapter.py`) zijn echte adapters met probe-ladders (AST → import → full CLI/server) en API routes.
- Cockpit pills lezen operational data ipv enkel disk-presence; nieuw Codex panel; AgentS/OpenHands gebruiken echte adapter status.

## Belangrijkste bestanden

### Nieuw
- `controller/status_contracts.py` — gemeenschappelijke status ladder + helpers
- `controller/codex_status.py` — Codex environment + capability discovery
- `controller/nexus_status.py` — operational Nexus state service
- `controller/agent_runtime/adapters/agents_cli.py` — AgentS adapter
- `controller/agent_runtime/adapters/openhands_adapter.py` — OpenHands adapter
- `controller/api/codex_routes.py` — `/api/codex/*`
- `controller/api/agents_routes.py` — `/api/agents/*`
- `controller/api/openhands_routes.py` — `/api/openhands/*`
- 9 nieuwe sandbox_tests modules

### Aangepast
- `controller/codex_registry.py` — gelaagde `get_codex_capability_inventory()`
- `controller/agent_runtime/adapters/codex_cli.py` — binary path detection, version capture, error categories
- `controller/agent_runtime/orchestrator.py` — Nexus event ingestion bij job_created/job_finished
- `controller/api/agent_runtime_routes.py` — `/nexus/{summary,events,recompute}`
- `controller/api/ouroboros_esoteric_routes.py` — `/living/{events,output}`
- `controller/api/world_agent_routes.py` — `/{dependencies,health}`
- `controller/codex_agent.py` — timeout override met env var
- `controller/main.py` — mount codex/agents/openhands routers
- `controller/slash_agent_router.py` — `/codex {status,capabilities,jobs,discovery,version,app-status,mcp-status,run}` subcommands; default timeout 1800s
- `ouroboros_cockpit/src/App.tsx` — Codex panel, truthful pills, AgentS/OpenHands loaders
- `ouroboros_esoteric/ouroboros_consciousness_loop.py` — 5 helpers + `mode` + `events()`/`output()` + Nexus ingest per tick

## Runtime checks

Lokaal groen:

```bash
cd /home/pwintri2/WintripAI && python3 -m unittest \
    sandbox_tests.test_codex_status \
    sandbox_tests.test_codex_capability_discovery \
    sandbox_tests.test_codex_routes \
    sandbox_tests.test_codex_registry \
    sandbox_tests.test_codex_agent \
    sandbox_tests.test_slash_agent_router \
    sandbox_tests.test_agent_runtime_orchestrator \
    sandbox_tests.test_status_contracts \
    sandbox_tests.test_nexus_status_truthful \
    sandbox_tests.test_living_runtime \
    sandbox_tests.test_agents_integration \
    sandbox_tests.test_openhands_integration \
    sandbox_tests.test_world_agent_health \
    sandbox_tests.test_living_ouroboros
# 94+ tests green; 17 skipped (host PEP 668 / fastapi-only)

cd /home/pwintri2/WintripAI/ouroboros_cockpit && npm run build
# clean
```

Live rooktests in container:

```bash
curl -sS http://localhost:8010/api/codex/status               # status: online
curl -sS http://localhost:8010/api/agents/status              # status: available
curl -sS http://localhost:8010/api/openhands/status           # status: available
curl -sS http://localhost:8010/api/agent-runtime/nexus/summary  # status: online
curl -sS http://localhost:8010/api/world-agent/health         # status: online
curl -sS http://localhost:8010/api/ouroboros/esoteric/living/status  # mode: speaking/running

# Codex run e2e met Akkoord:
curl -sS -X POST http://localhost:8010/api/codex/run \
  -H 'Content-Type: application/json' \
  -d '{"task":"List directories in /workspace","approval":"Akkoord","timeout_seconds":300}'
# Volgende job_id pollen met:
curl -sS http://localhost:8010/api/codex/jobs/<job_id>
```

## Container setup (idempotent recept)

Container draait op image `python:3.10-slim` met 104 packages geïnstalleerd. Bind mounts: `/workspace` ← `/home/pwintri2/WintripAI`, `/codex` ← `/home/pwintri2/Codex`, `/codeneuron` ← `/home/pwintri2/CodeNeuron`. Voor truthful AgentS/OpenHands en werkende Codex Run zijn extra paden gekopieerd:

```bash
# Codex native binary (vermijdt node-shim)
docker exec wintrip-standalone-ui mkdir -p /codex_native/bin/linux-x86_64
docker cp /home/pwintri2/.windsurf/extensions/openai.chatgpt-26.422.71525-linux-x64/bin/linux-x86_64/codex \
    wintrip-standalone-ui:/codex_native/bin/linux-x86_64/codex
docker exec wintrip-standalone-ui chmod +x /codex_native/bin/linux-x86_64/codex

# AgentS source (1.4GB, excl heavy artifacts)
docker exec wintrip-standalone-ui mkdir -p /agents
cd /home/pwintri2/AgentS && tar --exclude='.git' --exclude='__pycache__' \
    --exclude='*.egg-info' --exclude='images' --exclude='evaluation_sets' \
    --exclude='node_modules' -cf - . | docker exec -i wintrip-standalone-ui tar -xf - -C /agents
docker exec wintrip-standalone-ui pip install --quiet pyautogui pillow

# OpenHands source (30MB, excl heavy artifacts)
docker exec wintrip-standalone-ui mkdir -p /openhands
cd /home/pwintri2/OpenHands && tar --exclude='.git' --exclude='__pycache__' \
    --exclude='node_modules' --exclude='cache' --exclude='logs' \
    --exclude='*.egg-info' --exclude='dist' --exclude='build' \
    --exclude='target' --exclude='.venv' --exclude='venv' \
    -cf - . | docker exec -i wintrip-standalone-ui tar -xf - -C /openhands

# Codex auth (chmod 600 voor secrets)
docker exec wintrip-standalone-ui mkdir -p /root/.codex
docker cp /home/pwintri2/.codex/auth.json wintrip-standalone-ui:/root/.codex/auth.json
docker cp /home/pwintri2/.codex/config.toml wintrip-standalone-ui:/root/.codex/config.toml
docker exec wintrip-standalone-ui chmod 600 /root/.codex/auth.json /root/.codex/config.toml

# Uvicorn restart met env vars
docker exec wintrip-standalone-ui sh -c "for f in /proc/[0-9]*/cmdline; do c=\$(tr '\0' ' ' < \"\$f\" 2>/dev/null); case \"\$c\" in *uvicorn*) p=\$(echo \"\$f\" | sed 's|/proc/||;s|/cmdline||'); kill -TERM \$p; esac; done"
sleep 3
docker exec -d -w /workspace wintrip-standalone-ui sh -c "\
    WINTRIP_AGENTS_PATH=/agents \
    WINTRIP_OPENHANDS_PATH=/openhands \
    WINTRIP_ROO_PATH=/roo \
    WINTRIP_RUFLO_PATH=/ruflo \
    WINTRIP_CODEX_BINARY=/codex_native/bin/linux-x86_64/codex \
    WINTRIP_OPENHANDS_SERVER_URL=http://host.docker.internal:3000 \
    WINTRIP_CODEX_TIMEOUT_SECONDS=1800 \
    nohup uvicorn controller.main:app --host 0.0.0.0 --port 8010 > /tmp/uvicorn.log 2>&1 &"
```

## Standalone cockpit starten

```bash
cd /home/pwintri2/WintripAI/ouroboros_cockpit
TAURI_BACKEND_URL=http://localhost:8010 VITE_BACKEND_URL=http://localhost:8010 \
    setsid nohup npm run dev > /tmp/cockpit-vite.log 2>&1 < /dev/null &
disown
DISPLAY=:1 WAYLAND_DISPLAY=wayland-1 \
    TAURI_BACKEND_URL=http://localhost:8010 VITE_BACKEND_URL=http://localhost:8010 \
    setsid nohup ./src-tauri/target/debug/ouroboros-cockpit > /tmp/ouroboros-cockpit.log 2>&1 < /dev/null &
disown
```

Stop met `pkill -f ouroboros-cockpit && pkill -f "vite --host"`.

## Niet meenemen als codewijziging

Deze runtime/data wijzigingen blijven bewust buiten de commit:
- `wintrip_brain/**` (Chroma DB state)
- `*.docx`, `*.odt`, `.~lock.*`
- Lokale dossiers (`Ouroboros_Grow.docx`, `Quantum Cognitive Corruption Nexus.docx`, `ZetaPlan.docx`)
- `Codex-repo_integration.md` en `Make_Reals_Build.md` zijn de prompt-input documenten — ook niet commit-waardig (handover documenten worden wel toegevoegd).

## Volgende focus

1. **OpenHands server starten** (`make run` in `/home/pwintri2/OpenHands`) zodat OpenHands van `available` naar `online` gaat in de cockpit.
2. **Container persistence**: huidige session-state (gekopieerde paden, geïnstalleerde deps, gevulde env vars) leeft in de huidige container layer. `docker commit wintrip-standalone-ui:saved` of een Dockerfile met deze setup geeft duurzame reproducibility.
3. **Codex sandbox bwrap**: voor sub-shell acties binnen Codex op te lossen, ofwel `--privileged` op de container of een sandbox-mode aanpassen via `--sandbox=danger-full-access` (alleen voor isolated dev).
4. **AgentS GUI runtime**: als Philip een echte AgentS run wil, moet er een X11 setup naar de container worden doorgezet (Xvfb, of host display via `-e DISPLAY` + `/tmp/.X11-unix` mount).
5. **Cockpit Codex panel**: kan uitgebreid worden met een "Open log" knop per recente job en een live event-stream (events endpoint bestaat al).
6. **Status contracts adoptie**: het Codex status object zou ook `evidence_status()` kunnen gebruiken voor consistentie met de andere subsystemen.
