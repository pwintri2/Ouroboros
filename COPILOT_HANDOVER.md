# COPILOT_HANDOVER.md

## WintripAI — Goose Handover to GitHub Copilot Cloud Agent
**Date:** 2026-04-12  
**Canonical repository:** `/Users/philip/WintripAI`

## Current baseline
WintripAI is handing off from the local Goose/OrbStack workflow to the GitHub Copilot Pro+ Cloud Agent for the next architectural leap.

### Foundation is live
The current baseline is operational and validated:
- working multi-agent backend
- live Mission Control webui
- Docker/OrbStack runtime
- hybrid model setup:
  - **Gemini CLI** for the orchestrator
  - **local Ollama / gemma4:latest** for the sub-agents

### Active swarm
Current named agents:
- **Wintrip Developer (Backend)**
- **Wintrip UI (Frontend)**
- **Wintrip Voorzitter (QA & Tester)**
- **Wintrip Kritiek (Docs/Planning)**

### Latest completed UI baseline
We completed the latest Mission Control interaction/polish rounds, including:
- improved streaming UX
- persona editor basis
- refined semantic search workflow
- stronger blueprint-aligned Mission Control layout

---

## WINTRIP-AGENT/1.0 protocol summary
All inter-agent communication should follow the strict envelope philosophy of:

```text
WINTRIP-AGENT/1.0
```

Expected JSON envelope shape:

```json
{
  "protocol": "WINTRIP-AGENT/1.0",
  "agent": "wintrip-developer-backend",
  "task_id": "WT-...",
  "type": "proposal|status|result|blocker|escalation",
  "scope": {
    "owned_paths": [],
    "read_paths": [],
    "write_paths": []
  },
  "summary": "Short summary",
  "inputs": [],
  "outputs": [],
  "risks": [],
  "needs_review": true,
  "requires_human": false
}
```

### Protocol intent
- agents should stay inside their file/domain boundaries
- results should be reviewable and structured
- blockers/escalations should be explicit
- the orchestrator remains responsible for synthesis/integration

---

## Round 9 goals
GitHub Copilot Cloud Agent should execute **Ronde 9** with focus on these exact goals:

1. **Replacing demo-streams with real token streaming from the orchestrator**
2. **Deepening chat/session persistence strictly to the backend**
3. **Creating click-to-insert/use interactions for semantic search hits**
4. **Building richer upload metadata and document flows**

These are the explicit handover priorities.

---

## Mandatory execution guardrails

### 1. Use Docker sandbox for tests
All tests, runtime validation, scripts, and execution checks must be performed through the **Docker sandbox/runtime**, not by assuming direct unsafe host execution.

Copilot should prefer:
- Docker-based validation
- existing compose/runtime paths
- container-aware runtime assumptions

### 2. Follow DiffView / Human-in-the-Loop philosophy
WintripAI uses a **DiffView-first** workflow.

For any file creation or modification, Copilot must follow this philosophy:
- analyze first
- propose changes clearly
- preserve a reviewable diff mindset
- avoid uncontrolled broad rewrites
- keep changes scoped and explainable

### 3. Respect canonical repo boundaries
Primary repo:
```text
/Users/philip/WintripAI
```

Treat nested / legacy paths as non-canonical unless explicitly re-authorized.
In particular, avoid using nested legacy snapshots as the primary working base.

### 4. Ignore runtime data noise
Do **not** treat runtime data as feature-code work:
- `wintrip_brain/`
- transient chat/runtime data
- generated cache/build artifacts unless explicitly part of the change

---

## Suggested focus areas for Copilot analysis
Relevant areas likely to matter for Round 9:

### Backend
- `controller/main.py`
- `controller/api/chat_routes.py`
- `controller/api/persona_routes.py`
- streaming/runtime/provider integration paths

### Frontend
- `webui/src/components/workspace/*`
- `webui/src/components/sidebar/*`
- `webui/src/lib/api.ts`
- `webui/src/stores/*`

### Docs / reference
- `PHASE2_STATUS.md`
- `docs/ROUND7_STATUS.md`
- `docs/ROUND8_STATUS.md`
- `docs/ROUND9_PLAN.md`
- `docs/UI_FEATURE_BACKLOG.md`
- `docs/CANONICAL_REPO.md`

---

## Repo readiness status
A repo audit was performed for:
- `webui/`
- `controller/`
- `docs/`

Result:
- **no lingering uncommitted files** in those handover-critical directories
- runtime data under `wintrip_brain/` is intentionally excluded from this cleanliness check

---

## Handover note
The repository is prepared as a launchpad for the GitHub Copilot Cloud Agent to continue the next architectural step of WintripAI.

Primary handover theme:
**Mission Control must evolve from prototype-grade interaction to deeper real-time orchestration fidelity.**
