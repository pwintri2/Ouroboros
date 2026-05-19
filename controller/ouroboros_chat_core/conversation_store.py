from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from .persona_store import now_iso, safe_slug


class ConversationStore:
    def __init__(self, directory: Path):
        self.directory = directory

    def list(self, *, persona_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        self.directory.mkdir(parents=True, exist_ok=True)
        conversations = []
        for path in sorted(self.directory.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
            data = self._read(path)
            if not data or data.get("archived"):
                continue
            if persona_id and data.get("persona_id") != safe_slug(persona_id):
                continue
            summary = {key: data.get(key) for key in ("id", "persona_id", "title", "created_at", "updated_at")}
            summary["message_count"] = len(data.get("messages") or [])
            conversations.append(summary)
            if len(conversations) >= limit:
                break
        return conversations

    def get(self, conversation_id: str) -> dict[str, Any]:
        clean_id = safe_slug(conversation_id)
        path = self._path(clean_id)
        if not path.exists():
            raise KeyError(clean_id)
        data = self._read(path)
        if not data:
            raise KeyError(clean_id)
        return data

    def create(self, *, persona_id: str, title: str = "New thread", conversation_id: str | None = None) -> dict[str, Any]:
        clean_id = safe_slug(conversation_id or f"conv-{uuid.uuid4().hex[:10]}", "conversation")
        now = now_iso()
        data = {
            "id": clean_id,
            "persona_id": safe_slug(persona_id or "ouroboros"),
            "title": (title or "New thread")[:160],
            "messages": [],
            "archived": False,
            "created_at": now,
            "updated_at": now,
        }
        self._write(data)
        return data

    def upsert_message(self, *, conversation_id: str | None, persona_id: str, user_content: str, assistant_content: str, title: str = "") -> dict[str, Any]:
        if conversation_id:
            try:
                data = self.get(conversation_id)
            except KeyError:
                data = self.create(persona_id=persona_id, title=title or user_content[:48], conversation_id=conversation_id)
        else:
            data = self.create(persona_id=persona_id, title=title or user_content[:48])
        now = now_iso()
        data.setdefault("messages", [])
        data["messages"].append({"id": f"msg-{uuid.uuid4().hex[:10]}", "role": "user", "content": user_content, "created_at": now})
        data["messages"].append({"id": f"msg-{uuid.uuid4().hex[:10]}", "role": "assistant", "content": assistant_content, "created_at": now})
        if not data.get("title") or data.get("title") == "New thread":
            data["title"] = (title or user_content[:48] or "New thread")[:160]
        data["updated_at"] = now
        self._write(data)
        return data

    def update(self, conversation_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = self.get(conversation_id)
        for key in ("title", "archived"):
            if key in payload:
                data[key] = payload[key]
        data["updated_at"] = now_iso()
        self._write(data)
        return data

    def delete(self, conversation_id: str, *, hard: bool = False) -> dict[str, Any]:
        clean_id = safe_slug(conversation_id)
        path = self._path(clean_id)
        if not path.exists():
            raise KeyError(clean_id)
        if hard:
            path.unlink()
            return {"status": "deleted", "id": clean_id}
        data = self.get(clean_id)
        data["archived"] = True
        data["updated_at"] = now_iso()
        self._write(data)
        return {"status": "archived", "conversation": data}

    def _path(self, conversation_id: str) -> Path:
        return (self.directory / f"{safe_slug(conversation_id)}.json").resolve()

    def _read(self, path: Path) -> dict[str, Any] | None:
        try:
            path.relative_to(self.directory.resolve())
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _write(self, data: dict[str, Any]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self._path(str(data["id"]))
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(path)

