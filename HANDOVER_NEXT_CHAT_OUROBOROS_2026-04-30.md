# Handover Voor Volgende Chat - Ouroboros Fase 4.5 / Fase 1

Datum: 2026-04-30
Repo: `/home/pwintri2/WintripAI`
GitHub: `pwintri2/wintripai`
Branch: `codex/ouroboros-phase1-agent-loop-20260430`
Laatste commit: `7ffeca1 Add Ouroboros phase 1 agent loop`

## Update Later Op 2026-04-30

Nieuwe werkbranch:

```text
codex/ouroboros-cockpit-roo-trainer-20260430
```

Belangrijkste nieuwe status:

- Primaire UI is nu `ouroboros_cockpit/`, een Tauri v2 + React cockpit.
- De oude `WintripAI_IDE.html` is legacy en mag niet opnieuw de hoofdinterface worden.
- Backend cockpit endpoints bestaan:
  - `GET /api/cockpit/config`
  - `POST /api/cockpit/chat`
  - `GET /api/cockpit/api-keys`
  - `POST /api/cockpit/api-keys`
  - `GET /api/ouroboros/loop/status`
  - `POST /api/ouroboros/loop/start|pause|abort`
- API keys worden lokaal opgeslagen via `controller/api_key_store.py`; raw secrets worden niet teruggegeven.
- Build/handoff voor Roo + LitGPT + Unsloth staat in:

```text
OUROBOROS_COCKPIT_ROO_TRAINER_HANDOFF_2026-04-30.md
```

Start cockpit:

```bash
cd /home/pwintri2/WintripAI/ouroboros_cockpit
npm run tauri -- dev
```

## Lees Eerst

De canonieke sessiestatus staat in:

```text
/home/pwintri2/WintripAI/OUROBOROS_FASE4_5_SESSION_REPORT_2026-04-28.md
```

Lees dat bestand als eerste. Het beschrijft wat nu echt gebouwd is, wat approval-gated is, welke endpoints bestaan, welke tests groen zijn, en welke grenzen nog eerlijk openstaan.

Aanvullend verslag:

```text
/home/pwintri2/WintripAI/WINTRIP_OUROBOROS_WEBBEEST_SESSION_REPORT_2026-04-29.md
```

## Huidige Stand

Ouroboros is omgebouwd van een decoratieve chat/cockpit-richting naar een backend-first agent-machine.

Belangrijkste onderdelen:

- `Modelfile.ouroboros` voor lokale Ollama modelidentiteit `ouroboros`.
- `controller/ouroboros_model.py` voor Modelfile/create-flow.
- `controller/agent_tools.py` als echte tool-registry.
- `controller/browser_research.py` voor Playwright browser research perimeter.
- `controller/api/browser_routes.py` voor browser endpoints.
- `controller/api/training_routes.py` voor Preview/Akkoord/11D ChromaDB opslag.
- `controller/safe_shell.py` voor approval-gated shell in `/workspace`.
- `controller/self_training.py` voor de eerste self-training loop.
- `controller/stream/geometry_11d.py` met Philip's exacte 11D bolberekening.
- `controller/virtual_team.py` met mentorrollen die echte tools gebruiken.
- `WintripAI_IDE.html` met knoppen die echte backend calls doen.

## Wat Werkt Nu

Backend endpoints:

- `GET /health`
- `GET /models`
- `GET /api/ouroboros/status`
- `POST /api/ouroboros/model/create-flow`
- `POST /browser/scrub`
- `POST /browser/research`
- `POST /browser/read-visible-text`
- `POST /browser/chatgpt/ask`
- `POST /api/ouroboros/research/browser`
- `POST /api/ouroboros/chatgpt/browser`
- `POST /api/ouroboros/training/ingest`
- `POST /api/ouroboros/hippocampus/inspect`
- `POST /api/ouroboros/self-training/step`
- `POST /agent/tool`
- `POST /sandbox/shell`
- `POST /team/discuss`

Runtime URL:

```text
http://localhost:3000/WintripAI_IDE.html?backend=http://localhost:8010
```

Docker container:

```text
wintrip-standalone-ui
```

Poorten:

```text
UI: 3000
Backend: 8010
```

## Belangrijk Gedrag

Browser research:

- Gaat via Playwright.
- Leest maximaal een pagina per actie.
- Geen scraping-achtige bulk-crawl.
- Geen CAPTCHA/login bypass.
- Browserdata is altijd `UNTRUSTED`.
- DiffView is verplicht voordat opslag gebeurt.

Training ingest:

- Preview zonder opslag.
- Opslag alleen met exact `Akkoord`.
- Schrijft naar ChromaDB trainingcollectie met 11D metadata.
- Frequentie 418-432 Hz wordt zichtbaar meegenomen.

