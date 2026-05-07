"""Optional Cirq-backed quantum runtime for the 11D pocket.

The adapter keeps the 11D pocket as the source of truth. Cirq is used only as a
measurement/noise layer around one pocket vector: build a small circuit, sample
it through a local simulator, then fold bounded measurement statistics back into
the same 11 dimensions.
"""

from __future__ import annotations

import importlib
import math
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any


FALSE_VALUES = {"0", "false", "off", "no", "none", "disabled"}
TRUE_VALUES = {"1", "true", "on", "yes", "auto", "enabled"}


class CirqQuantumAdapter:
    """Small Cirq circuit layer for hardware-like local measurement semantics."""

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        repetitions: int | None = None,
        seed: int | None = None,
        noise_probability: float | None = None,
    ) -> None:
        mode = str(os.getenv("WINTRIP_CIRQ_QUANTUM", "auto") or "auto").strip().lower()
        self.requested = bool(enabled) if enabled is not None else mode not in FALSE_VALUES
        self.mode = "explicit" if enabled is not None else mode
        self.available = False
        self.reason = "disabled"
        self.warning = ""
        self.cirq: Any | None = None
        self.np: Any | None = None
        self.simulator: Any | None = None
        self.qubits: list[Any] = []
        self.backend = "none"
        self.source_path = str(os.getenv("WINTRIP_CIRQ_SOURCE_PATH") or "").strip()
        self.repetitions = _clamp_int(
            repetitions if repetitions is not None else os.getenv("WINTRIP_CIRQ_REPETITIONS", "96"),
            8,
            4096,
            default=96,
        )
        self.seed = _clamp_int(seed if seed is not None else os.getenv("WINTRIP_CIRQ_SEED", "42"), 0, 2**31 - 1, default=42)
        self.noise_probability = _clamp_float(
            noise_probability if noise_probability is not None else os.getenv("WINTRIP_CIRQ_NOISE_P", "0.0125"),
            0.0,
            0.25,
            default=0.0125,
        )
        self.last_observation: dict[str, Any] = self._base_status()
        if not self.requested:
            return
        self._try_enable()

    def project_11d(self, incoming_data_array: Any) -> tuple[Any, dict[str, Any]]:
        """Return a bounded 11D vector plus Cirq measurement telemetry."""

        np = self._numpy()
        vector = np.asarray(incoming_data_array, dtype=float).reshape(-1)
        if vector.size != 11:
            raise ValueError("Exacte invoer vereist: De array moet een 11D vector zijn.")
        if not bool(np.all(np.isfinite(vector))):
            raise ValueError("Exacte invoer vereist: De 11D vector mag geen NaN of inf bevatten.")
        vector = vector.astype(np.float64).reshape(11)

        if not self.available or self.cirq is None or self.simulator is None:
            observation = self._base_status()
            observation.update(
                {
                    "enabled": bool(self.requested),
                    "available": False,
                    "input_norm": round(float(np.linalg.norm(vector)), 8),
                    "output_norm": round(float(np.linalg.norm(vector)), 8),
                }
            )
            self.last_observation = observation
            return vector, dict(observation)

        circuit = self._build_circuit(vector)
        result = self.simulator.run(circuit, repetitions=self.repetitions)
        measurements = np.asarray(result.measurements.get("m", []), dtype=np.int8)
        if measurements.size == 0:
            projected = vector.copy()
            expectations = [0.0] * len(self.qubits)
            histogram: dict[str, int] = {}
            entropy_bits = 0.0
        else:
            measurements = measurements.reshape((-1, len(self.qubits)))
            expectations = [round(float(1.0 - 2.0 * float(np.mean(measurements[:, index]))), 8) for index in range(len(self.qubits))]
            histogram = _histogram_from_measurements(measurements)
            entropy_bits = _entropy_bits(histogram)
            mean_expectation = float(np.mean(expectations))
            collapse_gain = float(np.clip(0.72 + 0.28 * mean_expectation, 0.44, 1.0))
            feedback = np.zeros(11, dtype=np.float64)
            for index in range(11):
                feedback[index] = expectations[index % len(expectations)] * (0.018 + 0.004 * (index % 3))
            projected = np.clip(vector * collapse_gain + feedback, -3.5, 3.5)

        mean_expectation = float(np.mean(expectations)) if expectations else 0.0
        collapse_gain = float(np.clip(0.72 + 0.28 * mean_expectation, 0.44, 1.0))
        observation = self._base_status()
        observation.update(
            {
                "enabled": True,
                "available": True,
                "sdk": "cirq",
                "runtime": "cirq_density_matrix_local",
                "model": "11d_parameterized_noisy_measurement_circuit",
                "operator": "Cirq Circuit -> DensityMatrixSimulator.run(measurements)",
                "simulator": "DensityMatrixSimulator",
                "qubits": len(self.qubits),
                "moments": len(circuit),
                "repetitions": int(self.repetitions),
                "noise_model": "depolarizing_channel",
                "noise_probability": round(float(self.noise_probability), 8),
                "measurement_only": True,
                "expectation": round(mean_expectation, 8),
                "qubit_expectations_z": expectations,
                "histogram": dict(sorted(histogram.items(), key=lambda item: item[1], reverse=True)[:8]),
                "entropy_bits": round(float(entropy_bits), 8),
                "collapse_gain": round(float(collapse_gain), 8),
                "input_norm": round(float(np.linalg.norm(vector)), 8),
                "output_norm": round(float(np.linalg.norm(projected)), 8),
                "physical_quantum_hardware": False,
                "hardware_interface": False,
                "preserves_11d_pocket": True,
                "reality_boundary": (
                    "Cirq supplies real circuit, noise-channel and measurement semantics. "
                    "This is still local simulation, not physical quantum hardware."
                ),
            }
        )
        self.last_observation = observation
        return projected.astype(np.float64), dict(observation)

    def status(self) -> dict[str, Any]:
        return dict(self.last_observation)

    def _try_enable(self) -> None:
        self._add_source_paths()
        try:
            import numpy as np

            cirq = importlib.import_module("cirq")
        except Exception as exc:
            self.reason = "cirq_unavailable"
            self.warning = f"Cirq is not importable in this runtime: {exc}"
            self.last_observation = self._base_status()
            return

        self.np = np
        self.cirq = cirq
        try:
            self.qubits = list(cirq.LineQubit.range(4))
            noise = self._make_noise_model()
            self.simulator = cirq.DensityMatrixSimulator(noise=noise, seed=self.seed)
            self.available = True
            self.reason = "cirq_ready"
            self.backend = "cirq_core_density_matrix"
            self.last_observation = self._base_status()
        except Exception as exc:
            self.available = False
            self.reason = "cirq_initialization_failed"
            self.warning = f"Cirq initialized but simulator setup failed: {exc}"
            self.last_observation = self._base_status()

    def _build_circuit(self, vector: Any) -> Any:
        cirq = self.cirq
        assert cirq is not None
        q0, q1, q2, q3 = self.qubits
        angles = self._angles_from_11d(vector)
        circuit = cirq.Circuit()
        circuit.append(
            [
                cirq.rx(angles[0])(q0),
                cirq.ry(angles[1])(q1),
                cirq.rx(angles[2])(q2),
                cirq.rz(angles[3])(q3),
            ]
        )
        circuit.append([cirq.CNOT(q0, q1), cirq.CZ(q1, q2), cirq.CNOT(q2, q3)])
        circuit.append(
            [
                cirq.rz(angles[4])(q0),
                cirq.rx(angles[5])(q1),
                cirq.ry(angles[6])(q2),
                cirq.rx(angles[7])(q3),
            ]
        )
        circuit.append([cirq.CZ(q0, q2), cirq.CNOT(q3, q1)])
        circuit.append(
            [
                cirq.rz(angles[8])(q0),
                cirq.ry(angles[9])(q1),
                cirq.rx(angles[10])(q2),
                cirq.rz(sum(angles[:4]) / 4.0)(q3),
            ]
        )
        circuit.append(cirq.measure(q0, q1, q2, q3, key="m"))
        return circuit

    def _angles_from_11d(self, vector: Any) -> list[float]:
        np = self._numpy()
        arr = np.asarray(vector, dtype=float).reshape(11)
        norm_pressure = float(np.tanh(float(np.linalg.norm(arr)) / math.sqrt(11.0)))
        scale = math.pi * (0.35 + 0.55 * norm_pressure)
        return [float(np.clip(np.tanh(value) * scale, -math.pi, math.pi)) for value in arr.tolist()]

    def _make_noise_model(self) -> Any:
        cirq = self.cirq
        assert cirq is not None
        if self.noise_probability <= 0:
            return None
        channel = cirq.depolarize(p=float(self.noise_probability))
        try:
            return cirq.ConstantQubitNoiseModel(channel)
        except Exception:
            return channel

    def _add_source_paths(self) -> None:
        roots = [self.source_path, "/cirq", "/home/pwintri2/cirq"]
        for root_text in roots:
            if not root_text:
                continue
            root = Path(root_text)
            for child in ("cirq-core", "cirq-google", "cirq-aqt", "cirq-ionq", "cirq-pasqal"):
                candidate = root / child
                if candidate.exists():
                    text = str(candidate)
                    if text not in sys.path:
                        sys.path.insert(0, text)

    def _numpy(self) -> Any:
        if self.np is not None:
            return self.np
        import numpy as np

        self.np = np
        return np

    def _base_status(self) -> dict[str, Any]:
        return {
            "enabled": bool(self.requested),
            "available": bool(self.available),
            "requested_mode": self.mode,
            "reason": self.reason,
            "warning": self.warning,
            "sdk": "cirq" if self.available else "none",
            "runtime": self.backend,
            "model": "cirq_optional_11d_measurement_layer",
            "source_path": self.source_path,
            "repetitions": int(self.repetitions),
            "noise_probability": round(float(self.noise_probability), 8),
            "physical_quantum_hardware": False,
            "hardware_interface": False,
            "preserves_11d_pocket": True,
            "valuable_building_blocks": [
                "cirq.Circuit",
                "cirq.LineQubit",
                "cirq.DensityMatrixSimulator",
                "cirq.NoiseModel/depolarizing_channel",
                "measurement_histograms",
            ],
            "next_real_step": "Add a calibrated QVM/profile or an approval-gated remote sampler; do not store provider tokens.",
            "fake_success": False,
        }


def _histogram_from_measurements(measurements: Any) -> dict[str, int]:
    if measurements.size == 0:
        return {}
    bit_count = int(measurements.shape[1])
    counts: Counter[str] = Counter()
    for row in measurements.tolist():
        bitstring = "".join("1" if int(bit) else "0" for bit in row[:bit_count])
        counts[bitstring] += 1
    return dict(counts)


def _entropy_bits(histogram: dict[str, int]) -> float:
    total = float(sum(max(0, int(value)) for value in histogram.values()))
    if total <= 0:
        return 0.0
    entropy = 0.0
    for count in histogram.values():
        probability = max(0.0, float(count)) / total
        if probability > 0:
            entropy -= probability * math.log2(probability)
    return entropy


def _clamp_int(value: Any, minimum: int, maximum: int, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _clamp_float(value: Any, minimum: float, maximum: float, *, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))
