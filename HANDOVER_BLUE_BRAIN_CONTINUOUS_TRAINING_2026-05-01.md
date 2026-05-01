# Handover: Blue Brain and Continuous Trainer Pipeline
**Date**: 2026-05-01
**Branch**: `backup/trainer-pipeline-integration-20260501-1557`

## Summary
The Ouroboros trainer pipeline now supports a third trainer, Blue Brain, and a continuous queue for LitGPT and Unsloth. Browser-approved 11D training records can be ingested through API calls, converted to text JSONL datasets, and queued for both trainers. Actual LitGPT/Unsloth training remains approval-gated and is currently safe to run in queue mode.

## Backend Changes
- Added `controller/blue_brain_adapter.py`.
  - Converts the original `Blue.py` demo into reusable functions.
  - Generates synthetic 11D e-type datasets.
  - Trains and evaluates a `RandomForestClassifier`.
  - Saves and reloads `.joblib` model artifacts.
  - Supports a dedicated `.venv_blue_brain` environment.
- Added `controller/trainer_continuous.py`.
  - Tracks continuous training state in `.secrets/trainer_continuous.json`.
  - Watches approved browser training records.
  - Builds text JSONL datasets for trainer consumption.
  - Creates LitGPT and Unsloth jobs in queue mode by default.
  - Can execute real trainer runs only when `Akkoord` approval is supplied.
- Extended trainer job and artifact metadata.
  - New trainer method: `blue_brain`.
  - New artifact types for Blue Brain models and metrics.
- Updated LitGPT and Unsloth adapters.
  - Replaced shell-string execution with explicit subprocess argument lists.
  - Kept training execution bounded and easier to test.
- Updated dataset building.
  - Supports text JSONL output for SFT-style training.
  - Uses configurable `WINTRIP_DB_PATH` and `WINTRIP_TRAINING_COLLECTION`.
- Updated `controller/ollama_client.py`.
  - Adds runtime discovery for reachable Ollama endpoints, including host Docker access.
- Updated `controller/main.py`.
  - Registers continuous trainer routes.
  - Publishes self-modification pipeline status for the cockpit.
  - Preserves test-provided fake multi-provider routers so backend tests do not call live OpenAI APIs.

## API Endpoints
- `GET /trainer/status`
  - Includes LitGPT, Unsloth, Blue Brain, continuous trainer, jobs, artifacts, and approved record counts.
- `POST /trainer/blue-brain/setup`
  - Creates or refreshes `.venv_blue_brain` with `numpy`, `scikit-learn`, and `joblib`.
- `POST /trainer/jobs`
  - Accepts `method=blue_brain` in addition to LitGPT and Unsloth.
- `GET /trainer/continuous/status`
  - Returns continuous trainer state, selected methods, worker status, dataset counts, and last jobs.
- `POST /trainer/continuous/start`
  - Starts continuous queueing for LitGPT and/or Unsloth.
- `POST /trainer/continuous/tick`
  - Runs one bounded dataset/job preparation tick.
- `POST /trainer/continuous/stop`
  - Stops the continuous worker.
- `POST /trainer/browser/ingest`
  - Accepts browser-originated records and notifies the continuous trainer.
- Existing browser approval flows also notify the queue:
  - `/training/browser/approve`
  - `/api/ouroboros/training/ingest`

## React UI
The Trainer tab now exposes:
- Blue Brain status and setup.
- Blue Brain model controls for samples, trees, max depth, and cycles.
- Blue Brain job creation and accuracy display.
- Continuous LitGPT/Unsloth controls.
- Method toggles for LitGPT and Unsloth.
- Queue mode vs actual training mode.
- Interval and manual tick controls.
- Continuous trainer status, last dataset, and last jobs.

## Runtime Notes
- Continuous training defaults to queue mode with `execute_training=false`.
- Queue mode builds datasets and creates trainer jobs without launching expensive trainer commands.
- Real LitGPT/Unsloth execution still requires the approval phrase `Akkoord`.
- Unsloth real training generally requires a compatible GPU/CUDA runtime.
- Blue Brain can run in the current Python environment when dependencies are present, or in `.venv_blue_brain`.
- Runtime artifacts are intentionally excluded from git:
  - `.venv_*`
  - `out/`
  - `tmp/`
  - Chroma sqlite databases
  - copied `litgpt/` and `unsloth/` source folders

## Validation
Docker validation was run in `wintrip-standalone-ui`.

```bash
docker exec -w /workspace wintrip-standalone-ui python -m unittest \
  sandbox_tests.test_trainer_continuous \
  sandbox_tests.test_blue_brain_adapter \
  sandbox_tests.test_trainer_pipeline_blue_brain \
  sandbox_tests.test_training_routes \
  sandbox_tests.test_agent_tools
```

Result: `Ran 16 tests ... OK`

```bash
docker exec -w /workspace wintrip-standalone-ui python -m unittest \
  sandbox_tests.test_tauri_backend_routes \
  sandbox_tests.test_multi_api_router \
  sandbox_tests.test_api_key_store \
  sandbox_tests.test_external_provider_isolation \
  sandbox_tests.test_safe_shell
```

Result: `Ran 23 tests ... OK`

```bash
npm --prefix ouroboros_cockpit run build
```

Result: build completed successfully.

## Current Deployment State
This work has been validated in Docker/local runtime. It has not been deployed beyond the local branch. The live backend was restarted locally after the OpenAI test-isolation fix, and cockpit status showed Ollama, Ouroboros, Pipeline, Roo, and Model online.
