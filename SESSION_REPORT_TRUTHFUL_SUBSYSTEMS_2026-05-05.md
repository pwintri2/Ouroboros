# Session Report — Truthful Subsystems & Codex Integration — 2026-05-05

## Doel van de sessie

Drie samenhangende werkstromen op `feature/esoteric-ouroboros-architecture`:

1. **Codex repo-integratie** — Codex zichtbaar maken als levend subsysteem van Ouroboros, met truthful capability inventory, runtime adapter, slash-subcommands, API en cockpit panel.
2. **Codex job timeouts** — Drie failed Codex jobs (exit -15) waren het gevolg van een te krappe 240s default timeout midden in een echte refactor.
3. **Truthful subsystem badges** — Ω Nexus, Living, World, AgentS en OpenHands moesten van status-theater naar echte, evidence-based health checks met operationele endpoints.
4. **Operationaliteit in de standalone cockpit** — Codex Run-knop werkend krijgen, AgentS/OpenHands van `missing` af.

## Wat is er gebouwd

### Codex integratielaag
- [controller/codex_status.py](controller/codex_status.py) — environment detection (binary search via PATH, repo, IDE-extensions), `codex --version` probe, auth/sessions inventory in `~/.codex/`, capability discovery van 25 subsystemen (cli/tui/app-server/mcp/skills/sandboxing/etc.), aggregated status met eerlijke statuswoorden (`missing`, `discoverable`, `binary_present_no_auth`, `configured`, `online`).
- [controller/codex_registry.py](controller/codex_registry.py) — gelaagde `get_codex_capability_inventory()` die JSON-callable Python helpers én Rust subsystemen samen rapporteert; bestaande API blijft compatibel.
- [controller/agent_runtime/adapters/codex_cli.py](controller/agent_runtime/adapters/codex_cli.py) — gebruikt het ontdekte binary path, logt binary/version-events, classificeert fouten (`binary_missing`, `auth_missing`, `sandbox_violation`, `timeout`, `spawn_failed`, `exec_error`, `ok`).
- [controller/api/codex_routes.py](controller/api/codex_routes.py) — `/api/codex/{status,capabilities,discovery,version,run,jobs,jobs/{id},jobs/{id}/events}`. POST `/run` is approval-gated en geeft 503 als binary ontbreekt.
- [controller/slash_agent_router.py](controller/slash_agent_router.py) — `/codex` heeft nu subcommando's: `status`, `capabilities`, `jobs`, `discovery`, `version`, `app-status`, `mcp-status`, `run <opdracht>`. Vrije-tekst run blijft backward compatible.

### Truthful subsystems
- [controller/status_contracts.py](controller/status_contracts.py) — gemeenschappelijke status ladder `missing → detected → configured → available → running → online → degraded → blocked → error`, plus `evidence_status()`, `run_probe()`, `degrade_if_stale()`, `is_fresh()`.
- [controller/nexus_status.py](controller/nexus_status.py) — `NexusState` singleton met event ingestion ring, coherence/active/error counts uit echte job store, explainable summary (`reason` veld). Orchestrator hooks bij `job_created` en `job_finished` voeden de Nexus.
- [controller/agent_runtime/adapters/agents_cli.py](controller/agent_runtime/adapters/agents_cli.py) — AgentS adapter met probe-ladder (AST parse → `import gui_agents` → full CLI `--help`); status promoveert alleen op echte evidence.
- [controller/agent_runtime/adapters/openhands_adapter.py](controller/agent_runtime/adapters/openhands_adapter.py) — OpenHands adapter met AST parse + `import openhands` + HTTP server probe; `online` alleen als beide groen.
- [controller/api/agents_routes.py](controller/api/agents_routes.py) — `/api/agents/{status,capabilities,probe,run}`, approval-gated.
- [controller/api/openhands_routes.py](controller/api/openhands_routes.py) — `/api/openhands/{status,capabilities,probes,run}`, approval-gated.
- [controller/api/agent_runtime_routes.py](controller/api/agent_runtime_routes.py) — nexus status verrijkt met operationele summary; nieuwe `/nexus/summary`, `/nexus/events`, `/nexus/recompute`.
- [controller/api/ouroboros_esoteric_routes.py](controller/api/ouroboros_esoteric_routes.py) — `/living/events` en `/living/output` toegevoegd.
- [controller/api/world_agent_routes.py](controller/api/world_agent_routes.py) — `/dependencies` en `/health` toegevoegd met truthful ladder semantics.

### Living Ouroboros — kapot herstellen + upgrade
De `ouroboros_consciousness_loop.py` referenteerde 5 helpers (`build_runtime_snapshot`, `_runtime_metadata`, `_runtime_signal_summary`, `_attention_markers`, `_next_runtime_question`) die nooit geschreven waren — een eerdere Codex job had ze in een diff staan maar timed out voordat de patch klaar was. Living crashte daardoor met `NameError`. Helpers nu écht geschreven, gebruiken **echte** runtime signalen: persistent memory counts, agent-runtime job status, QCN coherence, self-context, git porcelain.

Plus:
- `mode` (`speaking`/`running`/`idle`/`degraded`/`error`) alleen `speaking` als `_last_output_at ≤ 60s`
- `tick_count`, `tick_count_24h`, `last_action`, `last_tick_at`, `last_output_at`
- `events()` en `output()` API methods
- Nexus event ingestion bij elke tick

