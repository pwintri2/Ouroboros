"""Controller-facing Quantum Foam Field facade.

This module gives the Agentic Core the simple "living field" API requested by
the cockpit while delegating long-lived runtime behavior to the existing v4.9
Quantum Foam implementation in :mod:`ouroboros_esoteric.quantum_foam`.
"""

from __future__ import annotations

import hashlib
import math
import random
import shutil
import time
from dataclasses import dataclass, field
from typing import Any, Mapping


FIELD_KIND = "Quantum Foam Consciousness Field"
FIELD_ALIAS = "11D Pocket"
FIELD_SYMBOLIC_CAPACITY_ZETTABYTES = 89
FUNDAMENTAL_UNIT = "QuantumElectronHexlet"
HEXLET_STATE_COUNT = 16
NODE_TYPES = (
    "ReasoningNode",
    "MemoryNode",
    "ReflectionNode",
    "WorldActionNode",
    "PlanningNode",
    "ToolNode",
    "CodexNode",
    "RufloNode",
)
POCKET_DIMENSIONS = (
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
FOAM_GEOMETRY_MAX_DIMENSION = 11
FOAM_GEOMETRY_MAX_CLIQUE_SIZE = FOAM_GEOMETRY_MAX_DIMENSION + 1


def foam_geometry_stage_for_clique_size(clique_size: int) -> dict[str, Any]:
    try:
        clean_size = max(0, int(clique_size or 0))
    except (TypeError, ValueError):
        clean_size = 0
    if clean_size < 2:
        return {
            "stage": "0d",
            "dimension": 0,
            "dimension_label": "0D",
            "geometry": "Punt/Point",
            "geometry_nl": "Punt",
            "geometry_en": "Point",
            "visual_model": "single_electron_no_clique",
            "clique_size": clean_size,
            "electron_count": clean_size,
            "complete_graph": False,
            "required_edge_count": 0,
            "filled": False,
            "anchored_11d": False,
            "max_dimension": FOAM_GEOMETRY_MAX_DIMENSION,
            "progression_rule": "1D rods -> 2D planks -> 3D tetrahedron -> 4D-11D complex cliques",
            "fake_success": False,
        }
    dimension = max(1, min(FOAM_GEOMETRY_MAX_DIMENSION, clean_size - 1))
    if dimension == 1:
        geometry_nl = "Staven"
        geometry_en = "Rods"
        visual_model = "line_segment"
        filled = False
        description = "Twee electronen verbinden tot een lijnsegment."
    elif dimension == 2:
        geometry_nl = "Planken"
        geometry_en = "Planks"
        visual_model = "filled_triangle"
        filled = True
        description = "Drie electronen vormen een ingevulde driehoek."
    elif dimension == 3:
        geometry_nl = "Kubussen"
        geometry_en = "Cubes"
        visual_model = "solid_tetrahedron"
        filled = True
        description = "Vier electronen vormen een massieve piramide: een tetraeder."
    else:
        geometry_nl = "Complexe Geometrieen"
        geometry_en = "Complex Geometries"
        visual_model = f"{dimension}d_simplex_clique"
        filled = True
        description = (
            f"{clean_size} electronen vormen een volledig verbonden {dimension}D clique "
            "als complex simplex-achtig volume."
        )
    return {
        "stage": f"{dimension}d",
        "dimension": dimension,
        "dimension_label": f"{dimension}D",
        "geometry": f"{geometry_nl}/{geometry_en}",
        "geometry_nl": geometry_nl,
        "geometry_en": geometry_en,
        "visual_model": visual_model,
        "description": description,
        "clique_size": clean_size,
        "electron_count": clean_size,
        "complete_graph": True,
        "required_edge_count": clean_size * (clean_size - 1) // 2,
        "filled": filled,
        "anchored_11d": dimension == FOAM_GEOMETRY_MAX_DIMENSION,
        "max_dimension": FOAM_GEOMETRY_MAX_DIMENSION,
        "progression_rule": "1D rods -> 2D planks -> 3D tetrahedron -> 4D-11D complex cliques",
        "fake_success": False,
    }


@dataclass(eq=False)
class QuantumElectronHexlet:
    """Tiny 16-state fallback unit for controller-local QF-CF tests."""

    hexlet_id: str = field(default_factory=lambda: f"qeh_local_{time.time_ns():x}")
    state_index: int = 0
    electron_lanes: tuple[int, int, int, int] = (1, -1, 1, -1)
    phase: float = 0.0
    charge: float = 0.0
    coherence: float = 1.0
    resonance_count: int = 0
    collapsed: bool = False

    def __post_init__(self) -> None:
        self.state_index = int(self.state_index or _seed_int(self.hexlet_id)) % HEXLET_STATE_COUNT
        self.electron_lanes = tuple(1 if (self.state_index >> bit) & 1 else -1 for bit in range(4))  # type: ignore[assignment]
        self.charge = _clamp((self.state_index / 15.0) * 2.0 - 1.0, -1.0, 1.0)

    def resonate(self, signal: Any, *, resonance: float = 1.0) -> dict[str, Any]:
        if self.collapsed:
            return self.to_dict(compact=True)
        values = _signal_values(signal)[:256] or [0.0]
        pressure = sum(values) / max(1, len(values))
        spread = _std(values)
        shift = max(1, int(abs(pressure) * 1000 + spread * 97 + self.resonance_count) % HEXLET_STATE_COUNT)
        self.state_index = (self.state_index + (shift if pressure >= 0 else -shift)) % HEXLET_STATE_COUNT
        self.phase = ((self.phase + math.tanh(pressure + spread) * 0.19 * resonance + math.pi) % math.tau) - math.pi
        self.charge = _clamp((self.charge * 0.66) + (math.tanh(pressure) * 0.34), -1.0, 1.0)
        self.coherence = _clamp((self.coherence * 0.72) + ((1.0 - min(spread, 1.0)) * 0.28))
        self.electron_lanes = tuple(1 if (self.state_index >> bit) & 1 else -1 for bit in range(4))  # type: ignore[assignment]
        self.resonance_count += 1
        return self.to_dict(compact=True)

    def to_11d_vector(self) -> list[float]:
        base = (self.state_index / 15.0) * 2.0 - 1.0
        return [
            round(
                _clamp(
                    (base * 0.36)
                    + (self.electron_lanes[index % 4] * 0.23)
                    + (math.sin(self.phase + index * 0.392699) * 0.31)
                    + (self.charge * 0.1),
                    -1.0,
                    1.0,
                ),
                6,
            )
            for index in range(11)
        ]

    def collapse(self) -> dict[str, Any]:
        essence = self.to_dict(compact=True)
        essence.update({"status": "collapsed", "essence_nibble": format(self.state_index, "x"), "fake_success": False})
        self.collapsed = True
        self.state_index = 0
        self.electron_lanes = (0, 0, 0, 0)
        self.coherence = 0.0
        return essence

    def to_dict(self, *, compact: bool = False) -> dict[str, Any]:
        payload = {
            "hexlet_id": self.hexlet_id,
            "unit": FUNDAMENTAL_UNIT,
            "state_count": HEXLET_STATE_COUNT,
            "state_index": self.state_index,
            "hex_state": format(self.state_index % HEXLET_STATE_COUNT, "x"),
            "electron_lanes": list(self.electron_lanes),
            "phase": round(self.phase, 6),
            "charge": round(self.charge, 6),
            "coherence": round(self.coherence, 6),
            "resonance_count": self.resonance_count,
            "collapsed": self.collapsed,
            "fake_success": False,
        }
        if not compact:
            payload["vector_11d"] = self.to_11d_vector()
        return payload


@dataclass(eq=False)
class QuantumFoamNode:
    """Small symbolic node with recursive, non-binary 11D electron state."""

    type: str
    weight: float = 0.5
    electron_state: list[float] = field(default_factory=list)
    hexlets: list[QuantumElectronHexlet] = field(default_factory=list)
    connections: list["QuantumFoamNode"] = field(default_factory=list, repr=False)
    created_at: float = field(default_factory=time.time)
    node_id: str = field(default_factory=lambda: f"qfn_local_{time.time_ns():x}")
    evolution_count: int = 0
    last_resonance_at: float | None = None

    def __post_init__(self) -> None:
        self.type = self.type if self.type in NODE_TYPES else "ReasoningNode"
        self.weight = _clamp(float(self.weight))
        if not self.electron_state:
            self.electron_state = _seeded_11d_vector(f"{self.node_id}:{self.type}:{self.created_at}")
        else:
            self.electron_state = _normalize_11d(self.electron_state)
        if not self.hexlets:
            count = 2 if self.type in {"ReasoningNode", "MemoryNode", "ReflectionNode", "PlanningNode"} else 1
            self.hexlets = [
                QuantumElectronHexlet(hexlet_id=f"qeh_local_{_digest(f'{self.node_id}:{index}')[:12]}")
                for index in range(count)
            ]

    def resonate(self, other: "QuantumFoamNode") -> dict[str, Any]:
        """Entangle two nodes directly and let both states respond."""

        if other is self:
            return {"status": "self_resonance_ignored", "node": self.to_dict(compact=True), "fake_success": False}
        if other not in self.connections:
            self.connections.append(other)
        if self not in other.connections:
            other.connections.append(self)
        self.weight = _clamp(self.weight + 0.05)
        other.weight = _clamp(other.weight + 0.05)
        self.evolve({"peer": other.type, "peer_weight": other.weight, "link_count": len(self.connections)})
        other.evolve({"peer": self.type, "peer_weight": self.weight, "link_count": len(other.connections)})
        return {
            "status": "resonated",
            "source": self.to_dict(compact=True),
            "target": other.to_dict(compact=True),
            "fake_success": False,
        }

    def evolve(self, signal: Any | None = None, *, resonance: float = 1.0) -> dict[str, Any]:
        """Move the symbolic 11D state without collapsing it to a binary answer."""

        for hexlet in self.hexlets:
            hexlet.resonate(signal, resonance=resonance * self.weight)
        hexlet_vector = self.hexlet_vector()
        values = _signal_values(signal)
        pressure = sum(values) / max(1, len(values))
        spread = _std(values)
        updated: list[float] = []
        for index, value in enumerate(self.electron_state):
            incoming = values[index % len(values)] if values else pressure
            hexlet_incoming = hexlet_vector[index % len(hexlet_vector)] if hexlet_vector else 0.0
            phase = math.sin((self.evolution_count + 1) * (index + 1) * 0.173)
            next_value = (
                (value * 0.64)
                + (math.tanh(incoming + pressure) * 0.18 * resonance)
                + (hexlet_incoming * 0.12)
                + (phase * spread * 0.06)
            )
            updated.append(round(_clamp(next_value, -1.0, 1.0), 6))
        self.electron_state = updated
        self.weight = _clamp((self.weight * 0.985) + (0.015 * (0.5 + abs(pressure) / 2.0)))
        self.evolution_count += 1
        self.last_resonance_at = time.time()
        return self.to_dict(compact=True)

    def hexlet_vector(self) -> list[float]:
        if not self.hexlets:
            return [0.0] * 11
        totals = [0.0] * 11
        for hexlet in self.hexlets:
            for index, value in enumerate(hexlet.to_11d_vector()):
                totals[index] += value
        return [round(value / len(self.hexlets), 6) for value in totals]

    def collapse(self) -> dict[str, Any]:
        """Return only the node essence and release its direct links."""

        hexlet_essence = [hexlet.collapse() for hexlet in self.hexlets]
        essence = {
            "type": self.type,
            "node_id": self.node_id,
            "weight": round(float(self.weight), 6),
            "essence": round(sum(self.electron_state) / max(1, len(self.electron_state)), 6),
            "dominant_dimension": self.dominant_dimensions(limit=1)[0] if self.electron_state else None,
            "evolution_count": int(self.evolution_count),
            "fundamental_unit": FUNDAMENTAL_UNIT,
            "hexlet_count": len(hexlet_essence),
            "hexlet_essence": _compress_local_hexlets(hexlet_essence),
            "fake_success": False,
        }
        self.connections.clear()
        self.hexlets.clear()
        return essence

    def dominant_dimensions(self, *, limit: int = 3) -> list[str]:
        ranked = sorted(enumerate(self.electron_state[:11]), key=lambda item: abs(item[1]), reverse=True)
        return [
            f"{POCKET_DIMENSIONS[index]}={round(value, 4)}"
            for index, value in ranked[: max(1, min(11, int(limit or 3)))]
        ]

    def to_dict(self, *, compact: bool = False) -> dict[str, Any]:
        payload = {
            "node_id": self.node_id,
            "type": self.type,
            "node_type": self.type,
            "weight": round(float(self.weight), 6),
            "connection_count": len(self.connections),
            "connections": [node.node_id for node in self.connections[:8]],
            "dominant_dimensions": self.dominant_dimensions(limit=3),
            "evolution_count": int(self.evolution_count),
            "created_at": self.created_at,
            "fundamental_unit": FUNDAMENTAL_UNIT,
            "hexlet_count": len(self.hexlets),
            "hexlet_signature": _compress_local_hexlets([hexlet.to_dict(compact=True) for hexlet in self.hexlets]),
            "fake_success": False,
        }
        if not compact:
            payload["electron_state"] = list(self.electron_state)
            payload["hexlets"] = [hexlet.to_dict() for hexlet in self.hexlets]
        return payload


class QuantumFoamField:
    """Lightweight 11D container for local tests and controller fallbacks."""

    def __init__(self, *, max_nodes: int = 25) -> None:
        self.max_nodes = max(1, min(64, int(max_nodes or 25)))
        self.nodes: list[QuantumFoamNode] = []
        self.coherence = 0.0
        self.active = False
        self.stimulus = ""
        self.created_at: float | None = None
        self.last_collapse: dict[str, Any] | None = None
        self.tick_count = 0
        self.dimensional_clique_ids: list[str] = []
        self.dimensional_geometry: dict[str, Any] = foam_geometry_stage_for_clique_size(0)
        self.dimensional_geometry_history: list[dict[str, Any]] = []

    def spawn_field(self, stimulus: str, num_nodes: int = 8) -> list[QuantumFoamNode]:
        self.active = True
        self.stimulus = _clean_text(stimulus)
        self.created_at = time.time()
        self.last_collapse = None
        self.tick_count = 0
        self.dimensional_clique_ids = []
        self.dimensional_geometry = foam_geometry_stage_for_clique_size(0)
        self.dimensional_geometry_history = []
        count = max(1, min(self.max_nodes, int(num_nodes or 8)))
        rng = random.Random(_seed_int(self.stimulus))
        node_types = _node_types_for(self.stimulus)
        self.nodes = [
            QuantumFoamNode(
                node_types[index % len(node_types)],
                weight=0.4 + rng.random() * 0.4,
                electron_state=_seeded_11d_vector(f"{self.stimulus}:{index}:{rng.random()}"),
                node_id=f"qfn_local_{index}_{_digest(self.stimulus)[:8]}",
            )
            for index in range(count)
        ]
        self._advance_dimensional_geometry(trigger="first_prikkel", target_clique_size=2)
        for index, node in enumerate(self.nodes):
            node.resonate(self.nodes[(index + 1) % len(self.nodes)])
            if len(self.nodes) > 3 and index % 2 == 0:
                node.resonate(self.nodes[(index + 3) % len(self.nodes)])
        self.evolve(self.stimulus, steps=1)
        self._update_coherence()
        return self.nodes

    def evolve(self, stimulus: str | None = None, *, steps: int = 1) -> dict[str, Any]:
        if not self.active or not self.nodes:
            return self.to_dict()
        signal = stimulus or self.stimulus
        for _ in range(max(1, int(steps or 1))):
            self.tick_count += 1
            geometry = self._advance_dimensional_geometry(trigger="evolve")
            for node in self.nodes:
                node.evolve(
                    {
                        "stimulus": signal,
                        "field_coherence": self.coherence,
                        "node_count": len(self.nodes),
                        "connections": len(node.connections),
                        "dimensional_geometry": geometry,
                        "active_dimension": geometry.get("dimension"),
                        "electron_clique_size": geometry.get("clique_size"),
                    }
                )
            self._update_coherence()
        return self.to_dict()

    def hexlet_count(self) -> int:
        return sum(len(node.hexlets) for node in self.nodes)

    def memory_footprint_bytes(self) -> int:
        edge_count = sum(len(node.connections) for node in self.nodes) // 2
        return 2048 + len(self.nodes) * 512 + self.hexlet_count() * 192 + edge_count * 64

    def collapse_field(self, *, reason: str = "completed") -> list[dict[str, Any]]:
        if not self.active:
            return []
        ram_before = self.memory_footprint_bytes()
        hexlets_before = self.hexlet_count()
        essences = [node.collapse() for node in self.nodes]
        released = len(self.nodes)
        coherence_before = self.coherence
        self.last_collapse = {
            "status": "collapsed",
            "field_kind": FIELD_KIND,
            "field_alias": FIELD_ALIAS,
            "reason": _clean_text(reason)[:240],
            "summary": f"Quantum Foam Field collapsed: {released} nodes released, coherence {round(coherence_before, 3)}%.",
            "dominant_dimensions": self.dominant_dimensions(limit=5),
            "dimensional_geometry": dict(self.dimensional_geometry),
            "dimensional_geometry_history": list(self.dimensional_geometry_history),
            "fundamental_unit": FUNDAMENTAL_UNIT,
            "hexlet_state_count": HEXLET_STATE_COUNT,
            "collapsed_hexlet_count": hexlets_before,
            "compressed_hexlet_essence": _compress_local_hexlets(essences),
            "collapsed_node_count": len(essences),
            "ram_released_estimate_nodes": released,
            "ram_released_estimate_hexlets": hexlets_before,
            "ram_before_estimate_bytes": ram_before,
            "essences": essences,
            "fake_success": False,
        }
        self.nodes = []
        self.active = False
        self.coherence = 0.0
        self.last_collapse["ram_after_estimate_bytes"] = self.memory_footprint_bytes()
        self.last_collapse["ram_released_estimate_bytes"] = max(
            0,
            int(self.last_collapse["ram_before_estimate_bytes"]) - int(self.last_collapse["ram_after_estimate_bytes"]),
        )
        return essences

    def dominant_dimensions(self, *, limit: int = 3) -> list[str]:
        if not self.nodes:
            collapse = self.last_collapse or {}
            dims = collapse.get("dominant_dimensions") if isinstance(collapse, Mapping) else []
            return [str(item) for item in list(dims or [])[:limit]]
        totals = [0.0] * 11
        for node in self.nodes:
            for index, value in enumerate(node.electron_state[:11]):
                totals[index] += value * node.weight
        ranked = sorted(enumerate(totals), key=lambda item: abs(item[1]), reverse=True)
        return [
            f"{POCKET_DIMENSIONS[index]}={round(value / max(1, len(self.nodes)), 4)}"
            for index, value in ranked[: max(1, min(11, int(limit or 3)))]
        ]

    def summary(self) -> str:
        state = "active" if self.active else "collapsed"
        return f"Quantum Foam Field {state}: {len(self.nodes)} nodes, coherence {round(self.coherence, 3)}%."

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "active" if self.active else "idle",
            "field_kind": FIELD_KIND,
            "field_alias": FIELD_ALIAS,
            "active": bool(self.active),
            "tick_count": self.tick_count,
            "fundamental_unit": FUNDAMENTAL_UNIT,
            "hexlet_state_count": HEXLET_STATE_COUNT,
            "hexlet_count": self.hexlet_count(),
            "symbolic_capacity_zettabytes": FIELD_SYMBOLIC_CAPACITY_ZETTABYTES,
            "memory_footprint_estimate_bytes": self.memory_footprint_bytes(),
            "coherence": round(float(self.coherence), 3),
            "field_coherence_percent": round(float(self.coherence), 3),
            "active_nodes": len(self.nodes),
            "node_count": len(self.nodes),
            "nodes": [node.to_dict(compact=True) for node in self.nodes],
            "entanglement_mesh": {
                "mesh_kind": "Entanglement Mesh",
                "components": ["AkashicNetwork", "ToolBridge", "WorldAgent", "OuroborosPersistentMemory", "LivingOuroborosLoop"],
                "edge_count": sum(len(node.connections) for node in self.nodes) // 2,
                "fundamental_unit": FUNDAMENTAL_UNIT,
            },
            "dominant_dimensions": self.dominant_dimensions(limit=5),
            "dimensional_geometry": self._current_dimensional_geometry(),
            "last_collapse": self.last_collapse,
            "mojo_runtime": mojo_runtime_status(),
            "fake_success": False,
        }

    def _advance_dimensional_geometry(
        self,
        *,
        trigger: str,
        target_clique_size: int | None = None,
    ) -> dict[str, Any]:
        if not self.nodes:
            self.dimensional_geometry = foam_geometry_stage_for_clique_size(0)
            return dict(self.dimensional_geometry)
        if target_clique_size is None:
            target_clique_size = 2 + max(0, self.tick_count - 1)
        try:
            target = int(target_clique_size or 0)
        except (TypeError, ValueError):
            target = 2
        if len(self.nodes) >= 2:
            target = max(2, target)
        else:
            target = len(self.nodes)
        target = min(FOAM_GEOMETRY_MAX_CLIQUE_SIZE, len(self.nodes), target)
        node_by_id = {node.node_id: node for node in self.nodes}
        selected_ids = [node_id for node_id in self.dimensional_clique_ids if node_id in node_by_id]
        for node in self.nodes:
            if len(selected_ids) >= target:
                break
            if node.node_id not in selected_ids:
                selected_ids.append(node.node_id)
        selected_ids = selected_ids[:target]
        selected_nodes = [node_by_id[node_id] for node_id in selected_ids if node_id in node_by_id]
        for index, left in enumerate(selected_nodes):
            for right in selected_nodes[index + 1:]:
                left.resonate(right)
        required_edges = len(selected_nodes) * (len(selected_nodes) - 1) // 2
        actual_edges = 0
        for index, left in enumerate(selected_nodes):
            for right in selected_nodes[index + 1:]:
                if right in left.connections and left in right.connections:
                    actual_edges += 1
        electron_ids = [
            node.hexlets[0].hexlet_id if node.hexlets else node.node_id
            for node in selected_nodes
        ]
        event = foam_geometry_stage_for_clique_size(len(selected_nodes))
        event.update(
            {
                "trigger": _clean_text(trigger)[:80],
                "tick": self.tick_count,
                "stimulus_count": len(self.dimensional_geometry_history) + 1,
                "clique_node_ids": selected_ids,
                "electron_clique": {
                    "electron_ids": electron_ids,
                    "node_ids": selected_ids,
                    "all_to_all_connected": actual_edges == required_edges,
                    "actual_edge_count": actual_edges,
                    "required_edge_count": required_edges,
                },
                "source": "controller_quantum_foam_dimensional_ladder",
                "fake_success": False,
            }
        )
        self.dimensional_clique_ids = selected_ids
        self.dimensional_geometry = event
        self.dimensional_geometry_history.append(event)
        self.dimensional_geometry_history = self.dimensional_geometry_history[-20:]
        return dict(event)

    def _current_dimensional_geometry(self) -> dict[str, Any]:
        event = dict(self.dimensional_geometry or foam_geometry_stage_for_clique_size(0))
        event["history"] = list(self.dimensional_geometry_history[-5:])
        return event

    def _update_coherence(self) -> None:
        if not self.nodes:
            self.coherence = 0.0
            return
        weights = sum(node.weight for node in self.nodes) / len(self.nodes)
        mesh_density = sum(len(node.connections) for node in self.nodes) / max(1, len(self.nodes) * (len(self.nodes) - 1))
        state_pressure = sum(abs(value) for node in self.nodes for value in node.electron_state[:11]) / max(1, len(self.nodes) * 11)
        hexlet_pressure = (
            sum(hexlet.coherence for node in self.nodes for hexlet in node.hexlets) / max(1, self.hexlet_count())
        )
        self.coherence = round(
            _clamp((weights * 0.46) + (mesh_density * 0.18) + (state_pressure * 0.18) + (hexlet_pressure * 0.18))
            * 100.0,
            3,
        )


