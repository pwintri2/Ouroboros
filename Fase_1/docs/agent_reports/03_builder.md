# 03 Builder

## Implemented Modules

- `resonant_ouroboros/oscillator.py`: living Hertz oscillator and behavior map.
- `resonant_ouroboros/schema.py`: exact 11D schema, metadata validation, and
  deterministic 11-float vectorization.
- `resonant_ouroboros/memory.py`: ChromaDB-backed hippocampus plus in-memory
  test backend.
- `resonant_ouroboros/safety.py`: URL safety gate and query sanitizer.
- `resonant_ouroboros/vision.py`: screenshot-to-vision adapter with explicit
  local stub or opt-in OpenAI provider.
- `resonant_ouroboros/browser.py`: Playwright browser engine with navigate,
  click, scroll, type, read text, screenshot, and link extraction.
- `resonant_ouroboros/paeu_loop.py`: minimal frequency-driven PAEU loop.
- `resonant_ouroboros/paeu_graph.py`: LangGraph PAEU graph.
- `resonant_ouroboros/seed.py`: `AGI Kennis.txt` parser and seed-learning
  orchestration.
- `resonant_ouroboros/dashboard.py`: Gradio live Hz, browser view, and memory
  explorer dashboard.
- `resonant_ouroboros/main.py`: CLI entrypoints for dashboard, seed learning,
  and graph check.
- `resonant_ouroboros/gordon_bridge.py`: progress file bridge for Gordon AI.

## Docker Artifacts

- `Dockerfile`
- `docker-compose.yml`
- `docker-compose.ouroboros.yml`
- `.dockerignore`
- `start-docker.sh`
- `requirements.txt`

The Docker app now uses Gordon's expected workspace contract:

- Host workspace: `/tmp/codex-workspace`
- Container workspace mount: `/workspace`
- Runtime data: `/workspace/data`
- Gordon progress: `/workspace/gordon_progress.log`

## Seed Knowledge

The provided `AGI Kennis.txt` was copied into the workspace root and is mounted
read-only into Docker at `/app/data/seeds/AGI Kennis.txt`.
