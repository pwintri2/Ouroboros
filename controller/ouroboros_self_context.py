"""Persistent self-context for Ouroboros cockpit chats and IDE integration.

The cockpit can send history, but browser/app state is not a reliable memory
boundary. This module stores a small server-side conversation trace and a
machine-readable view of neighbouring agent workspaces, then injects that into
provider calls so Gemini/Ollama do not start from an empty room each turn.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.request
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    from controller.ouroboros_paths import roo_code_path
except Exception:
    def roo_code_path() -> Path:
        configured = os.getenv("WINTRIP_ROO_CODE_PATH") or os.getenv("WINTRIP_ROO_PATH") or DEFAULT_ROO_PATH
        return Path(configured).expanduser().resolve()

try:
    from controller.safe_shell import workspace_root
except Exception:
    def workspace_root() -> Path:
        configured = os.getenv("WINTRIP_WORKSPACE") or os.getenv("WORKSPACE_ROOT") or "/workspace"
        root = Path(configured)
        if not root.exists():
            root = Path.cwd()
        return root.resolve()

try:
    from controller.ziel_policy import compact_ziel_policy, load_ziel_policy, ziel_policy_context_block
except Exception:
    def load_ziel_policy(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"status": "unavailable", "loaded": False, "fake_success": False}

    def compact_ziel_policy(policy: Mapping[str, Any] | None = None, *, include_summary: bool = True) -> dict[str, Any]:
        return {"status": "unavailable", "loaded": False, "fake_success": False}

    def ziel_policy_context_block(policy: Mapping[str, Any] | None = None) -> str:
        return "Ziel policy unavailable; default guardrails remain enforced."


APPROVAL_PHRASE = "Akkoord"
DEFAULT_RUFLO_PATH = "/home/pwintri2/ruflo"
DEFAULT_CODEX_PATH = "/home/pwintri2/Codex"
DEFAULT_ROO_PATH = "/home/pwintri2/Roo-code"
MAX_TURNS_PER_CONVERSATION = 40
MAX_CONTEXT_TURNS = 10
MAX_LESSONS = 160
MAX_CONTEXT_LESSONS = 5
MAX_TEXT_CHARS = 4000
WORD_RE = re.compile(r"[A-Za-z0-9_+./:-]{3,}")
SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)(api[_-]?key|token|secret|password|passwd|bearer)\s*[:=]\s*['\"]?[^'\"\s]{8,}"),
    re.compile(r"(?i)authorization:\s*bearer\s+[A-Za-z0-9._\-]+"),
)


def self_context_state_path() -> Path:
    return (workspace_root() / ".secrets" / "ouroboros_self_context.json").resolve()


def ruflo_path() -> Path:
    return Path(os.getenv("WINTRIP_RUFLO_PATH") or DEFAULT_RUFLO_PATH).expanduser().resolve()


def codex_path() -> Path:
    return Path(os.getenv("WINTRIP_CODEX_PATH") or DEFAULT_CODEX_PATH).expanduser().resolve()


def roo_path() -> Path:
    return roo_code_path()


def build_chat_context(
    prompt: str,
    provider: str,
    model: str,
    system_prompt: str | None = None,
    history: Sequence[Mapping[str, Any]] | None = None,
    conversation_id: str | None = None,
) -> dict[str, Any]:
    """Return prompt/system/history enriched with durable Ouroboros context."""
    cid = normalize_conversation_id(conversation_id, provider, model)
    state = _load_state()
    conversation = _conversation(state, cid)
    recent_server_history = _recent_history_messages(conversation, limit=MAX_CONTEXT_TURNS)
    incoming_history = _sanitize_history(history or [])
    merged_history = _merge_history(recent_server_history, incoming_history)
    lessons = _relevant_lessons(prompt, state.get("lessons") or [], limit=MAX_CONTEXT_LESSONS)
    ziel_policy = load_ziel_policy()
    block = _context_block(prompt=prompt, conversation_id=cid, conversation=conversation, lessons=lessons, ziel_policy=ziel_policy)
    enriched_system_prompt = _join_system_prompt(system_prompt, block)
    return {
        "conversation_id": cid,
        "prompt": prompt,
        "system_prompt": enriched_system_prompt,
        "history": merged_history,
        "server_history_count": len(recent_server_history),
        "client_history_count": len(incoming_history),
        "self_context": {
            "enabled": True,
            "state_path": str(self_context_state_path()),
            "conversation_id": cid,
            "turn_count": len(conversation.get("turns") or []),
            "server_history_count": len(recent_server_history),
            "lesson_count": len(state.get("lessons") or []),
            "matched_lesson_count": len(lessons),
            "ziel_policy": compact_ziel_policy(ziel_policy),
            "ouroboros_agent_types": get_ouroboros_agent_types_status(),
            "ruflo": get_ruflo_status(),
        },
    }


def record_chat_turn(
    prompt: str,
    response: str,
    provider: str,
    model: str,
    conversation_id: str | None = None,
    status: str = "success",
) -> dict[str, Any]:
    """Persist one user/assistant exchange without storing secrets verbatim."""
    cid = normalize_conversation_id(conversation_id, provider, model)
    state = _load_state()
    conversation = _conversation(state, cid)
    now = time.time()
    turn = {
        "at": now,
        "provider": str(provider or ""),
        "model": str(model or ""),
        "status": str(status or ""),
        "user": _redact(_clip(prompt)),
        "assistant": _redact(_clip(response)),
    }
    turns = list(conversation.get("turns") or [])
    turns.append(turn)
    conversation["turns"] = turns[-MAX_TURNS_PER_CONVERSATION:]
    conversation["updated_at"] = now
    conversation["summary"] = _conversation_summary(conversation["turns"])
    _remember_lesson(state, cid, turn)
    state["updated_at"] = now
    state["conversations"][cid] = conversation
    _save_state(state)
    return {
        "status": "stored",
        "conversation_id": cid,
        "turn_count": len(conversation["turns"]),
        "state_path": str(self_context_state_path()),
        "fake_success": False,
    }


def get_self_context_status() -> dict[str, Any]:
    state = _load_state()
    conversations = state.get("conversations") or {}
    latest = sorted(
        (
            {
                "conversation_id": key,
                "turn_count": len((value or {}).get("turns") or []),
                "updated_at": (value or {}).get("updated_at"),
                "summary": (value or {}).get("summary", ""),
            }
            for key, value in conversations.items()
            if isinstance(value, dict)
        ),
        key=lambda item: item.get("updated_at") or 0,
        reverse=True,
    )[:8]
    return {
        "status": "online",
        "enabled": True,
        "state_path": str(self_context_state_path()),
        "conversation_count": len(conversations),
        "lesson_count": len(state.get("lessons") or []),
        "recent_lessons": list(state.get("lessons") or [])[:8],
        "latest_conversations": latest,
        "ziel_policy": compact_ziel_policy(load_ziel_policy()),
        "ouroboros_agent_types": get_ouroboros_agent_types_status(),
        "ruflo": get_ruflo_status(),
        "fake_success": False,
    }


def get_ouroboros_agent_types_status() -> dict[str, Any]:
    root = workspace_root() / ".agents" / "agent_types"
    types: list[dict[str, Any]] = []
    if root.exists():
        for type_dir in sorted(path for path in root.iterdir() if path.is_dir()):
            docs = _names(type_dir, patterns=("*.md",), limit=30)
            primary = type_dir / "Ziel.md"
            types.append(
                {
                    "id": type_dir.name,
                    "docs": docs,
                    "primary_doc": str(primary) if primary.exists() else "",
                    "has_ziel": primary.exists(),
                }
            )
    return {
        "status": "online" if types else "empty",
        "root": str(root),
        "types": types,
        "type_count": len(types),
        "fake_success": False,
    }


def get_ruflo_status() -> dict[str, Any]:
    bridge = _bridge_get("/ruflo/status")
    if bridge:
        bridge["via_bridge"] = True
        return bridge
    return _local_ruflo_status(via_bridge=False)


def normalize_conversation_id(conversation_id: str | None, provider: str, model: str) -> str:
    raw = str(conversation_id or "").strip()
    if not raw:
        raw = f"cockpit:{provider or 'provider'}:{model or 'model'}"
    slug = re.sub(r"[^A-Za-z0-9_.:-]+", "-", raw)[:100].strip("-")
    return slug or "cockpit"


def _context_block(
    prompt: str,
    conversation_id: str,
    conversation: dict[str, Any],
    lessons: Sequence[Mapping[str, Any]] | None = None,
    ziel_policy: Mapping[str, Any] | None = None,
) -> str:
    recent = list(conversation.get("turns") or [])[-MAX_CONTEXT_TURNS:]
    lines: list[str] = [
        "Ouroboros self-context:",
        "- Je bent Wintrip/Ouroboros, een lokaal-first systeem op Philip zijn laptop.",
        f"- WintripAI workspace: {workspace_root()}",
        f"- Ruflo workspace: {ruflo_path()}",
        f"- Codex pad: {codex_path()}",
        f"- Roo pad: {roo_path()}",
        f"- Conversation id: {conversation_id}",
        "- Gedraag je continu: gebruik vorige server-side beurten als context, ook als de client geen history meestuurt.",
        "- Behandel ruflo, Roo en Codex als IDE/agent-werkruimtes die samen aan WintripAI mogen werken.",
    ]
    ziel_block = ziel_policy_context_block(ziel_policy)
    if ziel_block:
        lines.append(ziel_block)
    summary = str(conversation.get("summary") or "").strip()
    if summary:
        lines.append(f"- Samenvatting tot nu toe: {summary}")
    if lessons:
        lines.append("Relevante lessen:")
        for lesson in lessons:
            text = _clip(lesson.get("text", ""), 420).replace("\n", " ")
            keywords = ", ".join(list(lesson.get("keywords") or [])[:8])
            lines.append(f"  - {text}" + (f" [keywords: {keywords}]" if keywords else ""))
    agent_types = get_ouroboros_agent_types_status()
    if agent_types.get("types"):
        labels = []
        for item in (agent_types.get("types") or [])[:8]:
            if isinstance(item, Mapping):
                docs = ", ".join(list(item.get("docs") or [])[:4])
                labels.append(f"{item.get('id')}({docs})")
        if labels:
            lines.append(f"Ouroboros agent types: {', '.join(labels)}")
    if recent:
        lines.append("Recente server-side beurten:")
        for turn in recent:
            lines.append(f"  user: {_clip(turn.get('user', ''), 500)}")
            assistant = _clip(turn.get("assistant", ""), 500)
            if assistant:
                lines.append(f"  assistant: {assistant}")
    ruflo = get_ruflo_status()
    if ruflo.get("exists"):
        agents = ", ".join((ruflo.get("agents") or [])[:6])
        plugins = ", ".join((ruflo.get("plugins") or [])[:8])
        lines.append(f"Ruflo zichtbaar: agents=[{agents}], plugins=[{plugins}]")
    else:
        lines.append(f"Ruflo nog niet zichtbaar vanuit backend: {ruflo.get('reason') or ruflo.get('path')}")
    return "\n".join(lines)


def _join_system_prompt(system_prompt: str | None, context_block: str) -> str:
    existing = str(system_prompt or "").strip()
    if existing:
        return f"{existing}\n\n[{context_block}]"
    return context_block


def _recent_history_messages(conversation: dict[str, Any], limit: int) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for turn in list(conversation.get("turns") or [])[-limit:]:
        user = str(turn.get("user") or "").strip()
        assistant = str(turn.get("assistant") or "").strip()
        if user:
            messages.append({"role": "user", "content": _clip(user, 1200)})
        if assistant:
            messages.append({"role": "assistant", "content": _clip(assistant, 1200)})
    return messages


def _merge_history(server_history: list[dict[str, str]], client_history: list[dict[str, str]]) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in [*server_history, *client_history]:
        role = str(item.get("role") or "user")
        content = str(item.get("content") or "")
        key = hashlib.sha256(f"{role}\0{content}".encode("utf-8", errors="ignore")).hexdigest()
        if content and key not in seen:
            merged.append({"role": role, "content": _clip(_redact(content), 1200)})
            seen.add(key)
    return merged[-(MAX_CONTEXT_TURNS * 2) :]


def _sanitize_history(history: Sequence[Mapping[str, Any]]) -> list[dict[str, str]]:
    sanitized: list[dict[str, str]] = []
    for item in history:
        if not isinstance(item, Mapping):
            continue
        role = str(item.get("role") or "user")
        if role not in {"system", "user", "assistant", "tool"}:
            role = "user"
        content = _clip(_redact(str(item.get("content") or "")), 1200)
        if content:
            sanitized.append({"role": role, "content": content})
    return sanitized[-20:]


def _conversation(state: dict[str, Any], conversation_id: str) -> dict[str, Any]:
    conversations = state.setdefault("conversations", {})
    conversation = conversations.get(conversation_id)
    if not isinstance(conversation, dict):
        conversation = {"turns": [], "summary": "", "created_at": time.time(), "updated_at": time.time()}
        conversations[conversation_id] = conversation
    return conversation


def _remember_lesson(state: dict[str, Any], conversation_id: str, turn: Mapping[str, Any]) -> None:
    text = _lesson_text(turn.get("user", ""), turn.get("assistant", ""))
    keywords = _keywords(text, limit=18)
    if not text.strip() or len(keywords) < 2:
        return

    digest = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()
    lesson = {
        "id": digest[:16],
        "at": turn.get("at") or time.time(),
        "conversation_id": conversation_id,
        "provider": str(turn.get("provider") or ""),
        "model": str(turn.get("model") or ""),
        "status": str(turn.get("status") or ""),
        "keywords": keywords,
        "text": _redact(_clip(text, 900)),
    }
    lessons = [item for item in list(state.get("lessons") or []) if item.get("id") != lesson["id"]]
    state["lessons"] = [lesson, *lessons][:MAX_LESSONS]


def _lesson_text(prompt: Any, response: Any) -> str:
    prompt_text = _clip(_redact(prompt), 700).strip()
    response_text = _clip(_redact(response), 700).strip()
    if prompt_text and response_text:
        return f"User: {prompt_text}\nAssistant: {response_text}"
    return prompt_text or response_text


def _relevant_lessons(prompt: str, lessons: Sequence[Any], limit: int) -> list[dict[str, Any]]:
    query_terms = set(_keywords(prompt, limit=24))
    if not query_terms:
        return []
    ranked: list[tuple[int, float, dict[str, Any]]] = []
    for raw in lessons:
        if not isinstance(raw, Mapping):
            continue
        text = str(raw.get("text") or "").lower()
        keywords = {str(item).lower() for item in raw.get("keywords") or []}
        score = sum(3 for term in query_terms if term in keywords)
        score += sum(1 for term in query_terms if term in text)
        if score <= 0:
            continue
        try:
            at = float(raw.get("at") or 0)
        except (TypeError, ValueError):
            at = 0.0
        ranked.append((score, at, dict(raw)))
    ranked.sort(key=lambda row: (row[0], row[1]), reverse=True)
    return [item for _score, _at, item in ranked[: max(1, min(limit, MAX_CONTEXT_LESSONS))]]


def _keywords(text: Any, limit: int = 18) -> list[str]:
    stopwords = {
        "the",
        "and",
        "for",
        "with",
        "een",
        "het",
        "dat",
        "dit",
        "van",
        "voor",
        "met",
        "zijn",
        "naar",
        "als",
        "wat",
        "wie",
        "waar",
        "hoe",
        "user",
        "assistant",
    }
    words: list[str] = []
    seen: set[str] = set()
    for match in WORD_RE.findall(str(text or "").lower()):
        word = match.strip("._:-/")
        if len(word) < 3 or word in stopwords or word in seen:
            continue
        seen.add(word)
        words.append(word)
        if len(words) >= limit:
            break
    return words


def _conversation_summary(turns: list[dict[str, Any]]) -> str:
    recent = turns[-6:]
    parts = []
    for turn in recent:
        user = _clip(turn.get("user", ""), 160)
        if user:
            parts.append(user)
    return " | ".join(parts)[-1200:]


def _load_state() -> dict[str, Any]:
    path = self_context_state_path()
    if not path.exists():
        return {"version": 1, "updated_at": None, "conversations": {}, "lessons": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "updated_at": None, "conversations": {}, "lessons": []}
    if not isinstance(data, dict):
        return {"version": 1, "updated_at": None, "conversations": {}, "lessons": []}
    data.setdefault("version", 1)
    data.setdefault("conversations", {})
    data.setdefault("lessons", [])
    return data


def _save_state(state: dict[str, Any]) -> None:
    path = self_context_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)
    path.chmod(0o600)


def _clip(value: Any, limit: int = MAX_TEXT_CHARS) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[truncated]"


def _redact(text: str) -> str:
    redacted = str(text or "")
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(_redact_secret_match, redacted)
    return redacted


def _redact_secret_match(match: re.Match[str]) -> str:
    raw = match.group(0)
    for separator in (":", "="):
        if separator in raw:
            return f"{raw.split(separator, 1)[0]}{separator} [REDACTED]"
    return "[REDACTED]"


def _local_ruflo_status(via_bridge: bool) -> dict[str, Any]:
    root = ruflo_path()
    if not root.exists():
        return {
            "status": "missing",
            "exists": False,
            "path": str(root),
            "wintrip_path": str(workspace_root()),
            "reason": "Ruflo path is not visible from this process. Mount it or use the host bridge.",
            "via_bridge": via_bridge,
            "fake_success": False,
        }
    package = _read_json(root / "package.json")
    agents = _names(root / "agents", patterns=("*.yaml", "*.yml", "*.md"), limit=20)
    if not agents:
        agents = _names(root / ".claude" / "agents", patterns=("*.md",), limit=20)
    plugins = _dir_names(root / "plugins", limit=40)
    skills = _dir_names(root / ".agents" / "skills", limit=30)
    return {
        "status": "online",
        "exists": True,
        "path": str(root),
        "wintrip_path": str(workspace_root()),
        "package": {
            "name": package.get("name", ""),
            "version": package.get("version", ""),
            "description": package.get("description", "")[:240],
        },
        "agents": agents,
        "plugins": plugins,
        "skills": skills,
        "mcp": {
            "claude_mcp": str(root / ".claude" / "mcp.json"),
            "v3_mcp": str(root / "v3" / "mcp"),
        },
        "ide_context_files": [
            str(workspace_root() / "OUROBOROS_IDE_CONTEXT.md"),
            str(root / "WINTRIPAI_CONTEXT.md"),
        ],
        "via_bridge": via_bridge,
        "fake_success": False,
    }


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _names(root: Path, patterns: tuple[str, ...], limit: int) -> list[str]:
    if not root.exists():
        return []
    names: list[str] = []
    for pattern in patterns:
        for path in sorted(root.glob(pattern)):
            if path.is_file():
                names.append(path.stem)
            if len(names) >= limit:
                return names
    return names


def _dir_names(root: Path, limit: int) -> list[str]:
    if not root.exists():
        return []
    return [path.name for path in sorted(root.iterdir()) if path.is_dir() and not path.name.startswith(".")][:limit]


def _bridge_get(path: str) -> dict[str, Any] | None:
    base_url = str(os.getenv("WINTRIP_RCLONE_BRIDGE_URL") or "").rstrip("/")
    token_path = os.getenv("WINTRIP_RCLONE_BRIDGE_TOKEN_PATH")
    if not base_url or not token_path:
        return None
    try:
        token = Path(token_path).read_text(encoding="utf-8").strip()
        request = urllib.request.Request(f"{base_url}{path}", headers={"X-Ouroboros-Bridge-Token": token})
        with urllib.request.urlopen(request, timeout=4) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        return None
