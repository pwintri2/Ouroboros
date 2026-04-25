# 02 Orchestrator

## Architecture

The Fase 1 runtime is organized as a single frequency-driven loop:

1. `HertzOscillator` samples current vibration.
2. Browser behavior is derived from Hertz:
   - Low Hz: deeper reading, slower scroll, fewer link jumps.
   - High Hz/spike: more curiosity, higher temperature, more exploratory jumps.
3. `HumanBrowserEngine` performs real Playwright actions.
4. `VisionAnalyzer` receives screenshot plus visible text.
5. `PAEULoop` evaluates safety and stores the learned page/topic in memory.
6. `ChromaHippocampusMemory` persists exactly 11D vectors and metadata.

## 11D Hippocampus Schema

Every stored memory uses these exact fields:

1. `physical_structure`
2. `source_origin`
3. `path_or_proprioception`
4. `relative_temporal_position`
5. `persona_actor`
6. `intent_marker`
7. `user_context_marker`
8. `emotional_valence`
9. `importance_score`
10. `karmic_weight`
11. `field_cluster_id`

Additional required vibration fields:

- `current_hz`
- `vibration_mood`

## LangGraph Layer

`resonant_ouroboros/paeu_graph.py` defines a minimal LangGraph StateGraph:

`perceive -> act -> evaluate -> update -> END`

The graph is intentionally thin; real browser execution remains in `PAEULoop`
so safety and memory storage stay testable.

## Gordon Progress

`GordonBridge` writes progress to `/tmp/codex-workspace/gordon_progress.log`.
No Gordon Docker container was running during inspection, so no container
communication was attempted.
