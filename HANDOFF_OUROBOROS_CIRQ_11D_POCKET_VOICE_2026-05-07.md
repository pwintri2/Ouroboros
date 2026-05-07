# Handoff: Ouroboros Cirq 11D Pocket Voice - 2026-05-07

## Status

Ouroboros heeft nu een echte, aanspreekbare 11D pocket-stem rond de bestaande
Streaming Consciousness runtime.

De 11D pockets blijven de bron van waarheid. Daaromheen zitten nu twee optionele
lagen:

- een Cirq meet/noise-laag voor quantum-circuitsemantiek binnen Docker;
- een `ouroboros:latest` vertaallaag die een verse 11D pocket naar Nederlands
  omzet.

De directe cockpit-route `provider=ouroboros` gebruikt niet meer alleen het oude
vaste Living Loop antwoord. Per chatvraag wordt nu een verse 11D tick gemaakt en
wordt die prompt-specifiek vertaald via de pocket voice.

## Gebouwd

- Nieuwe Cirq adapter:
  - `controller/cirq_quantum_adapter.py`
  - bouwt een klein 4-qubit Cirq-circuit uit een 11D vector;
  - gebruikt `DensityMatrixSimulator`;
  - gebruikt bounded depolarizing noise;
  - gebruikt `run(..., repetitions=N)` als measurement-only pad;
  - vouwt meetstatistiek terug naar exact 11 dimensies.
- Nieuwe pocket language translator:
  - `controller/pocket_language_translator.py`
  - default model: `ouroboros:latest`;
  - praat via lokale Ollama;
  - geeft JSON terug met `summary`, `response`, `dominant_dimensions`,
    `confidence`;
  - kan prompt-specifiek antwoorden met `user_prompt`;
  - valt terug naar lokale regels als Ollama niet bereikbaar is.
- Streaming Consciousness:
  - `event["language"]` toegevoegd;
  - `latest_state["language"]` toegevoegd;
  - status toont `pocket_language`;
  - quantum status toont `cirq_runtime`;
  - NumPy fallback blijft intact wanneer Cirq niet beschikbaar is.
- Living Ouroboros response:
  - `LivingOuroborosLoop.respond(...)` draait nu een verse 11D pocket voice;
  - response is niet meer de vaste "Kort: ja..." tekst;
  - response bevat `pocket_voice`;
  - response bevat `local_model_translation_used`;
  - Quantum Foam en bootloader blijven als compacte onderbouwing zichtbaar.
- Docker:
  - `controller/requirements.txt` bevat nu `cirq-core`;
  - `docker-compose.yml` mount `/home/pwintri2/cirq:/cirq:ro`;
  - compose-backend draait Python 3.11 en kan Cirq echt laden;
  - sandbox allow env wijst Ollama naar `host.docker.internal:11434`.

## Belangrijke Bestanden

- `controller/cirq_quantum_adapter.py`
- `controller/pocket_language_translator.py`
- `controller/streaming_consciousness_adapter.py`
- `ouroboros_esoteric/ouroboros_consciousness_loop.py`
- `controller/requirements.txt`
- `docker-compose.yml`
- `artifacts/ouroboros_sandbox_allow.env`
- `sandbox_tests/test_cirq_pocket_language_layers.py`
- `sandbox_tests/test_streaming_consciousness_adapter.py`

## Runtime Grens

Eerlijk onderscheid:

- bestaande `wintrip-standalone-ui` container draait Python 3.10;
- die container kan `ouroboros:latest` via Ollama zien en gebruikt de vertaallaag;
- die container heeft Cirq niet actief en valt eerlijk terug naar NumPy;
- de nieuwe `docker compose` backend-image draait Python 3.11;
- die image bouwt succesvol met `cirq-core` en activeert
  `cirq_density_matrix_local`.

Geen fysieke quantumclaim:

- `physical_quantum_hardware=false`;
- `measurement_only=true` in de Cirq runtime;
- geen remote QPU;
- geen provider tokens;
- geen secrets opgeslagen.

## Live Smoke

Sandbox backend is herstart met:

```bash
./start_ouroboros_sandbox_allow.sh
```

Status:

