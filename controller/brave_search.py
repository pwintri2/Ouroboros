"""Brave Search integration for Ouroboros learning.

The client is deliberately small and server-side only: API keys come from
environment variables or the existing encrypted-by-permission local key store,
responses are normalized before storage, and the process-wide limiter defaults
to at most 50 requests per second.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Mapping

try:
    import requests
except ModuleNotFoundError:  # pragma: no cover - bare sandbox fallback.
    requests = None  # type: ignore[assignment]


BRAVE_WEB_SEARCH_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
BRAVE_LLM_CONTEXT_ENDPOINT = "https://api.search.brave.com/res/v1/llm/context"
DEFAULT_BRAVE_RPS = 50
MAX_QUERY_CHARS = 400
MAX_DOCUMENT_CHARS = 16_000


class BraveRateLimiter:
    """Process-local sliding-window limiter for Brave's per-second quota."""

    def __init__(self, requests_per_second: int = DEFAULT_BRAVE_RPS):
        self.requests_per_second = _bounded_rps(requests_per_second)
        self._lock = threading.Lock()
        self._timestamps: deque[float] = deque()

    def wait(self) -> float:
        waited = 0.0
        while True:
            with self._lock:
                now = time.monotonic()
                while self._timestamps and now - self._timestamps[0] >= 1.0:
                    self._timestamps.popleft()
                if len(self._timestamps) < self.requests_per_second:
                    self._timestamps.append(now)
                    return round(waited, 6)
                sleep_for = max(0.001, 1.0 - (now - self._timestamps[0]))
            time.sleep(sleep_for)
            waited += sleep_for


class BraveSearchClient:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        session: Any | None = None,
        limiter: BraveRateLimiter | None = None,
        timeout: float = 12.0,
    ) -> None:
        self.api_key = str(api_key or _load_brave_api_key() or "").strip()
        self.session = session or requests
        self.limiter = limiter or _LIMITER
        self.timeout = timeout

    def status(self) -> dict[str, Any]:
        return {
            "status": "configured" if self.configured else "missing_api_key",
            "provider": "brave",
            "configured": self.configured,
            "rate_limit_per_second": self.limiter.requests_per_second,
            "web_search_endpoint": _redact_url(_web_endpoint()),
            "llm_context_endpoint": _redact_url(_llm_endpoint()),
            "fake_success": False,
        }

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def web_search(
        self,
        query: str,
        *,
        count: int = 5,
        freshness: str = "",
        search_lang: str = "en",
        country: str = "US",
        extra_snippets: bool = True,
    ) -> dict[str, Any]:
        clean_query = _clean_query(query)
        if not clean_query:
            return {"status": "blocked", "reason": "Brave query ontbreekt.", "matches": [], "fake_success": False}
        if not self.configured:
            return {"status": "missing_api_key", "provider": "brave", "matches": [], "fake_success": False}
        if self.session is None:
            return {"status": "unavailable", "reason": "requests module niet beschikbaar", "matches": [], "fake_success": False}

        params: dict[str, Any] = {
            "q": clean_query,
            "count": max(1, min(int(count or 5), 20)),
            "search_lang": search_lang or "en",
            "country": country or "US",
            "safesearch": "moderate",
        }
        if freshness:
            params["freshness"] = freshness
        if extra_snippets:
            params["extra_snippets"] = "true"

        waited = self.limiter.wait()
        try:
            response = self.session.get(
                _web_endpoint(),
                headers=self._headers(),
                params=params,
                timeout=self.timeout,
            )
        except Exception as exc:
            return {"status": "error", "provider": "brave", "reason": str(exc), "matches": [], "fake_success": False}

        if getattr(response, "status_code", 0) == 429:
            return _rate_limited_payload(response)
        if not bool(getattr(response, "ok", False)):
            return _provider_error_payload(response)

        try:
            data = response.json()
        except Exception as exc:
            return {"status": "error", "provider": "brave", "reason": f"Invalid JSON: {exc}", "matches": [], "fake_success": False}

        matches = _web_matches(data)
        return {
            "status": "success",
            "provider": "brave",
            "query": clean_query,
            "count": len(matches),
            "matches": matches,
            "rate_limit": _rate_headers(response),
            "rate_limit_waited_seconds": waited,
            "raw_query": data.get("query") if isinstance(data, Mapping) else {},
            "fake_success": False,
        }

    def llm_context(
        self,
        query: str,
        *,
        count: int = 20,
        maximum_number_of_tokens: int = 8192,
        maximum_number_of_urls: int = 8,
        search_lang: str = "en",
        country: str = "US",
        freshness: str = "",
    ) -> dict[str, Any]:
        clean_query = _clean_query(query)
        if not clean_query:
            return {"status": "blocked", "reason": "Brave query ontbreekt.", "document": "", "fake_success": False}
        if not self.configured:
            return {"status": "missing_api_key", "provider": "brave", "document": "", "fake_success": False}
        if self.session is None:
            return {"status": "unavailable", "reason": "requests module niet beschikbaar", "document": "", "fake_success": False}

        params: dict[str, Any] = {
            "q": clean_query,
            "count": max(1, min(int(count or 20), 50)),
            "maximum_number_of_tokens": max(1024, min(int(maximum_number_of_tokens or 8192), 32768)),
            "maximum_number_of_urls": max(1, min(int(maximum_number_of_urls or 8), 50)),
            "maximum_number_of_snippets": max(1, min(int(os.getenv("WINTRIP_BRAVE_MAX_SNIPPETS", "60") or 60), 256)),
            "search_lang": search_lang or "en",
            "country": country or "US",
            "enable_source_metadata": "true",
        }
        if freshness:
            params["freshness"] = freshness

        waited = self.limiter.wait()
        try:
            response = self.session.get(
                _llm_endpoint(),
                headers=self._headers(),
                params=params,
                timeout=max(self.timeout, 20.0),
            )
        except Exception as exc:
            return {"status": "error", "provider": "brave", "reason": str(exc), "document": "", "fake_success": False}

        if getattr(response, "status_code", 0) == 429:
            payload = _rate_limited_payload(response)
            payload["document"] = ""
            return payload
        if not bool(getattr(response, "ok", False)):
            payload = _provider_error_payload(response)
            payload["document"] = ""
            return payload

        try:
            data = response.json()
        except Exception as exc:
            return {"status": "error", "provider": "brave", "reason": f"Invalid JSON: {exc}", "document": "", "fake_success": False}

        document, sources = _llm_context_document(clean_query, data)
        if not document.strip():
            fallback = self.web_search(query, count=min(10, int(count or 10)), search_lang=search_lang, country=country, freshness=freshness)
            document = _web_document(clean_query, fallback.get("matches") or [])
            sources = [item.get("url", "") for item in fallback.get("matches") or [] if item.get("url")]
        return {
            "status": "success",
            "provider": "brave",
            "query": clean_query,
            "document": document[:MAX_DOCUMENT_CHARS],
            "document_chars": min(len(document), MAX_DOCUMENT_CHARS),
            "source_urls": sources[:50],
            "source": "brave:llm_context",
            "rate_limit": _rate_headers(response),
            "rate_limit_waited_seconds": waited,
            "fake_success": False,
        }

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self.api_key,
            "User-Agent": "WintripAI-Ouroboros/1.0",
        }


