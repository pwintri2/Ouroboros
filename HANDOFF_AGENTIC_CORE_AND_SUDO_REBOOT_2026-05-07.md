# Handoff: Agentic Core WIP + Sudo Reboot - 2026-05-07

Werkmap: `/home/pwintri2/WintripAI`

## Waarom Deze Handoff

Philip gaat rebooten omdat host-`sudo` vastloopt. Deze handoff legt vast waar
we waren, wat al getest is, en wat na reboot eerst gecontroleerd moet worden.

## Belangrijkste Correctie In Context

Gemini CLI was alleen genoemd omdat een eerdere prompt oorspronkelijk voor
Gemini CLI bedoeld was. Philip heeft besloten bij Codex te blijven. Het
tijdelijke Gemini-promptbestand dat Codex maakte is verwijderd. Gemini is dus
niet de actieve uitvoerder.

## Huidige Ouroboros Stand

De recente handoffs zijn gelezen en blijven leidend:

- `HANDOFF_QUANTUM_FOAM_FIELD_V4_9_2026-05-06.md`
- `HANDOFF_OUROBOROS_DOCKER_REALITY_HARDENING_2026-05-07.md`
- `HANDOFF_OUROBOROS_CIRQ_11D_POCKET_VOICE_2026-05-07.md`
- `HANDOFF_OUROBOROS_AGENT_RUNTIME_FASE1_KLAAR_2026-05-04.md`

Belangrijk beeld:

- Quantum Foam v4.9 is al gebouwd en getest.
- Docker/procfs real-observation hardening is al gebouwd en getest.
- Cirq/11D pocket voice is al gebouwd en getest.
- `/codex <taak>` is al aangesloten via Agent Runtime Fase 1 en host bridge.
- De huidige WIP is de Agentic Core: planning, tool execution, 11D pocket
  processing, ChromaDB session memory, en cockpit-zichtbaarheid/provenance.

## Agentic Core WIP Die Nu Staat

Nieuwe/onvoltooide maar geteste WIP:

- `controller/agentic_processor.py`
  - plant toolstappen via LLM of heuristic fallback;
  - corrigeert LLM-plannen deterministisch met intent-guardrails;
  - zet bij actuele/internetvragen eerst `memory_search` en daarna
    `brave_search`, ook wanneer het gekozen model Brave vergeet;
  - OV/reisplanner-vragen zoals trein/route/aankomst/afspraak-tijd worden nu
    als actuele reisplannercontext behandeld en krijgen `ns_travel_advice`;
  - Brave Search wordt bij OV niet meer gebruikt als bron voor exacte tijden,
    omdat snippets/LLM-context daarvoor te onnauwkeurig zijn;
  - `ns_travel_advice` gebruikt de officiële NS API wanneer een key via
    `WINTRIP_NS_API_KEY`, `NS_API_KEY`, `NS_APP_API_KEY` of
    `NS_API_SUBSCRIPTION_KEY` beschikbaar is;
  - zonder NS API key geeft `ns_travel_advice` alleen een officiële
    NS Reisplanner-link terug en markeert `authoritative=false`, zodat het model
    geen tijden mag verzinnen;
  - verwijdert irrelevante `voice_chat_status` stappen wanneer `spraak` alleen
    als substring in woorden zoals `afspraak` voorkomt;
  - voert tools stap voor stap uit;
  - blokkeert muterende/private acties zonder exact `Akkoord`;
  - verwerkt toolresultaten door de 11D pocket;
  - bouwt provenance zoals `brave_search_used`, `tools_used`,
    `pocket_processed_steps`, `mutating_tools_attempted`,
    `planner_guardrails_applied`.
- `controller/persistent_memory_manager.py`
  - `save_agentic_session`;
  - redigeert secrets;
  - schrijft bounded ChromaDB memory;
  - gebruikt 11D embedding.
- `controller/main.py`
  - route `/api/orchestrator/agentic`;
  - cockpit-chat routeert complexe non-slash prompts naar Agentic Core.
- `controller/orchestrator.py`
  - `should_use_agentic_processor`;
  - `WintripOrchestrator.agentic_process`.
