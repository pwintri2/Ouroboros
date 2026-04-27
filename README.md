# Resonant Ouroboros Proto 1.1 - Fase 3 Awake Keeper

This repository contains the `awake_keeper` supervisor app for Resonant Ouroboros. It starts the PAEU core, keeps it awake with a 418-432 Hz oscillator plus occasional curiosity spikes, uses local Ollama for reasoning, browses through a real Playwright browser inside Docker, and now keeps a persistent Fase 3 self-model with approval-gated safe actions.

## What Fase 3 Adds

- `AwakeKeeper` background supervisor with start/stop lifecycle.
- Docker dashboard autostarts Awake Mode by default, so opening the UI begins seed import and background enrichment.
- Automatic PAEU ticks every 10-30 seconds by default.
- Ollama bridge with `llama2-uncensored:latest` as the default model and local fallback models.
- Strong Resonant Ouroboros system prompt injected into Ollama calls with Hz, mood, topic, last 3 memory records, and self-model summary.
- Persistent self-model at `AWAKE_KEEPER_SELF_MODEL_PATH` or `/workspace/data/awake_keeper_self_model.json`.
- Periodic self-reflection every `AWAKE_KEEPER_SELF_REFLECTION_INTERVAL` iterations, default `5`.
- Safe Action Executor with whitelist classification, one-time approval tokens, Docker-contained execution, and 11D audit logging.
- Playwright-based human browser actions with URL safety gates.
- Seed learning from `AGI Kennis.txt`.
- Gradio dashboard plus REST API with awake mode controls, status, Hz history, knowledge incorporation feed, screenshot view, live chat, self-model, and action approval endpoints.

## Fase 3 API

- `GET /health`
- `GET /status`
- `GET /self-model`
- `POST /chat` with `{"message": "..."}`
- `POST /control` with `{"command": "start|stop|manual_paeu_step|creative_spike|clear_queue"}`
- `GET /memory?query=...&limit=18`
- `GET /actions?status=pending&limit=20`
- `POST /actions`
- `POST /actions/{id}/approve`
- `POST /actions/{id}/reject`

Safe executor command whitelist:

```text
ls, pwd, cat, head, tail, sed, grep, rg, find, python, python3, open
```

Whitelisted commands are still approval-required when proposed from chat. By default, approval records and audits a prepared `docker exec` command without running it; set `OUROBOROS_ENABLE_DOCKER_EXEC=true` only in a deployment where Docker access has been intentionally provided. `python`/`python3` are restricted to version checks or scripts under `/workspace`; `open` is restricted to http(s) URLs and the safe app allowlist. Dangerous shell tokens, host file deletion, Docker control, arbitrary shell, and credentials-oriented commands are blocked.

## Ollama Identity Prompt

Every Awake Keeper Ollama call is wrapped with the Resonant Ouroboros system prompt from `resonant_ouroboros/prompt_context.py`. The prompt injects current Hz, mood, topic, last action, last 3 memory records, self-model summary, and safe-action policy.

## Docker Files

- `docker-compose.ouroboros.yml` defines:
  - `ouroboros` app/dashboard service.
  - `ollama` local model service.
  - `ouroboros_data` and `ollama_models` named volumes.
- `Dockerfile.ouroboros` builds the Python/Playwright app image.
- `requirements.ouroboros.txt` lists runtime/test dependencies.

## Build And Test Without Deployment

These commands do not start the long-running stack:

```sh
docker compose -f docker-compose.ouroboros.yml -p ouroboros-fase2 config
docker compose -f docker-compose.ouroboros.yml -p ouroboros-fase2 build ouroboros
docker compose -f docker-compose.ouroboros.yml -p ouroboros-fase2 run --rm --no-deps ouroboros pytest -q
```

If VS Code is installed as a Flatpak and `docker` is hidden inside the editor terminal, run host Docker through Flatpak:

```sh
flatpak-spawn --host bash -lc 'cd /home/pwintri2/WintripAI && docker compose -f docker-compose.ouroboros.yml -p ouroboros-fase2 config'
```

If Fase 1 already uses dashboard port `7860`, start Fase 3 on `7861`. By default the app talks to your existing host Ollama at `http://host.docker.internal:11434`, so it can use the same model list as `ollama list` on the laptop:

```sh
flatpak-spawn --host bash -lc 'cd /home/pwintri2/WintripAI && OUROBOROS_GRADIO_PORT=7861 docker compose -f docker-compose.ouroboros.yml -p ouroboros-fase2 up --build -d'
```

## Model Setup

The default model is `llama2-uncensored:latest`. On this laptop, Fase 3 talks to the existing host Ollama server through `host.docker.internal`, so the app sees the same models as `ollama list` on the host without copying 46 GB of model files.

The Docker compose default bounds live chat latency with `OLLAMA_REQUEST_TIMEOUT=30` and `OLLAMA_MAX_MODEL_ATTEMPTS=1`. If the configured model is too slow or unavailable, the API returns the local safe fallback instead of holding the UI for several minutes.

The compose file still includes an optional Docker `ollama` service with its own named model volume. To force the app to use that service instead of host Ollama, start with `OLLAMA_BASE_URL=http://ollama:11434` and pull the model into the Docker Ollama volume:

```sh
docker compose -f docker-compose.ouroboros.yml -p ouroboros-fase2 exec ollama ollama pull llama2-uncensored:latest
```

To reuse an existing host Ollama model directory, set `OLLAMA_MODELS_PATH` to that absolute directory before starting Docker.

## No-Terminal Launcher

For a small desktop UI, open:

```text
AwakeKeeperLauncher.desktop
```

or double-click:

```text
start_awake_keeper_launcher.sh
```

The launcher has buttons for Start, Open Dashboard, Status, and Stop. It automatically uses `flatpak-spawn --host` when Docker is hidden inside a Flatpak VS Code terminal.

If Tkinter is not installed, the same launcher automatically opens a small browser UI instead. It runs locally at `http://127.0.0.1:8791` when that port is free.

## Deployment Gate

Do not run `docker compose up` until explicit permission is given by the user.
