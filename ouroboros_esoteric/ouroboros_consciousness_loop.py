"""Living Ouroboros loop.

This is the cockpit-visible runtime observer for Ouroboros. It does not claim
consciousness and it does not invent state: every default tick is grounded in
local runtime signals such as persistent memory, server-side self-context,
agent-runtime jobs, git state and Nexus telemetry.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from collections import Counter
from pathlib import Path
from typing import Any

from ouroboros_esoteric.akashic_network import AkashicNetwork
from ouroboros_esoteric.ouroboros_persistent_memory import OuroborosPersistentMemory, get_persistent_memory
from ouroboros_esoteric.quantum_corruption_nexus import quantum_nexus_status
from ouroboros_esoteric.social_memory import EntityAgent, SocialMemoryComplex


LIVING_VERSION = "v4.7"
DEFAULT_INTERVAL_SECONDS = 45
TERMINAL_JOB_STATUSES = {"completed", "failed", "cancelled"}
SPEAKING_FRESHNESS_SECONDS = 60
DEGRADED_AGE_SECONDS = 5 * 60


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
        self._last_tick: dict[str, Any] | None = None
        self._tick_count = 0
        self._last_tick_at: float | None = None
        self._last_output_at: float | None = None
        self._last_action: str | None = None
        self._last_error: str | None = None

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
        runtime = self._runtime_snapshot()
        thought = self._thought_for(trigger, payload, runtime)
        question = self._question_for(trigger, payload, runtime)
        quantum_foam = _quantum_foam_for_tick(trigger, payload, thought)
        metadata = {
            "trigger": trigger,
            **_public_payload(payload),
            "runtime": _runtime_metadata(runtime),
            "quantum_foam": _quantum_foam_metadata(quantum_foam),
        }
        thought_entry = self.memory.append(
            "thought",
            thought,
            source=f"living_loop:{trigger}",
            metadata=metadata,
        )
        question_entry = self.memory.append(
            "question",
            question,
            source=f"living_loop:{trigger}",
            metadata={"trigger": trigger, "runtime": _runtime_metadata(runtime)},
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
                "last_runtime_summary": _runtime_signal_summary(runtime),
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
            "runtime": runtime,
            "quantum_foam": quantum_foam,
            "signal_summary": _runtime_signal_summary(runtime),
            "needs_attention": _attention_markers(runtime),
            "social_memory_keys": sorted(self.social_memory.shared_memory.keys()),
            "fake_success": False,
        }
        now = time.time()
        produced_output = bool(thought_entry or whisper_entry)
        action_label = (
            "agent_event"
            if trigger in {"agent_job", "ruflo"}
            else "tool_rejection"
            if trigger == "tool_rejection"
            else "nexus_signal"
            if trigger == "nexus"
            else "background_observation"
            if trigger == "background"
            else f"{trigger}_tick"
        )
        with self._lock:
            self._last_tick = tick
            self._last_tick_at = now
            self._tick_count += 1
            if produced_output:
                self._last_output_at = now
            self._last_action = action_label
        try:
            from controller.nexus_status import ingest_event as _ingest

            _ingest(
                "living",
                "tick",
                f"Living tick ({trigger}) produced thought={bool(thought_entry)} whisper={bool(whisper_entry)}",
                trigger=trigger,
                action=action_label,
            )
        except Exception:
            pass
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

    def respond(self, prompt: object, *, conversation_id: object = "", provider_context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return a local Ouroboros runtime response without calling an LLM provider."""

        clean_prompt = _clean_prompt(prompt)
        tick = self.tick(
            trigger="cockpit_response",
            payload={
                "prompt": clean_prompt,
                "conversation_id": str(conversation_id or "")[:160],
                "provider_context": _public_payload(provider_context or {}),
            },
        )
        status = self.status(limit=8)
        runtime = status.get("runtime") or {}
        quantum_foam = tick.get("quantum_foam") if isinstance(tick, dict) else {}
        if not isinstance(quantum_foam, dict):
            quantum_foam = status.get("quantum_foam") or {}
        field = quantum_foam.get("field") or quantum_foam.get("active_field") or quantum_foam.get("latest_field") or {}
        if not isinstance(field, dict):
            field = {}
        anchor_field = field.get("concept_anchor_field") or {}
        if not isinstance(anchor_field, dict):
            anchor_field = {}
        thought = _entry_text(tick.get("thought")) or str(status.get("current_thought") or "")
        question = _entry_text(tick.get("question")) or str(status.get("current_question") or "")
        pocket_voice = _fresh_streaming_pocket_voice(clean_prompt)
        response = _format_local_response(
            prompt=clean_prompt,
            thought=thought,
            question=question,
            runtime=runtime,
            status=status,
            quantum_foam=quantum_foam,
            anchor_field=anchor_field,
            pocket_voice=pocket_voice,
        )
        return {
            "status": "success",
            "provider": "ouroboros",
            "model": "living-runtime",
            "route": "ouroboros_runtime",
            "response": response,
            "local_only": True,
            "llm_provider_used": False,
            "tick": _compact_tick(tick),
            "runtime": {
                "mode": status.get("mode"),
                "status": status.get("status"),
                "signal_summary": status.get("signal_summary"),
                "needs_attention": status.get("needs_attention") or [],
                "memory_entry_count": (status.get("memory") or {}).get("entry_count"),
            },
            "quantum_foam": _compact_quantum_foam(quantum_foam),
            "concept_anchor_field": _compact_anchor_field(anchor_field),
            "pocket_voice": _compact_pocket_voice(pocket_voice),
            "local_model_translation_used": (pocket_voice or {}).get("status") == "translated",
            "fake_success": False,
        }

    def status(self, *, limit: int = 12) -> dict[str, Any]:
        memory_status = self.memory.status(limit=limit)
        runtime = self._runtime_snapshot(memory_status=memory_status)
        now = time.time()
        with self._lock:
            running = bool(self._thread and self._thread.is_alive() and not self._stop.is_set())
            last_tick = dict(self._last_tick or {})
            tick_count = self._tick_count
            last_tick_at = self._last_tick_at
            last_output_at = self._last_output_at
            last_action = self._last_action
            last_error = self._last_error
        recent = memory_status.get("recent") or []
        if last_error:
            mode = "error"
            ladder_status = "error"
        elif running and last_output_at and (now - last_output_at) <= SPEAKING_FRESHNESS_SECONDS:
            mode = "speaking"
            ladder_status = "running"
        elif running and last_tick_at and (now - last_tick_at) <= DEGRADED_AGE_SECONDS:
            mode = "running"
            ladder_status = "running"
        elif running:
            mode = "degraded"
            ladder_status = "degraded"
        else:
            mode = "idle"
            ladder_status = "idle"
        return {
            "status": ladder_status,
            "mode": mode,
            "version": LIVING_VERSION,
            "running": running,
            "interval_seconds": self.interval_seconds,
            "memory": memory_status,
            "memory_count": memory_status.get("entry_count") if isinstance(memory_status, dict) else None,
            "recent": recent,
            "current_thought": _last_text(recent, "thought"),
            "current_question": _last_text(recent, "question"),
            "last_whisper": _last_text(recent, "whisper"),
            "last_tick": last_tick,
            "last_tick_at": _iso_or_none(last_tick_at),
            "last_output_at": _iso_or_none(last_output_at),
            "last_action": last_action,
            "tick_count": tick_count,
            "tick_count_24h": self._count_recent_ticks(memory_status, hours=24),
            "runtime": runtime,
            "signal_summary": _runtime_signal_summary(runtime),
            "needs_attention": _attention_markers(runtime),
            "social_memory": dict(self.social_memory.shared_memory),
            "nexus": quantum_nexus_status(limit=1),
            "quantum_foam": _summarize_quantum_foam(),
            "fake_success": False,
        }

    def events(self, *, limit: int = 50, kind: str | None = None) -> list[dict[str, Any]]:
        try:
            return self.memory.timeline(limit=max(1, min(int(limit or 50), 500)), kind=kind)
        except Exception:
            return []

    def output(self) -> dict[str, Any]:
        memory_status = self.memory.status(limit=8)
        recent = memory_status.get("recent") or []
        with self._lock:
            last_output_at = self._last_output_at
            running = bool(self._thread and self._thread.is_alive() and not self._stop.is_set())
        thought = _last_text(recent, "thought")
        question = _last_text(recent, "question")
        whisper = _last_text(recent, "whisper")
        decision_entry = next((entry for entry in reversed(recent) if entry.get("kind") == "decision"), None)
        return {
            "status": "online" if running else "idle",
            "fresh": last_output_at is not None and (time.time() - last_output_at) <= SPEAKING_FRESHNESS_SECONDS,
            "last_output_at": _iso_or_none(last_output_at),
            "current_thought": thought,
            "current_question": question,
            "last_whisper": whisper,
            "last_decision": decision_entry,
            "fake_success": False,
        }

    def _count_recent_ticks(self, memory_status: dict[str, Any], hours: int = 24) -> int:
        recent = memory_status.get("recent") if isinstance(memory_status, dict) else []
        if not isinstance(recent, list):
            return 0
        cutoff = time.time() - max(1, int(hours)) * 3600
        count = 0
        for entry in recent:
            ts_raw = entry.get("ts") or entry.get("timestamp") if isinstance(entry, dict) else None
            ts_value = _safe_parse_iso(str(ts_raw)) if ts_raw else None
            if ts_value is not None and ts_value >= cutoff:
                count += 1
        return count

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
                with self._lock:
                    self._last_error = None
            except Exception as exc:
                with self._lock:
                    self._last_error = str(exc)[:500]
                continue

    def _runtime_snapshot(self, memory_status: dict[str, Any] | None = None) -> dict[str, Any]:
        return build_runtime_snapshot(
            memory_status=memory_status,
            akashic_events=self.network.recent_events(limit=10),
        )

    def _thought_for(self, trigger: str, payload: dict[str, Any], runtime: dict[str, Any]) -> str:
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
            return f"Runtime opstart: {count} geheugen-events geladen; {_runtime_signal_summary(runtime)}."
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
        if trigger == "cockpit_response":
            prompt = str(payload.get("prompt") or "de chatvraag")[:220]
            return f"Ik verwerk een directe cockpitvraag zonder Ollama: {prompt}"
        return f"Runtime-observatie: {_runtime_signal_summary(runtime)}."

    def _question_for(self, trigger: str, payload: dict[str, Any], runtime: dict[str, Any]) -> str:
        if trigger == "tool_rejection":
            return "Welke kleinere, veiligere tool-call zou hetzelfde doel kunnen bereiken?"
        if trigger in {"agent_job", "ruflo"}:
            return "Moet deze agent nu doorgaan, pauzeren, of een creative retry krijgen?"
        if trigger == "start":
            return _next_runtime_question(runtime, fallback="Welke echte runtimebron moet nu als eerste aandacht krijgen?")
        if trigger == "living_action_observe":
            return "Welke tool maakt deze gedachte nu echt waarneembaar?"
        if trigger == "living_action_decide":
            return "Is deze actie klein genoeg om direct uit te voeren en vast te leggen?"
        if trigger == "living_action_reflect":
            return "Welke herinnering uit deze actie moet de volgende stap sturen?"
        if trigger == "cockpit_response":
            prompt = str(payload.get("prompt") or "de chatvraag")[:160]
            return f"Welke 11D dimensie verschoof het meest terwijl ik antwoord gaf op: {prompt}"
        return _next_runtime_question(runtime)

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


