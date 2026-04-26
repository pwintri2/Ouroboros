# Orchestrator Report - Awake Loop and Bridges

## Runtime Design
- `AwakeKeeper` owns the Fase 2 lifecycle.
- It constructs or receives:
  - `HertzOscillator` for 418-432 Hz base modulation plus creative spikes.
  - `HumanBrowserEngine` for real Playwright browsing.
  - `HippocampusMemory` for exact 11D records.
  - `PAEULoop` for Perceive, Act, Evaluate, Update steps.
  - `OllamaBridge` for summaries, empathy, code help, and emotional valence.

## Background Loop
- `start()` creates one daemon thread and returns immediately.
- Each tick:
  1. Selects a seed topic from `AGI Kennis.txt`.
  2. Samples current Hz.
  3. Uses more steps during `creative_spike`, fewer during normal or low-band reading.
  4. Runs PAEU browser steps.
  5. Summarizes any accepted page through Ollama.
  6. Sleeps for a randomized 10-30 second interval by default.
- `stop()` sets a thread event and closes the browser.
- `run_once()` exists for deterministic tests and dashboard/manual stepping.

## Ollama Bridge
- Default model: `llama2-uncensored:latest`.
- Base URL in Docker: `http://ollama:11434`.
- Preferred client: `langchain_ollama.ChatOllama`.
- Fallback client: direct Ollama HTTP `/api/chat` and `/api/tags` calls.
- Fallback model order:
  1. Configured default model.
  2. Models returned by local `/api/tags`.
  3. Configured fallback tuple.
- Failures are captured in `last_error` and returned as deterministic local fallback text so the app keeps running.

## Browser Behavior
- Low Hz/deep-read mode favors scroll/read/dwell.
- Baseline mode starts with a Wikipedia search for seed topics.
- Spike/curious mode can follow visible links from the current browser page.
- Every navigation target passes `evaluate_url()`.
- Browser content is gathered through Playwright page state, not raw HTTP scraping.

## Dashboard Flow
- `create_dashboard()` builds a Gradio Blocks interface.
- Controls:
  - Start Awake Mode.
  - Stop Awake Mode.
  - Refresh status.
  - Live chat using Ollama plus optional browser context.
- Status shows running state, current Hz, mood, topic, last action, last record, last summary/error, and next wake time.

## Docker Flow
- `ouroboros` service runs the dashboard or CLI.
- `ollama` service is available on the internal Docker network.
- A named `ollama_models` volume is provided, with an environment override to bind-mount an existing model directory when desired.
- Verification may use `docker compose config`, `docker compose build`, and `docker compose run`; `docker compose up` remains blocked pending user permission.
