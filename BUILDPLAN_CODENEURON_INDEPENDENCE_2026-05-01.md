# Buildplan: CodeNeuron, Curricula and Ouroboros Independence
**Date**: 2026-05-01
**Branch**: `feature/codex-agent-codeneuron-independence-20260501`

## Goal
Make the 11D pocket easier to understand, feed Ouroboros with structured knowledge tracks, and measure when the system can operate without an external model.

## 1. CodeNeuron Integration
Add a read-only integration for `/home/pwintri2/CodeNeuron/`.

Planned modules:
- `controller/codeneuron_adapter.py`
- `controller/codeneuron_ontology.py`

Index targets:
- `docs/`
- `coreneuron/`
- `tests/`
- `CMake/`

11D pocket mapping:
- e-type / neuron activation
- mechanisms and ion channels
- network events
- simulation timestep
- memory layout and SoA padding
- MPI / parallelism
- GPU offload
- binary IO and checkpointing
- model parameters
- hardware/runtime constraints
- validation and tests

## 2. Learning Curricula
Split learning into visible curriculum tracks:
- `general`: approved general knowledge and summaries
- `programming`: Python, TypeScript, C++, CMake, shell, SQL, repo-specific coding
- `local_machine`: Pop!_OS, hardware, software, Docker, Ollama, toolchains
- `popos`: System76/Pop!_OS desktop, power, firmware and user-space specifics
- `linux_internals`: systemd, cgroups, namespaces, seccomp, eBPF, VFS and kernel diagnostics
- `operating_systems`: Linux fundamentals, process model, filesystems, memory, networking, containers
- `google_workspace`: Google Account, Gmail, Drive, Calendar, Workspace and GCP/API concepts
- `microsoft_365`: Windows, Microsoft 365, Entra ID, Azure, Graph and Power Platform
- `sharepoint`: SharePoint architecture, permissions, content management, Graph, PnP and migration
- `agentic_tooling`: browser calls, approval gates, self-extension, tool use and long-term memory
- `codeneuron`: CoreNEURON concepts mapped into the 11D pocket
- `ouroboros_self`: self-extension, tool use, memory and local autonomy

Planned module:
- `controller/training_curriculum.py`

## 2B. Knowledge Acquisition From Local List
Use `/home/pwintri2/Downloads/OUROBOROS_KENNIS_LIJST.md` as a traceable acquisition plan.

Implemented module:
- `controller/knowledge_acquisition.py`

Capabilities:
- Parses the Markdown file into sections and topics.
- Runs bounded local Gemma/Ollama distillation per topic. This is not a literal extraction of model weights or every latent fact from Gemma; it is topic-by-topic teachable output from `gemma4:latest`.
- Runs bounded browser-call research through the existing Playwright perimeter, one page per topic, no result-click crawling and no bulk scraping.
- Stores approved records in `wintrip_training_11d` with source, source type, approval status, model/browser evidence and curriculum labels.
- Writes runtime state to `.secrets/knowledge_acquisition.json`.

API endpoints:
- `GET /trainer/knowledge/status`
- `POST /trainer/knowledge/index-list`
- `POST /trainer/knowledge/tick`

## 3. Local Machine Profiler
Add a read-only profiler that records:
- OS release and kernel
- CPU, RAM, disk
- GPU when available
- Docker containers/images
- Python, Node, npm, git versions
- Ollama status and local models

Planned module:
- `controller/local_machine_profile.py`

## 4. Independence Meter
Add `controller/ouroboros_independence.py`.

Signals:
- local inference availability
- local model quality on fixed prompts
- tool-use ability
- coding/test ability
- learning loop health
- self-extension gap handling
- validation and recovery
- curriculum coverage

Labels:
- `external_dependent`
- `local_assisted`
- `local_useful`
- `self_extending_with_approval`
- `mostly_independent`
- `independent_candidate`

## 5. UI
Add Trainer tab panels for:
- CodeNeuron status
- 11D Pocket Map
- curriculum coverage
- local machine profile
- independence score
- capability gaps and self-extension plans

## 6. Validation
Planned tests:
- `sandbox_tests/test_codeneuron_adapter.py`
- `sandbox_tests/test_training_curriculum.py`
- `sandbox_tests/test_local_machine_profile.py`
- `sandbox_tests/test_ouroboros_independence.py`

Docker validation:

```bash
python -m unittest \
  sandbox_tests.test_codeneuron_adapter \
  sandbox_tests.test_training_curriculum \
  sandbox_tests.test_local_machine_profile \
  sandbox_tests.test_ouroboros_independence
```

## Current Safety Rule
Ouroboros may detect missing capabilities and write self-extension plans. Applying code changes remains approval-gated and validated in Docker first.

