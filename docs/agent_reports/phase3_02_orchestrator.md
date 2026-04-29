# Phase 3 Orchestrator Report

Integration design:

- `AwakeKeeper` owns the self-model and builds prompt context from runtime state plus 11D memory.
- `DashboardRuntime` exposes `/self-model` and `/actions` alongside existing `/status`, `/chat`, `/control`, and `/memory`.
- `SafeActionExecutor` persists action proposals in JSON. Registered review handlers are local and non-mutating; whitelisted command actions prepare non-interactive `docker exec` vectors and only run them when `OUROBOROS_ENABLE_DOCKER_EXEC=true`.
- The Goose-like UI never executes local commands; it creates proposals and approves/rejects through the REST API.
