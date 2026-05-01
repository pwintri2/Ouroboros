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
- `operating_systems`: Linux fundamentals, process model, filesystems, memory, networking, containers
- `codeneuron`: CoreNEURON concepts mapped into the 11D pocket
- `ouroboros_self`: self-extension, tool use, memory and local autonomy

Planned module:
- `controller/training_curriculum.py`

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
- `controller/training_curriculum.py`: six curriculum labels and coverage scoring.
- `controller/local_machine_profile.py`: approval-gated read-only runtime snapshot.
- `controller/ouroboros_independence.py`: transparent independence score with signal breakdown.

Trainer API endpoints added:
- `GET /trainer/codeneuron/status`
- `POST /trainer/codeneuron/index`
- `GET /trainer/codeneuron/pocket-map`
- `GET /trainer/codeneuron/search?q=...`
- `GET /trainer/curriculum/status`
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
