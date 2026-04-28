import pytest

from resonant_ouroboros import quantum_memory
from resonant_ouroboros.quantum_memory import QuantumMemoryBody, allocate_11d_quantum_memory


pytestmark = pytest.mark.skipif(quantum_memory.np is None, reason="numpy is required for quantum memory allocation")


def test_allocate_11d_quantum_memory_is_seeded_by_position():
    position = [0.1, -0.2, 0.3, -0.4, 0.5, -0.6, 0.7, -0.8, 0.9, -1.0, 1.0]
    first = allocate_11d_quantum_memory(position, size_mb=1)
    second = allocate_11d_quantum_memory(position, size_mb=1)
    assert first.nbytes == 1024 * 1024
    assert first.dtype.name == "float32"
    assert (first == second).all()


def test_quantum_memory_body_pulse_writes_frequency_visualization():
    body = QuantumMemoryBody([0.01 * index for index in range(11)], size_mb=1)
    before = body.memory.copy()
    status = body.pulse(432.0, "curious_scan")
    assert status["allocated"] is True
    assert status["frequency_band"] == "baseline_418_432"
    assert status["visualization"]
    assert not (before == body.memory).all()

    spike = body.pulse(777.0, "creative_spike")
    assert spike["frequency_band"] == "creative_spike"
    assert spike["pulse_count"] == 2