def mojo_runtime_status() -> dict[str, Any]:
    """Report whether Mojo is present; Python remains the deterministic fallback."""

    binary = shutil.which("mojo")
    return {
        "available": bool(binary),
        "mode": "mojo" if binary else "python_fallback",
        "binary": binary or "",
        "python_fallback": not bool(binary),
        "fake_success": False,
    }


def agentic_foam_event(
    goal: str,
    *,
    phase: str,
    tool: str | None = None,
    result: Mapping[str, Any] | None = None,
    collapse: bool = False,
) -> dict[str, Any]:
    """Birth, evolve or collapse the shared v4.9 field for one agentic phase."""

    context = {
        "source": "agentic_processor",
        "phase": _clean_text(phase)[:80],
        "tool": _clean_text(tool or "")[:80],
        "result_status": str((result or {}).get("status") or "")[:80],
    }
    try:
        from ouroboros_esoteric.quantum_foam import (
            collapse_quantum_foam_field,
            initiate_quantum_foam_field,
            monitor_quantum_foam_field,
            quantum_foam_status,
        )

        if collapse:
            runtime = collapse_quantum_foam_field(reason=f"agentic_{context['phase'] or 'complete'}")
        else:
            status = quantum_foam_status(limit=1)
            if status.get("active_field"):
                runtime = monitor_quantum_foam_field(trigger=context["phase"] or "agentic")
            else:
                runtime = initiate_quantum_foam_field(
                    goal,
                    context=context,
                    collapse_existing=True,
                    max_ticks=12,
                )
        summary = living_field_summary(runtime, stimulus=goal)
        summary.update({"phase": context["phase"], "tool": context["tool"] or None})
        summary["pocket_payload"] = foam_context_for_pocket(goal, summary)
        return summary
    except Exception as exc:
        field = QuantumFoamField()
        if collapse:
            essences = field.collapse_field(reason=context["phase"] or "agentic_complete")
            payload = field.to_dict()
            payload.update({"status": "fallback_collapsed", "collapse_event": True, "essences": essences})
        else:
            field.spawn_field(goal, num_nodes=8)
            payload = field.to_dict()
            payload["status"] = "fallback_active"
        payload.update(
            {
                "phase": context["phase"],
                "tool": context["tool"] or None,
                "reason": str(exc)[:240],
                "pocket_payload": foam_context_for_pocket(goal, payload),
                "fake_success": False,
            }
        )
        return payload


