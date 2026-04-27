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