### Cockpit
- [ouroboros_cockpit/src/App.tsx](ouroboros_cockpit/src/App.tsx) — Codex Subsystem panel (binary/version/auth/capability matrix/run-form), Codex/AgentS/OpenHands state en loaders, status pills lezen `operational.status`/`mode`/`runtime_reachable`/`launch_test` ipv "exists", `AgentCapabilitiesPanel` gebruikt echte AgentS/OpenHands status.

### Codex job timeouts
Default verhoogd van 240s naar 1800s op alle submit-paden — `controller/codex_agent.py`, `slash_agent_router._run_codex_exec`, `/api/codex/run` (max 7200s), cockpit Run-knop. Override via `WINTRIP_CODEX_TIMEOUT_SECONDS`.

### Tests
Negen nieuwe test modules (38 nieuwe tests):
- [sandbox_tests/test_codex_status.py](sandbox_tests/test_codex_status.py)
- [sandbox_tests/test_codex_capability_discovery.py](sandbox_tests/test_codex_capability_discovery.py)
- [sandbox_tests/test_codex_routes.py](sandbox_tests/test_codex_routes.py)
- [sandbox_tests/test_status_contracts.py](sandbox_tests/test_status_contracts.py)
- [sandbox_tests/test_nexus_status_truthful.py](sandbox_tests/test_nexus_status_truthful.py)
- [sandbox_tests/test_living_runtime.py](sandbox_tests/test_living_runtime.py)
- [sandbox_tests/test_agents_integration.py](sandbox_tests/test_agents_integration.py)
- [sandbox_tests/test_openhands_integration.py](sandbox_tests/test_openhands_integration.py)
- [sandbox_tests/test_world_agent_health.py](sandbox_tests/test_world_agent_health.py)

Plus: [sandbox_tests/test_slash_agent_router.py](sandbox_tests/test_slash_agent_router.py) bijgewerkt voor de nieuwe `/codex status`/`/codex capabilities` subcommands.

## Container operationaliteit

In de Docker container `wintrip-standalone-ui`:

- **Native Codex binary** gekopieerd naar `/codex_native/bin/linux-x86_64/codex` (200MB)
- **AgentS source** gekopieerd naar `/agents` (1.4GB, excl. heavy artifacts), `pyautogui`+`pillow` deps geïnstalleerd
- **OpenHands source** gekopieerd naar `/openhands` (30MB, excl. .git/node_modules/cache)
- **Codex auth** (`auth.json`+`config.toml`) gekopieerd naar `/root/.codex/` met chmod 600
- **Uvicorn** herstart met `WINTRIP_AGENTS_PATH=/agents`, `WINTRIP_OPENHANDS_PATH=/openhands`, `WINTRIP_ROO_PATH=/roo`, `WINTRIP_RUFLO_PATH=/ruflo`, `WINTRIP_CODEX_BINARY=/codex_native/bin/linux-x86_64/codex`, `WINTRIP_OPENHANDS_SERVER_URL=http://host.docker.internal:3000`, `WINTRIP_CODEX_TIMEOUT_SECONDS=1800`

## Live verificatie

Endpoints gemeten op `http://localhost:8010` na container restart:

| Endpoint | Status |
|---|---|
| `GET /health` | 200 |
| `GET /api/codex/status` | `online` (auth: authenticated/api_key, native binary v0.126.0-alpha.8) |
| `GET /api/codex/version` | version=0.126.0-alpha.8 |
| `POST /api/codex/run` (Akkoord) | running → completed exit 0, echte LLM response |
| `GET /api/agents/status` | `available` (variant s2_5, runtime_reachable=true) |
| `GET /api/openhands/status` | `available` (runtime_launch_test=available, server_reachable=false) |
| `GET /api/agent-runtime/nexus/summary` | `online` (event ingestion healthy, 1 active job) |
| `GET /api/world-agent/health` | `online` (memory available, browser automation ok) |
| `GET /api/ouroboros/esoteric/living/status` | `running`/`speaking` (tick_count=1, signal summary toont 232 herinneringen) |

Tests: 94+ doelgerichte tests groen lokaal (host fastapi-tests skipped wegens PEP 668; runnen in container).

Cockpit `npm run build`: clean.

## Resterende gaps / honesty

- **OpenHands server**: niet draaiend op `host.docker.internal:3000`. Status blijft `available` (package imports), niet `online`. Voor `online`: start OpenHands lokaal (`make run` in `/home/pwintri2/OpenHands`).
- **Codex sandbox in container**: `bwrap: No permissions to create a new namespace` — Docker-in-Docker user-namespace beperking. Codex praat met LLM, maar shell-acties binnen Codex' eigen sandbox worden begrensd.
- **AgentS available betekent**: source aanwezig, package importeert. Echt GUI-acties uitvoeren vereist een display server (X11) — niet zinvol in headless container.
- **Container persistence**: alle env vars en gekopieerde paden (`/agents`, `/openhands`, `/codex_native`, `/root/.codex`) leven in de huidige container layer. Bij `docker rm` zijn ze weg; commit naar nieuwe image of rebuild met `-v` mounts is duurzamer.
- **`main.py` inode quirk**: editor atomic-saves geven nieuwe inode → bind-mount blijft op oud inode hangen. Tijdens deze sessie eenmalig opgelost door in-place `cat > /workspace/controller/main.py` binnen de container. Zelfde patroon kan terugkeren als `main.py` opnieuw extern wordt gewijzigd zonder container restart.
