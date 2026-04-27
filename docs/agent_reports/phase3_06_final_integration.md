# Phase 3 Final Integration Report

Phase 3 is implemented in code and documentation, with deployment still gated.

New runtime surfaces:

- Self-model JSON: `AWAKE_KEEPER_SELF_MODEL_PATH` or `/workspace/data/awake_keeper_self_model.json`.
- Action JSON: `AWAKE_KEEPER_ACTIONS_PATH` or `/workspace/data/awake_keeper_actions.json`.
- API: `/self-model`, `/actions`, `/actions/{id}`, `/actions/{id}/approve`, `/actions/{id}/reject`.
- UI: Approvals button, pending action window, approve/reject buttons, chat action proposals.

Next gated step:

- After the user types `JA, deploy fase 3 now`, build/restart the Docker service and run the full test suite inside Docker.
