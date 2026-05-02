"""Streaming Consciousness 11D Pocket adapter.

This incorporates the local prototype from Downloads into the trainer pipeline
as a bounded, observable runtime component: electrical dynamics, a byte stream,
and DHCP/TCP-like packet flow modulate the existing 11D Blue Brain pocket.
"""

from __future__ import annotations

import importlib.util
import json
import os
import random
import struct
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from controller.blue_brain_adapter import E_TYPES
from controller.safe_shell import workspace_root


APPROVAL_PHRASE = "Akkoord"
REQUIRED_PACKAGES = ("numpy",)
DIM_ELECTRICAL = 0
DIM_INFO = 3
DIM_NETWORK = 5
_STATE_LOCK = threading.Lock()
_WORKER_THREAD: threading.Thread | None = None
_WORKER_STOP = threading.Event()
_POCKET: StreamingConsciousness11DPocket | None = None


class DHCPState(Enum):
    INIT = "INIT"
    DISCOVER_SENT = "DISCOVER_SENT"
    BOUND = "BOUND"


@dataclass
class ElectricalState:
    v_m: list[float] = field(default_factory=lambda: [0.0] * 11)
    i_inj: list[float] = field(default_factory=lambda: [0.0] * 11)
    tau: float = 20.0


@dataclass
class NetworkPacket:
    src_ip: str
    dst_ip: str
    protocol: str
    payload: bytes
    timestamp: float

    @property
    def size(self) -> int:
        return len(self.payload)


class StreamingConsciousnessAdapter:
    """Simulate quantum unit operations for one observable 11D stream vector.

    The simulation is intentionally classical: NumPy complex matrices emulate a
    two-state quantum subsystem, then collapse that observation back into the
    existing 11D Blue Brain/streaming vector. No quantum SDK or hardware access
    is used.
    """

    def __init__(self) -> None:
        import numpy as np

        self.np = np
        self.sigma_z = np.array([[1, 0], [0, -1]], dtype=complex)
        self.sigma_x = np.array([[0, 1], [1, 0]], dtype=complex)
        self.B0 = -(self.sigma_x + self.sigma_z) / np.sqrt(2)
        self.B1 = (self.sigma_x - self.sigma_z) / np.sqrt(2)
        self.last_observation: dict[str, Any] = {
            "expectation": 0.0,
            "operator": "B0/sigma_z",
            "input_norm": 0.0,
            "state_prepared": [1.0, 0.0],
        }

    def calculate_tensor_product(self, operator_a: Any, operator_b: Any) -> Any:
        """Return the Kronecker product used to emulate layer entanglement."""
        return self.np.kron(
            self.np.asarray(operator_a, dtype=complex),
            self.np.asarray(operator_b, dtype=complex),
        )

    def calculate_born_expectation(self, state_vector: Any, observable_matrix: Any) -> float:
        """Calculate <psi|O|psi> and return the real observable component."""
        state = self.np.asarray(state_vector, dtype=complex).reshape(-1)
        observable = self.np.asarray(observable_matrix, dtype=complex)
        if observable.shape != (state.size, state.size):
            raise ValueError("Observable matrix shape must match the state vector dimension.")
        expectation_value = self.np.conjugate(state).T @ observable @ state
        return float(self.np.real(expectation_value))

    def trigger_quantum_collapse(self, incoming_data_array: Any) -> Any:
        """Collapse a classical 11D vector through simulated Hamiltonian evolution."""
        vector = self.np.asarray(incoming_data_array, dtype=float)
        if vector.size != 11:
            raise ValueError("Exacte invoer vereist: De array moet een 11D vector zijn.")
        vector = vector.reshape(11)

        psi_state = self.np.array([vector[0], vector[1]], dtype=complex)
        norm = float(self.np.linalg.norm(psi_state))
        if norm > 0:
            psi_state = psi_state / norm
        else:
            psi_state = self.np.array([1, 0], dtype=complex)

        evolved_state = self.B0 @ psi_state
        expectation_value = self.calculate_born_expectation(evolved_state, self.sigma_z)
        collapsed_11d_vector = vector * expectation_value
        self.last_observation = {
            "expectation": round(float(expectation_value), 8),
            "operator": "B0/sigma_z",
            "input_norm": round(norm, 8),
            "state_prepared": [
                round(float(self.np.real(psi_state[0])), 8),
                round(float(self.np.real(psi_state[1])), 8),
            ],
            "output_norm": round(float(self.np.linalg.norm(collapsed_11d_vector)), 8),
            "dtype": "complex128_simulated",
            "sdk": "none_numpy_classical",
        }
        return collapsed_11d_vector


