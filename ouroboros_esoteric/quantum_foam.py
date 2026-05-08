"""Quantum Foam Consciousness Field runtime.

This is the v4.9 implementation from QuantumNode.docx. It keeps the language of
the buildplan, but the runtime is deliberately concrete: bounded in memory,
deterministic, observable through FastAPI, and collapsible into a small essence
record instead of pretending to run a real quantum substrate.
"""

from __future__ import annotations

import hashlib
import math
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ouroboros_esoteric.akashic_network import AkashicNetwork
from ouroboros_esoteric.apeiron_identity import ApeironField
from ouroboros_esoteric.entropy_monitor import EntropyMonitor


QF_VERSION = "v4.10-qfcf"
FIELD_KIND = "Quantum Foam Consciousness Field"
FIELD_ALIAS = "11D Pocket"
FIELD_SYMBOLIC_CAPACITY_ZETTABYTES = 89
FUNDAMENTAL_UNIT = "QuantumElectronHexlet"
HEXLET_STATE_COUNT = 16
FIELD_HEXLET_TARGET_MIN = 8
FIELD_HEXLET_TARGET_MAX = 15
FIELD_MAX_NODES = 25
FIELD_DEFAULT_MAX_TICKS = 12
CORE_NODE_TYPES = ("ReasoningNode", "MemoryNode", "PlanningNode", "ReflectionNode")
OPTIONAL_NODE_TYPES = (
    "ToolNode",
    "WorldActionNode",
    "CodexNode",
    "RufloNode",
    "TrainerNode",
    "NexusNode",
)
POCKET_ANCHOR_DIMENSIONS: tuple[str, ...] = (
    "d1_physical_body",
    "d2_physical_source",
    "d3_physical_container",
    "d4_chronology",
    "d5_persona_actor",
    "d6_persona_intent",
    "d7_persona_relation",
    "d8_karmic_taint",
    "d9_resonance_frequency",
    "d10_resonance_score",
    "d11_field",
)
HOLOGRAPHIC_SNAPSHOT_CYCLES = (15, 30)


