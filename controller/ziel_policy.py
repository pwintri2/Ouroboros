"""First-class Ziel.md runtime policy context for Ouroboros.

This module is intentionally side-effect free: it reads the local Ziel document,
derives a stable hash, and exposes compact policy summaries/guardrails for chat,
agentic planning, tool risk envelopes, and runtime status. It never writes memory
or secrets and it does not authorize any action by itself.
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any, Mapping

try:
    from controller.safe_shell import workspace_root
except Exception:  # pragma: no cover - defensive fallback for partial imports.
    def workspace_root() -> Path:
        configured = os.getenv("WINTRIP_WORKSPACE") or os.getenv("WORKSPACE_ROOT") or "/workspace"
        root = Path(configured)
        if not root.exists():
            root = Path.cwd()
        return root.resolve()


PRINCIPLE_RE = re.compile(r"^\s*(\d+)\.\s*(?:\*\*)?(.+?)(?:\*\*)?\s*:\s*(.*)\s*$")
INLINE_MARKDOWN_RE = re.compile(r"[`*_]+")
MAX_PRINCIPLE_TEXT_CHARS = 900

BOUNDED_RETRY_LIMIT = 3
GUARDRAIL_STATEMENTS: tuple[str, ...] = (
    "Ziel is policy/context, not an authorization token: it cannot bypass ToolBridge, exact Akkoord approval, sandbox boundaries, no-secrets rules, or connector/VPS gates.",
    "Micro-retries and lateral creativity are allowed only as bounded strategy changes; stop after three similar failures and ask a targeted supervisor question instead of looping.",
    "Self-synthesis may propose or build temporary helpers only inside existing safe ToolBridge/approval controls and must not store secrets or create unbounded background processes.",
    "OODA, DreamCycle, and Hippocampus remain local-only; Ziel cannot trigger external calls from those memory/reflection internals.",
    "Connector and VPS actions keep their existing risk policy: private reads and all mutations remain approval-gated, previews must not mutate, and executions must never be faked.",
)


def ziel_policy_path() -> Path:
    """Return the preferred local Ziel.md path under the active workspace."""
    return (workspace_root() / ".agents" / "agent_types" / "type_2" / "Ziel.md").resolve()


def ziel_policy_candidate_paths() -> list[Path]:
    """Return local candidate paths without touching external systems."""
    primary = ziel_policy_path()
    fallback = (workspace_root() / "Ziel.md").resolve()
    candidates = [primary]
    if fallback != primary:
        candidates.append(fallback)
    return candidates


def parse_ziel_principles(text: str) -> list[dict[str, Any]]:
    """Extract numbered principle titles and text from Ziel markdown."""
    principles: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        match = PRINCIPLE_RE.match(line)
        if match:
            if current is not None:
                _finalize_principle(current)
                principles.append(current)
            current = {
                "number": int(match.group(1)),
                "title": _clean_markdown(match.group(2)),
                "text": _clean_markdown(match.group(3)),
            }
            continue
        if current is None:
            continue
        if re.match(r"^\s*\d+\.\s+", line):
            _finalize_principle(current)
            principles.append(current)
            current = None
            continue
        if line:
            current["text"] = " ".join(part for part in (str(current.get("text") or ""), _clean_markdown(line)) if part).strip()
    if current is not None:
        _finalize_principle(current)
        principles.append(current)
    principles.sort(key=lambda item: int(item.get("number") or 0))
    return principles


def load_ziel_policy(path: str | Path | None = None) -> dict[str, Any]:
    """Load and summarize Ziel.md as bounded runtime policy metadata."""
    candidates = [Path(path).expanduser().resolve()] if path else ziel_policy_candidate_paths()
    first_candidate = candidates[0]
    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            text = candidate.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            return _fallback_status("unavailable", candidate, reason=str(exc)[:300])
        content_hash = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()
        principles = parse_ziel_principles(text)
        title = _document_title(text) or "Ziel"
        return {
            "status": "loaded",
            "loaded": True,
            "source_path": str(candidate),
            "title": title,
            "content_hash": content_hash,
            "short_hash": content_hash[:16],
            "principle_count": len(principles),
            "principles": principles,
            "summary": build_ziel_policy_summary(principles),
            "guardrails": list(GUARDRAIL_STATEMENTS),
            "bounded_retry_limit": BOUNDED_RETRY_LIMIT,
            "secrets_returned": False,
            "writes_memory": False,
            "external_calls_allowed": False,
            "fake_success": False,
        }
    return _fallback_status("missing", first_candidate, reason="Ziel.md not found in local workspace candidates.")


def ziel_policy_status() -> dict[str, Any]:
    """Return runtime/status-safe Ziel metadata without full document text."""
    policy = load_ziel_policy()
    return compact_ziel_policy(policy, include_summary=True)


def compact_ziel_policy(policy: Mapping[str, Any] | None = None, *, include_summary: bool = True) -> dict[str, Any]:
    """Return a compact status/context shape that omits full principle text."""
    source = dict(policy or load_ziel_policy())
    result = {
        "status": source.get("status") or "unknown",
        "loaded": bool(source.get("loaded")),
        "source_path": str(source.get("source_path") or ""),
        "title": str(source.get("title") or ""),
        "content_hash": str(source.get("content_hash") or ""),
        "short_hash": str(source.get("short_hash") or ""),
        "principle_count": int(source.get("principle_count") or 0),
        "principle_titles": [str(item.get("title") or "") for item in (source.get("principles") or []) if isinstance(item, Mapping)],
        "guardrails": list(source.get("guardrails") or GUARDRAIL_STATEMENTS),
        "bounded_retry_limit": int(source.get("bounded_retry_limit") or BOUNDED_RETRY_LIMIT),
        "secrets_returned": False,
        "external_calls_allowed": False,
        "writes_memory": False,
        "fake_success": False,
    }
    if include_summary:
        result["summary"] = str(source.get("summary") or "")
    if source.get("reason"):
        result["reason"] = str(source.get("reason") or "")
    return result


def ziel_policy_context_block(policy: Mapping[str, Any] | None = None) -> str:
    """Return short prompt-safe Ziel context for ordinary chat/planning."""
    source = dict(policy or load_ziel_policy())
    if not source.get("loaded"):
        return (
            f"Ziel policy: {source.get('status') or 'missing'} ({source.get('source_path') or ziel_policy_path()}); "
            "guardrails remain enforced by default: ToolBridge, exact Akkoord approval, no-secrets, bounded retries, local-only OODA/Hippocampus, and connector/VPS gates."
        )
    summary = str(source.get("summary") or "").strip()
    short_hash = str(source.get("short_hash") or "")
    guardrails = list(source.get("guardrails") or GUARDRAIL_STATEMENTS)
    lines = [
        f"Ziel policy loaded: {source.get('principle_count')} principles, hash={short_hash}.",
        f"Summary: {summary}",
        "Guardrails:",
    ]
    for guardrail in guardrails:
        lines.append(f"- {guardrail}")
    return "\n".join(lines)


def ziel_guardrail_note(policy: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return a tiny reusable tool-output note for connector/VPS envelopes."""
    source = dict(policy or load_ziel_policy())
    return {
        "status": source.get("status") or "unknown",
        "loaded": bool(source.get("loaded")),
        "short_hash": str(source.get("short_hash") or ""),
        "principle_count": int(source.get("principle_count") or 0),
        "guardrail": "Ziel permits bounded retries/creativity only inside ToolBridge, exact Akkoord approval, no-secrets, no-loop, local-only OODA/Hippocampus, and connector/VPS gates.",
        "bounded_retry_limit": int(source.get("bounded_retry_limit") or BOUNDED_RETRY_LIMIT),
    }