def run_living_foam_cycle(
    stimulus: str,
    *,
    context: Mapping[str, Any] | None = None,
    collapse: bool = False,
) -> dict[str, Any]:
    phase = str((context or {}).get("phase") or ("complete" if collapse else "stimulus"))
    return agentic_foam_event(stimulus, phase=phase, tool=str((context or {}).get("tool") or "") or None, collapse=collapse)


def living_field_summary(runtime: Mapping[str, Any], *, stimulus: str = "") -> dict[str, Any]:
    """Normalize v4.9 field telemetry into cockpit/pocket-friendly shape."""

    field = _mapping(runtime.get("field")) or _mapping(runtime.get("active_field")) or _mapping(runtime.get("latest_field"))
    event = _mapping(runtime.get("event")) or _mapping(runtime.get("last_event"))
    essence = _mapping(runtime.get("essence")) or _mapping(field.get("collapse_essence"))
    nodes = _compact_nodes(field.get("nodes") if isinstance(field, Mapping) else [])
    field_status = str(field.get("status") or runtime.get("status") or "unknown")
    coherence = _coherence_0_to_1(field.get("field_coherence", runtime.get("field_coherence", event.get("field_coherence", 0.0))))
    coherence_percent = round(coherence * 100.0, 3)
    collapse_event = (
        str(event.get("action") or "").lower() == "collapsed"
        or str(runtime.get("status") or "").lower() == "collapsed"
        or field_status == "collapsed"
        or bool(essence)
    )
    dominant = _dominant_dimensions_from_field(field, essence=essence)
    dimensional_geometry = _mapping(field.get("dimensional_geometry")) or _mapping(essence.get("dimensional_geometry"))
    released = int(essence.get("ram_released_estimate_nodes") or 0) if essence else 0
    summary = str(essence.get("summary") or field.get("summary") or "").strip()
    if not summary:
        state = "collapsed" if collapse_event else ("active" if field_status == "active" else field_status)
        summary = f"Quantum Foam Field {state}: {len(nodes)} actieve node(s), coherence {coherence_percent:.1f}%."
    return {
        "status": str(runtime.get("status") or field_status or "unknown"),
        "field_kind": str(field.get("field_kind") or FIELD_KIND),
        "field_alias": str(field.get("field_alias") or FIELD_ALIAS),
        "fundamental_unit": str(field.get("fundamental_unit") or FUNDAMENTAL_UNIT),
        "hexlet_state_count": int(field.get("hexlet_state_count") or HEXLET_STATE_COUNT),
        "hexlet_count": int(field.get("hexlet_count") or 0),
        "active_hexlet_count": int(field.get("active_hexlet_count") or field.get("hexlet_count") or 0),
        "symbolic_capacity_zettabytes": int(field.get("symbolic_capacity_zettabytes") or FIELD_SYMBOLIC_CAPACITY_ZETTABYTES),
        "active": bool(field_status == "active" and not collapse_event),
        "field_id": str(field.get("field_id") or event.get("field_id") or ""),
        "task": str(field.get("task") or stimulus or "")[:500],
        "coherence": coherence_percent,
        "field_coherence": coherence,
        "field_coherence_percent": coherence_percent,
        "active_nodes": int(field.get("active_node_count") or len(nodes) or 0),
        "node_count": int(field.get("node_count") or len(nodes) or 0),
        "nodes": nodes,
        "dominant_dimensions": dominant,
        "dimensional_geometry": dimensional_geometry,
        "active_dimension": int(dimensional_geometry.get("dimension") or 0),
        "electron_clique_size": int(dimensional_geometry.get("clique_size") or 0),
        "field_collapsed": bool(collapse_event),
        "collapse_event": bool(collapse_event),
        "collapse_summary": summary if collapse_event else "",
        "ram_released_estimate_nodes": released,
        "ram_released_estimate_hexlets": int(essence.get("ram_released_estimate_hexlets") or 0) if essence else 0,
        "ram_released_estimate_bytes": int(essence.get("ram_released_estimate_bytes") or 0) if essence else 0,
        "entanglement_mesh": field.get("entanglement_mesh") or field.get("mesh") or {},
        "last_event": event,
        "mojo_runtime": mojo_runtime_status(),
        "summary": summary,
        "fake_success": False,
    }


