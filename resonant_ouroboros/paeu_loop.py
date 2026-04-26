"""Minimal frequency-driven PAEU loop."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from .browser import BrowserAction, BrowserSnapshot, HumanBrowserEngine
from .memory import HippocampusMemory
from .oscillator import HertzOscillator
from .safety import evaluate_url, sanitize_query
from .schema import build_11d_record, text_cluster_id


@dataclass
class PAEUMetrics:
    topics_attempted: int = 0
    pages_visited: int = 0
    useful_records_stored: int = 0
    rejected_pages: int = 0
    hz_band_performance: dict[str, int] = field(
        default_factory=lambda: {"deep_read": 0, "curious_scan": 0, "creative_spike": 0}
    )


@dataclass(frozen=True)
class PAEUEvent:
    topic: str
    action: BrowserAction
    snapshot: BrowserSnapshot | None
    current_hz: float
    vibration_mood: str
    stored_record_id: str | None
    safety_reason: str
    signal_fidelity: float = 0.0


class PAEULoop:
    """Perceive, Act, Evaluate, Update loop for seed learning."""

    def __init__(
        self,
        oscillator: HertzOscillator,
        browser: HumanBrowserEngine,
        memory: HippocampusMemory,
        persona_actor: str = "resonant_ouroboros_fase_1",
        emotional_valence_provider: Callable[[str], float] | None = None,
    ):
        self.oscillator = oscillator
        self.browser = browser
        self.memory = memory
        self.persona_actor = persona_actor
        self.emotional_valence_provider = emotional_valence_provider
        self.metrics = PAEUMetrics()

    async def learn_topic(self, topic: str, steps: int = 3) -> list[PAEUEvent]:
        self.metrics.topics_attempted += 1
        events: list[PAEUEvent] = []
        snapshot: BrowserSnapshot | None = None
        for _ in range(max(0, steps)):
            current_hz, behavior = self.oscillator.current_behavior()
            self.metrics.hz_band_performance[behavior.mood] = self.metrics.hz_band_performance.get(behavior.mood, 0) + 1
            action = self.browser.propose_next_action(topic, snapshot, behavior)
            safety_reason = "allowed"
            stored_record_id: str | None = None
            signal_fidelity = 0.0

            try:
                if action.action_type == "navigate":
                    decision = evaluate_url(
                        action.target,
                        allow_private_hosts=getattr(self.browser, "allow_private_hosts", False),
                    )
                    safety_reason = decision.reason
                    if not decision.allowed:
                        events.append(
                            PAEUEvent(topic, action, snapshot, current_hz, behavior.mood, None, safety_reason, 0.0)
                        )
                        continue
                    snapshot = await self.browser.navigate(action.target, behavior)
                    self.metrics.pages_visited += 1
                elif action.action_type == "scroll":
                    direction = action.target or "down"
                    snapshot = await self.browser.scroll(behavior, direction=direction, steps=2)
                elif action.action_type == "click":
                    snapshot = await self.browser.click(action.target, behavior)
                elif action.action_type == "type":
                    selector, _, text = action.target.partition("::")
                    snapshot = await self.browser.type(selector, text, behavior)
                elif action.action_type == "read":
                    snapshot = await self.browser.read(behavior)
                else:
                    raise ValueError(f"unsupported browser action: {action.action_type}")
            except Exception as exc:
                events.append(
                    PAEUEvent(topic, action, snapshot, current_hz, behavior.mood, None, f"rejected: {exc}", 0.0)
                )
                self.metrics.rejected_pages += 1
                continue

            if snapshot and snapshot.accepted:
                emotional_valence = self._emotional_valence(snapshot.visible_text)
                record = build_11d_record(
                    physical_structure="webpage_screenshot_text",
                    source_origin=snapshot.url,
                    path_or_proprioception=snapshot.screenshot_path or "",
                    relative_temporal_position=datetime.now(timezone.utc).isoformat(),
                    persona_actor=self.persona_actor,
                    intent_marker=f"learn:{sanitize_query(topic, 80)}",
                    user_context_marker=topic,
                    emotional_valence=emotional_valence,
                    importance_score=min(1.0, max(0.0, snapshot.quality_score)),
                    karmic_weight=min(1.0, max(0.0, current_hz / 1200.0)),
                    field_cluster_id=text_cluster_id(f"{topic}\n{snapshot.visible_text}"),
                    current_hz=current_hz,
                    vibration_mood=behavior.mood,
                )
                document = f"{snapshot.title}\n{snapshot.url}\n{snapshot.visible_text}\n{snapshot.vision.summary}"
                stored_record_id = self.memory.store(document, record)
                self.metrics.useful_records_stored += 1
                signal_fidelity = snapshot.quality_score
            elif snapshot:
                self.metrics.rejected_pages += 1
                safety_reason = snapshot.quality_reason

            events.append(
                PAEUEvent(
                    topic=topic,
                    action=action,
                    snapshot=snapshot,
                    current_hz=current_hz,
                    vibration_mood=behavior.mood,
                    stored_record_id=stored_record_id,
                    safety_reason=safety_reason,
                    signal_fidelity=signal_fidelity,
                )
            )
        return events

    def _emotional_valence(self, text: str) -> float:
        if self.emotional_valence_provider is None:
            return 0.0
        try:
            return max(-1.0, min(1.0, float(self.emotional_valence_provider(text))))
        except Exception:
            return 0.0

    def store_seed_topic_without_browser(self, topic: str, reason: str = "dry_run") -> str:
        current_hz, behavior = self.oscillator.current_behavior()
        record = build_11d_record(
            physical_structure="seed_topic_text",
            source_origin="AGI Kennis.txt",
            path_or_proprioception=reason,
            relative_temporal_position=datetime.now(timezone.utc).isoformat(),
            persona_actor=self.persona_actor,
            intent_marker=f"seed:{sanitize_query(topic, 80)}",
            user_context_marker="seed",
            emotional_valence=self._emotional_valence(topic),
            importance_score=0.7,
            karmic_weight=0.5,
            field_cluster_id=text_cluster_id(topic),
            current_hz=current_hz,
            vibration_mood=behavior.mood,
        )
        return self.memory.store(topic, record)
