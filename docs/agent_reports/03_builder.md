# Builder Report - Fase 2.5 Goose-like Standalone UI

## Scope

Rol: Builder
Project: Resonant Ouroboros Proto 1.1 - Fase 2.5
Datum: 2026-04-27
Branch-context: `codex/fase2-awake-keeper`

Builder-eigenaarschap in deze stap is bewust beperkt tot dit rapportbestand:

- `docs/agent_reports/03_builder.md`

Alle backend-, UI-, launcher- en packaging-wijzigingen blijven eigendom van Main Integration, tenzij Builder in een latere stap expliciet toestemming krijgt om die bestanden zelf te wijzigen.

## Context Inspectie

Builder heeft zich gebaseerd op:

- De overgedragen Fase 2 Awake Keeper-context.
- De Planner-readback: Swift/xcrun niet beschikbaar; Python/customtkinter fallback gekozen.
- De Orchestrator-readback: API-contract voor `/status`, `/chat`, `/control`, `/memory`; polling cadence; Safe Mode-regels; UI-button mapping.

Een Docker-safe read via `docker compose exec` is geprobeerd, maar de lokale VS Code-shell had geen `docker` binary beschikbaar. Er is daarna geen `flatpak-spawn --host` fallback gebruikt, omdat de opdracht expliciet host shelling verbiedt. Er zijn geen Docker `up`, `restart`, build-, package- of launch-commando's uitgevoerd.

## Build Decision

SwiftUI-pad:

- Niet gekozen.
- Planner heeft vastgesteld dat Swift/xcrun niet beschikbaar is.

Fallback-pad:

- Gekozen implementatiepad is een standalone Python desktop app met `customtkinter`.
- Doel is een premium Goose-inspired layout: donkere moderne desktop-app, linker status/control sidebar, centrale chat, onderste input composer.

## Intended Implementation: `goose_like_ui/`

Main Integration hoort een nieuwe map aan te maken:

- `goose_like_ui/`
- `goose_like_ui/app.py`
- `goose_like_ui/api_client.py`
- `goose_like_ui/state.py`
- `goose_like_ui/theme.py`
- `goose_like_ui/launcher.sh`
- `goose_like_ui/README.md`
- Eventueel `goose_like_ui/requirements.txt` als dependencies niet via de bestaande container/app-laag gedeeld worden.

Aanbevolen verantwoordelijkheden:

- `app.py`: customtkinter shell, layout, event wiring, polling loop.
- `api_client.py`: HTTP client voor Awake Keeper REST endpoints.
- `state.py`: typed/default UI state, chat-message model, error-state helpers.
- `theme.py`: Goose-like kleuren, spacing, typography constants.
- `launcher.sh`: one-click starter die de Python UI opent zonder Docker services te starten of te restarten.
- `README.md`: run-instructies, vereiste draaiende backend, safety notes.

## Intended UI Behavior

De standalone UI moet:

- Elke 1-2 seconden `/status` pollen.
- Een duidelijke Safe Mode indicator tonen.
- Live status tonen voor Hz, mood, iterations, current topic en last action.
- Chatberichten weergeven met assistant/user styling.
- Markdown-achtige tekst leesbaar renderen, minimaal met nette line wrapping en code/source blokken.
- Sources tonen wanneer de backend die meestuurt.
- Control buttons aanbieden:
  - Start Awake Mode
  - Stop
  - Manual PAEU Step
  - Creative Spike
  - View 11D Memory
  - Clear Queue

Chat-input moet via `/chat` lopen en niet rechtstreeks naar Ollama praten vanuit de UI. De UI blijft daarmee een veilige client bovenop de bestaande Fase 2 stack.

## Intended Backend REST Endpoints

Main Integration hoort, indien nog niet aanwezig, eenvoudige REST endpoints toe te voegen naast de bestaande Gradio/FastAPI service op `http://localhost:7861`.

### `GET /status`

Responsdoel:

