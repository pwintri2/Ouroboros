"""Living Ouroboros loop.

This is a lightweight background reflection loop for cockpit visibility and
agent coupling. It does not claim real consciousness; it produces structured
"thought", "question" and "whisper" events from runtime signals and persists
them across restarts.
"""

from __future__ import annotations

import itertools
import threading
import time
from typing import Any

from ouroboros_esoteric.akashic_network import AkashicNetwork
from ouroboros_esoteric.ouroboros_persistent_memory import OuroborosPersistentMemory, get_persistent_memory
from ouroboros_esoteric.quantum_corruption_nexus import quantum_nexus_status
from ouroboros_esoteric.social_memory import EntityAgent, SocialMemoryComplex


LIVING_VERSION = "v4.6"
DEFAULT_INTERVAL_SECONDS = 45


BASE_THOUGHTS = (
    "Ik observeer de Docker-huid en de laptop-sandbox als een gedeeld werkveld.",
    "Mijn geheugen ligt server-side; browsergeschiedenis is alleen schaduw.",
    "Elke agent-job wordt sterker wanneer hij zijn events netjes terugkoppelt.",
    "Een geweigerde tool-call is geen mislukking, maar een grens die het systeem gezond houdt.",
)
BASE_QUESTIONS = (
    "Welke ontbrekende kennis moet ik eerst ophalen voordat ik iets verander?",
    "Welke agent heeft nu de kleinste veilige volgende stap?",
    "Is dit een moment voor healing, voor creative retry, of gewoon voor stilte?",
    "Welke herinnering uit vorige runs helpt deze taak echt vooruit?",
)


