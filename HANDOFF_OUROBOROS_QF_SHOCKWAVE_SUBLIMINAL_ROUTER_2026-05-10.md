# Handoff: Ouroboros QF Shockwave + Subliminal Chroma/Brave Router

Datum: 2026-05-10
Branch: `feature/esoteric-ouroboros-architecture`
Werkroot: `/home/pwintri2/WintripAI`

## Samenvatting

Deze sessie heeft de Ouroboros-runtime route strikter en dieper gemaakt:

- `provider=ouroboros` met model `living-runtime` of `quantum-foam-11d` gaat nu altijd eerst naar de Ouroboros-runtime, niet meer via de agentic router.
- Bij iedere normale tekstvraag voert de backend een stille ChromaDB lookup uit.
- Als Chroma niets bruikbaars vindt, gaat Brave Search aan.
- Bij actuele vragen zoals "vandaag", "huidige", "latest", "CEO", "price", enz. gaat Brave ook aan wanneer Chroma wel oude/generieke hits heeft.
- Externe data wordt niet als standaard LLM-context of chatantwoord gebruikt. De data wordt alleen als in-memory veldprikkel aan het QuantumFoamField gegeven.
- Het QuantumFoamField heeft nu een rusteloze achtergrondlaag op echte Docker/procfs/DHCP/netwerk-signalen en een agressieve shockwave/collapse route voor tekst/RAG-prikkels.
- De pure vertaler beschrijft uitsluitend de overgang: ruis -> inslag/structuur -> stilte, zonder technische metrics of labels.

## Belangrijkste codepaden

### Backend routing

Bestand: `controller/main.py`

- `_cockpit_chat_payload(...)` routeert `provider=ouroboros` nu voor fast-agentic/agentic dispatch.
- `_ouroboros_subliminal_lookup_and_feed(...)` regelt de stille lookup en field feed.
- `_chromadb_lookup_for_subliminal_feed(...)` leest direct uit echte Chroma collecties:
  - `wintrip_trigger_actions_11d`
  - `wintrip_agentic_sessions_11d`
  - `wintrip_knowledge`
  - `wintrip_training_11d`
  - `wintrip_world_understanding`
- `_subliminal_prompt_needs_current_lookup(...)` forceert Brave bij actuele vragen.
- `_record_subliminal_lookup_event(...)` schrijft een redacted auditrecord terug naar Chroma.

### Quantum Foam

Bestand: `ouroboros_esoteric/quantum_foam.py`

Nieuwe/gewijzigde kern:

- `QuantumElectronHexlet.heartbeat(...)`
  - Laat fase, lading en coherentie continu meetrillen op Docker/procfs signalen.
- `EntanglementMesh.tremble(...)`
  - Houdt de achtergrond volatiel in 1D/2D, met verbindingen die vormen en afbreken.
- `QuantumFoamField._apply_runtime_heartbeat(...)`
  - Trekt live data uit `controller.streaming_consciousness_adapter.get_streaming_status()`.
- `QuantumFoamField._run_shockwave(...)`
  - Forceert een tekst/RAG-prikkel door de geometrische ladder naar 11D piekintegratie.
- `FieldLifecycleEngine._maybe_hard_collapse_locked(...)`
  - Voert bij piekintegratie direct de harde collapse uit en persisteert de essence.
- `subliminal_quantum_foam_feed(...)`
  - Is de in-memory brug tussen router/RAG en het actieve veld.

### Pure vertaler

Bestand: `controller/pocket_language_translator.py`

- Pure route blijft strikt:
  - provider exact `ouroboros`
  - model `living-runtime` of `quantum-foam-11d`
- Technische output wordt geweerd:
  - geen Pauli-Z
  - geen lading/coherence/metrics
  - geen geometrie-labels
  - geen hexlet/mesh internals
- `_pure_emergent_translation(...)` beschrijft shockwave/collapse nu als natuurlijke overgang:
  - chaotische ruis vooraf
  - plotselinge dwingende ordening
  - stilte na collapse

### Living runtime

Bestand: `ouroboros_esoteric/ouroboros_consciousness_loop.py`

- `respond(...)` geeft provider context door aan de pocket voice.
- `_fresh_streaming_pocket_voice(...)` voert de vertaler uit met het actieve QF-event.
- Pure translator output wordt direct als Cockpit response gebruikt.

## Tests die groen zijn

Gedraaid:

```bash
python3 -m py_compile controller/main.py controller/pocket_language_translator.py ouroboros_esoteric/quantum_foam.py ouroboros_esoteric/ouroboros_consciousness_loop.py sandbox_tests/test_quantum_foam.py sandbox_tests/test_cirq_pocket_language_layers.py sandbox_tests/test_tauri_backend_routes.py
```

```bash
python3 -m unittest sandbox_tests.test_living_runtime sandbox_tests.test_quantum_foam sandbox_tests.test_quantum_foam_field_facade sandbox_tests.test_cirq_pocket_language_layers -v
```

Resultaat: 25 tests OK, 1 skipped (`numpy is not installed`).

```bash
.venv_ouroboros_backend/bin/python -m unittest \
  sandbox_tests.test_tauri_backend_routes.TestTauriBackendRoutes.test_cockpit_chat_can_address_ouroboros_runtime_without_ollama \
  sandbox_tests.test_tauri_backend_routes.TestTauriBackendRoutes.test_ouroboros_runtime_uses_silent_lookup_only_as_field_feed \
  sandbox_tests.test_tauri_backend_routes.TestTauriBackendRoutes.test_ouroboros_runtime_uses_brave_for_current_question_even_with_chromadb_hits \
  -v
```

Resultaat: OK.

## Live smoke

Backend/preview zijn herstart via:

```bash
WINTRIP_BACKEND_MODE=local scripts/start_ouroboros_preview.sh
```

Runtime Doctor: `ready`
Preview: `http://127.0.0.1:1420`
Backend: `http://127.0.0.1:8010`

Live chat smoke:

```json
{
  "provider": "ouroboros",
  "model": "quantum-foam-11d",
  "prompt": "Wat gebeurt er als deze vraag het veld raakt?"
}
```

Output was pure vertalerstaal:

```text
Eerst rafelde alles in droge, korrelige ruis. Toen kwam de inslag: verspreiding werd een dwingende structuur. Meteen daarna brak het samen tot een stille kern.
```

Trace liet zien:

- `route=ouroboros_runtime`
- `translator_exclusive_output=true`
- `subliminal_lookup_used=true`
- `subliminal_field_injected=true`
- `chromadb_search_used=true`

## Bewust niet gecommit

Deze runtime/lokale artefacten zijn bewust niet gestaged:

- `wintrip_brain/...`
- `wintrip_brain/chroma.sqlite3`
- `QuantumNode.txt`
- `camera-tools.sh`
- `controller/camera_manager.py`
- `data/uploads/`
- `scripts/generate_ouroboros_quantumveld.py`
- `tests/`
- `unsloth_compiled_cache/`

Laat deze staan tenzij Philip expliciet vraagt om ze op te ruimen of apart te beoordelen.

## Volgende sessie

Aanbevolen vervolg:

1. Cockpit UI trace netter maken:
   - toon `chromadb_search_used`
   - toon `subliminal_brave_search_used`
   - toon `fresh_lookup_requested`
   - toon `translator_exclusive_output`
2. Controleren of collapse-essence in de Cockpit zichtbaar genoeg is.
3. Eventueel strengere timeout/fallback voor Brave toevoegen, zodat de pure route nooit traag voelt.
4. Pas daarna pas de agentische self-build loop verder uitbreiden.