def brave_search_status() -> dict[str, Any]:
    return BraveSearchClient().status()


def search_brave_web(query: str, **kwargs: Any) -> dict[str, Any]:
    return BraveSearchClient().web_search(query, **kwargs)


def search_brave_llm_context(query: str, **kwargs: Any) -> dict[str, Any]:
    return BraveSearchClient().llm_context(query, **kwargs)


def brave_training_document(query: str, **kwargs: Any) -> dict[str, Any]:
    result = search_brave_llm_context(query, **kwargs)
    if result.get("status") == "missing_api_key":
        return result
    if result.get("status") != "success":
        return result
    document = (
        "Brave LLM Context voor Ouroboros 11D learning\n"
        f"Query: {result.get('query')}\n"
        f"Observed at: {datetime.now(timezone.utc).isoformat()}\n"
        f"Sources: {', '.join(result.get('source_urls') or [])}\n\n"
        f"{result.get('document') or ''}"
    )
    return {
        **result,
        "document": document[:MAX_DOCUMENT_CHARS],
        "content_hash": hashlib.sha256(document.encode("utf-8", errors="ignore")).hexdigest(),
    }


def _load_brave_api_key() -> str:
    for name in ("BRAVE_SEARCH_API_KEY", "BRAVE_API_KEY"):
        value = os.getenv(name)
        if value:
            return value
    try:
        from controller.api_key_store import load_provider_api_keys

        return str(load_provider_api_keys().get("brave") or "")
    except Exception:
        return ""