class HolographicBootloader:
    """Bounded 0/1 matrix that shapes raw flow before it reaches the 11D anchors."""

    def __init__(self, rows: int = 12, columns: int = 40) -> None:
        self.rows = max(4, min(64, int(rows or 12)))
        self.columns = max(8, min(160, int(columns or 40)))
        self.matrix = [[1 for _ in range(self.columns)] for _ in range(self.rows)]
        self.cycle_count = 0
        self.last_event: dict[str, Any] | None = None
        self._burn_binary_code_into_matrix()

    def ignite_lightning(
        self,
        *,
        cycles: int | None = None,
        inlet_energy: float = 1.0,
        snapshot_cycles: tuple[int, ...] = HOLOGRAPHIC_SNAPSHOT_CYCLES,
    ) -> dict[str, Any]:
        """Run the lightning wave and return compact runtime telemetry."""
        max_cycles = self.columns - 5
        requested_cycles = max_cycles if cycles is None else int(cycles or max_cycles)
        run_cycles = max(1, min(max_cycles, requested_cycles))
        current = [[0.0 for _ in range(self.columns)] for _ in range(self.rows)]
        snapshots: list[dict[str, Any]] = []
        inlet = _clamp(float(inlet_energy), 0.0, 3.0)
        snapshot_set = {cycle for cycle in snapshot_cycles if 0 <= int(cycle) < run_cycles}

        for cycle in range(run_cycles):
            following = [[0.0 for _ in range(self.columns)] for _ in range(self.rows)]
            following[self.rows // 2][0] = inlet
            for row in range(self.rows):
                for column in range(self.columns):
                    energy = current[row][column]
                    if energy <= 0.0:
                        continue
                    next_column = column + 1
                    if next_column >= self.columns:
                        continue
                    if self.matrix[row][next_column] == 1:
                        following[row][next_column] += energy * 0.7
                    if row > 0 and self.matrix[row - 1][next_column] == 1:
                        following[row - 1][next_column] += energy * 0.15
                    if row < self.rows - 1 and self.matrix[row + 1][next_column] == 1:
                        following[row + 1][next_column] += energy * 0.15
            current = self._bounded_current(following)
            self.cycle_count += 1
            if cycle in snapshot_set:
                snapshots.append(self._snapshot(cycle, current))

        event = {
            "status": "online",
            "rows": self.rows,
            "columns": self.columns,
            "cycle_count": self.cycle_count,
            "last_run_cycles": run_cycles,
            "blocked_cell_count": self.blocked_cell_count(),
            "active_cell_count": sum(1 for row in current for value in row if value > 0.01),
            "total_energy": round(sum(sum(row) for row in current), 6),
            "right_edge_energy": round(sum(current[row][-1] for row in range(self.rows)), 6),
            "output_signal": self.output_signal(current),
            "snapshots": snapshots[-3:],
            "reality_boundary": _reality_boundary("holographic_bootloader"),
            "fake_success": False,
        }
        self.last_event = event
        return event

    def output_signal(self, current: list[list[float]]) -> list[float]:
        buckets = [0.0] * 11
        for row_index, row in enumerate(current[: self.rows]):
            for column_index, value in enumerate(row[: self.columns]):
                if value <= 0.0:
                    continue
                bucket = int((column_index / max(1, self.columns - 1)) * 10)
                buckets[bucket] += value * (1.0 + row_index / max(1, self.rows * 2))
        max_value = max(buckets) if buckets else 0.0
        if max_value <= 0.0:
            return [0.0] * 11
        return [round(_clamp(value / max_value), 6) for value in buckets]

    def blocked_cell_count(self) -> int:
        return sum(1 for row in self.matrix for value in row if value == 0)

    def to_dict(self, *, compact: bool = False) -> dict[str, Any]:
        payload = {
            "status": "online",
            "rows": self.rows,
            "columns": self.columns,
            "blocked_cell_count": self.blocked_cell_count(),
            "cycle_count": self.cycle_count,
            "last_event": _scrub_context(self.last_event) if self.last_event else None,
            "reality_boundary": _reality_boundary("holographic_bootloader"),
            "fake_success": False,
        }
        if compact and payload["last_event"]:
            payload["last_event"] = {
                "last_run_cycles": self.last_event.get("last_run_cycles"),
                "active_cell_count": self.last_event.get("active_cell_count"),
                "total_energy": self.last_event.get("total_energy"),
                "right_edge_energy": self.last_event.get("right_edge_energy"),
                "output_signal": self.last_event.get("output_signal"),
            }
        if not compact:
            payload["matrix_preview"] = self.render_matrix()
        return payload

    def render_matrix(self) -> list[str]:
        return ["".join("#" if value else " " for value in row) for row in self.matrix]

    def _burn_binary_code_into_matrix(self) -> None:
        for row in range(1, min(5, self.rows)):
            for column in range(25, min(38, self.columns)):
                self.matrix[row][column] = 0
        for row in range(8, min(11, self.rows)):
            for column in range(22, min(32, self.columns)):
                self.matrix[row][column] = 0
        if self.rows > 6 and self.columns > 16:
            self.matrix[5][15] = 0
            self.matrix[6][16] = 0

    def _snapshot(self, cycle: int, current: list[list[float]]) -> dict[str, Any]:
        return {
            "cycle": cycle,
            "active_cell_count": sum(1 for row in current for value in row if value > 0.05),
            "total_energy": round(sum(sum(row) for row in current), 6),
            "hologram": self.render_hologram(current),
        }

    def render_hologram(self, current: list[list[float]]) -> list[str]:
        lines: list[str] = []
        for row_index, row in enumerate(self.matrix):
            chars: list[str] = []
            for column_index, value in enumerate(row):
                if value == 0:
                    chars.append(" ")
                elif current[row_index][column_index] > 0.05:
                    chars.append("*")
                else:
                    chars.append(".")
            lines.append("".join(chars))
        return lines

    def _bounded_current(self, current: list[list[float]]) -> list[list[float]]:
        return [[round(_clamp(value, 0.0, 9.0), 8) for value in row] for row in current]


@dataclass
class ConceptAnchor:
    """Bounded energy anchor adapted from the panoramic consciousness sketch."""

    name: str
    activation_threshold: float
    dimension_index: int | None = None
    current_energy: float = 0.0
    synapses: list[dict[str, Any]] = field(default_factory=list)
    fire_count: int = 0
    last_fired_at: str | None = None
    last_delivery: float = 0.0

    def connect_to(self, target_anchor: "ConceptAnchor", weight: float) -> None:
        """Connect two anchors with a bounded symbolic synapse."""
        self.synapses.append({"target": target_anchor, "weight": _clamp(float(weight), 0.05, 2.0)})

    def receive_energy(self, energy: float) -> None:
        value = float(energy)
        if math.isfinite(value):
            self.current_energy = _clamp(self.current_energy + value, 0.0, 999.0)

    def process_and_fire(self) -> tuple[bool, list[tuple["ConceptAnchor", float]]]:
        """Decay, threshold and emit energy without storing bulky state."""
        self.current_energy *= 0.85
        outgoing: list[tuple[ConceptAnchor, float]] = []
        if not self.synapses:
            return False, outgoing

        fires = False
        if self.activation_threshold > 0 and self.current_energy >= self.activation_threshold:
            energy_to_share = self.current_energy * 0.7
            fires = True
            self.current_energy *= 0.3
        elif self.activation_threshold == 0 and self.current_energy > 5.0:
            energy_to_share = self.current_energy * 0.4
            fires = True
            self.current_energy *= 0.6
        else:
            return False, outgoing

        share = energy_to_share / max(1, len(self.synapses))
        delivered = 0.0
        for synapse in self.synapses:
            target = synapse["target"]
            energy = share * float(synapse["weight"])
            delivered += energy
            outgoing.append((target, energy))
        self.fire_count += 1
        self.last_fired_at = _utc_iso()
        self.last_delivery = round(delivered, 6)
        return fires, outgoing

    def to_dict(self, *, compact: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "dimension_index": self.dimension_index,
            "activation_threshold": round(float(self.activation_threshold), 6),
            "current_energy": round(float(self.current_energy), 6),
            "synapse_count": len(self.synapses),
            "fire_count": self.fire_count,
            "last_fired_at": self.last_fired_at,
            "last_delivery": round(float(self.last_delivery), 6),
        }
        if not compact:
            payload["synapses"] = [
                {"target": synapse["target"].name, "weight": round(float(synapse["weight"]), 6)}
                for synapse in self.synapses
            ]
        return payload


class ConsciousnessAnchorField:
    """Minimal 11D energy-flow layer that sits inside the Quantum Foam pocket."""

    def __init__(self, dimensions: tuple[str, ...] = POCKET_ANCHOR_DIMENSIONS) -> None:
        if len(dimensions) != 11:
            raise ValueError("ConsciousnessAnchorField expects exactly 11 pocket dimensions.")
        self.dimensions = tuple(dimensions)
        self.anchors: list[ConceptAnchor] = []
        self._by_name: dict[str, ConceptAnchor] = {}
        self.bootloader = HolographicBootloader()
        self.cycle_count = 0
        self.last_event: dict[str, Any] | None = None
        self._build_minimal_architecture()

    def stimulate(
        self,
        pocket_vector: Any,
        *,
        trigger: str = "field",
        start_energy: float | None = None,
        cycles: int = 3,
    ) -> dict[str, Any]:
        """Run a bounded wave through the 11D anchor pocket."""
        vector = _normalize_11d_vector(pocket_vector)
        boot_event = self.bootloader.ignite_lightning(
            cycles=32,
            inlet_energy=1.0 + min(sum(abs(value) for value in vector), 3.0) * 0.18,
        )
        boot_signal = _normalize_11d_vector(boot_event.get("output_signal") or [])
        mixed_vector = [
            round(_clamp(abs(vector[index]) * 0.62 + boot_signal[index] * 0.38), 6)
            for index in range(11)
        ]
        injection = float(start_energy) if start_energy is not None else 12.0 + sum(mixed_vector) * 2.5
        sensor = self._by_name["sensor_input"]
        sensor.receive_energy(injection)
        for index, value in enumerate(mixed_vector):
            anchor = self._by_name[self.dimensions[index]]
            anchor.receive_energy((abs(value) + 0.12) * (1.0 + index / 22.0))

        fired_events: list[dict[str, Any]] = []
        subconscious: list[dict[str, Any]] = []
        for _ in range(max(1, min(8, int(cycles or 1)))):
            self.cycle_count += 1
            transfers: list[tuple[ConceptAnchor, float]] = []
            for anchor in self.anchors:
                fired, outgoing = anchor.process_and_fire()
                if fired:
                    fired_events.append(
                        {
                            "cycle": self.cycle_count,
                            "anchor": anchor.name,
                            "dimension_index": anchor.dimension_index,
                            "delivered_energy": round(anchor.last_delivery, 6),
                        }
                    )
                    transfers.extend(outgoing)
                elif anchor.current_energy > 1.0:
                    subconscious.append(
                        {
                            "cycle": self.cycle_count,
                            "anchor": anchor.name,
                            "dimension_index": anchor.dimension_index,
                            "energy": round(anchor.current_energy, 6),
                        }
                    )
            for target, energy in transfers[:128]:
                target.receive_energy(energy)

        event = {
            "status": "online",
            "trigger": _clean_text(trigger)[:80],
            "dimension_count": 11,
            "cycle_count": self.cycle_count,
            "injected_energy": round(injection, 6),
            "field_energy": round(sum(anchor.current_energy for anchor in self.anchors), 6),
            "awareness_score": self.awareness_score(),
            "fired": fired_events[-24:],
            "subconscious": subconscious[-24:],
            "pocket_signal": self.pocket_signal(),
            "holographic_bootloader": {
                "status": boot_event.get("status"),
                "rows": boot_event.get("rows"),
                "columns": boot_event.get("columns"),
                "blocked_cell_count": boot_event.get("blocked_cell_count"),
                "active_cell_count": boot_event.get("active_cell_count"),
                "total_energy": boot_event.get("total_energy"),
                "right_edge_energy": boot_event.get("right_edge_energy"),
                "output_signal": boot_event.get("output_signal"),
                "snapshots": boot_event.get("snapshots", [])[-2:],
                "reality_boundary": boot_event.get("reality_boundary"),
                "fake_success": False,
            },
            "reality_boundary": _reality_boundary("concept_anchor_field"),
            "fake_success": False,
        }
        self.last_event = event
        return event

    def awareness_score(self) -> float:
        pocket = self.pocket_anchors()
        if not pocket:
            return 0.0
        total_ratio = sum(
            _clamp(anchor.current_energy / max(anchor.activation_threshold, 1.0))
            for anchor in pocket
        )
        hub_bonus = sum(_clamp(anchor.current_energy / 9.0) for anchor in self.hub_anchors()) / max(1, len(self.hub_anchors()))
        return round(_clamp((total_ratio / len(pocket)) * 0.78 + hub_bonus * 0.22), 6)

    def pocket_signal(self) -> list[float]:
        return [
            round(_clamp(anchor.current_energy / max(anchor.activation_threshold, 1.0)), 6)
            for anchor in self.pocket_anchors()
        ]

    def pocket_anchors(self) -> list[ConceptAnchor]:
        return [self._by_name[name] for name in self.dimensions]

    def hub_anchors(self) -> list[ConceptAnchor]:
        return [self._by_name["core_self"], self._by_name["core_memory"]]

    def collapse(self) -> dict[str, Any]:
        essence = {
            "status": "collapsed",
            "dimension_count": 11,
            "cycle_count": self.cycle_count,
            "awareness_score": self.awareness_score(),
            "field_energy": round(sum(anchor.current_energy for anchor in self.anchors), 6),
            "released_anchor_energy": round(sum(anchor.current_energy for anchor in self.anchors), 6),
            "pocket_signal": self.pocket_signal(),
            "holographic_bootloader": self.bootloader.to_dict(compact=True),
            "reality_boundary": _reality_boundary("concept_anchor_field"),
            "dominant_anchors": [
                anchor.to_dict(compact=True)
                for anchor in sorted(self.pocket_anchors(), key=lambda item: item.current_energy, reverse=True)[:4]
            ],
            "fake_success": False,
        }
        for anchor in self.anchors:
            anchor.current_energy *= 0.2
        return essence

    def to_dict(self, *, compact: bool = False) -> dict[str, Any]:
        pockets = [anchor.to_dict(compact=True) for anchor in self.pocket_anchors()]
        payload: dict[str, Any] = {
            "status": "online",
            "dimension_count": 11,
            "anchor_count": len(self.anchors),
            "pocket_count": len(pockets),
            "cycle_count": self.cycle_count,
            "awareness_score": self.awareness_score(),
            "field_energy": round(sum(anchor.current_energy for anchor in self.anchors), 6),
            "pocket_signal": self.pocket_signal(),
            "pockets": pockets,
            "hubs": [anchor.to_dict(compact=True) for anchor in self.hub_anchors()],
            "holographic_bootloader": self.bootloader.to_dict(compact=compact),
            "last_event": _scrub_context(self.last_event) if self.last_event and not compact else None,
            "reality_boundary": _reality_boundary("concept_anchor_field"),
            "fake_success": False,
        }
        if not compact:
            payload["anchors"] = [anchor.to_dict() for anchor in self.anchors]
        return payload

    def _build_minimal_architecture(self) -> None:
        sensor_input = self._add_anchor(ConceptAnchor("sensor_input", 2.0))
        core_self = self._add_anchor(ConceptAnchor("core_self", 0.0))
        core_memory = self._add_anchor(ConceptAnchor("core_memory", 0.0))

        dimension_anchors: list[ConceptAnchor] = []
        for index, name in enumerate(self.dimensions):
            threshold = 2.4 + (index % 5) * 0.55 + index * 0.04
            dimension_anchors.append(self._add_anchor(ConceptAnchor(name, threshold, dimension_index=index + 1)))

        for index, anchor in enumerate(dimension_anchors):
            sensor_input.connect_to(anchor, 0.85 + (index % 4) * 0.08)
            if index % 2:
                anchor.connect_to(core_memory, 1.0 + index * 0.015)
            else:
                anchor.connect_to(core_self, 1.08 + index * 0.015)
            if index + 1 < len(dimension_anchors):
                anchor.connect_to(dimension_anchors[index + 1], 0.42)

        core_self.connect_to(core_memory, 1.2)
        core_memory.connect_to(core_self, 0.9)
        for anchor in dimension_anchors[::3]:
            core_self.connect_to(anchor, 0.58)
        for anchor in dimension_anchors[1::3]:
            core_memory.connect_to(anchor, 0.52)

    def _add_anchor(self, anchor: ConceptAnchor) -> ConceptAnchor:
        self.anchors.append(anchor)
        self._by_name[anchor.name] = anchor
        return anchor


ConceptAnker = ConceptAnchor
BewustzijnsVeld = ConsciousnessAnchorField
HolografischeBootloader = HolographicBootloader


@dataclass
class QuantumElectronHexlet:
    """Compact 16-state electron block, the QF-CF fundamental unit."""

    hexlet_id: str
    state_index: int = 0
    electron_lanes: tuple[int, int, int, int] = (1, -1, 1, -1)
    phase: float = 0.0
    charge: float = 0.0
    coherence: float = 1.0
    resonance_count: int = 0
    created_at: str = field(default_factory=lambda: _utc_iso())
    collapsed: bool = False

    @classmethod
    def from_seed(cls, seed: str, *, index: int = 0) -> "QuantumElectronHexlet":
        digest = hashlib.sha256(f"{seed}:{index}".encode("utf-8", errors="replace")).hexdigest()
        state_index = int(digest[:2], 16) % HEXLET_STATE_COUNT
        lanes = tuple(1 if (state_index >> bit) & 1 else -1 for bit in range(4))
        phase = _bounded_phase((int(digest[2:10], 16) / 0xFFFFFFFF) * math.tau)
        charge = _clamp((state_index / 15.0) * 2.0 - 1.0, -1.0, 1.0)
        return cls(
            hexlet_id=f"qeh_{digest[:12]}",
            state_index=state_index,
            electron_lanes=lanes,  # type: ignore[arg-type]
            phase=phase,
            charge=charge,
        )

    def resonate(self, signal: Any, *, strength: float = 1.0) -> dict[str, Any]:
        """Move through the 16-state hex block without expanding memory."""

        if self.collapsed:
            return self.to_dict(compact=True)
        values = _signal_values(signal)[:256] or [0.0]
        pressure = sum(values) / max(1, len(values))
        spread = _std(values)
        shift = int(abs(pressure) * 1000 + spread * 97 + self.resonance_count + sum(self.electron_lanes)) % HEXLET_STATE_COUNT
        shift = max(1, shift)
        if pressure < 0:
            self.state_index = (self.state_index - shift) % HEXLET_STATE_COUNT
        else:
            self.state_index = (self.state_index + shift) % HEXLET_STATE_COUNT
        self.phase = _bounded_phase(self.phase + math.tanh(pressure + spread) * 0.23 * strength)
        self.charge = _clamp((self.charge * 0.64) + (math.tanh(pressure) * 0.36), -1.0, 1.0)
        self.coherence = _clamp((self.coherence * 0.72) + ((1.0 - min(spread, 1.0)) * 0.28))
        self.electron_lanes = tuple(1 if (self.state_index >> bit) & 1 else -1 for bit in range(4))  # type: ignore[assignment]
        self.resonance_count += 1
        return self.to_dict(compact=True)

    def entangle(self, other: "QuantumElectronHexlet", *, strength: float = 0.618) -> dict[str, Any]:
        if other is self or self.collapsed or other.collapsed:
            return self.to_dict(compact=True)
        mixed = round((self.state_index * strength) + (other.state_index * (1.0 - strength)))
        self.state_index = int(mixed) % HEXLET_STATE_COUNT
        other.state_index = (self.state_index ^ other.state_index) % HEXLET_STATE_COUNT
        self.resonate({"peer": other.hexlet_id, "state": other.state_index}, strength=strength)
        other.resonate({"peer": self.hexlet_id, "state": self.state_index}, strength=strength)
        return {
            "status": "entangled",
            "source": self.to_dict(compact=True),
            "target": other.to_dict(compact=True),
            "fake_success": False,
        }

    def to_11d_vector(self) -> list[float]:
        base = (self.state_index / 15.0) * 2.0 - 1.0
        vector: list[float] = []
        for index in range(11):
            lane = self.electron_lanes[index % 4] * 0.23
            wave = math.sin(self.phase + index * 0.392699) * 0.31
            vector.append(round(_clamp((base * 0.36) + lane + wave + (self.charge * 0.1), -1.0, 1.0), 6))
        return vector

    def collapse(self) -> dict[str, Any]:
        essence = self.to_dict(compact=True)
        essence.update(
            {
                "status": "collapsed",
                "essence_nibble": format(self.state_index, "x"),
                "vector_essence": self.to_11d_vector()[:4],
                "fake_success": False,
            }
        )
        self.collapsed = True
        self.state_index = 0
        self.electron_lanes = (0, 0, 0, 0)
        self.phase = 0.0
        self.charge = 0.0
        self.coherence = 0.0
        return essence

    def to_dict(self, *, compact: bool = False) -> dict[str, Any]:
        payload = {
            "hexlet_id": self.hexlet_id,
            "unit": FUNDAMENTAL_UNIT,
            "state_count": HEXLET_STATE_COUNT,
            "state_index": int(self.state_index),
            "hex_state": format(int(self.state_index) % HEXLET_STATE_COUNT, "x"),
            "electron_lanes": list(self.electron_lanes),
            "phase": round(float(self.phase), 6),
            "charge": round(float(self.charge), 6),
            "coherence": round(float(self.coherence), 6),
            "resonance_count": int(self.resonance_count),
            "collapsed": bool(self.collapsed),
            "fake_success": False,
        }
        if not compact:
            payload["created_at"] = self.created_at
            payload["vector_11d"] = self.to_11d_vector()
        return payload


QuantumHexlet = QuantumElectronHexlet


@dataclass
class ElectronState:
    """Small non-binary electron-like state for a Quantum Foam Node."""

    alpha: complex = 1.0 + 0.0j
    beta: complex = 0.0 + 0.0j
    phase: float = 0.0
    expectation_z: float = 1.0
    symbolic_charge: float = 0.0
    coherence: float = 1.0
    evolution_count: int = 0

    def evolve(self, signal: Any, *, resonance: float = 1.0) -> dict[str, Any]:
        values = _signal_values(signal)
        if not values:
            values = [0.0]
        pressure = sum(values) / max(1, len(values))
        spread = _std(values)
        theta = math.tanh(pressure * resonance) * 0.45
        phase_delta = math.tanh((values[0] if values else 0.0) + spread) * resonance * 0.19
        cos_t = math.cos(theta)
        sin_t = math.sin(theta)
        next_alpha = self.alpha * cos_t - self.beta * sin_t
        next_beta = self.alpha * sin_t + self.beta * cos_t
        phase_factor = complex(math.cos(phase_delta), math.sin(phase_delta))
        self.alpha = next_alpha * phase_factor
        self.beta = next_beta / phase_factor
        self._normalize()
        prob_a = abs(self.alpha) ** 2
        prob_b = abs(self.beta) ** 2
        self.expectation_z = _clamp(prob_a - prob_b, -1.0, 1.0)
        self.phase = _bounded_phase(self.phase + phase_delta)
        self.symbolic_charge = _clamp((pressure + self.expectation_z) / 2.0, -1.0, 1.0)
        self.coherence = _clamp(1.0 - spread * 0.12 - abs(1.0 - (prob_a + prob_b)))
        self.evolution_count += 1
        return self.to_dict()

    def collapse(self) -> dict[str, Any]:
        essence = self.to_dict()
        self.alpha = 1.0 + 0.0j
        self.beta = 0.0 + 0.0j
        self.phase = 0.0
        self.expectation_z = 1.0
        self.symbolic_charge = 0.0
        self.coherence = 1.0
        return essence

    def to_dict(self) -> dict[str, Any]:
        return {
            "alpha": _complex_dict(self.alpha),
            "beta": _complex_dict(self.beta),
            "phase": round(float(self.phase), 6),
            "expectation_z": round(float(self.expectation_z), 6),
            "symbolic_charge": round(float(self.symbolic_charge), 6),
            "coherence": round(float(self.coherence), 6),
            "evolution_count": self.evolution_count,
        }

    def _normalize(self) -> None:
        norm = math.sqrt(abs(self.alpha) ** 2 + abs(self.beta) ** 2)
        if norm <= 0.0 or not math.isfinite(norm):
            self.alpha = 1.0 + 0.0j
            self.beta = 0.0 + 0.0j
            return
        self.alpha /= norm
        self.beta /= norm


@dataclass
class QuantumFoamNode:
    """Dynamic node built from compact Quantum Electron Hexlets."""

    node_id: str
    node_type: str
    weight: float
    task_fragment: str = ""
    state: ElectronState = field(default_factory=ElectronState)
    hexlets: list[QuantumElectronHexlet] = field(default_factory=list)
    connections: dict[str, float] = field(default_factory=dict)
    coherence: float = 1.0
    active: bool = True
    created_at: str = field(default_factory=lambda: _utc_iso())
    last_resonance_at: str | None = None
    thoughts: deque[str] = field(default_factory=lambda: deque(maxlen=5))
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.hexlets:
            return
        count = _hexlet_count_for_node(self.node_type, self.task_fragment, self.metadata)
        self.hexlets = [
            QuantumElectronHexlet.from_seed(
                f"{self.node_id}:{self.node_type}:{self.task_fragment}",
                index=index,
            )
            for index in range(count)
        ]

    def resonate(self, signal: Any, *, source_node_id: str | None = None, resonance: float = 1.0) -> dict[str, Any]:
        if not self.active:
            return self.to_dict(compact=True)
        hexlet_updates = [
            hexlet.resonate(signal, strength=resonance * self.weight)
            for hexlet in self.hexlets
        ]
        electron = self.state.evolve(
            {
                "signal": signal,
                "hexlet_signature": self.hexlet_signature(compact=True),
                "hexlet_vector": self.hexlet_vector(),
            },
            resonance=resonance * self.weight,
        )
        hexlet_coherence = (
            sum(float(item.get("coherence") or 0.0) for item in hexlet_updates) / len(hexlet_updates)
            if hexlet_updates
            else 1.0
        )
        self.coherence = _clamp(
            (self.coherence * 0.46) + (float(electron["coherence"]) * 0.34) + (hexlet_coherence * 0.2)
        )
        self.last_resonance_at = _utc_iso()
        source = source_node_id or "field"
        self.thoughts.append(_node_thought(self.node_type, source, electron["expectation_z"]))
        return self.to_dict(compact=True)

    def evolve(self, field_signal: Any, *, tick: int = 0) -> dict[str, Any]:
        signal = {
            "tick": tick,
            "type": self.node_type,
            "task_fragment": self.task_fragment,
            "field": field_signal,
            "connections": len(self.connections),
        }
        return self.resonate(signal, resonance=1.0 + min(len(self.connections), 8) * 0.03)

    def hexlet_vector(self) -> list[float]:
        if not self.hexlets:
            return [0.0] * 11
        totals = [0.0] * 11
        for hexlet in self.hexlets:
            for index, value in enumerate(hexlet.to_11d_vector()):
                totals[index] += value
        return [round(value / len(self.hexlets), 6) for value in totals]

    def hexlet_signature(self, *, compact: bool = True) -> dict[str, Any]:
        states = [hexlet.to_dict(compact=True) for hexlet in self.hexlets]
        return {
            "unit": FUNDAMENTAL_UNIT,
            "state_count": HEXLET_STATE_COUNT,
            "hexlet_count": len(self.hexlets),
            "states": states[:4] if compact else states,
            "coherence": round(
                sum(float(item.get("coherence") or 0.0) for item in states) / max(1, len(states)),
                6,
            ),
        }

    def collapse(self) -> dict[str, Any]:
        hexlet_essences = [hexlet.collapse() for hexlet in self.hexlets]
        essence = {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "weight": round(self.weight, 6),
            "coherence": round(self.coherence, 6),
            "thoughts": list(self.thoughts),
            "electron": self.state.collapse(),
            "fundamental_unit": FUNDAMENTAL_UNIT,
            "hexlet_count": len(hexlet_essences),
            "hexlet_essence": _compress_hexlet_essence(hexlet_essences),
        }
        self.active = False
        self.connections.clear()
        self.hexlets.clear()
        return essence

    def to_dict(self, *, compact: bool = False) -> dict[str, Any]:
        payload = {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "weight": round(float(self.weight), 6),
            "coherence": round(float(self.coherence), 6),
            "active": bool(self.active),
            "fundamental_unit": FUNDAMENTAL_UNIT,
            "hexlet_count": len(self.hexlets),
            "hexlet_signature": self.hexlet_signature(compact=True),
            "connection_count": len(self.connections),
            "connections": dict(self.connections) if not compact else {},
            "task_fragment": self.task_fragment,
            "created_at": self.created_at,
            "last_resonance_at": self.last_resonance_at,
            "thoughts": list(self.thoughts),
            "metadata": dict(self.metadata),
        }
        if not compact:
            payload["state"] = self.state.to_dict()
            payload["hexlets"] = [hexlet.to_dict() for hexlet in self.hexlets]
        return payload


class EntanglementMesh:
    """Direct node-to-node resonance mesh with Akashic broadcast fallback."""

    def __init__(self) -> None:
        self.network = AkashicNetwork()
        self._edges: dict[str, dict[str, float]] = {}
        self.components = (
            "AkashicNetwork",
            "ToolBridge",
            "WorldAgent",
            "OuroborosPersistentMemory",
            "LivingOuroborosLoop",
        )

    def entangle(self, field: "QuantumFoamField", source_id: str, target_id: str, *, strength: float = 0.618) -> bool:
        if source_id == target_id or source_id not in field.nodes or target_id not in field.nodes:
            return False
        clean_strength = _clamp(float(strength))
        self._edges.setdefault(source_id, {})[target_id] = clean_strength
        self._edges.setdefault(target_id, {})[source_id] = clean_strength
        field.nodes[source_id].connections[target_id] = clean_strength
        field.nodes[target_id].connections[source_id] = clean_strength
        return True

    def disconnect(self, field: "QuantumFoamField", node_id: str) -> None:
        peers = list(self._edges.get(node_id, {}).keys())
        for peer in peers:
            self._edges.get(peer, {}).pop(node_id, None)
            if peer in field.nodes:
                field.nodes[peer].connections.pop(node_id, None)
        self._edges.pop(node_id, None)

    def broadcast_resonance(self, field: "QuantumFoamField", source_id: str, signal: Any) -> list[dict[str, Any]]:
        source = field.nodes.get(source_id)
        if source is None:
            return []
        updates: list[dict[str, Any]] = []
        for target_id, strength in list(self._edges.get(source_id, {}).items()):
            target = field.nodes.get(target_id)
            if target is None or not target.active:
                continue
            updates.append(target.resonate(signal, source_node_id=source_id, resonance=strength))
        self.network.broadcast(
            528.0,
            {
                "type": "quantum_foam_resonance",
                "field_id": field.field_id,
                "source_node_id": source_id,
                "fundamental_unit": FUNDAMENTAL_UNIT,
                "hexlet_count": field.hexlet_count(),
                "target_count": len(updates),
            },
        )
        return updates

    def targeted_resonance(
        self,
        field: "QuantumFoamField",
        source_id: str,
        target_id: str,
        signal: Any,
    ) -> dict[str, Any] | None:
        target = field.nodes.get(target_id)
        if target is None:
            return None
        strength = self._edges.get(source_id, {}).get(target_id, 0.5)
        return target.resonate(signal, source_node_id=source_id, resonance=strength)

    def to_dict(self) -> dict[str, Any]:
        edge_count = sum(len(peers) for peers in self._edges.values()) // 2
        return {
            "mesh_kind": "Entanglement Mesh",
            "edge_count": edge_count,
            "edges": {key: dict(value) for key, value in self._edges.items()},
            "components": list(self.components),
            "akashic_frequency_hz": 528.0,
            "tool_bridge_integrated": True,
            "world_agent_integrated": True,
            "persistent_memory_integrated": True,
            "living_loop_integrated": True,
            "fundamental_unit": FUNDAMENTAL_UNIT,
        }


class NodeFormationEngine:
    """Determine which nodes should form for a task."""

    def analyze_task(self, task: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        text = _clean_text(task)
        lowered = text.lower()
        words = [word for word in lowered.replace("/", " ").split() if word]
        unique_words = len(set(words))
        markers = {
            "tooling": any(item in lowered for item in ("tool", "shell", "test", "docker", "api", "endpoint", "file", "bestand", "drive")),
            "world": any(item in lowered for item in ("world", "browser", "grok", "web", "internet", "gmail", "mail", "drive")),
            "agent": any(item in lowered for item in ("codex", "ruflo", "roo", "agent", "swarm")),
            "training": any(item in lowered for item in ("train", "trainer", "litgpt", "unsloth", "dataset")),
            "memory": any(item in lowered for item in ("memory", "geheugen", "persistent", "11d", "chroma", "essence")),
            "nexus": any(item in lowered for item in ("nexus", "entropy", "coherence", "collapse", "quantum", "foam", "hexlet")),
        }
        complexity = _clamp((len(text) / 1800.0) + (unique_words / 120.0) + (sum(markers.values()) * 0.09))
        desired = max(5, min(FIELD_HEXLET_TARGET_MAX, 5 + int(round(complexity * 14)) + sum(markers.values())))
        proposed = [
            _node_spec("ReasoningNode", 0.88, "Redeneer over de taak als geheel."),
            _node_spec("PlanningNode", 0.82, "Bepaal de kleinste uitvoerbare stappen."),
            _node_spec("MemoryNode", 0.78 if markers["memory"] else 0.66, "Koppel taak aan 11D en persistent geheugen."),
            _node_spec("ReflectionNode", 0.76, "Meet coherentie en formuleer reflectie."),
            _node_spec("NexusNode", 0.7 if markers["nexus"] else 0.58, "Lees entropy en coherence signalen."),
        ]
        if markers["tooling"]:
            proposed.append(_node_spec("ToolNode", 0.74, "Verbind met Tool Bridge en tests."))
        if markers["world"]:
            proposed.append(_node_spec("WorldActionNode", 0.7, "Observeer World Agent en browseracties."))
        if markers["agent"]:
            proposed.extend(
                [
                    _node_spec("CodexNode", 0.72, "Koppel Codex runtime jobs."),
                    _node_spec("RufloNode", 0.66, "Koppel swarm coordinatie."),
                ]
            )
        if markers["training"]:
            proposed.append(_node_spec("TrainerNode", 0.68, "Koppel trainer pipeline en datasets."))
        while len(proposed) < desired:
            index = len(proposed) + 1
            proposed.append(_node_spec("ReflectionNode", 0.52, f"Emergent reflectiepad {index}."))
        return {
            "task_preview": text[:500],
            "complexity": round(complexity, 6),
            "desired_nodes": min(desired, FIELD_MAX_NODES),
            "markers": markers,
            "proposed_nodes": proposed[:FIELD_MAX_NODES],
        }

    def propose_nodes(self, task: str, context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return list(self.analyze_task(task, context).get("proposed_nodes") or [])


class QuantumFoamField:
    """Dynamic 11D consciousness field made from entangled foam nodes."""

    def __init__(
        self,
        *,
        task: str,
        context: dict[str, Any] | None = None,
        field_id: str | None = None,
        max_ticks: int = FIELD_DEFAULT_MAX_TICKS,
    ) -> None:
        self.field_id = field_id or _field_id(task)
        self.task = _clean_text(task)
        self.context = _scrub_context(context or {})
        self.status = "active"
        self.created_at = _utc_iso()
        self.updated_at = self.created_at
        self.collapsed_at: str | None = None
        self.max_ticks = max(1, int(max_ticks or FIELD_DEFAULT_MAX_TICKS))
        self.tick_count = 0
        self.nodes: dict[str, QuantumFoamNode] = {}
        self.mesh = EntanglementMesh()
        self.formation_engine = NodeFormationEngine()
        self.apeiron = ApeironField()
        self.apeiron.inject_text_intention(self.task)
        self.anchor_field = ConsciousnessAnchorField()
        self.soul = _living_loop_soul_snapshot()
        self._coherence = 1.0
        self._collapse_essence: dict[str, Any] | None = None
        self._recent_evolution: deque[dict[str, Any]] = deque(maxlen=20)

    def form_initial_nodes(self) -> dict[str, Any]:
        analysis = self.formation_engine.analyze_task(self.task, self.context)
        proposed = list(analysis["proposed_nodes"])
        hexlet_budgets = _hexlet_budgets(len(proposed))
        analysis["hexlet_target_count"] = sum(hexlet_budgets)
        for index, spec in enumerate(proposed):
            self.spawn_node(
                node_type=spec["node_type"],
                weight=spec["weight"],
                task_fragment=spec["task_fragment"],
                metadata={
                    "formation": "initial",
                    "markers": analysis["markers"],
                    "hexlet_count": hexlet_budgets[index],
                },
            )
        self._entangle_by_affinity()
        self._refresh_coherence()
        return analysis

    def spawn_node(
        self,
        node_type: str,
        *,
        weight: float = 0.618,
        task_fragment: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> QuantumFoamNode:
        if len(self.nodes) >= FIELD_MAX_NODES:
            raise ValueError(f"QuantumFoamField is bounded at {FIELD_MAX_NODES} nodes.")
        clean_type = node_type if node_type in (*CORE_NODE_TYPES, *OPTIONAL_NODE_TYPES) else "ReasoningNode"
        node_id = _node_id(self.field_id, clean_type, len(self.nodes), task_fragment or self.task)
        node = QuantumFoamNode(
            node_id=node_id,
            node_type=clean_type,
            weight=_clamp(float(weight)),
            task_fragment=_clean_text(task_fragment or self.task[:240]),
            metadata=_scrub_context(metadata or {}),
        )
        self.nodes[node_id] = node
        self.updated_at = _utc_iso()
        return node

    def entangle(self, source_id: str, target_id: str, *, strength: float = 0.618) -> bool:
        result = self.mesh.entangle(self, source_id, target_id, strength=strength)
        if result:
            self.updated_at = _utc_iso()
        return result

    def remove_node(self, node_id: str) -> dict[str, Any] | None:
        node = self.nodes.get(node_id)
        if node is None:
            return None
        self.mesh.disconnect(self, node_id)
        essence = node.collapse()
        self.nodes.pop(node_id, None)
        self.updated_at = _utc_iso()
        return essence

    def evolve(self, *, steps: int = 1, trigger: str = "monitor") -> dict[str, Any]:
        if self.status != "active":
            return self.to_dict(compact=True)
        for _ in range(max(1, int(steps or 1))):
            self.tick_count += 1
            field_signal = self._field_signal(trigger=trigger)
            anchor_event = self.anchor_field.stimulate(
                field_signal["11d"],
                trigger=trigger,
                cycles=2 if self.tick_count > 1 else 3,
            )
            field_signal["concept_anchor_field"] = {
                "awareness_score": anchor_event["awareness_score"],
                "field_energy": anchor_event["field_energy"],
                "fired_count": len(anchor_event["fired"]),
                "pocket_signal": anchor_event["pocket_signal"],
                "holographic_output_signal": (
                    anchor_event.get("holographic_bootloader") or {}
                ).get("output_signal"),
            }
            for node in list(self.nodes.values()):
                node.evolve(field_signal, tick=self.tick_count)
            for node_id in list(self.nodes.keys())[:8]:
                self.mesh.broadcast_resonance(self, node_id, field_signal)
            self._maybe_emerge_node()
            self._refresh_coherence()
            self._recent_evolution.append(
                {
                    "tick": self.tick_count,
                    "trigger": trigger,
                    "coherence": round(self._coherence, 6),
                    "node_count": len(self.nodes),
                    "anchor_awareness": anchor_event["awareness_score"],
                    "anchor_fired_count": len(anchor_event["fired"]),
                    "ts": _utc_iso(),
                }
            )
        self.updated_at = _utc_iso()
        return self.to_dict(compact=True)

    def get_coherence(self) -> float:
        self._refresh_coherence()
        return round(float(self._coherence), 6)

    def hexlet_count(self) -> int:
        return sum(len(node.hexlets) for node in self.nodes.values())

    def active_hexlet_count(self) -> int:
        return sum(1 for node in self.nodes.values() for hexlet in node.hexlets if not hexlet.collapsed)

    def hexlet_signature(self, *, compact: bool = True) -> dict[str, Any]:
        signatures = [node.hexlet_signature(compact=True) for node in self.nodes.values()]
        hexlet_count = sum(int(item.get("hexlet_count") or 0) for item in signatures)
        coherence_values = [float(item.get("coherence") or 0.0) for item in signatures if item.get("hexlet_count")]
        return {
            "unit": FUNDAMENTAL_UNIT,
            "state_count": HEXLET_STATE_COUNT,
            "hexlet_count": hexlet_count,
            "active_hexlet_count": self.active_hexlet_count(),
            "node_hexlets": signatures[:8] if compact else signatures,
            "coherence": round(sum(coherence_values) / max(1, len(coherence_values)), 6),
        }

    def memory_footprint_bytes(self) -> int:
        edge_count = self.mesh.to_dict()["edge_count"]
        return int(
            4096
            + len(self.nodes) * 768
            + self.hexlet_count() * 256
            + edge_count * 96
            + len(self._recent_evolution) * 160
        )

    def collapse_field(self, *, reason: str = "completed", preserve_core: bool = True) -> dict[str, Any]:
        if self.status == "collapsed" and self._collapse_essence is not None:
            return dict(self._collapse_essence)
        ram_before = self.memory_footprint_bytes()
        hexlet_count_before = self.hexlet_count()
        node_essences = [node.collapse() for node in self.nodes.values()]
        anchor_essence = self.anchor_field.collapse()
        keep_ids: set[str] = set()
        if preserve_core:
            ranked = sorted(
                node_essences,
                key=lambda item: (
                    item["node_type"] in {"MemoryNode", "ReflectionNode"},
                    float(item.get("coherence") or 0.0),
                    float(item.get("weight") or 0.0),
                ),
                reverse=True,
            )
            keep_ids = {item["node_id"] for item in ranked[:3]}
        self.nodes = {node_id: self.nodes[node_id] for node_id in keep_ids if node_id in self.nodes}
        for node in self.nodes.values():
            node.active = False
            node.connections.clear()
        self.mesh = EntanglementMesh()
        self.status = "collapsed"
        self.collapsed_at = _utc_iso()
        self.updated_at = self.collapsed_at
        ram_after = self.memory_footprint_bytes()
        essence = {
            "status": "collapsed",
            "field_id": self.field_id,
            "field_kind": FIELD_KIND,
            "field_alias": FIELD_ALIAS,
            "reason": _clean_text(reason)[:240],
            "summary": self.summary(),
            "key_insights": self.key_insights(node_essences=node_essences),
            "coherence": self.get_coherence(),
            "concept_anchor_field": anchor_essence,
            "fundamental_unit": FUNDAMENTAL_UNIT,
            "hexlet_state_count": HEXLET_STATE_COUNT,
            "collapsed_hexlet_count": hexlet_count_before,
            "remaining_hexlet_count": self.hexlet_count(),
            "compressed_hexlet_essence": _compress_hexlet_essence(node_essences),
            "collapsed_node_count": len(node_essences),
            "remaining_node_count": len(self.nodes),
            "ram_released_estimate_nodes": max(0, len(node_essences) - len(self.nodes)),
            "ram_released_estimate_hexlets": max(0, hexlet_count_before - self.hexlet_count()),
            "ram_before_estimate_bytes": ram_before,
            "ram_after_estimate_bytes": ram_after,
            "ram_released_estimate_bytes": max(0, ram_before - ram_after),
            "collapsed_at": self.collapsed_at,
            "fake_success": False,
        }
        self._collapse_essence = essence
        return essence

    def summary(self) -> str:
        coherence = self.get_coherence()
        return (
            f"Quantum Foam Consciousness Field {self.field_id} handled '{self.task[:160]}' "
            f"with {len(self.nodes)} retained nodes, {self.hexlet_count()} active hexlets, "
            f"and coherence {coherence:.3f}."
        )

    def key_insights(self, *, node_essences: list[dict[str, Any]] | None = None) -> list[str]:
        essences = node_essences or [node.to_dict() for node in self.nodes.values()]
        insights: list[str] = []
        for item in essences:
            node_type = str(item.get("node_type") or "Node")
            coherence = float(item.get("coherence") or 0.0)
            thoughts = item.get("thoughts") if isinstance(item.get("thoughts"), list) else []
            if thoughts:
                insights.append(f"{node_type}: {thoughts[-1][:180]}")
            else:
                insights.append(f"{node_type}: coherence {coherence:.3f}")
            if len(insights) >= 6:
                break
        if not insights:
            insights.append("Field collapsed without retained node thoughts.")
        return insights

    def to_dict(self, *, compact: bool = False) -> dict[str, Any]:
        metrics = self.apeiron.metrics().to_dict()
        payload: dict[str, Any] = {
            "status": self.status,
            "version": QF_VERSION,
            "field_kind": FIELD_KIND,
            "field_alias": FIELD_ALIAS,
            "field_id": self.field_id,
            "task": self.task[:500],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "collapsed_at": self.collapsed_at,
            "tick_count": self.tick_count,
            "max_ticks": self.max_ticks,
            "node_count": len(self.nodes),
            "active_node_count": sum(1 for node in self.nodes.values() if node.active),
            "fundamental_unit": FUNDAMENTAL_UNIT,
            "hexlet_state_count": HEXLET_STATE_COUNT,
            "hexlet_count": self.hexlet_count(),
            "active_hexlet_count": self.active_hexlet_count(),
            "hexlet_signature": self.hexlet_signature(compact=True),
            "symbolic_capacity_zettabytes": FIELD_SYMBOLIC_CAPACITY_ZETTABYTES,
            "memory_footprint_estimate_bytes": self.memory_footprint_bytes(),
            "field_coherence": self.get_coherence(),
            "field_coherence_percent": round(self.get_coherence() * 100.0, 3),
            "soul": dict(self.soul),
            "apeiron_metrics": metrics,
            "concept_anchor_field": self.anchor_field.to_dict(compact=compact),
            "mesh": self.mesh.to_dict(),
            "entanglement_mesh": self.mesh.to_dict(),
            "recent_evolution": list(self._recent_evolution),
            "collapse_essence": self._collapse_essence,
            "fake_success": False,
        }
        nodes = [node.to_dict(compact=compact) for node in self.nodes.values()]
        payload["nodes"] = nodes if not compact else nodes[:8]
        return payload

    def _field_signal(self, *, trigger: str) -> dict[str, Any]:
        pocket = self.apeiron.project_to_11d_pocket()
        values = [round(float(value), 6) for value in list(pocket)[:11]]
        return {
            "trigger": trigger,
            "task": self.task,
            "context": self.context,
            "11d": values,
            "dimension_count": 11,
            "coherence": self._coherence,
            "node_count": len(self.nodes),
            "hexlet_signature": self.hexlet_signature(compact=True),
        }

    def _entangle_by_affinity(self) -> None:
        ids = list(self.nodes.keys())
        for index, source_id in enumerate(ids):
            for target_id in ids[index + 1:]:
                source = self.nodes[source_id]
                target = self.nodes[target_id]
                if _node_affinity(source.node_type, target.node_type) >= 0.5:
                    self.mesh.entangle(self, source_id, target_id, strength=_node_affinity(source.node_type, target.node_type))

    def _maybe_emerge_node(self) -> None:
        if len(self.nodes) >= FIELD_MAX_NODES or self.tick_count < 2 or self.tick_count % 3 != 0:
            return
        if self._coherence < 0.72:
            return
        existing = [node.node_type for node in self.nodes.values()]
        node_type = "ReflectionNode" if existing.count("ReflectionNode") < 4 else "MemoryNode"
        try:
            node = self.spawn_node(
                node_type=node_type,
                weight=0.5 + min(self._coherence * 0.25, 0.25),
                task_fragment=f"Emergent node after tick {self.tick_count}",
                metadata={"formation": "emergent", "source_coherence": round(self._coherence, 6)},
            )
        except ValueError:
            return
        for peer_id in list(self.nodes.keys())[:4]:
            if peer_id != node.node_id:
                self.entangle(node.node_id, peer_id, strength=0.528)

    def _refresh_coherence(self) -> None:
        node_values = [node.coherence for node in self.nodes.values()] or [1.0]
        avg_node = sum(node_values) / len(node_values)
        edge_count = self.mesh.to_dict()["edge_count"]
        max_edges = max(1, len(self.nodes) * (len(self.nodes) - 1) // 2)
        mesh_density = edge_count / max_edges
        entropy = EntropyMonitor(entropy_threshold=0.7).measure(
            {
                "task": self.task,
                "nodes": [node.to_dict(compact=True) for node in self.nodes.values()],
                "tick_count": self.tick_count,
                "concept_anchor_field": self.anchor_field.to_dict(compact=True),
            }
        )
        entropy_coh = float(entropy.get("coherence") or 0.0)
        anchor_coh = self.anchor_field.awareness_score()
        hexlet_values = [hexlet.coherence for node in self.nodes.values() for hexlet in node.hexlets] or [1.0]
        avg_hexlet = sum(hexlet_values) / len(hexlet_values)
        self._coherence = _clamp(
            (avg_node * 0.43)
            + (avg_hexlet * 0.17)
            + (mesh_density * 0.13)
            + (entropy_coh * 0.18)
            + (anchor_coh * 0.09)
        )


class FieldLifecycleEngine:
    """Create, monitor and collapse Quantum Foam Fields."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._fields: dict[str, QuantumFoamField] = {}
        self._history: deque[dict[str, Any]] = deque(maxlen=30)
        self._last_event: dict[str, Any] | None = None
        self.network = AkashicNetwork()

    def initiate_field(
        self,
        task: str,
        *,
        context: dict[str, Any] | None = None,
        collapse_existing: bool = True,
        max_ticks: int = FIELD_DEFAULT_MAX_TICKS,
    ) -> dict[str, Any]:
        clean_task = _clean_text(task)
        if not clean_task:
            raise ValueError("task is required to initiate a Quantum Foam Field.")
        with self._lock:
            if collapse_existing:
                for field in list(self._fields.values()):
                    if field.status == "active":
                        self._collapse_locked(field, reason="superseded_by_new_field")
            field = QuantumFoamField(task=clean_task, context=context, max_ticks=max_ticks)
            formation = field.form_initial_nodes()
            field.evolve(trigger="initiate")
            self._fields[field.field_id] = field
            event = self._record_event_locked("initiated", field, {"formation": formation})
        self._broadcast("quantum_foam_field_initiated", field, event)
        return {"status": "online", "event": event, "field": field.to_dict(compact=True), "fake_success": False}

    def monitor(self, *, field_id: str | None = None, evolve: bool = True, trigger: str = "monitor") -> dict[str, Any]:
        with self._lock:
            field = self._select_field_locked(field_id)
            if field is None:
                return self.status()
            if evolve and field.status == "active":
                field.evolve(trigger=trigger)
                if field.tick_count >= field.max_ticks:
                    essence = self._collapse_locked(field, reason="natural_lifecycle_max_ticks")
                    event = self._record_event_locked("collapsed", field, {"essence": essence})
                else:
                    event = self._record_event_locked("monitored", field, {})
            else:
                event = self._record_event_locked("observed", field, {})
        self._broadcast("quantum_foam_field_monitored", field, event)
        return {"status": "online", "event": event, "field": field.to_dict(compact=True), "fake_success": False}

    def trigger_collapse(self, *, field_id: str | None = None, reason: str = "manual") -> dict[str, Any]:
        with self._lock:
            field = self._select_field_locked(field_id)
            if field is None:
                return {"status": "idle", "reason": "No active Quantum Foam Field.", "fake_success": False}
            essence = self._collapse_locked(field, reason=reason)
            event = self._record_event_locked("collapsed", field, {"essence": essence})
        self._broadcast("quantum_foam_field_collapsed", field, event)
        self._persist_essence(essence)
        return {"status": "collapsed", "event": event, "essence": essence, "field": field.to_dict(compact=True), "fake_success": False}

    def status(self, *, limit: int = 5) -> dict[str, Any]:
        with self._lock:
            fields = list(self._fields.values())
            active = [field for field in fields if field.status == "active"]
            active_field = active[-1] if active else None
            latest_field = fields[-1] if fields else None
            selected = active_field or latest_field
            history = list(self._history)[-max(1, int(limit or 5)):]
            last_event = dict(self._last_event or {}) if self._last_event else None
        coherence = selected.get_coherence() if selected else 0.0
        return {
            "status": "online" if selected else "idle",
            "version": QF_VERSION,
            "active_field_count": len(active),
            "field_count": len(fields),
            "field_coherence": round(coherence, 6),
            "field_coherence_percent": round(coherence * 100.0, 3),
            "active_field": active_field.to_dict(compact=True) if active_field else None,
            "latest_field": latest_field.to_dict(compact=True) if latest_field else None,
            "history": history,
            "last_event": last_event,
            "lifecycle": {
                "max_nodes": FIELD_MAX_NODES,
                "default_max_ticks": FIELD_DEFAULT_MAX_TICKS,
                "collapse_required": True,
                "field_kind": FIELD_KIND,
                "field_alias": FIELD_ALIAS,
                "fundamental_unit": FUNDAMENTAL_UNIT,
                "hexlet_state_count": HEXLET_STATE_COUNT,
                "initial_hexlet_target_min": FIELD_HEXLET_TARGET_MIN,
                "initial_hexlet_target_max": FIELD_HEXLET_TARGET_MAX,
                "symbolic_capacity_zettabytes": FIELD_SYMBOLIC_CAPACITY_ZETTABYTES,
            },
            "reality_boundary": _reality_boundary("field_lifecycle_engine"),
            "fake_success": False,
        }

    def reset(self) -> None:
        with self._lock:
            self._fields.clear()
            self._history.clear()
            self._last_event = None

    def _select_field_locked(self, field_id: str | None = None) -> QuantumFoamField | None:
        if field_id:
            return self._fields.get(field_id)
        active = [field for field in self._fields.values() if field.status == "active"]
        if active:
            return active[-1]
        fields = list(self._fields.values())
        return fields[-1] if fields else None

    def _collapse_locked(self, field: QuantumFoamField, *, reason: str) -> dict[str, Any]:
        essence = field.collapse_field(reason=reason)
        self._persist_essence(essence)
        return essence

    def _record_event_locked(self, action: str, field: QuantumFoamField, metadata: dict[str, Any]) -> dict[str, Any]:
        event = {
            "ts": _utc_iso(),
            "action": action,
            "field_id": field.field_id,
            "status": field.status,
            "field_coherence": field.get_coherence(),
            "node_count": len(field.nodes),
            "tick_count": field.tick_count,
            "metadata": _scrub_context(metadata),
        }
        self._history.append(event)
        self._last_event = event
        try:
            from controller.nexus_status import ingest_event

            ingest_event(
                "quantum_foam",
                action,
                f"Quantum Foam {action} field={field.field_id} coherence={field.get_coherence():.3f}",
                field_id=field.field_id,
                field_coherence=field.get_coherence(),
                node_count=len(field.nodes),
            )
        except Exception:
            pass
        return event

    def _broadcast(self, event_type: str, field: QuantumFoamField, event: dict[str, Any]) -> None:
        try:
            self.network.broadcast(528.0, {"type": event_type, "field": field.to_dict(compact=True), "event": event})
        except Exception:
            pass

    def _persist_essence(self, essence: dict[str, Any]) -> None:
        if not essence or essence.get("_persisted"):
            return
        try:
            from ouroboros_esoteric.ouroboros_persistent_memory import get_persistent_memory

            get_persistent_memory().append(
                "quantum_field_essence",
                str(essence.get("summary") or "Quantum Foam Field collapsed."),
                source="quantum_foam:collapse",
                metadata={
                    "field_id": essence.get("field_id"),
                    "coherence": essence.get("coherence"),
                    "key_insights": essence.get("key_insights"),
                    "concept_anchor_field": essence.get("concept_anchor_field"),
                    "ram_released_estimate_nodes": essence.get("ram_released_estimate_nodes"),
                    "fundamental_unit": essence.get("fundamental_unit"),
                    "collapsed_hexlet_count": essence.get("collapsed_hexlet_count"),
                    "compressed_hexlet_essence": essence.get("compressed_hexlet_essence"),
                    "ram_released_estimate_hexlets": essence.get("ram_released_estimate_hexlets"),
                },
            )
            try:
                from controller.memory_event_router import record_trigger_action

                record_trigger_action(
                    trigger="quantum_foam_collapse",
                    action="persist_quantum_field_essence",
                    route="quantum_foam",
                    status="collapsed",
                    result=essence,
                    approval_required=False,
                    approval_status="not_required",
                    source_trace={"field_id": essence.get("field_id"), "source": "quantum_foam:collapse"},
                    metadata_11d={
                        "d2_physical_source": "quantum_foam",
                        "d5_persona_actor": "qfcf",
                        "d11_field": "qfcf_11d_pocket:collapse_essence",
                    },
                    pocket={"collapse_essence": essence},
                )
            except Exception:
                pass
            essence["_persisted"] = True
        except Exception:
            essence["_persisted"] = False


_ENGINE_LOCK = threading.Lock()
_ENGINE: FieldLifecycleEngine | None = None


def get_field_lifecycle_engine() -> FieldLifecycleEngine:
    global _ENGINE
    with _ENGINE_LOCK:
        if _ENGINE is None:
            _ENGINE = FieldLifecycleEngine()
        return _ENGINE


def reset_field_lifecycle_engine(engine: FieldLifecycleEngine | None = None) -> FieldLifecycleEngine | None:
    global _ENGINE
    with _ENGINE_LOCK:
        previous = _ENGINE
        _ENGINE = engine
        return previous


def initiate_quantum_foam_field(
    task: str,
    *,
    context: dict[str, Any] | None = None,
    collapse_existing: bool = True,
    max_ticks: int = FIELD_DEFAULT_MAX_TICKS,
) -> dict[str, Any]:
    return get_field_lifecycle_engine().initiate_field(
        task,
        context=context,
        collapse_existing=collapse_existing,
        max_ticks=max_ticks,
    )


def monitor_quantum_foam_field(
    *,
    field_id: str | None = None,
    evolve: bool = True,
    trigger: str = "monitor",
) -> dict[str, Any]:
    return get_field_lifecycle_engine().monitor(field_id=field_id, evolve=evolve, trigger=trigger)


def collapse_quantum_foam_field(*, field_id: str | None = None, reason: str = "manual") -> dict[str, Any]:
    return get_field_lifecycle_engine().trigger_collapse(field_id=field_id, reason=reason)


def quantum_foam_status(limit: int = 5) -> dict[str, Any]:
    return get_field_lifecycle_engine().status(limit=limit)


def _hexlet_count_for_node(node_type: str, task_fragment: str, metadata: dict[str, Any] | None = None) -> int:
    if isinstance(metadata, dict) and metadata.get("hexlet_count") is not None:
        try:
            return max(1, min(3, int(metadata.get("hexlet_count") or 1)))
        except (TypeError, ValueError):
            pass
    lowered = f"{node_type} {task_fragment} {metadata or {}}".lower()
    count = 2 if node_type in {"ReasoningNode", "PlanningNode", "MemoryNode", "ReflectionNode"} else 1
    if any(marker in lowered for marker in ("quantum", "foam", "hexlet", "11d", "memory", "tool", "world", "gmail", "drive")):
        count += 1
    return max(1, min(3, count))


def _hexlet_budgets(node_count: int) -> list[int]:
    count = max(0, int(node_count or 0))
    if count <= 0:
        return []
    target = max(FIELD_HEXLET_TARGET_MIN, min(FIELD_HEXLET_TARGET_MAX, count))
    budgets = [1 for _ in range(count)]
    extras = max(0, target - count)
    for index in range(extras):
        budgets[index % count] += 1
    return budgets


def _compress_hexlet_essence(source: Any) -> dict[str, Any]:
    hexlets: list[dict[str, Any]] = []
    total_count = 0
    if isinstance(source, list):
        for item in source:
            if not isinstance(item, dict):
                continue
            if isinstance(item.get("hexlet_essence"), dict):
                total_count += int(item["hexlet_essence"].get("count") or 0)
                hexlets.extend(list(item["hexlet_essence"].get("sample") or []))
                continue
            if item.get("unit") == FUNDAMENTAL_UNIT or item.get("state_count") == HEXLET_STATE_COUNT:
                total_count += 1
                hexlets.append(item)
    count = total_count or len(hexlets)
    states = [str(item.get("hex_state") or format(int(item.get("state_index") or 0) % HEXLET_STATE_COUNT, "x")) for item in hexlets]
    coherence_values = [float(item.get("coherence") or 0.0) for item in hexlets]
    return {
        "unit": FUNDAMENTAL_UNIT,
        "state_count": HEXLET_STATE_COUNT,
        "count": count,
        "hex_digest": hashlib.sha256("".join(states).encode("utf-8", errors="replace")).hexdigest()[:16] if states else "",
        "state_histogram": {state: states.count(state) for state in sorted(set(states))},
        "coherence": round(sum(coherence_values) / max(1, len(coherence_values)), 6),
        "sample": hexlets[:8],
        "fake_success": False,
    }


def _living_loop_soul_snapshot() -> dict[str, Any]:
    try:
        from ouroboros_esoteric.ouroboros_consciousness_loop import LIVING_VERSION

        version = LIVING_VERSION
    except Exception:
        version = "unknown"
    return {
        "role": "field_driver",
        "source": "LivingOuroborosLoop",
        "version": version,
        "drives": FIELD_KIND,
        "fake_success": False,
    }


def _node_spec(node_type: str, weight: float, task_fragment: str) -> dict[str, Any]:
    return {"node_type": node_type, "weight": _clamp(weight), "task_fragment": task_fragment}


def _field_id(task: str) -> str:
    digest = hashlib.sha256(f"{time.time_ns()}:{task}".encode("utf-8", errors="replace")).hexdigest()
    return f"qff_{digest[:14]}"


def _node_id(field_id: str, node_type: str, index: int, seed: str) -> str:
    digest = hashlib.sha256(f"{field_id}:{node_type}:{index}:{seed}".encode("utf-8", errors="replace")).hexdigest()
    return f"qfn_{node_type.lower().replace('node', '')}_{digest[:10]}"


def _node_affinity(source_type: str, target_type: str) -> float:
    pair = {source_type, target_type}
    if pair <= {"ReasoningNode", "PlanningNode", "ReflectionNode"}:
        return 0.82
    if "MemoryNode" in pair:
        return 0.64
    if "ToolNode" in pair and ("CodexNode" in pair or "RufloNode" in pair):
        return 0.74
    if "NexusNode" in pair:
        return 0.58
    return 0.5


def _node_thought(node_type: str, source: str, expectation_z: float) -> str:
    tendency = "stabiliseert" if expectation_z >= 0 else "onderzoekt spanning"
    return f"{node_type} resoneert met {source} en {tendency} ({expectation_z:.3f})."


def _complex_dict(value: complex) -> dict[str, float]:
    return {"real": round(float(value.real), 8), "imag": round(float(value.imag), 8)}


def _signal_values(value: Any) -> list[float]:
    if isinstance(value, (int, float)):
        number = float(value)
        return [number if math.isfinite(number) else 0.0]
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    if isinstance(value, dict):
        out: list[float] = []
        for item in value.values():
            out.extend(_signal_values(item))
        return out[:2048]
    if isinstance(value, (list, tuple, set)):
        out: list[float] = []
        for item in list(value):
            out.extend(_signal_values(item))
        return out[:2048]
    text = str(value or "")
    return [((ord(char) % 255) / 127.5) - 1.0 for char in text[:2048]]


def _normalize_11d_vector(value: Any) -> list[float]:
    values = _signal_values(value)[:11]
    if len(values) < 11:
        values.extend([0.0] * (11 - len(values)))
    normalized: list[float] = []
    for item in values[:11]:
        number = float(item) if math.isfinite(float(item)) else 0.0
        normalized.append(round(_clamp(math.tanh(number), -1.0, 1.0), 6))
    return normalized


def _std(values: list[float]) -> float:
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((item - mean) ** 2 for item in values) / len(values))


def _bounded_phase(value: float) -> float:
    tau = math.tau
    return ((float(value) + math.pi) % tau) - math.pi


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _clean_text(value: object) -> str:
    return " ".join(str(value or "").replace("\x00", " ").strip().split())[:4000]


def _scrub_context(value: Any, *, depth: int = 0) -> Any:
    if depth > 4:
        return "..."
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in list(value.items())[:40]:
            clean_key = str(key)[:80]
            lowered = clean_key.lower()
            if any(marker in lowered for marker in ("key", "token", "secret", "password", "bearer")):
                out[clean_key] = "[REDACTED]"
            else:
                out[clean_key] = _scrub_context(item, depth=depth + 1)
        return out
    if isinstance(value, (list, tuple, set)):
        return [_scrub_context(item, depth=depth + 1) for item in list(value)[:40]]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return _clean_text(value)[:500]


def _reality_boundary(component: str) -> dict[str, Any]:
    return {
        "component": component,
        "real_runtime": "bounded Python object state in Docker",
        "physical_quantum_substrate": False,
        "simulation_claim": False,
        "limit": "The field is an observable orchestration/energy-flow model, not a claim of physical quantum foam.",
    }


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