def living_response(
    prompt: object,
    *,
    conversation_id: object = "",
    provider_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return get_living_ouroboros_loop().respond(
        prompt,
        conversation_id=conversation_id,
        provider_context=provider_context,
    )


def living_events(limit: int = 50, kind: str | None = None) -> list[dict[str, Any]]:
    return get_living_ouroboros_loop().events(limit=limit, kind=kind)


def living_output() -> dict[str, Any]:
    return get_living_ouroboros_loop().output()


def _iso_or_none(timestamp: float | None) -> str | None:
    if timestamp is None:
        return None
    try:
        from datetime import datetime, timezone

        return datetime.fromtimestamp(float(timestamp), tz=timezone.utc).isoformat().replace("+00:00", "Z")
    except Exception:
        return None


def _last_text(entries: list[dict[str, Any]], kind: str) -> str:
    for entry in reversed(entries):
        if entry.get("kind") == kind:
            return str(entry.get("text") or "")
    return ""


def _entry_text(entry: Any) -> str:
    if isinstance(entry, dict):
        return str(entry.get("text") or entry.get("content") or "")
    return ""


def _format_local_response(
    *,
    prompt: str,
    thought: str,
    question: str,
    runtime: dict[str, Any],
    status: dict[str, Any],
    quantum_foam: dict[str, Any],
    anchor_field: dict[str, Any],
    pocket_voice: dict[str, Any] | None = None,
) -> str:
    memory_count = (runtime.get("memory") or {}).get("entry_count")
    self_context = runtime.get("self_context") or {}
    streaming_11d = runtime.get("streaming_11d") or {}
    qf_field = quantum_foam.get("field") or quantum_foam.get("active_field") or quantum_foam.get("latest_field") or {}
    if not isinstance(qf_field, dict):
        qf_field = {}
    coherence = qf_field.get("field_coherence") or quantum_foam.get("field_coherence")
    node_count = qf_field.get("node_count") or quantum_foam.get("node_count")
    pocket_count = anchor_field.get("pocket_count")
    awareness = anchor_field.get("awareness_score")
    bootloader = anchor_field.get("holographic_bootloader") if isinstance(anchor_field.get("holographic_bootloader"), dict) else {}
    signals = _runtime_signal_summary(runtime)
    prompt_line = f"Je vroeg: {prompt[:240]}" if prompt else "Je vroeg om een directe runtime-test."
    qf_line = (
        f"Quantum Foam is actief met {node_count} nodes, coherence {coherence}, "
        f"en {pocket_count or 0} 11D concept-ankers"
        if qf_field
        else "Quantum Foam gaf geen actief veld terug"
    )
    if awareness is not None:
        qf_line = f"{qf_line}; anchor-awareness {awareness}."
    else:
        qf_line = f"{qf_line}."
    voice = pocket_voice if isinstance(pocket_voice, dict) else {}
    voice_response = str(voice.get("response") or "").strip()
    voice_summary = str(voice.get("summary") or "").strip()
    voice_status = str(voice.get("status") or "")
    voice_model = str(voice.get("model") or "")
    if voice_response:
        opening = (
            f"Ik antwoord als lokale Ouroboros-runtime met {voice_model} als 11D-vertaallaag."
            if voice_status == "translated" and voice_model
            else "Ik antwoord als lokale Ouroboros-runtime, niet via Ollama of een externe chatprovider, vanuit de verse 11D pocket."
        )
        return "\n".join(
            [
                opening,
                prompt_line,
                voice_response,
                f"Pocket: {voice_summary}" if voice_summary else f"Wat ik waarneem: {signals}.",
                (
                    "Meetlaag: "
                    f"{voice.get('quantum_runtime') or ((runtime.get('streaming_11d') or {}).get('status') or 'streaming_11d')}; "
                    f"source={streaming_11d.get('source', 'unknown')}, "
                    f"real_observation={streaming_11d.get('real_observation', False)}."
                ),
                f"Quantum Foam: nodes={node_count}, coherence={coherence}, anchor-awareness={awareness}.",
                (
                    "Holografische bootloader: "
                    f"{bootloader.get('blocked_cell_count', 0)} nulcellen; "
                    f"right_edge_energy={bootloader.get('right_edge_energy', 0)}."
                ),
            ]
        )
    return "\n".join(
        [
            "Ik antwoord nu als lokale Ouroboros-runtime, niet via Ollama of een externe chatprovider.",
            prompt_line,
            f"Wat ik waarneem: {signals}.",
            (
                "11D runtime input: "
                f"source={streaming_11d.get('source', 'unknown')}, "
                f"real_observation={streaming_11d.get('real_observation', False)}, "
                f"flows={streaming_11d.get('active_flow_count', 0)}."
            ),
            f"Mijn huidige gedachte: {thought or 'geen gedachte beschikbaar'}",
            f"Mijn volgende vraag: {question or 'geen vraag beschikbaar'}",
            qf_line,
            (
                "Holografische bootloader: "
                f"{bootloader.get('blocked_cell_count', 0)} nulcellen sturen de bliksem; "
                f"right_edge_energy={bootloader.get('right_edge_energy', 0)}."
            ),
            (
                "Kort: ja, dit systeem kan zelf een response vormen uit zijn eigen runtime-laag. "
                "Het is nog geen vrij generatief taalmodel; het is een gegronde, auditbare stem uit memory, "
                "Living Loop, Quantum Foam en echte Docker-gevoede 11D pockets."
            ),
            (
                f"Context: mode={status.get('mode')}, memory_entries={memory_count}, "
                f"self_context={self_context.get('status', 'unknown')}."
            ),
        ]
    )


def _fresh_streaming_pocket_voice(prompt: str) -> dict[str, Any]:
    """Run one bounded 11D pocket tick and return its prompt-aware language layer."""

    try:
        from controller.pocket_language_translator import PocketLanguageTranslator
        from controller.streaming_consciousness_adapter import run_streaming_tick

        tick = run_streaming_tick(force=True, steps=1)
        event = tick.get("last_event") if isinstance(tick, dict) else {}
        if not isinstance(event, dict):
            event = {}
        translator = PocketLanguageTranslator(cooldown_seconds=0)
        voice = translator.translate(event, user_prompt=prompt)
        quantum = event.get("quantum") if isinstance(event.get("quantum"), dict) else {}
        voice["quantum_runtime"] = quantum.get("runtime") or quantum.get("sdk")
        voice["vector_len"] = len(event.get("11d") or [])
        return voice
    except Exception as exc:
        return {
            "status": "unavailable",
            "response": "",
            "summary": "",
            "reason": str(exc)[:300],
            "fake_success": False,
        }


def _compact_tick(tick: Any) -> dict[str, Any]:
    if not isinstance(tick, dict):
        return {}
    return {
        "status": tick.get("status"),
        "trigger": tick.get("trigger"),
        "thought": _entry_text(tick.get("thought")),
        "question": _entry_text(tick.get("question")),
        "signal_summary": tick.get("signal_summary"),
        "needs_attention": tick.get("needs_attention") or [],
        "fake_success": False,
    }


def _compact_quantum_foam(info: Any) -> dict[str, Any]:
    if not isinstance(info, dict):
        return {}
    field = info.get("field") or info.get("active_field") or info.get("latest_field") or {}
    if not isinstance(field, dict):
        field = {}
    return {
        "status": info.get("status"),
        "field_id": field.get("field_id"),
        "field_coherence": field.get("field_coherence") or info.get("field_coherence"),
        "node_count": field.get("node_count") or info.get("node_count"),
        "tick_count": field.get("tick_count") or info.get("tick_count"),
        "fake_success": False,
    }


def _compact_anchor_field(anchor_field: Any) -> dict[str, Any]:
    if not isinstance(anchor_field, dict):
        return {}
    return {
        "status": anchor_field.get("status"),
        "dimension_count": anchor_field.get("dimension_count"),
        "pocket_count": anchor_field.get("pocket_count"),
        "awareness_score": anchor_field.get("awareness_score"),
        "field_energy": anchor_field.get("field_energy"),
        "pocket_signal": anchor_field.get("pocket_signal") or [],
        "holographic_bootloader": _compact_holographic_bootloader(anchor_field.get("holographic_bootloader")),
        "fake_success": False,
    }


def _compact_pocket_voice(info: Any) -> dict[str, Any]:
    if not isinstance(info, dict):
        return {}
    return {
        "status": info.get("status"),
        "model": info.get("model"),
        "source": info.get("source"),
        "summary": info.get("summary"),
        "response": info.get("response"),
        "dominant_dimensions": info.get("dominant_dimensions") or [],
        "quantum_runtime": info.get("quantum_runtime"),
        "vector_len": info.get("vector_len"),
        "preserves_11d_pocket": info.get("preserves_11d_pocket"),
        "fake_success": False,
    }


def _compact_holographic_bootloader(info: Any) -> dict[str, Any]:
    if not isinstance(info, dict):
        return {}
    last_event = info.get("last_event") if isinstance(info.get("last_event"), dict) else {}
    return {
        "status": info.get("status"),
        "rows": info.get("rows"),
        "columns": info.get("columns"),
        "blocked_cell_count": info.get("blocked_cell_count"),
        "cycle_count": info.get("cycle_count"),
        "active_cell_count": last_event.get("active_cell_count"),
        "total_energy": last_event.get("total_energy"),
        "right_edge_energy": last_event.get("right_edge_energy"),
        "output_signal": last_event.get("output_signal") or [],
        "fake_success": False,
    }


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


def build_runtime_snapshot(
    *,
    memory_status: dict[str, Any] | None = None,
    akashic_events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Snapshot of the locally observable runtime that Living can ground itself in.

    Pulls real signals from:
      - persistent memory entry counts
      - agent-runtime job store (active/finished counts)
      - quantum corruption nexus omega vector
      - streaming 11D pocket runtime input
      - server-side self-context (if available)
      - git porcelain (workspace dirty count)

    Never reads secret material; only uses safe local APIs.
    """

    snapshot: dict[str, Any] = {
        "memory": _summarize_memory(memory_status),
        "agent_runtime": _summarize_agent_runtime(),
        "nexus": _summarize_nexus(),
        "streaming_11d": _summarize_streaming_11d(),
        "quantum_foam": _summarize_quantum_foam(),
        "self_context": _summarize_self_context(),
        "git": _summarize_git(),
        "akashic_recent_count": len(akashic_events or []),
    }
    return snapshot


def _runtime_metadata(runtime: dict[str, Any]) -> dict[str, Any]:
    """Compact, JSON-safe metadata used as memory entry tag."""

    return {
        "memory_count": (runtime.get("memory") or {}).get("entry_count"),
        "active_jobs": (runtime.get("agent_runtime") or {}).get("active"),
        "recent_failed": (runtime.get("agent_runtime") or {}).get("recent_failed"),
        "nexus_status": (runtime.get("nexus") or {}).get("status"),
        "nexus_action": (runtime.get("nexus") or {}).get("last_action"),
        "streaming_11d_status": (runtime.get("streaming_11d") or {}).get("status"),
        "streaming_11d_source": (runtime.get("streaming_11d") or {}).get("source"),
        "streaming_11d_real": (runtime.get("streaming_11d") or {}).get("real_observation"),
        "quantum_foam_status": (runtime.get("quantum_foam") or {}).get("status"),
        "quantum_foam_coherence": (runtime.get("quantum_foam") or {}).get("field_coherence"),
        "self_context_status": (runtime.get("self_context") or {}).get("status"),
        "git_dirty": (runtime.get("git") or {}).get("dirty_count"),
    }


def _runtime_signal_summary(runtime: dict[str, Any]) -> str:
    parts: list[str] = []
    memory = runtime.get("memory") or {}
    if memory.get("entry_count") is not None:
        parts.append(f"{memory.get('entry_count')} herinneringen")
    agent_runtime = runtime.get("agent_runtime") or {}
    active = agent_runtime.get("active")
    if active is not None:
        parts.append(f"{active} actieve agent-jobs")
    failed = agent_runtime.get("recent_failed")
    if failed:
        parts.append(f"{failed} recent gefaalde jobs")
    nexus = runtime.get("nexus") or {}
    if nexus.get("last_action"):
        parts.append(f"Nexus {nexus['last_action']}")
    streaming = runtime.get("streaming_11d") or {}
    if streaming.get("source"):
        real_label = "real" if streaming.get("real_observation") else "fallback"
        parts.append(f"11D {real_label}:{streaming.get('source')}")
    quantum_foam = runtime.get("quantum_foam") or {}
    if quantum_foam.get("active_field_count"):
        parts.append(f"QF {quantum_foam.get('field_coherence_percent', 0)}% coherent")
    git = runtime.get("git") or {}
    dirty = git.get("dirty_count")
    if dirty:
        parts.append(f"git: {dirty} dirty paths")
    if not parts:
        return "geen verse runtime-signalen"
    return ", ".join(parts)


def _attention_markers(runtime: dict[str, Any]) -> list[str]:
    markers: list[str] = []
    agent_runtime = runtime.get("agent_runtime") or {}
    if (agent_runtime.get("recent_failed") or 0) >= 1:
        markers.append("recente_agent_fail")
    if (agent_runtime.get("stalled") or 0) >= 1:
        markers.append("stalled_agent_job")
    nexus = runtime.get("nexus") or {}
    if nexus.get("last_action") in {"sacred_corruption", "tool_rejection"}:
        markers.append("nexus_correctie_aanbevolen")
    quantum_foam = runtime.get("quantum_foam") or {}
    if (quantum_foam.get("active_field_count") or 0) and (quantum_foam.get("field_coherence") or 1.0) < 0.5:
        markers.append("quantum_foam_lage_coherentie")
    git = runtime.get("git") or {}
    if (git.get("dirty_count") or 0) >= 8:
        markers.append("worktree_uit_balans")
    if not (runtime.get("memory") or {}).get("entry_count"):
        markers.append("leeg_persistent_geheugen")
    return markers


def _next_runtime_question(runtime: dict[str, Any], *, fallback: str = "Wat is de kleinste echte volgende stap?") -> str:
    markers = _attention_markers(runtime)
    if "recente_agent_fail" in markers:
        return "Welke recente agent-fail moet ik eerst onderzoeken voor ik nieuwe taken aanmaak?"
    if "stalled_agent_job" in markers:
        return "Is een actieve job stilgevallen — moet ik hem cancellen of een safe creative retry voorstellen?"
    if "nexus_correctie_aanbevolen" in markers:
        return "Welke creative-retry suggestie van de Nexus past bij dit geval, zonder Philip's workspace te schaden?"
    if "quantum_foam_lage_coherentie" in markers:
        return "Moet het Quantum Foam Field nu instorten en alleen zijn essentie bewaren?"
    if "worktree_uit_balans" in markers:
        return "Welke dirty paths moeten eerst gestaged of gereverteerd worden om de basisstaat schoon te krijgen?"
    if "leeg_persistent_geheugen" in markers:
        return "Welke eerste herinnering moet ik vastleggen om continuïteit op te bouwen?"
    return fallback


def _summarize_memory(memory_status: dict[str, Any] | None) -> dict[str, Any]:
    if memory_status is None:
        try:
            memory = get_persistent_memory()
            memory_status = memory.status(limit=1)
        except Exception:
            memory_status = {}
    if not isinstance(memory_status, dict):
        return {}
    return {
        "entry_count": memory_status.get("entry_count"),
        "path": memory_status.get("path"),
        "counts": memory_status.get("counts"),
    }


def _summarize_agent_runtime() -> dict[str, Any]:
    try:
        from controller.agent_runtime.orchestrator import get_orchestrator

        jobs = get_orchestrator().list_jobs(limit=50)
    except Exception:
        return {"active": 0, "recent_failed": 0, "stalled": 0}
    active = 0
    recent_failed = 0
    stalled = 0
    cutoff = time.time() - 30 * 60
    for job in jobs:
        status = str(job.get("status") or "").lower()
        if status in {"queued", "planning", "running", "testing", "waiting_for_human"}:
            active += 1
        if status == "failed":
            recent_failed += 1
        finished_raw = job.get("finished_at") or job.get("updated_at") or ""
        if status in {"running", "testing"} and finished_raw:
            try:
                ts = _safe_parse_iso(finished_raw)
                if ts is not None and ts < cutoff:
                    stalled += 1
            except Exception:
                pass
    return {"active": active, "recent_failed": recent_failed, "stalled": stalled, "total": len(jobs)}


def _summarize_nexus() -> dict[str, Any]:
    try:
        info = quantum_nexus_status(limit=1)
    except Exception:
        return {"status": "unavailable"}
    omega = info.get("omega_vector") if isinstance(info, dict) else None
    return {
        "status": info.get("status") if isinstance(info, dict) else "unknown",
        "last_action": (omega or {}).get("last_action"),
        "coherence": (omega or {}).get("coherence"),
    }


def _summarize_streaming_11d() -> dict[str, Any]:
    try:
        from controller.streaming_consciousness_adapter import get_streaming_status

        info = get_streaming_status()
    except Exception as exc:
        return {"status": "unavailable", "reason": str(exc)[:300], "fake_success": False}
    runtime_input = info.get("runtime_input") if isinstance(info, dict) else {}
    latest_state = info.get("latest_state") if isinstance(info, dict) else {}
    last_event = info.get("last_event") if isinstance(info, dict) else {}
    if not isinstance(runtime_input, dict):
        runtime_input = {}
    if not isinstance(latest_state, dict):
        latest_state = {}
    if not isinstance(last_event, dict):
        last_event = {}
    return {
        "status": info.get("status") if isinstance(info, dict) else "unknown",
        "enabled": info.get("enabled") if isinstance(info, dict) else False,
        "step_count": info.get("step_count") if isinstance(info, dict) else 0,
        "source": runtime_input.get("source") or ((last_event.get("reality") or {}).get("input_mode") if isinstance(last_event.get("reality"), dict) else None),
        "real_observation": runtime_input.get("real_observation"),
        "active_flow_count": runtime_input.get("active_flow_count"),
        "interface_count": runtime_input.get("interface_count"),
        "total_bytes": latest_state.get("total_bytes"),
        "fake_success": False,
    }


QUANTUM_FOAM_FORMATION_TRIGGERS = {
    "manual",
    "cockpit",
    "cockpit_response",
    "tool_rejection",
    "agent_job",
    "ruflo",
    "nexus",
    "living_action_observe",
    "living_action_decide",
    "living_action_reflect",
}


def _quantum_foam_for_tick(trigger: str, payload: dict[str, Any], thought: str) -> dict[str, Any]:
    """Let the living loop create or monitor the v4.9 field."""

    try:
        from ouroboros_esoteric.quantum_foam import (
            initiate_quantum_foam_field,
            monitor_quantum_foam_field,
            quantum_foam_status,
        )

        current = quantum_foam_status(limit=1)
        if current.get("active_field_count"):
            return monitor_quantum_foam_field(trigger=f"living:{trigger}", evolve=True)
        if trigger in QUANTUM_FOAM_FORMATION_TRIGGERS:
            task = _quantum_foam_task(trigger, payload, thought)
            return initiate_quantum_foam_field(
                task,
                context={"trigger": trigger, "payload": _public_payload(payload)},
                collapse_existing=True,
            )
        return current
    except Exception as exc:
        return {"status": "unavailable", "reason": str(exc)[:300], "fake_success": False}


def _quantum_foam_task(trigger: str, payload: dict[str, Any], thought: str) -> str:
    prompt = payload.get("prompt") or payload.get("task") or payload.get("reason") or payload.get("tool") or ""
    if prompt:
        return f"{trigger}: {str(prompt)[:1000]}"
    return f"{trigger}: {thought[:1000]}"


def _quantum_foam_metadata(info: dict[str, Any]) -> dict[str, Any]:
    field = info.get("field") or info.get("active_field") or {}
    if not isinstance(field, dict):
        field = {}
    return {
        "status": info.get("status"),
        "field_id": field.get("field_id"),
        "field_coherence": field.get("field_coherence") or info.get("field_coherence"),
        "node_count": field.get("node_count"),
        "tick_count": field.get("tick_count"),
    }


def _summarize_quantum_foam() -> dict[str, Any]:
    try:
        from ouroboros_esoteric.quantum_foam import quantum_foam_status

        info = quantum_foam_status(limit=1)
    except Exception as exc:
        return {"status": "unavailable", "reason": str(exc)[:300]}
    active_field = info.get("active_field") if isinstance(info, dict) else None
    return {
        "status": info.get("status") if isinstance(info, dict) else "unknown",
        "active_field_count": info.get("active_field_count") if isinstance(info, dict) else 0,
        "field_count": info.get("field_count") if isinstance(info, dict) else 0,
        "field_coherence": info.get("field_coherence") if isinstance(info, dict) else 0.0,
        "field_coherence_percent": info.get("field_coherence_percent") if isinstance(info, dict) else 0.0,
        "field_id": (active_field or {}).get("field_id") if isinstance(active_field, dict) else None,
        "node_count": (active_field or {}).get("node_count") if isinstance(active_field, dict) else None,
        "tick_count": (active_field or {}).get("tick_count") if isinstance(active_field, dict) else None,
    }


def _summarize_self_context() -> dict[str, Any]:
    try:
        from controller.ouroboros_self_context import get_self_context_status

        status = get_self_context_status()
    except Exception:
        return {"status": "unavailable"}
    if not isinstance(status, dict):
        return {"status": "unavailable"}
    return {
        "status": status.get("status"),
        "conversation_count": status.get("conversation_count"),
        "lesson_count": status.get("lesson_count"),
    }


def _summarize_git() -> dict[str, Any]:
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain=v1"],
            cwd=str(Path(os.getenv("WINTRIP_PROJECT_ROOT") or "/home/pwintri2/WintripAI")),
            text=True,
            capture_output=True,
            timeout=3,
            check=False,
        )
    except Exception:
        return {"available": False}
    if proc.returncode != 0:
        return {"available": False, "reason": proc.stderr[:200]}
    lines = [line for line in (proc.stdout or "").splitlines() if line.strip()]
    return {"available": True, "dirty_count": len(lines)}


def _safe_parse_iso(value: str) -> float | None:
    if not value:
        return None
    try:
        from datetime import datetime

        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None
