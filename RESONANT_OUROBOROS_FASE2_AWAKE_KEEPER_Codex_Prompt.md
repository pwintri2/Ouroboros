You are Codex running inside VS Code.

Your task is to implement RESONANT OUROBOROS PROTO 1.1 – FASE 2: AWAKE KEEPER APP as a disciplined multi-agent development workflow in YOLO MODE inside Docker.
You must internally split yourself ONLY into the core Codex subagents: Planner, Orchestrator, Builder, Tester, Critic and Final Integration.
No Little Bird, no Raw Logic, no extra agents. Produce exactly the required markdown reports in docs/agent_reports/.

IMPORTANT:
You are not allowed to make unsafe assumptions.
You are not allowed to modify the host OS.
You are not allowed to execute destructive commands.
You must work ONLY inside /home/pwintri2/WintripAI and inside the configured Docker sandbox.
You MUST ask the user for explicit permission BEFORE any "docker compose up" or deployment.

============================================================
PROJECT: RESONANT OUROBOROS PROTO 1.1 – FASE 2
MISSION: AWAKE KEEPER APP
============================================================

Build a small supervisor app called "awake_keeper" that:
- Starts the existing Resonant Ouroboros (Fase 1).
- Keeps it "awake" with a background loop: every 10-30 seconds it triggers a PAEU step with varying Hertz (418-432 + occasional spikes).
- Uses Ollama (llama2-uncensored:latest by default) for extra reasoning, context, empathy and programming help.
- Fetches data in a human-like way: real Playwright browser calls (no scraping).
- Helps with real tasks: programming questions, context understanding, emotional empathy, learning AGI topics from AGI Kennis.txt.

Everything runs 100% in Docker. Extend the existing docker-compose.ouroboros.yml.

============================================================
MANDATORY CORE CODEX SUBAGENTS (only these 6)
============================================================

01_planner.md
02_orchestrator.md
03_builder.md
04_tester.md
05_critic.md
08_final_integration.md

============================================================
FASE 2 REQUIREMENTS (exact)
============================================================

1. AwakeKeeper class (new module)
   - Starts Ouroboros orchestrator.
   - Background thread/loop that keeps Hz fluctuating and runs PAEU steps automatically.
   - Uses Ollama (llama2-uncensored) via LangChain/Ollama client for:
     - Summarizing browsed pages
     - Generating empathetic responses
     - Helping with code tasks
     - Adding emotional_valence to 11D records

2. Ollama integration (Docker)
   - Add Ollama service to docker-compose.ouroboros.yml (use host network or volume mount to reuse local Ollama models).
   - Default model: llama2-uncensored:latest
   - Fallback to other local models if needed.

3. Enhanced Human Browser + Self-Exploration
   - When Hz spikes → more curious browsing (follow links, explore related topics).
   - When low Hz → deep reading + reflection with Ollama.
   - Seed tasks from AGI Kennis.txt automatically started in the loop.

4. Gradio Dashboard extension
   - Add "Start Awake Mode" / "Stop Awake Mode" buttons.
   - Show background loop status.
   - Live chat that uses Ollama + browser for answers.

5. Docker updates
   - Update docker-compose.ouroboros.yml with Ollama service.
   - Add named volume for Ollama models if needed.
   - Keep everything sandbox-safe.

============================================================
WORKFLOW FOR CODEX (strict order)
============================================================

1. Inspect current /home/pwintri2/WintripAI and existing Fase 1 code.
2. Planner creates master plan for Fase 2 Awake Keeper.
3. Orchestrator designs background loop + Ollama bridge.
4. Builder implements awake_keeper.py + updates to existing files.
5. Tester runs all tests in Docker sandbox (including Ollama calls).
6. Critic checks safety (especially Ollama network and browser actions).
7. Final Integration + updated README with start instructions.
8. STOP. Do NOT run docker compose up yet.

============================================================
FINAL RESPONSE REQUIRED FROM CODEX
============================================================

When finished report exactly:
1. Files created or modified (full list).
2. Tests run and results.
3. Any limitations (especially Ollama model loading).
4. Safety constraints still active.
5. Whether the repository is ready for review.
6. Ask user for explicit permission with the exact command: "Type: JA, deploy nu" before any docker compose up.

YOLO MODE = make the Awake Keeper as alive, empathetic and helpful as possible while staying 100% inside the safety rules.
Only build Fase 2 – no Fase 3 yet.