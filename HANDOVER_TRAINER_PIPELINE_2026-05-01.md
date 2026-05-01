# Handover Report: Trainer Pipeline Integration
**Date**: 2026-05-01
**Branch**: `trainer-pipeline-integration`  
**Commit**: 2550e1a

## Summary
Integrated LitGPT and Unsloth training capabilities into the Ouroboros Cockpit UI. Added Trainer and Context tabs to both standalone HTML UI and React UI. Set up training environments and fixed backend routing issues.

## Work Completed

### 1. Backend Integration

#### New Files Created
- `controller/api/trainer_pipeline_routes.py` - FastAPI routes for trainer pipeline (status, jobs, dataset preview, job management)
- `controller/litgpt_adapter.py` - LitGPT integration adapter for fine-tuning
- `controller/unsloth_adapter.py` - Unsloth integration adapter for training
- `controller/trainer_jobs.py` - Training job state management
- `controller/training_dataset_builder.py` - Dataset building for training
- `controller/project_context.py` - Project context API
- `controller/model_artifacts.py` - Model artifact management
- `controller/roo_manifest.py` - Roo tool manifest integration

#### Modified Files
- `controller/main.py` - Registered new trainer pipeline routes
- Fixed Pydantic v2 error: changed `regex` to `pattern` in Field definition

### 2. Frontend Updates

#### Standalone UI (WintripAI_IDE.html)
- Added tab navigation (Main, Trainer, Context)
- Added Trainer panel showing LitGPT/Unsloth status, approved records, job list
- Added Context panel showing project context summary
- Wired API calls to fetch trainer/context data on tab change

#### React UI (ouroboros_cockpit/src/App.tsx)
- Added tab navigation (Main, Trainer, Context)
- Added TrainerPanel component with job creation and management
- Added ContextPanel component with file tree and context exploration
- Fixed CSS positioning for trainer/context panels
- Added useEffect to fetch data when tab changes

#### Styles (ouroboros_cockpit/src/styles.css)
- Added CSS for tab navigation buttons
- Added styling for trainer status grid, job list, dataset preview
- Added styling for context panel

### 3. Environment Setup

#### LitGPT
- Created virtual environment at `/workspace/.venv_litgpt`
- Installed LitGPT from pip (version 0.5.12)
- Copied source code to `/workspace/litgpt`
- Updated source path in `litgpt_adapter.py` to `/workspace/litgpt`

#### Unsloth
- Created virtual environment at `/workspace/.venv_unsloth`
- Installed Unsloth from git (version 2026.4.8)
- Copied source code to `/workspace/unsloth`
- Updated source path in `unsloth_adapter.py` to `/workspace/unsloth`

#### Container Configuration
- Installed git in Docker container for package installation
- Restarted backend to pick up path changes

### 4. Git Commit
- Created new branch: `trainer-pipeline-integration`
- Committed 12 files with 3003 insertions
- Excluded from commit: venv directories, sqlite databases, copied source directories

## Current Status

### Backend
- **LitGPT**: Online (venv exists, source available)
- **Unsloth**: Online (venv exists, source available)
- **Trainer Pipeline**: Configured and ready
- **Approved Dataset Records**: 0
- **Total Jobs**: 0

### Frontend
- **Standalone UI**: Running at http://localhost:3000/WintripAI_IDE.html
- **React UI**: Running at http://127.0.0.1:1420/
- Both UIs show Trainer and Context tabs with correct data

### API Endpoints
- `GET /trainer/status` - Get trainer pipeline status
- `GET /trainer/jobs` - List all training jobs
- `POST /trainer/jobs` - Create new training job
- `GET /trainer/dataset/preview` - Preview training dataset
- `GET /context/summary` - Get project context summary
- `GET /context/file-tree` - Get project file tree
- `GET /context/changed-files` - Get changed files

## Known Issues

