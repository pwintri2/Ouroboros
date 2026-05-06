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


QF_VERSION = "v4.9"
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
    """Smallest runtime unit in the Quantum Foam Field."""

    node_id: str
    node_type: str
    weight: float
    task_fragment: str = ""
    state: ElectronState = field(default_factory=ElectronState)
    connections: dict[str, float] = field(default_factory=dict)
    coherence: float = 1.0
    active: bool = True
    created_at: str = field(default_factory=lambda: _utc_iso())
    last_resonance_at: str | None = None
    thoughts: deque[str] = field(default_factory=lambda: deque(maxlen=5))
    metadata: dict[str, Any] = field(default_factory=dict)

    def resonate(self, signal: Any, *, source_node_id: str | None = None, resonance: float = 1.0) -> dict[str, Any]:
        if not self.active:
            return self.to_dict(compact=True)
        electron = self.state.evolve(signal, resonance=resonance * self.weight)
        self.coherence = _clamp((self.coherence * 0.55) + (float(electron["coherence"]) * 0.45))
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

    def collapse(self) -> dict[str, Any]:
        essence = {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "weight": round(self.weight, 6),
            "coherence": round(self.coherence, 6),
            "thoughts": list(self.thoughts),
            "electron": self.state.collapse(),
        }
        self.active = False
        self.connections.clear()
        return essence

    def to_dict(self, *, compact: bool = False) -> dict[str, Any]:
        payload = {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "weight": round(float(self.weight), 6),
            "coherence": round(float(self.coherence), 6),
            "active": bool(self.active),
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
        return payload


class EntanglementMesh:
    """Direct node-to-node resonance mesh with Akashic broadcast fallback."""

    def __init__(self) -> None:
        self.network = AkashicNetwork()
        self._edges: dict[str, dict[str, float]] = {}

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
        return {"edge_count": edge_count, "edges": {key: dict(value) for key, value in self._edges.items()}}


class NodeFormationEngine:
    """Determine which nodes should form for a task."""

    def analyze_task(self, task: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        text = _clean_text(task)
        lowered = text.lower()
        words = [word for word in lowered.replace("/", " ").split() if word]
        unique_words = len(set(words))
        markers = {
            "tooling": any(item in lowered for item in ("tool", "shell", "test", "docker", "api", "endpoint", "file")),
            "world": any(item in lowered for item in ("world", "browser", "grok", "web", "internet")),
            "agent": any(item in lowered for item in ("codex", "ruflo", "roo", "agent", "swarm")),
            "training": any(item in lowered for item in ("train", "trainer", "litgpt", "unsloth", "dataset")),
            "memory": any(item in lowered for item in ("memory", "geheugen", "persistent", "11d", "chroma")),
            "nexus": any(item in lowered for item in ("nexus", "entropy", "coherence", "collapse", "quantum")),
        }
        complexity = _clamp((len(text) / 1800.0) + (unique_words / 120.0) + (sum(markers.values()) * 0.09))
        desired = max(5, min(FIELD_MAX_NODES, 5 + int(round(complexity * 14)) + sum(markers.values())))
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
        self._coherence = 1.0
        self._collapse_essence: dict[str, Any] | None = None
        self._recent_evolution: deque[dict[str, Any]] = deque(maxlen=20)

    def form_initial_nodes(self) -> dict[str, Any]:
        analysis = self.formation_engine.analyze_task(self.task, self.context)
        for spec in analysis["proposed_nodes"]:
            self.spawn_node(
                node_type=spec["node_type"],
                weight=spec["weight"],
                task_fragment=spec["task_fragment"],
                metadata={"formation": "initial", "markers": analysis["markers"]},
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
                    "ts": _utc_iso(),
                }
            )
        self.updated_at = _utc_iso()
        return self.to_dict(compact=True)

    def get_coherence(self) -> float:
        self._refresh_coherence()
        return round(float(self._coherence), 6)

    def collapse_field(self, *, reason: str = "completed", preserve_core: bool = True) -> dict[str, Any]:
        if self.status == "collapsed" and self._collapse_essence is not None:
            return dict(self._collapse_essence)
        node_essences = [node.collapse() for node in self.nodes.values()]
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
        essence = {
            "status": "collapsed",
            "field_id": self.field_id,
            "reason": _clean_text(reason)[:240],
            "summary": self.summary(),
            "key_insights": self.key_insights(node_essences=node_essences),
            "coherence": self.get_coherence(),
            "collapsed_node_count": len(node_essences),
            "remaining_node_count": len(self.nodes),
            "ram_released_estimate_nodes": max(0, len(node_essences) - len(self.nodes)),
            "collapsed_at": self.collapsed_at,
            "fake_success": False,
        }
        self._collapse_essence = essence
        return essence

    def summary(self) -> str:
        coherence = self.get_coherence()
        return (
            f"Quantum Foam Field {self.field_id} handled '{self.task[:160]}' "
            f"with {len(self.nodes)} retained nodes at coherence {coherence:.3f}."
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
            "field_id": self.field_id,
            "task": self.task[:500],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "collapsed_at": self.collapsed_at,
            "tick_count": self.tick_count,
            "max_ticks": self.max_ticks,
            "node_count": len(self.nodes),
            "active_node_count": sum(1 for node in self.nodes.values() if node.active),
            "field_coherence": self.get_coherence(),
            "field_coherence_percent": round(self.get_coherence() * 100.0, 3),
            "apeiron_metrics": metrics,
            "mesh": self.mesh.to_dict(),
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
            "coherence": self._coherence,
            "node_count": len(self.nodes),
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
            }
        )
        entropy_coh = float(entropy.get("coherence") or 0.0)
        self._coherence = _clamp((avg_node * 0.58) + (mesh_density * 0.17) + (entropy_coh * 0.25))


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
            },
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
                    "ram_released_estimate_nodes": essence.get("ram_released_estimate_nodes"),
                },
            )
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


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