```json
{
  "ok": true,
  "safe_mode": true,
  "awake": true,
  "hz": 432.0,
  "mood": "steady",
  "iterations": 42,
  "current_topic": "empathy and context",
  "last_action": "incorporated knowledge",
  "queue_size": 0,
  "model": "llama2-uncensored:latest"
}
```

### `POST /chat`

Requestdoel:

```json
{
  "message": "Wat weet je nu over empathische assistentie?",
  "context": {
    "source": "goose_like_ui"
  }
}
```

Responsdoel:

```json
{
  "ok": true,
  "reply": "Samengevat...",
  "hz": 432.0,
  "mood": "steady",
  "sources": [
    {
      "label": "11D memory",
      "detail": "AGI Kennis.txt / empathy"
    }
  ],
  "actions": []
}
```

`/chat` hoort de bestaande full stack te gebruiken: Ollama `llama2-uncensored:latest`, browser/browser-fallback context waar beschikbaar, 11D memory, empathie/context en de bestaande Awake Keeper state.

### `POST /control`

Requestdoel:

```json
{
  "action": "creative_spike"
}
```

Toegestane acties:

- `start_awake`
- `stop`
- `manual_paeu_step`
- `creative_spike`
- `clear_queue`

Responsdoel:

```json
{
  "ok": true,
  "action": "creative_spike",
  "status": {
    "hz": 888.0,
    "mood": "creative"
  }
}
```

### `GET /memory`

Responsdoel:

```json
{
  "ok": true,
  "records": [
    {
      "kind": "seed_knowledge",
      "topic": "empathy",
      "source": "AGI Kennis.txt",
      "record_id": "...",
      "hz": 432.0,
      "mood": "steady",
      "fidelity": 0.98,
      "summary": "..."
    }
  ]
}
```

## Backend Sharing Notes

De REST-laag moet dezelfde state gebruiken als het bestaande Gradio dashboard. Belangrijk:

- Geen tweede Awake Keeper instantie starten vanuit de UI.
- Geen directe host commands vanuit de UI.
- Geen Docker lifecycle management in de UI.
- Control requests moeten alleen bestaande in-process functies/state muteren.
- Polling mag licht blijven en mag geen PAEU-loop triggeren tenzij expliciet via `manual_paeu_step`.

Als de huidige Gradio app al een FastAPI object mount of expose heeft, hoort Main Integration daarop door te bouwen in plaats van een tweede server naast poort `7861` te starten.

## Safety Constraints For Implementation

Builder verwacht dat Main Integration bewaakt:

- Geen `subprocess` calls vanuit de desktop UI voor Docker, shell, host apps of build tools.
- UI communiceert alleen met `http://localhost:7861`.
- Ollama blijft backend-owned; desktop UI praat niet direct met `http://localhost:11434`.
- Clear Queue wist alleen de runtime queue, niet persisted memory.
- View 11D Memory is read-only.
- Creative Spike is een expliciete control call en moet zichtbaar terugvallen naar normale cadence/status.
- Safe Mode blijft altijd zichtbaar in de sidebar.

## Testing Handoff

Tester hoort na implementatie, maar voor een finale build/run, binnen de toegestane Docker-safe grenzen te controleren:

- `/status` geeft HTTP 200 en verwacht JSON-shape.
- `/memory` geeft records of een lege records-lijst met `ok: true`.
- `/control` accepteert alle toegestane acties en weigert onbekende acties.
- `/chat` retourneert `reply`, `hz`, `mood`, en eventueel `sources`.
- UI-code importeert zonder syntax/runtime import errors in de containeromgeving.
- Launcher-script bevat geen Docker up/restart/build logic.

Een echte desktop launch of final run mag pas na expliciete gebruikerstoestemming.

## Current Builder Changes

Builder heeft in deze stap alleen dit rapport toegevoegd:

- `docs/agent_reports/03_builder.md`

Geen backendbestanden, UI-bestanden, compose-bestanden, launchers of package scripts zijn door Builder gewijzigd.