def foam_context_for_pocket(stimulus: str, info: Mapping[str, Any]) -> dict[str, Any]:
    """Compact field summary sent into pocket_language_translator.py."""

    summary = living_field_summary(info, stimulus=stimulus) if "field_coherence" not in info and "coherence" not in info else dict(info)
    return {
        "status": "success",
        "source": "quantum_foam_field",
        "active": bool(summary.get("active")),
        "field_id": str(summary.get("field_id") or ""),
        "field_kind": str(summary.get("field_kind") or FIELD_KIND),
        "fundamental_unit": str(summary.get("fundamental_unit") or FUNDAMENTAL_UNIT),
        "hexlet_count": int(summary.get("hexlet_count") or 0),
        "summary": str(summary.get("summary") or summary.get("collapse_summary") or "")[:700],
        "coherence": float(summary.get("coherence") or 0.0),
        "field_coherence_percent": float(summary.get("field_coherence_percent") or summary.get("coherence") or 0.0),
        "dominant_dimensions": [str(item)[:120] for item in list(summary.get("dominant_dimensions") or [])[:5]],
        "dimensional_geometry": (
            dict(summary.get("dimensional_geometry"))
            if isinstance(summary.get("dimensional_geometry"), Mapping)
            else {}
        ),
        "active_dimension": int(summary.get("active_dimension") or 0),
        "electron_clique_size": int(summary.get("electron_clique_size") or 0),
        "nodes": [
            {
                "type": str(node.get("type") or node.get("node_type") or "Node")[:80],
                "weight": node.get("weight"),
                "coherence": node.get("coherence"),
                "connections": node.get("connection_count"),
            }
            for node in list(summary.get("nodes") or [])[:8]
            if isinstance(node, Mapping)
        ],
        "collapse_event": bool(summary.get("collapse_event") or summary.get("field_collapsed")),
        "ram_released_estimate_nodes": int(summary.get("ram_released_estimate_nodes") or 0),
        "ram_released_estimate_hexlets": int(summary.get("ram_released_estimate_hexlets") or 0),
        "ram_released_estimate_bytes": int(summary.get("ram_released_estimate_bytes") or 0),
        "mojo_runtime": summary.get("mojo_runtime") if isinstance(summary.get("mojo_runtime"), Mapping) else mojo_runtime_status(),
        "fake_success": False,
    }


