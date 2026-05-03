# 🦅 Wintrip: Local-First AI Agent voor macOS én Linux

Wintrip is een autonome, privacy-gerichte AI-agent die volledig lokaal draait op **macOS** én **Linux/Pop!_OS**. Het project combineert xAI Grok (cloud) en lokale taalmodellen (Ollama) met een platform-native interface en een robuuste Python controller-laag.

## 🏗️ Architectuur & Mappenstructuur

- **/controller/**: De hersenen van de agent. FastAPI server, Agentic Router, Scrubber en data-parsers.
  - `grok_xai_client.py` — xAI Grok API (model: grok-3)
  - `groq_client.py` — Groq inference API (llama-3.3-70b)
  - `ollama_client.py` — Lokale Ollama LLMs
  - `linux_automator.py` — Linux computer-access tools
  - `mac_automator.py` — macOS AppleScript tools
- **/linux_app/**: Native GTK4/libadwaita chat-app voor Linux (Pop!_OS)
- **/regiekamer/**: Native macOS SwiftUI menubalk-applicatie
- **/data/**: Veilige landingszone voor ruwe input
- **/output/**: Eindbestemming voor AI-gegenereerde bestanden

## 🛡️ Veiligheidsmechanismen

1. **Strikte Isolatie**: Agent heeft uitsluitend leesrechten in `/data` en schrijfrechten in `/output`
2. **De Scrubber Regel**: Alle data wordt lokaal gescand voor verzending naar cloud-tier
3. **Read-Only IMAP**: E-mail integratie is beperkt tot alleen-lezen
4. **Local-First Default**: Tier 3 (Ollama) is de standaard verwerkingslaag

## 🧠 Agentic Router & Tools

- **Web Search**: Actuele kennis via Wikipedia API
- **Mail Fetcher**: Beveiligde IMAP-verbinding (alleen-lezen)
- **File Parser**: Analyseert lokale documenten (.txt, .json, .md, .pdf, .docx)
- **Shell Runner**: `RUN: <commando>` voert een shell-commando uit (Linux)
- **App Launcher**: `open <appnaam>` opent applicaties

## 🚀 Opstarten

### Linux / Pop!_OS (nieuw)
```bash
cp ".env copy" .env
# Vul XAI_API_KEY in .env
chmod +x start_linux.sh
./start_linux.sh
```

### macOS
1. Zorg dat **Ollama** draait (`ollama serve`)
2. `pip install -r controller/requirements.txt`
3. `./start.sh`

## ⚙️ Configuratie (.env)

| Variabele | Beschrijving |
|-----------|-------------|
| `XAI_API_KEY` | xAI Grok API-sleutel (https://console.x.ai/) |
| `GROQ_API_KEY` | Groq inference API-sleutel (optioneel) |
| `IMAP_SERVER` | IMAP-server adres |
| `IMAP_USER` | E-mailadres |
| `IMAP_PASS` | App-wachtwoord |
| `WINTRIP_DEFAULT_MODEL` | Standaard model (`grok`, `ollama`, etc.) |

---
*Ontwikkeld met passie voor privacy en AI-autonomie.*