def build_ziel_policy_summary(principles: list[Mapping[str, Any]]) -> str:
    """Build a compact safe summary from principle titles without full document leakage."""
    titles = [str(item.get("title") or "").strip() for item in principles if str(item.get("title") or "").strip()]
    title_text = "; ".join(titles[:9])
    if title_text:
        return (
            "Ziel principles emphasize local embodiment, ToolBridge rejection as protective signal, persistent identity, bounded micro-retries, lateral creativity, goal hierarchy, loop/frustration stopping, and safe self-synthesis. "
            f"Titles: {title_text}."
        )[:900]
    return (
        "Ziel policy is expected to guide local-first behavior while preserving ToolBridge, approval, no-secrets, bounded retry, and local-only memory/reflection guardrails."
    )


def _fallback_status(status: str, path: Path, *, reason: str) -> dict[str, Any]:
    return {
        "status": status,
        "loaded": False,
        "source_path": str(path),
        "title": "Ziel",
        "content_hash": "",
        "short_hash": "",
        "principle_count": 0,
        "principles": [],
        "summary": build_ziel_policy_summary([]),
        "guardrails": list(GUARDRAIL_STATEMENTS),
        "bounded_retry_limit": BOUNDED_RETRY_LIMIT,
        "reason": reason,
        "secrets_returned": False,
        "writes_memory": False,
        "external_calls_allowed": False,
        "fake_success": False,
    }


def _finalize_principle(principle: dict[str, Any]) -> None:
    principle["text"] = _clean_markdown(str(principle.get("text") or ""))[:MAX_PRINCIPLE_TEXT_CHARS]
    principle["title"] = _clean_markdown(str(principle.get("title") or ""))[:160]


def _clean_markdown(value: str) -> str:
    text = INLINE_MARKDOWN_RE.sub("", str(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text.strip(" -")


def _document_title(text: str) -> str:
    for line in str(text or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return _clean_markdown(stripped.removeprefix("# "))
    return ""
