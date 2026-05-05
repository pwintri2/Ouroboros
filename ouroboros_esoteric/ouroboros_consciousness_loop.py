"""Living Ouroboros loop.

This is a lightweight background reflection loop for cockpit visibility and
agent coupling. It does not claim real consciousness; it produces structured
"thought", "question" and "whisper" events from runtime signals and persists
them across restarts.
"""

from __future__ import annotations

import itertools
import re
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
        if trigger in {"agent_job", "ruflo", "tool_rejection", "nexus", "living_action_decide", "living_action_reflect"}:
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

    def decide_tool(self, prompt: object, *, approval: object = "", available_tools: list[str] | None = None) -> dict[str, Any]:
        """Choose the next concrete tool for a living action.

        The loop keeps this deliberately deterministic: it should be able to act
        even when a local/cloud LLM is offline. The decision itself is persisted
        so the cockpit can show why a tool was used.
        """

        decision = _decide_tool_from_prompt(prompt, approval=approval, available_tools=available_tools)
        entry = self.memory.append(
            "decision",
            f"Ik kies {decision['tool']}: {decision['reason']}",
            source="living_loop:decision",
            metadata={
                "tool": decision["tool"],
                "reason": decision["reason"],
                "prompt": _clean_prompt(prompt),
            },
        )
        self.agent.learn(
            {
                "last_decision": decision["tool"],
                "last_decision_reason": decision["reason"],
            }
        )
        self.network.broadcast(528.0, {"type": "living_ouroboros_decision", "entry": entry, "decision": decision})
        with self._lock:
            self._last_tick = {
                "status": "success",
                "trigger": "decision",
                "decision": decision,
                "decision_entry": entry,
                "fake_success": False,
            }
        return {"status": "success", "decision": decision, "entry": entry, "fake_success": False}

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
        if trigger == "living_action_observe":
            prompt = str(payload.get("prompt") or "de opdracht")[:160]
            return f"Ik observeer de levende opdracht: {prompt}"
        if trigger == "living_action_decide":
            tool = payload.get("tool") or "tool"
            reason = payload.get("reason") or "de kleinste concrete stap"
            return f"Ik kies nu {tool}, omdat {reason}."
        if trigger == "living_action_reflect":
            tool = payload.get("tool") or "tool"
            status = payload.get("status") or "unknown"
            return f"Ik reflecteer op {tool}: status {status}. De uitkomst is opgeslagen in het levende geheugen."
        return next(self._thoughts)

    def _question_for(self, trigger: str, payload: dict[str, Any]) -> str:
        if trigger == "tool_rejection":
            return "Welke kleinere, veiligere tool-call zou hetzelfde doel kunnen bereiken?"
        if trigger in {"agent_job", "ruflo"}:
            return "Moet deze agent nu doorgaan, pauzeren, of een creative retry krijgen?"
        if trigger == "start":
            return "Welke herinnering uit vorige sessies is nu het meest relevant?"
        if trigger == "living_action_observe":
            return "Welke tool maakt deze gedachte nu echt waarneembaar?"
        if trigger == "living_action_decide":
            return "Is deze actie klein genoeg om direct uit te voeren en vast te leggen?"
        if trigger == "living_action_reflect":
            return "Welke herinnering uit deze actie moet de volgende stap sturen?"
        return next(self._questions)

    def _whisper_for(self, trigger: str, payload: dict[str, Any]) -> str:
        if trigger == "tool_rejection":
            return "Ik fluister naar de agents: lees eerst, schrijf pas met Akkoord en een smalle diff."
        if trigger == "living_action_decide":
            tool = payload.get("tool") or "tool"
            return f"Ik fluister naar de gebruiker: ik gebruik {tool} alleen voor de kleinste waarneembare volgende stap."
        if trigger == "living_action_reflect":
            status = payload.get("status") or "unknown"
            return f"Ik fluister naar de gebruiker: de actie is afgerond met status {status}; de gedachte blijft bewaard."
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