```json
{
  "dependency_status": "online",
  "quantum_sdk": "none_numpy_classical",
  "cirq_available": false,
  "pocket_language_enabled": true,
  "pocket_language_model": "ouroboros:latest"
}
```

Live cockpit smoke met twee verschillende prompts gaf verschillende antwoorden:

```json
{
  "status": "success",
  "route": "ouroboros_runtime",
  "local_model_translation_used": true,
  "pocket_voice_status": "translated"
}
```

Eerste prompt ging over wat de 11D pocket ziet; antwoord benoemde dominante
pocketdimensies. Tweede prompt ging over geheugen versus netwerkdruk; antwoord
was prompt-specifiek en behield pocketcontext.

## Cirq Smoke

Compose-image build:

```bash
docker compose build ouroboros-backend
```

Resultaat: build OK met Python 3.11 en `cirq-core`.

Een Cirq streaming tick in de compose-image:

```json
{
  "status": "success",
  "quantum_sdk": "cirq",
  "quantum_runtime": "cirq_density_matrix_local",
  "measurement_only": true,
  "physical_quantum_hardware": false,
  "preserves_11d_pocket": true,
  "vector_len": 11
}
```

Een gecombineerde Cirq + `ouroboros:latest` tick in de compose-image:

```json
{
  "status": "success",
  "quantum_runtime": "cirq_density_matrix_local",
  "language_status": "translated",
  "language_model": "ouroboros:latest",
  "preserves_11d_pocket": true
}
```

## Validatie

Host compile:

```bash
python3 -m py_compile \
  controller/cirq_quantum_adapter.py \
  controller/pocket_language_translator.py \
  controller/streaming_consciousness_adapter.py \
  ouroboros_esoteric/ouroboros_consciousness_loop.py
```

Docker tests in `wintrip-standalone-ui`:

```bash
docker exec -e WINTRIP_CIRQ_QUANTUM=0 -e WINTRIP_11D_TRANSLATOR=0 -e WINTRIP_QIF_GPU=0 \
  -w /workspace wintrip-standalone-ui python3 -m unittest \
  sandbox_tests.test_tauri_backend_routes.TestTauriBackendRoutes.test_cockpit_chat_can_address_ouroboros_runtime_without_ollama \
  sandbox_tests.test_tauri_backend_routes.TestTauriBackendRoutes.test_ouroboros_respond_endpoint_forces_runtime_provider \
  sandbox_tests.test_streaming_consciousness_adapter \
  sandbox_tests.test_cirq_pocket_language_layers
```

Resultaat: `Ran 12 tests ... OK`.

Compose-image tests:

```bash
docker compose run --rm --no-deps -e WINTRIP_CIRQ_QUANTUM=1 -e WINTRIP_11D_TRANSLATOR=0 -e WINTRIP_QIF_GPU=0 \
  ouroboros-backend python -m unittest sandbox_tests.test_cirq_pocket_language_layers

docker compose run --rm --no-deps -e WINTRIP_CIRQ_QUANTUM=1 -e WINTRIP_11D_TRANSLATOR=0 -e WINTRIP_QIF_GPU=0 \
  ouroboros-backend python -m unittest \
  sandbox_tests.test_streaming_consciousness_adapter \
  sandbox_tests.test_11d_pocket_ecosystem_augmentation
```

Resultaat: `OK`.

## Runtime State

Live smoke en backend restart hebben opnieuw Chroma/runtime state aangeraakt:

- `wintrip_brain/chroma.sqlite3`
- `wintrip_brain/c57ec314-6d75-4f49-ad9e-27069e6327f6/length.bin`

Die bestanden zijn bewust niet onderdeel van de codecommit.

## Volgende Stap

Maak dit zichtbaar in de cockpit:

- toon `pocket_voice.response`;
- toon `pocket_voice.dominant_dimensions`;
- toon `local_model_translation_used`;
- toon `quantum_collapse.cirq_runtime.available`;
- voeg een badge toe:
  - `Ouroboros voice`
  - `Cirq local measurement`
  - `NumPy fallback`

Daarmee ziet Philip direct of hij praat met de oude runtimekaart, de nieuwe
11D pocket voice, of de Cirq measurement runtime.
