from resonant_ouroboros.memory import InMemoryHippocampusMemory
from resonant_ouroboros.schema import ELEVEN_DIMENSIONS, build_11d_record


def test_record_has_exact_11d_vector_and_required_metadata():
    record = build_11d_record(
        physical_structure="webpage_screenshot_text",
        source_origin="https://example.com",
        path_or_proprioception="./app/data/screenshots/current_browser_view.png",
        relative_temporal_position="now",
        persona_actor="tester",
        intent_marker="learn:test",
        user_context_marker="unit_test",
        emotional_valence=0.33333,
        importance_score=0.8,
        karmic_weight=0.4,
        field_cluster_id="field_test",
        current_hz=426.0,
        vibration_mood="curious_scan",
    )
    assert len(record.vector()) == 11
    metadata = record.metadata()
    assert metadata["dimension_count"] == 11
    for field in ELEVEN_DIMENSIONS:
        assert field in metadata
    assert "current_hz" in metadata
    assert "vibration_mood" in metadata


def test_in_memory_store_and_search():
    memory = InMemoryHippocampusMemory()
    record = build_11d_record(
        physical_structure="seed_topic_text",
        source_origin="AGI Kennis.txt",
        path_or_proprioception="seed",
        relative_temporal_position="now",
        persona_actor="tester",
        intent_marker="seed",
        user_context_marker="seed",
        emotional_valence=0.0,
        importance_score=0.7,
        karmic_weight=0.5,
        field_cluster_id="field_linear_algebra",
        current_hz=419.0,
        vibration_mood="deep_read",
    )
    identifier = memory.store("linear algebra and calculus for AGI", record)
    assert identifier.startswith("memory_")
    assert memory.count() == 1
    rows = memory.search("linear algebra")
    assert rows
    assert rows[0]["id"] == identifier
