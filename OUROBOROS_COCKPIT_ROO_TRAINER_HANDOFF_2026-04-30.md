# Ouroboros Cockpit + Roo/Trainer Handoff

Datum: 2026-04-30
Laatste snapshotbranch: `codex/wintripai-roo-ui-core-snapshot-20260501-0030`
Oorspronkelijke cockpitbranch: `codex/ouroboros-cockpit-roo-trainer-20260430`
Repo: `/home/pwintri2/WintripAI`

## Status

De primaire UI is nu de native Tauri/React cockpit in `ouroboros_cockpit/`.
De oude `WintripAI_IDE.html` blijft legacy en mag niet opnieuw de hoofdinterface worden.

## Werkbasis En Bestandslocaties

Werk altijd vanuit:

```text
/home/pwintri2/WintripAI
```

Canonieke projectdelen:

```text
/home/pwintri2/WintripAI/ouroboros_cockpit/     primaire mooie Tauri/React UI
/home/pwintri2/WintripAI/controller/            FastAPI backend, tools, routers, trainer adapters
/home/pwintri2/WintripAI/sandbox_tests/         backend/unit/sandbox tests
/home/pwintri2/WintripAI/resonant_ouroboros/    Fase 1/Awake Keeper modules
/home/pwintri2/WintripAI/Modelfile.ouroboros    lokale Ollama modelidentiteit
/home/pwintri2/WintripAI/wintrip_brain/         lokale ChromaDB state; niet committen
/home/pwintri2/WintripAI/.secrets/              lokale API keys; nooit committen
```

Externe bronmappen voor de volgende bouwfase:

```text
/home/pwintri2/Roo       Roo Code bron voor tool/mode/task lifecycle inventaris
/home/pwintri2/litgpt    LitGPT bron en CLI/tutorials voor LoRA/QLoRA jobs
/home/pwintri2/unsloth   Unsloth bron voor snelle SFT/LoRA/GGUF/Ollama export
```

Eerst te bouwen/configureren bestanden in `controller/`:

```text
controller/roo_manifest.py
controller/project_context.py
controller/trainer_jobs.py
controller/training_dataset_builder.py
controller/litgpt_adapter.py
controller/unsloth_adapter.py
controller/model_artifacts.py
```

De cockpit-uitbreiding hoort in:

```text
ouroboros_cockpit/src/App.tsx
ouroboros_cockpit/src/styles.css
```

Behoud de bestaande React/Tauri cockpit als hoofd-UI. De visuele layout, providerkeuze, statusstrip, terminal, approval-paneel, 11D memory en API-key beheer moeten intact blijven. Voeg alleen nieuwe Roo/Trainer panels toe rond de bestaande structuur; vervang de cockpit niet door `WintripAI_IDE.html` of een losse webpagina.

## Docker-First En Deploy-Gate

- Ontwikkel en test eerst Docker-contained of via de bestaande safe shell perimeter.
- Nieuwe trainer-commando's moeten via `controller/safe_shell.py`, Docker exec, of een expliciet job-runner pad in `/workspace` lopen.
- Installeer geen persistente packages op de host als default route.
- Draai geen `docker compose up`, deployment, langdurige trainer-job, Ollama model create, of public service start zonder expliciete toestemming.
- De vereiste toestemmingstekst voor deploy blijft exact:

```text
JA, deploy nu
```

- Voor die toestemming mag alleen worden voorbereid: code, config, tests, Dockerfile/compose wijzigingen, dry-runs, command previews en job previews.

## Pipeline Configuratie

De Roo/LitGPT/Unsloth pipeline moet job-based en eerlijk geconfigureerd worden:

```text
draft -> approved -> dataset_ready -> training -> validating -> exporting -> ollama_create -> online
```

Foutpad:

```text
failed
```

Statusregels:

- `self_modification_pipeline.status=configured` pas zetten nadat Roo manifest, context engine, preview/apply/test flow en endpoints bestaan.
- `fine_tune.status=success` of `completed` pas zetten na een echte LitGPT of Unsloth job met artifact registratie.
- `model.online=true` pas zetten nadat Ollama inventory het model echt rapporteert.
- Datasetbouw mag alleen uit goedgekeurde 11D records of expliciete snapshots met exact `Akkoord`.
- Browserdata blijft `UNTRUSTED` tot scrubbed, previewed en goedgekeurd.
- ChromaDB binary state, model weights, GGUFs, LoRA artifacts en secrets horen niet in commits; registreer alleen metadata en relatieve artifact paths.

