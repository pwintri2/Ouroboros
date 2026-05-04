# Handover Ouroboros World Agent - 2026-05-04

## Status

Ouroboros heeft nu een World Agent-laag voor natuurlijke-taalacties richting Grok en een apart wereld-geheugen in ChromaDB.

Belangrijkste gebruikerflow:

```text
open grok.com en vraag wat het verschil is tussen simulatie en bewustzijn
```

Met `Akkoord` in het approvalveld:

1. De cockpit detecteert de Grok-intent voor de normale modelrouter.
2. De standalone Tauri/React cockpit opent zichtbaar `https://grok.com/` via een native Tauri URL-opener.
3. De host-bridge probeert dezelfde vraag via Playwright aan Grok te stellen.
4. Het gescrubde resultaat of de eerlijke foutstatus wordt opgeslagen in `wintrip_world_understanding`.
5. Later kan de gebruiker semantisch zoeken met zinnen zoals:

```text
wat weet je nog over simulatie en bewustzijn?
```

## Nieuwe En Gewijzigde Bestanden

- `controller/world_agent.py`
  - `WorldAgent`, `WorldMemory`, ChromaDB world collection, Grok intentdetectie, hash-embedding fallback, actie-log.
  - Bridge-aware helpers: `ask_grok_via_world_agent`, `search_world_memory`, `world_agent_status`.
  - Detecteert Grok drukte/rate-limit en meldt dit eerlijk als geen echte succesvolle ask.

- `controller/api/world_agent_routes.py`
  - `GET /api/world-agent/status`
  - `GET /api/world-agent/actions/recent`
  - `POST /api/world-agent/grok/ask`
  - `POST /api/world-agent/memory/search`

- `controller/main.py`
  - Registreert World Agent routes.
  - Cockpit-chat routeert Grok- en world-memory intenten voor Ollama/multi-api.
  - Geeft bij Grok-intent een `frontend_action` terug zodat de cockpit de zichtbare tab opent.

- `scripts/rclone_host_bridge.py`
  - Host-bridge endpoints voor world actions:
    - `GET /world/status`
    - `GET /world/actions`
    - `POST /world/grok`
    - `POST /world/search`

- `start_ouroboros_sandbox_allow.sh`
  - Herstart oude host-bridge-processen als `/world/status` ontbreekt.
  - Gebruikt automatisch `.venv_world_agent/bin/python` als die bestaat.

- `ouroboros_cockpit/src-tauri/src/main.rs`
  - Nieuwe Tauri command `open_external_url`.
  - Alleen `http(s)` URLs worden extern geopend.
  - Linux fallback-volgorde: `xdg-open`, `gio open`, `flatpak-spawn --host xdg-open`.

- `ouroboros_cockpit/src/App.tsx`
  - Native Tauri opener wordt gebruikt voor `frontend_action.open_url`.
  - Fallback naar `window.open` blijft bestaan.
  - Nieuw `World Actions` panel met world-memory status, dependency status en recente world actions.

- `ouroboros_cockpit/src/styles.css`
  - Styling voor World Actions panel.

- Tests:
  - `sandbox_tests/test_world_agent.py`
  - Uitbreidingen in `sandbox_tests/test_tauri_backend_routes.py`
  - Uitbreidingen in `sandbox_tests/test_tauri_cockpit_files.py`

## Runtime Setup

Host-venv voor de bridge:

```bash
cd /home/pwintri2/WintripAI
python3 -m venv .venv_world_agent
.venv_world_agent/bin/python -m pip install chromadb playwright
.venv_world_agent/bin/python -m playwright install chromium
```

De venv is lokaal en wordt niet gecommit door `.venv_*/`.

Backend + bridge:

```bash
cd /home/pwintri2/WintripAI
./start_ouroboros_sandbox_allow.sh
```

Standalone desktop cockpit:

```bash
cd /home/pwintri2/WintripAI/ouroboros_cockpit
npm run tauri -- dev
```

Tijdens deze sessie is de standalone cockpit gestart als:

```text
target/debug/ouroboros-cockpit
```

Vite draait op:

```text
http://127.0.0.1:1420/
```

Logbestand:

```text
artifacts/ouroboros_cockpit_tauri.log
```

## Live Bevindingen

Werkend:

- `/api/world-agent/status` meldt:
  - `status=online`
  - backend ChromaDB beschikbaar
  - host bridge beschikbaar
  - host Playwright beschikbaar wanneer de bridge via `.venv_world_agent/bin/python` draait

- Veilige store/search smoke test:
  - `POST /api/world-agent/grok/ask` met `open_tab=false`, `submit=false`, `Akkoord`
  - sloeg world-memory op in `wintrip_world_understanding`
  - `POST /api/world-agent/memory/search` vond de entry terug

- Cockpit chat smoke:
  - Prompt: `open grok.com en vraag antwoord alleen met OK`
  - Resultaat bevatte `frontend_action.open_url=https://grok.com/`
  - `browser_action_performed=true`
  - `via_bridge=true`

Let op:

- Grok kan zelf rate-limit, drukte, login of CAPTCHA tonen.
- De automation omzeilt geen login/CAPTCHA en slaat geen sessiemateriaal op.
- De zichtbare tab wordt door de Tauri cockpit geopend; de Playwright ask draait los via de host-bridge.

## Verificatie

Gedraaid:

```bash
python -m py_compile controller/main.py controller/world_agent.py sandbox_tests/test_tauri_backend_routes.py
python -m unittest sandbox_tests.test_tauri_cockpit_files sandbox_tests.test_world_agent sandbox_tests.test_tauri_backend_routes
python -m unittest sandbox_tests.test_world_agent sandbox_tests.test_browser_research sandbox_tests.test_multi_api_router sandbox_tests.test_tool_bridge sandbox_tests.test_agent_tools sandbox_tests.test_tauri_backend_routes
npm --prefix ouroboros_cockpit run build
cd ouroboros_cockpit/src-tauri && cargo check
```

Resultaten:

- Python tests groen; enkele FastAPI/TestClient-afhankelijke tests zijn in deze shell geskipt.
- Frontend build groen met alleen de bekende Vite chunk-size warning.
- Rust `cargo check` groen.

## Niet Committen

Niet meenemen in git:

- `wintrip_brain/*` runtime ChromaDB state.
- `.venv_world_agent/`.
- `artifacts/world_agent_actions.jsonl`.
- Office lockfiles zoals `.~lock.*`.
- Lokale `.docx/.odt` werkdocumenten tenzij expliciet bedoeld als repo-documentatie.

## Volgende Stap

Als Grok in de zichtbare tab wel werkt maar Playwright niet, is de beste volgende technische stap een handmatige-login-vriendelijke mode:

- zichtbare Grok-tab openen;
- prompt klaarzetten of kopieerbaar tonen in de cockpit;
- gebruiker drukt zelf Enter in de ingelogde browser;
- gebruiker kan antwoord teruggeven via browser/text ingest.

Dat is robuuster dan proberen sessies/cookies van de echte browser te hergebruiken, wat bewust niet gebeurt.
