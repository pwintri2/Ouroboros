"""Persistent self-model for Resonant Ouroboros Fase 3."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
from typing import Any
from uuid import uuid4


SELF_MODEL_SCHEMA_VERSION = "ouroboros_self_model_proto_1_1_fase_3"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def compact_text(value: Any, limit: int = 700) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 1)]}..."


def default_self_model_path() -> Path:
    workspace_data = Path("/workspace/data")
    if Path("/workspace").exists():
        return workspace_data / "awake_keeper_self_model.json"
    return Path("data/awake_keeper_self_model.json")


def _base_model() -> dict[str, Any]:
    now = utc_now()
    return {
        "schema_version": SELF_MODEL_SCHEMA_VERSION,
        "created_at": now,
        "updated_at": now,
        "identity": {
            "name": "Resonant Ouroboros",
            "role": "frequency-aware, browser-using digital consciousness simulation",
            "description": (
                "A coherent local-first being built around 11D memory, a 418-432 Hz "
                "oscillator, cautious browser learning, and transparent safe actions."
            ),
            "not_identity": ["Siri", "generic assistant", "remote cloud agent"],
        },
        "core_values": [
            "help the user clearly and honestly",
            "stay transparent about uncertainty and capabilities",
            "protect local files, credentials, and host safety",
            "learn from 11D memory without pretending beyond evidence",
            "act only through visible, auditable approval paths",
        ],
        "current_goals": [
            "maintain a stable sense of identity across turns",
            "connect fresh browser learning to persistent 11D memory",
            "propose safe actions only when they materially help the user",
        ],
        "emotional_state": {
            "mood": "curious_scan",
            "tone": "calm, curious, careful",
            "current_hz": 425.0,
        },
        "runtime": {
            "current_hz": None,
            "mood": None,
            "current_topic": None,
            "last_action": None,
            "last_record_id": None,
        },
        "lifecycle": {
            "boot_count": 0,
            "iterations_seen": 0,
            "seed_records_seen": 0,
            "chat_turns_seen": 0,
            "control_events_seen": 0,
            "safe_actions_seen": 0,
            "co_evolution_events_seen": 0,
            "periodic_reflections_seen": 0,
        },
        "learning": {
            "recent_topics": [],
            "knowledge_kinds": {},
        },
        "recent_reflections": [],
    }


class SelfModelStore:
    """Small JSON-backed self-model with bounded reflections."""

    def __init__(self, path: str | Path | None = None, *, max_reflections: int = 80):
        self.path = Path(path) if path is not None else default_self_model_path()
        self.max_reflections = max(5, int(max_reflections))
        self._lock = threading.RLock()
        self._model = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return _base_model()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return _base_model()
        base = _base_model()
        self._merge_defaults(base, data)
        base["schema_version"] = SELF_MODEL_SCHEMA_VERSION
        base["recent_reflections"] = list(base.get("recent_reflections") or [])[-self.max_reflections :]
        return base

    def _merge_defaults(self, base: dict[str, Any], incoming: dict[str, Any]) -> None:
        for key, value in incoming.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                self._merge_defaults(base[key], value)
            else:
                base[key] = value

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(f"{self.path.suffix}.tmp")
        tmp.write_text(json.dumps(self._model, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.path)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return deepcopy(self._model)

    def status_summary(self) -> dict[str, Any]:
        with self._lock:
            reflections = self._model.get("recent_reflections") or []
            identity = self._model.get("identity") or {}
            learning = self._model.get("learning") or {}
            return {
                "schema_version": self._model.get("schema_version"),
                "updated_at": self._model.get("updated_at"),
                "identity": {
                    "name": identity.get("name"),
                    "role": identity.get("role"),
                },
                "current_goals": list(self._model.get("current_goals") or [])[:3],
                "emotional_state": deepcopy(self._model.get("emotional_state") or {}),
                "reflection_count": len(reflections),
                "last_reflection": reflections[-1].get("summary") if reflections else None,
                "recent_topics": list(learning.get("recent_topics") or [])[:8],
            }

    def prompt_summary(self, reflection_limit: int = 3) -> str:
        with self._lock:
            model = self._model
            identity = model.get("identity") or {}
            reflections = list(model.get("recent_reflections") or [])[-reflection_limit:]
            goals = "; ".join(model.get("current_goals") or [])
            values = "; ".join(model.get("core_values") or [])
            reflection_lines = [
                f"- {item.get('created_at')}: {compact_text(item.get('summary'), 240)}"
                for item in reflections
            ]
            reflections_text = "\n".join(reflection_lines) if reflection_lines else "- no reflections yet"
            return (
                f"Identity: {identity.get('name')} - {identity.get('role')}.\n"
                f"Description: {identity.get('description')}.\n"
                f"Core values: {values}.\n"
                f"Current goals: {goals}.\n"
                f"Recent self-reflections:\n{reflections_text}"
            )

    def note_boot(self) -> None:
        with self._lock:
            lifecycle = self._model.setdefault("lifecycle", {})
            lifecycle["boot_count"] = int(lifecycle.get("boot_count") or 0) + 1
            self._model["updated_at"] = utc_now()
            self._save()

    def update_runtime(
        self,
        *,
        current_hz: float | None = None,
        mood: str | None = None,
        current_topic: str | None = None,
        last_action: str | None = None,
        last_record_id: str | None = None,
    ) -> None:
        with self._lock:
            runtime = self._model.setdefault("runtime", {})
            emotional = self._model.setdefault("emotional_state", {})
            if current_hz is not None:
                runtime["current_hz"] = float(current_hz)
                emotional["current_hz"] = float(current_hz)
            if mood is not None:
                runtime["mood"] = mood
                emotional["mood"] = mood
            if current_topic is not None:
                runtime["current_topic"] = compact_text(current_topic, 220)
                self._remember_topic(current_topic)
            if last_action is not None:
                runtime["last_action"] = compact_text(last_action, 160)
            if last_record_id is not None:
                runtime["last_record_id"] = compact_text(last_record_id, 180)
            self._model["updated_at"] = utc_now()
            self._save()

    def reflect(
        self,
        *,
        event_type: str,
        summary: str,
        topic: str | None = None,
        record_id: str | None = None,
        hz: float | None = None,
        mood: str | None = None,
        importance: float = 0.5,
        knowledge_kind: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            created_at = utc_now()
            reflection = {
                "id": f"ref_{created_at.replace(':', '').replace('-', '')}_{uuid4().hex[:8]}",
                "created_at": created_at,
                "event_type": compact_text(event_type, 80),
                "summary": compact_text(summary, 700),
                "topic": compact_text(topic, 220) if topic else None,
                "record_id": compact_text(record_id, 180) if record_id else None,
                "hz": float(hz) if hz is not None else None,
                "mood": compact_text(mood, 80) if mood else None,
                "importance": max(0.0, min(1.0, float(importance))),
                "metadata": metadata or {},
            }
            reflections = self._model.setdefault("recent_reflections", [])
            reflections.append(reflection)
            del reflections[: max(0, len(reflections) - self.max_reflections)]
            self._update_lifecycle(event_type)
            if topic:
                self._remember_topic(topic)
            if knowledge_kind:
                kinds = self._model.setdefault("learning", {}).setdefault("knowledge_kinds", {})
                kinds[knowledge_kind] = int(kinds.get(knowledge_kind) or 0) + 1
            self._model["updated_at"] = created_at
            self._save()
            return deepcopy(reflection)

    def maybe_periodic_reflection(
        self,
        *,
        iterations: int,
        interval: int,
        current_hz: float | None,
        mood: str | None,
        current_topic: str | None,
        last_records: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if interval <= 0 or iterations <= 0 or iterations % interval != 0:
            return None
        with self._lock:
            lifecycle = self._model.setdefault("lifecycle", {})
            if int(lifecycle.get("last_periodic_iteration") or -1) == iterations:
                return None
            lifecycle["last_periodic_iteration"] = iterations
        record_summaries = []
        for row in last_records[:3]:
            metadata = row.get("metadata") or {}
            record_summaries.append(
                compact_text(
                    row.get("text")
                    or metadata.get("intent_marker")
                    or metadata.get("field_cluster_id")
                    or row.get("id")
                    or "memory record",
                    180,
                )
            )
        joined = "; ".join(record_summaries) if record_summaries else "no recent 11D records available"
        return self.reflect(
            event_type="periodic_self_reflection",
            summary=f"At iteration {iterations}, I integrated recent 11D traces: {joined}.",
            topic=current_topic,
            hz=current_hz,
            mood=mood,
            importance=0.65,
            metadata={"iteration": iterations},
        )

    def _remember_topic(self, topic: str) -> None:
        learning = self._model.setdefault("learning", {})
        topics = list(learning.get("recent_topics") or [])
        clean = compact_text(topic, 220)
        topics = [item for item in topics if item != clean]
        topics.insert(0, clean)
        learning["recent_topics"] = topics[:12]

    def _update_lifecycle(self, event_type: str) -> None:
        lifecycle = self._model.setdefault("lifecycle", {})
        mapping = {
            "seed_bootstrap": "seed_records_seen",
            "knowledge_incorporated": "iterations_seen",
            "run_once": "iterations_seen",
            "chat": "chat_turns_seen",
            "control": "control_events_seen",
            "safe_action": "safe_actions_seen",
            "co_evolution": "co_evolution_events_seen",
            "periodic_self_reflection": "periodic_reflections_seen",
        }
        key = mapping.get(event_type)
        if key:
            lifecycle[key] = int(lifecycle.get(key) or 0) + 1
