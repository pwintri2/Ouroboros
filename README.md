# Resonant Ouroboros Proto 1.1 - Fase 2 Awake Keeper

This repository contains the Fase 2 `awake_keeper` supervisor app for Resonant Ouroboros. It starts the Fase 1 PAEU core, keeps it awake with a 418-432 Hz oscillator plus occasional curiosity spikes, uses local Ollama for reasoning, and browses through a real Playwright browser inside Docker.

## What Fase 2 Adds

- `AwakeKeeper` background supervisor with start/stop lifecycle.
- Docker dashboard autostarts Awake Mode by default, so opening the UI begins seed import and background enrichment.
- Automatic PAEU ticks every 10-30 seconds by default.
- Ollama bridge with `llama2-uncensored:latest` as the default model and local fallback models.
- Playwright-based human browser actions with URL safety gates.
- Seed learning from `AGI Kennis.txt`.
- Gradio dashboard with awake mode controls, 3-times-per-second live refresh, status, Hz history, knowledge incorporation feed, screenshot view, and live chat.

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

If Fase 1 already uses dashboard port `7860`, start Fase 2 on `7861`. By default the app talks to your existing host Ollama at `http://host.docker.internal:11434`, so it can use the same model list as `ollama list` on the laptop:

```sh
flatpak-spawn --host bash -lc 'cd /home/pwintri2/WintripAI && OUROBOROS_GRADIO_PORT=7861 docker compose -f docker-compose.ouroboros.yml -p ouroboros-fase2 up --build -d'
```

## Model Setup

The default model is `llama2-uncensored:latest`. On this laptop, Fase 2 talks to the existing host Ollama server through `host.docker.internal`, so the app sees the same models as `ollama list` on the host without copying 46 GB of model files.

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

The launcher has buttons for Start Fase 2, Open Dashboard, Status, and Stop. It automatically uses `flatpak-spawn --host` when Docker is hidden inside a Flatpak VS Code terminal.

If Tkinter is not installed, the same launcher automatically opens a small browser UI instead. It runs locally at `http://127.0.0.1:8791` when that port is free.

## Deployment Gate

Do not run `docker compose up` until explicit permission is given by the user.
