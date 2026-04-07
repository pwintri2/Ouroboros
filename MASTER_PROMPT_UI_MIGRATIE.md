# MASTER PROMPT — Wintrip AI: Web Frontend Migratie

> **Kopieer alles hieronder naar de AI Chat in VS Code / Cursor.**
> De prompt begint na de streep.

---

Je bent de autonome developer voor het Wintrip AI project. Je hebt volledige toegang tot de workspace. Je gaat een strategische architectuur-pivot uitvoeren: de volledige User Interface verhuist van Swift/SwiftUI naar een web-frontend die draait bovenop de bestaande Python FastAPI + ChromaDB (Docker) backend. De eigenaar, Philip, wil op termijn (Fase 100) een "Data uit Star Trek"-achtige AI-assistent naast zich. Daarvoor moet de basis simpel, schaalbaar en onzichtbaar zijn — geen open terminals, geen zichtbare poorten.

## STAP 0 — ANALYSEER EERST (VERPLICHT)

Voordat je ook maar één bestand aanmaakt:

1. Lees en begrijp de volledige mappenstructuur van de workspace.
2. Lees `controller/main.py` om de huidige FastAPI app, routes en middleware te begrijpen.
3. Lees `docker-compose.yml` (of `docker-compose.yaml`) om de container-setup, volumes, poorten en services te begrijpen.
4. Lees `controller/requirements.txt` voor de huidige dependencies.
5. Zoek naar eventuele Swift/SwiftUI bestanden en noteer ze (verwijder ze NIET zonder bevestiging).
6. Lees `controller/api/stream_routes.py` — dit is de Phase 7.X Stream of Consciousness API die al werkt.
7. Lees `controller/router.py` en `controller/orchestrator.py` om de bestaande chatflow te snappen.

Print na deze analyse een korte samenvatting: welke routes bestaan, welke poorten open staan, waar de data-directory zit, en welke bestanden je gaat aanmaken/wijzigen.

## STAP 1 — DE UI LAYOUT (SINGLE SOURCE OF TRUTH)

Hieronder staat de exacte layout zoals Philip heeft geschetst. Dit is je absolute blauwdruk. Wijk hier niet van af.

```
┌──────────────────────────────────────────────────────────────────┐
│ TOP BAR                                                          │
│ [Model: GPT-4o ▼] [Model: Claude ▼] [Model: Gemini ▼]   [API's]│
├────────────────┬─────────────────────────────────────────────────┤
│ LEFT SIDEBAR   │ MAIN CONTENT AREA                               │
│ (220px fixed)  │                                                 │
│                │ ┌─────────────────────────────────────────────┐ │
│ ☐ Vergadertafel│ │ TABBLADEN:                                  │ │
│   (Meeting Rm) │ │ [Meeting Room] [IT Team] [Persona's]       │ │
│                │ ├─────────────────────────────────────────────┤ │
│ ☐ IT Team      │ │                                             │ │
│                │ │              CHAT MESSAGES                   │ │
│ ○ Persona's    │ │              (scrollbaar, flex-grow)         │ │
│   beheer       │ │                                             │ │
│                │ │                                             │ │
│ ○ Projecten    │ │                                             │ │
│                │ ├─────────────────────────────────────────────┤ │
│ [+ Nieuwe Chat]│ │ BOTTOM BAR ("Hand and Feet")                │ │
│                │ │ 📎 Bijlagen  🎤 Voice    [Type hier...]  ➤ │ │
│ ── Chats ──    │ │ ☰ Tools                                    │ │
│ Chat 1         │ └─────────────────────────────────────────────┘ │
│ Chat 2         │                                                 │
│ Chat 3         │                                                 │
│ Chat 4         │                                                 │
│ ...            │                                                 │
└────────────────┴─────────────────────────────────────────────────┘
```

### Elementen in detail:

**TOP BAR (h-14, border-bottom)**
- Links: Model-selectoren als dropdown badges. Drie modellen: OpenAI (GPT-4o), Anthropic (Claude), Google (Gemini). Elk met een gekleurd icoon. De actieve model heeft een lichtgevende rand.
- Rechts: "API's" knop die een modal opent om API keys te beheren per provider.

