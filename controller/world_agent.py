"""World Agent: approved browser actions plus local vector understanding.

The module is intentionally narrow: it can open/ask Grok, store scrubbed
observations in a ChromaDB collection, and search that collection later. When
the backend runs in Docker it can delegate the laptop browser action to the
authenticated host bridge instead of pretending that a container opened a tab.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
import urllib.error
import urllib.request
import uuid
import webbrowser
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

from controller.browser_research import BrowserActionResult
from controller.scrubber import scrub_data
from controller.stream.browser_scrubber import DEFAULT_APPROVAL_PHRASE, prepare_browser_ingest


GROK_URL = "https://grok.com/"
WORLD_COLLECTION_NAME = "wintrip_world_understanding"
WORLD_ACTION_LOG_NAME = "world_agent_actions.jsonl"
MAX_WORLD_QUESTION_CHARS = 4000
MAX_WORLD_ANSWER_CHARS = 64_000
DEFAULT_WORLD_TIMEOUT_MS = 25_000
DEFAULT_GROK_WAIT_MS = 12_000

_LOGIN_OR_CAPTCHA_RE = re.compile(
    r"(?i)\b("
    r"captcha|verify you are human|verify you're human|cloudflare|"
    r"log in|login|sign in|signin|create account|password|two-factor|2fa"
    r")\b"
)
_GROK_RATE_LIMIT_RE = re.compile(
    r"(?i)\b("
    r"veel vraag|probeer het straks opnieuw|try (?:again|it) later|"
    r"higher priority access|hogere prioriteitstoegang|rate limit|too many requests"
    r")\b"
)
_TOKEN_RE = re.compile(r"(?u)\b[\wÀ-ÿ][\wÀ-ÿ'-]{2,}\b")


@dataclass(frozen=True)
class WorldIntent:
    action: str
    query: str
    target: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"action": self.action, "query": self.query, "target": self.target}


class HashEmbeddingFunction:
    """Small deterministic embedding fallback for ChromaDB.

    It is not a replacement for a large embedding model, but it keeps world
    memory searchable without requiring Ollama's embedding model to be present.
    Set WINTRIP_WORLD_AGENT_EMBEDDINGS=ollama to use the Ollama embedding path.
    """

    def __init__(self, dimensions: int = 384):
        self.dimensions = dimensions

    def name(self) -> str:
        return f"wintrip_hash_embedding_{self.dimensions}"

    def __call__(self, input: Sequence[str]) -> list[list[float]]:  # noqa: A002 - Chroma expects this name.
        return [self._embed(str(text or "")) for text in input]

    def embed_documents(self, documents: Sequence[str] | None = None, input: Sequence[str] | None = None) -> list[list[float]]:  # noqa: A002
        return self(documents if documents is not None else (input or []))

    def embed_query(self, query: str | Sequence[str] | None = None, input: str | Sequence[str] | None = None) -> list[list[float]]:  # noqa: A002
        value = query if query is not None else input
        if isinstance(value, (list, tuple)):
            return self([str(item or "") for item in value])
        return self([str(value or "")])

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in _tokens(text):
            digest = hashlib.blake2b(token.encode("utf-8", errors="ignore"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            weight = 1.0 + min(len(token), 12) / 24.0
            vector[index] += sign * weight
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


class WorldMemory:
    def __init__(
        self,
        persist_dir: str | Path | None = None,
        collection_name: str | None = None,
        collection: Any | None = None,
    ):
        self.persist_dir = Path(persist_dir or _chroma_dir()).expanduser().resolve()
        self.collection_name = collection_name or os.getenv("WINTRIP_WORLD_AGENT_COLLECTION", WORLD_COLLECTION_NAME)
        self._collection_override = collection
        self._collection: Any | None = collection
        self._init_error = ""

    def status(self) -> dict[str, Any]:
        collection = self._get_collection()
        count = 0
        if collection is not None:
            try:
                count = int(collection.count())
            except Exception:
                count = 0
        return {
            "available": collection is not None,
            "collection": self.collection_name,
            "persist_dir": str(self.persist_dir),
            "count": count,
            "embedding_mode": _embedding_mode(),
            "reason": self._init_error,
        }

    def store_understanding(
        self,
        *,
        question: str,
        answer: str,
        source_url: str,
        action_id: str,
        status: str,
        browser_action_performed: bool,
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        collection = self._get_collection()
        if collection is None:
            return {"status": "unavailable", "stored": False, "reason": self._init_error, "fake_success": False}

        clean_question = _clean_question(question)
        clean_answer = _bounded_text(answer, MAX_WORLD_ANSWER_CHARS)
        document = (
            "Ouroboros world understanding\n"
            f"Source: {source_url}\n"
            f"Status: {status}\n"
            f"Question: {clean_question}\n"
            f"Answer: {clean_answer or '[geen browserantwoord vastgelegd]'}"
        )
        digest = hashlib.sha256(document.encode("utf-8", errors="ignore")).hexdigest()
        memory_id = f"world_grok_{action_id}_{digest[:16]}"
        metadatas = {
            "type": "world_understanding",
            "source": "world_agent",
            "source_type": "browser",
            "source_url": source_url,
            "host": "grok.com",
            "provider": "grok",
            "status": str(status or "unknown"),
            "action_id": action_id,
            "content_hash": digest,
            "question_hash": hashlib.sha256(clean_question.encode("utf-8", errors="ignore")).hexdigest(),
            "browser_action_performed": bool(browser_action_performed),
            "ingested_at": _now_iso(),
            "title": "Grok world understanding",
            "tags": "world_agent,grok,browser_understanding",
            "taint": "untrusted_web",
            "approval_status": "approved",
        }
        for key, value in (metadata or {}).items():
            if key not in metadatas and isinstance(value, (str, int, float, bool)):
                metadatas[str(key)[:64]] = value

        try:
            if hasattr(collection, "upsert"):
                collection.upsert(documents=[document], metadatas=[metadatas], ids=[memory_id])
            else:
                collection.add(documents=[document], metadatas=[metadatas], ids=[memory_id])
        except Exception as exc:
            return {"status": "error", "stored": False, "reason": str(exc), "fake_success": False}

        return {
            "status": "success",
            "stored": True,
            "memory_id": memory_id,
            "collection": self.collection_name,
            "document_chars": len(document),
        }

    def search(self, query: str, limit: int = 5) -> dict[str, Any]:
        clean_query = _clean_question(query)
        if not clean_query:
            return {"status": "blocked", "reason": "Zoekvraag ontbreekt.", "matches": [], "fake_success": False}
        collection = self._get_collection()
        if collection is None:
            return {"status": "unavailable", "reason": self._init_error, "matches": [], "fake_success": False}

        fetch_limit = max(1, min(int(limit or 5), 20))
        try:
            raw = collection.query(query_texts=[clean_query], n_results=fetch_limit)
        except Exception as exc:
            return {"status": "error", "reason": str(exc), "matches": [], "fake_success": False}

        matches: list[dict[str, Any]] = []
        documents = _first_list(raw.get("documents"))
        metadatas = _first_list(raw.get("metadatas"))
        distances = _first_list(raw.get("distances"))
        ids = _first_list(raw.get("ids"))
        for index, document in enumerate(documents):
            metadata = metadatas[index] if index < len(metadatas) and isinstance(metadatas[index], dict) else {}
            distance = distances[index] if index < len(distances) else None
            matches.append(
                {
                    "id": ids[index] if index < len(ids) else "",
                    "text": str(document or "")[:3000],
                    "metadata": metadata,
                    "distance": distance,
                    "score": _distance_to_score(distance),
                }
            )
        return {
            "status": "success",
            "query": clean_query,
            "count": len(matches),
            "matches": matches,
            "collection": self.collection_name,
        }

    def _get_collection(self) -> Any | None:
        if self._collection_override is not None:
            return self._collection_override
        if self._collection is not None:
            return self._collection
        try:
            import chromadb
        except Exception as exc:
            self._init_error = f"ChromaDB niet beschikbaar: {exc}"
            return None

        self.persist_dir.mkdir(parents=True, exist_ok=True)
        try:
            client = chromadb.PersistentClient(path=str(self.persist_dir))
            self._collection = client.get_or_create_collection(
                name=self.collection_name,
                embedding_function=_embedding_function(),
            )
            self._init_error = ""
        except Exception as exc:
            self._collection = None
            self._init_error = f"World memory niet beschikbaar: {exc}"
        return self._collection


class WorldActionLog:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or (_workspace_root() / "artifacts" / WORLD_ACTION_LOG_NAME)).expanduser().resolve()

    def append(self, payload: Mapping[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        record = {"ts": _now_iso(), **dict(payload)}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True, default=str) + "\n")

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()[-max(1, min(limit, 100)) :]
        except OSError:
            return []
        records: list[dict[str, Any]] = []
        for line in lines:
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                records.append(value)
        return records


class WorldAgent:
    def __init__(
        self,
        memory: WorldMemory | None = None,
        action_log: WorldActionLog | None = None,
        browser_runner: Callable[[str], BrowserActionResult] | None = None,
        tab_opener: Callable[[str], bool] | None = None,
    ):
        self.memory = memory or WorldMemory()
        self.action_log = action_log or WorldActionLog()
        self.browser_runner = browser_runner or _run_grok_ask_with_playwright
        self.tab_opener = tab_opener or _open_url_in_default_browser

    def status(self) -> dict[str, Any]:
        return {
            "status": "online",
            "agent": "world_agent",
            "grok_url": GROK_URL,
            "memory": self.memory.status(),
            "dependencies": {
                "chromadb": _module_available("chromadb"),
                "playwright": _module_available("playwright.sync_api"),
            },
            "host_bridge": bool(os.getenv("WINTRIP_RCLONE_BRIDGE_URL")),
            "recent_actions": self.action_log.recent(limit=12),
            "fake_success": False,
        }

    def ask_grok(
        self,
        question: str,
        *,
        approval: object = None,
        open_tab: bool = True,
        submit: bool = True,
    ) -> dict[str, Any]:
        clean_question = _clean_question(question)
        action_id = uuid.uuid4().hex
        frontend_action = {
            "type": "open_url",
            "url": GROK_URL,
            "target": "_blank",
            "agent": "world_agent",
            "action_id": action_id,
        }
        if not clean_question:
            return _world_payload(
                status="blocked",
                action_id=action_id,
                question="",
                response="",
                reason="Vraag ontbreekt.",
                next_action="Geef een concrete Grok-vraag op.",
                frontend_action=frontend_action if open_tab else None,
            )
        if submit and not _has_exact_approval(approval):
            return _world_payload(
                status="approval_required",
                action_id=action_id,
                question=clean_question,
                response="",
                reason="Grok openen en een vraag typen/submits vereist exact Akkoord.",
                next_action="Zet het Akkoord-veld op Akkoord en stuur de opdracht opnieuw.",
                frontend_action=frontend_action if open_tab else None,
                extra={
                    "approval_required": True,
                    "approval_phrase": DEFAULT_APPROVAL_PHRASE,
                    "blocked_actions": ["type", "submit"],
                    "browser_action_performed": False,
                },
            )

        tab_opened = False
        if open_tab:
            tab_opened = bool(self.tab_opener(GROK_URL))

        browser = self.browser_runner(clean_question) if submit else BrowserActionResult(
            status="opened",
            url=GROK_URL,
            reason="Grok-tab openen aangevraagd; er is niets getypt.",
            browser_action_performed=tab_opened,
        )
        visible_text = _bounded_text(browser.visible_text, MAX_WORLD_ANSWER_CHARS)
        scrubbed_answer = ""
        scrubbed_payload: dict[str, Any] = {}
        if visible_text:
            try:
                scrubbed = prepare_browser_ingest(
                    url=browser.url or GROK_URL,
                    browser_text=visible_text,
                    approval=approval,
                    title="Grok world answer",
                )
                scrubbed_answer = scrubbed.scrubbed_text
                scrubbed_payload = {
                    "taint": scrubbed.taint,
                    "blocked_patterns": list(scrubbed.blocked_patterns),
                    "diff_hash": scrubbed.diff_hash,
                    "approval_status": scrubbed.approval_status,
                    "source_host": scrubbed.source_host,
                }
            except Exception as exc:
                scrubbed_answer = scrub_data(visible_text)[:MAX_WORLD_ANSWER_CHARS]
                scrubbed_payload = {"taint": "untrusted_web", "scrub_error": str(exc)}

        answer_for_memory = scrubbed_answer or browser.reason or "Grok-tab geopend; geen browserantwoord vastgelegd."
        memory = self.memory.store_understanding(
            question=clean_question,
            answer=answer_for_memory,
            source_url=browser.url or GROK_URL,
            action_id=action_id,
            status=browser.status,
            browser_action_performed=bool(browser.browser_action_performed or tab_opened),
            metadata={
                "browser_status": browser.status,
                "tab_opened": bool(tab_opened),
                "title": browser.title[:240] if browser.title else "",
            },
        )
        payload = _world_payload(
            status=browser.status,
            action_id=action_id,
            question=clean_question,
            response=_answer_excerpt(scrubbed_answer, browser.reason),
            reason=browser.reason,
            next_action=browser.next_action or ("Semantisch zoeken kan via: wat weet je nog over <onderwerp>." if memory.get("stored") else ""),
            frontend_action=frontend_action if open_tab and not tab_opened else None,
            extra={
                "url": browser.url or GROK_URL,
                "title": browser.title,
                "backend": browser.backend,
                "browser_action_performed": bool(browser.browser_action_performed or tab_opened),
                "tab_opened": bool(tab_opened),
                "memory": memory,
                "scrubbed": scrubbed_payload,
                "fake_success": False,
            },
        )
        self._log_action(payload)
        return payload

    def search(self, query: str, limit: int = 5) -> dict[str, Any]:
        result = self.memory.search(query=query, limit=limit)
        payload = {
            "status": result.get("status", "unknown"),
            "route": "world_agent",
            "provider": "world_agent",
            "action": "memory_search",
            "query": result.get("query") or _clean_question(query),
            "matches": result.get("matches", []),
            "count": result.get("count", 0),
            "response": _format_memory_matches(result.get("matches", [])),
            "reason": result.get("reason", ""),
            "collection": result.get("collection", ""),
            "local_only": True,
            "fake_success": False,
        }
        self._log_action(payload)
        return payload

    def _log_action(self, payload: Mapping[str, Any]) -> None:
        try:
            self.action_log.append(payload)
        except Exception:
            pass


_WORLD_AGENT: WorldAgent | None = None


def get_world_agent() -> WorldAgent:
    global _WORLD_AGENT
    if _WORLD_AGENT is None:
        _WORLD_AGENT = WorldAgent()
    return _WORLD_AGENT


def world_agent_status() -> dict[str, Any]:
    local = get_world_agent().status()
    bridge = _bridge_request("GET", "/world/status", None, timeout=5)
    if bridge:
        bridge["via_bridge"] = True
        bridge["host_bridge"] = True
        bridge["memory"] = local.get("memory", {})
        bridge_dependencies = bridge.get("dependencies") if isinstance(bridge.get("dependencies"), dict) else {}
        local_dependencies = local.get("dependencies") if isinstance(local.get("dependencies"), dict) else {}
        bridge["dependencies"] = {
            **bridge_dependencies,
            "chromadb": bool(local_dependencies.get("chromadb")),
            "playwright_host": bool(bridge_dependencies.get("playwright")),
        }
        if local.get("recent_actions"):
            bridge["recent_actions"] = local.get("recent_actions", [])
        return bridge
    return local


def ask_grok_via_world_agent(
    question: str,
    *,
    approval: object = None,
    open_tab: bool = True,
    submit: bool = True,
    prefer_bridge: bool = True,
) -> dict[str, Any]:
    payload = {"question": question, "approval": approval or "", "open_tab": open_tab, "submit": submit}
    if prefer_bridge:
        bridge = _bridge_request("POST", "/world/grok", payload, timeout=_world_timeout_seconds())
        if bridge:
            bridge["via_bridge"] = True
            _store_bridge_world_result(bridge, question=question, approval=approval)
            return bridge
    return get_world_agent().ask_grok(question, approval=approval, open_tab=open_tab, submit=submit)


def search_world_memory(query: str, *, limit: int = 5, prefer_bridge: bool = False) -> dict[str, Any]:
    payload = {"query": query, "limit": limit}
    if prefer_bridge:
        bridge = _bridge_request("POST", "/world/search", payload, timeout=15)
        if bridge:
            bridge.setdefault("via_bridge", True)
            return bridge
    return get_world_agent().search(query, limit=limit)


def recent_world_actions(limit: int = 20, prefer_bridge: bool = False) -> dict[str, Any]:
    if prefer_bridge:
        bridge = _bridge_request("GET", f"/world/actions?limit={max(1, min(limit, 100))}", None, timeout=5)
        if bridge:
            bridge.setdefault("via_bridge", True)
            return bridge
    return {
        "status": "success",
        "actions": get_world_agent().action_log.recent(limit=limit),
        "fake_success": False,
    }


def _store_bridge_world_result(result: dict[str, Any], *, question: str, approval: object = None) -> None:
    if not _has_exact_approval(approval):
        return
    status = str(result.get("status") or "unknown")
    if status == "approval_required":
        return
    agent = get_world_agent()
    action_id = str(result.get("action_id") or uuid.uuid4().hex)
    memory = agent.memory.store_understanding(
        question=str(result.get("question") or question),
        answer=str(result.get("response") or result.get("reason") or result.get("next_action") or ""),
        source_url=str(result.get("url") or GROK_URL),
        action_id=action_id,
        status=status,
        browser_action_performed=bool(result.get("browser_action_performed") or result.get("tab_opened")),
        metadata={
            "via_bridge": True,
            "bridge_memory_status": str((result.get("memory") or {}).get("status") or ""),
        },
    )
    result["memory"] = memory
    try:
        agent.action_log.append(result)
    except Exception:
        pass


def detect_world_intent(prompt: object) -> WorldIntent | None:
    text = " ".join(str(prompt or "").strip().split())
    if not text or text.startswith("/"):
        return None
    lowered = text.lower()

    memory_patterns = (
        r"^wat weet (?:je|hij|ouroboros) nog over (?P<query>.+)$",
        r"^zoek (?:semantisch )?(?:in )?(?:het )?(?:wereldgeheugen|begrip-geheugen|begrip|world memory)(?: naar)? (?P<query>.+)$",
        r"^zoek in alles wat (?:je|ouroboros) (?:ooit )?heeft begrepen(?: naar)? (?P<query>.+)$",
    )
    for pattern in memory_patterns:
        match = re.search(pattern, lowered, flags=re.IGNORECASE)
        if match:
            return WorldIntent(action="memory_search", query=_clean_question(match.group("query")), target="world_memory")

    if "grok.com" in lowered or re.search(r"\bgrok\b", lowered):
        ask_patterns = (
            r"(?:open|ga naar|start)\s+grok(?:\.com)?\s+(?:en\s+)?(?:vraag|stel)\s+(?P<query>.+)$",
            r"(?:vraag|stel)\s+(?:aan\s+)?grok(?:\.com)?\s+(?P<query>.+)$",
            r"grok(?:\.com)?\s*[:\-]\s*(?P<query>.+)$",
        )
        for pattern in ask_patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return WorldIntent(action="grok_ask", query=_clean_question(match.group("query")), target="grok.com")
        if re.search(r"\b(open|ga naar|start)\b", lowered):
            return WorldIntent(action="grok_open", query="", target="grok.com")
    return None


def _run_grok_ask_with_playwright(question: str) -> BrowserActionResult:
    if _inside_running_asyncio_loop():
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(_run_grok_ask_with_playwright_blocking, question).result()
    return _run_grok_ask_with_playwright_blocking(question)


def _run_grok_ask_with_playwright_blocking(question: str) -> BrowserActionResult:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        return _playwright_unavailable(exc)

    timeout_ms = _world_timeout_ms()
    started = False
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=_world_headless())
            started = True
            try:
                page = browser.new_page(viewport={"width": 1400, "height": 900})
                page.goto(GROK_URL, wait_until="domcontentloaded", timeout=timeout_ms)
                _safe_network_idle(page, min(timeout_ms, 8_000))
                before = _safe_body_text(page)
                if _looks_like_login_or_captcha(before):
                    return BrowserActionResult(
                        status="login_required",
                        url=GROK_URL,
                        title=_safe_page_title(page),
                        visible_text=before,
                        reason="Grok toont login/CAPTCHA/interactieve verificatie; er is geen bypass uitgevoerd.",
                        next_action="Log handmatig in of gebruik een expliciete API-route; sessiemateriaal wordt niet opgeslagen.",
                        browser_action_performed=True,
                    )

                prompt = _first_visible_locator(
                    page,
                    [
                        'textarea[placeholder*="Ask"]',
                        'textarea[aria-label*="Ask"]',
                        'textarea[placeholder*="Message"]',
                        '[data-testid="composer-textarea"]',
                        'div[contenteditable="true"]',
                        "textarea",
                    ],
                )
                if prompt is None:
                    return BrowserActionResult(
                        status="blocked",
                        url=GROK_URL,
                        title=_safe_page_title(page),
                        visible_text=before,
                        reason="Geen Grok promptveld gevonden; er is niets getypt of gesubmit.",
                        next_action="Controleer handmatig of grok.com publiek bereikbaar en ingelogd is.",
                        browser_action_performed=True,
                    )

                prompt.click(timeout=2_000)
                try:
                    prompt.fill(question, timeout=3_000)
                except Exception:
                    prompt.type(question, timeout=5_000)
                page.keyboard.press("Enter")
                page.wait_for_timeout(_grok_wait_ms())
                text = _safe_body_text(page)
                title = _safe_page_title(page)
                if _looks_like_grok_rate_limit(text):
                    return BrowserActionResult(
                        status="rate_limited",
                        url=GROK_URL,
                        title=title,
                        visible_text=text,
                        reason="Grok accepteerde de prompt, maar gaf een drukte/rate-limit melding terug.",
                        next_action="Probeer later opnieuw of stel de vraag in de zichtbare Grok-tab waar je eventueel ingelogd bent.",
                        browser_action_performed=True,
                    )
            finally:
                browser.close()
    except PlaywrightTimeoutError as exc:
        return BrowserActionResult(
            status="failed",
            url=GROK_URL,
            reason=f"Grok browser timeout: {exc}",
            next_action="Probeer later opnieuw; er wordt geen antwoord gefaket.",
            browser_action_performed=True,
        )
    except PlaywrightError as exc:
        if _is_missing_browser_error(exc):
            return _playwright_unavailable(exc)
        return BrowserActionResult(
            status="failed",
            url=GROK_URL,
            reason=f"Playwright fout tijdens Grok ask: {exc}",
            next_action="Controleer browserinstallatie en Grok bereikbaarheid.",
            browser_action_performed=started,
        )
    except Exception as exc:
        return BrowserActionResult(
            status="failed",
            url=GROK_URL,
            reason=f"Grok browseractie mislukt: {exc}",
            next_action="Geen mock-response gemaakt; controleer Playwright/display/Grok handmatig.",
            browser_action_performed=started,
        )

    return BrowserActionResult(
        status="success",
        url=GROK_URL,
        title=title,
        visible_text=text,
        next_action="Grok-antwoord is gescrubd en opgeslagen in world understanding memory.",
        browser_action_performed=True,
    )


def _world_payload(
    *,
    status: str,
    action_id: str,
    question: str,
    response: str,
    reason: str = "",
    next_action: str = "",
    frontend_action: dict[str, Any] | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "status": status,
        "route": "world_agent",
        "provider": "world_agent",
        "model": "grok.com",
        "action": "grok_ask",
        "action_id": action_id,
        "question": question,
        "response": response,
        "reason": reason,
        "next_action": next_action,
        "local_only": False,
        "tool_schemas": [],
        "tool_schema_count": 0,
        "fake_success": False,
    }
    if frontend_action:
        payload["frontend_action"] = frontend_action
    payload.update(dict(extra or {}))
    return payload


def _format_memory_matches(matches: Sequence[Mapping[str, Any]]) -> str:
    if not matches:
        return "Geen wereld-geheugenmatches gevonden."
    lines = ["Wereldgeheugen:"]
    for index, match in enumerate(matches[:8], start=1):
        text = str(match.get("text") or "").strip().replace("\n", " ")
        score = match.get("score")
        score_text = f" score={score:.3f}" if isinstance(score, (int, float)) else ""
        lines.append(f"{index}. {text[:700]}{score_text}")
    return "\n".join(lines)


def _answer_excerpt(answer: str, reason: str = "") -> str:
    text = str(answer or "").strip()
    if text:
        return text[:4000]
    return str(reason or "Grok actie uitgevoerd; geen antwoordtekst vastgelegd.").strip()


def _open_url_in_default_browser(url: str) -> bool:
    try:
        return bool(webbrowser.open(url, new=2, autoraise=True))
    except Exception:
        return False


def _bridge_request(method: str, path: str, payload: Mapping[str, Any] | None, timeout: float) -> dict[str, Any]:
    base_url = str(os.getenv("WINTRIP_RCLONE_BRIDGE_URL") or "").rstrip("/")
    token_path = os.getenv("WINTRIP_RCLONE_BRIDGE_TOKEN_PATH")
    if not base_url or not token_path:
        return {}
    try:
        token = Path(token_path).read_text(encoding="utf-8").strip()
    except OSError:
        return {}
    data = json.dumps(dict(payload or {}), ensure_ascii=False).encode("utf-8") if method == "POST" else None
    request = urllib.request.Request(
        f"{base_url}{path}",
        data=data,
        method=method,
        headers={
            "Content-Type": "application/json",
            "X-Ouroboros-Bridge-Token": token,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            value = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            value = json.loads(exc.read().decode("utf-8"))
        except Exception:
            value = {"status": "error", "reason": str(exc), "fake_success": False}
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _embedding_function() -> Any:
    mode = _embedding_mode()
    if mode == "ollama":
        try:
            from chromadb.utils import embedding_functions

            ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            embed_model = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
            return embedding_functions.OllamaEmbeddingFunction(
                url=f"{ollama_url}/api/embeddings",
                model_name=embed_model,
            )
        except Exception:
            return HashEmbeddingFunction()
    return HashEmbeddingFunction()


def _embedding_mode() -> str:
    return os.getenv("WINTRIP_WORLD_AGENT_EMBEDDINGS", "hash").strip().lower() or "hash"


def _workspace_root() -> Path:
    return Path(os.getenv("WINTRIP_WORKSPACE") or Path(__file__).resolve().parents[1]).expanduser().resolve()


def _chroma_dir() -> Path:
    return Path(os.getenv("WINTRIP_DB_PATH") or (_workspace_root() / "wintrip_brain")).expanduser().resolve()


def _tokens(text: str) -> Iterable[str]:
    for token in _TOKEN_RE.findall(str(text or "").casefold()):
        yield token


def _clean_question(value: object) -> str:
    return _bounded_text(scrub_data(str(value or "").replace("\x00", " ").strip()), MAX_WORLD_QUESTION_CHARS)


def _has_exact_approval(value: object) -> bool:
    return str(value or "").strip() == DEFAULT_APPROVAL_PHRASE


def _bounded_text(value: object, max_chars: int) -> str:
    text = str(value or "").replace("\x00", " ").strip()
    return text[:max_chars] if len(text) > max_chars else text


def _first_list(value: Any) -> list[Any]:
    if isinstance(value, list) and value and isinstance(value[0], list):
        return value[0]
    return value if isinstance(value, list) else []


def _distance_to_score(distance: Any) -> float:
    try:
        return max(0.0, 1.0 / (1.0 + float(distance)))
    except Exception:
        return 0.0


def _module_available(module_name: str) -> bool:
    try:
        __import__(module_name)
        return True
    except Exception:
        return False


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _inside_running_asyncio_loop() -> bool:
    try:
        import asyncio

        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


def _world_timeout_seconds() -> float:
    return max(3.0, min((_world_timeout_ms() / 1000.0) + 10.0, 90.0))


def _world_timeout_ms() -> int:
    try:
        return max(2_000, min(90_000, int(os.getenv("WINTRIP_WORLD_AGENT_TIMEOUT_MS", str(DEFAULT_WORLD_TIMEOUT_MS)))))
    except ValueError:
        return DEFAULT_WORLD_TIMEOUT_MS


def _grok_wait_ms() -> int:
    try:
        return max(1_000, min(60_000, int(os.getenv("WINTRIP_GROK_WAIT_MS", str(DEFAULT_GROK_WAIT_MS)))))
    except ValueError:
        return DEFAULT_GROK_WAIT_MS


def _world_headless() -> bool:
    return os.getenv("WINTRIP_WORLD_AGENT_HEADLESS", "0").strip().lower() in {"1", "true", "yes"}


def _playwright_unavailable(exc: BaseException) -> BrowserActionResult:
    return BrowserActionResult(
        status="unavailable",
        url=GROK_URL,
        reason=f"Playwright backend/browser niet beschikbaar: {exc}",
        next_action="Installeer optioneel: pip install playwright && python -m playwright install chromium.",
        browser_action_performed=False,
    )


def _is_missing_browser_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    return "executable doesn't exist" in message or "playwright install" in message or "browser executable" in message


def _looks_like_login_or_captcha(text: str) -> bool:
    return bool(_LOGIN_OR_CAPTCHA_RE.search(text or ""))


def _looks_like_grok_rate_limit(text: str) -> bool:
    return bool(_GROK_RATE_LIMIT_RE.search(text or ""))


def _safe_network_idle(page: Any, timeout_ms: int) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=timeout_ms)
    except Exception:
        pass


def _safe_page_title(page: Any) -> str:
    try:
        return str(page.title() or "")[:256]
    except Exception:
        return ""


def _safe_body_text(page: Any) -> str:
    try:
        return str(page.locator("body").inner_text(timeout=2_000) or "")
    except Exception:
        try:
            return str(page.content() or "")
        except Exception:
            return ""


def _first_visible_locator(page: Any, selectors: Sequence[str]) -> Any | None:
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.is_visible(timeout=1_000):
                return locator
        except Exception:
            continue
    return None