### Path Configuration
- Source paths were originally set to `/home/pwintri2/litgpt` and `/home/pwintri2/unsloth`
- These paths don't exist inside the Docker container
- Fixed by updating paths to `/workspace/litgpt` and `/workspace/unsloth`
- Source directories were copied into container workspace

### Virtual Environment Persistence
- Virtual environments are created inside the container at `/workspace/.venv_litgpt` and `/workspace/.venv_unsloth`
- If container is recreated, venvs will need to be recreated
- Consider using persistent volumes or building venvs into a custom image

## Next Steps

### Immediate
1. Test creating a training job through the Trainer tab
2. Verify dataset preview functionality
3. Test job lifecycle (draft → approved → training → online)

### Future Improvements
1. Build custom Docker image with LitGPT and Unsloth pre-installed
2. Use persistent volumes for virtual environments
3. Add error handling for missing venvs
4. Add configuration for source paths instead of hardcoding
5. Implement dataset approval workflow
6. Add job monitoring and progress updates
7. Implement model artifact export to Ollama

## Configuration

### Backend
- **Backend URL**: http://localhost:8010
- **Container**: wintrip-standalone-ui
- **Volume Mount**: /home/pwintri2/WintripAI:/workspace

### Training Environments
- **LitGPT venv**: /workspace/.venv_litgpt
- **Unsloth venv**: /workspace/.venv_unsloth
- **LitGPT source**: /workspace/litgpt
- **Unsloth source**: /workspace/unsloth

### Frontend
- **Standalone UI**: Python http.server on port 3000
- **React UI**: Vite dev server on port 1420

## Testing Checklist
- [ ] Create training job via Trainer tab
- [ ] Preview dataset before training
- [ ] Approve training job
- [ ] Monitor training progress
- [ ] Export trained model to Ollama
- [ ] View job history
- [ ] Explore project context
- [ ] View changed files
- [ ] Test file tree navigation

## Notes
- The trainer pipeline uses "Akkoord" (Dutch for "approved") as the approval phrase for job creation
- Jobs require approval before training can start
- Dataset must be built and approved before training
- Model artifacts can be exported to Ollama for deployment

---

## Addendum: CodeNeuron, 11D Pocket and Independence Update
**Date**: 2026-05-01
**Branch**: `feature/codex-agent-codeneuron-independence-20260501`

### Summary
The Trainer tab has grown from a trainer/job surface into a live Ouroboros learning cockpit. It now includes a read-only CodeNeuron/CoreNEURON knowledge index, a visible 11D pocket map, six curriculum tracks, a local machine profiler, an independence score, Codex agent/registry panels, and a faster Blue Brain Rotating loop.

### New Backend Modules
- `controller/codeneuron_adapter.py`
  - Read-only scanner for `/home/pwintri2/CodeNeuron` or `/codeneuron` in Docker.
  - Indexes `docs/`, `coreneuron/`, `tests/`, and `CMake/`.
  - Writes compact runtime state to `.secrets/codeneuron_index.json`.
- `controller/codeneuron_ontology.py`
  - Defines the canonical 11D pocket dimensions.
  - Maps CodeNeuron source evidence to e-type/11D concepts.
- `controller/training_curriculum.py`
  - Adds curriculum labels: `general`, `programming`, `local_machine`, `operating_systems`, `codeneuron`, `ouroboros_self`.
  - Dataset exports now include curriculum metadata.
- `controller/local_machine_profile.py`
  - Approval-gated read-only snapshot of OS/runtime/hardware/tooling.
  - Current Docker snapshots honestly report `environment.scope=docker_container`.
- `controller/ouroboros_independence.py`
  - Computes `independence_score` and labels from local inference, tool use, code ability, learning loop, self-extension, validation, recovery and knowledge coverage.

### Rotating Blue Brain Update
The 11D rotation loop now has CPU-clock mode:
- `cpu_clock_mode=true` decouples lightweight orthogonal pocket rotations from heavy RandomForest training.
- Rotation cadence is derived from CPU clock as `cpu_clock_hz / clock_divisor`, then capped by `max_rotation_hz`.
- Live local setting after validation:
  - `max_rotation_hz=20000`
  - `clock_divisor=100000`
  - `train_every_rotations=10000`
