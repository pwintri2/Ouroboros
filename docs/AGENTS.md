# WintripAI Multi-Agent Ownership Matrix

## Protocol
Alle inter-agent communicatie gebruikt:

- `WINTRIP-AGENT/1.0`

## Hoofdagent
- Rol: integratie, review, escalatie
- Provider: Gemini CLI
- Model: `gemini-2.5-pro` (default via `.env`)

## Agent 1 — Wintrip Developer (Backend)
- Provider: Ollama
- Model: `gemma4:latest`
- Ownership:
  - `/app/controller`
  - `/app/docker-image`
  - `/app/Dockerfile`
  - `/app/docker-compose.yml`
  - `/app/data/main_sandbox.py`
  - `/app/data/start_sandbox.sh`

## Agent 2 — Wintrip UI (Frontend)
- Provider: Ollama
- Model: `gemma4:latest`
- Ownership:
  - `/app/regiekamer`
  - `/app/WintripAI_IDE.html`
  - `/app/demo_stream_of_consciousness.html`
  - `/app/demo_stream_of_consciousness_en.html`

## Agent 3 — Wintrip Voorzitter (QA & Tester)
- Provider: Ollama
- Model: `gemma4:latest`
- Ownership:
  - `/app/sandbox_tests`
  - `/app/smoke_test.py`
  - `/app/test_phase1.py`
  - `/app/test_phase2.py`
  - `/app/test_phase3.py`
  - `/app/test_phase4.py`
  - `/app/requirements-dev.txt`
  - `/app/setup.cfg`

## Agent 4 — Wintrip Kritiek (Docs/Planning)
- Provider: Ollama
- Model: `gemma4:latest`
- Ownership:
  - `/app/ARCHITECTURE.md`
  - `/app/PROJECT.md`
  - `/app/SESSION.md`
  - `/app/SESSIE_VERSLAG_2026-04-07.md`
  - `/app/README_AI.md`
  - `/app/GEMINI.md`
  - `/app/docs`

## Escalatievoorwaarden
Escalatie naar Philip bij:
- onduidelijke canonical repo
- ownership conflict
- sandbox-failure
- verschil tussen legacy snapshot en actieve code
- provider tooling niet beschikbaar in Docker-sandbox
