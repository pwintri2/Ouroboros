from resonant_ouroboros.evolution import EvolutionEvent, EvolutionEventStore


def test_evolution_scorecard_weights_status_and_lists_proposals(tmp_path):
    store = EvolutionEventStore(tmp_path / "evolution.jsonl")
    store.append(
        EvolutionEvent(
            event_type="chat",
            topic="identity",
            input_summary="human asked",
            output_summary="answer stored",
            importance=0.8,
            score_delta=0.1,
        )
    )
    store.append(
        EvolutionEvent(
            event_type="safe_action",
            topic="blocked command",
            input_summary="unsafe command",
            output_summary="blocked",
            status="blocked",
            importance=0.8,
            score_delta=0.1,
        )
    )
    proposal = store.reflect(
        "Fase 4",
        "self reflection",
        "Observation: link records better. Proposal: keep links bounded.",
        proposal_payload={"target_files": ["resonant_ouroboros/awake_keeper.py"]},
        status="approved",
        score_delta=0.14,
    )

    scorecard = store.scorecard()
    assert scorecard["score"] == 0.193
    assert scorecard["recent_delta"] == 0.193
    assert scorecard["proposal_events"] == 1
    assert scorecard["failed_or_blocked_events"] == 1
    assert "chat" in scorecard["by_type"]
    assert proposal["proposal_kind"] == "evolution_proposal"
    assert store.list_proposals(limit=5)[0]["id"] == proposal["id"]


def test_autonomy_scorecard_rewards_memory_links_and_approved_proposals(tmp_path):
    store = EvolutionEventStore(tmp_path / "evolution.jsonl")
    store.append(
        EvolutionEvent(
            event_type="chat",
            topic="memory assisted answer",
            input_summary="human asked",
            output_summary="answer used memory",
            prompt_context_record_ids=["r1", "r2", "r3"],
            score_delta=0.1,
        )
    )
    store.append(
        EvolutionEvent(
            event_type="knowledge_link",
            topic="memory assisted answer",
            input_summary="link input",
            output_summary="linked r1 to r2",
            record_ids=["source", "link", "r1", "r2"],
            score_delta=0.07,
        )
    )
    store.reflect(
        "Fase 4.5",
        "self reflection",
        "Observation: links are useful. Proposal: keep links visible.",
        status="approved",
        score_delta=0.14,
    )

    autonomy = store.autonomy_scorecard(
        runtime_status={"running": True, "current_hz": 425.0, "current_topic": "memory assisted answer"},
        action_summary={"pending_count": 0, "pending_evolution_proposals": 0, "failed_count": 0, "blocked_count": 0},
    )
    assert autonomy["score"] >= 70
    assert autonomy["level"] == "supervised_autonomy"
    assert autonomy["signals"]["memory_assisted_answers"] == 25.0
    assert autonomy["penalties"]["failed_or_blocked_events"] == 0
