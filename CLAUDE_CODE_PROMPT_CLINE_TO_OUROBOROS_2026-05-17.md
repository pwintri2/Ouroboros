# Claude Code Prompt: Bring Cline-Grade Agentic Power Into Ouroboros

Use this as the Claude Code task prompt from `/home/pwintri2/WintripAI`.

```text
Werk in /home/pwintri2/WintripAI.

Lees eerst:
- AGENTS.md
- OUROBOROS_IDE_CONTEXT.md
- HANDOFF_CLINE_AGENTIC_POWER_TAURI_UI_2026-05-17.md

Gebruik /home/pwintri2/cline als read-only referentie voor Cline-achtige agentische eigenschappen. Wijzig /home/pwintri2/cline niet. Kopieer geen secrets, browser sessions, API keys, Chroma/vector-store payloads, uploads of caches. Cline is Apache-2.0; behoud attribution/notices als je letterlijk code overneemt, maar geef de voorkeur aan het vertalen van patronen naar Ouroboros.

Doel:
Maak Ouroboros merkbaar Cline-krachtiger: plan/act workflow, zichtbare tool-timeline, approvals, checkpoints/diffs, stale-file context, loop detection, command permissions, task history, provider/model status, Brave/web evidence, memory writes en een bruikbare Tauri cockpit UI. Dit moet praktisch en inspecteerbaar zijn, geen claim van consciousness of autonome personhood.

Belangrijke Cline referenties:
- /home/pwintri2/cline/src/core/task/index.ts
- /home/pwintri2/cline/src/core/task/ToolExecutor.ts
- /home/pwintri2/cline/src/core/task/tools/autoApprove.ts
- /home/pwintri2/cline/src/core/task/loop-detection.ts
- /home/pwintri2/cline/src/core/context/context-management/ContextManager.ts
- /home/pwintri2/cline/src/core/context/context-tracking/FileContextTracker.ts
- /home/pwintri2/cline/src/integrations/checkpoints/CheckpointTracker.ts
- /home/pwintri2/cline/src/core/permissions/CommandPermissionController.ts
- /home/pwintri2/cline/src/core/hooks/
- /home/pwintri2/cline/src/core/prompts/system-prompt/
- /home/pwintri2/cline/webview-ui/src/components/chat/
- /home/pwintri2/cline/webview-ui/src/components/common/CheckpointControls.tsx
- /home/pwintri2/cline/webview-ui/src/components/history/
- /home/pwintri2/cline/webview-ui/src/components/settings/
- /home/pwintri2/cline/webview-ui/src/components/worktrees/

Belangrijke Ouroboros targets:
- controller/agentic_processor.py
- controller/agent_tools.py
- controller/tool_bridge.py
- controller/slash_agent_router.py
- controller/persistent_memory_manager.py
- controller/agentic_strength.py
- controller/main.py
- controller/approval_resume.py
- controller/connector_catalog.py
- ouroboros_cockpit/src/App.tsx
- ouroboros_cockpit/src/styles.css
- ouroboros_cockpit/src/types/index.ts
- ouroboros_cockpit/src-tauri/src/main.rs, alleen als native capability echt nodig is

Maak eerst een korte implementatiecheck op basis van git status en bestaande code. Werk daarna in smalle, testbare stappen.

Backend eisen:
1. Voeg een expliciete agentic session/event laag toe of breid de bestaande laag uit:
   - session_id
   - timeline events
   - plan/act mode
   - provider/model
   - planned tool calls
   - tool status: planned, awaiting_approval, running, completed, blocked, failed
   - duration, stdout/stderr summary, redacted args
   - approval_required en approval_status
   - memory_status
   - provenance
   - agentic_strength
   - fake_success=false
2. Emit events vanuit AgenticProcessor planning, validation, dispatch, completion en memory persistence.
3. Voeg Cline-achtige loop detection toe voor repeated identical tool calls.
4. Voeg command permission policy toe geinspireerd door Cline, zonder de bestaande Akkoord gates te omzeilen.
5. Voeg file context/stale-file tracking toe voor files die de agent leest of wijzigt.
6. Voeg checkpoint/diff support toe voor mutaties. Restore mag alleen approval-gated met exact Akkoord.
7. Exposeer compacte routes voor sessions/events/diff/checkpoint/cancel/approval, bij voorkeur onder /api/ouroboros/agentic/.
8. Alles redacteren voor persistence. Geen secrets in JSONL, Chroma of responses.

Tauri UI eisen:
1. Maak in ouroboros_cockpit een Cline-grade Agent Workspace:
   - linkerkant: active/recent sessions en agent jobs
   - midden: chat/task timeline met tool rows, command output, diff rows, browser/search evidence, approval needed en completion
   - rechterkant: inspector met selected event details, redacted args, stdout/stderr, memory_status, provenance en agentic_strength
   - bovenin: provider/model, Plan/Act segmented control, approval input, stop/cancel, checkpoint/diff actions
2. Geen landing page. De eerste view moet de echte werkervaring zijn.
3. Maak Brave Search gebruik zichtbaar: gebruikt/niet gebruikt, query, source count, reason, memory action.
4. Maak Chroma/memory writes zichtbaar: collection, status, recovery/fallback, errors.
5. Maak model/rate-limit/provider problemen zichtbaar met concrete next action.
6. Houd styling compact en operationeel. Geen nested cards, geen decoratieve hero.

Tests:
- Voeg regressietests toe voor session events, approval blocks, loop detection, Chroma/memory redaction en command policy.
- Draai minimaal:
  python3 -m unittest sandbox_tests.test_agentic_processor sandbox_tests.test_agent_tools
  python3 -m unittest sandbox_tests.test_persistent_memory_manager tests.test_persistent_memory_ooda
  cd ouroboros_cockpit && npm run build
- Draai bredere tests wanneer haalbaar:
  python3 -m unittest discover sandbox_tests

Runtime smoke:
- Herstart backend als nodig.
- Check /health.
- Doe een veilige agentic smoke: een read-only vraag die memory_search + Brave/context of self_training_plan gebruikt.
- Bevestig dat events in backend response en Tauri UI zichtbaar zijn.

Definition of done:
- Een gebruiker ziet per agentische taak wat Ouroboros doet, waarom, met welk model, welke tools, welke approval nodig is, welke bestanden geraakt zijn, welke memory-write gebeurde en hoe hij kan herstellen of verdergaan.
- Geen fake success.
- Geen secrets gelekt.
- Geen vector stores/uploads/caches gecommit.
- Eindrapport bevat gewijzigde files, testresultaten, runtime smoke-resultaat en resterende beperkingen.
```

