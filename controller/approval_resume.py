"""Persistent resume buffer for approval-gated cockpit actions."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Mapping


APPROVAL_PHRASE = "Akkoord"
DEFAULT_TTL_SECONDS = 15 * 60
_LOCK = threading.Lock()


def extract_inline_approval(prompt: object, *, phrase: str = APPROVAL_PHRASE) -> dict[str, Any]:
    """Return an exact Akkoord prefix without weakening the approval phrase."""

    text = str(prompt or "").strip()
    if text == phrase:
        return {"approval": phrase, "prompt": "", "resume_only": True}
    if text.startswith(phrase):
        rest = text[len(phrase) :]
        if rest and rest[0] in {" ", "\t", ":", "-", ","}:
            clean = rest.strip(" \t:,-")
            if clean:
                return {"approval": phrase, "prompt": clean, "resume_only": False}
    return {"approval": "", "prompt": str(prompt or ""), "resume_only": False}


def remember_pending_approval(
    *,
    conversation_id: object,
    prompt: object,
    provider: object = "",
    model: object = "",
    requested_provider: object = "",
    route: object = "",
    blocked_tools: list[str] | None = None,
    ttl_seconds: int = DEFAULT_TTL_SECONDS,
) -> dict[str, Any]:
    clean_prompt = " ".join(str(prompt or "").replace("\x00", " ").split())
    key = _key(conversation_id)
    if not key or not clean_prompt or clean_prompt == APPROVAL_PHRASE:
        return {"status": "skipped", "reason": "No resumable prompt.", "fake_success": False}
    record = {
        "status": "waiting_for_approval",
        "conversation_id": key,
        "prompt": clean_prompt,
        "provider": str(provider or ""),
        "requested_provider": str(requested_provider or provider or ""),
        "model": str(model or ""),
        "route": str(route or ""),
        "blocked_tools": list(blocked_tools or []),
        "created_at": time.time(),
        "expires_at": time.time() + max(30, int(ttl_seconds or DEFAULT_TTL_SECONDS)),
        "approval_phrase": APPROVAL_PHRASE,
        "fake_success": False,
    }
    with _LOCK:
        pending = _load_pending_unlocked()
        _prune_expired_unlocked(pending)
        pending[key] = record
        _save_pending_unlocked(pending)
    return public_pending_view(record)


def consume_pending_approval(conversation_id: object) -> dict[str, Any] | None:
    key = _key(conversation_id)
    now = time.time()
    with _LOCK:
        pending = _load_pending_unlocked()
        record = pending.pop(key, None)
        _prune_expired_unlocked(pending, now=now)
        _save_pending_unlocked(pending)
    if not record:
        return None
    if float(record.get("expires_at") or 0) < now:
        return None
    return dict(record)


def clear_pending_approval(conversation_id: object) -> None:
    key = _key(conversation_id)
    if not key:
        return
    with _LOCK:
        pending = _load_pending_unlocked()
        pending.pop(key, None)
        _save_pending_unlocked(pending)


def pending_approval_status(conversation_id: object) -> dict[str, Any]:
    key = _key(conversation_id)
    with _LOCK:
        pending = _load_pending_unlocked()
        _prune_expired_unlocked(pending)
        _save_pending_unlocked(pending)
        record = dict(pending.get(key) or {})
    if not record:
        return {"status": "none", "conversation_id": key, "fake_success": False}
    return public_pending_view(record)


def pending_approval_overview(limit: int = 20) -> dict[str, Any]:
    with _LOCK:
        pending = _load_pending_unlocked()
        _prune_expired_unlocked(pending)
        _save_pending_unlocked(pending)
        records = sorted(pending.values(), key=lambda item: float(item.get("created_at") or 0), reverse=True)
    return {
        "status": "online",
        "path": str(pending_approval_state_path()),
        "count": len(records),
        "records": [public_pending_view(record) for record in records[: max(1, min(int(limit or 20), 100))]],
        "secrets_returned": False,
        "fake_success": False,
    }


def store_pending_from_result(
    result: Mapping[str, Any],
    *,
    conversation_id: object,
    prompt: object,
    provider: object = "",
    model: object = "",
    requested_provider: object = "",
) -> dict[str, Any] | None:
    if _result_requires_approval(result):
        trace = result.get("source_trace") if isinstance(result.get("source_trace"), dict) else {}
        blocked = _string_list(trace.get("tools_blocked")) or _string_list(result.get("blocked_tools"))
        return remember_pending_approval(
            conversation_id=conversation_id,
            prompt=prompt,
            provider=provider,
            model=model,
            requested_provider=requested_provider,
            route=result.get("route") or "",
            blocked_tools=blocked,
        )
    if str(result.get("status") or "").lower() in {"success", "completed", "opened"}:
        clear_pending_approval(conversation_id)
    return None


def public_pending_view(record: Mapping[str, Any]) -> dict[str, Any]:
    prompt = str(record.get("prompt") or "")
    remaining = max(0, int(float(record.get("expires_at") or 0) - time.time()))
    return {
        "status": "waiting_for_approval",
        "conversation_id": str(record.get("conversation_id") or ""),
        "route": str(record.get("route") or ""),
        "blocked_tools": _string_list(record.get("blocked_tools")),
        "approval_phrase": APPROVAL_PHRASE,
        "resume_hint": "Typ exact Akkoord als volgend chatbericht om deze geblokkeerde actie te hervatten.",
        "prompt_preview": prompt[:240],
        "ttl_seconds_remaining": remaining,
        "fake_success": False,
    }


def _result_requires_approval(result: Mapping[str, Any]) -> bool:
    if bool(result.get("approval_required")):
        return True
    trace = result.get("source_trace")
    if isinstance(trace, dict) and bool(trace.get("approval_required")):
        return True
    return str(result.get("status") or "").lower() in {"blocked", "approval_required"} and bool(
        _string_list(result.get("blocked_tools")) or _string_list((trace or {}).get("tools_blocked") if isinstance(trace, dict) else None)
    )


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    output: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = str(item or "").strip()
        if text and text not in seen:
            output.append(text)
            seen.add(text)
    return output


def _key(value: object) -> str:
    return str(value or "").strip()


def pending_approval_state_path() -> Path:
    configured = os.getenv("WINTRIP_PENDING_APPROVAL_PATH", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    root = Path(os.getenv("WINTRIP_WORKSPACE") or os.getenv("WORKSPACE_ROOT") or Path.cwd()).expanduser().resolve()
    return root / ".secrets" / "agentic_pending_approvals.json"


def _load_pending_unlocked() -> dict[str, dict[str, Any]]:
    path = pending_approval_state_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    raw_records = data.get("pending") if isinstance(data.get("pending"), dict) else data
    pending: dict[str, dict[str, Any]] = {}
    if isinstance(raw_records, dict):
        for key, value in raw_records.items():
            if isinstance(value, dict):
                pending[str(key)] = dict(value)
    return pending


def _save_pending_unlocked(pending: Mapping[str, Mapping[str, Any]]) -> None:
    path = pending_approval_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "updated_at": time.time(),
        "approval_phrase": APPROVAL_PHRASE,
        "pending": {str(key): _public_storage_record(value) for key, value in pending.items()},
        "secrets_returned": False,
    }
    fd, tmp_name = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        Path(tmp_name).replace(path)
        path.chmod(0o600)
    finally:
        try:
            Path(tmp_name).unlink(missing_ok=True)
        except Exception:
            pass


def _public_storage_record(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": "waiting_for_approval",
        "conversation_id": str(value.get("conversation_id") or ""),
        "prompt": str(value.get("prompt") or "")[:2000],
        "provider": str(value.get("provider") or ""),
        "requested_provider": str(value.get("requested_provider") or value.get("provider") or ""),
        "model": str(value.get("model") or ""),
        "route": str(value.get("route") or ""),
        "blocked_tools": _string_list(value.get("blocked_tools")),
        "created_at": float(value.get("created_at") or time.time()),
        "expires_at": float(value.get("expires_at") or (time.time() + DEFAULT_TTL_SECONDS)),
        "approval_phrase": APPROVAL_PHRASE,
        "fake_success": False,
    }


def _prune_expired_unlocked(pending: dict[str, dict[str, Any]], *, now: float | None = None) -> None:
    current = time.time() if now is None else now
    expired = [key for key, value in pending.items() if float(value.get("expires_at") or 0) < current]
    for key in expired:
        pending.pop(key, None)
