# Handover Fase 9 - Cockpit Lanes

Datum: 2026-05-05
Branch: `feature/esoteric-ouroboros-architecture`
Laatste basiscommit voor deze ronde: `cd9692e`

## Doel

De React cockpit is overzichtelijker gemaakt zonder de bestaande pijplijnen, key store of runtime contracten te verplaatsen. De browser UI en standalone Tauri UI gebruiken dezelfde React laag.

## Veranderd

- `ouroboros_cockpit/src/App.tsx`
  - Cockpit opgesplitst in duidelijke lanes: Chat, Tools, Models, Agents, Memory, Trainer en Context.
  - Chat lane houdt Agent Chat en Living Ouroboros echo gescheiden.
  - Tools lane bevat shell command runner, backend test runner, loop controls en terminal.
  - Models lane toont lokale Ollama modellen, abonnement/provider-overzicht en API key beheer.
  - Agents lane bundelt agent capabilities, Codex, agent jobs en Nexus events.
  - Memory lane bundelt 11D memory, Living Ouroboros, World Agent acties en raw status.
  - Terminal lifecycle gerepareerd zodat xterm opnieuw correct opent na tabwissels.

- `ouroboros_cockpit/src/styles.css`
  - Nieuwe cockpit layout met verticale lane navigatie.
  - Responsieve grids voor tools, modellen en memory.
  - Terminal, model chips, memory rows en statuspanelen visueel aangescherpt.

## Bewust Niet Aangeraakt

- Geen API keys of secrets verplaatst of opgeslagen in docs.
- Geen bestaande Docker/backend endpoints hernoemd.
- Geen nieuwe mappen aangemaakt.
- Runtime ChromaDB/brain data is buiten de commit gelaten.
- Lokale docx/odt/lock/bak artefacten zijn buiten de commit gelaten.

## Validatie

- `npm run build` in `ouroboros_cockpit` is geslaagd.
- Docker backend tests zijn geslaagd:
  - 53 tests OK voor Codex status/routes, slash router, living runtime, agents, OpenHands, World Agent health en Tauri backend routes.
  - 24 route tests OK voor Tauri backend routes en Codex routes.
- Live checks:
  - Backend health: `http://localhost:8010/health` online.
  - Browser UI: `http://127.0.0.1:1420/` online.
  - Standalone service: `ouroboros-cockpit-standalone.service` active.

## Huidige Werkende Startpunten

- Browser cockpit: `http://127.0.0.1:1420/`
- Backend API: `http://localhost:8010`
- Standalone cockpit draait via user systemd service:
  - `systemctl --user status ouroboros-cockpit-standalone.service`

## Volgende Logische Stap

De UI is nu functioneel opgeschoond. Als de cockpit verder groeit, is de volgende nette stap om de lanes uit `App.tsx` naar aparte componenten te halen, zonder eerst nieuwe architectuurlagen te introduceren.
