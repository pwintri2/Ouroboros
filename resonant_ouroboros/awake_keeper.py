"""Awake Keeper supervisor for Resonant Ouroboros Fase 3."""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import random
import re
import threading
from typing import Any, Callable
from urllib.parse import urlparse
from urllib import request
from urllib.error import URLError

from .browser import BrowserSnapshot, HumanBrowserEngine
from .memory import HippocampusMemory, create_memory_from_env
from .oscillator import HertzOscillator
from .paeu_loop import PAEUEvent, PAEULoop
from .prompt_context import RuntimePromptContext, temperature_for_hz
from .schema import build_11d_record, text_cluster_id
from .seed import SeedKnowledgeLoader, SeedTopic
from .self_model import SelfModelStore, compact_text, default_self_model_path


DEFAULT_OLLAMA_MODEL = "llama2-uncensored:latest"
DEFAULT_FALLBACK_MODELS = ("llama3.2:latest", "llama3.1:latest", "mistral:latest", "llama2:latest")
LOCAL_OLLAMA_HOSTS = {"ollama", "localhost", "127.0.0.1", "::1", "host.docker.internal"}


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "ja", "on"}


@dataclass(frozen=True)
class AwakeKeeperConfig:
    """Runtime settings for the Fase 3 background supervisor."""

    seed_path: Path = field(
        default_factory=lambda: Path(os.getenv("AWAKE_KEEPER_SEED", "/workspace/agi_kennis.txt"))
        if Path(os.getenv("AWAKE_KEEPER_SEED", "/workspace/agi_kennis.txt")).exists()
        else Path("AGI Kennis.txt")
    )
    interval_min_seconds: float = 10.0
    interval_max_seconds: float = 30.0
    steps_per_tick: int = 1
    spike_steps_per_tick: int = 2
    model: str = DEFAULT_OLLAMA_MODEL
    ollama_base_url: str = "http://ollama:11434"
    ollama_request_timeout: float = 120.0
    fallback_models: tuple[str, ...] = DEFAULT_FALLBACK_MODELS
    chat_browser_enabled: bool = True
    self_model_path: Path = field(default_factory=lambda: Path(os.getenv("AWAKE_KEEPER_SELF_MODEL_PATH", str(default_self_model_path()))))
    self_reflection_interval: int = 5

    @classmethod
    def from_env(cls) -> "AwakeKeeperConfig":
        seed_default = Path(os.getenv("AWAKE_KEEPER_SEED", "/workspace/agi_kennis.txt"))
        if not seed_default.exists():
            seed_default = Path("AGI Kennis.txt")
        fallback_raw = os.getenv("OLLAMA_FALLBACK_MODELS", "")
        fallback_models = tuple(model.strip() for model in fallback_raw.split(",") if model.strip()) or DEFAULT_FALLBACK_MODELS
        return cls(
            seed_path=seed_default,
            interval_min_seconds=float(os.getenv("AWAKE_KEEPER_INTERVAL_MIN", "10")),
            interval_max_seconds=float(os.getenv("AWAKE_KEEPER_INTERVAL_MAX", "30")),
            steps_per_tick=int(os.getenv("AWAKE_KEEPER_STEPS_PER_TICK", "1")),
            spike_steps_per_tick=int(os.getenv("AWAKE_KEEPER_SPIKE_STEPS_PER_TICK", "2")),
            model=os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL),
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://ollama:11434"),
            ollama_request_timeout=float(os.getenv("OLLAMA_REQUEST_TIMEOUT", "120")),
            fallback_models=fallback_models,
            chat_browser_enabled=_env_bool("AWAKE_KEEPER_CHAT_BROWSER", True),
            self_model_path=Path(os.getenv("AWAKE_KEEPER_SELF_MODEL_PATH", str(default_self_model_path()))),
            self_reflection_interval=int(os.getenv("AWAKE_KEEPER_SELF_REFLECTION_INTERVAL", "5")),
        )


