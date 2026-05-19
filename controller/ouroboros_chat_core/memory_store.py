from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from .persona_store import now_iso, safe_slug


SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?i)\b(api[_-]?key|client[_-]?secret|secret|token|password|passwd|authorization|oauth)\b"
        r"\s*[:=]\s*['\"]?[A-Za-z0-9_./+=:@\-]{8,}"
    ),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{12,}"),
)


def contains_secret_like(value: Any) -> bool:
    if isinstance(value, str):
        return any(pattern.search(value) for pattern in SECRET_PATTERNS)
    if isinstance(value, dict):
        return any(contains_secret_like(key) or contains_secret_like(item) for key, item in value.items())
    if isinstance(value, (list, tuple, set)):
        return any(contains_secret_like(item) for item in value)
    return False


class MemoryStore:
    def __init__(self, path: Path):
        self.path = path

    def list(self, *, persona_id: str | None = None, scope: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        items = self._load()
        if persona_id:
            clean_id = safe_slug(persona_id)
            items = [item for item in items if item.get("persona_id") in {clean_id, None}]
        if scope:
            items = [item for item in items if item.get("scope") == scope]
        return sorted(items, key=lambda item: item.get("updated_at", ""), reverse=True)[: max(1, min(limit, 500))]

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        if contains_secret_like(payload):
            raise ValueError("Memory content appears to contain a secret, token, password, or bearer credential.")
        now = now_iso()
        item = {
            "id": safe_slug(str(payload.get("id") or f"mem-{uuid.uuid4().hex[:10]}"), "memory"),
            "persona_id": safe_slug(str(payload.get("persona_id"))) if payload.get("persona_id") else None,
            "conversation_id": safe_slug(str(payload.get("conversation_id"))) if payload.get("conversation_id") else None,
            "scope": str(payload.get("scope") or "persona"),
            "content": str(payload.get("content") or "").strip()[:4000],
            "tags": [str(tag).strip()[:80] for tag in (payload.get("tags") or [])[:12] if str(tag).strip()],
            "importance": max(1, min(int(payload.get("importance") or 3), 5)),
            "created_at": now,
            "updated_at": now,
        }
        if not item["content"]:
            raise ValueError("Memory content is empty.")
        items = [existing for existing in self._load() if existing.get("id") != item["id"]]
        items.append(item)
        self._save(items)
        return item

    def update(self, memory_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if contains_secret_like(payload):
            raise ValueError("Memory update appears to contain a secret, token, password, or bearer credential.")
        clean_id = safe_slug(memory_id)
        items = self._load()
        for index, item in enumerate(items):
            if item.get("id") != clean_id:
                continue
            updated = {**item}
            for key in ("content", "scope", "persona_id", "conversation_id", "tags", "importance"):
                if key in payload:
                    updated[key] = payload[key]
            updated["updated_at"] = now_iso()
            items[index] = updated
            self._save(items)
            return updated
        raise KeyError(clean_id)

    def delete(self, memory_id: str) -> dict[str, Any]:
        clean_id = safe_slug(memory_id)
        items = self._load()
        kept = [item for item in items if item.get("id") != clean_id]
        if len(kept) == len(items):
            raise KeyError(clean_id)
        self._save(kept)
        return {"status": "deleted", "id": clean_id}

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return []
        items = data.get("items", []) if isinstance(data, dict) and isinstance(data.get("items"), list) else []
        return [item for item in items if isinstance(item, dict) and not contains_secret_like(item)]

    def _save(self, items: list[dict[str, Any]]) -> None:
        if contains_secret_like(items):
            raise ValueError("Memory store write blocked because content appears to contain a secret.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"version": 1, "items": items}, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.path)