- This makes the 11D pocket feel live while keeping model training bounded.

### Streaming Consciousness 11D Update
The prototype `/home/pwintri2/Downloads/streaming_consciousness_11d_pocket.py` has been incorporated as `controller/streaming_consciousness_adapter.py`.

It runs as a bounded trainer-pipeline component:
- Electrical layer: membrane potentials, injected currents and spike-like reset dynamics.
- Digital layer: binary consciousness buffer using packed 11D/electrical/timestamp state.
- Network layer: DHCP self-configuration plus TCP/HTTP-like packet flow.
- Dataset export: 17 features (`11D + electrical + digital + network`) for later trainer use.

New endpoints:
- `GET /trainer/streaming-consciousness/status`
- `POST /trainer/streaming-consciousness/start`
- `POST /trainer/streaming-consciousness/stop`
- `POST /trainer/streaming-consciousness/tick`
- `POST /trainer/streaming-consciousness/export-dataset`

The React Trainer tab now includes a Streaming Consciousness 11D panel showing steps, steps/s, DHCP/IP state, average membrane voltage, byte count, packet count and a compact 2D projection.

Live local configuration after integration:
- `steps_per_tick=25`
- `interval_seconds=0.2`
- `n_samples=8000`
- DHCP observed: `BOUND`
- State file: `.secrets/streaming_consciousness_11d.json`
- Dataset exports: `out/streaming_consciousness/`

### New API Endpoints
- `GET /trainer/codeneuron/status`
- `POST /trainer/codeneuron/index`
- `GET /trainer/codeneuron/pocket-map`
- `GET /trainer/codeneuron/search?q=...`
- `GET /trainer/curriculum/status`
- `GET /trainer/local-machine/status`
- `POST /trainer/local-machine/snapshot`
- `GET /trainer/independence/status`
- `GET /trainer/streaming-consciousness/status`
- `POST /trainer/streaming-consciousness/start`
- `POST /trainer/streaming-consciousness/stop`
- `POST /trainer/streaming-consciousness/tick`
- `POST /trainer/streaming-consciousness/export-dataset`

### UI Additions
The React Trainer tab now shows:
- CodeNeuron index/search status.
- 11D Pocket Map cards with source counts.
- Curriculum coverage.
- Local machine profile scope/status.
- Independence score and external-model-needed indicator.
- Capability gaps/recommendations.
- CPU Clock controls for Blue Brain Rotating: `CPU Clock`, `Hz Cap`, `Clock Div`, `Train Every`.

### Live Docker Evidence
- Backend: `http://localhost:8010`
- React dev server: `http://localhost:1420`
- Docker container: `wintrip-standalone-ui`
- CodeNeuron mount: `/codeneuron` read-only.
- Real index observed: 191 files, 30,537 lines, all 11 pocket dimensions matched.
- Independence score observed: `0.8412`, label `mostly_independent`, `external_model_needed=true`.

### Validation
Run in Docker:

```bash
python -m unittest \
  sandbox_tests.test_codeneuron_adapter \
  sandbox_tests.test_training_curriculum \
  sandbox_tests.test_local_machine_profile \
  sandbox_tests.test_ouroboros_independence
```

Result: OK.

```bash
python -m unittest \
  sandbox_tests.test_streaming_consciousness_adapter \
  sandbox_tests.test_trainer_pipeline_blue_brain \
  sandbox_tests.test_rotating_blue_brain \
  sandbox_tests.test_codex_registry \
  sandbox_tests.test_codex_agent
```

Result: OK.

```bash
python -m unittest sandbox_tests.test_tauri_backend_routes
```

Result: OK.

```bash
npm --prefix ouroboros_cockpit run build
```

Result: OK.
