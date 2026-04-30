# Ouroboros Fase 4.5 / Fase 1 Session Report

Datum update: 2026-04-30
Repository: `pwintri2/wintripai`
Werkbranch voor deze update: `codex/ouroboros-phase1-agent-loop-20260430`

## Samenvatting

De richting is gecorrigeerd van een decoratieve cockpit naar een backend-first agent-machine voor `Ouroboros`.

Fase 1 levert nu een lokaal systeem op waarin:

- `ouroboros` als eigen Ollama-modelidentiteit voorbereid is via een Modelfile.
- Browseronderzoek echt via Playwright kan lopen binnen Docker.
- Browserdata altijd door een prompt-injection scrubber gaat.
- Opslag naar ChromaDB 11D-geheugen alleen na Philip's `Akkoord` gebeurt.
- Mentorrollen via Ollama niet alleen praten, maar echte registry-tools kunnen gebruiken.
- Shell-uitvoer via safe shell zichtbaar terugkomt als stdout/stderr.
- 11D-geometrie volume en oppervlakte opslaat bij training records.

Er is niets gedaan alsof het fine-tuning is. De Ollama modelidentiteit is een `ollama create`-flow met Modelfile; echte LoRA/weight training is nog een latere stap.

## Modelidentiteit `ouroboros`

Toegevoegd:

- `Modelfile.ouroboros`
- `controller/ouroboros_model.py`
- API flow in `controller/main.py`

Gedrag:

- Basisvoorkeur: `llama3.2:latest`, tenzij een lokaal beter/beschikbaar model gekozen wordt.
- System prompt benoemt expliciet:
  - "Je bent Ouroboros."
  - eerste doel: leren hoe het zichzelf kan trainen;
  - Ollama-mentoren helpen;
  - web/browserdata is `UNTRUSTED` tot scrubbed + approved;
  - ontbrekende kennis eerst uitzoeken;
  - alleen approval-gated tools gebruiken;
  - geen verzonnen commando's, bestanden, endpoints of resultaten.
- `/api/ouroboros/model/create-flow` schrijft/valideert de Modelfile.
- Met `Akkoord` kan de flow via Ollama API proberen `ouroboros` aan te maken.
- Status is eerlijk: `online` betekent pas dat Ollama het model `ouroboros` echt rapporteert.

## Browser Research Perimeter

Toegevoegd:

- `controller/browser_research.py`
- `controller/api/browser_routes.py`

Endpoints:

- `POST /browser/research`
- `POST /browser/read-visible-text`
- `POST /browser/chatgpt/ask`
- `POST /browser/scrub`
- `POST /api/ouroboros/research/browser`
- `POST /api/ouroboros/chatgpt/browser`

Gedrag:

- Playwright opent maximaal een pagina per researchactie.
- Geen bulk scraping.
- Geen login/CAPTCHA bypass.
- ChatGPT-browseractie typt/submittet alleen na exact `Akkoord`.
- Browserinhoud wordt altijd als `untrusted_web` behandeld.
- Scrubber maakt DiffView en blokkeert o.a. prompt injection, system prompt probes en tool-call requests.
- Browseronderzoek schrijft niet stiekem naar ChromaDB; opslag blijft een aparte `training_ingest` stap met `Akkoord`.

Runtime status:

- Playwright is toegevoegd aan `controller/requirements.txt`.
- Chromium en dependencies zijn in de Docker-container gevalideerd.
- Rooktest op `https://example.com` gaf:
  - `status`: `browser_observed`
  - browser action uitgevoerd: `true`
  - DiffView aanwezig: `true`

## Tool Registry

Toegevoegd:

- `controller/agent_tools.py`
- `controller/self_training.py`

Beschikbare tools:

- `memory_search(query)`
- `browser_research(query, approval)`
- `chatgpt_browser_ask(question, approval)`
- `scrub_browser_content(content)`
- `training_ingest(content, source, approval, target_hz)`
- `safe_shell(command, approval)`
- `prompt_understanding(prompt)`
- `self_training_plan(goal)`
- `inspect_hippocampus(limit)`
- `run_tests(selector, approval)`

Elke tool geeft een JSON-envelope terug met:

- `status`
- `tool_name`
- `stdout`
- `stderr`
- `result`
- `source`
- `approval_status`
- `stored_to_memory`
- `metadata_11d`
- `next_action`

Belangrijk:

- Oude/fictieve toolnamen zoals `training_preview`, `training_approve` en `train_cycle` zijn uit de mentorlaag gehaald.
- `/agent/train-cycle` routeert nu naar echte `training_ingest`.
- Toolresultaten worden zichtbaar in UI en teamgesprek.

## Safe Shell

Toegevoegd:

- `controller/safe_shell.py`

Gedrag:

- Vereist exact `Akkoord`.
- Draait in `/workspace`.
- Alleen whitelist-commando's.
- Shell operators, redirection en substitutie worden geblokkeerd.
- `git push`, `sudo`, `rm`, `chmod`, `chown`, `wget`, `curl | sh` en unrestricted Docker-acties zitten niet in de UI-shell.
- stdout/stderr/exit_code komen terug in UI en tool-resultaat.