- Cockpit:
  - `AgenticTraceReadout`;
  - badges voor Bronpad, Brave Search, 11D pocket, Memory;
  - badge/chips voor `planner_guardrails_applied`;
  - `planner_source` en guardrails in de compacte result-samenvatting;
  - samenvatting laat route/tool/provenance zien.

## Fase-2 Slice Net Toegevoegd

`controller/agent_tools.py` heeft nu schemas en dispatch voor:

- `world_grok_ask`
- `mail_read_recent`
- `mail_send_preview`
- `mail_send`
- `social_post_preview`
- `social_post_publish`
- `codex_job_start`
- `voice_chat_status`

Veiligheidsstatus:

- Brave Search blijft read-only en vereist geen `Akkoord`.
- `mail_read_recent` vereist `Akkoord` omdat het private mailboxdata leest.
- `mail_send`, `social_post_publish`, `world_grok_ask`, `codex_job_start`
  vereisen `Akkoord`.
- Mail/social previews voeren geen externe actie uit.
- `mail_send` en `social_post_publish` geven eerlijk `unavailable` als er geen
  connector is; ze claimen geen verzenden/posten.
- `codex_job_start` start via bestaande Agent Runtime en vereist `Akkoord`.
- `voice_chat_status` is alleen status; geen microfoon/audio wordt geopend.

`controller/agentic_processor.py` kent deze tools nu als approval/external/
mutating waar nodig en de heuristic planner herkent mail/social/Grok/voice/
Codex-doelen.

## Validatie Voor Reboot

Groen:

```bash
python3 -m py_compile \
  controller/agent_tools.py \
  controller/agentic_processor.py \
  controller/persistent_memory_manager.py \
  controller/orchestrator.py \
  controller/main.py
```

Groen:

```bash
python3 -m unittest \
  sandbox_tests.test_agentic_processor \
  sandbox_tests.test_persistent_memory_manager \
  sandbox_tests.test_agent_tools \
  sandbox_tests.test_tauri_backend_routes \
  sandbox_tests.test_tauri_cockpit_files
```

Resultaat voor reboot: `Ran 51 tests ... OK (skipped=24)`.

Na reboot extra guardrail-slice toegevoegd en groen:

```bash
python3 -m unittest \
  sandbox_tests.test_agentic_processor \
  sandbox_tests.test_persistent_memory_manager \
  sandbox_tests.test_agent_tools \
  sandbox_tests.test_tauri_backend_routes \
  sandbox_tests.test_tauri_cockpit_files
```

Resultaat: `Ran 53 tests ... OK (skipped=24)`.

Daarna is een OV/trein-regressie toegevoegd voor:

```text
Kun je opzoeken hoe laat ik de trein in Ermelo moet nemen als ik om 13:30 een afspraak op Utrecht centraal heb?
```

Verwacht bronpad: `memory_search -> ns_travel_advice`, geen
`voice_chat_status`. Zonder NS API key mag de agent geen exacte tijden noemen.

Validatie groen:

```bash
python3 -m unittest \
  sandbox_tests.test_agentic_processor \
  sandbox_tests.test_persistent_memory_manager \
  sandbox_tests.test_agent_tools \
  sandbox_tests.test_tauri_backend_routes \
  sandbox_tests.test_tauri_cockpit_files
```

Resultaat: `Ran 57 tests ... OK (skipped=24)`.

Later aangescherpt omdat Brave-snippets niet betrouwbaar genoeg zijn voor
treintijden:

- Nieuwe tool: `controller/agent_tools.py::ns_travel_advice`
- Docker env pass-through toegevoegd voor NS API keys.
- Regressie verwacht nu `memory_search -> ns_travel_advice`.

Validatie groen:

```bash
python3 -m unittest \
  sandbox_tests.test_agentic_processor \
  sandbox_tests.test_persistent_memory_manager \
  sandbox_tests.test_agent_tools \
  sandbox_tests.test_tauri_backend_routes \
  sandbox_tests.test_tauri_cockpit_files
```

Resultaat: `Ran 59 tests ... OK (skipped=24)`.

Ook groen na de cockpit guardrail-readout:

```bash
cd ouroboros_cockpit && npm run build
```

