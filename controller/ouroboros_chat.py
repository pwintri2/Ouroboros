"""Standalone Ouroboros chat backend routes.

This module is intentionally mount-only: the integrator can include
``ouroboros_chat_router`` or call ``init_ouroboros_chat_routes(app)`` without
changing the existing cockpit routes. Cline context is read-only and meetings
are transcript artifacts only; they never execute Cline, shell, browser, or
write tools.
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
import base64
import copy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from fastapi import APIRouter, HTTPException, Request, UploadFile
try:
    from pydantic import BaseModel, Field
except ModuleNotFoundError:  # pragma: no cover - lightweight unit-test fallback
    _FIELD_MISSING = object()

    class _FallbackField:
        def __init__(self, default: Any = _FIELD_MISSING, default_factory: Callable[[], Any] | None = None):
            self.default = default
            self.default_factory = default_factory

    def Field(default: Any = _FIELD_MISSING, *, default_factory: Callable[[], Any] | None = None, **_kwargs: Any) -> Any:
        return _FallbackField(default=default, default_factory=default_factory)

    class BaseModel:
        def __init__(self, **data: Any):
            annotations: dict[str, Any] = {}
            for cls in reversed(type(self).mro()):
                annotations.update(getattr(cls, "__annotations__", {}))
            for key in annotations:
                if key in data:
                    value = data[key]
                else:
                    field = getattr(type(self), key, _FIELD_MISSING)
                    if isinstance(field, _FallbackField):
                        if field.default_factory is not None:
                            value = field.default_factory()
                        elif field.default is _FIELD_MISSING or field.default is Ellipsis:
                            raise TypeError(f"Missing required field: {key}")
                        else:
                            value = copy.deepcopy(field.default)
                    elif field is _FIELD_MISSING:
                        value = None
                    else:
                        value = copy.deepcopy(field)
                setattr(self, key, value)
            for key, value in data.items():
                if key not in annotations:
                    setattr(self, key, value)

        def model_dump(self) -> dict[str, Any]:
            return dict(self.__dict__)

        def dict(self) -> dict[str, Any]:
            return self.model_dump()
try:
    from fastapi.responses import FileResponse
except Exception:  # pragma: no cover - optional in unit-test fakes
    FileResponse = None  # type: ignore[assignment]

try:
    from fastapi import File as FastAPIFile
except Exception:  # pragma: no cover - FastAPI import compatibility
    FastAPIFile = None  # type: ignore[assignment]

try:
    import multipart as _multipart_probe  # noqa: F401

    _MULTIPART_AVAILABLE = True
except Exception:
    _MULTIPART_AVAILABLE = False

from controller.ouroboros_chat_core.conversation_store import ConversationStore
from controller.ouroboros_chat_core.knowledge_store import KnowledgeStore
from controller.ouroboros_chat_core.memory_store import MemoryStore
from controller.ouroboros_chat_core.persona_store import (
    default_persona as core_default_persona,
    normalize_persona_payload,
)
from controller.ouroboros_chat_core.prompt_assembler import PromptAssembler
from controller.ouroboros_chat_core.tool_registry import enforce_tool_policy, tool_catalog


APPROVAL_PHRASE = "Akkoord"
DEFAULT_PROVIDER = "ollama"
DEFAULT_MODEL = "ouroboros:latest"
MAX_TEXT_CHARS = 16_000
MAX_UPLOAD_BYTES = 20_000_000
MAX_ATTACHMENT_CONTEXT_CHARS = 24_000
TEXT_ATTACHMENT_EXTENSIONS = {
    "txt",
    "md",
    "csv",
    "json",
    "yaml",
    "yml",
    "toml",
    "py",
    "ts",
    "tsx",
    "js",
    "jsx",
    "rs",
    "go",
    "java",
    "c",
    "cc",
    "cpp",
    "h",
    "hpp",
    "css",
    "html",
    "sql",
    "sh",
}
DOCUMENT_ATTACHMENT_EXTENSIONS = TEXT_ATTACHMENT_EXTENSIONS | {"pdf", "docx"}
IMAGE_ATTACHMENT_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
VISION_MODEL_MARKERS = ("llava", "bakllava", "moondream", "minicpm-v", "vision")

CLINE_ROOT = Path("/home/pwintri2/cline")
ALLOWED_CLINE_FILES: tuple[str, ...] = (
    "README.md",
    "README.marketplace.md",
    "docs/cline-overview.mdx",
    "docs/core-workflows/plan-and-act.mdx",
    "docs/core-workflows/task-management.mdx",
    "docs/core-workflows/working-with-files.mdx",
    "docs/core-workflows/checkpoints.mdx",
    "docs/features/subagents.mdx",
    "docs/customization/cline-rules.mdx",
    "docs/customization/hooks.mdx",
    "docs/mcp/mcp-overview.mdx",
    "docs/cli/cli-reference.mdx",
    "docs/cli/agent-teams.mdx",
    "docs/cli/connectors.mdx",
    "docs/sdk/overview.mdx",
    "package.json",
)

SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?i)\b(api[_-]?key|client[_-]?secret|secret|token|password|passwd|authorization|oauth)\b"
        r"\s*[:=]\s*['\"]?[A-Za-z0-9_./+=:@\-]{8,}"
    ),
    re.compile(r"(?i)\bauthorization\s*:\s*bearer\s+[A-Za-z0-9._\-]{12,}"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{12,}"),
    re.compile(r"\b(?:sk|ghp|gho|github_pat|xoxb|xoxp|xoxa|ya29)[-_A-Za-z0-9]{10,}\b"),
    re.compile(r"\b[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\b"),
)

MEETING_FORBIDDEN_TOOL_MARKERS = (
    "cline",
    "shell",
    "safe_shell",
    "browser",
    "write",
    "apply_patch",
    "execute",
    "run_command",
    "run_tests",
    "roo_write",
    "roo_apply",
    "roo_execute",
)


class OuroborosChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=MAX_TEXT_CHARS)
    provider: Optional[str] = Field(default=DEFAULT_PROVIDER, max_length=80)
    model: Optional[str] = Field(default=DEFAULT_MODEL, max_length=160)
    system_prompt: Optional[str] = Field(default=None, max_length=MAX_TEXT_CHARS)
    persona_id: Optional[str] = Field(default=None, max_length=80)
    conversation_id: Optional[str] = Field(default=None, max_length=120)
    thread_id: Optional[str] = Field(default=None, max_length=120)
    approval: Optional[str] = Field(default=None, max_length=128)
    history: list[dict[str, Any]] = Field(default_factory=list)
    files: list[str] = Field(default_factory=list)
    attachments: list[dict[str, Any]] = Field(default_factory=list)


class PersonaRequest(BaseModel):
    id: Optional[str] = Field(default=None, max_length=80)
    name: str = Field(..., min_length=1, max_length=120)
    description: str = Field(default="", max_length=4000)
    role: str = Field(default="", max_length=240)
    introduction: str = Field(default="", max_length=1200)
    instructions: str = Field(default="", max_length=MAX_TEXT_CHARS)
    system_prompt: str = Field(default="", max_length=MAX_TEXT_CHARS)
    tone: str = Field(default="Grounded, practical, inspectable", max_length=240)
    language: str = Field(default="nl", max_length=40)
    rules: list[str] = Field(default_factory=list)
    tools: dict[str, bool] = Field(default_factory=dict)
    memory: dict[str, Any] = Field(default_factory=dict)
    model: str = Field(default=DEFAULT_MODEL, max_length=160)
    model_settings: dict[str, Any] = Field(default_factory=dict)
    avatar: dict[str, Any] = Field(default_factory=dict)
    conversation_starters: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    knowledge_sources: list[dict[str, Any]] = Field(default_factory=list)
    knowledge_files: list[dict[str, Any]] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class ConversationRequest(BaseModel):
    persona_id: str = Field(default="ouroboros", max_length=80)
    title: str = Field(default="New thread", max_length=160)


class MemoryRequest(BaseModel):
    persona_id: Optional[str] = Field(default=None, max_length=80)
    conversation_id: Optional[str] = Field(default=None, max_length=120)
    scope: str = Field(default="persona", max_length=40)
    content: str = Field(..., min_length=1, max_length=4000)
    tags: list[str] = Field(default_factory=list)
    importance: int = Field(default=3)


class MeetingRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=MAX_TEXT_CHARS)
    participants: list[str] = Field(default_factory=list)
    provider: Optional[str] = Field(default=DEFAULT_PROVIDER, max_length=80)
    model: Optional[str] = Field(default=DEFAULT_MODEL, max_length=160)
    approval: Optional[str] = Field(default=None, max_length=128)
    tools: list[str] = Field(default_factory=list)
    allow_tools: bool = False


def init_ouroboros_chat_routes(app: Any, service: "OuroborosChatService | None" = None) -> None:
    """Mount the standalone Ouroboros chat routes onto a FastAPI app."""

    if service is not None:
        app.state.ouroboros_chat_service = service
    app.include_router(ouroboros_chat_router)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _workspace_root() -> Path:
    configured = os.getenv("WINTRIP_WORKSPACE") or os.getenv("WORKSPACE_ROOT") or os.getenv("WINTRIP_PROJECT_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def _default_data_dir() -> Path:
    configured = os.getenv("WINTRIP_OUROBOROS_CHAT_DATA_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return (_workspace_root() / "data" / "ouroboros_chat").resolve()


def _default_persona() -> dict[str, Any]:
    return core_default_persona()


def _safe_slug(value: str, fallback: str = "item") -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "").strip()).strip(".-").lower()
    return (text[:80] or fallback).strip(".-") or fallback


def _clip_text(value: Any, limit: int = 1200) -> str:
    text = " ".join(str(value or "").replace("\x00", " ").split())
    return text[:limit]


def _attachment_extension(path_or_name: Any) -> str:
    name = str(path_or_name or "").lower().split("?", 1)[0]
    return name.rsplit(".", 1)[-1] if "." in name else ""


def _attachment_kind(path_or_name: Any) -> str:
    ext = _attachment_extension(path_or_name)
    if ext in IMAGE_ATTACHMENT_EXTENSIONS:
        return "image"
    if ext in DOCUMENT_ATTACHMENT_EXTENSIONS:
        return "document"
    return "unsupported"


def _model_supports_images(model: str) -> bool:
    lowered = str(model or "").lower()
    return any(marker in lowered for marker in VISION_MODEL_MARKERS)


def _contains_secret_like(value: Any) -> bool:
    if isinstance(value, str):
        return any(pattern.search(value) for pattern in SECRET_PATTERNS)
    if isinstance(value, dict):
        return any(_contains_secret_like(key) or _contains_secret_like(item) for key, item in value.items())
    if isinstance(value, (list, tuple, set)):
        return any(_contains_secret_like(item) for item in value)
    return False


def _redact_secret_like(text: str) -> str:
    clean = str(text or "")
    for pattern in SECRET_PATTERNS:
        clean = pattern.sub("[REDACTED]", clean)
    return clean


def _read_text_limited(path: Path, limit: int = 80_000) -> str:
    with path.open("rb") as handle:
        data = handle.read(limit)
    return data.decode("utf-8", errors="replace")


def _extract_attachment_text(path: Path, limit: int = MAX_ATTACHMENT_CONTEXT_CHARS) -> str:
    ext = _attachment_extension(path.name)
    try:
        if ext in TEXT_ATTACHMENT_EXTENSIONS:
            return _read_text_limited(path, limit=limit)
        if ext == "pdf":
            import PyPDF2

            pages: list[str] = []
            with path.open("rb") as handle:
                reader = PyPDF2.PdfReader(handle)
                for page in reader.pages[:12]:
                    page_text = page.extract_text() or ""
                    if page_text:
                        pages.append(page_text)
                    if len("\n".join(pages)) >= limit:
                        break
            return "\n".join(pages)[:limit]
        if ext == "docx":
            import docx

            doc = docx.Document(str(path))
            return "\n".join(paragraph.text for paragraph in doc.paragraphs)[:limit]
    except Exception as exc:
        return f"[Attachment read error for {path.name}: {exc}]"
    return ""


def _safe_relative_path(root: Path, relative_path: str) -> Path:
    if relative_path not in ALLOWED_CLINE_FILES:
        raise ValueError(f"Cline path is not allowlisted: {relative_path}")
    resolved_root = root.expanduser().resolve()
    candidate = (resolved_root / relative_path).resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"Cline path escapes root: {relative_path}") from exc
    return candidate


def _extract_headings(text: str, limit: int = 8) -> list[str]:
    headings: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            heading = stripped.lstrip("#").strip()
            if heading:
                headings.append(_redact_secret_like(heading)[:160])
        if len(headings) >= limit:
            break
    return headings


def _excerpt(text: str, limit: int = 500) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(("---", "import ", "export ")):
            continue
        lines.append(stripped)
        if len(" ".join(lines)) >= limit:
            break
    return _redact_secret_like(" ".join(lines))[:limit]


def _history_for_ollama(history: list[dict[str, Any]]) -> list[dict[str, str]]:
    clean: list[dict[str, str]] = []
    for item in history[-20:]:
        role = str(item.get("role") or "").strip().lower()
        content = str(item.get("content") or "")
        if role not in {"system", "user", "assistant", "tool"} or not content:
            continue
        clean.append({"role": role, "content": content[:MAX_TEXT_CHARS]})
    return clean


def _slug_list(values: list[str], limit: int = 12) -> list[str]:
    result: list[str] = []
    for value in values[:limit]:
        slug = _safe_slug(value, fallback="")
        if slug:
            result.append(slug)
    return result


def _safe_attachment_path(value: Any) -> Path | None:
    raw = ""
    if isinstance(value, dict):
        raw = str(value.get("path") or value.get("file_path") or "")
    else:
        raw = str(value or "")
    if not raw.strip():
        return None
    path = Path(raw.strip()).expanduser()
    try:
        return path.resolve()
    except Exception:
        return None


def _model_to_dict(model: BaseModel) -> dict[str, Any]:
    dumper = getattr(model, "model_dump", None)
    if callable(dumper):
        return dict(dumper())
    return dict(model.dict())


class PersonaStore:
    def __init__(self, path: Path | None = None):
        self.path = path or (_default_data_dir() / "personas.json")

    def list_personas(self) -> list[dict[str, Any]]:
        return list(self._load().get("personas", []))

    def get(self, persona_id: str | None) -> dict[str, Any] | None:
        if not persona_id:
            return None
        clean_id = _safe_slug(persona_id)
        for persona in self.list_personas():
            if persona.get("id") == clean_id:
                return dict(persona)
        return None

    def upsert(self, request: PersonaRequest) -> dict[str, Any]:
        payload = _model_to_dict(request)
        if _contains_secret_like(payload):
            raise ValueError("Persona content appears to contain a secret, token, password, or bearer credential.")

        clean_id = _safe_slug(request.id or request.name, fallback=f"persona-{uuid.uuid4().hex[:8]}")
        data = self._load()
        existing = {str(item.get("id")): dict(item) for item in data.get("personas", []) if item.get("id")}
        previous = existing.get(clean_id, {})
        persona = normalize_persona_payload({**payload, "id": clean_id}, previous=previous)
        persona["tags"] = _slug_list(request.tags)
        existing[clean_id] = persona
        self._save({"version": 1, "personas": sorted(existing.values(), key=lambda item: item["id"])})
        return persona

    def duplicate(self, persona_id: str) -> dict[str, Any]:
        source = self.get(persona_id)
        if source is None:
            raise KeyError(_safe_slug(persona_id))
        payload = dict(source)
        payload["id"] = f"{source.get('id', 'persona')}-copy-{uuid.uuid4().hex[:4]}"
        payload["name"] = f"{source.get('name', 'Persona')} Copy"
        payload["builtin"] = False
        normalized = normalize_persona_payload(payload, previous={})
        data = self._load()
        personas = {str(item.get("id")): dict(item) for item in data.get("personas", []) if item.get("id")}
        personas[normalized["id"]] = normalized
        self._save({"version": 1, "personas": sorted(personas.values(), key=lambda item: item["id"])})
        return normalized

    def import_persona(self, payload: dict[str, Any]) -> dict[str, Any]:
        if _contains_secret_like(payload):
            raise ValueError("Persona import appears to contain a secret, token, password, or bearer credential.")
        normalized = normalize_persona_payload(payload, previous={})
        data = self._load()
        personas = {str(item.get("id")): dict(item) for item in data.get("personas", []) if item.get("id")}
        personas[normalized["id"]] = normalized
        self._save({"version": 1, "personas": sorted(personas.values(), key=lambda item: item["id"])})
        return normalized

    def patch(self, persona_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        if _contains_secret_like(payload):
            raise ValueError("Persona patch appears to contain a secret, token, password, or bearer credential.")
        clean_id = _safe_slug(persona_id)
        data = self._load()
        personas = {str(item.get("id")): dict(item) for item in data.get("personas", []) if item.get("id")}
        previous = personas.get(clean_id)
        if previous is None:
            raise KeyError(clean_id)
        normalized = normalize_persona_payload({**previous, **payload, "id": clean_id}, previous=previous)
        personas[clean_id] = normalized
        self._save({"version": 1, "personas": sorted(personas.values(), key=lambda item: item["id"])})
        return normalized

    def archive(self, persona_id: str, *, hard: bool = False) -> dict[str, Any]:
        clean_id = _safe_slug(persona_id)
        data = self._load()
        personas = [dict(item) for item in data.get("personas", []) if isinstance(item, dict)]
        for index, persona in enumerate(personas):
            if persona.get("id") != clean_id:
                continue
            if hard:
                removed = personas.pop(index)
                self._save({"version": 1, "personas": personas or [_default_persona()]})
                return {"status": "deleted", "persona": removed}
            persona["archived"] = True
            persona["updated_at"] = _now_iso()
            personas[index] = persona
            self._save({"version": 1, "personas": personas})
            return {"status": "archived", "persona": persona}
        raise KeyError(clean_id)

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": 1, "personas": [_default_persona()]}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError(f"Could not read persona store: {exc}") from exc
        personas = data.get("personas") if isinstance(data, dict) else None
        if not isinstance(personas, list):
            return {"version": 1, "personas": [_default_persona()]}
        safe_personas: list[dict[str, Any]] = []
        for item in personas:
            if isinstance(item, dict) and item.get("id") and not _contains_secret_like(item):
                normalized = normalize_persona_payload(dict(item), previous=dict(item))
                if isinstance(item.get("tags"), list):
                    normalized["tags"] = _slug_list([str(tag) for tag in item.get("tags", [])])
                if item.get("updated_at"):
                    normalized["updated_at"] = str(item.get("updated_at"))
                safe_personas.append(normalized)
        if not safe_personas:
            safe_personas.append(_default_persona())
        return {"version": 1, "personas": safe_personas}

    def _save(self, data: dict[str, Any]) -> None:
        if _contains_secret_like(data):
            raise ValueError("Persona store write blocked because content appears to contain a secret.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.path)


MeetingLLMCall = Callable[..., dict[str, Any]]


class MeetingRunner:
    """Runs a transcript-only persona meeting without granting tool access."""

    def __init__(self, llm_call: MeetingLLMCall | None = None):
        self.llm_call = llm_call

    def run(
        self,
        *,
        topic: str,
        personas: list[dict[str, Any]],
        provider: str,
        model: str,
        meeting_id: str,
    ) -> dict[str, Any]:
        participants = [self._public_persona(persona) for persona in personas]
        transcript: list[dict[str, Any]] = []
        events: list[dict[str, Any]] = []

        for round_number, phase, instruction in (
            (
                1,
                "brainstorm",
                "Geef je eerste analyse van het onderwerp vanuit jouw rol. Noem kansen, risico's en een concrete vervolgstap.",
            ),
            (
                2,
                "discussion",
                "Reageer op de eerdere bijdragen. Verdiep, nuanceer of geef een tegenargument vanuit jouw expertise.",
            ),
        ):
            for persona in personas:
                participant = self._public_persona(persona)
                system_prompt = self._social_system_prompt(persona, personas, topic)
                user_prompt = self._turn_prompt(
                    topic=topic,
                    round_number=round_number,
                    phase=phase,
                    instruction=instruction,
                    transcript=transcript,
                )
                fallback = self._fallback_turn(persona, topic, phase, transcript)
                response = self._call_model(
                    prompt=user_prompt,
                    system_prompt=system_prompt,
                    model=model,
                    fallback=fallback,
                )
                event = {
                    "type": "participant_turn",
                    "meeting_id": meeting_id,
                    "timestamp": _now_iso(),
                    "round": round_number,
                    "phase": phase,
                    "participant": participant,
                    "provider": provider,
                    "model": model,
                    "content": _clip_text(response["content"], 4000),
                    "ok": response["ok"],
                    "error": response["error"],
                    "prompt_context": {
                        "social_awareness": True,
                        "other_participants": [
                            {"id": item.get("id"), "name": item.get("name"), "role": item.get("role")}
                            for item in participants
                            if item.get("id") != participant.get("id")
                        ],
                        "transcript_turns_supplied": len(transcript),
                    },
                }
                events.append(event)
                transcript.append(
                    {
                        "round": round_number,
                        "phase": phase,
                        "participant": participant,
                        "content": event["content"],
                    }
                )

        summary = self._summarize(topic=topic, transcript=transcript, model=model)
        summary_event = {
            "type": "meeting_summary",
            "meeting_id": meeting_id,
            "timestamp": _now_iso(),
            "content": _clip_text(summary["content"], 5000),
            "summary": _clip_text(summary["content"], 5000),
            "provider": provider,
            "model": model,
            "ok": summary["ok"],
            "error": summary["error"],
            "safety_note": (
                "No Cline execution, shell commands, browser control, agent execution, or write tools were run."
            ),
            "next_action": (
                f"Use exact {APPROVAL_PHRASE} only in the existing gated action routes "
                "when real-world changes are intended."
            ),
        }
        events.append(summary_event)
        return {
            "participants": participants,
            "rounds": [event for event in events if event.get("type") == "participant_turn"],
            "summary": summary_event["summary"],
            "events": events,
        }

    def _social_system_prompt(self, persona: dict[str, Any], personas: list[dict[str, Any]], topic: str) -> str:
        others = [
            f"- {item.get('name') or item.get('id')}: {item.get('role') or 'geen rol opgegeven'}"
            for item in personas
            if item.get("id") != persona.get("id")
        ]
        rules = persona.get("rules") if isinstance(persona.get("rules"), list) else []
        base_prompt = str(persona.get("system_prompt") or persona.get("instructions") or "").strip()
        return "\n".join(
            part
            for part in [
                base_prompt,
                "Je bent in een Ouroboros Vergadering.",
                f"Onderwerp: {_clip_text(topic, 1200)}",
                "Andere aanwezigen:\n" + ("\n".join(others) if others else "- Geen andere persona's."),
                f"Jouw Rol: {persona.get('role') or 'Niet opgegeven'}",
                f"Jouw Regels: {', '.join(str(rule) for rule in rules) if rules else 'Geen extra regels opgegeven.'}",
                f"Jouw Toon: {persona.get('tone') or 'Grounded, practical, inspectable'}",
                f"Jouw Taal: {persona.get('language') or 'nl'}",
                (
                    "Instructie: Reageer op het onderwerp en de input van anderen vanuit jouw specifieke expertise. "
                    "Voer geen tools uit en claim geen externe acties."
                ),
            ]
            if part
        )

    def _turn_prompt(
        self,
        *,
        topic: str,
        round_number: int,
        phase: str,
        instruction: str,
        transcript: list[dict[str, Any]],
    ) -> str:
        transcript_text = self._transcript_text(transcript)
        return "\n\n".join(
            [
                f"Onderwerp: {_clip_text(topic, 1600)}",
                f"Ronde {round_number} ({phase})",
                instruction,
                "Volledige transcriptie tot nu toe:",
                transcript_text or "Nog geen eerdere bijdragen.",
                "Antwoord kort, concreet en inspecteerbaar.",
            ]
        )

    def _summarize(self, *, topic: str, transcript: list[dict[str, Any]], model: str) -> dict[str, Any]:
        prompt = "\n\n".join(
            [
                f"Onderwerp: {_clip_text(topic, 1600)}",
                "Volledige vergaderingstranscriptie:",
                self._transcript_text(transcript) or "Geen bijdragen.",
                (
                    "Maak een 'Consensus & Actiepunten' samenvatting. "
                    "Gebruik deze koppen: Consensus, Risico's, Actiepunten, Agent follow-up prompt."
                ),
            ]
        )
        fallback = self._fallback_summary(topic, transcript)
        return self._call_model(
            prompt=prompt,
            system_prompt=(
                "Je bent de neutrale synthese-laag van een Ouroboros Vergadering. "
                "Vat alleen samen; voer geen tools, shell, browser of agents uit."
            ),
            model=model,
            fallback=fallback,
        )

    def _call_model(self, *, prompt: str, system_prompt: str, model: str, fallback: str) -> dict[str, Any]:
        if self.llm_call is None:
            return {"ok": True, "content": fallback, "error": ""}
        try:
            result = self.llm_call(
                prompt=prompt,
                model=model,
                system_prompt=system_prompt,
                history=[],
                images=[],
            )
        except TypeError:
            try:
                result = self.llm_call(prompt=prompt, model=model, system_prompt=system_prompt, history=[])
            except Exception as exc:
                return {"ok": False, "content": fallback, "error": str(exc)}
        except Exception as exc:
            return {"ok": False, "content": fallback, "error": str(exc)}

        if isinstance(result, dict):
            content = str(result.get("content") or result.get("response") or "").strip()
            return {
                "ok": bool(result.get("ok", True)) and bool(content),
                "content": content or fallback,
                "error": str(result.get("error") or ""),
            }
        content = str(result or "").strip()
        return {"ok": bool(content), "content": content or fallback, "error": ""}

    def _fallback_turn(
        self,
        persona: dict[str, Any],
        topic: str,
        phase: str,
        transcript: list[dict[str, Any]],
    ) -> str:
        name = persona.get("name") or persona.get("id") or "participant"
        role = persona.get("role") or "deelnemer"
        if phase == "brainstorm":
            return (
                f"{name} ({role}) ziet '{_clip_text(topic, 240)}' als overlegcontext. "
                "Eerste stap: maak de gewenste uitkomst expliciet, benoem risico's en houd vervolgacties approval-gated."
            )
        return (
            f"{name} ({role}) bouwt voort op {len(transcript)} eerdere bijdrage(n): "
            "verklein de scope, toets aannames en formuleer een concrete volgende stap zonder tools uit te voeren."
        )

    def _fallback_summary(self, topic: str, transcript: list[dict[str, Any]]) -> str:
        names = []
        for item in transcript:
            participant = item.get("participant") if isinstance(item.get("participant"), dict) else {}
            name = participant.get("name")
            if name and name not in names:
                names.append(str(name))
        return (
            "Consensus: behandel het onderwerp praktisch, auditable en zonder automatische externe acties.\n"
            f"Risico's: scope creep, onduidelijke eigenaar, en tool-executie zonder {APPROVAL_PHRASE}.\n"
            "Actiepunten: destilleer de follow-up, kies een agent expliciet, en gebruik de bestaande approval-flow.\n"
            f"Agent follow-up prompt: /agents Werk de vervolgstappen uit voor '{_clip_text(topic, 220)}' "
            f"op basis van de bijdragen van {', '.join(names) if names else 'de persona-deelnemers'}."
        )

    def _public_persona(self, persona: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": persona.get("id"),
            "name": persona.get("name") or persona.get("id"),
            "role": persona.get("role") or "",
            "tone": persona.get("tone") or "",
            "rules": persona.get("rules", []) if isinstance(persona.get("rules"), list) else [],
            "system_prompt": persona.get("system_prompt") or persona.get("instructions") or "",
            "tags": persona.get("tags", []) if isinstance(persona.get("tags"), list) else [],
        }

    def _transcript_text(self, transcript: list[dict[str, Any]]) -> str:
        lines = []
        for item in transcript:
            participant = item.get("participant") if isinstance(item.get("participant"), dict) else {}
            name = participant.get("name") or "participant"
            phase = item.get("phase") or "round"
            lines.append(f"[{phase}] {name}: {item.get('content') or ''}")
        return "\n".join(lines)[-12_000:]


class MeetingStore:
    def __init__(self, directory: Path | None = None):
        self.directory = directory or (_default_data_dir() / "meetings")

    def list_meetings(self, limit: int = 50) -> list[dict[str, Any]]:
        if not self.directory.exists():
            return []
        records: list[dict[str, Any]] = []
        for path in sorted(self.directory.glob("*.jsonl"), key=lambda item: item.stat().st_mtime, reverse=True)[:limit]:
            try:
                event_count = sum(1 for _line in path.open("r", encoding="utf-8"))
            except OSError:
                event_count = 0
            records.append(
                {
                    "meeting_id": path.stem,
                    "artifact_path": str(path),
                    "event_count": event_count,
                    "updated_at": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).replace(microsecond=0).isoformat(),
                }
            )
        return records

    def read_meeting(self, meeting_id: str) -> dict[str, Any]:
        clean_id = _safe_slug(meeting_id)
        path = (self.directory / f"{clean_id}.jsonl").resolve()
        try:
            path.relative_to(self.directory.resolve())
        except ValueError as exc:
            raise ValueError("Meeting id escapes meeting directory.") from exc
        if not path.exists():
            raise FileNotFoundError(clean_id)
        events: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(json.loads(line))
        return {"status": "online", "meeting_id": clean_id, "artifact_path": str(path), "events": events, "fake_success": False}

    def create_meeting(
        self,
        request: MeetingRequest,
        persona_store: PersonaStore,
        llm_call: MeetingLLMCall | None = None,
    ) -> dict[str, Any]:
        requested_tools = [str(item).strip() for item in request.tools if str(item).strip()]
        forbidden = [
            tool
            for tool in requested_tools
            if any(marker in tool.lower() for marker in MEETING_FORBIDDEN_TOOL_MARKERS)
        ]
        if request.allow_tools or requested_tools:
            return {
                "status": "blocked",
                "reason": "Ouroboros chat meetings are transcript-only and do not execute Cline, shell, browser, or write tools.",
                "requested_tools": requested_tools,
                "forbidden_tools": forbidden,
                "tool_policy": self.tool_policy(),
                "approval_phrase": APPROVAL_PHRASE,
                "fake_success": False,
            }
        if _contains_secret_like({"topic": request.topic, "participants": request.participants}):
            raise ValueError("Meeting content appears to contain a secret, token, password, or bearer credential.")

        participants = request.participants or ["ouroboros"]
        personas = []
        for persona_id in participants[:12]:
            persona = persona_store.get(persona_id)
            personas.append(persona or {"id": _safe_slug(persona_id), "name": str(persona_id), "description": "", "tags": []})

        meeting_id = f"{int(time.time())}-{uuid.uuid4().hex[:10]}"
        provider = (request.provider or DEFAULT_PROVIDER).strip().lower() or DEFAULT_PROVIDER
        model = (request.model or DEFAULT_MODEL).strip() or DEFAULT_MODEL
        events: list[dict[str, Any]] = [
            {
                "type": "meeting_started",
                "meeting_id": meeting_id,
                "timestamp": _now_iso(),
                "topic": _clip_text(request.topic, 2000),
                "provider": provider,
                "model": model,
                "approval_phrase": APPROVAL_PHRASE,
                "approval_supplied": str(request.approval or "").strip() == APPROVAL_PHRASE,
                "tool_policy": self.tool_policy(),
                "safety_note": (
                    "No Cline execution, shell commands, browser control, agent execution, or write tools were run."
                ),
            }
        ]
        runner_payload = MeetingRunner(llm_call=llm_call).run(
            topic=request.topic,
            personas=personas,
            provider=provider,
            model=model,
            meeting_id=meeting_id,
        )
        events.extend(runner_payload["events"])

        path = self._write_events(meeting_id, events)
        return {
            "status": "recorded",
            "meeting_id": meeting_id,
            "artifact_path": str(path),
            "event_count": len(events),
            "events": events,
            "participants": runner_payload["participants"],
            "rounds": runner_payload["rounds"],
            "summary": runner_payload["summary"],
            "tool_policy": self.tool_policy(),
            "fake_success": False,
        }

    def tool_policy(self) -> dict[str, Any]:
        return {
            "mode": "no_tools",
            "cline_execution": False,
            "shell": False,
            "browser": False,
            "write_tools": False,
            "artifact_write": "jsonl_only",
        }

    def _write_events(self, meeting_id: str, events: list[dict[str, Any]]) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = (self.directory / f"{_safe_slug(meeting_id)}.jsonl").resolve()
        try:
            path.relative_to(self.directory.resolve())
        except ValueError as exc:
            raise ValueError("Meeting artifact path escapes meeting directory.") from exc
        with path.open("w", encoding="utf-8") as handle:
            for event in events:
                handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
        return path


class OuroborosChatService:
    def __init__(
        self,
        *,
        data_dir: Path | None = None,
        cline_root: Path | None = None,
        ollama_client: Any | None = None,
        ollama_timeout_seconds: float | None = None,
    ):
        self.data_dir = data_dir or _default_data_dir()
        self.cline_root = (cline_root or CLINE_ROOT).expanduser()
        self.ollama_client = ollama_client
        self.ollama_timeout_seconds = float(
            ollama_timeout_seconds if ollama_timeout_seconds is not None else os.getenv("WINTRIP_OUROBOROS_CHAT_OLLAMA_TIMEOUT", "45")
        )
        self.personas = PersonaStore(self.data_dir / "personas.json")
        self.meetings = MeetingStore(self.data_dir / "meetings")
        self.conversations = ConversationStore(self.data_dir / "conversations")
        self.memory = MemoryStore(self.data_dir / "memory.json")
        self.knowledge = KnowledgeStore()
        self.prompt_assembler = PromptAssembler()
        self.uploads_dir = self.data_dir / "uploads"

    def create_meeting(self, request: MeetingRequest) -> dict[str, Any]:
        return self.meetings.create_meeting(request, self.personas, llm_call=self._call_ollama)

    def chat(self, request: OuroborosChatRequest) -> dict[str, Any]:
        if _contains_secret_like({"prompt": request.prompt, "system_prompt": request.system_prompt, "history": request.history}):
            raise ValueError("Chat prompt/system/history content appears to contain a secret, token, password, or bearer credential.")
        slash_preview = self._slash_preview(request.prompt)
        if slash_preview:
            return slash_preview
        persona = self.personas.get(request.persona_id) or self.personas.get("ouroboros") or _default_persona()
        persona_id = str(persona.get("id") or "ouroboros")
        model_settings = persona.get("model_settings") if isinstance(persona.get("model_settings"), dict) else {}
        provider = (request.provider or model_settings.get("provider") or DEFAULT_PROVIDER).strip().lower() or DEFAULT_PROVIDER
        model = (request.model or model_settings.get("name") or persona.get("model") or DEFAULT_MODEL).strip() or DEFAULT_MODEL
        if provider not in {DEFAULT_PROVIDER, "local", "ouroboros"}:
            return {
                "status": "unsupported_provider",
                "provider": provider,
                "model": model,
                "default_provider": DEFAULT_PROVIDER,
                "default_model": DEFAULT_MODEL,
                "local_only": True,
                "response": "Deze backend ondersteunt in deze slice alleen lokale Ollama-chat.",
                "approval_phrase": APPROVAL_PHRASE,
                "fake_success": False,
            }

        attachment_payload = self._prepare_attachments([*request.files, *request.attachments], model=model)
        if attachment_payload["blocked"]:
            return {
                "status": "blocked",
                "reason": "image_model_unsupported",
                "provider": DEFAULT_PROVIDER,
                "model": model,
                "default_provider": DEFAULT_PROVIDER,
                "default_model": DEFAULT_MODEL,
                "response": (
                    "Ik heb de afbeelding(en) ontvangen, maar dit model is niet als vision-capable gedeclareerd. "
                    "Ik ga niet doen alsof ik de inhoud van de afbeelding begrijp."
                ),
                "attachments": attachment_payload["records"],
                "local_only": True,
                "fake_success": False,
            }
        conversation_id = request.conversation_id or request.thread_id
        recent_history = list(request.history or [])
        if not recent_history and conversation_id:
            try:
                recent_history = list(self.conversations.get(conversation_id).get("messages") or [])
            except KeyError:
                recent_history = []
        policy = enforce_tool_policy(persona)
        memories = self.memory.list(persona_id=persona_id, limit=16) if (persona.get("memory") or {}).get("enabled", True) else []
        knowledge = self.knowledge.snippets_for_persona(persona, request.prompt) if policy.get("can_search_files") else []
        assembled = self.prompt_assembler.assemble(
            persona=persona,
            memories=memories,
            knowledge=knowledge,
            recent_history=recent_history,
            user_message=request.prompt,
            attachment_context=attachment_payload["context"],
        )
        system_prompt = "\n\n".join(part for part in [assembled["system_prompt"], request.system_prompt or ""] if str(part).strip())
        response = self._call_ollama(
            prompt=assembled["user_prompt"],
            model=model,
            system_prompt=system_prompt,
            history=_history_for_ollama(assembled["history"]),
            images=attachment_payload["images"],
        )
        status = "success" if response.get("ok") else "error"
        conversation = self.conversations.upsert_message(
            conversation_id=conversation_id,
            persona_id=persona_id,
            user_content=request.prompt,
            assistant_content=str(response.get("content", "")),
            title=request.prompt[:48],
        )
        return {
            "status": status,
            "provider": DEFAULT_PROVIDER,
            "model": model,
            "default_provider": DEFAULT_PROVIDER,
            "default_model": DEFAULT_MODEL,
            "persona_id": persona_id,
            "conversation": conversation,
            "response": response.get("content", ""),
            "error": response.get("error", ""),
            "sources": assembled.get("sources", []),
            "tool_policy": policy,
            "prompt_assembled": True,
            "local_only": True,
            "approval_phrase": APPROVAL_PHRASE,
            "approval_supplied": str(request.approval or "").strip() == APPROVAL_PHRASE,
            "files_received": [_clip_text(path, 240) for path in request.files[:20]],
            "attachments": attachment_payload["records"],
            "transient_attachment_context": bool(attachment_payload["context"]),
            "fake_success": False,
        }

    def cline_capabilities(self) -> dict[str, Any]:
        root = self.cline_root.expanduser().resolve()
        files: list[dict[str, Any]] = []
        detected: set[str] = set()
        for relative_path in ALLOWED_CLINE_FILES:
            try:
                path = _safe_relative_path(root, relative_path)
            except ValueError:
                continue
            record: dict[str, Any] = {
                "path": relative_path,
                "allowlisted": True,
                "exists": path.exists(),
                "read": False,
            }
            if path.exists() and path.is_file():
                try:
                    text = _read_text_limited(path)
                    record.update(
                        {
                            "read": True,
                            "size_bytes": path.stat().st_size,
                            "headings": _extract_headings(text),
                            "excerpt": _excerpt(text),
                        }
                    )
                    detected.add(relative_path)
                except OSError as exc:
                    record["error"] = str(exc)
            files.append(record)
        return {
            "status": "online" if root.exists() else "missing",
            "root": str(root),
            "read_only": True,
            "executed": False,
            "allowlisted_files": list(ALLOWED_CLINE_FILES),
            "files": files,
            "capabilities": self._cline_capability_cards(detected),
            "redaction": {"enabled": True, "secret_like_patterns": len(SECRET_PATTERNS)},
            "fake_success": False,
        }

    async def save_uploads(self, uploads: list[UploadFile]) -> dict[str, Any]:
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        saved: list[dict[str, Any]] = []
        attachments: list[dict[str, Any]] = []
        for upload in uploads:
            original_name = Path(upload.filename or "upload").name
            safe_name = _safe_slug(original_name, fallback="upload")
            kind = _attachment_kind(original_name)
            content = await upload.read()
            if len(content) > MAX_UPLOAD_BYTES:
                saved.append({"filename": original_name, "status": "rejected", "reason": "file too large", "size": len(content)})
                continue
            if kind == "unsupported":
                saved.append({"filename": original_name, "status": "rejected", "reason": "unsupported file type", "size": len(content)})
                continue
            text = content.decode("utf-8", errors="ignore") if kind == "document" else ""
            if text and _contains_secret_like(text):
                saved.append({"filename": original_name, "status": "rejected", "reason": "secret-like content blocked", "size": len(content)})
                continue
            dest = (self.uploads_dir / f"{int(time.time())}-{uuid.uuid4().hex[:8]}-{safe_name}").resolve()
            try:
                dest.relative_to(self.uploads_dir.resolve())
            except ValueError as exc:
                raise ValueError("Upload path escapes upload directory.") from exc
            dest.write_bytes(content)
            record = {
                "filename": original_name,
                "path": str(dest),
                "status": "ok",
                "size": len(content),
                "kind": kind,
                "mime_type": getattr(upload, "content_type", None),
            }
            saved.append(record)
            attachments.append({k: v for k, v in record.items() if k != "status"})
        return {
            "status": "success" if any(item["status"] == "ok" for item in saved) else "blocked",
            "uploaded": len([item for item in saved if item["status"] == "ok"]),
            "files": saved,
            "attachments": attachments,
            "storage": str(self.uploads_dir),
            "fake_success": False,
        }

    def _system_prompt(self, request: OuroborosChatRequest) -> str:
        persona = self.personas.get(request.persona_id) or self.personas.get("ouroboros") or _default_persona()
        pieces = [
            str(persona.get("system_prompt") or "").strip(),
            str(request.system_prompt or "").strip(),
            (
                "Core route guardrails: this endpoint does not execute shell, browser, Cline, or write tools. "
                f"When such action is needed, preserve the approval phrase {APPROVAL_PHRASE} and use the existing gated routes."
            ),
        ]
        return "\n\n".join(piece for piece in pieces if piece)

    def _slash_preview(self, prompt: str) -> dict[str, Any] | None:
        text = str(prompt or "").strip()
        if not text.startswith("/"):
            return None
        command = text[1:].partition(" ")[0].strip().lower() or "help"
        catalog = self.slash_menu()
        if command in {"agents", "help", "?"}:
            return {
                **catalog,
                "status": "online",
                "route": "slash_menu",
                "response": "Slash-menu beschikbaar; deze Ouroboros chat slice voert geen agent-commandos uit.",
            }
        return {
            "status": "blocked",
            "route": "slash_menu",
            "agent": command,
            "response": "Slash-agent execution stays with the existing approval-gated cockpit router.",
            "catalog": catalog,
            "approval_phrase": APPROVAL_PHRASE,
            "fake_success": False,
        }

    def slash_menu(self) -> dict[str, Any]:
        try:
            from controller.slash_agent_router import slash_command_catalog

            catalog = slash_command_catalog()
        except Exception as exc:
            catalog = {"status": "unavailable", "commands": {}, "reason": str(exc), "fake_success": False}
        commands = catalog.get("commands") if isinstance(catalog.get("commands"), dict) else {}
        cockpit_items = [
            {
                "command": key,
                "title": key.split(" ", 1)[0].lstrip("/") or key,
                "description": str(value),
                "source": "cockpit",
                "backend_route": "/api/cockpit/chat",
                "approval_required": any(agent in key for agent in ("/codex", "/deepseek", "/atlas", "/ruflo", "/claude", "/roo")),
                "enabled": True,
            }
            for key, value in commands.items()
        ]
        cline_items = [
            ("/plan", "Plan", "Cline-style plan mode for bounded task analysis.", False),
            ("/act", "Act", "Cline-style act mode routed through existing approval gates.", True),
            ("/deep-planning", "Deep Planning", "Use deeper task decomposition before action.", False),
            ("/newtask", "New Task", "Prepare a focused subtask handoff.", False),
            ("/persona", "Persona", "Create or select a GPT-like Ouroboros persona.", False),
            ("/meeting", "Meeting", "Let selected personas discuss a topic.", False),
            ("/read", "Read File", "Read-only file context pattern from Cline.", False),
            ("/list", "List Files", "Read-only file listing pattern from Cline.", False),
            ("/search", "Search Files", "Read-only search pattern from Cline.", False),
            ("/shell", "Shell", "Shell proposal requiring exact Akkoord through gated routes.", True),
            ("/patch", "Patch", "Write proposal requiring exact Akkoord through gated routes.", True),
            ("/browser", "Browser", "Browser action proposal requiring exact Akkoord.", True),
        ]
        items = [
            *cockpit_items,
            *[
                {
                    "command": command,
                    "title": title,
                    "description": description,
                    "source": "cline",
                    "backend_route": "/api/ouroboros-chat/chat",
                    "approval_required": approval_required,
                    "enabled": True,
                }
                for command, title, description, approval_required in cline_items
            ],
        ]
        catalog["approval_phrase"] = APPROVAL_PHRASE
        catalog["execution"] = "not_executed_by_ouroboros_chat_router"
        catalog["items"] = items
        catalog["cline_source_root"] = str(self.cline_root)
        catalog.setdefault("fake_success", False)
        return catalog

    def _prepare_attachments(self, attachments: list[Any], *, model: str) -> dict[str, Any]:
        records: list[dict[str, Any]] = []
        context_parts: list[str] = []
        images: list[str] = []
        blocked = False
        supports_images = _model_supports_images(model)

        for item in attachments[:20]:
            path = _safe_attachment_path(item)
            if path is None:
                continue
            kind = _attachment_kind(path.name)
            record = {
                "path": str(path),
                "filename": path.name,
                "kind": kind,
                "exists": path.exists(),
                "included": False,
            }
            if not path.exists() or not path.is_file():
                record["reason"] = "not_found"
                records.append(record)
                continue
            if kind == "image":
                if not supports_images:
                    record["reason"] = "image_model_unsupported"
                    blocked = True
                else:
                    images.append(base64.b64encode(path.read_bytes()).decode("ascii"))
                    record["included"] = True
                records.append(record)
                continue
            if kind == "document":
                text = _extract_attachment_text(path)
                if text.strip():
                    context_parts.append(f"--- {path.name} ---\n{text[:MAX_ATTACHMENT_CONTEXT_CHARS]}")
                    record["included"] = True
                else:
                    record["reason"] = "empty_or_unreadable"
                records.append(record)
                continue
            record["reason"] = "unsupported_file_type"
            records.append(record)

        return {
            "blocked": blocked,
            "records": records,
            "context": "\n\n".join(context_parts)[:MAX_ATTACHMENT_CONTEXT_CHARS],
            "images": images,
        }

    def _call_ollama(
        self,
        *,
        prompt: str,
        model: str,
        system_prompt: str,
        history: list[dict[str, str]],
        images: list[str] | None = None,
    ) -> dict[str, Any]:
        if self.ollama_client is not None and callable(getattr(self.ollama_client, "chat", None)):
            try:
                content = self.ollama_client.chat(
                    user_input=prompt,
                    history=history,
                    model=model,
                    system_prompt=system_prompt,
                    images=images or None,
                )
            except TypeError:
                content = self.ollama_client.chat(prompt, history=history, model=model, system_prompt=system_prompt)
            except Exception as exc:
                return {"ok": False, "content": "", "error": str(exc)}
            return {"ok": True, "content": str(content or ""), "error": ""}

        try:
            import requests

            base_url = (os.getenv("OLLAMA_HOST") or os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434").rstrip("/")
            if base_url.endswith("/api"):
                base_url = base_url[:-4]
            user_message: dict[str, Any] = {"role": "user", "content": prompt}
            if images:
                user_message["images"] = images
            messages = [{"role": "system", "content": system_prompt}, *history, user_message]
            response = requests.post(
                f"{base_url}/api/chat",
                json={"model": model, "messages": messages, "stream": False, "options": {"temperature": 0.15}},
                timeout=max(1.0, self.ollama_timeout_seconds),
            )
            response.raise_for_status()
            return {"ok": True, "content": str(response.json().get("message", {}).get("content", "") or ""), "error": ""}
        except Exception as exc:
            return {"ok": False, "content": "", "error": f"Local Ollama chat failed for {model}: {exc}"}

    def _cline_capability_cards(self, detected: set[str]) -> list[dict[str, Any]]:
        def has(path: str) -> bool:
            return path in detected

        return [
            {
                "id": "plan_act",
                "label": "Plan and Act workflow",
                "detected": has("docs/core-workflows/plan-and-act.mdx"),
                "source": "docs/core-workflows/plan-and-act.mdx",
                "execution": "read_only_context",
            },
            {
                "id": "task_management",
                "label": "Task management patterns",
                "detected": has("docs/core-workflows/task-management.mdx"),
                "source": "docs/core-workflows/task-management.mdx",
                "execution": "read_only_context",
            },
            {
                "id": "checkpoints",
                "label": "Checkpoint and restore concepts",
                "detected": has("docs/core-workflows/checkpoints.mdx"),
                "source": "docs/core-workflows/checkpoints.mdx",
                "execution": "read_only_context",
            },
            {
                "id": "cline_rules",
                "label": "Cline rules and customization",
                "detected": has("docs/customization/cline-rules.mdx"),
                "source": "docs/customization/cline-rules.mdx",
                "execution": "read_only_context",
            },
            {
                "id": "subagents",
                "label": "Subagent planning context",
                "detected": has("docs/features/subagents.mdx"),
                "source": "docs/features/subagents.mdx",
                "execution": "read_only_context",
            },
            {
                "id": "mcp",
                "label": "MCP integration concepts",
                "detected": has("docs/mcp/mcp-overview.mdx"),
                "source": "docs/mcp/mcp-overview.mdx",
                "execution": "read_only_context",
            },
        ]


ouroboros_chat_router = APIRouter(prefix="/api/ouroboros-chat", tags=["ouroboros-chat"])


def _service_from_request(request: Request) -> OuroborosChatService:
    service = getattr(request.app.state, "ouroboros_chat_service", None)
    if service is None:
        service = OuroborosChatService()
        request.app.state.ouroboros_chat_service = service
    return service


@ouroboros_chat_router.post("/chat")
async def chat(request_body: OuroborosChatRequest, request: Request) -> dict[str, Any]:
    try:
        return _service_from_request(request).chat(request_body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


if _MULTIPART_AVAILABLE and FastAPIFile is not None:

    @ouroboros_chat_router.post("/upload")
    async def upload_files(request: Request, files: list[UploadFile] = FastAPIFile(...)) -> dict[str, Any]:
        try:
            return await _service_from_request(request).save_uploads(files)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

else:

    @ouroboros_chat_router.post("/upload")
    async def upload_files_unavailable() -> dict[str, Any]:
        raise HTTPException(status_code=503, detail="python-multipart is not installed in this runtime.")


@ouroboros_chat_router.get("/cline-capabilities")
async def cline_capabilities(request: Request) -> dict[str, Any]:
    return _service_from_request(request).cline_capabilities()


@ouroboros_chat_router.get("/slash-menu")
async def slash_menu(request: Request) -> dict[str, Any]:
    return _service_from_request(request).slash_menu()


@ouroboros_chat_router.get("/uploads/{filename}")
async def get_upload(filename: str, request: Request) -> Any:
    if FileResponse is None:
        raise HTTPException(status_code=503, detail="File responses are not available in this runtime.")
    service = _service_from_request(request)
    safe_name = Path(filename or "").name
    path = (service.uploads_dir / safe_name).resolve()
    try:
        path.relative_to(service.uploads_dir.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="upload path escapes upload directory") from exc
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"unknown upload: {safe_name}")
    return FileResponse(path)


@ouroboros_chat_router.get("/personas")
async def list_personas(request: Request) -> dict[str, Any]:
    service = _service_from_request(request)
    personas = service.personas.list_personas()
    return {
        "status": "online",
        "path": str(service.personas.path),
        "personas": personas,
        "count": len(personas),
        "approval_phrase": APPROVAL_PHRASE,
        "fake_success": False,
    }


@ouroboros_chat_router.post("/personas")
async def upsert_persona(request_body: PersonaRequest, request: Request) -> dict[str, Any]:
    try:
        persona = _service_from_request(request).personas.upsert(request_body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "saved", "persona": persona, "approval_phrase": APPROVAL_PHRASE, "fake_success": False}


@ouroboros_chat_router.post("/personas/import")
async def import_persona(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    try:
        persona = _service_from_request(request).personas.import_persona(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "imported", "persona": persona, "fake_success": False}


@ouroboros_chat_router.get("/personas/{persona_id}")
async def get_persona(persona_id: str, request: Request) -> dict[str, Any]:
    persona = _service_from_request(request).personas.get(persona_id)
    if persona is None:
        raise HTTPException(status_code=404, detail=f"unknown persona: {persona_id}")
    return {"status": "online", "persona": persona, "approval_phrase": APPROVAL_PHRASE, "fake_success": False}


@ouroboros_chat_router.get("/personas/{persona_id}/export")
async def export_persona(persona_id: str, request: Request) -> dict[str, Any]:
    persona = _service_from_request(request).personas.get(persona_id)
    if persona is None:
        raise HTTPException(status_code=404, detail=f"unknown persona: {persona_id}")
    return {"status": "exported", "persona": persona, "schema": "ouroboros_chat_persona_v1", "fake_success": False}


@ouroboros_chat_router.post("/personas/{persona_id}/duplicate")
async def duplicate_persona(persona_id: str, request: Request) -> dict[str, Any]:
    try:
        persona = _service_from_request(request).personas.duplicate(persona_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown persona: {persona_id}") from exc
    return {"status": "duplicated", "persona": persona, "fake_success": False}


@ouroboros_chat_router.put("/personas/{persona_id}")
async def update_persona(persona_id: str, request_body: PersonaRequest, request: Request) -> dict[str, Any]:
    update = _model_to_dict(request_body)
    update["id"] = persona_id
    try:
        persona = _service_from_request(request).personas.upsert(PersonaRequest(**update))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "saved", "persona": persona, "approval_phrase": APPROVAL_PHRASE, "fake_success": False}


@ouroboros_chat_router.put("/personas/{persona_id}/tools")
async def update_persona_tools(persona_id: str, payload: dict[str, bool], request: Request) -> dict[str, Any]:
    service = _service_from_request(request)
    try:
        persona = service.personas.patch(persona_id, {"tools": payload})
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown persona: {persona_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "saved", "persona": persona, "tool_policy": enforce_tool_policy(persona), "fake_success": False}


@ouroboros_chat_router.delete("/personas/{persona_id}")
async def delete_persona(persona_id: str, request: Request, hard: bool = False) -> dict[str, Any]:
    try:
        result = _service_from_request(request).personas.archive(persona_id, hard=hard)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown persona: {persona_id}") from exc
    return {**result, "approval_phrase": APPROVAL_PHRASE, "fake_success": False}


@ouroboros_chat_router.get("/tools")
async def get_tools() -> dict[str, Any]:
    return tool_catalog()


@ouroboros_chat_router.get("/conversations")
async def list_conversations(request: Request, persona_id: str = "", limit: int = 100) -> dict[str, Any]:
    service = _service_from_request(request)
    conversations = service.conversations.list(persona_id=persona_id or None, limit=max(1, min(limit, 500)))
    return {"status": "online", "conversations": conversations, "count": len(conversations), "fake_success": False}


@ouroboros_chat_router.post("/conversations")
async def create_conversation(request_body: ConversationRequest, request: Request) -> dict[str, Any]:
    conversation = _service_from_request(request).conversations.create(
        persona_id=request_body.persona_id,
        title=request_body.title,
    )
    return {"status": "created", "conversation": conversation, "fake_success": False}


@ouroboros_chat_router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, request: Request) -> dict[str, Any]:
    try:
        conversation = _service_from_request(request).conversations.get(conversation_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown conversation: {conversation_id}") from exc
    return {"status": "online", "conversation": conversation, "fake_success": False}


@ouroboros_chat_router.put("/conversations/{conversation_id}")
async def update_conversation(conversation_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    try:
        conversation = _service_from_request(request).conversations.update(conversation_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown conversation: {conversation_id}") from exc
    return {"status": "saved", "conversation": conversation, "fake_success": False}


@ouroboros_chat_router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str, request: Request, hard: bool = False) -> dict[str, Any]:
    try:
        return {**_service_from_request(request).conversations.delete(conversation_id, hard=hard), "fake_success": False}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown conversation: {conversation_id}") from exc


@ouroboros_chat_router.get("/memory")
async def list_memory(request: Request, persona_id: str = "", scope: str = "", limit: int = 100) -> dict[str, Any]:
    service = _service_from_request(request)
    items = service.memory.list(persona_id=persona_id or None, scope=scope or None, limit=max(1, min(limit, 500)))
    return {"status": "online", "memory": items, "count": len(items), "fake_success": False}


@ouroboros_chat_router.post("/memory")
async def create_memory(request_body: MemoryRequest, request: Request) -> dict[str, Any]:
    try:
        item = _service_from_request(request).memory.create(_model_to_dict(request_body))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "created", "memory": item, "fake_success": False}


@ouroboros_chat_router.put("/memory/{memory_id}")
async def update_memory(memory_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
    try:
        item = _service_from_request(request).memory.update(memory_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown memory: {memory_id}") from exc
    return {"status": "saved", "memory": item, "fake_success": False}


@ouroboros_chat_router.delete("/memory/{memory_id}")
async def delete_memory(memory_id: str, request: Request) -> dict[str, Any]:
    try:
        return {**_service_from_request(request).memory.delete(memory_id), "fake_success": False}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown memory: {memory_id}") from exc


@ouroboros_chat_router.get("/knowledge/search")
async def search_knowledge(request: Request, persona_id: str, q: str = "", limit: int = 5) -> dict[str, Any]:
    service = _service_from_request(request)
    persona = service.personas.get(persona_id)
    if persona is None:
        raise HTTPException(status_code=404, detail=f"unknown persona: {persona_id}")
    snippets = service.knowledge.snippets_for_persona(persona, q, limit=max(1, min(limit, 20)))
    return {"status": "online", "snippets": snippets, "count": len(snippets), "fake_success": False}


@ouroboros_chat_router.get("/meetings")
async def list_meetings(request: Request, limit: int = 50) -> dict[str, Any]:
    service = _service_from_request(request)
    records = service.meetings.list_meetings(limit=max(1, min(int(limit), 200)))
    return {
        "status": "online",
        "directory": str(service.meetings.directory),
        "meetings": records,
        "count": len(records),
        "tool_policy": service.meetings.tool_policy(),
        "approval_phrase": APPROVAL_PHRASE,
        "fake_success": False,
    }


@ouroboros_chat_router.post("/meetings")
async def create_meeting(request_body: MeetingRequest, request: Request) -> dict[str, Any]:
    service = _service_from_request(request)
    try:
        return service.create_meeting(request_body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@ouroboros_chat_router.get("/meetings/{meeting_id}")
async def get_meeting(meeting_id: str, request: Request) -> dict[str, Any]:
    try:
        return _service_from_request(request).meetings.read_meeting(meeting_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"unknown meeting: {meeting_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


__all__ = [
    "APPROVAL_PHRASE",
    "ALLOWED_CLINE_FILES",
    "DEFAULT_MODEL",
    "DEFAULT_PROVIDER",
    "MeetingRequest",
    "OuroborosChatRequest",
    "OuroborosChatService",
    "PersonaRequest",
    "init_ouroboros_chat_routes",
    "ouroboros_chat_router",
]