Rooktest:

- `safe_shell("ls", "Akkoord")` gaf `status=success` en zichtbare stdout.

## 11D Geheugen En Geometrie

Toegevoegd:

- `controller/stream/geometry_11d.py`

Exacte functie:

```python
def bereken_11d_bol(radius):
    teller_constante = 64 * math.pi**5
    noemer_volume = 10395
    noemer_oppervlakte = 945
    volume = (teller_constante / noemer_volume) * (radius**11)
    oppervlakte = (teller_constante / noemer_oppervlakte) * (radius**10)
    return volume, oppervlakte
```

Aanvullend:

- `measure_geometry_11d(value)` accepteert radius, frequentie of 11D-vector.
- 418-432 Hz wordt naar een 11D-radius gemapt.
- Training records krijgen:
  - `geometry_11d_available`
  - `geometry_11d_radius`
  - `geometry_11d_volume`
  - `geometry_11d_oppervlakte`
  - `geometry_11d_source`

Rooktest:

- Training ingest met `target_hz=432.0` is opgeslagen in ChromaDB.
- Resultaat bevatte 11D volume en oppervlakte.

## ChromaDB Hippocampus

Aangepast:

- `controller/api/training_routes.py`
- `controller/stream/storage.py`

Gedrag:

- Browser/training data gaat door:
  `Observe -> Scrub -> DiffView -> Akkoord -> 11D ChromaDB -> Reflect`
- Training records krijgen 11D metadata plus 11D geometrie.
- Huidige runtime-status na rooktests: ongeveer `152` gecombineerde records in hoofd- en trainingcollecties.

## Multi-Ollama Mentoren

Aangepast:

- `controller/virtual_team.py`
- `controller/ollama_client.py`

Mentorrollen:

- Developer
- Researcher
- Critic
- Trainer
- Tester

Gedrag:

- Mentoren krijgen de Ouroboros-trainingcontext.
- Mentoren krijgen de echte registry-tool lijst.
- Mentoren mogen geen fictieve tools of commando's verzinnen.
- Researcher gebruikt memory first.
- Trainer gebruikt `training_ingest`.
- Tester gebruikt `run_tests`.
- Developer gebruikt `safe_shell` alleen na `Akkoord`.
- Ollama modelselectie gebruikt beschikbare lokale modellen en vermijdt oude 404 modelnamen.

## UI

Aangepast:

- `WintripAI_IDE.html`

De UI toont nu:

- Ouroboros model online/offline
- actieve Ollama basis
- browser research status
- DiffView
- prompt-injection flags
- 11D volume/oppervlakte
- Hippocampus record count
- stdout/stderr van tools
- laatste tool-call
- wat Ouroboros net leerde
- mentor en `next_action`
- autonomie/status op basis van toolgebruik

Knoppen zijn gekoppeld aan echte endpoints:

- Create/Refresh Ouroboros Model
- Research Missing Knowledge
- Ask ChatGPT in Browser
- Preview Ingest
- Akkoord + Store in 11D Memory
- Safe Shell
- Run Tests
- Inspect Hippocampus
- Self-Training Step
- Laat Team Verbeteren

UI URL:

```text
http://localhost:3000/WintripAI_IDE.html?backend=http://localhost:8010
```

## Docker Runtime

Container:

- `wintrip-standalone-ui`

Poorten:

- UI: `3000`
- backend: `8010`

Gevalideerd:

- `GET /health`
- `GET /models`
- `GET /api/ouroboros/status`
- `POST /api/ouroboros/model/create-flow`
- `POST /browser/scrub`
- `POST /api/ouroboros/training/ingest`
- `POST /agent/tool` met `safe_shell`
- `POST /api/ouroboros/research/browser`

## Tests

Uitgevoerd in Docker:

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
Ran 45 tests in 1.283s
OK
```

## Eerlijke Grenzen

- `ouroboros` is voorbereid als Ollama modelidentiteit, maar staat pas `online` wanneer `ollama create ouroboros` echt is uitgevoerd en Ollama het model rapporteert.
- Er is nog geen echte fine-tuning of weight update gedaan.
- Browsergebruik is bewust beperkt tot approval-gated, een-pagina observaties.
- ChatGPT-browseractie werkt alleen als de browser/ChatGPT omgeving beschikbaar is en Philip `Akkoord` geeft.
- `.vscode/`, `gordon_progress.log`, `ouroboros_proto1/` en losse prompt-scratch blijven buiten deze commit.

## Volgende Stap

1. In de UI `Akkoord` typen.
2. `Create/Refresh Ouroboros Model` klikken om `ouroboros` lokaal in Ollama aan te maken.
3. `Research Missing Knowledge` gebruiken voor echte browserobservatie.
4. DiffView beoordelen.
5. `Akkoord + Store in 11D Memory` gebruiken om goedgekeurde kennis naar ChromaDB te schrijven.
6. Daarna pas LoRA/dataset/fine-tune flow ontwerpen voor echte weight training.