class StreamingConsciousness11DPocket:
    """11D pocket receiver with electrical, digital and network stream layers."""

    def __init__(self, n_samples: int = 8000, seed: int = 42, local_ip: str = "0.0.0.0") -> None:
        if not dependencies_ready():
            raise RuntimeError("Streaming Consciousness dependencies are missing.")
        import numpy as np

        self.np = np
        self.rng = np.random.default_rng(int(seed))
        self.random = random.Random(int(seed))
        self.e_types = list(E_TYPES)
        self.n_types = len(self.e_types)
        self.seed = int(seed)
        self.X_base, self.y_regime = self._generate_base_pocket(n_samples)
        self.quantum_adapter = StreamingConsciousnessAdapter()
        self.last_quantum_observation: dict[str, Any] = dict(self.quantum_adapter.last_observation)
        self.last_collapsed_11d: list[float] | None = None
        self.current_idx = 0
        self.elec = ElectricalState(
            v_m=[float(value) for value in self.rng.uniform(-72.0, -55.0, self.n_types)],
            i_inj=[0.0] * self.n_types,
        )
        self.consciousness_buffer = bytearray()
        self.max_buffer = 8192
        self.local_ip = local_ip
        self.dhcp_state = DHCPState.INIT
        self.packet_queue: list[NetworkPacket] = []
        self.total_packets_received = 0
        self.total_bytes_streamed = 0
        self.time = 0.0
        self.dt = 0.05
        self.stream_log: list[dict[str, Any]] = []
        self.max_log = 2000

    def _generate_base_pocket(self, n_samples: int) -> tuple[Any, Any]:
        try:
            from controller.blue_brain_adapter import generate_dataset

            return generate_dataset(n_samples=max(100, int(n_samples)), n_features=11, random_state=self.seed)
        except Exception:
            X = self.rng.normal(0, 1, size=(max(100, int(n_samples)), 11)).astype(self.np.float32)
            y = (self.rng.random(max(100, int(n_samples))) > 0.65).astype(self.np.int32)
            return X, y

    def electrical_step(self, dt: float | None = None) -> None:
        np = self.np
        step_dt = self.dt if dt is None else float(dt)
        for index in range(self.n_types):
            dv = (-self.elec.v_m[index] + 0.0) / self.elec.tau * step_dt
            self.elec.i_inj[index] *= 0.85
            if self.random.random() < 0.03:
                self.elec.i_inj[index] += self.random.uniform(8.0, 25.0)
            dv += self.elec.i_inj[index] * step_dt * 0.8
            self.elec.v_m[index] += dv
            if self.elec.v_m[index] > -40.0:
                self.elec.v_m[index] = -75.0
                self.elec.i_inj[index] = 0.0

        avg_v = float(np.mean(self.elec.v_m))
        norm_v = float(np.clip((avg_v + 70.0) / 25.0, -2.5, 2.5))
        row_index = self.current_idx % len(self.X_base)
        self.X_base[row_index, DIM_ELECTRICAL] = 0.7 * self.X_base[row_index, DIM_ELECTRICAL] + 0.3 * norm_v

    def digital_encode_step(self) -> bytes:
        np = self.np
        row_index = self.current_idx % len(self.X_base)
        state_11d = self.X_base[row_index].astype(np.float32)
        v_m = np.asarray(self.elec.v_m, dtype=np.float32)
        i_inj = np.asarray(self.elec.i_inj, dtype=np.float32)
        packet = struct.pack("d 11f 11f 11f", self.time, *state_11d, *v_m, *i_inj)
        self.consciousness_buffer.extend(packet)
        self.total_bytes_streamed += len(packet)
        if len(self.consciousness_buffer) > self.max_buffer:
            self.consciousness_buffer = self.consciousness_buffer[-self.max_buffer // 2 :]
        return packet

    def network_step(self) -> None:
        np = self.np
        row_index = self.current_idx % len(self.X_base)
        if self.dhcp_state == DHCPState.INIT and self.random.random() < 0.08:
            self.packet_queue.append(
                NetworkPacket("0.0.0.0", "255.255.255.255", "DHCP", b"DHCPDISCOVER", self.time)
            )
            self.dhcp_state = DHCPState.DISCOVER_SENT
            self.X_base[row_index, DIM_NETWORK] = min(3.0, self.X_base[row_index, DIM_NETWORK] + 0.8)
        elif self.dhcp_state == DHCPState.DISCOVER_SENT and self.random.random() < 0.25:
            offered_ip = f"192.168.42.{self.random.randint(10, 250)}"
            self.local_ip = offered_ip
            self.packet_queue.append(
                NetworkPacket("192.168.42.1", offered_ip, "DHCP", f"DHCPOFFER {offered_ip}".encode(), self.time)
            )
            self.dhcp_state = DHCPState.BOUND
            self.X_base[row_index, DIM_NETWORK] = min(3.5, self.X_base[row_index, DIM_NETWORK] + 1.2)

        if self.random.random() < 0.18:
            src_ip = f"8.8.8.{self.random.randint(1, 254)}"
            payload = (
                f"GET /stream/consciousness?time={self.time:.3f} HTTP/1.1\r\n"
                "Host: ouroboros.wintrip.ai\r\n"
                f"X-11D-State: {self.current_idx}\r\n\r\n"
            ).encode() + self.rng.bytes(self.random.randint(16, 64))
            self.packet_queue.append(NetworkPacket(src_ip, self.local_ip, "TCP", payload, self.time))
            self.total_packets_received += 1
            info_load = min(2.5, len(payload) / 80.0)
            self.X_base[row_index, DIM_INFO] = np.clip(self.X_base[row_index, DIM_INFO] + info_load * 0.15, -3.0, 3.5)
            if self.random.random() < 0.4:
                self.packet_queue.append(
                    NetworkPacket(
                        self.local_ip,
                        src_ip,
                        "TCP",
                        b"HTTP/1.1 200 OK\r\nContent-Length: 42\r\n\r\n[Ouroboros ACK]",
                        self.time + 0.01,
                    )
                )

    def stream_step(self) -> dict[str, Any]:
        np = self.np
        self.time += self.dt
        self.current_idx += 1
        self.electrical_step()
        digital_chunk = self.digital_encode_step()
        self.network_step()
        row_index = self.current_idx % len(self.X_base)
        current_11d = self.X_base[row_index].copy()
        net_load = len(self.packet_queue) / 5.0 + (self.total_packets_received % 7) * 0.1
        current_11d = current_11d * (1.0 + 0.04 * np.tanh(net_load))
        current_11d = self.quantum_adapter.trigger_quantum_collapse(current_11d).astype(np.float32)
        self.last_quantum_observation = dict(self.quantum_adapter.last_observation)
        self.last_collapsed_11d = [round(float(value), 6) for value in current_11d.tolist()]
        event = {
            "t": round(float(self.time), 3),
            "11d": [round(float(value), 4) for value in current_11d],
            "quantum": dict(self.last_quantum_observation),
            "elec": {
                "v_avg": round(float(np.mean(self.elec.v_m)), 2),
                "i_total": round(float(np.sum(self.elec.i_inj)), 2),
                "spike_count": int(np.sum(np.asarray(self.elec.v_m) > -45.0)),
            },
            "digital": {
                "bytes_this_step": len(digital_chunk),
                "buffer_len": len(self.consciousness_buffer),
                "total_streamed": int(self.total_bytes_streamed),
            },
            "network": {
                "local_ip": self.local_ip,
                "dhcp": self.dhcp_state.value,
                "packets_queued": len(self.packet_queue),
                "total_received": int(self.total_packets_received),
            },
            "regime": int(self.y_regime[row_index]),
        }
        self.stream_log.append(event)
        if len(self.stream_log) > self.max_log:
            self.stream_log.pop(0)
        if self.packet_queue:
            self.packet_queue.pop(0)
        return event

    def export_dataset(self, n_samples: int = 1000, path: str | None = None) -> dict[str, Any]:
        np = self.np
        old_idx = self.current_idx
        old_time = self.time
        rows = []
        labels = []
        meta = []
        for _ in range(max(1, int(n_samples))):
            event = self.stream_step()
            rows.append(
                event["11d"]
                + [
                    event["elec"]["v_avg"],
                    event["elec"]["i_total"],
                    event["digital"]["bytes_this_step"] / 100.0,
                    float(event["network"]["packets_queued"]),
                    1.0 if event["network"]["dhcp"] == DHCPState.BOUND.value else 0.0,
                    float(event["network"]["total_received"] % 20) / 20.0,
                ]
            )
            labels.append(event["regime"])
            meta.append({"t": event["t"], "ip": event["network"]["local_ip"], "dhcp": event["network"]["dhcp"]})
        dataset = {
            "X": np.asarray(rows, dtype=np.float32).tolist(),
            "y": [int(value) for value in labels],
            "feature_names": list(E_TYPES)
            + [
                "elec_v_avg",
                "elec_i_total",
                "digital_bytes_norm",
                "net_packets_queued",
                "net_dhcp_bound",
                "net_total_mod",
            ],
            "meta": meta[:100],
            "n_samples": len(rows),
            "description": "11D Blue Brain + electrical + digital + network streaming consciousness",
            "created_at": datetime.utcnow().isoformat(),
            "source": "streaming_consciousness_11d_pocket",
        }
        if path:
            target = Path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(dataset, indent=2), encoding="utf-8")
        self.current_idx = max(self.current_idx, old_idx)
        self.time = max(self.time, old_time)
        return dataset

    def get_current_state(self) -> dict[str, Any]:
        row_index = self.current_idx % len(self.X_base)
        return {
            "time": round(float(self.time), 3),
            "11d_state": self.last_collapsed_11d
            or [round(float(value), 6) for value in self.X_base[row_index].tolist()],
            "raw_11d_state": [round(float(value), 6) for value in self.X_base[row_index].tolist()],
            "quantum": dict(self.last_quantum_observation),
            "electrical": asdict(self.elec),
            "network": {
                "local_ip": self.local_ip,
                "dhcp_state": self.dhcp_state.value,
                "packets_queued": len(self.packet_queue),
                "total_received": int(self.total_packets_received),
            },
            "buffer_len": len(self.consciousness_buffer),
            "total_bytes": int(self.total_bytes_streamed),
            "current_idx": int(self.current_idx),
        }