**LEFT SIDEBAR (w-56, bg-gray-900, border-right)**
Van boven naar beneden:
1. Wintrip AI logo + naam (klein, subtiel)
2. **Vergadertafel** (Meeting Room) — knop, opent het multi-agent vergaderzicht in het hoofdpaneel.
3. **IT Team** — knop, toont de team-configuratie (welke agents actief zijn, hun rollen).
4. **Persona's beheer** — knop, opent een scherm om persona's aan te maken/bewerken. Met upload-mogelijkheid voor profielfoto's.
5. **Projecten** — knop, toont de projectenlijst.
6. **[+ Nieuwe Chat]** knop — maakt een nieuw gesprek aan.
7. Divider
8. **Chatgeschiedenis** — scrollbare lijst van eerdere chats, gesorteerd op datum (nieuwst bovenaan). Klikbaar om te openen in het hoofdpaneel.

**MAIN CONTENT AREA (flex-1)**
- Bovenaan: **tabbladen** die wisselen afhankelijk van wat geselecteerd is in de sidebar. Meeting Room, IT Team, Persona's zijn elk een tab-view. De standaard-view is de Chat.
- Midden: **Chat message area** — scrollbaar, neemt alle beschikbare ruimte in. Berichten tonen: afzender (model/user), tekst, timestamp. Markdown rendering.
- Onderaan: **"Hand and Feet" input bar** — de actie-balk:
  - 📎 Paperclip icoon: bijlagen uploaden (bestanden, afbeeldingen)
  - 🎤 Microfoon icoon: voice input (Fase 7, voorlopig als disabled/placeholder)
  - ☰ Tools dropdown: snelle acties (web search, code execute, etc.)
  - Tekstveld: auto-grow textarea
  - ➤ Verzendknop

## STAP 2 — TECH STACK

```
Frontend:  Vanilla HTML + Tailwind CSS (via CDN) + vanilla JavaScript (ES modules)
           GEEN React, GEEN npm build stap, GEEN node_modules.
           Alle frontend-bestanden worden geserveerd door FastAPI als static files.
Backend:   Bestaande FastAPI app (controller/main.py)
Storage:   ChromaDB (reeds in Docker) + SQLite voor chat-history
Container: Docker Compose (bestaand)
Styling:   Tailwind CSS via <script src="https://cdn.tailwindcss.com"> in dev;
           later optioneel eigen build.
Fonts:     Inter (Google Fonts CDN)
Kleurenpalet: Donker thema (bg-gray-950 / bg-gray-900), cyan (#00d4ff) accenten,
              consistent met de bestaande Wintrip AI branding.
```

## STAP 3 — BESTANDEN AANMAKEN

Maak de volgende bestandenstructuur aan:

```
regiekamer/                        ← Frontend root (nieuw)
├── index.html                     ← Hoofdpagina (SPA shell)
├── css/
│   └── wintrip.css               ← Custom CSS (minimaal, Tailwind doet het meeste)
├── js/
│   ├── app.js                    ← Hoofd-initialisatie, router, state management
│   ├── api.js                    ← Alle fetch()-calls naar de FastAPI backend
│   ├── chat.js                   ← Chat UI logica (berichten renderen, verzenden)
│   ├── sidebar.js                ← Sidebar navigatie, chat-lijst
│   ├── models.js                 ← Model-selector logica (GPT/Claude/Gemini switch)
│   ├── meeting.js                ← Vergadertafel / Meeting Room view
│   ├── team.js                   ← IT Team configuratie view
│   ├── personas.js               ← Persona beheer + foto upload
│   └── tools.js                  ← Tools dropdown logica
├── img/
│   └── wintrip-logo.svg          ← Logo (maak een minimalistisch SVG)
│
controller/
├── main.py                        ← WIJZIG: voeg StaticFiles mount en UI route toe
├── api/
│   ├── chat_routes.py             ← NIEUW: POST /api/chat, GET /api/chats, GET /api/chats/{id}
│   ├── model_routes.py            ← NIEUW: GET /api/models, POST /api/models/select
│   ├── persona_routes.py          ← NIEUW: CRUD + foto upload voor persona's
│   └── stream_routes.py           ← BESTAAND, niet wijzigen
│
wintrip_launcher.command            ← NIEUW: Mac one-click launcher (zie Stap 6)
```