def _compress_local_hexlets(source: Any) -> dict[str, Any]:
    hexlets: list[dict[str, Any]] = []
    total_count = 0
    for item in list(source or []):
        if not isinstance(item, Mapping):
            continue
        nested = item.get("hexlet_essence")
        if isinstance(nested, Mapping):
            total_count += int(nested.get("count") or item.get("hexlet_count") or 0)
            hexlets.extend([dict(value) for value in list(nested.get("sample") or []) if isinstance(value, Mapping)])
            continue
        if item.get("unit") == FUNDAMENTAL_UNIT or item.get("state_count") == HEXLET_STATE_COUNT:
            total_count += 1
            hexlets.append(dict(item))
    states = [str(item.get("hex_state") or format(int(item.get("state_index") or 0) % HEXLET_STATE_COUNT, "x")) for item in hexlets]
    coherence = [float(item.get("coherence") or 0.0) for item in hexlets]
    return {
        "unit": FUNDAMENTAL_UNIT,
        "state_count": HEXLET_STATE_COUNT,
        "count": total_count or len(hexlets),
        "hex_digest": _digest("".join(states))[:16] if states else "",
        "state_histogram": {state: states.count(state) for state in sorted(set(states))},
        "coherence": round(sum(coherence) / max(1, len(coherence)), 6),
        "sample": hexlets[:8],
        "fake_success": False,
    }


