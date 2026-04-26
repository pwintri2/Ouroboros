# Planner Report - Fase 2 Awake Keeper

## Scope
- Build only Resonant Ouroboros Proto 1.1 Fase 2: `awake_keeper`.
- Keep all work inside `/home/pwintri2/WintripAI` and Docker-defined services.
- Do not run `docker compose up` or deploy without explicit user permission.
- Produce only the six required Codex role reports in `docs/agent_reports/`.

## Inspection Findings
- The repository has controller-layer Wintrip/Ollama code, a static Ouroboros site, and root tests for older phases.
- The `resonant_ouroboros/` and `tests/` directories existed only with ignored `__pycache__` files; source files were absent.
- Bytecode metadata exposed the intended Fase 1/Fase 2 module surface: oscillator, safety, browser, schema, memory, PAEU loop, seed loader, dashboard, Gordon bridge, and awake keeper.
- `docker-compose.ouroboros.yml`, `Dockerfile.ouroboros`, and `AGI Kennis.txt` were not present, so Fase 2 needs sandbox scaffolding.

## Master Plan
1. Recreate the `resonant_ouroboros` source package against the discovered API surface.
2. Implement `AwakeKeeper` as a thread-managed supervisor around the Fase 1 oscillator, browser, memory, and PAEU loop.
3. Add an Ollama bridge using LangChain Ollama when available, with safe HTTP fallback and local-model fallback handling.
4. Extend the browser loop so low Hz favors deep reading and spike Hz favors exploratory link following.
5. Add dashboard controls for awake mode, status, Hz history, and Ollama/browser chat.
6. Add Docker compose and Dockerfile support with an Ollama service and model volume.
7. Add tests for schema, memory, safety, oscillator, PAEU, seed parsing, dashboard history, Gordon bridge, and Awake Keeper.
8. Verify without `docker compose up`.

## Safety Boundaries
- Browser navigation is gated by URL safety checks that block localhost, loopback, private, link-local, file URLs, and unsupported schemes by default.
- The app uses Playwright browser operations rather than raw scraping libraries.
- Ollama calls are local to the Docker network by default: `http://ollama:11434`.
- Missing Ollama models must be reported as limitations; no automatic destructive model management is performed.

## Deliverables
- New `resonant_ouroboros` source modules.
- New Docker sandbox files.
- New focused tests.
- Updated README/start instructions.
- Six required agent reports only.