## STAP 4 — FRONTEND IMPLEMENTATIE

### index.html
- Laad Tailwind via CDN, Inter font via Google Fonts.
- Eén `<div id="app">` container.
- Importeer alle JS modules via `<script type="module" src="/static/js/app.js">`.
- Geen inline scripts, geen inline styles.

### app.js
- Initialiseer de app: laad chatgeschiedenis, zet de active view, bind event listeners.
- Simpele state object: `{ activeView: 'chat', activeChat: null, activeModel: 'gpt-4o', chats: [] }`.
- Router: luister naar sidebar-klikken en wissel de main content area.

### api.js
- Wrapper rond `fetch()` met base URL `/api/`.
- Functies: `sendMessage(chatId, message)`, `getChats()`, `getChat(id)`, `createChat()`, `getModels()`, `selectModel(name)`, `getStreamStatus()`, `getStreamQueue()`, `approveStreamItem(id)`.
- Error handling: toon een toast-notificatie bij falen.

### chat.js
- Render berichten als bubbles: user rechts (blauw/cyan), AI links (grijs).
- Markdown rendering: gebruik een simpele regex-based renderer (geen externe library). Bold, italic, code blocks, links.
- Auto-scroll naar beneden bij nieuw bericht.
- Streaming-support: als de backend Server-Sent Events stuurt, toon het antwoord letter voor letter.

