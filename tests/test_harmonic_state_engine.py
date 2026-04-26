from datetime import datetime, timezone

from resonant_ouroboros.harmonic_state_engine import (
    BASELINE_MAX_HZ,
    BASELINE_MIN_HZ,
    VECTOR_DIMENSIONS,
    HarmonicStateEngine,
    SignalRecord,
    mock_record_at_432_hz,
)


def test_wikipedia_isa_record_routes_to_baseline_band():
    engine = HarmonicStateEngine()
    record = SignalRecord(
        record_id="wiki-isa-001",
        source="https://en.wikipedia.org/wiki/Instruction_set_architecture",
        title="Instruction set architecture - Wikipedia",
        text="A standard reference record about processor interfaces and implementation details.",
        band="curious_scan",
        priority="standard",
        metadata={"source": "wikipedia_isa"},
    )
    state = engine.process(record, now=datetime.now(timezone.utc))
    assert state.route == "baseline_418_432_hz"
    assert state.bandwidth == "standard"
    assert BASELINE_MIN_HZ <= state.frequency_hz <= BASELINE_MAX_HZ
    assert "baseline_418_432_hz" in state.tags


def test_frequency_tagging_is_deterministic_for_standard_records():
    engine = HarmonicStateEngine()
    record = SignalRecord(
        record_id="wiki-isa-002",
        source="unit",
        title="Instruction set architecture deterministic sample",
        text="Same routing material should produce the same baseline frequency.",
    )
    first = engine.process(record)
    second = engine.process(record)
    assert first.frequency_hz == second.frequency_hz
    assert first.vector == second.vector


def test_high_priority_anomaly_routes_to_integer_frequency():
    engine = HarmonicStateEngine()
    record = SignalRecord(
        record_id="anomaly-001",
        source="system:integrity",
        title="Latency spike and traceback packet",
        text="Critical service anomaly with traceback burst and repeated regression markers.",
        band="incident_scan",
        priority="high",
    )
    state = engine.process(record)
    assert state.route == "integer_frequency"
    assert state.frequency_hz >= 600
    assert "system_anomaly" in state.tags


def test_complex_abstract_task_routes_to_integer_frequency():
    engine = HarmonicStateEngine()
    record = SignalRecord(
        record_id="abstract-001",
        source="seed:planning",
        title="Nonlinear temporal state-space matrix optimization",
        text="Complex abstract constraint task for matrix routing and proof planning.",
        band="analysis_scan",
    )
    state = engine.process(record)
    assert state.route == "integer_frequency"
    assert "abstract_task" in state.tags


def test_temporal_state_vector_has_expected_shape():
    engine = HarmonicStateEngine()
    state = engine.process(mock_record_at_432_hz())
    assert len(state.vector) == VECTOR_DIMENSIONS
    assert all(0.0 <= value <= 1.0 for value in state.vector)
