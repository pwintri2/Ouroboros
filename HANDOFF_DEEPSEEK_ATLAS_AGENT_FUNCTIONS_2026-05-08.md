# Handoff: DeepSeek + Atlas agent functions

Datum: 2026-05-08
Workspace: `/home/pwintri2/WintripAI`

## Status

DeepSeek en Atlas zijn doorgezet van read-only zichtbaarheid naar echte slash/runtime agent routes.

Live geverifieerd:

- DeepSeek status: `available`
- DeepSeek launcher: `/home/pwintri2/deepseek/npm/deepseek-tui/bin/downloads/deepseek-tui`
- DeepSeek doctor: werkt via host bridge, maar meldt `api_key.source = missing`
- Atlas status: `available`
- Atlas launcher: `/home/pwintri2/atlas/packages/cli/dist/launcher.mjs`
- Atlas doctor: werkt via host bridge
- Backend: `http://127.0.0.1:8010`
- Cockpit devserver: `http://127.0.0.1:5173`
- Host bridge: `0.0.0.0:8766`

## Nieuwe cockpit slash functies

- `/deepseek status`
- `/deepseek capabilities`
- `/deepseek doctor`
- `/deepseek jobs`
- `/deepseek run <opdracht>`
- `/atlas status`
- `/atlas capabilities`
- `/atlas doctor`
- `/atlas jobs`
- `/atlas ask <opdracht>`

`run` en `ask` blijven gated met de approval phrase `Akkoord`.

## Belangrijkste implementatie

- Nieuwe CLI/runtime adapter:
  - `controller/agent_runtime/adapters/ecosystem_cli.py`
- Agent Runtime ondersteunt nu:
  - `deepseek`
  - `atlas`
- Nieuwe API routes:
  - `controller/api/ecosystem_agent_routes.py`
  - `/api/deepseek/status`
  - `/api/deepseek/capabilities`
  - `/api/deepseek/doctor`
  - `/api/deepseek/run`
  - `/api/atlas/status`
  - `/api/atlas/capabilities`
  - `/api/atlas/doctor`
  - `/api/atlas/run`
- Slash router uitgebreid:
  - `controller/slash_agent_router.py`
- Host bridge uitgebreid:
  - `/deepseek/status`
  - `/deepseek/capabilities`
  - `/deepseek/doctor`
  - `/atlas/status`
  - `/atlas/capabilities`
  - `/atlas/doctor`
  - `/agents/command` accepteert nu ook DeepSeek/Atlas
- Docker compose mount/bridge env uitgebreid:
  - `/home/pwintri2/deepseek:/deepseek:ro`
  - `/home/pwintri2/atlas:/atlas:ro`
  - `WINTRIP_RCLONE_BRIDGE_URL=http://host.docker.internal:8766`
  - `WINTRIP_RCLONE_BRIDGE_TOKEN_PATH=/workspace/.secrets/rclone_bridge_token`
- Cockpit UI toont en suggereert `/deepseek` en `/atlas`.
- `scripts/start_ouroboros_cockpit.sh` start de host bridge automatisch met `setsid -f`.

## Host-side setup gedaan

- Atlas dependencies geinstalleerd met Corepack/pnpm.
- Atlas gebouwd met `pnpm build`, waardoor `packages/cli/dist/launcher.mjs` bestaat.
- DeepSeek TUI binary gedownload via de lokale npm-wrapper.

Deze wijzigingen staan in de naastliggende repos zelf als build/install output en zijn niet onderdeel van deze WintripAI commit.

## Verificatie

Gedraaid in WintripAI:

```bash
python3 -m py_compile controller/agent_runtime/adapters/ecosystem_cli.py controller/slash_agent_router.py scripts/rclone_host_bridge.py
python3 -m unittest sandbox_tests.test_slash_agent_router sandbox_tests.test_agent_runtime_orchestrator sandbox_tests.test_agent_tools sandbox_tests.test_agentic_processor sandbox_tests.test_fase8_agent sandbox_tests.test_tauri_backend_routes sandbox_tests.test_tauri_cockpit_files
npm run build
```

Resultaat:

- Python compile: OK
- Tests: 92 tests OK, 24 skipped
- Cockpit build: OK, bestaande Vite chunk-size warning blijft

Live probes:

```bash
curl http://127.0.0.1:8010/api/deepseek/status
curl http://127.0.0.1:8010/api/atlas/status
curl http://127.0.0.1:8010/api/deepseek/doctor
curl http://127.0.0.1:8010/api/atlas/doctor
```

## Bekende aandachtspunten voor morgen

- DeepSeek doctor meldt geen API key/config. Echte model-antwoorden via `/deepseek run ...` hebben dus nog DeepSeek auth/config nodig.
- Atlas CLI is launchable en doctor werkt. Echte `/atlas ask ...` model-antwoorden hangen af van Atlas providerconfig.
- Geen secrets in memory/context/commit zetten. Auth/config alleen via de normale tool-specifieke veilige setup doen.
- De host bridge draait nu als hostproces. Als hij na reboot weg is, start `scripts/start_ouroboros_cockpit.sh` hem opnieuw.

## Niet meegenomen in deze commit

Bewust buiten scope gelaten:

- `wintrip_brain/...` databasewijzigingen
- `QuantumNode.txt`
- `camera-tools.sh`
- `controller/camera_manager.py`

Die lijken niet direct onderdeel van DeepSeek/Atlas agent functions.