### sidebar.js
- Render de navigatie-items (Vergadertafel, IT Team, Persona's, Projecten).
- Render de chatlijst dynamisch vanuit state.
- Active item krijgt een cyan linkerborder + lichtere achtergrond.
- "Nieuwe Chat" knop bovenaan de chatlijst.

### models.js
- Drie model-badges in de topbar: OpenAI (groen), Claude (oranje), Gemini (blauw).
- Klikken selecteert het actieve model. Het actieve model krijgt een glow-effect.
- De selectie wordt doorgegeven aan api.js bij elke sendMessage().

## STAP 5 — BACKEND WIJZIGINGEN

### controller/main.py — Wijzigingen:

```python
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

# Na het aanmaken van de app:
app.mount("/static", StaticFiles(directory="regiekamer"), name="static")

# Catch-all route voor de SPA (MOET na alle /api/ routes):
@app.get("/")
async def serve_ui():
    return FileResponse("regiekamer/index.html")
```

### controller/api/chat_routes.py — Nieuwe routes:

```
POST /api/chat          → Stuur een bericht, ontvang AI-antwoord
GET  /api/chats         → Lijst van alle chats (id, titel, laatste bericht, datum)
GET  /api/chats/{id}    → Alle berichten in een chat
POST /api/chats         → Maak nieuwe chat aan
DELETE /api/chats/{id}  → Verwijder chat
```

De chat-route moet de bestaande `orchestrator.py` of `router.py` aanroepen — analyseer in Stap 0 hoe de huidige chatflow werkt en sluit daar naadloos op aan. Maak GEEN nieuwe LLM-aanroeplogica; hergebruik wat er al is.

### controller/api/model_routes.py — Nieuwe routes:

```
GET  /api/models             → Beschikbare modellen (naam, provider, status)
POST /api/models/active      → Selecteer actief model { "model": "gpt-4o" }
```

Lees uit de bestaande `provider_router.py` of `ollama_client.py` welke modellen beschikbaar zijn.

### controller/api/persona_routes.py — Nieuwe routes:

```
GET    /api/personas             → Lijst van persona's
POST   /api/personas             → Maak nieuwe persona aan
PUT    /api/personas/{id}        → Wijzig persona
DELETE /api/personas/{id}        → Verwijder persona
POST   /api/personas/{id}/photo  → Upload profielfoto (multipart/form-data)
```

Sla persona-data op in `data/personas/` als JSON + afbeeldingen.

## STAP 6 — DE MAGISCHE KNOP (NO-TERMINAL LAUNCHER)

Maak het bestand `wintrip_launcher.command` in de root van het project:

```bash
#!/bin/bash
# Wintrip AI Launcher — Dubbelklik om te starten
# Verbergt zichzelf en opent de browser automatisch.

cd "$(dirname "$0")"

# Verberg Terminal (sluit het venster na het starten)
osascript -e 'tell application "Terminal" to set visible of front window to false' 2>/dev/null &

# Start Docker Compose op de achtergrond
docker-compose up -d 2>/dev/null

# Wacht tot de backend klaar is (max 30 seconden)
echo "Wintrip AI wordt gestart..."
for i in $(seq 1 30); do
    if curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
        break
    fi
    sleep 1
done

# Open de browser
open "http://localhost:8000"

# Sluit dit terminal-venster
osascript -e 'tell application "Terminal" to close front window' 2>/dev/null &
exit 0
```

Na het aanmaken: `chmod +x wintrip_launcher.command`

Maak ook een health-check endpoint aan:

```python
# In controller/main.py
@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "wintrip-ai", "phase": "7.X"}
```

## STAP 7 — DOCKER AANPASSINGEN

Controleer en pas `docker-compose.yml` aan:
- Zorg dat port 8000 gemapt is: `ports: ["8000:8000"]`
- Voeg een volume mount toe voor `regiekamer/`: zodat de frontend bestanden beschikbaar zijn in de container.
- Voeg een health check toe aan de service.

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/api/health"]
  interval: 10s
  timeout: 5s
  retries: 3
```

## STAP 8 — VERWIJDER SWIFT AFHANKELIJKHEDEN

Zoek naar alle bestanden gerelateerd aan Swift/SwiftUI/Xcode:
- `.swift` bestanden
- `.xcodeproj` / `.xcworkspace` mappen
- `Package.swift`
- `Info.plist` gerelateerd aan de macOS app

**VERWIJDER DEZE NIET AUTOMATISCH.** Maak een lijst en vraag Philip om bevestiging voordat je iets verwijdert. Verplaats ze eventueel naar een `archive/swift-legacy/` map.

## STAP 9 — KWALITEITSCONTROLE

Na het aanmaken van alle bestanden:

1. Controleer dat `index.html` correct laadt met alle JS-modules.
2. Controleer dat alle API-routes geregistreerd zijn in main.py.
3. Controleer dat de sidebar-navigatie werkt (klik → view wisselt).
4. Controleer dat de model-selector visueel werkt.
5. Controleer dat het chat-inputveld berichten kan verzenden naar de backend.
6. Controleer dat `wintrip_launcher.command` executable is.
7. Run `flake8 controller/api/ --max-line-length=120` om lint-fouten te checken.

## ABSOLUTE REGELS

- **Sandbox veilig**: Geen `rm -rf`, geen `sudo`, geen systeemwijzigingen.
- **Geen .env wijzigingen**: Raak bestaande secrets/API keys NIET aan.
- **Geen push naar main**: Werk op branch `webbeest`.
- **Geen npm / node_modules**: Alle frontend is vanilla HTML/JS + Tailwind CDN.
- **Bestaande routes niet breken**: De Phase 7.X stream endpoints moeten intact blijven.
- **Alle web-content is UNTRUSTED**: Sanitize alle user input in de frontend.
- **Mobile-ready**: De layout moet responsive zijn (sidebar collapse op small screens).

## SAMENVATTING

Je bouwt in deze volgorde:
1. Analyseer de workspace (Stap 0)
2. Maak de frontend-bestanden aan (Stap 3 + 4)
3. Wijzig de backend (Stap 5)
4. Maak de launcher (Stap 6)
5. Pas Docker aan (Stap 7)
6. Inventariseer Swift-bestanden (Stap 8)
7. Test alles (Stap 9)

Begin met Stap 0. Rapporteer je bevindingen. Ga daarna autonoom door met de rest.
