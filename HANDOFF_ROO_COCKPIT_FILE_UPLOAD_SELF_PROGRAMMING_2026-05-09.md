# Handoff: Roo Cockpit + Bestand Bijvoegen + Eerste Zelf-Programmeer Stap

Datum: 2026-05-09
Workspace: `/home/pwintri2/WintripAI`
Branch: `feature/esoteric-ouroboros-architecture`

## Samenvatting

De Cockpit heeft nu een werkende eerste stap richting zelf programmeren:

- Bestanden kunnen vanuit de web preview aan de chat worden toegevoegd.
- De backend slaat uploads op onder `data/uploads` en geeft veilige file paths terug aan de chatflow.
- Chat requests kunnen deze file paths meesturen naar de agentische laag.
- Roo is niet meer alleen een losse IDE-handoff: de Cockpit kan Roo jobs starten met het model/provider-profiel dat in de Cockpit geselecteerd is.
- Runtime Doctor en het preview-startscript zijn aangescherpt zodat backend, preview, host bridge, Chroma, Roo runtime en toolroutes als een samenhangende runtime gecontroleerd worden.

Dit is nog geen volledige self-build loop, maar het is wel de eerste tastbare bouwsteen: de agent kan nu inputmateriaal ontvangen en doorgeven aan de runtime die vervolgens echte jobs kan starten.

## Belangrijkste wijzigingen

### Cockpit file upload

- `controller/main.py`
  - Nieuw endpoint: `POST /api/upload`
  - Accepteert meerdere `UploadFile` bestanden.
  - Slaat op onder `data/uploads`.
  - Geeft per upload `filename`, `path`, `size` en `status` terug.
- `controller/requirements.txt`
  - `python-multipart` toegevoegd voor FastAPI file uploads.
- `ouroboros_cockpit/src/App.tsx`
  - Paperclip/upload UI toegevoegd bij de chat input.
  - Uploads worden direct naar `/api/upload` gestuurd.
  - Succesvolle uploads worden als file paths meegestuurd in `POST /api/cockpit/chat`.
- `ouroboros_cockpit/src/styles.css`
  - Styling toegevoegd voor uploadstrip, knop, file chips en remove buttons.

### Roo via Cockpit-selected model

- `controller/roo_cli_runtime.py`
  - Nieuwe runtime-laag voor Roo CLI.
  - Mapt Cockpit provider/model naar Roo provider/config.
  - Gebruikt transient API key env vars, zonder secrets duurzaam op te slaan.
  - Classificeert bekende failures, zoals modellen zonder tool support en encrypted-content mismatch.
- `controller/agent_runtime/adapters/roo_cli.py`
  - Nieuwe Roo adapter voor agent-runtime jobs.
  - Gebruikt host bridge `/roo/status` en `/roo/run`.
  - Faalt gesloten als de bridge niet beschikbaar is.
- `controller/slash_agent_router.py`
  - `/roo status`, `/roo jobs`, `/roo capabilities`.
  - `/roo read/list/search` blijven directe veilige adapter-acties.
  - `/roo <task>` start nu een echte Roo job via geselecteerde Cockpit provider/model.
- `controller/main.py`
  - Provider `roo` toegevoegd als Cockpit keuze.
  - Roo chatrequests worden naar de Roo runtime/jobroute geleid.
  - Preflight checkt of cloudmodellen een beschikbare API key hebben.
- `scripts/rclone_host_bridge.py`
  - Host bridge endpoints voor Roo toegevoegd: `/roo/status` en `/roo/run`.

### Runtime harness

- `controller/runtime_doctor.py`
  - Runtime Doctor versie bijgewerkt naar Roo runtime harness.
  - Checkt onder andere backend, preview, host bridge, Chroma, tool registry, agentic router, Roo runtime en preview source.
- `scripts/doctor_ouroboros_runtime.py`
  - CLI doctor volgt dezelfde runtime-status.
- `scripts/start_ouroboros_preview.sh`
  - Officiele preview-start aangescherpt.
  - Zorgt dat de bekende Node/NPM install uit `~/.nvm/versions/node/v22.22.2/bin` gevonden wordt als de shell geen nvm laadt.
- `ouroboros_cockpit/src/App.tsx`
  - Runtime Doctor paneel toont de nieuwe Roo/runtime signalen.

### Context en paden

- `AGENTS.md`
- `OUROBOROS_IDE_CONTEXT.md`
- `controller/ouroboros_self_context.py`
- `controller/roo_manifest.py`
- `controller/roo_tools.py`

Alle Roo verwijzingen zijn gecorrigeerd naar:

`/home/pwintri2/Roo-code`

## Huidige runtime-observaties

- Web preview werkte na start via `scripts/start_ouroboros_preview.sh`.
- Runtime Doctor kwam op `ready` nadat de preview, backend, bridge en Roo checks overeenkwamen.
- File upload werkt in de Cockpit UI.
- Er kan nog een Roo job als `running` zichtbaar blijven terwijl er geen host Roo proces meer actief is. Dat moet in de volgende stap een job-liveness watchdog krijgen.
- Lokale Ollama-modellen moeten tool calls ondersteunen. `codellama:13b` faalde bijvoorbeeld terecht als `model_lacks_tool_support`.
- Roo + OpenAI `gpt-4.1` gaf nog een Responses API melding over encrypted content. De runtime classificeert dat nu, maar een stabiel Roo cloud-profiel moet nog gekozen of geblokkeerd worden in de UI.

## Tests en verificatie

Aanbevolen checks voor de volgende sessie:

```bash
python3 -m py_compile \
  controller/main.py \
  controller/runtime_doctor.py \
  controller/slash_agent_router.py \
  controller/agent_runtime/orchestrator.py \
  controller/agent_runtime/adapters/roo_cli.py \
  controller/roo_cli_runtime.py \
  scripts/rclone_host_bridge.py

python3 -m unittest \
  sandbox_tests.test_tauri_backend_routes \
  sandbox_tests.test_slash_agent_router \
  sandbox_tests.test_roo_cli_runtime \
  sandbox_tests.test_roo_cli_adapter \
  -v

bash -n scripts/start_ouroboros_preview.sh
```

Laatste lokale verificatie in deze shell:

- `py_compile` op gewijzigde backend/runtime scripts: groen.
- `bash -n scripts/start_ouroboros_preview.sh`: groen.
- Gerichte unittest-run: `56 tests OK`, waarvan `27 skipped` omdat `fastapi` in deze shell ontbreekt.

## Niet meenemen in deze commit

Bewust buiten de commit houden tenzij later expliciet nodig:

- `wintrip_brain/*` runtime/Chroma data.
- Lokale upload payloads in `data/uploads`.
- Losse experimentele artefacts zoals `QuantumNode.txt`, `camera-tools.sh`, `controller/camera_manager.py`.
- De losse untracked `tests/` map totdat duidelijk is of die bij deze feature hoort.

## Volgende bouwstap

1. Uploads inhoudelijk gebruiken: file preview/read/indexing in de chatcontext, met size/type limits.
2. Job-liveness watchdog: running Roo jobs fail-closed maken als het proces/output verdwenen is.
3. Cockpit UI: bekende ongeschikte modelprofielen blokkeren of markeren.
4. Self-programming loop: opdracht + bestanden -> Roo/Codex job -> tests -> resultaat terug in Cockpit -> Chroma audit record.
5. E2E smoke: upload bestand, vraag wijziging, laat Roo/Codex patch maken, draai tests, toon trace.