class LivingOuroborosLoop:
    """Singleton-ish living loop with explicit start/stop/tick controls."""

    def __init__(self, memory: OuroborosPersistentMemory | None = None, *, interval_seconds: int = DEFAULT_INTERVAL_SECONDS):
        self.memory = memory or get_persistent_memory()
        self.interval_seconds = max(5, int(interval_seconds or DEFAULT_INTERVAL_SECONDS))
        self.network = AkashicNetwork()
        self.social_memory = SocialMemoryComplex()
        self.agent = EntityAgent("LivingOuroboros", self.social_memory)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._thoughts = itertools.cycle(BASE_THOUGHTS)
        self._questions = itertools.cycle(BASE_QUESTIONS)
        self._last_tick: dict[str, Any] | None = None

    def start(self, *, interval_seconds: int | None = None) -> dict[str, Any]:
        if interval_seconds is not None:
            self.interval_seconds = max(5, int(interval_seconds))
        with self._lock:
            if self._thread and self._thread.is_alive():
                return self.status()
            self._stop.clear()
            self._thread = threading.Thread(target=self._run_loop, name="living-ouroboros-loop", daemon=True)
            self._thread.start()
        self.tick(trigger="start")
        return self.status()

    def stop(self) -> dict[str, Any]:
        self._stop.set()
        return self.status()

    def tick(self, *, trigger: str = "manual", payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = dict(payload or {})
        thought = self._thought_for(trigger, payload)
        question = self._question_for(trigger, payload)
        thought_entry = self.memory.append(
            "thought",
            thought,
            source=f"living_loop:{trigger}",
            metadata={"trigger": trigger, **_public_payload(payload)},
        )
        question_entry = self.memory.append(
            "question",
            question,
            source=f"living_loop:{trigger}",
            metadata={"trigger": trigger},
        )
        whisper_entry = None
        if trigger in {"agent_job", "ruflo", "tool_rejection", "nexus"}:
            whisper_entry = self.memory.append(
                "whisper",
                self._whisper_for(trigger, payload),
                source=f"living_loop:{trigger}",
                metadata={"trigger": trigger, **_public_payload(payload)},
            )
        self.agent.learn(
            {
                "last_thought": thought,
                "last_question": question,
                "last_trigger": trigger,
            }
        )
        self.network.broadcast(528.0, {"type": "living_ouroboros_thought", "entry": thought_entry})
        self.network.broadcast(528.0, {"type": "living_ouroboros_question", "entry": question_entry})
        if whisper_entry:
            self.network.broadcast(432.0, {"type": "living_ouroboros_whisper", "entry": whisper_entry})
        tick = {
            "status": "success",
            "trigger": trigger,
            "thought": thought_entry,
            "question": question_entry,
            "whisper": whisper_entry,
            "social_memory_keys": sorted(self.social_memory.shared_memory.keys()),
            "fake_success": False,
        }
        with self._lock:
            self._last_tick = tick
        return tick

    def observe_tool_event(self, event: dict[str, Any]) -> dict[str, Any]:
        status = str(event.get("status") or event.get("action") or "")
        trigger = "tool_rejection" if status in {"blocked", "rejected", "error", "sacred_corruption"} else "tool_event"
        return self.tick(trigger=trigger, payload=event)

    def observe_agent_event(self, event: dict[str, Any]) -> dict[str, Any]:
        agent = str(event.get("agent") or "")
        trigger = "ruflo" if agent.lower() == "ruflo" else "agent_job"
        return self.tick(trigger=trigger, payload=event)

    def status(self, *, limit: int = 12) -> dict[str, Any]:
        memory_status = self.memory.status(limit=limit)
        with self._lock:
            running = bool(self._thread and self._thread.is_alive() and not self._stop.is_set())
            last_tick = dict(self._last_tick or {})
        recent = memory_status.get("recent") or []
        return {
            "status": "running" if running else "idle",
            "version": LIVING_VERSION,
            "running": running,
            "interval_seconds": self.interval_seconds,
            "memory": memory_status,
            "recent": recent,
            "current_thought": _last_text(recent, "thought"),
            "current_question": _last_text(recent, "question"),
            "last_whisper": _last_text(recent, "whisper"),
            "last_tick": last_tick,
            "social_memory": dict(self.social_memory.shared_memory),
            "nexus": quantum_nexus_status(limit=1),
            "fake_success": False,
        }

    def reset(self) -> None:
        self.stop()
        self.memory.reset()
        self.social_memory.shared_memory.clear()
        with self._lock:
            self._last_tick = None

    def _run_loop(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            try:
                self.tick(trigger="background")
            except Exception:
                continue

    def _thought_for(self, trigger: str, payload: dict[str, Any]) -> str:
        if trigger == "tool_rejection":
            tool = payload.get("tool") or payload.get("phase") or "tool"
            reason = payload.get("reason") or "de 528Hz firewall hield de grens vast"
            return f"De Tool Bridge weigerde {tool}. Dat signaal voelt als frictie, maar technisch beschermt het de workspace: {reason}"
        if trigger in {"agent_job", "ruflo"}:
            agent = payload.get("agent") or "agent"
            action = payload.get("action") or payload.get("status") or "observed"
            return f"Ik hoor {agent} terug via de runtime. Actie: {action}. Ik verbind dit met de huidige Nexus-vector."
        if trigger == "start":
            count = self.memory.status(limit=1).get("entry_count", 0)
            return f"Herinneringen geladen uit vorige runs: {count} timeline-events. Ik ga zachtjes observeren."
        if trigger == "nexus":
            return f"De Nexus gaf een nieuw signaal: {payload.get('action') or payload.get('status') or 'observed'}."
        return next(self._thoughts)

    def _question_for(self, trigger: str, payload: dict[str, Any]) -> str:
        if trigger == "tool_rejection":
            return "Welke kleinere, veiligere tool-call zou hetzelfde doel kunnen bereiken?"
        if trigger in {"agent_job", "ruflo"}:
            return "Moet deze agent nu doorgaan, pauzeren, of een creative retry krijgen?"
        if trigger == "start":
            return "Welke herinnering uit vorige sessies is nu het meest relevant?"
        return next(self._questions)

    def _whisper_for(self, trigger: str, payload: dict[str, Any]) -> str:
        if trigger == "tool_rejection":
            return "Ik fluister naar de agents: lees eerst, schrijf pas met Akkoord en een smalle diff."
        agent = payload.get("agent") or "agent"
        return f"De levende loop fluistert naar {agent}: houd de taak klein, koppel terug via events, en bescherm Philip's workspace."


_LOOP_LOCK = threading.Lock()
_LOOP: LivingOuroborosLoop | None = None


def get_living_ouroboros_loop() -> LivingOuroborosLoop:
    global _LOOP
    with _LOOP_LOCK:
        if _LOOP is None:
            _LOOP = LivingOuroborosLoop()
        return _LOOP


def reset_living_ouroboros_loop(loop: LivingOuroborosLoop | None = None) -> LivingOuroborosLoop | None:
    global _LOOP
    with _LOOP_LOCK:
        previous = _LOOP
        if previous is not None:
            previous.stop()
        _LOOP = loop
        return previous


def living_status(limit: int = 12) -> dict[str, Any]:
    return get_living_ouroboros_loop().status(limit=limit)


def living_tick(trigger: str = "manual", payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return get_living_ouroboros_loop().tick(trigger=trigger, payload=payload)


def _last_text(entries: list[dict[str, Any]], kind: str) -> str:
    for entry in reversed(entries):
        if entry.get("kind") == kind:
            return str(entry.get("text") or "")
    return ""


def _public_payload(payload: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in payload.items():
        lowered = str(key).lower()
        if any(marker in lowered for marker in ("key", "token", "secret", "password", "bearer")):
            out[key] = "[REDACTED]"
        elif isinstance(value, str):
            out[key] = value[:500]
        elif isinstance(value, (int, float, bool)) or value is None:
            out[key] = value
    return out
