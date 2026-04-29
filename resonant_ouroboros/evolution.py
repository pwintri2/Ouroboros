"""Append-only co-evolution event journal for Fase 4."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import threading
from typing import Any
from uuid import uuid4

from .self_model import compact_text


EVOLUTION_SCHEMA_VERSION = "ouroboros_co_evolution_proto_1_1_fase_4"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_evolution_path() -> Path:
    if Path("/workspace").exists():
        return Path("/workspace/data/awake_keeper_evolution_events.jsonl")
    return Path("data/awake_keeper_evolution_events.jsonl")


@dataclass(frozen=True)
class EvolutionEvent:
    event_type: str
    topic: str
    input_summary: str
    output_summary: str
    hz: float | None = None
    mood: str | None = None
    record_ids: list[str] = field(default_factory=list)
    source_urls: list[str] = field(default_factory=list)
    action_ids: list[str] = field(default_factory=list)
    status: str = "ok"
    safety: str = "safe_mode"
    model: str | None = None
    error: str | None = None
    importance: float = 0.5
    prompt_context_record_ids: list[str] = field(default_factory=list)
    score_delta: float = 0.0

    def row(self) -> dict[str, Any]:
        created_at = utc_now()
        return {
            "schema_version": EVOLUTION_SCHEMA_VERSION,
            "id": f"evo_{created_at.replace(':', '').replace('-', '')}_{uuid4().hex[:8]}",
            "created_at": created_at,
            "type": compact_text(self.event_type, 80),
            "topic": compact_text(self.topic, 220),
            "input_summary": compact_text(self.input_summary, 700),
            "output_summary": compact_text(self.output_summary, 900),
            "hz": float(self.hz) if self.hz is not None else None,
            "mood": compact_text(self.mood, 80) if self.mood else None,
            "record_ids": [compact_text(item, 180) for item in self.record_ids[:8]],
            "source_urls": [compact_text(item, 240) for item in self.source_urls[:6]],
            "action_ids": [compact_text(item, 180) for item in self.action_ids[:6]],
            "status": compact_text(self.status, 80),
            "safety": compact_text(self.safety, 240),
            "model": compact_text(self.model, 120) if self.model else None,
            "error": compact_text(self.error, 500) if self.error else None,
            "importance": max(0.0, min(1.0, float(self.importance))),
            "prompt_context_record_ids": [
                compact_text(item, 180) for item in self.prompt_context_record_ids[:8]
            ],
            "score_delta": round(max(0.0, min(1.0, float(self.score_delta))), 4),
        }


@dataclass(frozen=True)
class ReflectionEvent(EvolutionEvent):
    """Special event for reflections leading to improvement proposals."""

    proposal: str | None = None  # Proposed improvement
    proposal_kind: str | None = None
    proposal_payload: dict[str, Any] | None = None

    def row(self) -> dict[str, Any]:
        base = super().row()
        base["proposal"] = compact_text(self.proposal, 500) if self.proposal else None
        base["proposal_kind"] = compact_text(self.proposal_kind, 80) if self.proposal_kind else None
        base["proposal_payload"] = self._compact_payload(self.proposal_payload or {})
        return base

    def _compact_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        compact: dict[str, Any] = {}
        for key, value in payload.items():
            if isinstance(value, (str, int, float, bool)) or value is None:
                compact[compact_text(key, 80)] = compact_text(value, 700) if isinstance(value, str) else value
            elif isinstance(value, list):
                compact[compact_text(key, 80)] = [compact_text(item, 240) for item in value[:8]]
            else:
                compact[compact_text(key, 80)] = compact_text(value, 700)
        return compact


class EvolutionEventStore:
    """Small JSONL journal used as the durable co-evolution read model."""

    def __init__(self, path: str | Path | None = None, *, max_summary_events: int = 6):
        self.path = Path(path) if path is not None else default_evolution_path()
        self.max_summary_events = max(1, int(max_summary_events))
        self._lock = threading.RLock()

    @classmethod
    def from_env(cls) -> "EvolutionEventStore":
        return cls(path=os.getenv("AWAKE_KEEPER_EVOLUTION_EVENTS_PATH") or None)

    def append(self, event: EvolutionEvent) -> dict[str, Any]:
        row = event.row()
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        return row

    def list_events(self, limit: int = 20, event_type: str | None = None) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(int(limit or 20), 200))
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with self._lock:
            lines = self.path.read_text(encoding="utf-8", errors="ignore").splitlines()
        for line in reversed(lines):
            try:
                row = json.loads(line)
            except Exception:
                continue
            if event_type and row.get("type") != event_type:
                continue
            rows.append(row)
            if len(rows) >= bounded_limit:
                break
        return rows

    def count(self) -> int:
        if not self.path.exists():
            return 0
        with self._lock:
            return sum(1 for line in self.path.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip())

    def score(self) -> float:
        return float(self.scorecard()["score"])

    def autonomy_scorecard(
        self,
        *,
        runtime_status: dict[str, Any] | None = None,
        action_summary: dict[str, Any] | None = None,
        limit: int = 80,
    ) -> dict[str, Any]:
        """Return a bounded read model for visible self-sufficiency.

        This is not a permission model. It is a UI metric derived from recent
        local evidence: memory use, 11D linking, approved review proposals,
        safe-action health, and whether the loop is currently awake.
        """

        events = self.list_events(limit=limit)
        action_summary = action_summary or {}
        runtime_status = runtime_status or {}

        chat_events = [event for event in events if event.get("type") == "chat"]
        memory_assisted_chats = [
            event
            for event in chat_events
            if event.get("prompt_context_record_ids")
        ]
        knowledge_links = [event for event in events if event.get("type") == "knowledge_link"]
        approved_proposals = [
            event
            for event in events
            if (event.get("proposal") or "proposal" in str(event.get("type") or ""))
            and str(event.get("status") or "").lower() in {"approved", "executed"}
        ]
        learning_events = [event for event in events if event.get("type") in {"learning", "seed_learning", "local_learning"}]
        fallback_events = [event for event in events if str(event.get("status") or "").lower() == "fallback"]
        failed_events = [
            event
            for event in events
            if str(event.get("status") or "").lower() in {"failed", "blocked"}
        ]

        pending_approvals = int(action_summary.get("pending_count") or 0)
        pending_proposals = int(action_summary.get("pending_evolution_proposals") or 0)
        failed_actions = int(action_summary.get("failed_count") or 0)
        blocked_actions = int(action_summary.get("blocked_count") or 0)

        memory_signal = 0.0
        if chat_events:
            memory_signal = min(25.0, 25.0 * (len(memory_assisted_chats) / max(1, len(chat_events))))
        elif knowledge_links or learning_events:
            memory_signal = min(25.0, 10.0 + (1.5 * len(knowledge_links)))

        link_signal = min(20.0, len(knowledge_links) * 4.0)
        reflection_signal = min(15.0, len(approved_proposals) * 5.0)

        terminal_pressure = pending_approvals + pending_proposals + failed_actions + blocked_actions + len(failed_events)
        safe_action_signal = max(0.0, 20.0 - (terminal_pressure * 2.5))
        if approved_proposals:
            safe_action_signal = min(20.0, safe_action_signal + 2.0)

        liveness_signal = 0.0
        if runtime_status.get("running"):
            liveness_signal += 10.0
        if runtime_status.get("current_hz") is not None:
            liveness_signal += 4.0
        if runtime_status.get("current_topic"):
            liveness_signal += 3.0
        if events:
            liveness_signal += 3.0
        liveness_signal = min(20.0, liveness_signal)

        penalties = {
            "pending_approvals": pending_approvals,
            "pending_evolution_proposals": pending_proposals,
            "fallback_events": len(fallback_events),
            "failed_or_blocked_events": len(failed_events) + failed_actions + blocked_actions,
            "last_error": bool(runtime_status.get("last_error")),
        }
        penalty_score = (
            len(fallback_events) * 1.5
            + penalties["failed_or_blocked_events"] * 3.0
            + pending_approvals * 0.75
            + (4.0 if runtime_status.get("last_error") else 0.0)
        )

        signals = {
            "memory_assisted_answers": round(memory_signal, 1),
            "knowledge_links": round(link_signal, 1),
            "reflection_closure": round(reflection_signal, 1),
            "safe_action_health": round(safe_action_signal, 1),
            "liveness": round(liveness_signal, 1),
        }
        score = max(0.0, min(100.0, sum(signals.values()) - penalty_score))

        if score >= 75:
            level = "self_sufficient"
        elif score >= 50:
            level = "supervised_autonomy"
        elif score >= 25:
            level = "memory_assisted"
        else:
            level = "seeded"

        recent_delta = float(self.scorecard(limit=limit).get("recent_delta") or 0.0)
        if penalties["failed_or_blocked_events"] or penalties["last_error"]:
            trend = "needs_attention"
        elif recent_delta > 0.2 or len(knowledge_links) >= 2:
            trend = "warming"
        elif score > 0:
            trend = "stable"
        else:
            trend = "quiet"

        if pending_proposals:
            phase = "approval_waiting"
        elif runtime_status.get("running"):
            phase = "awake_learning"
        elif events:
            phase = "quiet_memory"
        else:
            phase = "seed_state"

        summary = (
            f"{level.replace('_', ' ')} at {score:.1f}%: "
            f"{len(memory_assisted_chats)} memory-assisted chat(s), "
            f"{len(knowledge_links)} recent 11D link(s), "
            f"{len(approved_proposals)} approved proposal(s)."
        )
        if pending_proposals:
            summary += f" {pending_proposals} evolution proposal(s) waiting for review."
        if penalties["last_error"]:
            summary += " Last runtime error is still visible."

        return {
            "score": round(score, 1),
            "level": level,
            "label": level.replace("_", " ").title(),
            "trend": trend,
            "phase": phase,
            "signals": signals,
            "penalties": penalties,
            "summary": compact_text(summary, 700),
            "meaning": (
                "Observational UI metric only; safety and execution still require explicit approval."
            ),
        }

    def scorecard(self, limit: int = 200) -> dict[str, Any]:
        """Return a bounded, explainable co-evolution score view.

        The score rewards useful, successful exchanges more than noisy or blocked
        events, while still keeping fallback and pending proposal signals visible.
        """

        events = self.list_events(limit=limit)
        by_type: dict[str, float] = {}
        score = 0.0
        recent_delta = 0.0
        proposal_events = 0
        fallback_events = 0
        failed_events = 0
        status_weights = {
            "ok": 1.0,
            "executed": 1.0,
            "approved": 0.8,
            "pending": 0.45,
            "fallback": 0.35,
            "blocked": 0.1,
            "rejected": 0.05,
            "failed": 0.0,
        }
        for index, event in enumerate(events):
            event_type = str(event.get("type") or "unknown")
            status = str(event.get("status") or "ok").lower()
            importance = max(0.0, min(1.0, float(event.get("importance") or 0.5)))
            delta = max(0.0, min(1.0, float(event.get("score_delta") or 0.0)))
            weighted = delta * (0.35 + (0.65 * importance)) * status_weights.get(status, 0.65)
            score += weighted
            by_type[event_type] = by_type.get(event_type, 0.0) + weighted
            if index < 12:
                recent_delta += weighted
            if "proposal" in event_type or event.get("proposal"):
                proposal_events += 1
            if status == "fallback":
                fallback_events += 1
            if status in {"failed", "blocked"}:
                failed_events += 1
        return {
            "score": round(score, 3),
            "recent_delta": round(recent_delta, 3),
            "event_count": len(events),
            "proposal_events": proposal_events,
            "fallback_events": fallback_events,
            "failed_or_blocked_events": failed_events,
            "by_type": {key: round(value, 3) for key, value in sorted(by_type.items())},
            "meaning": (
                "Weighted by importance, status, successful memory feedback, and approved safe proposals."
            ),
        }

    def summary(self, limit: int | None = None) -> str:
        events = self.list_events(limit=limit or self.max_summary_events)
        if not events:
            return "No co-evolution events have been recorded yet."
        parts = []
        for event in events:
            parts.append(
                f"{event.get('type')}:{compact_text(event.get('topic'), 90)} -> "
                f"{compact_text(event.get('output_summary'), 140)}"
            )
        return " | ".join(parts)

    def list_proposals(self, limit: int = 20) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for event in self.list_events(limit=200):
            event_type = str(event.get("type") or "")
            if event.get("proposal") or "proposal" in event_type:
                rows.append(event)
            if len(rows) >= max(1, min(int(limit or 20), 100)):
                break
        return rows

    def reflect(
        self,
        topic: str,
        input_summary: str,
        proposal: str,
        *,
        proposal_kind: str = "evolution_proposal",
        proposal_payload: dict[str, Any] | None = None,
        record_ids: list[str] | None = None,
        prompt_context_record_ids: list[str] | None = None,
        hz: float | None = None,
        mood: str | None = None,
        model: str | None = None,
        status: str = "pending",
        safety: str = "proposal_only_until_approved",
        score_delta: float = 0.0,
    ) -> dict[str, Any]:
        """Generate a reflection event with proposal."""

        event = ReflectionEvent(
            event_type="reflection_proposal",
            topic=topic,
            input_summary=input_summary,
            output_summary=f"Reflection generated an improvement proposal: {compact_text(proposal, 520)}",
            proposal=proposal,
            proposal_kind=proposal_kind,
            proposal_payload=proposal_payload or {},
            record_ids=record_ids or [],
            prompt_context_record_ids=prompt_context_record_ids or [],
            hz=hz,
            mood=mood,
            model=model,
            status=status,
            safety=safety,
            importance=0.8,
            score_delta=score_delta,
        )
        return self.append(event)
