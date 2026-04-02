# 🦅 Wintrip: Local-First AI Agent voor macOS

Wintrip is een autonome, privacy-gerichte AI-agent die volledig lokaal op macOS draait. Het project combineert de kracht van lokale taalmodellen (Ollama) met een native Swift interface en een robuuste Python controller-laag.

## 🏗️ Architectuur & Mappenstructuur

-   **/controller/**: De hersenen van de agent. Bevat de FastAPI server, de Agentic Router, de Scrubber en alle data-parsers.
-   **/regiekamer/**: De native macOS UI (SwiftUI). Een minimalistische menubalk-applicatie voor directe interactie met het brein.
-   **/data/**: De veilige landingszone voor ruwe input (ongestructureerde documenten, archieven).
-   **/output/**: De gecontroleerde eindbestemming voor alle door de AI gegenereerde bestanden en rapporten (Human-in-the-Loop flow).

## 🛡️ Veiligheidsmechanismen (Constraint-Driven)

1.  **Strikte Isolatie**: De agent heeft uitsluitend leesrechten in `/data` en schrijfrechten in `/output`, beveiligd met *Path Traversal* validatie in de Python-laag.
2.  **De Scrubber Regel**: Alle data wordt lokaal gescand en gereinigd (API-keys, wachtwoorden, PII) voordat deze naar een Cloud-tier (Tier 1/2) wordt gestuurd.
3.  **Read-Only IMAP**: E-mail integratie is softwarematig beperkt tot alleen-lezen; de agent kan NOOIT mails verwijderen of als gelezen markeren.
4.  **Local-First Default**: Tier 3 (Ollama) is de standaard verwerkingslaag, waardoor gevoelige data de machine nooit verlaat.

## 🧠 Agentic Router & Tools

De AI-agent is niet passief, maar beschikt over een **Agentic Router** die op basis van jouw vragen autonoom gereedschap kan inzetten:
-   **Web Search**: Haalt actuele kennis en definities op via de Wikipedia API.
-   **Mail Fetcher**: Leest op verzoek recente e-mails via een beveiligde IMAP-verbinding.
-   **File Parser**: Analyseert lokale documenten (.txt, .json, .md, .eml) en ChatGPT exports.

## 🚀 Het project opstarten

1.  **Vereisten**:
    -   Zorg dat **Ollama** draait op je Mac (standaard model: `llama3`).
    -   Installeer Python dependencies: `pip install -r controller/requirements.txt`.
    -   Swift Toolchain (macOS 13+) voor de Regiekamer.
2.  **Configuratie**:
    -   Vul het `.env` bestand in de `WintripAI/` hoofdmap met je IMAP-credentials (`IMAP_SERVER`, `IMAP_USER`, `IMAP_PASS`).
3.  **Uitvoeren**:
    -   Start de volledige agent (backend + frontend) met één commando vanuit de hoofdmap:
        ```bash
        ./start.sh
        ```
    -   Gebruik `Ctrl+C` om alles veilig af te sluiten.

---
*Ontwikkeld met passie voor privacy en AI-autonomie.*
