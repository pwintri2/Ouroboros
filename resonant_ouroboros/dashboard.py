"""Gradio dashboard and local REST API for the Fase 3 Awake Keeper."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any

from .awake_keeper import AwakeKeeper, AwakeKeeperConfig, run_coroutine_sync
from .memory import HippocampusMemory, InMemoryHippocampusMemory, create_memory_from_env
from .oscillator import HertzOscillator
from .safe_executor import SafeActionExecutor


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

    def _status_with_sample(self) -> tuple[Any, Any]:
        state = self.oscillator.modulation_state()
        self.history.add(state.current_hz)
        status = self.keeper.status()
        return status, state

    def status_payload(self) -> dict[str, Any]:
        status, state = self._status_with_sample()
        current_hz = status.current_hz if status.current_hz is not None else state.current_hz
        mood = status.vibration_mood or state.mood
        knowledge_feed = self.keeper.knowledge_feed()
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
            "actions": self.safe_executor.summary(),
            "sandbox": self.safe_executor.summary(),
            "co_evolution": {
                "score": status.co_evolution_score,
                "events": status.co_evolution_events,
                "last_event": status.last_co_evolution_event,
                "last_summary": status.last_co_evolution_summary,
                "summary": self.keeper.evolution_store.summary(limit=5),
                "suggested_learning_actions": status.suggested_learning_actions,
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
            f"sandbox_exec_enabled: {status['actions']['sandbox_exec_enabled']}",
        ]
        return "\n".join(rows)

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
        )

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
        return {
            "ok": True,
            "safe_mode": True,
            "count": self.keeper.evolution_store.count(),
            "score": self.keeper.evolution_store.score(),
            "events": rows,
            "summary": self.keeper.evolution_store.summary(limit=5),
        }

    def self_model_payload(self) -> dict[str, Any]:
        return {
            "ok": True,
            "safe_mode": True,
            "self_model": self.keeper.self_model.snapshot(),
            "summary": self.keeper.self_model.status_summary(),
        }

    def actions_payload(self, status: str | None = None, limit: int = 20) -> dict[str, Any]:
        return {
            "ok": True,
            "safe_mode": True,
            "actions": self.safe_executor.list_actions(status=status, limit=limit),
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
        self.keeper.record_safe_action(result["proposal"])
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
        self.keeper.record_safe_action(result["proposal"])
        result["safe_mode"] = True
        result["summary"] = self.safe_executor.summary()
        return result

    def reject_action(self, action_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        result = self.safe_executor.reject(action_id, reason=payload.get("reason"))
        self.keeper.record_safe_action(result["proposal"])
        result["safe_mode"] = True
        result["summary"] = self.safe_executor.summary()
        return result

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
        lowered = message.lower()
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
        command = self._safe_command_from_message(lowered)
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
        return proposals

    def _safe_command_from_message(self, lowered: str) -> list[str] | None:
        if "list files" in lowered or "show files" in lowered or "run ls" in lowered:
            return ["ls", "-la", "/workspace"]
        if "current directory" in lowered or "run pwd" in lowered:
            return ["pwd"]
        if "python version" in lowered:
            return ["python3", "--version"]
        return None

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
        status, rows, label, image, knowledge = refresh_status()
        return f"{response['message']}\n\n{status}", rows, label, image, knowledge

    def stop_awake():
        response = runtime.control_sync("stop")
        status, rows, label, image, knowledge = refresh_status()
        return f"{response['message']}\n\n{status}", rows, label, image, knowledge

    def manual_step():
        response = runtime.control_sync("manual_paeu_step")
        status, rows, label, image, knowledge = refresh_status()
        return f"{response['message']}\n\n{status}", rows, label, image, knowledge

    def creative_spike():
        response = runtime.control_sync("creative_spike")
        status, rows, label, image, knowledge = refresh_status()
        return f"{response['message']}\n\n{status}", rows, label, image, knowledge

    def clear_queue():
        response = runtime.control_sync("clear_queue")
        status, rows, label, image, knowledge = refresh_status()
        return f"{response['message']}\n\n{status}", rows, label, image, knowledge

    def chat(message, chat_history):
        response = runtime.chat_sync(message)
        chat_history = chat_history or []
        chat_history.append((message, response["answer"]))
        status, rows, label, image, knowledge = refresh_status()
        return "", chat_history, status, rows, label, image, knowledge

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
        status_box = gr.Textbox(label="Background loop status", lines=12, interactive=False)
        hz_table = gr.Dataframe(headers=["seconds_ago", "hz"], label="Hz history", interactive=False)
        knowledge_table = gr.Dataframe(
            headers=["time", "kind", "topic", "title", "source", "record_id", "action", "hz", "mood", "fidelity", "summary"],
            label="Knowledge Incorporation",
            interactive=False,
            wrap=True,
        )
        screenshot = gr.Image(label="Latest browser view", interactive=False)
        chatbot = gr.Chatbot(label="Live Ollama + Browser Chat")
        chat_input = gr.Textbox(label="Ask Awake Keeper")
        chat_button = gr.Button("Send")

        live_outputs = [status_box, hz_table, hz_label, screenshot, knowledge_table]
        start_button.click(start_awake, outputs=live_outputs)
        stop_button.click(stop_awake, outputs=live_outputs)
        step_button.click(manual_step, outputs=live_outputs)
        spike_button.click(creative_spike, outputs=live_outputs)
        clear_button.click(clear_queue, outputs=live_outputs)
        refresh_button.click(refresh_status, outputs=live_outputs)
        chat_button.click(
            chat,
            inputs=[chat_input, chatbot],
            outputs=[chat_input, chatbot, status_box, hz_table, hz_label, screenshot, knowledge_table],
        )
        chat_input.submit(
            chat,
            inputs=[chat_input, chatbot],
            outputs=[chat_input, chatbot, status_box, hz_table, hz_label, screenshot, knowledge_table],
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