Safe shell:

- Alleen via `controller/safe_shell.py`.
- Vereist exact `Akkoord`.
- Draait in `/workspace`.
- Alleen whitelist-commando's.
- Geeft stdout/stderr/exit_code terug.

Ollama:

- `ouroboros` is voorbereid als modelidentiteit.
- Status `online` betekent alleen: Ollama rapporteert model `ouroboros` echt.
- Er is nog geen echte fine-tune/weight update gedaan.

## 11D Geheugen

De exacte 11D bolfunctie staat in:

```text
controller/stream/geometry_11d.py
```

Kernformule:

```python
def bereken_11d_bol(radius):
    teller_constante = 64 * math.pi**5
    noemer_volume = 10395
    noemer_oppervlakte = 945
    volume = (teller_constante / noemer_volume) * (radius**11)
    oppervlakte = (teller_constante / noemer_oppervlakte) * (radius**10)
    return volume, oppervlakte
```

Training records slaan onder andere op:

- `dimension_count`
- `d1_physical_body` t/m `d11_field`
- `geometry_11d_radius`
- `geometry_11d_volume`
- `geometry_11d_oppervlakte`
- `dream_hz`
- `frequency_band`
- `approval_status`
- `taint`

## Laatste Validatie

Binnen Docker uitgevoerd:

```bash
python -m unittest \
  sandbox_tests.test_geometry_11d \
  sandbox_tests.test_ouroboros_model \
  sandbox_tests.test_browser_research \
  sandbox_tests.test_agent_tools \
  sandbox_tests.test_self_training_loop \
  sandbox_tests.test_virtual_team_tools \
  sandbox_tests.test_mentor_roles \
  sandbox_tests.test_training_routes \
  sandbox_tests.test_api_ouroboros_phase1
```

Resultaat:

```text
Ran 45 tests in 1.264s
OK
```

Browser rooktest:

- `POST /api/ouroboros/research/browser`
- URL: `https://example.com`
- approval: `Akkoord`
- resultaat: `browser_observed`
- browser action uitgevoerd: `true`
- DiffView aanwezig: `true`

Training rooktest:

- `target_hz=432.0`
- `approval=Akkoord`
- resultaat: opgeslagen in 11D ChromaDB.

## GitHub

Branch gepusht:

```text
codex/ouroboros-phase1-agent-loop-20260430
```

Commit:

```text
7ffeca1 Add Ouroboros phase 1 agent loop
```

PR-link:

```text
https://github.com/pwintri2/wintripai/pull/new/codex/ouroboros-phase1-agent-loop-20260430
```

Let op: `gh auth` was verlopen. De branch is wel via `git push` naar GitHub gepusht.

## Lokale Scratch Die Niet In Commit Zat

Deze bestanden/mappen zijn bewust lokaal/untracked gelaten:

```text
.vscode/
RESONANT_OUROBOROS_FASE2_AWAKE_KEEPER_Codex_Prompt.md
gordon_progress.log
ouroboros_proto1/
```

Niet zomaar toevoegen zonder Philip te vragen.

## Startpunt Voor Volgende Chat

Geef de volgende Codex-chat deze opdracht:

```text
Je bent Codex in VS Code, werkend in /home/pwintri2/WintripAI.

Lees eerst:
- HANDOVER_NEXT_CHAT_OUROBOROS_2026-04-30.md
- OUROBOROS_FASE4_5_SESSION_REPORT_2026-04-28.md
- WINTRIP_OUROBOROS_WEBBEEST_SESSION_REPORT_2026-04-29.md

Werk vanaf branch:
codex/ouroboros-phase1-agent-loop-20260430

Huidige doel:
Ga verder vanaf de backend-first Ouroboros Fase 1 agent-machine.
Niet terug naar decoratieve UI.
Controleer eerst /health, /api/ouroboros/status en de Docker tests.

Belangrijk:
- Alles Docker-contained.
- Browserdata blijft UNTRUSTED tot scrubbed + Akkoord.
- Shell alleen via safe_shell.
- ChromaDB opslag alleen met 11D metadata.
- Geen fake toolcalls of mock-success.
- Echte fine-tune/weights niet claimen tenzij het werkelijk is uitgevoerd.
```

## Waarschijnlijke Volgende Stap

1. Maak of activeer het Ollama model `ouroboros` via de UI create-flow met `Akkoord`.
2. Controleer of `/api/ouroboros/status` daarna `model.online=true` meldt.
3. Bouw daarna de dataset/logboek-flow voor latere LoRA/fine-tune.
4. Pas daarna pas UI verder aan.