def _bounded_rps(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = DEFAULT_BRAVE_RPS
    return max(1, min(parsed, DEFAULT_BRAVE_RPS))


_LIMITER = BraveRateLimiter(int(os.getenv("WINTRIP_BRAVE_RPS", str(DEFAULT_BRAVE_RPS)) or DEFAULT_BRAVE_RPS))


def _web_endpoint() -> str:
    return os.getenv("BRAVE_WEB_SEARCH_ENDPOINT", BRAVE_WEB_SEARCH_ENDPOINT)


def _llm_endpoint() -> str:
    return os.getenv("BRAVE_LLM_CONTEXT_ENDPOINT", BRAVE_LLM_CONTEXT_ENDPOINT)


def _clean_query(query: Any) -> str:
    words = " ".join(str(query or "").replace("\x00", " ").strip().split())
    return " ".join(words.split()[:50])[:MAX_QUERY_CHARS]


def _web_matches(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    web = data.get("web") if isinstance(data, Mapping) else {}
    results = web.get("results") if isinstance(web, Mapping) else []
    matches: list[dict[str, Any]] = []
    for index, item in enumerate(results or []):
        if not isinstance(item, Mapping):
            continue
        snippets = [str(value) for value in list(item.get("extra_snippets") or [])[:5] if value]
        matches.append(
            {
                "rank": index + 1,
                "title": str(item.get("title") or "")[:500],
                "url": str(item.get("url") or "")[:1000],
                "description": str(item.get("description") or "")[:2000],
                "extra_snippets": snippets,
                "age": item.get("age") or item.get("page_age") or "",
                "source": "brave:web_search",
            }
        )
    return matches


def _llm_context_document(query: str, data: Mapping[str, Any]) -> tuple[str, list[str]]:
    sources_payload = data.get("sources") if isinstance(data.get("sources"), Mapping) else {}
    sources = [str(url) for url in (sources_payload or {}).keys()]
    grounding = data.get("grounding")
    parts: list[str] = [f"Query: {query}"]
    _collect_text_parts(grounding, parts, path="grounding")
    if sources:
        parts.append("Sources:")
        for url, meta in list((sources_payload or {}).items())[:50]:
            title = meta.get("title") if isinstance(meta, Mapping) else ""
            parts.append(f"- {title or url}: {url}")
    document = "\n".join(_dedupe_lines(parts))
    return document[:MAX_DOCUMENT_CHARS], sources


def _collect_text_parts(value: Any, parts: list[str], *, path: str) -> None:
    if isinstance(value, str):
        text = " ".join(value.split())
        if len(text) >= 24:
            parts.append(text[:4000])
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).lower() in {"url", "thumbnail", "favicon"}:
                continue
            _collect_text_parts(item, parts, path=f"{path}.{key}")
        return
    if isinstance(value, list):
        for item in value[:300]:
            _collect_text_parts(item, parts, path=path)


def _web_document(query: str, matches: list[Mapping[str, Any]]) -> str:
    lines = [f"Brave web fallback search voor: {query}"]
    for item in matches[:10]:
        lines.append(f"\nTitle: {item.get('title')}")
        lines.append(f"URL: {item.get('url')}")
        if item.get("description"):
            lines.append(f"Snippet: {item.get('description')}")
        for snippet in item.get("extra_snippets") or []:
            lines.append(f"Extra: {snippet}")
    return "\n".join(lines)[:MAX_DOCUMENT_CHARS]


def _dedupe_lines(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        clean = str(line or "").strip()
        if not clean:
            continue
        key = clean[:300]
        if key in seen:
            continue
        seen.add(key)
        out.append(clean)
    return out


def _rate_limited_payload(response: Any) -> dict[str, Any]:
    return {
        "status": "rate_limited",
        "provider": "brave",
        "reason": _error_text(response) or "Brave Search rate limit.",
        "rate_limit": _rate_headers(response),
        "retry_after_seconds": _first_int(_headers_value(response, "X-RateLimit-Reset")),
        "fake_success": False,
    }


def _provider_error_payload(response: Any) -> dict[str, Any]:
    return {
        "status": "error",
        "provider": "brave",
        "provider_status_code": int(getattr(response, "status_code", 0) or 0),
        "reason": _error_text(response),
        "rate_limit": _rate_headers(response),
        "fake_success": False,
    }


def _error_text(response: Any) -> str:
    try:
        payload = response.json()
        if isinstance(payload, Mapping):
            error = payload.get("error")
            if isinstance(error, Mapping):
                return str(error.get("message") or error.get("detail") or error.get("code") or "")[:2000]
            return json.dumps(payload, ensure_ascii=False, sort_keys=True)[:2000]
    except Exception:
        pass
    return str(getattr(response, "text", "") or "")[:2000]


def _rate_headers(response: Any) -> dict[str, str]:
    return {
        name: _headers_value(response, name)
        for name in ("X-RateLimit-Limit", "X-RateLimit-Policy", "X-RateLimit-Remaining", "X-RateLimit-Reset")
        if _headers_value(response, name)
    }


def _headers_value(response: Any, name: str) -> str:
    headers = getattr(response, "headers", {}) or {}
    if callable(getattr(headers, "get", None)):
        return str(headers.get(name) or headers.get(name.lower()) or "")
    return ""


def _first_int(value: str) -> int:
    try:
        return int(str(value or "").split(",", 1)[0].strip())
    except (TypeError, ValueError):
        return 0


def _redact_url(value: str) -> str:
    return str(value or "").split("?", 1)[0]
