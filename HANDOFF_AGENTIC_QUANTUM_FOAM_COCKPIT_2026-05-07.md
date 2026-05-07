# Handoff: Agentic Core + Living Quantum Foam + Cockpit - 2026-05-07

Werkmap: `/home/pwintri2/WintripAI`

## Kernstand

Ouroboros heeft nu een zichtbare, agentische route:

- complexe non-slash cockpit-chat gaat via `AgenticProcessor`;
- toolgebruik wordt gepland, gevalideerd en stap voor stap uitgevoerd;
- muterende/private acties blijven geblokkeerd zonder exact `Akkoord`;
- Brave Search, mail/social/browser/Codex/voice-status tools zitten in het
  toolcatalogus-framework;
- het gekozen cockpitmodel blijft de interpretatielaag rond toolresultaten en
  11D-pocket context;
- Quantum Foam is nu gekoppeld aan agentische taken als tijdelijke levende laag:
  geboorte bij start, resonantie per toolstap, collapse voor eindsynthese.

## Nieuw Geïmplementeerd In Deze Slice

### Living Quantum Foam facade

Nieuwe file:

- `controller/quantum_foam_field.py`

Deze biedt de gevraagde controller-API:

- `QuantumFoamNode`
  - `type`
  - `weight`
  - `electron_state` als 11D symbolische, niet-binaire state
  - `connections`
  - `resonate()`
  - `evolve()`
  - `collapse()`
- `QuantumFoamField`
  - `spawn_field()`
  - `evolve()`
  - `collapse_field()`
  - `coherence`
  - `dominant_dimensions()`
  - bounded node count
- Mojo-detectie via `mojo_runtime_status()`, met expliciete
  `python_fallback` wanneer Mojo niet aanwezig is.

Belangrijk: deze file dupliceert de bestaande v4.9-kern niet. Hij fungeert als
controller-facing facade en gebruikt de bestaande runtime in
`ouroboros_esoteric/quantum_foam.py` waar mogelijk.

### Agentic Core integratie

Gewijzigd:

- `controller/agentic_processor.py`

Nieuwe flow:

1. `agentic_start` maakt/evolueert een Quantum Foam Field.
2. Elke toolstap schrijft een `quantum_foam` event in de step.
3. Toolresultaten worden met compact foam-context door de pocket gestuurd.
4. Voor synthese wordt `quantum_foam_collapse` uitgevoerd.
5. De audit-header toont nu ook:

```text
Quantum Foam: collapsed / coherence XX%
```

De synthese-prompt bevat de guardrail dat collapse leidend is: het veld mag na
taakafronding niet als blijvend actief worden voorgesteld.

### Pocket voice integratie

Gewijzigd:

- `controller/pocket_language_translator.py`

De vertaler accepteert nu `event["quantum_foam"]` en neemt mee:

- actieve/collapsed status;
- coherence;
- dominant dimensions;
- node types, weights en connections;
- collapse-event;
- ram release estimate.

### Cockpit zichtbaarheid

Gewijzigd:

- `ouroboros_cockpit/src/App.tsx`
- `ouroboros_cockpit/src/styles.css`

Zichtbaar in de cockpit:

- status-pill `Quantum Foam Field`;
- badge `Quantum Foam Field active`;
- coherence percentage;
- node list met type, weight, coherence en link count;
- expliciet `Field Collapse` event;
- aantal vrijgegeven nodes;
- chat refresh haalt na een agentische chat meteen QF/Living/Nexus-status op.

### Standalone cockpit en logo

In dezelfde werkreeks zaten al:

- native Tauri logo assets;
- in-app Ouroboros-logo;
- `scripts/start_ouroboros_cockpit.sh`;
- `scripts/install_ouroboros_cockpit_desktop.sh`.

De cockpit kan daarmee als standalone/native app gestart en in Applications
geregistreerd worden.

## Agentic Core Tooling Stand

Nieuwe/ongewijzigd belangrijke files:

- `controller/agentic_processor.py`
- `controller/persistent_memory_manager.py`
- `controller/agent_tools.py`
- `controller/orchestrator.py`
- `controller/main.py`
- `controller/tool_bridge.py` blijft de executielaag voor bridge tools.

Tools/framework:

- `memory_search`
- `brave_search`
- `browser_research`
- `mail_read_recent`
- `mail_send_preview`
- `mail_send`
- `social_post_preview`
- `social_post_publish`
- `world_grok_ask`
- `codex_job_start`
- `voice_chat_status`
- bridge tools zoals `read_file`, `write_file`, `run_command`, `apply_patch`.

Veiligheid:

- muterende/private acties vereisen `Akkoord`;
- secrets worden gescrubd voor geheugen/provenance;
- ChromaDB session-memory is bounded en mag geen keys/tokens bevatten.

## Belangrijke Openstaande Correctie

De eerdere OV-tool heet nog `ns_travel_advice`. Philip heeft daarna terecht
gecorrigeerd dat er geen NS API-route als uitgangspunt moet zijn.

Volgende stap:

- vervang/verbouw de OV-route naar mensachtige browserbediening:
  - open `ns.nl` of `9292.nl`;
  - vul vertrek/aankomst/tijd in;
  - lees resultaat uit de pagina;
  - geef alleen tijden als die zichtbaar uit de officiële planner komen;
  - anders officiële plannerlink en onzekerheid tonen.

Dit moet waarschijnlijk via de bestaande `browser_research`/World Agent route
of een nieuwe `browser_travel_planner` tool.

## Validatie

Groen:

```bash
python3 -m py_compile \
  controller/quantum_foam_field.py \
  controller/agentic_processor.py \
  controller/pocket_language_translator.py
```

Groen:

```bash
python3 -m unittest \
  sandbox_tests.test_quantum_foam_field_facade \
  sandbox_tests.test_quantum_foam \
  sandbox_tests.test_agentic_processor \
  sandbox_tests.test_tauri_cockpit_files
```

Resultaat: `Ran 28 tests ... OK`.

Groen:

```bash
python3 -m unittest \
  sandbox_tests.test_agentic_processor \
  sandbox_tests.test_persistent_memory_manager \
  sandbox_tests.test_agent_tools \
  sandbox_tests.test_tauri_backend_routes \
  sandbox_tests.test_tauri_cockpit_files \
  sandbox_tests.test_quantum_foam \
  sandbox_tests.test_quantum_foam_field_facade
```

Resultaat: `Ran 69 tests ... OK (skipped=24)`.

Groen:

```bash
cd ouroboros_cockpit && npm run build
```

Resultaat: build OK. Alleen bestaande Vite chunk-size warning.

Docker:

- `docker compose restart ouroboros-backend` uitgevoerd;
- `GET http://127.0.0.1:8010/health` geeft online;
- Quantum Foam API initiate/collapse smoke is OK;
- in Docker meldt `mojo_runtime_status()` nu `python_fallback`.

## Bewust Niet Meegenomen In Commit

Runtime-memory artefacten zijn bewust niet gestaged:

- `wintrip_brain/*`

Deze staan wel dirty omdat de backend/Chroma heeft geschreven, maar horen niet
bij de source-commit.

Losse untracked bestanden die buiten deze slice lijken te vallen en daarom niet
blind meegenomen zijn:

- `QuantumNode.txt`
- `camera-tools.sh`
- `controller/camera_manager.py`

`network-tools.sh` hoort wel bij de recente Docker/network werkreeks en is
meegenomen.

## Aanbevolen Volgende Stap

Pak de OV/reisplanner correctie als eerste:

1. maak browser-gebaseerde planner tool voor `ns.nl`/`9292.nl`;
2. vervang de `ns_travel_advice` guardrail of laat die alleen nog plannerlinks
   bouwen;
3. voeg regressie toe voor Ermelo -> Utrecht Centraal om 13:30 aankomst;
4. zorg dat het model geen tijden noemt zonder zichtbare officiële plannerdata.