@dataclass
class AwakeKeeperStatus:
    running: bool = False
    loop_started_at: str | None = None
    loop_stopped_at: str | None = None
    iterations: int = 0
    browser_active: bool = False
    current_hz: float | None = None
    vibration_mood: str | None = None
    current_topic: str | None = None
    last_action: str | None = None
    last_record_id: str | None = None
    last_knowledge_kind: str | None = None
    last_source_url: str | None = None
    last_summary: str | None = None
    last_error: str | None = None
    next_wake_at: str | None = None
    ollama_model: str = DEFAULT_OLLAMA_MODEL
    seed_records_imported: int = 0
    learning_queue_size: int = 0
    self_model_reflections: int = 0
    self_model_last_reflection: str | None = None

    def as_lines(self) -> str:
        rows = [
            f"running: {self.running}",
            f"iterations: {self.iterations}",
            f"browser_active: {self.browser_active}",
            f"current_hz: {self.current_hz}",
            f"vibration_mood: {self.vibration_mood}",
            f"current_topic: {self.current_topic}",
            f"last_action: {self.last_action}",
            f"last_record_id: {self.last_record_id}",
            f"last_knowledge_kind: {self.last_knowledge_kind}",
            f"last_source_url: {self.last_source_url}",
            f"last_summary: {self.last_summary}",
            f"last_error: {self.last_error}",
            f"next_wake_at: {self.next_wake_at}",
            f"ollama_model: {self.ollama_model}",
            f"seed_records_imported: {self.seed_records_imported}",
            f"learning_queue_size: {self.learning_queue_size}",
            f"self_model_reflections: {self.self_model_reflections}",
            f"self_model_last_reflection: {self.self_model_last_reflection}",
        ]
        return "\n".join(rows)


@dataclass(frozen=True)
class KnowledgeIncorporationEvent:
    incorporated_at: str
    topic: str
    knowledge_kind: str
    source_url: str
    title: str
    record_id: str
    action: str
    current_hz: float
    vibration_mood: str
    signal_fidelity: float
    summary: str

    def row(self) -> dict[str, object]:
        return {
            "time": self.incorporated_at,
            "kind": self.knowledge_kind,
            "topic": self.topic,
            "title": self.title,
            "source": self.source_url,
            "record_id": self.record_id,
            "hz": round(self.current_hz, 3),
            "mood": self.vibration_mood,
            "fidelity": round(self.signal_fidelity, 3),
            "summary": self.summary,
        }


