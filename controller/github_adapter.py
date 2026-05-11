"""Read-only GitHub connector adapter for Ouroboros ordinary chat.

Purpose:
    Provide truthful GitHub status, public repository metadata and public
    repository search through the official GitHub REST API.
Safety notes:
    Tokens may be loaded from environment variables or the cockpit API-key
    store for rate-limit/auth support, but tokens are never returned. Write and
    mutating operations are intentionally absent from this adapter.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from controller.ecosystem_11d import redact_sensitive_text


APPROVAL_PHRASE = "Akkoord"
GITHUB_API_BASE = "https://api.github.com"
GITHUB_TOKEN_ENVS = ("GITHUB_TOKEN", "GH_TOKEN", "GITHUB_API_TOKEN")


def get_github_status() -> dict[str, Any]:
    return GitHubAdapter().status()


class GitHubAdapter:
    """Small read-only GitHub REST API wrapper.

    The adapter deliberately exposes no create/update/delete methods. Public
    reads do not require approval. Private repository metadata is blocked unless
    explicit Akkoord is supplied, and even then only sanitized metadata is
    returned.
    """

    def __init__(
        self,
        token: str | None = None,
        *,
        api_base: str | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        resolved = _resolve_github_token(token)
        self._token = resolved["token"]
        self._token_source = resolved["source"]
        self._token_masked = resolved["masked"]
        self.api_base = (api_base or os.getenv("WINTRIP_GITHUB_API_BASE") or GITHUB_API_BASE).rstrip("/")
        self.timeout_seconds = max(3, min(int(timeout_seconds or os.getenv("WINTRIP_GITHUB_TIMEOUT", "15")), 60))

    def status(self) -> dict[str, Any]:
        return {
            "status": "configured" if self._token else "anonymous_public_only",
            "adapter": "github",
            "api_base": self.api_base,
            "token": {
                "configured": bool(self._token),
                "source": self._token_source,
                "masked": self._token_masked,
                "secrets_returned": False,
            },
            "read_only": True,
            "public_reads_without_approval": True,
            "private_reads_require_approval": True,
            "write_methods_enabled": False,
            "supported_methods": ["status", "get_repository", "search_repositories"],
            "secrets_returned": False,
            "fake_success": False,
        }

    def get_repository(self, repo: str, *, approval: str = "") -> dict[str, Any]:
        parsed = _parse_repo(repo)
        if not parsed:
            return {
                "status": "error",
                "operation": "get_repository",
                "reason": "GitHub repository must be owner/repo or a github.com/owner/repo URL.",
                "fake_success": False,
            }
        owner, name = parsed
        response = self._request_json(
            f"/repos/{urllib.parse.quote(owner, safe='')}/{urllib.parse.quote(name, safe='')}",
            use_token=approval == APPROVAL_PHRASE,
        )
        if response.get("status") != "success":
            response["operation"] = "get_repository"
            response["repo"] = f"{owner}/{name}"
            return response
        payload = response.get("payload") if isinstance(response.get("payload"), dict) else {}
        is_private = bool(payload.get("private"))
        if is_private and approval != APPROVAL_PHRASE:
            return {
                "status": "blocked",
                "operation": "get_repository",
                "repo": f"{owner}/{name}",
                "private": True,
                "approval_required": True,
                "reason": "Private GitHub repository metadata requires exact Akkoord.",
                "secrets_returned": False,
                "fake_success": False,
            }
        compact = _compact_repo(payload)
        return {
            "status": "success",
            "source": "github_api",
            "operation": "get_repository",
            "repo": compact,
            "private": is_private,
            "read_only": True,
            "approval_status": "approved_private_read" if is_private else "not_required_public_readonly",
            "secrets_returned": False,
            "fake_success": False,
        }

    def search_repositories(self, query: str, *, limit: int = 10, approval: str = "") -> dict[str, Any]:
        clean_query = " ".join(str(query or "").split())
        if not clean_query:
            return {
                "status": "error",
                "operation": "search_repositories",
                "reason": "GitHub repository search query is empty.",
                "fake_success": False,
            }
        if _private_query_requested(clean_query) and approval != APPROVAL_PHRASE:
            return {
                "status": "blocked",
                "operation": "search_repositories",
                "query": clean_query[:400],
                "approval_required": True,
                "reason": "Private GitHub search requires exact Akkoord and is not executed by the public-search adapter.",
                "secrets_returned": False,
                "fake_success": False,
            }
        effective_query = _force_public_repo_query(clean_query)
        per_page = max(1, min(int(limit or 10), 50))
        response = self._request_json(
            "/search/repositories",
            params={"q": effective_query, "per_page": str(per_page), "sort": "updated", "order": "desc"},
        )
        if response.get("status") != "success":
            response["operation"] = "search_repositories"
            response["query"] = clean_query[:400]
            response["effective_query"] = effective_query[:450]
            return response
        payload = response.get("payload") if isinstance(response.get("payload"), dict) else {}
        raw_items = payload.get("items", []) if isinstance(payload, dict) else []
        public_items = [item for item in raw_items if isinstance(item, dict) and not bool(item.get("private"))]
        compact = [_compact_repo(item) for item in public_items[:per_page]]
        return {
            "status": "success",
            "source": "github_api",
            "operation": "search_repositories",
            "query": clean_query[:400],
            "effective_query": effective_query[:450],
            "count": len(compact),
            "total_count": int(payload.get("total_count") or 0) if isinstance(payload, dict) else len(compact),
            "items": compact,
            "private_items_filtered": max(0, len([item for item in raw_items if isinstance(item, dict)]) - len(public_items)),
            "read_only": True,
            "approval_status": "not_required_public_readonly",
            "secrets_returned": False,
            "fake_success": False,
        }

    def _request_json(self, path: str, params: dict[str, str] | None = None, *, use_token: bool = True) -> dict[str, Any]:
        query = "?" + urllib.parse.urlencode(params or {}) if params else ""
        url = f"{self.api_base}{path}{query}"
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "WintripAI-Ouroboros/0.1",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._token and use_token:
            headers["Authorization"] = f"Bearer {self._token}"
        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8", "replace")
            payload = json.loads(raw) if raw.strip() else {}
            return {"status": "success", "source": "github_api", "payload": payload, "fake_success": False}
        except urllib.error.HTTPError as exc:
            status = "not_found" if exc.code == 404 else ("rate_limited" if exc.code in {403, 429} else "error")
            return {"status": status, "http_status": exc.code, "reason": _safe_github_error(exc), "fake_success": False}
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            return {"status": "error", "reason": _safe_github_error(exc), "fake_success": False}


def _resolve_github_token(explicit: str | None = None) -> dict[str, str]:
    if explicit:
        token = str(explicit).strip()
        return {"token": token, "source": "explicit", "masked": _mask_token(token)}
    for name in GITHUB_TOKEN_ENVS:
        value = os.getenv(name, "").strip()
        if value:
            return {"token": value, "source": f"env:{name}", "masked": _mask_token(value)}
    try:
        from controller.api_key_store import load_provider_api_keys

        value = str(load_provider_api_keys().get("github") or "").strip()
        if value:
            return {"token": value, "source": "api_key_store", "masked": _mask_token(value)}
    except Exception:
        pass
    return {"token": "", "source": "missing", "masked": ""}


def _parse_repo(value: str) -> tuple[str, str] | None:
    text = str(value or "").strip()
    if not text:
        return None
    url_match = re.search(r"github\.com[:/]+([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)", text, re.IGNORECASE)
    if url_match:
        owner, repo = url_match.group(1), url_match.group(2)
    else:
        match = re.search(r"\b([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)\b", text)
        if not match:
            return None
        owner, repo = match.group(1), match.group(2)
    repo = repo.removesuffix(".git").strip(".,;:!?)]}")
    if not owner or not repo:
        return None
    return owner, repo


def _private_query_requested(query: str) -> bool:
    lowered = str(query or "").lower()
    return bool(re.search(r"\bis:private\b|\bvisibility:private\b|\bprivate\s+repo", lowered))


def _force_public_repo_query(query: str) -> str:
    clean = " ".join(str(query or "").split())
    if re.search(r"\bis:public\b|\bvisibility:public\b", clean, flags=re.IGNORECASE):
        return clean
    return f"{clean} is:public"


def _compact_repo(item: dict[str, Any]) -> dict[str, Any]:
    owner = item.get("owner") if isinstance(item.get("owner"), dict) else {}
    license_info = item.get("license") if isinstance(item.get("license"), dict) else {}
    return {
        "id": item.get("id"),
        "name": str(item.get("name") or "")[:180],
        "full_name": str(item.get("full_name") or "")[:240],
        "private": bool(item.get("private")),
        "html_url": str(item.get("html_url") or "")[:500],
        "description": _redact_github_text(str(item.get("description") or ""), max_chars=500),
        "visibility": str(item.get("visibility") or ("private" if item.get("private") else "public"))[:80],
        "fork": bool(item.get("fork")),
        "archived": bool(item.get("archived")),
        "disabled": bool(item.get("disabled")),
        "default_branch": str(item.get("default_branch") or "")[:160],
        "language": str(item.get("language") or "")[:120],
        "stargazers_count": int(item.get("stargazers_count") or 0),
        "forks_count": int(item.get("forks_count") or item.get("forks") or 0),
        "open_issues_count": int(item.get("open_issues_count") or 0),
        "updated_at": str(item.get("updated_at") or "")[:120],
        "pushed_at": str(item.get("pushed_at") or "")[:120],
        "topics": [str(topic)[:80] for topic in (item.get("topics") or [])[:20]],
        "license": str(license_info.get("spdx_id") or license_info.get("key") or "")[:80],
        "owner": {
            "login": str(owner.get("login") or "")[:160],
            "type": str(owner.get("type") or "")[:80],
            "html_url": str(owner.get("html_url") or "")[:500],
        },
    }


def _safe_github_error(exc: BaseException) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        try:
            raw = exc.read().decode("utf-8", errors="replace")
        except Exception:
            raw = str(exc)
        return _redact_github_text(raw or str(exc), max_chars=1200)
    return _redact_github_text(str(exc), max_chars=1200)


def _redact_github_text(value: str, *, max_chars: int = 1200) -> str:
    text = redact_sensitive_text(str(value or ""), max_chars=max_chars)
    patterns = (
        re.compile(r"(?i)(api[_-]?key|token|secret|password|passwd|bearer)\s*[:=]\s*['\"]?[^'\"\s,;}]+"),
        re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{12,}\b"),
    )
    for pattern in patterns:
        text = pattern.sub(lambda match: f"{match.group(1)}=[REDACTED]" if match.groups() else "[REDACTED]", text)
    return text[:max_chars]


def _mask_token(value: str) -> str:
    text = str(value or "")
    if not text:
        return ""
    if len(text) <= 8:
        return "*" * len(text)
    return f"{text[:4]}...{text[-4:]}"
