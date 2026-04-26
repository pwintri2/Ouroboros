"""Awake Keeper supervisor for Resonant Ouroboros Fase 2."""

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
from .seed import SeedKnowledgeLoader, SeedTopic


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
    """Runtime settings for the Fase 2 background supervisor."""

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
    ):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.fallback_models = fallback_models
        self.request_timeout = request_timeout
        self.enabled = enabled
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
        for model in (self.model, *self.available_models(), *self.fallback_models):
            if model and model not in ordered:
                ordered.append(model)
        return ordered

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
                answer = self._chat_langchain(model, system_prompt, user_prompt, temperature)
                self.last_model_used = model
                self.last_error = None
                return answer
            except Exception as exc:
                errors.append(f"{model}: {exc}")
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
        return f"Ollama lokaal niet beschikbaar; veilige fallback reflectie: {compact[:360]}"

    def summarize_page(
        self,
        title: str,
        url: str,
        visible_text: str,
        hz: float | None = None,
        mood: str | None = None,
    ) -> str:
        system = "You summarize browsed pages for a local 11D learning memory. Be concise, factual, and safety-aware."
        user = (
            f"Title: {title}\nURL: {url}\nHz: {hz}\nMood: {mood}\n\n"
            f"Visible browser text:\n{visible_text[:5000]}\n\nReturn a short useful summary."
        )
        return self._chat(system, user, temperature=0.25)

    def empathetic_response(self, message: str, context: str = "") -> str:
        system = "You are a calm local assistant. Respond with grounded empathy and practical next steps. Do not pretend to have feelings."
        user = f"Context:\n{context[:3000]}\n\nHuman message:\n{message}"
        return self._chat(system, user, temperature=0.55)

    def code_help(self, question: str, context: str = "") -> str:
        system = "You are a precise programming helper. Explain assumptions, give runnable code when useful, and stay concise."
        user = f"Context:\n{context[:4000]}\n\nProgramming question:\n{question}"
        return self._chat(system, user, temperature=0.3)

    def emotional_valence(self, text: str) -> float:
        system = "Return only one decimal number from -1.0 to 1.0 for the emotional valence of the text."
        answer = self._chat(system, text[:2500], temperature=0.0)
        match = re.search(r"-?\d+(?:\.\d+)?", answer)
        if match:
            return max(-1.0, min(1.0, float(match.group(0))))
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
        self.rng = rng or random.Random()
        self._status = AwakeKeeperStatus(ollama_model=self.config.model)
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._topic_index = 0
        self._knowledge_events: deque[KnowledgeIncorporationEvent] = deque(maxlen=80)
        self._bootstrapped_topics: set[str] = set()

    def status(self) -> AwakeKeeperStatus:
        with self._lock:
            return AwakeKeeperStatus(**self._status.__dict__)

    def _set_status(self, **updates: Any) -> None:
        with self._lock:
            for key, value in updates.items():
                setattr(self._status, key, value)

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
            self._thread = threading.Thread(target=self._thread_main, name="awake_keeper_loop", daemon=True)
            self._thread.start()
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
            emotional_valence_provider=self.ollama.emotional_valence,
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
            summary = self.ollama.summarize_page(
                last_event.snapshot.title,
                last_event.snapshot.url,
                last_event.snapshot.visible_text,
                hz=last_event.current_hz,
                mood=last_event.vibration_mood,
            )
        self._set_status(
            iterations=self.status().iterations + 1,
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
        return events

    async def answer_question(self, question: str) -> str:
        context = ""
        if self.config.chat_browser_enabled:
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
        if any(marker in lowered for marker in ("code", "python", "bug", "error", "program", "function", "class")):
            return self.ollama.code_help(question, context=context)
        return self.ollama.empathetic_response(question, context=context)

    def answer_question_sync(self, question: str) -> str:
        return run_coroutine_sync(self.answer_question(question))


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
