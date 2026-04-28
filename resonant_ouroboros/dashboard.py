"""Gradio dashboard and local REST API for the Fase 4 Awake Keeper."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
import os
from pathlib import Path
import shlex
from typing import Any

from .awake_keeper import AwakeKeeper, AwakeKeeperConfig, run_coroutine_sync
from .memory import HippocampusMemory, InMemoryHippocampusMemory, create_memory_from_env
from .oscillator import HertzOscillator
from .quantum_memory import QuantumMemoryBody
from .safe_executor import SAFE_EXEC_COMMANDS, SafeActionExecutor


_DASHBOARD_MEMORY_SINGLETON: HippocampusMemory | None = None


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "ja", "on"}


@dataclass(frozen=True)
class HzSample:
    sampled_at: datetime
    hz: float


class HzHistory:
    """Rolling 60-second Hertz history for the dashboard plot."""

    def __init__(self, window_seconds: float = 60.0):
        self.window_seconds = window_seconds
        self._samples: deque[HzSample] = deque()

    def add(self, hz: float, sampled_at: datetime | None = None) -> None:
        now = sampled_at or datetime.now(timezone.utc)
        self._samples.append(HzSample(now, hz))
        self._prune(now)

    def rows(self, now: datetime | None = None) -> list[dict[str, float]]:
        moment = now or datetime.now(timezone.utc)
        self._prune(moment)
        rows = []
        for sample in self._samples:
            seconds_ago = round((moment - sample.sampled_at).total_seconds(), 3)
            rows.append({"seconds_ago": seconds_ago, "hz": sample.hz})
        return rows

    def _prune(self, now: datetime) -> None:
        while self._samples and (now - self._samples[0].sampled_at).total_seconds() > self.window_seconds:
            self._samples.popleft()


@dataclass
class DashboardRuntime:
    """Shared runtime used by both Gradio and the standalone Goose-like UI."""

    keeper: AwakeKeeper
    oscillator: HertzOscillator
    history: HzHistory = field(default_factory=HzHistory)
    screenshot_path: Path = Path("/workspace/data/screenshots/current_browser_view.png")
    chat_log: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=80))
    safe_executor: SafeActionExecutor = field(default_factory=SafeActionExecutor.from_env)
    quantum_body: QuantumMemoryBody = field(default_factory=QuantumMemoryBody.from_env)
    server_approval_tokens: dict[str, str] = field(default_factory=dict)
    queued_periodic_reflections: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.keeper.reflection_proposal_callback = self.queue_periodic_reflection_proposal
        try:
            self.keeper.quantum_body = self.quantum_body
        except Exception:
            pass

    def _status_with_sample(self) -> tuple[Any, Any]:
        state = self.oscillator.modulation_state()
        self.history.add(state.current_hz)
        try:
            self.quantum_body.pulse(state.current_hz, mood=state.mood)
        except Exception:
            pass
        status = self.keeper.status()
        return status, state

    def status_payload(self) -> dict[str, Any]:
        status, state = self._status_with_sample()
        current_hz = status.current_hz if status.current_hz is not None else state.current_hz
        mood = status.vibration_mood or state.mood
        knowledge_feed = self.keeper.knowledge_feed()
        action_summary = self.safe_executor.summary()
        recent_events = self.keeper.evolution_store.list_events(limit=6)
        recent_links = self.keeper.evolution_store.list_events(limit=5, event_type="knowledge_link")
        recent_proposals = self.keeper.evolution_store.list_proposals(limit=6)
        scorecard = self.keeper.evolution_store.scorecard()
        growth = self.keeper.growth_indicators(action_summary=action_summary)
        autonomy = dict(growth["autonomy"])
        co_status = growth["co_evolution_status"]
        interaction = getattr(self.keeper.ollama, "last_interaction", None) or {}
        quantum_body = self.keeper.quantum_memory_status(hz=current_hz, mood=mood)
        autonomy["last_answer_mode"] = self._last_answer_mode(recent_events, interaction)
        ollama_core = {
            "model": status.ollama_model,
            "reachable": status.last_error is None,
            "last_task": interaction.get("task"),
            "success": interaction.get("success"),
            "fallback": interaction.get("fallback"),
            "latency_seconds": interaction.get("latency_seconds"),
            "co_evolution_state": co_status["state"],
            "co_evolution_label": co_status["label"],
            "score": scorecard["score"],
            "recent_delta": scorecard.get("recent_delta", 0),
            "event_count": self.keeper.evolution_store.count(),
            "pending_evolution_proposals": int(action_summary.get("pending_evolution_proposals") or 0),
            "help_moments": co_status["help_moments"],
            "summary": (
                f"{co_status['label']}: {co_status['summary']} "
                f"Autonomy {autonomy['score']:.1f}% ({autonomy['label']})."
            ),
        }
        collaboration = {
            "label": "Ollama <-> Core Collaboration",
            "state": co_status["state"],
            "active": co_status["active"],
            "model": status.ollama_model,
            "last_task": interaction.get("task"),
            "last_contribution": interaction.get("response_preview"),
            "core_recording": status.last_co_evolution_summary,
            "summary": ollama_core["summary"],
        }
        shell_status = {
            "enabled": bool(action_summary.get("sandbox_exec_enabled") or action_summary.get("docker_exec_enabled")),
            "mode": "sandbox_exec" if action_summary.get("sandbox_exec_enabled") else "docker_exec" if action_summary.get("docker_exec_enabled") else "approval_log_only",
            "cwd": action_summary.get("sandbox_cwd"),
            "whitelist": action_summary.get("whitelist") or [],
            "last_command_line": action_summary.get("last_command_line"),
            "last_exit_code": action_summary.get("last_exit_code"),
            "last_feedback": action_summary.get("last_command_feedback"),
            "last_stdout_preview": action_summary.get("last_stdout_preview"),
            "last_stderr_preview": action_summary.get("last_stderr_preview"),
        }
        updated_at = datetime.now(timezone.utc).isoformat()
        return {
            "ok": True,
            "safe_mode": True,
            "safe_mode_label": "Safe Mode: Docker-local API, localhost Ollama, public-browser safety gates",
            "running": status.running,
            "awake": status.running,
            "loop_started_at": status.loop_started_at,
            "loop_stopped_at": status.loop_stopped_at,
            "iterations": status.iterations,
            "browser_active": status.browser_active,
            "hz": current_hz,
            "current_hz": current_hz,
            "mood": mood,
            "vibration_mood": mood,
            "curiosity": state.curiosity_factor,
            "temperature": state.temperature_modifier,
            "current_topic": status.current_topic,
            "last_action": status.last_action,
            "last_record_id": status.last_record_id,
            "last_knowledge_kind": status.last_knowledge_kind,
            "last_source_url": status.last_source_url,
            "last_summary": status.last_summary,
            "last_error": status.last_error,
            "next_wake_at": status.next_wake_at,
            "ollama_model": status.ollama_model,
            "model": status.ollama_model,
            "seed_records_imported": status.seed_records_imported,
            "local_records_imported": status.local_records_imported,
            "learning_queue_size": status.learning_queue_size,
            "queue_size": status.learning_queue_size,
            "self_model": self.keeper.self_model.status_summary(),
            "autonomy": autonomy,
            "autonomy_level": autonomy["score"],
            "self_sufficiency_score": autonomy["score"],
            "ollama_core": ollama_core,
            "ollama_core_collaboration": collaboration,
            "co_evolution_status": co_status,
            "actions": action_summary,
            "sandbox": action_summary,
            "shell": shell_status,
            "quantum_memory": quantum_body,
            "co_evolution": {
                "score": scorecard["score"],
                "events": self.keeper.evolution_store.count(),
                "last_event": status.last_co_evolution_event,
                "last_summary": status.last_co_evolution_summary,
                "summary": self.keeper.evolution_store.summary(limit=5),
                "scorecard": scorecard,
                "ui_status": co_status,
                "status": co_status["state"],
                "active": co_status["active"],
                "help_moments": co_status["help_moments"],
                "recent_events": recent_events,
                "suggested_learning_actions": status.suggested_learning_actions,
            },
            "events": {
                "count": self.keeper.evolution_store.count(),
                "latest_event_id": recent_events[0].get("id") if recent_events else None,
                "recent": recent_events,
            },
            "knowledge_links": {
                "recent": recent_links,
                "count_recent": len(recent_links),
            },
            "proposals": {
                "pending_count": int(action_summary.get("pending_evolution_proposals") or 0),
                "recent": recent_proposals,
            },
            "history": self.history.rows(),
            "knowledge_feed": knowledge_feed,
            "screenshot": str(self.screenshot_path) if self.screenshot_path.exists() else None,
            "poll_seconds": 1.5,
            "updated_at": updated_at,
            "ollama": {
                "reachable": status.last_error is None,
                "base_url": self.keeper.config.ollama_base_url,
                "model": status.ollama_model,
            },
            "memory": {
                "records": self._memory_count_fallback(len(knowledge_feed)),
                "last_record_id": status.last_record_id,
                "last_source": status.last_source_url,
                "backend": self._memory_info(),
            },
            "api": {
                "status": "/status",
                "chat": "/chat",
                "control": "/control",
                "memory": "/memory",
                "self_model": "/self-model",
                "actions": "/actions",
                "evolution": "/evolution",
                "events": "/events",
                "reflect": "/reflect",
            },
        }

    def status_lines(self) -> str:
        status = self.status_payload()
        rows = [
            f"safe_mode: {status['safe_mode']}",
            f"running: {status['running']}",
            f"iterations: {status['iterations']}",
            f"browser_active: {status['browser_active']}",
            f"current_hz: {status['current_hz']}",
            f"vibration_mood: {status['vibration_mood']}",
            f"current_topic: {status['current_topic']}",
            f"last_action: {status['last_action']}",
            f"last_record_id: {status['last_record_id']}",
            f"last_knowledge_kind: {status['last_knowledge_kind']}",
            f"last_source_url: {status['last_source_url']}",
            f"last_summary: {status['last_summary']}",
            f"last_error: {status['last_error']}",
            f"next_wake_at: {status['next_wake_at']}",
            f"ollama_model: {status['ollama_model']}",
            f"seed_records_imported: {status['seed_records_imported']}",
            f"local_records_imported: {status['local_records_imported']}",
            f"learning_queue_size: {status['learning_queue_size']}",
            f"self_model_reflections: {status['self_model']['reflection_count']}",
            f"last_self_reflection: {status['self_model']['last_reflection']}",
            f"pending_actions: {status['actions']['pending_count']}",
            f"co_evolution_score: {status['co_evolution']['score']}",
            f"co_evolution_events: {status['co_evolution']['events']}",
            f"co_evolution_status: {status['co_evolution']['ui_status']['label']}",
            f"co_evolution_active: {status['co_evolution']['ui_status']['active']}",
            f"ollama_core_collaboration: {status['ollama_core_collaboration']['summary']}",
            f"quantum_memory_body: {status['quantum_memory']['body_label']} allocated={status['quantum_memory']['allocated']} pulses={status['quantum_memory']['pulse_count']} write_head_mb={status['quantum_memory']['write_head_mb']}",
            f"autonomy_level: {status['autonomy']['score']}%",
            f"autonomy_label: {status['autonomy']['label']}",
            f"autonomy_last_answer_mode: {status['autonomy']['last_answer_mode']['label']}",
            f"pending_evolution_proposals: {status['proposals']['pending_count']}",
            f"recent_knowledge_links: {status['knowledge_links']['count_recent']}",
            f"sandbox_exec_enabled: {status['actions']['sandbox_exec_enabled']}",
            f"last_shell_feedback: {status['shell']['last_feedback'] or 'none'}",
            f"last_shell_stdout: {status['shell']['last_stdout_preview'] or ''}",
            f"last_shell_stderr: {status['shell']['last_stderr_preview'] or ''}",
        ]
        return "\n".join(rows)

    def growth_lines(self, payload: dict[str, Any] | None = None) -> str:
        status = payload or self.status_payload()
        co_status = status["co_evolution"]["ui_status"]
        autonomy = status["autonomy"]
        collaboration = status["ollama_core_collaboration"]
        shell = status["shell"]
        quantum = status["quantum_memory"]
        moments = co_status.get("help_moments") or []
        moment_rows = [
            f"- {moment.get('summary')}"
            for moment in moments[:5]
        ] or ["- No mutual-help moments yet."]
        return "\n".join(
            [
                f"Co-evolution Status: {co_status['label']} [{co_status['indicator']}]",
                f"Ollama <-> Core Collaboration: {collaboration['summary']}",
                f"Core recorded: {collaboration.get('core_recording') or 'waiting for next contribution'}",
                f"Active collaboration: {co_status['active']}",
                f"Recent co-evolution delta: {co_status.get('recent_delta', 0)}",
                f"Autonomy Level: {autonomy['score']}% ({autonomy['label']}, {autonomy['trend']})",
                f"Last answer mode: {autonomy['last_answer_mode']['label']} - {autonomy['last_answer_mode']['summary']}",
                f"Self-sufficiency phase: {autonomy['phase']}",
                f"Meaning: {autonomy['summary']}",
                f"Hands/feet shell: {shell['mode']} in {shell.get('cwd')}; last={shell.get('last_feedback') or 'none'}",
                f"Quantum memory body: {quantum['body_label']} / band={quantum['frequency_band']} / write_head={quantum['write_head_mb']}MB",
                "Recent mutual help:",
                *moment_rows,
            ]
        )

    def gradio_outputs(self):
        payload = self.status_payload()
        hz_label = (
            f"{float(payload['current_hz']):.2f} Hz | {payload['vibration_mood']} | "
            f"curiosity {float(payload['curiosity']):.2f} | Safe Mode"
        )
        return (
            self.status_lines(),
            payload["history"],
            hz_label,
            payload["screenshot"],
            payload["knowledge_feed"],
            self.growth_lines(payload),
            payload["quantum_memory"]["visualization"],
        )

    def _build_chat_provenance(self, status: dict[str, Any]) -> dict[str, Any]:
        """Assemble the chat-time provenance trace shown in the UI.

        The trace explains which 11D records the answer was built from, which
        Hz/mood the body was in, what the quantum body was doing, and whether
        Ollama was needed or the core answered from memory.
        """

        events = (status.get("co_evolution") or {}).get("recent_events") or []
        chat_event: dict[str, Any] | None = next(
            (event for event in events if event.get("type") == "chat"),
            None,
        )
        prompt_record_ids = [
            str(item)
            for item in (chat_event or {}).get("prompt_context_record_ids") or []
            if str(item).strip()
        ]
        record_ids = [
            str(item)
            for item in (chat_event or {}).get("record_ids") or []
            if str(item).strip()
        ]
        ollama_core = status.get("ollama_core") or {}
        autonomy = status.get("autonomy") or {}
        last_answer_mode = autonomy.get("last_answer_mode") or {}
        memory_info = (status.get("memory") or {}).get("backend") or {}
        quantum = status.get("quantum_memory") or {}
        ollama_used = bool(ollama_core.get("reachable")) and bool(ollama_core.get("last_task"))
        fallback = bool(last_answer_mode.get("fallback")) or bool(ollama_core.get("fallback"))
        if last_answer_mode.get("mostly_own_memory"):
            origin = "11D memory primary, Ollama assist"
        elif prompt_record_ids:
            origin = "balanced 11D memory + Ollama"
        elif ollama_used:
            origin = "Ollama-led, no records retrieved"
        else:
            origin = "core only (no Ollama interaction recorded)"
        story = (
            f"Body was at {status.get('current_hz', '?')} Hz / {status.get('vibration_mood', 'unknown')} "
            f"({quantum.get('frequency_band') or 'baseline_418_432'}), "
            f"write head {quantum.get('write_head_mb', 0)} MB into the {quantum.get('body_label') or 'quantum body'}. "
            f"Origin: {origin}. "
            f"{len(prompt_record_ids)} prompt record(s) retrieved; "
            f"{len(record_ids)} record(s) stamped this turn."
        )
        return {
            "label": last_answer_mode.get("label") or "Memory + Ollama",
            "summary": last_answer_mode.get("summary") or story,
            "story": story,
            "origin": origin,
            "ollama_used": ollama_used,
            "ollama_fallback": fallback,
            "ollama_model": ollama_core.get("model"),
            "ollama_latency_seconds": ollama_core.get("latency_seconds"),
            "memory_backend": memory_info.get("backend"),
            "memory_collection": memory_info.get("collection"),
            "memory_records_total": memory_info.get("records"),
            "prompt_record_ids": prompt_record_ids,
            "stamped_record_ids": record_ids,
            "quantum": {
                "frequency_band": quantum.get("frequency_band"),
                "frequency_hz": quantum.get("frequency_hz"),
                "write_head_mb": quantum.get("write_head_mb"),
                "pulse_count": quantum.get("pulse_count"),
                "body_label": quantum.get("body_label"),
            },
        }

    def _last_answer_mode(self, events: list[dict[str, Any]], interaction: dict[str, Any]) -> dict[str, Any]:
        chat = next((event for event in events if event.get("type") == "chat"), None)
        if not chat:
            return {
                "label": "No chat answer yet",
                "summary": "Waiting for a chat turn to measure memory/Ollama balance.",
                "prompt_record_count": 0,
                "mostly_own_memory": False,
            }
        prompt_records = [item for item in (chat.get("prompt_context_record_ids") or []) if item]
        status = str(chat.get("status") or "ok").lower()
        fallback = bool(interaction.get("fallback")) or status == "fallback"
        if prompt_records and fallback:
            label = "Mostly 11D memory"
            mostly = True
            summary = "Ollama was light/fallback while the core still had retrieved 11D memory context."
        elif len(prompt_records) >= 2:
            label = "11D memory-led with Ollama help"
            mostly = True
            summary = "The answer used multiple retrieved 11D records and then recorded the exchange."
        elif prompt_records:
            label = "Memory-assisted"
            mostly = False
            summary = "The answer used one retrieved 11D record plus Ollama reasoning."
        else:
            label = "Ollama-led"
            mostly = False
            summary = "No retrieved 11D prompt records were visible for the last chat answer."
        return {
            "label": label,
            "summary": summary,
            "prompt_record_count": len(prompt_records),
            "mostly_own_memory": mostly,
            "fallback": fallback,
        }

    async def control_async(self, command: str, topic: str | None = None) -> dict[str, Any]:
        normalized = (command or "").strip().lower().replace("-", "_")
        if normalized in {"start", "start_awake", "start_awake_mode"}:
            message = self.keeper.start()
        elif normalized in {"stop", "stop_awake", "stop_awake_mode"}:
            message = self.keeper.stop()
        elif normalized in {"manual_paeu_step", "manual_step", "paeu_step"}:
            active_topic = topic or self.keeper.status().current_topic or "manual PAEU step"
            events = await self.keeper.run_once(topic=active_topic)
            message = f"Manual PAEU step completed with {len(events)} event(s)."
        elif normalized in {"creative_spike", "force_high_hz", "spike"}:
            message = self.keeper.force_creative_spike()
        elif normalized in {"clear_queue", "clear"}:
            message = self.keeper.clear_queue()
        else:
            raise ValueError(f"Unsupported control command: {command}")
        self.keeper.self_model.reflect(
            event_type="control",
            summary=f"Control command '{normalized}' completed: {message}",
            topic=topic or self.keeper.status().current_topic,
            importance=0.45,
            metadata={"command": normalized},
        )
        return {
            "ok": True,
            "accepted": True,
            "safe_mode": True,
            "command": normalized,
            "action": normalized,
            "message": message,
            "status": self.status_payload(),
        }

    def control_sync(self, command: str, topic: str | None = None) -> dict[str, Any]:
        return run_coroutine_sync(self.control_async(command, topic=topic))

    async def chat_async(self, message: str) -> dict[str, Any]:
        clean_message = " ".join((message or "").split())
        if not clean_message:
            raise ValueError("message is required")
        answer = await self.keeper.answer_question(clean_message)
        status = self.status_payload()
        sources = self._sources_from_feed(status["knowledge_feed"])
        message_id = f"chat_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')}"
        provenance = self._build_chat_provenance(status)
        response = {
            "ok": True,
            "conversation_id": "local-ui-default",
            "message_id": message_id,
            "role": "assistant",
            "message": clean_message,
            "answer": answer,
            "reply": answer,
            "content": answer,
            "sources": sources,
            "provenance": provenance,
            "actions": [
                {
                    "id": "browse_more",
                    "label": "Browse more",
                    "kind": "control",
                    "payload": {"command": "manual_paeu_step"},
                }
            ]
            + self._proposed_actions(clean_message, answer, message_id),
            "suggested_learning_actions": self.keeper.status().suggested_learning_actions
            or self.keeper._suggested_learning_actions(clean_message),
            "hz": status["current_hz"],
            "mood": status["vibration_mood"],
            "safe_mode": status["safe_mode"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "status": status,
        }
        self.chat_log.append(
            {
                "time": datetime.now(timezone.utc).isoformat(),
                "message": clean_message,
                "answer": answer,
                "sources": sources,
            }
        )
        return response

    def chat_sync(self, message: str) -> dict[str, Any]:
        return run_coroutine_sync(self.chat_async(message))

    def memory_payload(self, query: str = "", limit: int = 12) -> dict[str, Any]:
        bounded_limit = max(1, min(int(limit or 12), 50))
        rows: list[dict[str, Any]] = []
        count: int | None = None
        error: str | None = None
        try:
            memory = self.keeper.memory_factory()
            count = memory.count()
            rows = memory.search(query or "", n_results=bounded_limit)
        except Exception as exc:
            error = str(exc)
        return {
            "ok": error is None,
            "safe_mode": True,
            "query": query,
            "count": count,
            "backend": self._memory_info(),
            "rows": rows,
            "records": rows,
            "knowledge_feed": self.keeper.knowledge_feed()[:bounded_limit],
            "error": error,
        }

    def evolution_payload(self, limit: int = 20, event_type: str | None = None) -> dict[str, Any]:
        rows = self.keeper.evolution_store.list_events(limit=limit, event_type=event_type)
        action_summary = self.safe_executor.summary()
        growth = self.keeper.growth_indicators(action_summary=action_summary)
        scorecard = self.keeper.evolution_store.scorecard()
        return {
            "ok": True,
            "safe_mode": True,
            "count": self.keeper.evolution_store.count(),
            "score": scorecard["score"],
            "scorecard": scorecard,
            "autonomy": growth["autonomy"],
            "co_evolution_status": growth["co_evolution_status"],
            "events": rows,
            "proposals": self.keeper.evolution_store.list_proposals(limit=min(limit, 20)),
            "knowledge_links": self.keeper.evolution_store.list_events(
                limit=min(limit, 20),
                event_type="knowledge_link",
            ),
            "summary": self.keeper.evolution_store.summary(limit=5),
        }

    def events_payload(self, limit: int = 20, event_type: str | None = None) -> dict[str, Any]:
        rows = self.keeper.evolution_store.list_events(limit=limit, event_type=event_type)
        return {
            "ok": True,
            "safe_mode": True,
            "latest_event_id": rows[0].get("id") if rows else None,
            "events": rows,
            "scorecard": self.keeper.evolution_store.scorecard(),
        }

    def self_model_payload(self) -> dict[str, Any]:
        return {
            "ok": True,
            "safe_mode": True,
            "self_model": self.keeper.self_model.snapshot(),
            "summary": self.keeper.self_model.status_summary(),
        }

    def reflect_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        reflection = self.keeper.preview_self_reflection_sync(topic=payload.get("topic"))
        action_result = self.safe_executor.propose(
            kind="evolution_proposal",
            label="Evolution Proposal",
            summary=reflection["proposal"],
            payload=reflection.get("proposal_payload") or {"proposal": reflection["proposal"]},
            source={"client": "api", "phase": "proposal_preview"},
            auto_execute=False,
        )
        return {
            **reflection,
            "safe_action": action_result["proposal"],
            "approval_token": action_result["approval_token"],
            "status": self.status_payload(),
        }

    def actions_payload(self, status: str | None = None, limit: int = 20) -> dict[str, Any]:
        return {
            "ok": True,
            "safe_mode": True,
            "actions": self._actions_with_tokens(self.safe_executor.list_actions(status=status, limit=limit)),
            "summary": self.safe_executor.summary(),
        }

    def action_payload(self, action_id: str) -> dict[str, Any]:
        action = self.safe_executor.get_action(action_id)
        if not action:
            raise KeyError(action_id)
        return {"ok": True, "safe_mode": True, "action": action}

    def propose_action(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = self.safe_executor.propose(
            kind=str(payload.get("kind") or ""),
            label=payload.get("label"),
            summary=payload.get("summary"),
            payload=payload.get("payload") or {},
            source=payload.get("source") or {"client": "api"},
        )
        proposal = result["proposal"]
        if proposal.get("status") != "pending" or proposal.get("kind") not in {
            "evolution_proposal",
            "safe_evolution_proposal",
        }:
            self.keeper.record_safe_action(proposal)
        result["safe_mode"] = True
        result["summary"] = self.safe_executor.summary()
        return result

    def approve_action(self, action_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        result = self.safe_executor.approve(
            action_id,
            approval_token=str(payload.get("approval_token") or ""),
            approved_by=str(payload.get("approved_by") or "local_user"),
            note=payload.get("note"),
        )
        if result.get("ok"):
            commit = self.keeper.commit_reflection_proposal_action(result["proposal"])
            if commit:
                result["evolution_commit"] = commit
            self.server_approval_tokens.pop(str(result["proposal"].get("id") or ""), None)
        self.keeper.record_safe_action(result["proposal"])
        result["safe_mode"] = True
        result["summary"] = self.safe_executor.summary()
        return result

    def approve_actions_batch(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = self.safe_executor.approve_many(
            list(payload.get("approvals") or []),
            approved_by=str(payload.get("approved_by") or "local_user"),
            note=payload.get("note"),
        )
        for item in result.get("results") or []:
            proposal = item.get("proposal")
            if proposal:
                if item.get("ok"):
                    commit = self.keeper.commit_reflection_proposal_action(proposal)
                    if commit:
                        item["evolution_commit"] = commit
                    self.server_approval_tokens.pop(str(proposal.get("id") or ""), None)
                self.keeper.record_safe_action(proposal)
        result["safe_mode"] = True
        result["status"] = self.status_payload()
        return result

    def reject_actions_batch(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = self.safe_executor.reject_many(
            [str(item) for item in payload.get("action_ids") or []],
            reason=payload.get("reason") or "Rejected by local user.",
        )
        for item in result.get("results") or []:
            proposal = item.get("proposal")
            if proposal:
                self.server_approval_tokens.pop(str(proposal.get("id") or ""), None)
                self.keeper.record_safe_action(proposal)
        result["safe_mode"] = True
        result["status"] = self.status_payload()
        return result

    def reject_action(self, action_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        result = self.safe_executor.reject(action_id, reason=payload.get("reason"))
        self.server_approval_tokens.pop(str(action_id), None)
        self.keeper.record_safe_action(result["proposal"])
        result["safe_mode"] = True
        result["summary"] = self.safe_executor.summary()
        return result

    def queue_periodic_reflection_proposal(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        reflection_id = str(payload.get("reflection_id") or payload.get("generated_at") or "")
        if reflection_id and reflection_id in self.queued_periodic_reflections:
            return None
        result = self.safe_executor.propose(
            kind="evolution_proposal",
            label="Periodic Reflection Proposal",
            summary=str(payload.get("proposal") or ""),
            payload=payload,
            source={"client": "awake_keeper", "phase": "periodic_self_reflection"},
            auto_execute=False,
        )
        self._remember_approval_token(result)
        proposal = result.get("proposal") or {}
        if reflection_id:
            self.queued_periodic_reflections.add(reflection_id)
        return result

    def _remember_approval_token(self, result: dict[str, Any]) -> None:
        proposal = result.get("proposal") or {}
        token = result.get("approval_token")
        action_id = proposal.get("id")
        if token and action_id:
            self.server_approval_tokens[str(action_id)] = str(token)

    def _actions_with_tokens(self, actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        enriched: list[dict[str, Any]] = []
        for action in actions:
            row = dict(action)
            token = self.server_approval_tokens.get(str(row.get("id") or ""))
            if token and row.get("status") == "pending":
                row["approval_token"] = token
            enriched.append(row)
        return enriched

    def _sources_from_feed(self, feed: list[dict[str, Any]]) -> list[dict[str, Any]]:
        sources = []
        seen: set[str] = set()
        for row in feed:
            source = str(row.get("source") or "")
            record_id = str(row.get("record_id") or "")
            key = source or record_id
            if not key or key in seen:
                continue
            seen.add(key)
            sources.append(
                {
                    "title": row.get("title") or row.get("topic") or source,
                    "url": source,
                    "record_id": record_id,
                    "kind": row.get("kind"),
                    "summary": row.get("summary"),
                }
            )
            if len(sources) >= 4:
                break
        return sources

    def _proposed_actions(self, message: str, answer: str, message_id: str) -> list[dict[str, Any]]:
        proposals: list[dict[str, Any]] = []
        if "```" in answer or "def " in answer or "class " in answer:
            proposals.append(
                {
                    "id": "apply_code_review",
                    "label": "Approve & Review Code",
                    "kind": "apply_code_review",
                    "requires_approval": True,
                    "payload": {
                        "message_id": message_id,
                        "code": answer[:6000],
                        "language": "text",
                    },
                }
            )
        command = self._safe_command_from_message(message)
        if command:
            proposals.append(
                {
                    "id": "safe_command",
                    "label": f"Approve & Execute: {' '.join(command)}",
                    "kind": "safe_command",
                    "requires_approval": True,
                    "payload": {"argv": command},
                }
            )
        improvement = self._self_improvement_payload(message, answer, message_id)
        if improvement:
            proposals.append(improvement)
        return proposals

    def _safe_command_from_message(self, message: str) -> list[str] | None:
        lowered = message.lower()
        if "list files" in lowered or "show files" in lowered or "run ls" in lowered:
            return ["ls", "-la", "/workspace"]
        if "current directory" in lowered or "run pwd" in lowered:
            return ["pwd"]
        if "python version" in lowered:
            return ["python3", "--version"]
        command_text = self._extract_requested_command(message)
        if not command_text:
            return None
        try:
            argv = shlex.split(command_text)
        except ValueError:
            return None
        if not argv:
            return None
        executable = Path(argv[0]).name
        if executable not in SAFE_EXEC_COMMANDS:
            return None
        return argv[:12]

    def _extract_requested_command(self, message: str) -> str | None:
        lowered = message.lower()
        markers = (
            "run command:",
            "run shell:",
            "shell command:",
            "execute command:",
            "execute:",
            "run:",
            "please run ",
            "can you run ",
            "execute ",
        )
        for marker in markers:
            index = lowered.find(marker)
            if index < 0:
                continue
            command_text = message[index + len(marker) :].strip()
            command_text = command_text.strip("`'\" ")
            return command_text.splitlines()[0][:300]
        return None

    def _self_improvement_payload(self, message: str, answer: str, message_id: str) -> dict[str, Any] | None:
        lowered = message.lower()
        markers = (
            "improve yourself",
            "self improve",
            "self-improve",
            "improve your prompt",
            "improve the system",
            "fix yourself",
            "evolve yourself",
            "change yourself",
            "update yourself",
        )
        if not any(marker in lowered for marker in markers):
            return None
        proposal = (
            f"Observation: the user asked for a self-improvement around '{message[:240]}'. "
            f"Current answer preview: {answer[:420]} "
            "Proposal: review the relevant prompt, self-model, knowledge-linking, or helper-function path and make one bounded improvement. "
            "Safety: review-only SafeActionExecutor proposal; no files change until a separate human-approved coding session. "
            "Next test: run the focused pytest suite for the touched path."
        )
        return {
            "id": "evolution_proposal",
            "label": "Approve Evolution Proposal",
            "kind": "evolution_proposal",
            "requires_approval": True,
            "summary": "Review a bounded self-improvement request.",
            "payload": {
                "proposal": proposal,
                "topic": message[:240],
                "message_id": message_id,
                "target_files": [
                    "resonant_ouroboros/prompt_context.py",
                    "resonant_ouroboros/awake_keeper.py",
                    "resonant_ouroboros/dashboard.py",
                    "README.md",
                ],
                "allowed_scope": "prompt wording, self-model wording, knowledge linking, or small helper functions",
                "risk": "medium_review_required",
                "tests_to_run": ["pytest -q tests"],
            },
        }

    def _memory_info(self) -> dict[str, Any]:
        try:
            memory = self.keeper.memory_factory()
            info = getattr(memory, "info", None)
            if callable(info):
                return info()
            return {
                "backend": getattr(memory, "backend_name", type(memory).__name__),
                "records": memory.count(),
            }
        except Exception as exc:
            return {"backend": "unavailable", "error": str(exc)}

    def _memory_count_fallback(self, fallback: int) -> int:
        try:
            return int(self.keeper.memory_factory().count())
        except Exception:
            return fallback


def _dashboard_memory():
    global _DASHBOARD_MEMORY_SINGLETON
    if _DASHBOARD_MEMORY_SINGLETON is not None:
        return _DASHBOARD_MEMORY_SINGLETON
    try:
        _DASHBOARD_MEMORY_SINGLETON = create_memory_from_env(fallback_in_memory=True)
    except Exception:
        _DASHBOARD_MEMORY_SINGLETON = InMemoryHippocampusMemory()
    return _DASHBOARD_MEMORY_SINGLETON


def create_dashboard_runtime(
    oscillator: HertzOscillator | None = None,
    screenshot_path: str | Path = "/workspace/data/screenshots/current_browser_view.png",
    keeper: AwakeKeeper | None = None,
    autostart: bool | None = None,
) -> DashboardRuntime:
    oscillator = oscillator or HertzOscillator()
    config = AwakeKeeperConfig.from_env()
    keeper = keeper or AwakeKeeper(config=config, oscillator=oscillator, memory_factory=_dashboard_memory)
    runtime = DashboardRuntime(
        keeper=keeper,
        oscillator=oscillator,
        screenshot_path=Path(screenshot_path),
    )
    should_autostart = _env_bool("AWAKE_KEEPER_AUTOSTART", False) if autostart is None else autostart
    if should_autostart:
        keeper.start()
    return runtime


def create_api_app(runtime: DashboardRuntime | None = None, demo: Any | None = None):
    try:
        from fastapi import FastAPI, HTTPException, Query
    except ImportError as exc:
        raise RuntimeError("fastapi is required for the Goose-like REST API; use Docker requirements") from exc

    runtime = runtime or create_dashboard_runtime()
    app = FastAPI(
        title="Resonant Ouroboros Awake Keeper API",
        description="Docker-local REST bridge for the Goose-like standalone UI.",
        version="4.0",
    )

    @app.get("/health")
    def health():
        return {"ok": True, "safe_mode": True, "service": "awake_keeper_api"}

    @app.get("/status")
    def status():
        return runtime.status_payload()

    @app.get("/self-model")
    def self_model():
        return runtime.self_model_payload()

    @app.post("/control")
    async def control(payload: dict[str, Any]):
        try:
            command = payload.get("command") or payload.get("action") or ""
            return await runtime.control_async(
                str(command),
                topic=payload.get("topic"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/chat")
    async def chat(payload: dict[str, Any]):
        try:
            return await runtime.chat_async(str(payload.get("message", "")))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/reflect")
    def reflect(payload: dict[str, Any]):
        try:
            return runtime.reflect_payload(payload)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.get("/memory")
    def memory(
        query: str = Query(default=""),
        limit: int = Query(default=12, ge=1, le=50),
    ):
        return runtime.memory_payload(query=query, limit=limit)

    @app.get("/evolution")
    def evolution(
        limit: int = Query(default=20, ge=1, le=100),
        event_type: str | None = Query(default=None),
    ):
        return runtime.evolution_payload(limit=limit, event_type=event_type)

    @app.get("/events")
    def events(
        limit: int = Query(default=20, ge=1, le=100),
        event_type: str | None = Query(default=None),
    ):
        return runtime.events_payload(limit=limit, event_type=event_type)

    @app.get("/actions")
    def actions(
        status: str | None = Query(default=None),
        limit: int = Query(default=20, ge=1, le=100),
    ):
        return runtime.actions_payload(status=status, limit=limit)

    @app.get("/actions/{action_id}")
    def action(action_id: str):
        try:
            return runtime.action_payload(action_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Unknown action: {action_id}") from exc

    @app.post("/actions")
    def propose_action(payload: dict[str, Any]):
        try:
            return runtime.propose_action(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/actions/approve-batch")
    def approve_actions_batch(payload: dict[str, Any]):
        try:
            return runtime.approve_actions_batch(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/actions/reject-batch")
    def reject_actions_batch(payload: dict[str, Any]):
        try:
            return runtime.reject_actions_batch(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/actions/{action_id}/approve")
    def approve_action(action_id: str, payload: dict[str, Any]):
        try:
            return runtime.approve_action(action_id, payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Unknown action: {action_id}") from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/actions/{action_id}/reject")
    def reject_action(action_id: str, payload: dict[str, Any]):
        try:
            return runtime.reject_action(action_id, payload)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Unknown action: {action_id}") from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    if demo is not None:
        try:
            import gradio as gr  # type: ignore
        except ImportError as exc:
            raise RuntimeError("gradio is required to mount the dashboard") from exc
        app = gr.mount_gradio_app(app, demo, path="/", show_api=False)
    return app


def create_dashboard(
    oscillator: HertzOscillator | None = None,
    screenshot_path: str | Path = "/workspace/data/screenshots/current_browser_view.png",
    runtime: DashboardRuntime | None = None,
):
    try:
        import gradio as gr  # type: ignore
    except ImportError as exc:
        raise RuntimeError("gradio is required for the dashboard; use Docker or install requirements.txt") from exc

    runtime = runtime or create_dashboard_runtime(oscillator=oscillator, screenshot_path=screenshot_path)

    def refresh_status():
        return runtime.gradio_outputs()

    def start_awake():
        response = runtime.control_sync("start")
        status, rows, label, image, knowledge, growth, quantum = refresh_status()
        return f"{response['message']}\n\n{status}", rows, label, image, knowledge, growth, quantum

    def stop_awake():
        response = runtime.control_sync("stop")
        status, rows, label, image, knowledge, growth, quantum = refresh_status()
        return f"{response['message']}\n\n{status}", rows, label, image, knowledge, growth, quantum

    def manual_step():
        response = runtime.control_sync("manual_paeu_step")
        status, rows, label, image, knowledge, growth, quantum = refresh_status()
        return f"{response['message']}\n\n{status}", rows, label, image, knowledge, growth, quantum

    def creative_spike():
        response = runtime.control_sync("creative_spike")
        status, rows, label, image, knowledge, growth, quantum = refresh_status()
        return f"{response['message']}\n\n{status}", rows, label, image, knowledge, growth, quantum

    def clear_queue():
        response = runtime.control_sync("clear_queue")
        status, rows, label, image, knowledge, growth, quantum = refresh_status()
        return f"{response['message']}\n\n{status}", rows, label, image, knowledge, growth, quantum

    def chat(message, chat_history):
        response = runtime.chat_sync(message)
        chat_history = chat_history or []
        chat_history.append({"role": "user", "content": message})
        chat_history.append({"role": "assistant", "content": response["answer"]})
        status, rows, label, image, knowledge, growth, quantum = refresh_status()
        return "", chat_history, status, rows, label, image, knowledge, growth, quantum

    with gr.Blocks(title="Resonant Ouroboros Awake Keeper") as demo:
        gr.Markdown("# Resonant Ouroboros Awake Keeper")
        with gr.Row():
            start_button = gr.Button("Start Awake Mode", variant="primary")
            stop_button = gr.Button("Stop Awake Mode")
            step_button = gr.Button("Manual PAEU Step")
            spike_button = gr.Button("Creative Spike")
            clear_button = gr.Button("Clear Queue")
            refresh_button = gr.Button("Refresh")
        hz_label = gr.Textbox(label="Hertz state", interactive=False)
        growth_box = gr.Textbox(label="Ollama <-> Core Collaboration + Autonomy Level", lines=12, interactive=False)
        status_box = gr.Textbox(label="Background loop status", lines=20, interactive=False)
        hz_table = gr.Dataframe(headers=["seconds_ago", "hz"], label="Hz history", interactive=False)
        quantum_table = gr.Dataframe(
            headers=["slot", "amplitude"],
            label="512MB 11D Quantum Memory - Frequency Movement",
            interactive=False,
        )
        knowledge_table = gr.Dataframe(
            headers=["time", "kind", "topic", "title", "source", "record_id", "action", "hz", "mood", "fidelity", "summary"],
            label="Knowledge Incorporation",
            interactive=False,
            wrap=True,
        )
        screenshot = gr.Image(label="Latest browser view", interactive=False)
        chatbot = gr.Chatbot(label="Live Ollama + Browser Chat", type="messages")
        chat_input = gr.Textbox(label="Ask Awake Keeper")
        chat_button = gr.Button("Send")

        live_outputs = [status_box, hz_table, hz_label, screenshot, knowledge_table, growth_box, quantum_table]
        start_button.click(start_awake, outputs=live_outputs)
        stop_button.click(stop_awake, outputs=live_outputs)
        step_button.click(manual_step, outputs=live_outputs)
        spike_button.click(creative_spike, outputs=live_outputs)
        clear_button.click(clear_queue, outputs=live_outputs)
        refresh_button.click(refresh_status, outputs=live_outputs)
        chat_button.click(
            chat,
            inputs=[chat_input, chatbot],
            outputs=[chat_input, chatbot, status_box, hz_table, hz_label, screenshot, knowledge_table, growth_box, quantum_table],
        )
        chat_input.submit(
            chat,
            inputs=[chat_input, chatbot],
            outputs=[chat_input, chatbot, status_box, hz_table, hz_label, screenshot, knowledge_table, growth_box, quantum_table],
        )
        demo.load(refresh_status, outputs=live_outputs)
        refresh_timer = gr.Timer(value=1 / 3)
        refresh_timer.tick(refresh_status, outputs=live_outputs)
    return demo


def launch_dashboard() -> None:
    runtime = create_dashboard_runtime()
    demo = create_dashboard(runtime=runtime)
    app = create_api_app(runtime=runtime, demo=demo)
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError("uvicorn is required for the combined Gradio/API server") from exc
    uvicorn.run(
        app,
        host=os.getenv("GRADIO_SERVER_NAME", "0.0.0.0"),
        port=int(os.getenv("GRADIO_SERVER_PORT", "7860")),
    )
