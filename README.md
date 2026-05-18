<div align="center">

# ⭕ Ouroboros

### *Jouw privé AI-brein. Volledig lokaal. Volledig van jou.*

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Ollama](https://img.shields.io/badge/LLM-Ollama-black?logo=llama&logoColor=white)](https://ollama.com/)
[![ChromaDB](https://img.shields.io/badge/Memory-ChromaDB-orange)](https://www.trychroma.com/)
[![macOS](https://img.shields.io/badge/Platform-macOS-lightgrey?logo=apple&logoColor=white)](https://www.apple.com/macos/)
[![License](https://img.shields.io/badge/Licentie-MIT-green)](LICENSE)

<br/>

> **Ouroboros** is een autonome, privacy-first AI-agent die volledig lokaal op jouw machine draait.  
> Geen data naar de cloud. Geen afluisteren. Alleen jij en jouw eigen brein.

<br/>

![Ouroboros Dashboard](https://img.shields.io/badge/Demo-Dashboard%20beschikbaar-brightgreen?style=for-the-badge)

</div>

---

## 📋 Inhoudsopgave

- [Over Ouroboros](#-over-ouroboros)
- [Kenmerken](#-kenmerken)
- [Architectuur](#-architectuur)
- [Componenten](#-componenten)
- [Privacy & Veiligheid](#-privacy--veiligheid)
- [Snel Starten](#-snel-starten)
- [API Overzicht](#-api-overzicht)
- [Ambient Sentinel PoC](#-ambient-sentinel-poc-demo)
- [Projectstructuur](#-projectstructuur)
- [Roadmap](#-roadmap)
- [Support Ouroboros](#-support-ouroboros)

---

## 🧠 Over Ouroboros

**Ouroboros** is gebouwd op een simpele maar krachtige overtuiging:

> *AI moet voor jou werken — niet omgekeerd. En zeker niet voor een techbedrijf in Silicon Valley.*

Ouroboros is een **lokaal-first, autonoom AI-systeem** dat de OODA-loop (Observe → Orient → Decide → Act) implementeert om taken volledig zelfstandig uit te voeren. Het draait op je eigen Mac, praat met een lokaal taalmodel via [Ollama](https://ollama.com/), slaat herinneringen op in een lokale vectordatabase ([ChromaDB](https://www.trychroma.com/)), en heeft een native macOS-interface gebouwd in SwiftUI.

Ouroboros is een product van [Ouroboros AI](https://ouroboros-ai.nl) — een Nederlands AI-bureau dat gelooft in AI die de mens versterkt, niet vervangt.

---

## ✨ Kenmerken

| Feature | Beschrijving |
|---|---|
| 🔒 **Privacy-First** | Al je data blijft op jouw machine. Lokaal LLM via Ollama als standaard. |
| 🧠 **Hippocampus (RAG)** | Persoonlijk geheugen via ChromaDB — de agent onthoudt wat jij hem vertelt. |
| 🔄 **OODA-Loop Orchestrator** | Autonoom taken uitvoeren in iteraties met reflectie en zelf-correctie. |
| 🛡️ **Ambient Sentinel** | Detecteert anomalieën op je OS (bijv. scareware) en lost ze stil op. |
| 📧 **Mail Integratie** | Leest e-mails via IMAP (alleen-lezen, nooit verwijderen). |
| 🌐 **Web Research** | Haalt actuele informatie op via Wikipedia API — geautomatiseerd. |
| 🗂️ **Document Analyse** | Verwerkt .txt, .pdf, .docx, .json, .md en ChatGPT exports. |
| 🤝 **Virtueel Team** | Meerdere AI-persona's die met elkaar vergaderen over een taak. |
| 🍎 **Native macOS UI** | Minimalistische menubalk-app gebouwd in SwiftUI. |
| 🔧 **Multi-Model Support** | Wissel naadloos tussen Ollama, Groq (cloud-escalatie), ChatGPT of Gemini. |

---

## 🏗️ Architectuur

Ouroboros is gebouwd rondom de **OODA-loop**: een militair besluitvormingsmodel dat perfect past bij autonome AI-agenten.

```
┌─────────────────────────────────────────────────────────────────┐
│                        Ouroboros Systeem                        │
│                                                                 │
│  ┌──────────────┐    HTTP/JSON    ┌───────────────────────────┐ │
│  │  Regiekamer  │ ◄────────────► │   FastAPI Backend          │ │
│  │  (SwiftUI)   │                │   controller/main.py       │ │
│  └──────────────┘                └──────────┬────────────────┘ │
│                                             │                   │
│              ┌──────────────────────────────┼──────────────┐    │
│              │                             │              │    │
│       ┌──────▼──────┐            ┌─────────▼──────┐  ┌───▼──┐ │
│       │  AI Router  │            │  Orchestrator  │  │ PoC  │ │
│       │  (OODA)     │            │  (OODA Loop)   │  │ Demo │ │
│       └──────┬──────┘            └─────────┬──────┘  └──────┘ │
│              │                             │                   │
│    ┌─────────┼──────────┐        ┌─────────┴──────────┐        │
│    │         │          │        │                    │        │
│  ┌─▼──┐  ┌──▼───┐  ┌───▼──┐  ┌──▼────┐          ┌───▼────┐   │
│  │LLM │  │ Mail │  │ Web  │  │Sandbox│          │Reflector│  │
│  │Tier│  │(IMAP)│  │Search│  │(Docker│          │         │  │
│  └────┘  └──────┘  └──────┘  └───────┘          └─────────┘  │
│              │                                                  │
│         ┌────▼──────────────────────────────────┐              │
│         │       Hippocampus (ChromaDB)           │              │
│         │       Persoonlijk Geheugen / RAG       │              │
│         └───────────────────────────────────────┘              │
└─────────────────────────────────────────────────────────────────┘
```

### LLM Tier-Systeem

```
Tier 3 (Standaard) ── Ollama lokaal ──────────── 🔒 Data verlaat nooit de machine
Tier 2 (Escalatie) ── Groq Cloud 70B ──────────── ⚡ Bij complexe taken na 2 lokale pogingen
Tier 1 (Optioneel) ── ChatGPT / Gemini / Claude ── 🌐 Handmatig te activeren
```

---

## 🧩 Componenten

### 🗂️ `/controller/` — Het Brein

| Bestand | Rol |
|---|---|
| `main.py` | FastAPI server — het centrale API-eindpunt |
| `router.py` | **Agentic Router** — herkent intent en stuurt acties aan |
| `orchestrator.py` | **OODA Orchestrator** — autonoom taken uitvoeren in iteraties |
| `knowledge_base.py` | **Hippocampus** — ChromaDB vectorgeheugen + RAG-zoekopdrachten |
| `reflector.py` | **Reflector** — evalueert output en classificeert resultaten (GREEN/YELLOW/RED) |
| `sandbox.py` | **Sandbox Executor** — voert LLM-gegenereerde code veilig uit in Docker |
| `scrubber.py` | **Scrubber** — verwijdert API-keys, wachtwoorden en PII vóór cloud-verwerking |
| `poc_demo.py` | **Ambient Sentinel** — anomaliedetectie & stille remediatie PoC |
| `web_search.py` | Wikipedia API integratie voor web-onderzoek |
| `mail_fetcher.py` | IMAP e-mail ophalen (alleen-lezen) |
| `virtual_team.py` | Meerdere AI-persona's in een virtuele vergadering |
| `groq_client.py` | Cloud-escalatie naar Groq 70B model |
| `ollama_client.py` | Lokale LLM client (Ollama) |

### 🍎 `/regiekamer/` — Native macOS UI

Een minimalistische **SwiftUI** menubalk-applicatie voor directe interactie met de backend. Gebouwd met SwiftData voor lokale persistentie. Alle API-aanroepen verlopen via `NetworkManager` met veilige optionals.

### 📂 `/data/` & `/output/`

```
/data/   ← Invoerzone (alleen lezen voor de agent)
          Ruwe documenten, archieven, e-mails, exports

/output/ ← Uitvoerzone (alleen schrijven door de agent)
          AI-rapporten, gegenereerde bestanden (Human-in-the-Loop)
```

### 🖥️ `/dashboard/`

Een webdashboard (`index.html`) dat automatisch opent op `http://localhost:8000` bij het starten via `start_demo.bat` of `start_demo.ps1`.

---

## 🛡️ Privacy & Veiligheid

Ouroboros is gebouwd met **privacy als basisvereiste**, niet als bijzaak.

```
╔══════════════════════════════════════════════════════════════╗
║  VEILIGHEIDSLAGEN                                            ║
╠══════════════════════════════════════════════════════════════╣
║  1. Strikte Pad-Isolatie                                     ║
║     → Leesrechten alleen in /data, schrijfrechten in /output ║
║     → Path Traversal validatie in de Python-laag            ║
╠══════════════════════════════════════════════════════════════╣
║  2. De Scrubber Regel                                        ║
║     → API-keys, wachtwoorden en PII worden LOKAAL gescand   ║
║     → Pas na scrubbing gaat data naar een cloud-tier        ║
╠══════════════════════════════════════════════════════════════╣
║  3. Read-Only IMAP                                           ║
║     → De agent kan NOOIT mails verwijderen of markeren      ║
║     → Softwarematig beperkt tot alleen-lezen                ║
╠══════════════════════════════════════════════════════════════╣
║  4. Sandbox Executie                                         ║
║     → LLM-gegenereerde code draait ALTIJD in Docker         ║
║     → Ephemere containers, geen persistente toegang         ║
╠══════════════════════════════════════════════════════════════╣
║  5. Local-First Default                                      ║
║     → Tier 3 (Ollama) is de standaard                       ║
║     → Gevoelige data verlaat de machine nooit               ║
╚══════════════════════════════════════════════════════════════╝
```

---

## 🚀 Snel Starten

### Vereisten

- **macOS** 13+ (Ventura of nieuwer)
- **Python** 3.10+
- **Ollama** geïnstalleerd en actief ([ollama.com](https://ollama.com/))
- **Docker** (voor sandbox code-executie)
- Swift Toolchain (voor de native Regiekamer UI)

### Installatie

```bash
# 1. Clone de repository
git clone https://github.com/pwintri2/wintripai.git
cd wintripai

# 2. Installeer Python dependencies
pip install -r controller/requirements.txt

# 3. Configureer je omgeving
cp ".env copy" .env
# Vul .env in met je IMAP-gegevens (optioneel voor mail-functionaliteit):
# IMAP_SERVER=imap.jouwprovider.nl
# IMAP_USER=jouw@email.nl
# IMAP_PASS=jouwwachtwoord

# 4. Zorg dat Ollama draait met het juiste model
ollama pull llama3.1
```

### Starten

#### macOS (aanbevolen)
```bash
./start.sh
```

#### Windows Demo
Dubbelklik op `start_demo.bat` — het script:
- Maakt automatisch een `.venv` aan
- Installeert alle dependencies
- Start de backend op `http://localhost:8000`
- Opent het dashboard in je browser

#### Handmatig
```bash
cd controller
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

### Gezondheidscheck

```bash
curl http://localhost:8000/health
# → {"status": "online", "agent": "Wintrip"}
```

---

## 📡 API Overzicht

| Methode | Endpoint | Beschrijving |
|---|---|---|
| `GET` | `/health` | Gezondheidscheck |
| `GET` | `/models` | Lijst beschikbare Ollama-modellen |
| `POST` | `/ask` | Stel een vraag aan de agent |
| `POST` | `/orchestrate` | Voer een taak autonoom uit (OODA-loop) |
| `POST` | `/learn/url` | Leer een webpagina in het geheugen |
| `POST` | `/team/discuss` | Virtuele teamvergadering over een taak |
| `POST` | `/model/switch` | Wissel actief LLM-model |
| `POST` | `/demo/run` | Start een Ambient Sentinel simulatie |
| `GET` | `/demo/state` | Huidige staat van de Ambient Sentinel |

### Voorbeeld: Een vraag stellen

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Wat staat er in mijn laatste e-mails?",
    "model": "llama3.1"
  }'
```

### Voorbeeld: Autonome taakuitvoering

```bash
curl -X POST http://localhost:8000/orchestrate \
  -H "Content-Type: application/json" \
  -d '{
    "task": "Schrijf een Python script dat de eerste 10 priemgetallen berekent",
    "max_iterations": 3
  }'
```

---

## 🔬 Ambient Sentinel PoC Demo

De **Ambient Sentinel** is een van de meest geavanceerde features van Ouroboros: een continu-bewakingssysteem dat anomalieën op je OS detecteert en **stil oplost** — zonder de gebruiker te alarmeren.

### Scenario: Scareware-aanval op een oudere gebruiker

```
Ouder persoon → opent browser → malafide popup verschijnt
               ↓
          Systeem audio gedempt (door malware)
               ↓
    ┌─── Ambient Sentinel detecteert anomalie ───┐
    │                                            │
    │  KernelStateMatrix (256-dim buffer)        │
    │     ↓                                      │
    │  AnomalyDetectionEngine                    │
    │  (Frobenius-norm temporal delta-score)     │
    │     ↓ CRITICAL anomalie gedetecteerd       │
    │  AutonomousResolutionLoop                  │
    │  → Beëindigt malafide proces               │
    │  → Herstelt systeem audio                 │
    │  → Sluit overlay                           │
    │     ↓                                      │
    │  EmpathyEngine                             │
    │  → Empathisch, rustgevend NL-bericht       │
    └────────────────────────────────────────────┘
               ↓
    "Geen zorgen, alles is weer in orde. 
     Ik heb een ongewenst venster voor je gesloten."
```

### Demo starten

```bash
# Start de demo simulatie
curl -X POST http://localhost:8000/demo/run \
  -H "Content-Type: application/json" \
  -d '{"inject_attack": true}'

# Controleer de huidige staat
curl http://localhost:8000/demo/state
```

---

## 📁 Projectstructuur

```
wintripai/
├── 📂 controller/           # FastAPI backend & agent-logica
│   ├── main.py              # API server entrypoint
│   ├── router.py            # Agentic Router (OODA)
│   ├── orchestrator.py      # Autonome taak-orchestrator
│   ├── knowledge_base.py    # Hippocampus (ChromaDB RAG)
│   ├── reflector.py         # Output-evaluator
│   ├── sandbox.py           # Docker sandbox executor
│   ├── scrubber.py          # Privacy scrubber
│   ├── poc_demo.py          # Ambient Sentinel PoC
│   ├── virtual_team.py      # Multi-persona vergadering
│   ├── mail_fetcher.py      # IMAP client
│   ├── web_search.py        # Wikipedia onderzoekstool
│   └── requirements.txt     # Python dependencies
│
├── 📂 regiekamer/           # Native macOS SwiftUI app
│
├── 📂 dashboard/            # Web dashboard (HTML)
│   └── index.html
│
├── 📂 data/                 # Invoerzone voor documenten
│
├── 📂 output/               # Uitvoerzone voor AI-rapporten
│
├── 📂 sandbox_tests/        # Unit tests voor OODA-logica
│
├── 🚀 start.sh              # Start-script macOS
├── 🚀 start_demo.bat        # Start-script Windows
├── 🚀 start_demo.ps1        # Start-script PowerShell
├── 📄 PROJECT.md            # Architectuur & structuur
├── 📄 ARCHITECTURE.md       # Agent-instructies
└── 📄 SESSION.md            # Actuele projectstatus
```

---

## 🗺️ Roadmap

- [x] **Fase 1** — Lokale LLM integratie (Ollama)
- [x] **Fase 2** — Hippocampus (ChromaDB RAG + tiered search)
- [x] **Fase 3** — Agentic Router met intent-detectie
- [x] **Fase 4** — OODA Orchestrator met reflectie & zelf-correctie
- [x] **Fase 4.5** — Ambient Sentinel PoC Demo
- [ ] **Fase 5** — Operationele OODA-loop zonder menselijke goedkeuring
- [ ] **Fase 6** — Gepersonaliseerde empathische berichten (`user_profile`)
- [ ] **Fase 7** — Volledige Docker-sandboxing op macOS (TCC/permissies)

---

## 💚 Support Ouroboros

Ouroboros wordt ontwikkeld als een open, praktisch AI-initiatief voor transparante en toegankelijke automatisering — met extra aandacht voor toepassingen die ouderen en kwetsbare mensen kunnen ondersteunen.

Sponsorship helpt om ontwikkeltijd, infrastructuur, testen, documentatie, publieke demo's en verantwoord onderzoek naar agent-based AI mogelijk te maken. Daarmee draag je direct bij aan tooling die repetitief werk vermindert, besluitvorming ondersteunt en AI-agenten op een zorgvuldige manier met mensen laat samenwerken.

Wil je dit werk steunen? Bekijk de sponsoropties in [SPONSORSHIP.md](SPONSORSHIP.md) of bezoek [ouroboros-ai.nl](https://ouroboros-ai.nl/).

---

## 🤝 Bijdragen

Dit is een privé-project van [Ouroboros AI](https://ouroboros-ai.nl). Feedback en suggesties zijn altijd welkom via de [Issues](https://github.com/pwintri2/wintripai/issues) pagina.

---

## 📄 Licentie

Zie [LICENSE](LICENSE) voor details.

---

<div align="center">

*Gebouwd met passie voor privacy en AI-autonomie.*

**[Ouroboros AI](https://ouroboros-ai.nl)** — *AI die voor jou werkt.*

</div>
