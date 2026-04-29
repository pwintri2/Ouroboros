from resonant_ouroboros.self_model import SelfModelStore


def test_self_model_persists_identity_runtime_and_reflections(tmp_path):
    path = tmp_path / "self_model.json"
    store = SelfModelStore(path, max_reflections=5)
    store.note_boot()
    store.update_runtime(
        current_hz=426.5,
        mood="curious_scan",
        current_topic="self model unit",
        last_action="unit_test",
        last_record_id="record_1",
    )
    reflection = store.reflect(
        event_type="knowledge_incorporated",
        summary="I connected a useful unit record to the persistent self model.",
        topic="self model unit",
        record_id="record_1",
        hz=426.5,
        mood="curious_scan",
        knowledge_kind="AGI Architecture",
    )
    store.update_autonomy(
        score=42.3,
        level="memory_assisted",
        trend="warming",
        summary="Unit autonomy snapshot.",
        signals={"memory_assisted_answers": 12.0},
        penalties={"pending_approvals": 0},
    )

    reloaded = SelfModelStore(path, max_reflections=5)
    snapshot = reloaded.snapshot()
    assert snapshot["identity"]["name"] == "Resonant Ouroboros"
    assert snapshot["runtime"]["current_hz"] == 426.5
    assert snapshot["recent_reflections"][-1]["id"] == reflection["id"]
    assert reloaded.status_summary()["last_reflection"].startswith("I connected")
    assert "self model unit" in reloaded.status_summary()["recent_topics"]
    assert reloaded.status_summary()["autonomy"]["score"] == 42.3
    assert "Autonomy: 42.3%" in reloaded.prompt_summary()


def test_periodic_reflection_runs_once_per_iteration(tmp_path):
    store = SelfModelStore(tmp_path / "self_model.json")
    first = store.maybe_periodic_reflection(
        iterations=5,
        interval=5,
        current_hz=424.0,
        mood="curious_scan",
        current_topic="periodic",
        last_records=[{"id": "r1", "text": "Recent 11D trace"}],
    )
    second = store.maybe_periodic_reflection(
        iterations=5,
        interval=5,
        current_hz=424.0,
        mood="curious_scan",
        current_topic="periodic",
        last_records=[{"id": "r1", "text": "Recent 11D trace"}],
    )
    assert first is not None
    assert second is None
    assert store.status_summary()["reflection_count"] == 1
    assert "Safe improvement proposal" in first["summary"]
    assert "suggested_improvement" in first["metadata"]
