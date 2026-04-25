"""Minimal frequency-driven PAEU loop."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from .browser import BrowserAction, BrowserSnapshot, HumanBrowserEngine
from .memory import HippocampusMemory
from .oscillator import HertzOscillator
from .safety import evaluate_url
from .schema import build_11d_record, text_cluster_id


@dataclass(frozen=True)
class PAEUEvent:
    topic: str
    action: BrowserAction
    snapshot: BrowserSnapshot | None
    current_hz: float
    vibration_mood: str
    stored_record_id: str | None
    safety_reason: str


class PAEULoop:
    """Perceive, Act, Evaluate, Update loop for seed learning."""

    def __init__(
        self,
        oscillator: HertzOscillator,
        browser: HumanBrowserEngine,
        memory: HippocampusMemory,
        persona_actor: str = "resonant_ouroboros_fase_1",
    ):
        self.oscillator = oscillator
        self.browser = browser
        self.memory = memory
        self.persona_actor = persona_actor

    async def learn_topic(self, topic: str, steps: int = 3) -> list[PAEUEvent]:
        events: list[PAEUEvent] = []
        snapshot: BrowserSnapshot | None = None
        for _ in range(max(1, steps)):
            hz, behavior = self.oscillator.current_behavior()
            action = await self.browser.propose_next_action(topic, snapshot, behavior)
            safety_reason = "allowed"

            if action.action_type == "navigate":
                decision = evaluate_url(action.target)
                if not decision.allowed:
                    events.append(
                        PAEUEvent(topic, action, snapshot, hz, behavior.mood, None, decision.reason)
                    )
                    break
                safety_reason = decision.reason
                snapshot = await self.browser.navigate(action.target, behavior)
            elif action.action_type == "scroll":
                snapshot = await self.browser.scroll(behavior, action.target)
            elif action.action_type == "click":
                snapshot = await self.browser.click(action.target, behavior)
            elif action.action_type == "type":
                selector, text = action.target.split("::", maxsplit=1)
                snapshot = await self.browser.type(selector, text, behavior)
            else:
                raise ValueError(f"unsupported browser action: {action.action_type}")

            record_id = self._store_snapshot(topic, snapshot, hz, behavior.mood)
            events.append(PAEUEvent(topic, action, snapshot, hz, behavior.mood, record_id, safety_reason))
        return events

    def store_seed_topic_without_browser(self, topic: str, reason: str = "dry_run") -> str:
        """Store exact seed topics when Docker/browser execution is not active."""

        hz, behavior = self.oscillator.current_behavior()
        document = f"Seed topic queued for browser learning: {topic}. Reason: {reason}."
        record = build_11d_record(
            physical_structure="seed_topic_text",
            source_origin="AGI Kennis.txt",
            path_or_proprioception="/workspace/agi_kennis.txt",
            relative_temporal_position="now",
            persona_actor=self.persona_actor,
            intent_marker="seed_browser_learning_queue",
            user_context_marker="fase_1_seed_knowledge",
            emotional_valence=0.15,
            importance_score=0.92,
            karmic_weight=0.35,
            field_cluster_id=text_cluster_id(topic, prefix="seed"),
            current_hz=hz,
            vibration_mood=behavior.mood,
        )
        return self.memory.store(document, record)

    def _store_snapshot(
        self,
        topic: str,
        snapshot: BrowserSnapshot,
        hz: float,
        vibration_mood: str,
    ) -> str:
        now = datetime.now(UTC).isoformat()
        document = (
            f"Topic: {topic}\n"
            f"URL: {snapshot.url}\n"
            f"Title: {snapshot.title}\n"
            f"Vision: {snapshot.vision.summary}\n\n"
            f"Visible text:\n{snapshot.visible_text[:6000]}"
        )
        record = build_11d_record(
            physical_structure="webpage_screenshot_text",
            source_origin=snapshot.url,
            path_or_proprioception=snapshot.screenshot_path or snapshot.url,
            relative_temporal_position=now,
            persona_actor=self.persona_actor,
            intent_marker=f"learn:{topic}",
            user_context_marker="fase_1_agi_kennis_seed",
            emotional_valence=0.2 if hz < 600 else 0.55,
            importance_score=0.72 if hz < 600 else 0.86,
            karmic_weight=0.25,
            field_cluster_id=text_cluster_id(topic),
            current_hz=hz,
            vibration_mood=vibration_mood,
        )
        return self.memory.store(document, record)