Resultaat: build OK; alleen bestaande Vite chunk-size warning.

Groen:

```bash
cd ouroboros_cockpit && npm run build
```

Resultaat: build OK; alleen bestaande Vite chunk-size warning.

## Git Status Voor Reboot

Niet gecommit. Selectief stagen later.

Code/config WIP:

- `Dockerfile.ouroboros-backend`
- `controller/agent_tools.py`
- `controller/main.py`
- `controller/orchestrator.py`
- `docker-compose.yml`
- `ouroboros_cockpit/src/App.tsx`
- `ouroboros_cockpit/src/styles.css`
- `ouroboros_esoteric/ouroboros_consciousness_loop.py`
- `sandbox_tests/test_agent_tools.py`
- `sandbox_tests/test_tauri_backend_routes.py`
- `sandbox_tests/test_tauri_cockpit_files.py`
- `controller/agentic_processor.py` nieuw
- `controller/persistent_memory_manager.py` nieuw
- `sandbox_tests/test_agentic_processor.py` nieuw
- `sandbox_tests/test_persistent_memory_manager.py` nieuw

Runtime/local artefacts:

- `wintrip_brain/chroma.sqlite3`
- `wintrip_brain/c57ec314-6d75-4f49-ad9e-27069e6327f6/length.bin`
- `QuantumNode.txt`
- `network-tools.sh`

De Chroma/runtime files niet committen tenzij Philip dat expliciet vraagt.

## Sudo Probleem

Philip meldde dat echte host-terminal `sudo` een leeg scherm geeft met een
knipperende cursor; getypte letters zijn zichtbaar en Ctrl-C werkt niet.

Onderzoek:

- Dit was niet de cockpit-terminal.
- `~/.bashrc` had een riskante regel:

```bash
stty echo
```

Die is verwijderd/vervangen door commentaar:

```bash
# Do not force terminal echo here: sudo/password prompts manage echo
# themselves. If a terminal ever gets stuck after an aborted command, run:
#   stty sane
```

Daarmee is een duidelijke terminal-echo fout opgelost, maar sudo zelf hing nog.

Logs tonen sinds ongeveer 19:20:

```text
pam_unix(sudo:auth): conversation failed
pam_unix(sudo:auth): auth could not identify password for [pwintri2]
```

Laatste process snapshot voor reboot:

```text
root sudo sudo -k
```

Eerdere vastgelopen sudo-processen zijn waarschijnlijk deels verdwenen, maar
reboot is de juiste cleanup omdat root sudo-processen zonder werkende sudo niet
veilig door de user te killen zijn.

Na reboot eerst testen:

```bash
stty sane
sudo -k
sudo -v
```

Bij `sudo -v` moet het wachtwoord niet zichtbaar zijn tijdens typen.

Als sudo nog hangt na reboot:

1. Sluit die terminaltab.
2. Open een verse terminal.
3. Test non-interactive:

```bash
sudo -n true
echo $?
```

Dit hoort direct te eindigen met een melding/code als er geen cached auth is,
niet te hangen.

## Directe Volgende Stap Na Reboot

1. Check sudo:

```bash
stty sane
sudo -k
sudo -v
```

2. Check repo:

```bash
cd /home/pwintri2/WintripAI
git status --short
```

3. Herhaal gerichte validatie:

```bash
python3 -m unittest \
  sandbox_tests.test_agentic_processor \
  sandbox_tests.test_persistent_memory_manager \
  sandbox_tests.test_agent_tools \
  sandbox_tests.test_tauri_backend_routes \
  sandbox_tests.test_tauri_cockpit_files
```

4. Daarna verder met cockpit-zichtbaarheid:

- model-only versus `agentic_processor`;
- Brave -> 11D pocket -> gekozen cockpitmodel;
- geplande maar geblokkeerde tools;
- werkelijke tool-execution;
- memory save status.

## Guardrails

- Geen secrets in memory/context/handoff schrijven.
- Geen `.secrets/**` committen.
- Geen `wintrip_brain/**` runtime DB committen zonder expliciete keuze.
- Mail/social echte send/post pas met connector + exact `Akkoord`.
- Codex self-modification pas via Agent Runtime en exact `Akkoord`.