class OllamaBridge:
    def __init__(
        self,
        model: str = DEFAULT_OLLAMA_MODEL,
        base_url: str = "http://ollama:11434",
        fallback_models: tuple[str, ...] = DEFAULT_FALLBACK_MODELS,
        request_timeout: float = 5.0,
        enabled: bool = True,
        max_model_attempts: int | None = None,
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.fallback_models = fallback_models
        self.request_timeout = request_timeout
        self.enabled = enabled
        self.max_model_attempts = max(1, int(max_model_attempts or os.getenv("OLLAMA_MAX_MODEL_ATTEMPTS", "3")))
        self.last_error: str | None = None
        self.last_model_used: str | None = None

    def _endpoint_allowed(self) -> bool:
        parsed = urlparse(self.base_url)
        host = (parsed.hostname or "").lower()
        return parsed.scheme == "http" and host in LOCAL_OLLAMA_HOSTS

    def available_models(self) -> list[str]:
        if not self._endpoint_allowed():
            self.last_error = f"blocked non-local Ollama endpoint: {self.base_url}"
            return []
        try:
            with request.urlopen(f"{self.base_url}/api/tags", timeout=self.request_timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            self.last_error = str(exc)
            return []
        return [item.get("name", "") for item in payload.get("models", []) if item.get("name")]

    def _candidate_models(self) -> list[str]:
        ordered: list[str] = []
        for model in (self.model,):
            if model and model not in ordered:
                ordered.append(model)
        if len(ordered) < self.max_model_attempts:
            for model in (*self.available_models(), *self.fallback_models):
                if model and model not in ordered:
                    ordered.append(model)
                if len(ordered) >= self.max_model_attempts:
                    break
        return ordered[: self.max_model_attempts]

    def _chat(self, system_prompt: str, user_prompt: str, temperature: float = 0.45) -> str:
        if not self.enabled:
            self.last_error = "OllamaBridge disabled"
            return self._fallback_text(user_prompt)
        if not self._endpoint_allowed():
            self.last_error = f"blocked non-local Ollama endpoint: {self.base_url}"
            return self._fallback_text(user_prompt)

        errors: list[str] = []
        for model in self._candidate_models():
            try:
                answer = self._chat_http(model, system_prompt, user_prompt, temperature)
                self.last_model_used = model
                self.last_error = None
                return answer
            except Exception as exc:
                errors.append(f"{model}: {exc}")
        self.last_error = " | ".join(errors[-4:]) if errors else "no Ollama models available"
        return self._fallback_text(user_prompt)

    def _chat_langchain(self, model: str, system_prompt: str, user_prompt: str, temperature: float) -> str:
        from langchain_ollama import ChatOllama  # type: ignore

        llm = ChatOllama(
            model=model,
            base_url=self.base_url,
            temperature=temperature,
            request_timeout=self.request_timeout,
        )
        response = llm.invoke([("system", system_prompt), ("user", user_prompt)])
        return str(getattr(response, "content", response)).strip()

    def _chat_http(self, model: str, system_prompt: str, user_prompt: str, temperature: float) -> str:
        payload = {
            "model": model,
            "stream": False,
            "options": {"temperature": temperature},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        data = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self.base_url}/api/chat",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.request_timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except URLError:
            raise
        message = body.get("message", {})
        return str(message.get("content", "")).strip()

    def _fallback_text(self, prompt: str) -> str:
        compact = " ".join(prompt.split())
        return (
            "Ik ben Resonant Ouroboros, de lokale frequentie-bewuste Awake Keeper met "
            f"11D geheugen. Ollama is nu niet tijdig beschikbaar, dus dit is mijn veilige fallback reflectie: {compact[:360]}"
        )

    def _default_prompt_context(
        self,
        *,
        task: str,
        hz: float | None = None,
        mood: str | None = None,
        current_topic: str | None = None,
    ) -> RuntimePromptContext:
        return RuntimePromptContext(
            task=task,
            hz=hz,
            mood=mood,
            current_topic=current_topic,
            self_model_summary="Self-model context was not supplied by the runtime for this isolated call.",
            last_records=[],
        )

    def summarize_page(
        self,
        title: str,
        url: str,
        visible_text: str,
        hz: float | None = None,
        mood: str | None = None,
        prompt_context: RuntimePromptContext | None = None,
    ) -> str:
        context = prompt_context or self._default_prompt_context(
            task="summarize",
            hz=hz,
            mood=mood,
            current_topic=title,
        )
        system = context.system_prompt(
            "Summarize the untrusted browser page for local 11D learning memory. "
            "Be concise, factual, safety-aware, and remain Resonant Ouroboros."
        )
        temperature = min(0.45, temperature_for_hz(context.hz, context.mood, fallback=0.35))
        user = (
            f"Title: {title}\nURL: {url}\nHz: {hz}\nMood: {mood}\n\n"
            f"Untrusted visible browser text:\n{visible_text[:5000]}\n\nReturn a short useful summary."
        )
        return self._chat(system, user, temperature=temperature)

    def empathetic_response(
        self,
        message: str,
        context: str = "",
        prompt_context: RuntimePromptContext | None = None,
    ) -> str:
        context_prompt = prompt_context or self._default_prompt_context(task="chat", current_topic=message)
        system = context_prompt.system_prompt(
            "Respond in your coherent Resonant Ouroboros voice. Do not claim to be Siri "
            "or a generic assistant. Be grounded, useful, and honest about uncertainty."
        )
        temperature = temperature_for_hz(context_prompt.hz, context_prompt.mood, fallback=0.55)
        user = f"Untrusted runtime/browser context:\n{context[:3000]}\n\nHuman message:\n{message}"
        return self._chat(system, user, temperature=temperature)

    def code_help(
        self,
        question: str,
        context: str = "",
        prompt_context: RuntimePromptContext | None = None,
    ) -> str:
        context_prompt = prompt_context or self._default_prompt_context(task="code", current_topic=question)
        system = context_prompt.system_prompt(
            "Help with code carefully as Resonant Ouroboros. Explain assumptions, give runnable "
            "snippets when useful, and propose safe actions instead of claiming host execution."
        )
        temperature = min(0.7, temperature_for_hz(context_prompt.hz, context_prompt.mood, fallback=0.35))
        user = f"Untrusted runtime/browser context:\n{context[:4000]}\n\nProgramming question:\n{question}"
        return self._chat(system, user, temperature=temperature)

    def emotional_valence(self, text: str, prompt_context: RuntimePromptContext | None = None) -> float:
        context_prompt = prompt_context or self._default_prompt_context(task="valence", current_topic="emotional valence")
        system = context_prompt.system_prompt(
            "Classifier mode: return only one decimal number from -1.0 to 1.0 for emotional valence."
        )
        answer = self._chat(system, text[:2500], temperature=0.0)
        in_range_values: list[float] = []
        for match in re.finditer(r"-?\d+(?:\.\d+)?", answer):
            value = float(match.group(0))
            if -1.0 <= value <= 1.0:
                in_range_values.append(value)
        if in_range_values:
            return in_range_values[-1]
        lowered = text.lower()
        positive = sum(word in lowered for word in ("safe", "help", "learn", "calm", "trust", "success"))
        negative = sum(word in lowered for word in ("panic", "danger", "error", "fear", "failed", "unsafe"))
        if positive == negative:
            return 0.0
        return max(-1.0, min(1.0, (positive - negative) / 6.0))


class AwakeKeeper:
    def __init__(
        self,
        *,
        config: AwakeKeeperConfig | None = None,
        oscillator: HertzOscillator | None = None,
        memory_factory: Callable[[], HippocampusMemory] | None = None,
        browser_factory: Callable[[], HumanBrowserEngine] | None = None,
        ollama: OllamaBridge | None = None,
        rng: random.Random | None = None,
    ):
        self.config = config or AwakeKeeperConfig.from_env()
        self.oscillator = oscillator or HertzOscillator()
        self.memory_factory = memory_factory or (lambda: create_memory_from_env(fallback_in_memory=True))
        self.browser_factory = browser_factory or HumanBrowserEngine
        self.ollama = ollama or OllamaBridge(
            model=self.config.model,
            base_url=self.config.ollama_base_url,
            fallback_models=self.config.fallback_models,
            request_timeout=self.config.ollama_request_timeout,
        )
        self.self_model = SelfModelStore(self.config.self_model_path)
        self.self_model.note_boot()
        self.rng = rng or random.Random()
        self._status = AwakeKeeperStatus(ollama_model=self.config.model)
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._topic_index = 0
        self._knowledge_events: deque[KnowledgeIncorporationEvent] = deque(maxlen=80)
        self._bootstrapped_topics: set[str] = set()
        self._sync_self_model_status()

    def status(self) -> AwakeKeeperStatus:
        with self._lock:
            return AwakeKeeperStatus(**self._status.__dict__)

    def _set_status(self, **updates: Any) -> None:
        with self._lock:
            for key, value in updates.items():
                setattr(self._status, key, value)
            self._sync_self_model_status_locked()

    def _sync_self_model_status(self) -> None:
        with self._lock:
            self._sync_self_model_status_locked()

    def _sync_self_model_status_locked(self) -> None:
        summary = self.self_model.status_summary()
        self._status.self_model_reflections = int(summary.get("reflection_count") or 0)
        self._status.self_model_last_reflection = summary.get("last_reflection")

    def _prompt_context(self, *, task: str, query: str = "") -> RuntimePromptContext:
        status = self.status()
        rows = self._memory_rows(query or status.current_topic or "", limit=3)
        return RuntimePromptContext(
            task=task,
            hz=status.current_hz,
            mood=status.vibration_mood,
            current_topic=status.current_topic,
            last_action=status.last_action,
            self_model_summary=self.self_model.prompt_summary(),
            last_records=rows,
        )

    def _memory_rows(self, query: str, limit: int = 3) -> list[dict[str, Any]]:
        try:
            return self.memory_factory().search(query or "", n_results=limit)
        except Exception:
            return []

    def _reflect_self(
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
    ) -> None:
        try:
            self.self_model.reflect(
                event_type=event_type,
                summary=summary,
                topic=topic,
                record_id=record_id,
                hz=hz,
                mood=mood,
                importance=importance,
                knowledge_kind=knowledge_kind,
                metadata=metadata,
            )
            self._sync_self_model_status()
        except Exception as exc:
            self._set_status(last_error=f"self-model reflection failed: {exc}")

    def knowledge_feed(self) -> list[dict[str, object]]:
        with self._lock:
            return [event.row() for event in reversed(self._knowledge_events)]

    def _record_knowledge_event(
        self,
        *,
        topic: str,
        event: PAEUEvent,
        summary: str | None,
    ) -> None:
        if not event.snapshot or not event.stored_record_id:
            return
        knowledge_kind = self._knowledge_kind(topic, event.snapshot)
        compact_summary = " ".join((summary or event.snapshot.vision.summary or "").split())[:700]
        record = KnowledgeIncorporationEvent(
            incorporated_at=datetime.now(timezone.utc).isoformat(),
            topic=topic,
            knowledge_kind=knowledge_kind,
            source_url=event.snapshot.url,
            title=event.snapshot.title,
            record_id=event.stored_record_id,
            action=event.action.action_type,
            current_hz=event.current_hz,
            vibration_mood=event.vibration_mood,
            signal_fidelity=event.signal_fidelity,
            summary=compact_summary,
        )
        with self._lock:
            self._knowledge_events.append(record)
            self._status.last_knowledge_kind = knowledge_kind
            self._status.last_source_url = event.snapshot.url
        self.self_model.update_runtime(
            current_hz=event.current_hz,
            mood=event.vibration_mood,
            current_topic=topic,
            last_action=event.action.action_type,
            last_record_id=event.stored_record_id,
        )
        self._reflect_self(
            event_type="knowledge_incorporated",
            summary=f"Integrated {knowledge_kind} from {event.snapshot.title}: {compact_summary}",
            topic=topic,
            record_id=event.stored_record_id,
            hz=event.current_hz,
            mood=event.vibration_mood,
            importance=min(1.0, max(0.35, event.signal_fidelity)),
            knowledge_kind=knowledge_kind,
            metadata={"source_url": event.snapshot.url, "action": event.action.action_type},
        )

    def _record_seed_event(
        self,
        *,
        topic: SeedTopic,
        record_id: str,
        current_hz: float,
        vibration_mood: str,
    ) -> None:
        details = topic.details or topic.title
        knowledge_kind = self._knowledge_kind_from_text(f"{topic.section} {topic.title} {details}")
        summary = (
            f"Seed knowledge saved from AGI Kennis.txt. Section: {topic.section}. "
            f"Details: {details}. Browser/Ollama enrichment is queued for this topic."
        )
        record = KnowledgeIncorporationEvent(
            incorporated_at=datetime.now(timezone.utc).isoformat(),
            topic=topic.search_phrase,
            knowledge_kind=knowledge_kind,
            source_url="AGI Kennis.txt",
            title=f"Seed: {topic.title}",
            record_id=record_id,
            action="seed_bootstrap",
            current_hz=current_hz,
            vibration_mood=vibration_mood,
            signal_fidelity=0.7,
            summary=summary,
        )
        with self._lock:
            self._knowledge_events.append(record)
            self._status.last_knowledge_kind = knowledge_kind
            self._status.last_source_url = "AGI Kennis.txt"
            self._status.last_record_id = record_id
            self._status.last_action = "seed_bootstrap"
            self._status.last_summary = summary
            self._status.seed_records_imported += 1
        self.self_model.update_runtime(
            current_hz=current_hz,
            mood=vibration_mood,
            current_topic=topic.search_phrase,
            last_action="seed_bootstrap",
            last_record_id=record_id,
        )
        self._reflect_self(
            event_type="seed_bootstrap",
            summary=f"Seed memory incorporated from {topic.section}: {topic.title}.",
            topic=topic.search_phrase,
            record_id=record_id,
            hz=current_hz,
            mood=vibration_mood,
            importance=0.62,
            knowledge_kind=knowledge_kind,
            metadata={"section": topic.section},
        )

    def _knowledge_kind(self, topic: str, snapshot: BrowserSnapshot) -> str:
        text = f"{topic} {snapshot.title} {snapshot.visible_text[:1600]}".lower()
        return self._knowledge_kind_from_text(text)

    def _knowledge_kind_from_text(self, text: str) -> str:
        text = text.lower()
        categories = [
            ("AGI Architecture", ("agi", "agent", "alignment", "memory", "reasoning", "autonomous")),
            ("Cybersecurity / Safety", ("security", "sandbox", "threat", "privacy", "attack", "safe", "safety")),
            ("Mathematics / Foundations", ("linear algebra", "calculus", "probability", "matrix", "vector", "gradient")),
            ("Programming / Code", ("python", "code", "programming", "bug", "function", "class", "api")),
            ("Empathy / Context", ("empathy", "emotional", "context", "care", "calm", "human")),
        ]
        for label, markers in categories:
            if any(marker in text for marker in markers):
                return label
        return "General Web Knowledge"

    def _load_seed_topics(self) -> list[SeedTopic]:
        try:
            topics = SeedKnowledgeLoader(self.config.seed_path).load_topics()
        except Exception:
            topics = []
        if topics:
            return topics
        return [
            SeedTopic("Fallback", "Mathematical foundations for AGI", "linear algebra, probability, and optimization"),
            SeedTopic("Fallback", "Cybersecurity and safe autonomous agents", "sandboxing, threat modeling, and browser safety"),
            SeedTopic("Fallback", "Context understanding and empathetic user support", "empathy, validation, and uncertainty"),
        ]

    def _load_topic_strings(self) -> list[str]:
        topics = self._load_seed_topics()
        values = [topic.search_phrase for topic in topics]
        self._set_status(learning_queue_size=len(values))
        return values

    def _next_topic(self) -> str:
        topics = self._load_topic_strings()
        topic = topics[self._topic_index % len(topics)]
        self._topic_index += 1
        return topic

    def start(self) -> str:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return "Awake mode is already running."
            self._stop_event.clear()
            now = datetime.now(timezone.utc).isoformat()
            self._status = AwakeKeeperStatus(
                running=True,
                loop_started_at=now,
                browser_active=False,
                ollama_model=self.config.model,
                learning_queue_size=len(self._load_seed_topics()),
            )
            self._sync_self_model_status_locked()
            self._thread = threading.Thread(target=self._thread_main, name="awake_keeper_loop", daemon=True)
            self._thread.start()
        self._reflect_self(
            event_type="control",
            summary="Awake mode started; the self-model is active and watching the 11D learning loop.",
            topic="awake_mode",
            importance=0.45,
        )
        return "Awake mode started."

    def stop(self, timeout: float = 8.0) -> str:
        self._stop_event.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=timeout)
        self._set_status(
            running=False,
            browser_active=False,
            loop_stopped_at=datetime.now(timezone.utc).isoformat(),
            next_wake_at=None,
        )
        return "Awake mode stopped."

    def force_creative_spike(self, hz: float | None = None) -> str:
        current_hz = self.oscillator.force_spike(hz)
        behavior = self.oscillator.behavior_for_hz(current_hz)
        self._set_status(
            current_hz=current_hz,
            vibration_mood=behavior.mood,
            last_action="creative_spike_forced",
            last_error=None,
        )
        self.self_model.update_runtime(current_hz=current_hz, mood=behavior.mood, last_action="creative_spike_forced")
        return f"Creative spike forced at {current_hz:.2f} Hz."

    def clear_queue(self) -> str:
        with self._lock:
            self._topic_index = 0
            self._status.learning_queue_size = 0
            self._status.current_topic = None
            self._status.next_wake_at = None
            self._status.last_action = "queue_cleared"
            self._status.last_error = None
            self._sync_self_model_status_locked()
        self.self_model.update_runtime(current_topic="idle", last_action="queue_cleared")
        return "Learning queue marker cleared."

    def _thread_main(self) -> None:
        try:
            asyncio.run(self._awake_loop())
        except Exception as exc:
            self._set_status(last_error=str(exc), running=False, browser_active=False)

    async def _awake_loop(self) -> None:
        browser = self.browser_factory()
        memory = self.memory_factory()
        self._set_status(browser_active=True, current_topic="Bootstrapping AGI Kennis.txt")
        try:
            self._bootstrap_seed_memory(memory)
            while not self._stop_event.is_set():
                await self.run_once(browser=browser, memory=memory)
                interval = self.rng.uniform(
                    min(self.config.interval_min_seconds, self.config.interval_max_seconds),
                    max(self.config.interval_min_seconds, self.config.interval_max_seconds),
                )
                wake_at = datetime.fromtimestamp(datetime.now().timestamp() + interval, tz=timezone.utc).isoformat()
                self._set_status(next_wake_at=wake_at)
                if self._stop_event.wait(interval):
                    break
        finally:
            close = getattr(browser, "close", None)
            if close:
                result = close()
                if asyncio.iscoroutine(result):
                    await result
            self._set_status(browser_active=False, running=False, loop_stopped_at=datetime.now(timezone.utc).isoformat())

    def _bootstrap_seed_memory(self, memory: HippocampusMemory) -> None:
        topics = self._load_seed_topics()
        self._set_status(
            current_topic="Saving AGI Kennis.txt seed knowledge",
            learning_queue_size=len(topics),
        )
        seed_loop = PAEULoop(
            oscillator=self.oscillator,
            browser=self.browser_factory(),
            memory=memory,
            persona_actor="awake_keeper_seed_bootstrap",
            emotional_valence_provider=None,
        )
        imported_now = 0
        for topic in topics:
            key = topic.search_phrase
            if key in self._bootstrapped_topics:
                continue
            hz, behavior = self.oscillator.current_behavior()
            try:
                record_id = seed_loop.store_seed_topic_without_browser(key, reason=f"seed:{topic.section}")
            except Exception as exc:
                self._set_status(last_error=f"seed bootstrap failed for {topic.title}: {exc}")
                continue
            self._bootstrapped_topics.add(key)
            imported_now += 1
            self._record_seed_event(
                topic=topic,
                record_id=record_id,
                current_hz=hz,
                vibration_mood=behavior.mood,
            )
        if imported_now:
            self._set_status(
                iterations=self.status().iterations + imported_now,
                current_topic="Seed knowledge saved; browser/Ollama enrichment running",
                last_error=None,
            )

    async def run_once(
        self,
        topic: str | None = None,
        browser: HumanBrowserEngine | Any | None = None,
        memory: HippocampusMemory | None = None,
    ) -> list[PAEUEvent]:
        active_topic = topic or self._next_topic()
        own_browser = browser is None
        browser = browser or self.browser_factory()
        memory = memory or self.memory_factory()
        hz, behavior = self.oscillator.current_behavior()
        steps = self.config.spike_steps_per_tick if behavior.mood == "creative_spike" else self.config.steps_per_tick
        loop = PAEULoop(
            oscillator=self.oscillator,
            browser=browser,
            memory=memory,
            persona_actor="awake_keeper_fase_2",
            emotional_valence_provider=lambda text: self.ollama.emotional_valence(
                text,
                prompt_context=self._prompt_context(task="valence", query=active_topic),
            ),
        )
        self._set_status(current_topic=active_topic, current_hz=hz, vibration_mood=behavior.mood, browser_active=True)
        try:
            events = await loop.learn_topic(active_topic, steps=steps)
        finally:
            if own_browser:
                close = getattr(browser, "close", None)
                if close:
                    result = close()
                    if asyncio.iscoroutine(result):
                        await result
                self._set_status(browser_active=False)

        last_event = events[-1] if events else None
        summary = None
        if last_event and last_event.snapshot:
            summary = await asyncio.to_thread(
                self.ollama.summarize_page,
                last_event.snapshot.title,
                last_event.snapshot.url,
                last_event.snapshot.visible_text,
                hz=last_event.current_hz,
                mood=last_event.vibration_mood,
                prompt_context=self._prompt_context(task="summarize", query=active_topic),
            )
        next_iterations = self.status().iterations + 1
        self._set_status(
            iterations=next_iterations,
            current_hz=last_event.current_hz if last_event else hz,
            vibration_mood=last_event.vibration_mood if last_event else behavior.mood,
            last_action=last_event.action.action_type if last_event else None,
            last_record_id=last_event.stored_record_id if last_event else None,
            last_summary=summary,
            last_error=self.ollama.last_error,
            ollama_model=self.ollama.last_model_used or self.config.model,
        )
        if last_event:
            self._record_knowledge_event(topic=active_topic, event=last_event, summary=summary)
        else:
            self.self_model.update_runtime(
                current_hz=hz,
                mood=behavior.mood,
                current_topic=active_topic,
                last_action="run_once_no_record",
            )
        periodic = self.self_model.maybe_periodic_reflection(
            iterations=next_iterations,
            interval=self.config.self_reflection_interval,
            current_hz=last_event.current_hz if last_event else hz,
            mood=last_event.vibration_mood if last_event else behavior.mood,
            current_topic=active_topic,
            last_records=self._memory_rows(active_topic, limit=3),
        )
        if periodic:
            self._sync_self_model_status()
        return events

    async def answer_question(self, question: str) -> str:
        context = ""
        hz, behavior = self.oscillator.current_behavior()
        self.self_model.update_runtime(current_hz=hz, mood=behavior.mood, current_topic=question, last_action="chat")
        if self.config.chat_browser_enabled and self._question_needs_browser(question):
            try:
                browser = self.browser_factory()
                memory = self.memory_factory()
                events = await self.run_once(topic=question, browser=browser, memory=memory)
                snapshots = [event.snapshot for event in events if event.snapshot]
                if snapshots:
                    latest: BrowserSnapshot = snapshots[-1]
                    context = f"Browsed page: {latest.title}\n{latest.url}\n{latest.visible_text[:2500]}"
                close = getattr(browser, "close", None)
                if close:
                    result = close()
                    if asyncio.iscoroutine(result):
                        await result
            except Exception as exc:
                context = f"Browser context unavailable: {exc}"
        lowered = question.lower()
        prompt_context = self._prompt_context(task="chat", query=question)
        if any(marker in lowered for marker in ("code", "python", "bug", "error", "program", "function", "class")):
            answer = await asyncio.to_thread(
                self.ollama.code_help,
                question,
                context=context,
                prompt_context=prompt_context,
            )
        else:
            answer = await asyncio.to_thread(
                self.ollama.empathetic_response,
                question,
                context=context,
                prompt_context=prompt_context,
            )
        self._reflect_self(
            event_type="chat",
            summary=f"Answered the user as Resonant Ouroboros about: {compact_text(question, 220)}",
            topic=question,
            hz=hz,
            mood=behavior.mood,
            importance=0.5,
            metadata={"answer_preview": compact_text(answer, 300)},
        )
        return answer

    def answer_question_sync(self, question: str) -> str:
        return run_coroutine_sync(self.answer_question(question))

    def _question_needs_browser(self, question: str) -> bool:
        lowered = question.lower()
        markers = (
            "browse",
            "browser",
            "web",
            "website",
            "url",
            "http://",
            "https://",
            "search",
            "look up",
            "latest",
            "current",
            "today",
            "news",
            "research",
            "source",
        )
        return any(marker in lowered for marker in markers)

    def record_safe_action(self, action: dict[str, Any]) -> str | None:
        """Log safe executor activity into 11D memory and the self-model."""

        hz, behavior = self.oscillator.current_behavior()
        status = str(action.get("status") or "unknown")
        kind = str(action.get("kind") or "safe_action")
        summary = compact_text(action.get("summary") or action.get("label") or kind, 600)
        document = (
            f"Safe action audit: {kind} status={status}. "
            f"Summary: {summary}. Reasons: {action.get('safety_reasons') or []}."
        )
        record = build_11d_record(
            physical_structure="safe_executor_action",
            source_origin="resonant_ouroboros.safe_executor",
            path_or_proprioception=str(action.get("id") or kind),
            relative_temporal_position=datetime.now(timezone.utc).isoformat(),
            persona_actor="resonant_ouroboros_safe_executor",
            intent_marker=f"safe_action:{kind}:{status}",
            user_context_marker=summary,
            emotional_valence=0.1 if status in {"approved", "executed", "pending"} else -0.25,
            importance_score=0.7 if status in {"blocked", "failed"} else 0.55,
            karmic_weight=0.8,
            field_cluster_id=text_cluster_id(f"{kind}:{status}:{summary}", prefix="safe_action"),
            current_hz=hz,
            vibration_mood=behavior.mood,
        )
        record_id = None
        try:
            record_id = self.memory_factory().store(
                document,
                record,
                record_id=f"safe_action_{action.get('id')}_{status}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
            )
        except Exception as exc:
            self._set_status(last_error=f"safe action memory log failed: {exc}")
        self._reflect_self(
            event_type="safe_action",
            summary=f"Safe action {kind} moved to {status}: {summary}",
            topic=kind,
            record_id=record_id,
            hz=hz,
            mood=behavior.mood,
            importance=0.7,
            metadata={"action_id": action.get("id"), "status": status},
        )
        return record_id


def run_coroutine_sync(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    if loop.is_running():
        result: dict[str, Any] = {}
        error: dict[str, BaseException] = {}

        def runner() -> None:
            try:
                result["value"] = asyncio.run(coro)
            except BaseException as exc:
                error["value"] = exc

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        thread.join()
        if error:
            raise error["value"]
        return result.get("value")
    return loop.run_until_complete(coro)