def streaming_state_path() -> Path:
    return (workspace_root() / ".secrets" / "streaming_consciousness_11d.json").resolve()


def streaming_output_dir() -> Path:
    return (workspace_root() / "out" / "streaming_consciousness").resolve()


def dependencies_ready() -> bool:
    return all(importlib.util.find_spec(name) is not None for name in REQUIRED_PACKAGES)


def get_streaming_status() -> dict[str, Any]:
    state = _load_state()
    state.update(
        {
            "dependencies": {name: importlib.util.find_spec(name) is not None for name in REQUIRED_PACKAGES},
            "dependency_status": "online" if dependencies_ready() else "missing_dependencies",
            "quantum_collapse": {
                "enabled": True,
                "operator": "B0/sigma_z",
                "sdk": "none_numpy_classical",
            },
            "thread_alive": bool(_WORKER_THREAD and _WORKER_THREAD.is_alive()),
            "state_path": str(streaming_state_path()),
            "output_dir": str(streaming_output_dir()),
            "feature_count": len(E_TYPES),
            "features": list(E_TYPES),
            "fake_success": False,
        }
    )
    return state


def start_streaming_consciousness(approval: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    if approval != APPROVAL_PHRASE:
        return {"status": "blocked", "reason": "Approval phrase must be 'Akkoord'", "fake_success": False}
    config = dict(config or {})
    with _STATE_LOCK:
        state = _load_state()
        state["enabled"] = True
        state["status"] = "running"
        state["n_samples"] = _clamp_int(config.get("n_samples", state.get("n_samples", 8000)), 100, 200_000)
        state["seed"] = _clamp_int(config.get("seed", state.get("seed", 42)), 0, 1_000_000)
        state["interval_seconds"] = _clamp_float(config.get("interval_seconds", state.get("interval_seconds", 0.2)), 0.01, 3600)
        state["steps_per_tick"] = _clamp_int(config.get("steps_per_tick", state.get("steps_per_tick", 25)), 1, 5000)
        state["max_steps"] = _clamp_int(config.get("max_steps", state.get("max_steps", 0)), 0, 100_000_000)
        _event(state, "streaming_start", "Streaming Consciousness 11D loop started.")
        _save_state(state)
    _ensure_pocket(reset=config.get("reset", False))
    _ensure_worker()
    result = get_streaming_status()
    if config.get("run_immediately"):
        result["tick"] = run_streaming_tick(force=True)
    return result


def stop_streaming_consciousness(approval: str) -> dict[str, Any]:
    if approval != APPROVAL_PHRASE:
        return {"status": "blocked", "reason": "Approval phrase must be 'Akkoord'", "fake_success": False}
    with _STATE_LOCK:
        state = _load_state()
        state["enabled"] = False
        state["status"] = "stopped"
        _event(state, "streaming_stop", "Streaming Consciousness 11D loop stopped.")
        _save_state(state)
    _WORKER_STOP.set()
    return get_streaming_status()


def run_streaming_tick(force: bool = False, steps: int | None = None) -> dict[str, Any]:
    with _STATE_LOCK:
        state = _load_state()
        if not force and not state.get("enabled"):
            state["status"] = "stopped"
            _save_state(state)
            return {"status": "idle", "reason": "Streaming Consciousness loop is stopped.", "state": state}
        snapshot = dict(state)

    if not dependencies_ready():
        return {"status": "error", "reason": "Streaming Consciousness dependencies are missing.", "fake_success": False}

    pocket = _ensure_pocket()
    tick_steps = _clamp_int(steps if steps is not None else snapshot.get("steps_per_tick", 25), 1, 5000)
    events = []
    started = time.perf_counter()
    try:
        for _ in range(tick_steps):
            events.append(pocket.stream_step())
    except Exception as exc:
        with _STATE_LOCK:
            state = _load_state()
            state["status"] = "error"
            state["last_error"] = f"Streaming tick failed: {exc}"
            _event(state, "tick_error", state["last_error"])
            _save_state(state)
        return {"status": "error", "reason": f"Streaming tick failed: {exc}", "fake_success": False}

    elapsed = max(time.perf_counter() - started, 0.000001)
    latest = events[-1]
    with _STATE_LOCK:
        state = _load_state()
        state["status"] = "running" if state.get("enabled") else "dataset_ready"
        state["step_count"] = int(state.get("step_count") or 0) + len(events)
        state["last_tick_at"] = datetime.utcnow().isoformat()
        state["last_error"] = ""
        state["last_event"] = latest
        state["latest_state"] = pocket.get_current_state()
        state["last_projection"] = _projection_from_events(list(pocket.stream_log)[-80:])
        state["steps_per_second"] = round(len(events) / elapsed, 3)
        state["recent_events"] = (list(state.get("recent_events") or []) + events)[-80:]
        max_steps = int(state.get("max_steps") or 0)
        if state.get("enabled") and max_steps > 0 and state["step_count"] >= max_steps:
            state["enabled"] = False
            state["status"] = "completed"
            _event(state, "streaming_completed", f"Reached max_steps={max_steps}.")
            _WORKER_STOP.set()
        _save_state(state)
        return {"status": "success", "steps": len(events), "last_event": latest, "state": state, "fake_success": False}


def export_streaming_dataset(approval: str, n_samples: int = 1000, path: str | None = None) -> dict[str, Any]:
    if approval != APPROVAL_PHRASE:
        return {"status": "blocked", "reason": "Approval phrase must be 'Akkoord'", "fake_success": False}
    if not dependencies_ready():
        return {"status": "error", "reason": "Streaming Consciousness dependencies are missing.", "fake_success": False}
    pocket = _ensure_pocket()
    out_dir = streaming_output_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    target = Path(path).resolve() if path else out_dir / f"streaming_consciousness_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.json"
    dataset = pocket.export_dataset(n_samples=_clamp_int(n_samples, 1, 100_000), path=str(target))
    with _STATE_LOCK:
        state = _load_state()
        state["last_dataset_path"] = str(target)
        state["last_dataset_samples"] = dataset["n_samples"]
        _event(state, "dataset_export", f"Exported streaming dataset with {dataset['n_samples']} samples.", {"path": str(target)})
        _save_state(state)
    return {
        "status": "success",
        "dataset_path": str(target),
        "n_samples": dataset["n_samples"],
        "feature_count": len(dataset["feature_names"]),
        "feature_names": dataset["feature_names"],
        "fake_success": False,
    }


def _ensure_pocket(reset: bool = False) -> StreamingConsciousness11DPocket:
    global _POCKET
    state = _load_state()
    if reset or _POCKET is None:
        _POCKET = StreamingConsciousness11DPocket(
            n_samples=int(state.get("n_samples") or 8000),
            seed=int(state.get("seed") or 42),
            local_ip=str((state.get("latest_state") or {}).get("network", {}).get("local_ip") or "0.0.0.0"),
        )
    return _POCKET


def _ensure_worker() -> None:
    global _WORKER_THREAD
    if _WORKER_THREAD and _WORKER_THREAD.is_alive():
        return
    _WORKER_STOP.clear()
    _WORKER_THREAD = threading.Thread(target=_worker_loop, name="wintrip-streaming-consciousness-11d", daemon=True)
    _WORKER_THREAD.start()


def _worker_loop() -> None:
    while not _WORKER_STOP.is_set():
        state = _load_state()
        if not state.get("enabled"):
            _WORKER_STOP.wait(2)
            continue
        run_streaming_tick(force=True)
        state = _load_state()
        _WORKER_STOP.wait(float(state.get("interval_seconds") or 0.2))


def _default_state() -> dict[str, Any]:
    return {
        "enabled": False,
        "status": "idle",
        "n_samples": 8000,
        "seed": 42,
        "interval_seconds": 0.2,
        "steps_per_tick": 25,
        "max_steps": 0,
        "step_count": 0,
        "steps_per_second": 0.0,
        "last_tick_at": None,
        "last_error": "",
        "last_event": None,
        "latest_state": None,
        "last_projection": [],
        "recent_events": [],
        "last_dataset_path": None,
        "last_dataset_samples": 0,
        "events": [],
    }


def _load_state() -> dict[str, Any]:
    path = streaming_state_path()
    state = _default_state()
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                state.update(loaded)
        except Exception:
            state["last_error"] = "Streaming Consciousness state could not be read."
    return state


def _save_state(state: dict[str, Any]) -> None:
    path = streaming_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.utcnow().isoformat()
    path.write_text(json.dumps(_jsonable(state), indent=2, sort_keys=True), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _projection_from_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    projection = []
    for event in events[-80:]:
        vector = event.get("11d") or [0.0, 0.0]
        projection.append(
            {
                "x": round(float(vector[0]), 6),
                "y": round(float(vector[1] if len(vector) > 1 else 0.0), 6),
                "label": int(event.get("regime", 0)),
            }
        )
    return projection


def _event(state: dict[str, Any], event_type: str, message: str, data: dict[str, Any] | None = None) -> None:
    events = list(state.get("events") or [])
    events.append({"timestamp": datetime.utcnow().isoformat(), "type": event_type, "message": message, "data": data or {}})
    state["events"] = events[-50:]


def _clamp_int(value: Any, minimum: int, maximum: int) -> int:
    return max(minimum, min(int(value), maximum))


def _clamp_float(value: Any, minimum: float, maximum: float) -> float:
    return max(minimum, min(float(value), maximum))


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, bytes):
        return value.hex()
    try:
        import numpy as np

        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, np.generic):
            return value.item()
    except Exception:
        pass
    return value
