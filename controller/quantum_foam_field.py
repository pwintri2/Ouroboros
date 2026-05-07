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


@dataclass(eq=False)
class QuantumFoamNode:
    """Small symbolic node with recursive, non-binary 11D electron state."""

    type: str
    weight: float = 0.5
    electron_state: list[float] = field(default_factory=list)
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

        values = _signal_values(signal)
        pressure = sum(values) / max(1, len(values))
        spread = _std(values)
        updated: list[float] = []
        for index, value in enumerate(self.electron_state):
            incoming = values[index % len(values)] if values else pressure
            phase = math.sin((self.evolution_count + 1) * (index + 1) * 0.173)
            next_value = (value * 0.72) + (math.tanh(incoming + pressure) * 0.2 * resonance) + (phase * spread * 0.08)
            updated.append(round(_clamp(next_value, -1.0, 1.0), 6))
        self.electron_state = updated
        self.weight = _clamp((self.weight * 0.985) + (0.015 * (0.5 + abs(pressure) / 2.0)))
        self.evolution_count += 1
        self.last_resonance_at = time.time()
        return self.to_dict(compact=True)

    def collapse(self) -> dict[str, Any]:
        """Return only the node essence and release its direct links."""

        essence = {
            "type": self.type,
            "node_id": self.node_id,
            "weight": round(float(self.weight), 6),
            "essence": round(sum(self.electron_state) / max(1, len(self.electron_state)), 6),
            "dominant_dimension": self.dominant_dimensions(limit=1)[0] if self.electron_state else None,
            "evolution_count": int(self.evolution_count),
            "fake_success": False,
        }
        self.connections.clear()
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
            "fake_success": False,
        }
        if not compact:
            payload["electron_state"] = list(self.electron_state)
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

    def spawn_field(self, stimulus: str, num_nodes: int = 8) -> list[QuantumFoamNode]:
        self.active = True
        self.stimulus = _clean_text(stimulus)
        self.created_at = time.time()
        self.last_collapse = None
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
            for node in self.nodes:
                node.evolve(
                    {
                        "stimulus": signal,
                        "field_coherence": self.coherence,
                        "node_count": len(self.nodes),
                        "connections": len(node.connections),
                    }
                )
            self._update_coherence()
        return self.to_dict()

    def collapse_field(self, *, reason: str = "completed") -> list[dict[str, Any]]:
        if not self.active:
            return []
        essences = [node.collapse() for node in self.nodes]
        released = len(self.nodes)
        coherence_before = self.coherence
        self.last_collapse = {
            "status": "collapsed",
            "reason": _clean_text(reason)[:240],
            "summary": f"Quantum Foam Field collapsed: {released} nodes released, coherence {round(coherence_before, 3)}%.",
            "dominant_dimensions": self.dominant_dimensions(limit=5),
            "collapsed_node_count": len(essences),
            "ram_released_estimate_nodes": released,
            "essences": essences,
            "fake_success": False,
        }
        self.nodes = []
        self.active = False
        self.coherence = 0.0
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
            "active": bool(self.active),
            "coherence": round(float(self.coherence), 3),
            "field_coherence_percent": round(float(self.coherence), 3),
            "active_nodes": len(self.nodes),
            "node_count": len(self.nodes),
            "nodes": [node.to_dict(compact=True) for node in self.nodes],
            "dominant_dimensions": self.dominant_dimensions(limit=5),
            "last_collapse": self.last_collapse,
            "mojo_runtime": mojo_runtime_status(),
            "fake_success": False,
        }

    def _update_coherence(self) -> None:
        if not self.nodes:
            self.coherence = 0.0
            return
        weights = sum(node.weight for node in self.nodes) / len(self.nodes)
        mesh_density = sum(len(node.connections) for node in self.nodes) / max(1, len(self.nodes) * (len(self.nodes) - 1))
        state_pressure = sum(abs(value) for node in self.nodes for value in node.electron_state[:11]) / max(1, len(self.nodes) * 11)
        self.coherence = round(_clamp((weights * 0.58) + (mesh_density * 0.22) + (state_pressure * 0.2)) * 100.0, 3)


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
    released = int(essence.get("ram_released_estimate_nodes") or 0) if essence else 0
    summary = str(essence.get("summary") or field.get("summary") or "").strip()
    if not summary:
        state = "collapsed" if collapse_event else ("active" if field_status == "active" else field_status)
        summary = f"Quantum Foam Field {state}: {len(nodes)} actieve node(s), coherence {coherence_percent:.1f}%."
    return {
        "status": str(runtime.get("status") or field_status or "unknown"),
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
        "field_collapsed": bool(collapse_event),
        "collapse_event": bool(collapse_event),
        "collapse_summary": summary if collapse_event else "",
        "ram_released_estimate_nodes": released,
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
        "summary": str(summary.get("summary") or summary.get("collapse_summary") or "")[:700],
        "coherence": float(summary.get("coherence") or 0.0),
        "field_coherence_percent": float(summary.get("field_coherence_percent") or summary.get("coherence") or 0.0),
        "dominant_dimensions": [str(item)[:120] for item in list(summary.get("dominant_dimensions") or [])[:5]],
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
        "mojo_runtime": summary.get("mojo_runtime") if isinstance(summary.get("mojo_runtime"), Mapping) else mojo_runtime_status(),
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