Runtime:

```bash
cd /home/pwintri2/WintripAI/ouroboros_cockpit
npm run tauri -- dev
```

Backend:

```text
http://localhost:8010
```

Cockpit dev URL:

```text
http://127.0.0.1:1420/
```

## Wat Nu Echt Werkt

- Tauri v2 desktop-shell met React cockpit.
- Dynamische lokale Ollama modelkeuze uit `/api/cockpit/config`.
- Externe providers zijn zichtbaar, maar alleen enabled als er echt een API key is opgeslagen of via env bestaat.
- API key beheer:
  - `GET /api/cockpit/api-keys`
  - `POST /api/cockpit/api-keys`
  - Vereist exact `Akkoord`.
  - Secrets worden lokaal opgeslagen in `.secrets/ouroboros_api_keys.json` of `WINTRIP_API_KEY_STORE`.
  - Raw keys worden nooit teruggegeven aan de UI.
- Roo adapters:
  - `roo_read_file`
  - `roo_list_files`
  - `roo_search_files`
  - `roo_write_file_preview`
  - `roo_write_file`
  - `roo_apply_patch_preview`
  - `roo_apply_patch`
  - `roo_execute_command`
  - `roo_attempt_completion`
  - `roo_ask_followup_question`
- Safe shell:
  - `POST /sandbox/shell`
  - exact `Akkoord`
  - `/workspace`
  - stdout/stderr/exit_code terug naar UI.
- Loop endpoints:
  - `GET /api/ouroboros/loop/status`
  - `POST /api/ouroboros/loop/start`
  - `POST /api/ouroboros/loop/pause`
  - `POST /api/ouroboros/loop/abort`

## Validatie

Laatste groene checks:

```bash
npm --prefix ouroboros_cockpit run build
```

```bash
WINTRIP_WORKSPACE=/home/pwintri2/WintripAI python3 -c "import json; from controller.safe_shell import run_safe_shell; result = run_safe_shell('python3 -m unittest sandbox_tests.test_tauri_cockpit_files sandbox_tests.test_tauri_backend_routes sandbox_tests.test_multi_api_router sandbox_tests.test_api_key_store sandbox_tests.test_external_provider_isolation sandbox_tests.test_safe_shell', approval='Akkoord', timeout=30); print(json.dumps(result, indent=2, ensure_ascii=False))"
```

## Belangrijke Waarheden

- `model.online=false` betekent dat Ollama het model `ouroboros` nog niet rapporteert.
- Dit is geen fine-tune.
- De cockpit heeft nu een echte `Create/Refresh` knop voor de Ollama modelidentiteit.
- Een echte trainer-pipeline moet pas `fine_tune.status=success` tonen nadat LitGPT of Unsloth daadwerkelijk een job heeft voltooid en een artifact is geregistreerd.
- Browserdata blijft `UNTRUSTED` tot scrubbed en goedgekeurd met `Akkoord`.
- ChromaDB binary state mag niet zomaar in commits.

## Build Plan: Roo Dieper Integreren

1. Roo Capability Inventory
   - Lees `/home/pwintri2/Roo/` en maak een manifest van commands, prompts, file tools, diff tools en task lifecycle.
   - Voeg `controller/roo_manifest.py` toe met read-only introspectie.
   - Expose `GET /api/roo/status` en `GET /api/roo/tools`.

2. Project Context Engine
   - Voeg `controller/project_context.py` toe.
   - Bouw file graph, symbol hints, test hints en recent git diff context.
   - Gebruik `rg`, `git diff`, `git ls-files` via safe_shell of read-only Python APIs.
   - UI: nieuwe Cockpit tab `Context` met project files, changed files en tool availability.

3. Multi-file Editing Pipeline
   - Houd preview verplicht.
   - Route Roo write/apply tools via `roo_write_file_preview` en `roo_apply_patch_preview`.
   - Alleen exact `Akkoord` mag naar `roo_write_file` of `roo_apply_patch`.
   - Na write: automatisch safe_shell tests draaien als de gebruiker dat aanvinkt.
   - stdout/stderr/exit_code direct terug naar agent trace en cockpit feed.

4. Roo Agent Lifecycle
   - Implementeer job states: `observe`, `plan`, `patch_preview`, `approval`, `apply`, `test`, `reflect`, `store_11d`.
   - Geen fake completion: `roo_attempt_completion` mag alleen status `success` betekenen als de verificatiestap groen is of expliciet als menselijke eindmelding is gemarkeerd.