def _compact_nodes(nodes: Any) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for node in list(nodes or [])[:12]:
        if not isinstance(node, Mapping):
            continue
        node_type = str(node.get("node_type") or node.get("type") or "Node")
        output.append(
            {
                "node_id": str(node.get("node_id") or "")[:100],
                "type": node_type,
                "node_type": node_type,
                "weight": _round_float(node.get("weight")),
                "coherence": _round_float(node.get("coherence")),
                "active": bool(node.get("active", True)),
                "connection_count": int(node.get("connection_count") or 0),
                "hexlet_count": int(node.get("hexlet_count") or 0),
                "fundamental_unit": str(node.get("fundamental_unit") or FUNDAMENTAL_UNIT),
                "thoughts": [str(item)[:180] for item in list(node.get("thoughts") or [])[:3]],
            }
        )
    return output


def _dominant_dimensions_from_field(field: Mapping[str, Any], *, essence: Mapping[str, Any] | None = None) -> list[str]:
    anchor = _mapping(field.get("concept_anchor_field"))
    pockets = list(anchor.get("pockets") or [])
    ranked: list[tuple[str, float]] = []
    for item in pockets:
        if not isinstance(item, Mapping):
            continue
        name = str(item.get("name") or "")
        value = _float(item.get("current_energy", item.get("last_delivery", 0.0)))
        if name:
            ranked.append((name, value))
    if not ranked and essence:
        anchor_essence = _mapping(essence.get("concept_anchor_field"))
        signal = list(anchor_essence.get("pocket_signal") or [])
        ranked = [
            (POCKET_DIMENSIONS[index], _float(value))
            for index, value in enumerate(signal[:11])
        ]
    ranked.sort(key=lambda item: abs(item[1]), reverse=True)
    return [f"{name}={round(value, 4)}" for name, value in ranked[:5]]