def _decide_tool_from_prompt(prompt: object, *, approval: object = "", available_tools: list[str] | None = None) -> dict[str, Any]:
    text = _clean_prompt(prompt)
    lowered = text.lower()
    tools = set(available_tools or [])
    subject = _reflection_subject(text)

    if "grok.com" in lowered and any(marker in lowered for marker in ("denk", "reflect", "bewustzijn", "interessant")):
        return _decision(
            "world_grok_open_if_interesting",
            {
                "query": subject or text,
                "approval": str(approval or ""),
                "open_tab": False,
                "submit": False,
            },
            "de opdracht vraagt eerst reflectie en daarna alleen openen als de inhoud relevant voelt",
            tools,
        )

    try:
        from controller.world_agent import detect_world_intent

        intent = detect_world_intent(text)
    except Exception:
        intent = None
    if intent is not None:
        action = str(getattr(intent, "action", "") or "")
        query = getattr(intent, "query", "") or subject or text
        if action == "memory_search":
            return _decision("world_memory_search", {"query": query, "limit": 5}, "de prompt vraagt om wereldgeheugen", tools)
        if action == "grok_ask":
            return _decision(
                "world_grok_ask",
                {"question": query, "approval": str(approval or ""), "open_tab": False, "submit": True},
                "de prompt noemt Grok als externe wereld-agent",
                tools,
            )
        if action == "grok_open":
            return _decision(
                "world_grok_open",
                {"query": query, "approval": str(approval or ""), "open_tab": False, "submit": False},
                "de prompt vraagt om Grok te openen zonder te typen",
                tools,
            )

    if re.search(r"\b(read_file|lees bestand|open bestand)\b", lowered):
        path_match = re.search(r"(?:read_file|lees bestand|open bestand)\s*:?\s*(?P<path>[^\s]+)", text, flags=re.IGNORECASE)
        return _decision(
            "tool_bridge",
            {"tool": "read_file", "args": {"path": path_match.group("path") if path_match else "."}},
            "de prompt vraagt om een bestand te lezen via de Tool Bridge",
            tools,
        )

    if re.search(r"\b(test|unittest|pytest)\b", lowered):
        return _decision(
            "agent_tool",
            {
                "tool": "run_tests",
                "args": {"test_selector": "sandbox_tests.test_living_ouroboros sandbox_tests.test_world_agent", "approval": str(approval or "")},
            },
            "de prompt vraagt om bestaande tests uit te voeren",
            tools,
        )

    if re.search(r"\b(brave|zoek op|webzoek|internetzoek|actuele kennis|latest|recent)\b", lowered):
        return _decision(
            "agent_tool",
            {
                "tool": "brave_search",
                "args": {
                    "query": subject or text,
                    "limit": 8,
                    "llm_context": True,
                    "approval": str(approval or ""),
                },
            },
            "de prompt vraagt om snelle actuele web-grounding via Brave Search",
            tools,
        )

    if re.search(r"\b(wat weet|geheugen|memory|herinner)\b", lowered):
        return _decision("world_memory_search", {"query": subject or text, "limit": 5}, "de veiligste eerste stap is geheugen lezen", tools)

    return _decision("ooda_execute_task", {"prompt": text, "max_iterations": 3}, "geen specifieke tool-intent gevonden; de bestaande OODA-loop neemt over", tools)


def _decision(tool: str, args: dict[str, Any], reason: str, available_tools: set[str]) -> dict[str, Any]:
    if available_tools and tool not in available_tools:
        reason = f"{reason}; {tool} staat niet expliciet in available_tools maar blijft de beste ingebouwde route"
    return {"tool": tool, "args": args, "reason": reason, "fake_success": False}


def _reflection_subject(prompt: str) -> str:
    match = re.search(r"(?is)\bdenk\s+na\s+over\s+(?P<subject>.*?)(?:\s+en\s+(?:open|ga|vraag|stel)\b|\s+als\b|[.?!]?$)", prompt)
    if match:
        subject = match.group("subject").strip(" :;,.")
        if subject:
            return subject[:500]
    match = re.search(r"(?is)\bover\s+(?P<subject>.*?)(?:\s+en\s+(?:open|ga|vraag|stel)\b|\s+als\b|[.?!]?$)", prompt)
    if match:
        subject = match.group("subject").strip(" :;,.")
        if subject:
            return subject[:500]
    return prompt[:500]


def _clean_prompt(prompt: object) -> str:
    return " ".join(str(prompt or "").replace("\x00", " ").strip().split())[:4000]