## Build Plan: LitGPT + Unsloth Trainer Pipeline

Bronnen:

```text
/home/pwintri2/litgpt
/home/pwintri2/unsloth
```

Relevant uit LitGPT:

- `litgpt/__main__.py` exposeert CLI commands zoals `finetune`, `finetune_lora`, `finetune_full`, `merge_lora`, `generate`, `serve`, `validate`.
- `litgpt/api.py` bevat `LLM.load`, generation en trainer setup.
- `litgpt/tutorials/finetune_lora.md` en verwante tutorials zijn de implementatiegids.

Relevant uit Unsloth:

- `unsloth/trainer.py` bevat `UnslothTrainer`, `UnslothTrainingArguments`, SFTTrainer integratie en Q-GaLore config.
- `unsloth/save.py` bevat GGUF/llama.cpp/Ollama export paden en quantization presets.
- `unsloth/ollama_template_mappers.py` bevat Ollama template mapping.

Fases:

1. Trainer Job Model
   - Voeg `controller/trainer_jobs.py` toe.
   - Persistent job registry in lokale JSON/SQLite, geen Chroma binary commit.
   - States: `draft`, `approved`, `dataset_ready`, `training`, `validating`, `exporting`, `ollama_create`, `online`, `failed`.

2. Dataset Builder
   - Voeg `controller/training_dataset_builder.py` toe.
   - Alleen goedgekeurde 11D records gebruiken: `approval_status=approved`.
   - Export JSONL met prompt/completion/chat format.
   - Metadata bevat geometry_11d radius/volume/oppervlakte, source, taint en content hash.

3. LitGPT Adapter
   - Voeg `controller/litgpt_adapter.py` toe.
   - Eerste target: LoRA fine-tune via `python -m litgpt finetune_lora ...`.
   - Alles via safe_shell of Docker exec in `/workspace`.
   - Capture stdout/stderr/exit_code in trainer job.
   - `merge_lora` alleen na succesvolle training.

4. Unsloth Adapter
   - Voeg `controller/unsloth_adapter.py` toe.
   - Eerste target: SFT/LoRA trainer met 4-bit pad wanneer GPU beschikbaar is.
   - Export naar GGUF via Unsloth save pipeline.
   - Ollama Modelfile genereren met template mapper waar mogelijk.

5. Artifact Registry
   - Voeg `controller/model_artifacts.py` toe.
   - Registreer adapter path, merged checkpoint, GGUF path, Modelfile path, Ollama model name en test result.
   - Nooit `model.online=true` zetten zonder Ollama inventory check.

6. Cockpit Trainer Tab
   - Behoud bestaande cockpit.
   - Voeg tab/pane toe voor:
     - dataset preview
     - trainer backend keuze: LitGPT of Unsloth
     - base model
     - LoRA params
     - start/pause/abort
     - logs
     - artifact status
     - `Create Ollama Model`

7. Acceptance Criteria
   - `GET /api/ouroboros/status` toont:
     - `self_modification_pipeline.status=configured`
     - `fine_tune.status` alleen `success` na echte trainer job.
     - `model.online=true` alleen als Ollama het model rapporteert.
   - Safe shell logs bevatten alle trainer commands.
   - 11D Chroma krijgt alleen approved trainer summaries, geen raw secrets en geen fake weight claims.

## API Key Plan

Reeds geïmplementeerd:

- `controller/api_key_store.py`
- `/api/cockpit/api-keys`
- Cockpit API key paneel voor OpenAI, Anthropic, xAI, Mistral en Google.

Volgende uitbreiding:

- Per-provider model override in de UI.
- Key test knop per provider die een korte non-tool prompt stuurt.
- Audit event in 11D zonder secretwaarde: provider, source, masked suffix, timestamp.

## Handoff Voor Volgende Agent

Start hier:

1. Open de Tauri cockpit en behoud de huidige UI.
2. Controleer:
   - `/health`
   - `/api/cockpit/config`
   - `/api/ouroboros/status`
   - `/api/cockpit/api-keys`
3. Run:
   - `npm --prefix ouroboros_cockpit run build`
   - safe_shell unittest command hierboven.
4. Bouw eerst `trainer_jobs.py` en dataset preview voordat je LitGPT/Unsloth training start.
5. Claim geen online model of fine-tune success zonder echte artifact + Ollama inventory.