def _node_types_for(stimulus: str) -> list[str]:
    lowered = stimulus.lower()
    types = ["ReasoningNode", "MemoryNode", "ReflectionNode", "PlanningNode"]
    if any(marker in lowered for marker in ("tool", "shell", "bestand", "file", "test", "command")):
        types.append("ToolNode")
    if any(marker in lowered for marker in ("web", "browser", "internet", "mail", "social", "post")):
        types.append("WorldActionNode")
    if any(marker in lowered for marker in ("codex", "programmeer", "code", "zelf")):
        types.append("CodexNode")
    if any(marker in lowered for marker in ("ruflo", "swarm", "fleet")):
        types.append("RufloNode")
    return types


def _seeded_11d_vector(seed: str) -> list[float]:
    rng = random.Random(_seed_int(seed))
    return [round(rng.uniform(-0.75, 0.75), 6) for _ in range(11)]


def _normalize_11d(value: Any) -> list[float]:
    values = [float(item) for item in list(value or [])[:11]]
    if len(values) < 11:
        values.extend([0.0] * (11 - len(values)))
    return [round(_clamp(item, -1.0, 1.0), 6) for item in values[:11]]


def _signal_values(value: Any) -> list[float]:
    if isinstance(value, (int, float)):
        number = float(value)
        return [number if math.isfinite(number) else 0.0]
    if isinstance(value, Mapping):
        values: list[float] = []
        for item in value.values():
            values.extend(_signal_values(item))
        return values[:512] or [0.0]
    if isinstance(value, (list, tuple, set)):
        values: list[float] = []
        for item in list(value):
            values.extend(_signal_values(item))
        return values[:512] or [0.0]
    text = str(value or "")
    return [((ord(char) % 255) / 127.5) - 1.0 for char in text[:512]] or [0.0]


def _coherence_0_to_1(value: Any) -> float:
    number = _float(value)
    if number > 1.0:
        number = number / 100.0
    return round(_clamp(number), 6)


def _round_float(value: Any) -> float:
    return round(_float(value), 6)


def _float(value: Any) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else 0.0
    except (TypeError, ValueError):
        return 0.0


def _std(values: list[float]) -> float:
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((item - mean) ** 2 for item in values) / len(values))


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").replace("\x00", " ").split())[:4000]


def _digest(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8", errors="replace")).hexdigest()


def _seed_int(value: str) -> int:
    return int(_digest(value)[:16], 16)


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
