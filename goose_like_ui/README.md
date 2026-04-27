# Resonant Ouroboros Goose-Like UI

Standalone desktop UI for the Fase 4 Awake Keeper.

## Build Decision

Swift and `xcrun` were not available in the Docker-safe detection step, so this UI uses the Python/customtkinter fallback.

## What It Does

- Goose-inspired dark chat window with a left status/control sidebar.
- Polls the local Awake Keeper API every 1-2 seconds.
- Shows Hz, mood, iterations, current topic, last action, model, co-evolution score, recent event id, pending evolution proposals, and Safe Mode.
- Sends chat through the existing Awake Keeper stack: Ollama, browser context, and 11D memory.
- Exposes controls for Start, Stop, Manual PAEU Step, Creative Spike, View 11D Memory, Reflection, Evolution Events, and Clear Queue.
- Shows pending safe action approvals and lets the user approve/reject one action or multiple selected actions at once.
- Creates review-only Evolution Proposal actions from explicit self-reflection requests; durable 11D/evolution commits happen only after approval.
- Shows stdout/stderr previews after approved sandbox actions complete or fail.
- Turns code/action proposals from chat into REST action proposals instead of running anything locally.

## Requirements

- The Fase 4 Docker service must expose the API on `http://127.0.0.1:7861`.
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
- `POST /reflect`
- `POST /control` with `{"command": "start|stop|manual_paeu_step|creative_spike|clear_queue"}`
- `GET /memory?query=...&limit=18`
- `GET /evolution?limit=24`
- `GET /actions?status=pending&limit=20`
- `POST /actions`
- `POST /actions/approve-batch`
- `POST /actions/reject-batch`
- `POST /actions/{id}/approve`
- `POST /actions/{id}/reject`

## Safety

The UI never runs shell commands. It only calls the local REST API, which is expected to be bound to `127.0.0.1:7861`. Code/action buttons create Safe Action Executor proposals, and approval uses one-time local tokens returned by the API. Evolution proposals are review-only; approving them records intent and audit context, but does not edit files.
