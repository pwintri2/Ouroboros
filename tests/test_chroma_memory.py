import pytest

from resonant_ouroboros.chroma_memory import ChromaHippocampusMemory, MemoryConfig
from resonant_ouroboros.schema import build_11d_record


chromadb = pytest.importorskip("chromadb")


def test_chroma_memory_upserts_exact_11d_records(tmp_path):
    memory = ChromaHippocampusMemory(
        MemoryConfig(persist_dir=tmp_path / "chroma", collection_name="test_ouroboros_11d")
    )
    record = build_11d_record(
        physical_structure="local_chat_turn",
        source_origin="unit",
        path_or_proprioception="chat",
        relative_temporal_position="now",
        persona_actor="tester",
        intent_marker="chat:test",
        user_context_marker="Jarosmalen graph memory",
        emotional_valence=0.2,
        importance_score=0.7,
        karmic_weight=0.6,
        field_cluster_id="field_chat_test",
        current_hz=426.0,
        vibration_mood="curious_scan",
    )
    identifier = memory.store("Jarosmalen graph memory connected to chat", record, record_id="stable")
    assert identifier == "stable"
    memory.store("Jarosmalen graph memory updated", record, record_id="stable")
    assert memory.count() == 1
    rows = memory.search("Jarosmalen graph", n_results=3)
    assert rows
    assert rows[0]["id"] == "stable"
    assert rows[0]["metadata"]["dimension_count"] == 11
    assert memory.info()["collection"] == "test_ouroboros_11d"