## Implementation Status
Implemented on `feature/codex-agent-codeneuron-independence-20260501`.

Backend modules added:
- `controller/codeneuron_adapter.py`: read-only CodeNeuron scanner and compact JSON index.
- `controller/codeneuron_ontology.py`: canonical 11D pocket map and source matching.
- `controller/training_curriculum.py`: expanded curriculum labels and coverage scoring.
- `controller/knowledge_acquisition.py`: OUROBOROS_KENNIS_LIJST topic planner, Gemma distillation, browser-call acquisition and approved Chroma training storage.
- `controller/local_machine_profile.py`: approval-gated read-only runtime snapshot.
- `controller/ouroboros_independence.py`: transparent independence score with signal breakdown.

Trainer API endpoints added:
- `GET /trainer/codeneuron/status`
- `POST /trainer/codeneuron/index`
- `GET /trainer/codeneuron/pocket-map`
- `GET /trainer/codeneuron/search?q=...`
- `GET /trainer/curriculum/status`
- `GET /trainer/knowledge/status`
- `POST /trainer/knowledge/index-list`
- `POST /trainer/knowledge/tick`
- `GET /trainer/local-machine/status`
- `POST /trainer/local-machine/snapshot`
- `GET /trainer/independence/status`

React Trainer-tab panels added:
- CodeNeuron status, index and search.
- 11D Pocket Map cards with source counts.
- Curriculum coverage.
- Local Machine snapshot status.
- Independence score, external-model-needed indicator and current gaps.

Rotating Blue Brain update:
- The 11D pocket rotation loop now supports `cpu_clock_mode`.
- Clock mode decouples lightweight orthogonal 11D rotations from heavier RandomForest training.
- Rotation cadence is derived from detected CPU clock (`cpu_clock_hz / clock_divisor`) and capped by `max_rotation_hz`.
- Training is sampled every `train_every_rotations`, so the pocket can spin fast while model updates remain bounded.
- Live Docker configuration after the update: `cpu_clock_mode=true`, `max_rotation_hz=20000`, `clock_divisor=100000`, `train_every_rotations=10000`.

Streaming Consciousness 11D update:
- Incorporated `/home/pwintri2/Downloads/streaming_consciousness_11d_pocket.py` as `controller/streaming_consciousness_adapter.py`.
- Adds a bounded runtime loop for electrical membrane state, digital byte-stream encoding and DHCP/TCP-like network flow.
- Exposes live status, tick, start/stop and 17-feature dataset export endpoints.
- Trainer UI now has a Streaming Consciousness 11D panel with steps, DHCP/IP, voltage, bytes, packets and projection sample.
- Live Docker configuration after the update: `steps_per_tick=25`, `interval_seconds=0.2`, `n_samples=8000`, with DHCP reaching `BOUND`.

Quantum 11D collapse update:
- Incorporated the mathematical core from `Quantum.py` into `controller/streaming_consciousness_adapter.py`.
- Uses NumPy-only complex matrices, not Qiskit/Cirq or physical quantum SDKs.
- Defines Pauli `sigma_x`, `sigma_z`, B0/B1 phase operators, tensor product helper and Born expectation helper.
- Every streaming 11D event now passes through `trigger_quantum_collapse()` before being returned/exported.
- The event includes `quantum.expectation`, operator metadata and `sdk=none_numpy_classical` for auditability.

Docker validation on 2026-05-01:

```bash
python -m unittest \
  sandbox_tests.test_codeneuron_adapter \
  sandbox_tests.test_training_curriculum \
  sandbox_tests.test_local_machine_profile \
  sandbox_tests.test_ouroboros_independence
```

Result: `Ran 6 tests in 0.615s - OK`.

Additional Docker validation:

```bash
python -m unittest \
  sandbox_tests.test_trainer_pipeline_blue_brain \
  sandbox_tests.test_rotating_blue_brain \
  sandbox_tests.test_codex_registry \
  sandbox_tests.test_codex_agent
```

Result: `Ran 11 tests in 2.068s - OK`.

```bash
python -m unittest sandbox_tests.test_tauri_backend_routes
```

Result: `Ran 8 tests in 0.122s - OK`.

Live Docker evidence:
- Backend container: `wintrip-standalone-ui`.
- Backend URL: `http://localhost:8010`.
- CodeNeuron mount: `/codeneuron` read-only.
- Real CodeNeuron index: 191 files, 30,537 lines, all 11 pocket dimensions matched.
- Local machine snapshot currently has `environment.scope=docker_container`; it is honest about the Docker runtime and does not pretend to be a full Pop!_OS host inventory.
- React dev URL: `http://localhost:1420`.
