# Resonant Ouroboros Goose-Like UI

Standalone desktop UI for the Fase 2 Awake Keeper.

## Build Decision

Swift and `xcrun` were not available in the Docker-safe detection step, so Fase 2.5 uses the Python/customtkinter fallback.

## What It Does

- Goose-inspired dark chat window with a left status/control sidebar.
- Polls the local Awake Keeper API every 1-2 seconds.
- Shows Hz, mood, iterations, current topic, last action, model, and Safe Mode.
- Sends chat through the existing Awake Keeper stack: Ollama, browser context, and 11D memory.
- Exposes controls for Start, Stop, Manual PAEU Step, Creative Spike, View 11D Memory, and Clear Queue.

## Requirements

- The Fase 2 Docker service must expose the API on `http://127.0.0.1:7861`.
- Python 3 with Tk support.
- `customtkinter`.

Install the UI dependency:

```sh
python3 -m pip install -r goose_like_ui/requirements.txt
```

If `tkinter` is missing, install the OS package for Tk support, for example `python3-tk` on Debian/Ubuntu-based systems.

## Run

From the repo root:

```sh
AWAKE_KEEPER_API_URL=http://127.0.0.1:7861 sh goose_like_ui/launch_goose_like_ui.sh
```

For double-click use, run `goose_like_ui/launch_goose_like_ui.command` or `goose_like_ui/launch_goose_like_ui.sh` from a file manager after making it executable.

## API Contract Used

- `GET /status`
- `POST /chat` with `{"message": "..."}`
- `POST /control` with `{"command": "start|stop|manual_paeu_step|creative_spike|clear_queue"}`
- `GET /memory?query=...&limit=18`

## Safety

The UI never runs shell commands. It only calls the local REST API. Code-application buttons are blocked by Safe Mode and display a review-only notice.
