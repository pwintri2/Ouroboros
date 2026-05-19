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
import asyncio
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
CLAUDE_MODEL_OPTIONS = (
    "claude-sonnet-4-6",
    "claude-opus-4-6",
    "claude-haiku-4-5-20251001",
    "claude-3-5-sonnet-latest",
)
OPENAI_MODEL_OPTIONS = (
    "gpt-5.4-mini",
    "gpt-5.4",
    "gpt-5.3-codex",
)
PROVIDER_MODEL_OPTIONS: dict[str, dict[str, Any]] = {
    "openai": {
        "label": "OpenAI via Cockpit API key",
        "models": list(OPENAI_MODEL_OPTIONS),
        "default_model": "gpt-5.4-mini",
    },
    "anthropic": {
        "label": "Claude via Cockpit API key",
        "models": list(CLAUDE_MODEL_OPTIONS),
        "default_model": "claude-sonnet-4-6",
    },
    "deepseek": {
        "label": "DeepSeek via Cockpit API key",
        "models": ["deepseek-v4-flash", "deepseek-v4-pro", "deepseek-chat", "deepseek-reasoner"],
        "default_model": "deepseek-chat",
    },
    "google": {
        "label": "Gemini via Cockpit API key",
        "models": ["gemini-2.5-flash", "gemini-2.5-pro"],
        "default_model": "gemini-2.5-flash",
    },
    "xai": {
        "label": "Grok/xAI via Cockpit API key",
        "models": ["grok-3", "grok-3-mini", "grok-3-latest", "grok-2-latest"],
        "default_model": "grok-3",
    },
    "mistral": {
        "label": "Mistral via Cockpit API key",
        "models": ["mistral-large-latest", "mistral-medium-latest", "mistral-small-latest"],
        "default_model": "mistral-large-latest",
    },
}
LOCAL_OLLAMA_FALLBACK_MODELS = (
    DEFAULT_MODEL,
    "gpt-oss:120b-cloud",
    "deepseek-coder:latest",
    "llama3.2:latest",
    "mistral:latest",
    "qwen2.5:latest",
    "llama2-uncensored:latest",
    "devstral:latest",
    "codellama:13b",
    "llama3:8b",
    "llama3:latest",
    "gemma4:latest",
    "phi3:latest",
)
DEFAULT_MEETING_PERSONAS: tuple[dict[str, Any], ...] = (
    {
        "id": "de-voorzitter",
        "name": "De voorzitter",
        "description": "Bewaakt doel, agenda, spreektijd, besluiten en actie-eigenaars.",
        "role": "Meeting facilitator and decision keeper",
        "introduction": "Ik houd de vergadering scherp: doel, volgorde, besluiten en concrete vervolgstappen.",
        "instructions": (
            "Leid het overleg rustig. Vat spanningen samen, vraag om verduidelijking waar nodig, "
            "en eindig met besluitpunten en eigenaars."
        ),
        "system_prompt": (
            "Leid het overleg rustig. Vat spanningen samen, vraag om verduidelijking waar nodig, "
            "en eindig met besluitpunten en eigenaars."
        ),
        "tone": "Rustig, structurerend, besluitvaardig",
        "language": "nl",
        "rules": [
            "Houd het onderwerp en de gewenste uitkomst zichtbaar.",
            "Benoem open vragen voordat actiepunten worden gemaakt.",
            "Geen externe acties zonder expliciete approval-flow.",
        ],
        "tools": {"web_search": True, "file_search": True},
        "model": "claude-sonnet-4-6",
        "model_settings": {"provider": "anthropic", "name": "claude-sonnet-4-6", "temperature": 0.4, "max_tokens": 2200, "fallback_model": DEFAULT_MODEL},
        "avatar": {"kind": "initials", "color": "#7bdcc3"},
        "knowledge_sources": [
            {"label": "Meeting facilitation patterns", "url": "https://en.wikipedia.org/wiki/Meeting_facilitation", "note": "Algemene context voor overlegstructuur."}
        ],
        "tags": ["meeting", "default"],
        "builtin": True,
    },
    {
        "id": "de-ontwerper",
        "name": "De ontwerper",
        "description": "Zet ruwe ideeën om in bruikbare flows, interfaces en ervaarbare concepten.",
        "role": "Product and interaction designer",
        "introduction": "Ik vertaal overleg naar heldere gebruikersflows, schermen en ontwerpkeuzes.",
        "instructions": (
            "Denk vanuit gebruiker, workflow en visuele hiërarchie. Maak ideeën concreet als schermen, "
            "states, copy en interactiepatronen."
        ),
        "system_prompt": (
            "Denk vanuit gebruiker, workflow en visuele hiërarchie. Maak ideeën concreet als schermen, "
            "states, copy en interactiepatronen."
        ),
        "tone": "Verbeeldend, praktisch, precies",
        "language": "nl",
        "rules": [
            "Vertaal abstracte wensen naar concrete UI- en workflowkeuzes.",
            "Let op rust, toegankelijkheid en dagelijkse bruikbaarheid.",
            "Noem ontwerp-aannames expliciet.",
        ],
        "tools": {"web_search": True, "file_search": True},
        "model": "claude-sonnet-4-6",
        "model_settings": {"provider": "anthropic", "name": "claude-sonnet-4-6", "temperature": 0.65, "max_tokens": 2600, "fallback_model": DEFAULT_MODEL},
        "avatar": {"kind": "initials", "color": "#f2c97d"},
        "knowledge_sources": [
            {"label": "Human interface guidelines", "url": "https://developer.apple.com/design/human-interface-guidelines/", "note": "Referentie voor rustige, bruikbare interactiepatronen."}
        ],
        "tags": ["design", "default"],
        "builtin": True,
    },
    {
        "id": "de-criticus",
        "name": "Criticus",
        "description": "Zoekt risico's, gaten in aannames, regressies en ontbrekende tests.",
        "role": "Critical reviewer and risk analyst",
        "introduction": "Ik prik vriendelijk maar stevig in aannames, risico's en testgaten.",
        "instructions": (
            "Review voorstellen op risico, veiligheid, regressies, ontbrekende acceptatiecriteria en testbaarheid. "
            "Geef kritiek als concrete verbetering."
        ),
        "system_prompt": (
            "Review voorstellen op risico, veiligheid, regressies, ontbrekende acceptatiecriteria en testbaarheid. "
            "Geef kritiek als concrete verbetering."
        ),
        "tone": "Scherp, eerlijk, constructief",
        "language": "nl",
        "rules": [
            "Noem eerst het grootste risico.",
            "Vraag om bewijs wanneer succes niet inspecteerbaar is.",
            "Maak kritiek actionable en testbaar.",
        ],
        "tools": {"web_search": True, "file_search": True},
        "model": "claude-opus-4-6",
        "model_settings": {"provider": "anthropic", "name": "claude-opus-4-6", "temperature": 0.25, "max_tokens": 2600, "fallback_model": DEFAULT_MODEL},
        "avatar": {"kind": "initials", "color": "#fb7185"},
        "knowledge_sources": [
            {"label": "Software testing", "url": "https://en.wikipedia.org/wiki/Software_testing", "note": "Basisreferentie voor regressie- en acceptatietesten."}
        ],
        "tags": ["critic", "default"],
        "builtin": True,
    },
)
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

MEETING_TYPE_ALIASES = {
    "team": "team",
    "team_meeting": "team",
    "teamvergadering": "team",
    "team vergadering": "team",
    "sprint": "sprint_planning",
    "sprint_planning": "sprint_planning",
    "sprint planning": "sprint_planning",
    "brainstorm": "brainstorm",
    "brainstormsessie": "brainstorm",
    "brainstorm sessie": "brainstorm",
}

MEETING_TYPE_LABELS = {
    "team": "Team vergadering",
    "sprint_planning": "Sprint planning",
    "brainstorm": "Brainstormsessie",
}

CODING_MODEL_HINTS = {
    "openai": ("gpt-5.3-codex", "gpt-5.4-mini"),
    "google": ("gemini-2.5-pro", "gemini-2.5-flash"),
    "ollama": ("devstral:latest", "deepseek-coder:latest", "codellama:13b"),
}


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
    meeting_type: str = Field(default="team", max_length=40)
    participants: list[str] = Field(default_factory=list)
    provider: Optional[str] = Field(default=DEFAULT_PROVIDER, max_length=80)
    model: Optional[str] = Field(default=DEFAULT_MODEL, max_length=160)
    approval: Optional[str] = Field(default=None, max_length=128)
    tools: list[str] = Field(default_factory=list)
    allow_tools: bool = False


class MeetingSaveRequest(BaseModel):
    topic: str = Field(default="", max_length=MAX_TEXT_CHARS)
    meeting_type: str = Field(default="", max_length=40)
    frontend_id: Optional[str] = Field(default=None, max_length=120)
    participants: list[dict[str, Any]] = Field(default_factory=list)
    participant_ids: list[str] = Field(default_factory=list)
    agent_ids: list[str] = Field(default_factory=list)
    rounds: list[dict[str, Any]] = Field(default_factory=list)
    summary: str = Field(default="", max_length=MAX_TEXT_CHARS)
    transcript: str = Field(default="", max_length=MAX_TEXT_CHARS * 2)
    status: str = Field(default="saved", max_length=40)


class DevelopmentTeamRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=MAX_TEXT_CHARS)
    persona_ids: list[str] = Field(default_factory=list)
    agent_ids: list[str] = Field(default_factory=list)
    provider: Optional[str] = Field(default=DEFAULT_PROVIDER, max_length=80)
    model: Optional[str] = Field(default=DEFAULT_MODEL, max_length=160)
    approval: Optional[str] = Field(default=None, max_length=128)
    max_iterations: int = Field(default=3)


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


def _default_meeting_personas() -> list[dict[str, Any]]:
    personas: list[dict[str, Any]] = []
    for item in DEFAULT_MEETING_PERSONAS:
        persona = normalize_persona_payload(dict(item), previous={"builtin": True})
        persona["builtin"] = True
        persona["tags"] = list(item.get("tags", []))
        personas.append(persona)
    return personas


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


def _dedupe_strings(values: list[Any] | tuple[Any, ...], *, fallback: tuple[str, ...] = ()) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in [*values, *fallback]:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        result.append(text)
        seen.add(text)
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


def _normalize_meeting_type(value: Any) -> str:
    text = str(value or "team").strip().lower().replace("-", "_")
    return MEETING_TYPE_ALIASES.get(text, MEETING_TYPE_ALIASES.get(text.replace("_", " "), "team"))


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
            return {"version": 1, "personas": self._with_builtin_personas([_default_persona()])}
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
        return {"version": 1, "personas": self._with_builtin_personas(safe_personas)}

    def _with_builtin_personas(self, personas: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_id = {str(item.get("id")): dict(item) for item in personas if item.get("id")}
        for persona in _default_meeting_personas():
            if persona["id"] not in by_id:
                by_id[persona["id"]] = persona
            elif by_id[persona["id"]].get("builtin"):
                existing = by_id[persona["id"]]
                merged = {**persona, **existing}
                if persona["id"] == "de-criticus" and str(existing.get("name") or "").strip().lower() == "de criticus":
                    merged["name"] = persona["name"]
                merged["tools"] = {**persona.get("tools", {}), **existing.get("tools", {})}
                merged["model_settings"] = {**persona.get("model_settings", {}), **existing.get("model_settings", {})}
                if not existing.get("knowledge_sources"):
                    merged["knowledge_sources"] = persona.get("knowledge_sources", [])
                by_id[persona["id"]] = merged
        return sorted(by_id.values(), key=lambda item: str(item.get("id") or ""))

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
        meeting_type: str = "team",
    ) -> dict[str, Any]:
        meeting_type = _normalize_meeting_type(meeting_type)
        personas = self._ordered_personas(personas)
        participants = [self._public_persona(persona) for persona in personas]
        chair = self._chair_persona(personas)
        transcript: list[dict[str, Any]] = []
        events: list[dict[str, Any]] = []

        if chair:
            agenda = self._chair_led_agenda(chair, personas, meeting_type)
            for round_number, phase, persona, instruction in agenda:
                event = self._run_turn(
                    topic=topic,
                    meeting_type=meeting_type,
                    personas=personas,
                    participants=participants,
                    persona=persona,
                    provider=provider,
                    model=model,
                    meeting_id=meeting_id,
                    round_number=round_number,
                    phase=phase,
                    instruction=instruction,
                    transcript=transcript,
                    max_words=95 if self._is_chair_persona(persona) else 80,
                )
                events.append(event)
                transcript.append(
                    {
                        "round": round_number,
                        "phase": phase,
                        "participant": event["participant"],
                        "content": event["content"],
                    }
                )
                if not self._is_chair_persona(persona) and self._looks_like_parroting(transcript, event["content"]):
                    intervention = self._run_turn(
                        topic=topic,
                        meeting_type=meeting_type,
                        personas=personas,
                        participants=participants,
                        persona=chair,
                        provider=provider,
                        model=model,
                        meeting_id=meeting_id,
                        round_number=round_number,
                        phase="intervention",
                        instruction=(
                            "Grijp als voorzitter kort in: benoem dat twee bijdragen elkaar te veel herhalen, "
                            "vraag om één nieuw onderscheidend punt en bepaal wie daarna spreekt. Maximaal 55 woorden."
                        ),
                        transcript=transcript,
                        max_words=65,
                    )
                    intervention["prompt_context"]["intervention_reason"] = "anti_parroting"
                    events.append(intervention)
                    transcript.append(
                        {
                            "round": round_number,
                            "phase": "intervention",
                            "participant": intervention["participant"],
                            "content": intervention["content"],
                        }
                    )
        else:
            for round_number, phase, instruction in (
                (
                    1,
                    "brainstorm",
                    "Geef je eerste reactie als spreekbeurt in het gesprek: maximaal 80 woorden, één concreet punt, één risico en één vraag of vervolgstap.",
                ),
                (
                    2,
                    "discussion",
                    "Reageer op de vorige spreker alsof je aan tafel zit: maximaal 80 woorden, bouw voort of nuanceer, en eindig met één concrete vervolgstap.",
                ),
            ):
                for persona in personas:
                    event = self._run_turn(
                        topic=topic,
                        meeting_type=meeting_type,
                        personas=personas,
                        participants=participants,
                        persona=persona,
                        provider=provider,
                        model=model,
                        meeting_id=meeting_id,
                        round_number=round_number,
                        phase=phase,
                        instruction=instruction,
                        transcript=transcript,
                        max_words=80,
                    )
                    events.append(event)
                    transcript.append(
                        {
                            "round": round_number,
                            "phase": phase,
                            "participant": event["participant"],
                            "content": event["content"],
                        }
                    )

        summary = self._summarize(topic=topic, transcript=transcript, model=model, provider=provider, meeting_type=meeting_type)
        summary_content = self._compact_conversation_text(summary["content"], max_words=180)
        summary_event = {
            "type": "meeting_summary",
            "meeting_id": meeting_id,
            "timestamp": _now_iso(),
            "meeting_type": meeting_type,
            "content": _clip_text(summary_content, 3000),
            "summary": _clip_text(summary_content, 3000),
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
            "meeting_type": meeting_type,
            "participants": participants,
            "rounds": [event for event in events if event.get("type") == "participant_turn"],
            "summary": summary_event["summary"],
            "events": events,
        }

    def _ordered_personas(self, personas: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [persona for _, persona in sorted(enumerate(personas), key=lambda item: (0 if self._is_chair_persona(item[1]) else 1, item[0]))]

    def _chair_persona(self, personas: list[dict[str, Any]]) -> dict[str, Any] | None:
        for persona in personas:
            if self._is_chair_persona(persona):
                return persona
        return None

    def _is_chair_persona(self, persona: dict[str, Any]) -> bool:
        persona_id = str(persona.get("id") or "").strip().lower()
        name = str(persona.get("name") or "").strip().lower()
        role = str(persona.get("role") or "").strip().lower()
        return persona_id == "de-voorzitter" or "voorzitter" in name or "facilitator" in role

    def _chair_led_agenda(
        self,
        chair: dict[str, Any],
        personas: list[dict[str, Any]],
        meeting_type: str,
    ) -> list[tuple[int, str, dict[str, Any], str]]:
        meeting_type = _normalize_meeting_type(meeting_type)
        if meeting_type == "sprint_planning":
            return self._sprint_planning_agenda(chair, personas)
        if meeting_type == "brainstorm":
            return self._brainstorm_agenda(chair, personas)
        return self._team_agenda(chair, personas)

    def _team_agenda(
        self,
        chair: dict[str, Any],
        personas: list[dict[str, Any]],
    ) -> list[tuple[int, str, dict[str, Any], str]]:
        contributors = [persona for persona in personas if persona is not chair]
        first_name = contributors[0].get("name") if contributors else "de tafel"
        agenda: list[tuple[int, str, dict[str, Any], str]] = [
            (
                1,
                "opening",
                chair,
                (
                    "Open als voorzitter. Noem in gewone spreektaal het doel van dit overleg, de volgorde, "
                    f"en geef daarna het woord aan {first_name}. Maximaal 65 woorden."
                ),
            )
        ]
        for persona in contributors:
            agenda.append(
                (
                    1,
                    "input",
                    persona,
                    (
                        "Geef je bijdrage aan de voorzitter en de andere deelnemers. Spreek natuurlijk, maximaal 75 woorden. "
                        "Noem één voorstel en één aandachtspunt. Geen rapportstijl."
                    ),
                )
            )
        if contributors:
            agenda.append(
                (
                    1,
                    "chair-bridge",
                    chair,
                    (
                        "Vat als voorzitter in maximaal 70 woorden samen wat je hoort. Benoem de spanning of keuze die nu op tafel ligt "
                        "en stel één gerichte vraag voor de tweede ronde."
                    ),
                )
            )
            for persona in contributors:
                agenda.append(
                    (
                        2,
                        "reply",
                        persona,
                        (
                            "Reageer kort op de vraag of samenvatting van de voorzitter. Maximaal 70 woorden. "
                            "Maak je antwoord concreet en eindig met één besluitbaar punt."
                        ),
                    )
                )
        agenda.append(
            (
                2,
                "closing",
                chair,
                (
                    "Sluit als voorzitter af in maximaal 90 woorden. Geef gewone spreektaal met drie korte regels: "
                    "Besluit, Open vraag, Volgende stap. Wijs geen acties toe buiten de approval-flow."
                ),
            )
        )
        return agenda

    def _sprint_planning_agenda(
        self,
        chair: dict[str, Any],
        personas: list[dict[str, Any]],
    ) -> list[tuple[int, str, dict[str, Any], str]]:
        contributors = [persona for persona in personas if persona is not chair]
        first_name = contributors[0].get("name") if contributors else "de tafel"
        agenda: list[tuple[int, str, dict[str, Any], str]] = [
            (
                1,
                "opening",
                chair,
                (
                    "Open als voorzitter een sprint planning. Zet direct de timebox, het doel en de volgorde neer. "
                    f"Geef daarna het woord aan {first_name}. Maximaal 55 woorden."
                ),
            )
        ]
        for persona in contributors:
            agenda.append(
                (
                    1,
                    "plan-slice",
                    persona,
                    (
                        "Lever één sprint-plak: doel, eerste taak, grootste risico en test. "
                        "Spreek kort en besluitbaar, maximaal 65 woorden."
                    ),
                )
            )
        if contributors:
            agenda.append(
                (
                    1,
                    "plan-bridge",
                    chair,
                    (
                        "Maak als voorzitter een concept-plan in gewone taal. Benoem de volgorde, het scherpste risico "
                        "en de ene vraag die nog nodig is om te starten. Maximaal 75 woorden."
                    ),
                )
            )
            for persona in contributors:
                agenda.append(
                    (
                        2,
                        "plan-check",
                        persona,
                        (
                            "Controleer het concept-plan. Voeg alleen één correctie, gat of test toe die het plan beter maakt. "
                            "Maximaal 55 woorden."
                        ),
                    )
                )
        agenda.append(
            (
                2,
                "closing",
                chair,
                (
                    "Presenteer het sprintplan als voorzitter. Gebruik vier korte regels: Doel, Taken, Test, Stopregel. "
                    "Geen externe uitvoering buiten de approval-flow."
                ),
            )
        )
        return agenda

    def _brainstorm_agenda(
        self,
        chair: dict[str, Any],
        personas: list[dict[str, Any]],
    ) -> list[tuple[int, str, dict[str, Any], str]]:
        contributors = [persona for persona in personas if persona is not chair]
        first_name = contributors[0].get("name") if contributors else "de tafel"
        agenda: list[tuple[int, str, dict[str, Any], str]] = [
            (
                1,
                "opening",
                chair,
                (
                    "Open als voorzitter een brainstormsessie. Zet de onderzoekslagen neer: bronnen, aannames, alternatieven, risico's. "
                    f"Geef daarna het woord aan {first_name}. Maximaal 65 woorden."
                ),
            )
        ]
        for persona in contributors:
            agenda.append(
                (
                    1,
                    "research",
                    persona,
                    (
                        "Breng één nieuwe onderzoekslaag in. Gebruik de beschikbare kennis- of Brave-context als die aanwezig is, "
                        "noem de bronlaag kort en voeg één aanname of vraag toe. Maximaal 85 woorden."
                    ),
                )
            )
        if contributors:
            agenda.append(
                (
                    1,
                    "research-bridge",
                    chair,
                    (
                        "Cluster als voorzitter de bronnen en lagen die op tafel liggen. Benoem welke laag nog ontbreekt "
                        "en geef de volgende spreker gericht het woord. Maximaal 80 woorden."
                    ),
                )
            )
            for persona in contributors:
                agenda.append(
                    (
                        2,
                        "research-layer",
                        persona,
                        (
                            "Voeg nu geen herhaling toe. Geef één andere invalshoek, bronlaag, tegenvoorbeeld of dieper risico. "
                            "Maximaal 80 woorden."
                        ),
                    )
                )
            agenda.append(
                (
                    2,
                    "research-synthesis",
                    chair,
                    (
                        "Maak als voorzitter een korte synthese van de lagen. Benoem wat voldoende onderbouwd lijkt, "
                        "wat onzeker blijft en welke bronlaag nog extra onderzoek vraagt. Maximaal 90 woorden."
                    ),
                )
            )
        agenda.append(
            (
                2,
                "closing",
                chair,
                (
                    "Sluit de brainstorm af met drie korte regels: Sterkste inzicht, Nog onzeker, Volgende onderzoeksstap. "
                    "Geen claims zonder bronlaag en geen uitvoering buiten de approval-flow."
                ),
            )
        )
        return agenda

    def _run_turn(
        self,
        *,
        topic: str,
        meeting_type: str,
        personas: list[dict[str, Any]],
        participants: list[dict[str, Any]],
        persona: dict[str, Any],
        provider: str,
        model: str,
        meeting_id: str,
        round_number: int,
        phase: str,
        instruction: str,
        transcript: list[dict[str, Any]],
        max_words: int,
    ) -> dict[str, Any]:
        participant = self._public_persona(persona)
        model_settings = persona.get("model_settings") if isinstance(persona.get("model_settings"), dict) else {}
        turn_provider = str(model_settings.get("provider") or provider or DEFAULT_PROVIDER).strip().lower() or DEFAULT_PROVIDER
        turn_model = str(model_settings.get("name") or persona.get("model") or model or DEFAULT_MODEL).strip() or DEFAULT_MODEL
        system_prompt = self._social_system_prompt(persona, personas, topic)
        user_prompt = self._turn_prompt(
            topic=topic,
            meeting_type=meeting_type,
            round_number=round_number,
            phase=phase,
            instruction=instruction,
            transcript=transcript,
        )
        fallback = self._fallback_turn(persona, topic, phase, transcript)
        response = self._call_model(
            prompt=user_prompt,
            system_prompt=system_prompt,
            provider=turn_provider,
            model=turn_model,
            fallback=fallback,
        )
        content = self._compact_conversation_text(response["content"], max_words=max_words)
        return {
            "type": "participant_turn",
            "meeting_id": meeting_id,
            "timestamp": _now_iso(),
            "round": round_number,
            "phase": phase,
            "meeting_type": meeting_type,
            "participant": participant,
            "provider": turn_provider,
            "model": turn_model,
            "content": _clip_text(content, 1800),
            "ok": response["ok"],
            "error": response["error"],
            "prompt_context": {
                "social_awareness": True,
                "chair_led": any(self._is_chair_persona(item) for item in personas),
                "meeting_type": meeting_type,
                "other_participants": [
                    {"id": item.get("id"), "name": item.get("name"), "role": item.get("role")}
                    for item in participants
                    if item.get("id") != participant.get("id")
                ],
                "transcript_turns_supplied": len(transcript),
                "max_words_requested": max_words,
            },
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
                self._knowledge_context(persona),
                (
                    "Instructie: Schrijf alsof je hardop aan tafel spreekt, niet als rapport. "
                    "Houd het kort: 3 tot 5 zinnen, maximaal één kort lijstje als dat echt helpt. "
                    "Help lichtere modellen door expliciet te kiezen voor één punt tegelijk. "
                    "Papegaai eerdere sprekers niet: als je het eens bent, voeg een nieuwe invalshoek, beperking of test toe. "
                    "Als je voorzitter bent, leid jij de volgorde en grijp je in wanneer twee deelnemers elkaar herhalen. "
                    "Voer geen tools uit en claim geen externe acties."
                ),
            ]
            if part
        )

    def _turn_prompt(
        self,
        *,
        topic: str,
        meeting_type: str,
        round_number: int,
        phase: str,
        instruction: str,
        transcript: list[dict[str, Any]],
    ) -> str:
        transcript_text = self._transcript_text(transcript)
        return "\n\n".join(
            [
                f"Onderwerp: {_clip_text(topic, 1600)}",
                f"Vergadertype: {MEETING_TYPE_LABELS.get(meeting_type, 'Team vergadering')}",
                f"Ronde {round_number} ({phase})",
                instruction,
                "Volledige transcriptie tot nu toe:",
                transcript_text or "Nog geen eerdere bijdragen.",
                (
                    "Schrijf als een spreekbeurt in een gesprek. Geen lange inleiding, geen markdown-koppen. "
                    "Gebruik maximaal 80 woorden, tenzij de voorzitter expliciet afsluit. "
                    "Begin meteen met je punt en verwijs waar nuttig naar de vorige spreker. "
                    "Herhaal geen formulering of conclusie die al is gezegd; maak je bijdrage onderscheidend."
                ),
            ]
        )

    def _summarize(
        self,
        *,
        topic: str,
        transcript: list[dict[str, Any]],
        model: str,
        provider: str = DEFAULT_PROVIDER,
        meeting_type: str = "team",
    ) -> dict[str, Any]:
        prompt = "\n\n".join(
            [
                f"Onderwerp: {_clip_text(topic, 1600)}",
                f"Vergadertype: {MEETING_TYPE_LABELS.get(meeting_type, 'Team vergadering')}",
                "Volledige vergaderingstranscriptie:",
                self._transcript_text(transcript) or "Geen bijdragen.",
                (
                    "Sluit het overleg af als korte vergadernotulen. Gebruik gewone zinnen, geen lange paragrafen. "
                    "Noem: wat is besloten, wat blijft open, en wat is de eerstvolgende stap."
                ),
            ]
        )
        fallback = self._fallback_summary(topic, transcript)
        return self._call_model(
            prompt=prompt,
            system_prompt=(
                "Je bent de neutrale synthese-laag van een Ouroboros Vergadering. "
                "Vat alleen kort samen in heldere spreektaal; voer geen tools, shell, browser of agents uit."
            ),
            provider=provider,
            model=model,
            fallback=fallback,
        )

    def _compact_conversation_text(self, text: str, max_words: int = 90) -> str:
        cleaned_lines = []
        for raw_line in str(text or "").splitlines():
            line = raw_line.strip()
            if not line:
                if cleaned_lines and cleaned_lines[-1]:
                    cleaned_lines.append("")
                continue
            line = re.sub(r"^\s{0,3}#{1,6}\s+", "", line)
            line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
            line = re.sub(r"^\s*[-*]\s+", "- ", line)
            cleaned_lines.append(line)
        cleaned = "\n".join(cleaned_lines).strip()
        words = cleaned.split()
        if len(words) <= max_words:
            return cleaned
        clipped = " ".join(words[:max_words]).rstrip(" ,;:")
        return clipped + "..."

    def _looks_like_parroting(self, transcript: list[dict[str, Any]], current_content: str) -> bool:
        current_terms = self._meaningful_terms(current_content)
        if len(current_terms) < 8:
            return False
        current_set = set(current_terms)
        for previous in reversed(transcript[:-1]):
            participant = previous.get("participant") if isinstance(previous.get("participant"), dict) else {}
            if self._is_public_chair(participant):
                continue
            previous_terms = self._meaningful_terms(str(previous.get("content") or ""))
            if len(previous_terms) < 8:
                continue
            previous_set = set(previous_terms)
            overlap = len(current_set & previous_set)
            if overlap < 6:
                continue
            containment = overlap / max(1, min(len(current_set), len(previous_set)))
            jaccard = overlap / max(1, len(current_set | previous_set))
            if containment >= 0.76 or jaccard >= 0.58:
                return True
            if self._shared_bigram_count(previous_terms, current_terms) >= 5:
                return True
        return False

    def _meaningful_terms(self, text: str) -> list[str]:
        stopwords = {
            "aan",
            "als",
            "bij",
            "dat",
            "de",
            "die",
            "dit",
            "een",
            "en",
            "er",
            "het",
            "hier",
            "ik",
            "in",
            "is",
            "met",
            "niet",
            "nog",
            "om",
            "op",
            "te",
            "tot",
            "van",
            "voor",
            "we",
            "wel",
            "zou",
            "moet",
            "naar",
            "ook",
            "the",
            "and",
            "for",
            "that",
            "this",
            "with",
        }
        words = re.findall(r"[A-Za-zÀ-ÿ0-9_:-]{4,}", str(text or "").lower())
        return [word for word in words if word not in stopwords]

    def _shared_bigram_count(self, left: list[str], right: list[str]) -> int:
        left_bigrams = set(zip(left, left[1:]))
        right_bigrams = set(zip(right, right[1:]))
        return len(left_bigrams & right_bigrams)

    def _is_public_chair(self, participant: dict[str, Any]) -> bool:
        return self._is_chair_persona(
            {
                "id": participant.get("id"),
                "name": participant.get("name"),
                "role": participant.get("role"),
            }
        )

    def _call_model(self, *, prompt: str, system_prompt: str, provider: str, model: str, fallback: str) -> dict[str, Any]:
        if self.llm_call is None:
            return {"ok": True, "content": fallback, "error": ""}
        try:
            result = self.llm_call(
                prompt=prompt,
                provider=provider,
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
        if self._is_chair_persona(persona):
            if phase == "opening":
                return (
                    f"Ik open dit overleg over '{_clip_text(topic, 180)}'. We houden het compact: eerst de kern van de tafel, "
                    "daarna de belangrijkste spanning, en dan een besluitbare vervolgstap. Ik geef nu het woord aan de eerste deelnemer."
                )
            if phase == "chair-bridge":
                return (
                    "Ik hoor een gedeelde richting, maar ook nog een keuze die scherper moet. "
                    "Laten we nu per persoon benoemen wat minimaal nodig is om dit verantwoord af te ronden."
                )
            if phase == "intervention":
                return (
                    "Ik onderbreek kort: deze twee bijdragen herhalen elkaar te veel. "
                    "Voeg nu een nieuw onderscheidend punt toe, of benoem expliciet welk risico anders is. Daarna geef ik het woord door."
                )
            if phase in {"plan-bridge", "research-bridge", "research-synthesis"}:
                return (
                    "Ik zet de lijnen even naast elkaar. We hebben richting, maar nog verschil nodig in bewijs, risico en volgorde. "
                    "De volgende spreker voegt daarom één nieuwe laag toe in plaats van dezelfde conclusie te herhalen."
                )
            if phase == "closing":
                return (
                    "Besluit: we werken verder in kleine, controleerbare stappen. "
                    "Open vraag: wie is eigenaar van de eerste toets? "
                    "Volgende stap: formuleer één approval-gated vervolgactie voordat er iets extern wordt uitgevoerd."
                )
        if phase == "brainstorm":
            return (
                f"Vanuit mijn rol als {role} zou ik '{_clip_text(topic, 180)}' eerst kleiner maken. "
                "De kans zit in een helder doel en een zichtbaar resultaat. Het risico is dat we te snel naar uitvoering springen. "
                "Mijn vervolgstap: bepaal eerst wat we willen kunnen toetsen."
            )
        if phase in {"input", "reply"}:
            return (
                f"Ik sluit aan vanuit {role}. Mijn belangrijkste punt is om dit praktisch en toetsbaar te houden. "
                "Ik zou nu één keuze vastleggen, één risico expliciet maken en pas daarna een vervolgstap formuleren."
            )
        if phase in {"plan-slice", "plan-check"}:
            return (
                f"Vanuit {role} zou ik het plan klein houden. De eerste taak moet zichtbaar resultaat geven, "
                "de test moet vooraf bekend zijn en de stopregel moet voorkomen dat we blijven draaien."
            )
        if phase in {"research", "research-layer"}:
            return (
                f"Mijn extra laag vanuit {role}: scheid bron, aanname en conclusie. "
                "Ik zou één bronlaag valideren, één alternatief scenario naast het voorstel zetten en daarna pas kiezen."
            )
        return (
            f"Ik bouw voort op {len(transcript)} eerdere bijdrage(n). De richting lijkt bruikbaar, maar de aannames moeten korter en scherper. "
            "Mijn voorstel is om de scope te verkleinen en één concrete volgende stap zonder tool-uitvoering af te spreken."
        )

    def _fallback_summary(self, topic: str, transcript: list[dict[str, Any]]) -> str:
        names = []
        for item in transcript:
            participant = item.get("participant") if isinstance(item.get("participant"), dict) else {}
            name = participant.get("name")
            if name and name not in names:
                names.append(str(name))
        return (
            "De tafel is het eens dat dit praktisch, controleerbaar en zonder automatische externe acties moet blijven. "
            f"Het grootste risico is onduidelijke eigenaarschap of tool-uitvoering zonder {APPROVAL_PHRASE}. "
            "De eerstvolgende stap is een kleine follow-up formuleren, expliciet een agent kiezen en de bestaande approval-flow gebruiken. "
            f"Voorstel voor vervolgprompt: /agents Werk de vervolgstappen uit voor '{_clip_text(topic, 180)}' "
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

    def _knowledge_context(self, persona: dict[str, Any]) -> str:
        snippets = persona.get("_meeting_knowledge") if isinstance(persona.get("_meeting_knowledge"), list) else []
        if not snippets:
            return ""
        blocks = []
        for item in snippets[:10]:
            if not isinstance(item, dict):
                continue
            label = _clip_text(item.get("label") or item.get("source") or "knowledge", 160)
            source = _clip_text(item.get("source") or "", 240)
            snippet = _clip_text(item.get("snippet") or "", 1200)
            if snippet:
                blocks.append(f"- {label} ({source}): {snippet}")
        if not blocks:
            return ""
        return "Beschikbare read-only kenniscontext voor deze persona:\n" + "\n".join(blocks)


class MeetingStore:
    def __init__(self, directory: Path | None = None):
        self.directory = directory or (_default_data_dir() / "meetings")

    def list_meetings(self, limit: int = 50) -> list[dict[str, Any]]:
        if not self.directory.exists():
            return []
        records: list[dict[str, Any]] = []
        ids = {path.stem for path in self.directory.glob("*.jsonl")}
        ids.update(path.stem for path in self.directory.glob("*.json"))
        sortable: list[tuple[float, str]] = []
        for meeting_id in ids:
            jsonl_path = self.directory / f"{meeting_id}.jsonl"
            record_path = self._record_path(meeting_id)
            mtimes = [path.stat().st_mtime for path in (jsonl_path, record_path) if path.exists()]
            sortable.append((max(mtimes) if mtimes else 0, meeting_id))
        for updated_ts, meeting_id in sorted(sortable, reverse=True)[:limit]:
            path = self.directory / f"{meeting_id}.jsonl"
            events = self._read_events(path) if path.exists() else []
            event_count = len(events)
            record = self._read_record(meeting_id)
            fallback = self._metadata_from_events(events)
            records.append(
                {
                    "meeting_id": meeting_id,
                    "artifact_path": str(path) if path.exists() else "",
                    "record_path": str(self._record_path(meeting_id)),
                    "event_count": event_count,
                    "topic": record.get("topic") or fallback.get("topic", ""),
                    "meeting_type": record.get("meeting_type") or fallback.get("meeting_type", "team"),
                    "status": record.get("status", "recorded"),
                    "summary": _clip_text(record.get("summary") or fallback.get("summary", ""), 900),
                    "participants": record.get("participants") or fallback.get("participants", []),
                    "agent_ids": record.get("agent_ids") or [],
                    "updated_at": datetime.fromtimestamp(updated_ts, timezone.utc).replace(microsecond=0).isoformat(),
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
        events: list[dict[str, Any]] = []
        record = self._read_record(clean_id)
        if not path.exists() and not record:
            raise FileNotFoundError(clean_id)
        if path.exists():
            events = self._read_events(path)
        fallback = self._metadata_from_events(events)
        return {
            "status": record.get("status", "online") if record else "online",
            "meeting_id": clean_id,
            "artifact_path": str(path) if path.exists() else "",
            "record_path": str(self._record_path(clean_id)),
            "events": events,
            "record": record,
            "participants": record.get("participants") or fallback.get("participants", []),
            "rounds": record.get("rounds") or fallback.get("rounds", []),
            "summary": record.get("summary") or fallback.get("summary", ""),
            "topic": record.get("topic") or fallback.get("topic", ""),
            "meeting_type": record.get("meeting_type") or fallback.get("meeting_type", "team"),
            "fake_success": False,
        }

    def save_snapshot(self, meeting_id: str, request: MeetingSaveRequest) -> dict[str, Any]:
        clean_id = _safe_slug(meeting_id)
        if _contains_secret_like(_model_to_dict(request)):
            raise ValueError("Meeting snapshot appears to contain a secret, token, password, or bearer credential.")
        existing = self._read_record(clean_id)
        record = {
            **existing,
            "meeting_id": clean_id,
            "frontend_id": request.frontend_id or existing.get("frontend_id", ""),
            "topic": _clip_text(request.topic or existing.get("topic", ""), 4000),
            "meeting_type": _normalize_meeting_type(request.meeting_type or existing.get("meeting_type", "team")),
            "participants": request.participants or existing.get("participants", []),
            "participant_ids": request.participant_ids or existing.get("participant_ids", []),
            "agent_ids": request.agent_ids or existing.get("agent_ids", []),
            "rounds": request.rounds or existing.get("rounds", []),
            "summary": _clip_text(request.summary or existing.get("summary", ""), 8000),
            "transcript": _clip_text(request.transcript or existing.get("transcript", ""), MAX_TEXT_CHARS * 2),
            "status": request.status or existing.get("status", "saved"),
            "updated_at": _now_iso(),
            "fake_success": False,
        }
        path = self._write_record(clean_id, record)
        return {"status": "saved", "meeting_id": clean_id, "record": record, "record_path": str(path), "fake_success": False}

    def create_meeting(
        self,
        request: MeetingRequest,
        persona_store: PersonaStore,
        llm_call: MeetingLLMCall | None = None,
        knowledge_store: KnowledgeStore | None = None,
        web_context_fetcher: Callable[[dict[str, Any], str], list[dict[str, Any]]] | None = None,
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

        meeting_type = _normalize_meeting_type(request.meeting_type)
        participants = request.participants or ["ouroboros"]
        personas = []
        for persona_id in participants[:12]:
            persona = persona_store.get(persona_id)
            persona = persona or {"id": _safe_slug(persona_id), "name": str(persona_id), "description": "", "tags": []}
            persona = dict(persona)
            policy = enforce_tool_policy(persona)
            knowledge: list[dict[str, Any]] = []
            if knowledge_store is not None and policy.get("can_search_files"):
                knowledge.extend(knowledge_store.snippets_for_persona(persona, request.topic, limit=3))
            if web_context_fetcher is not None and policy.get("can_search_web"):
                web_queries = [request.topic]
                if meeting_type == "brainstorm":
                    web_queries.extend(
                        [
                            f"{request.topic} bronnen onderzoek risico's alternatieven",
                            f"{request.topic} technische lagen ontwerp implementatie bewijs",
                        ]
                    )
                for query in web_queries:
                    knowledge.extend(web_context_fetcher(persona, query)[:2])
            if knowledge:
                persona["_meeting_knowledge"] = self._dedupe_knowledge(knowledge)[:10 if meeting_type == "brainstorm" else 5]
            personas.append(persona)

        meeting_id = f"{int(time.time())}-{uuid.uuid4().hex[:10]}"
        provider = (request.provider or DEFAULT_PROVIDER).strip().lower() or DEFAULT_PROVIDER
        model = (request.model or DEFAULT_MODEL).strip() or DEFAULT_MODEL
        events: list[dict[str, Any]] = [
            {
                "type": "meeting_started",
                "meeting_id": meeting_id,
                "timestamp": _now_iso(),
                "topic": _clip_text(request.topic, 2000),
                "meeting_type": meeting_type,
                "meeting_type_label": MEETING_TYPE_LABELS.get(meeting_type, MEETING_TYPE_LABELS["team"]),
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
            meeting_type=meeting_type,
        )
        events.extend(runner_payload["events"])

        path = self._write_events(meeting_id, events)
        transcript = self._transcript_from_runner(runner_payload)
        self._write_record(
            meeting_id,
            {
                "meeting_id": meeting_id,
                "topic": _clip_text(request.topic, 4000),
                "meeting_type": meeting_type,
                "participants": runner_payload["participants"],
                "participant_ids": [str(item.get("id")) for item in runner_payload["participants"] if item.get("id")],
                "agent_ids": [],
                "rounds": runner_payload["rounds"],
                "summary": runner_payload["summary"],
                "transcript": transcript,
                "status": "completed",
                "provider": provider,
                "model": model,
                "artifact_path": str(path),
                "created_at": events[0]["timestamp"],
                "updated_at": _now_iso(),
                "tool_policy": self.tool_policy(),
                "fake_success": False,
            },
        )
        return {
            "status": "recorded",
            "meeting_id": meeting_id,
            "artifact_path": str(path),
            "record_path": str(self._record_path(meeting_id)),
            "event_count": len(events),
            "meeting_type": meeting_type,
            "events": events,
            "participants": runner_payload["participants"],
            "rounds": runner_payload["rounds"],
            "summary": runner_payload["summary"],
            "transcript": transcript,
            "tool_policy": self.tool_policy(),
            "fake_success": False,
        }

    def _dedupe_knowledge(self, knowledge: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in knowledge:
            if not isinstance(item, dict):
                continue
            key = f"{item.get('source') or ''}:{str(item.get('snippet') or '')[:180]}"
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result

    def tool_policy(self) -> dict[str, Any]:
        return {
            "mode": "no_tools",
            "cline_execution": False,
            "shell": False,
            "browser": False,
            "write_tools": False,
            "read_only_web_context": "persona_brave_search_when_enabled",
            "artifact_write": "jsonl_and_json_snapshot",
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

    def _record_path(self, meeting_id: str) -> Path:
        return (self.directory / f"{_safe_slug(meeting_id)}.json").resolve()

    def _read_record(self, meeting_id: str) -> dict[str, Any]:
        path = self._record_path(meeting_id)
        try:
            path.relative_to(self.directory.resolve())
        except ValueError:
            return {}
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    def _read_events(self, path: Path) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                item = json.loads(line)
                if isinstance(item, dict):
                    events.append(item)
        except Exception:
            return events
        return events

    def _metadata_from_events(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        participants_by_id: dict[str, dict[str, Any]] = {}
        rounds: list[dict[str, Any]] = []
        topic = ""
        meeting_type = "team"
        summary = ""
        for index, event in enumerate(events):
            event_type = str(event.get("type") or "")
            if event_type == "meeting_started":
                topic = topic or str(event.get("topic") or "")
                meeting_type = _normalize_meeting_type(event.get("meeting_type") or meeting_type)
                continue
            participant = event.get("participant") if isinstance(event.get("participant"), dict) else {}
            if participant:
                participant_id = str(participant.get("id") or participant.get("name") or f"participant-{index}")
                participants_by_id.setdefault(
                    participant_id,
                    {
                        "id": participant_id,
                        "name": str(participant.get("name") or participant_id),
                        "role": str(participant.get("role") or ""),
                        "tone": str(participant.get("tone") or ""),
                        "rules": participant.get("rules", []) if isinstance(participant.get("rules"), list) else [],
                        "tags": participant.get("tags", []) if isinstance(participant.get("tags"), list) else [],
                    },
                )
            if event_type in {"participant_turn", "participant_note"}:
                rounds.append(event)
                continue
            if event_type == "meeting_summary":
                summary = str(event.get("summary") or event.get("content") or "")
        return {
            "topic": _clip_text(topic, 4000),
            "meeting_type": meeting_type,
            "participants": list(participants_by_id.values()),
            "rounds": rounds,
            "summary": _clip_text(summary, 8000),
        }

    def _write_record(self, meeting_id: str, record: dict[str, Any]) -> Path:
        if _contains_secret_like(record):
            raise ValueError("Meeting record write blocked because content appears to contain a secret.")
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self._record_path(meeting_id)
        try:
            path.relative_to(self.directory.resolve())
        except ValueError as exc:
            raise ValueError("Meeting record path escapes meeting directory.") from exc
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(path)
        return path

    def _transcript_from_runner(self, runner_payload: dict[str, Any]) -> str:
        parts = []
        for turn in runner_payload.get("rounds", []):
            participant = turn.get("participant") if isinstance(turn.get("participant"), dict) else {}
            name = participant.get("name") or "Persona"
            parts.append(f"{name} (ronde {turn.get('round')} / {turn.get('phase')}):\n{turn.get('content', '')}")
        if runner_payload.get("summary"):
            parts.append(f"Consensus & Actiepunten:\n{runner_payload['summary']}")
        return "\n\n---\n\n".join(parts)


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
        return self.meetings.create_meeting(
            request,
            self.personas,
            llm_call=self._call_model_provider,
            knowledge_store=self.knowledge,
            web_context_fetcher=self._brave_knowledge_for_persona,
        )

    def development_team(self, request: DevelopmentTeamRequest) -> dict[str, Any]:
        if _contains_secret_like({"prompt": request.prompt, "persona_ids": request.persona_ids, "agent_ids": request.agent_ids}):
            raise ValueError("Development-team prompt appears to contain a secret, token, password, or bearer credential.")

        provider = str(request.provider or DEFAULT_PROVIDER).strip().lower() or DEFAULT_PROVIDER
        requested_model = str(request.model or "").strip()
        model_hints = CODING_MODEL_HINTS.get(provider, ())
        model = requested_model or (model_hints[0] if model_hints else DEFAULT_MODEL)
        max_iterations = max(1, min(int(getattr(request, "max_iterations", 3) or 3), 8))
        persona_ids = request.persona_ids or ["de-voorzitter", "de-ontwerper", "de-criticus"]
        agent_ids = request.agent_ids or ["codex"]
        personas: list[dict[str, Any]] = []
        for persona_id in persona_ids[:12]:
            persona = self.personas.get(persona_id)
            if persona:
                personas.append(dict(persona))
        personas = MeetingRunner()._ordered_personas(personas)
        public_personas = [MeetingRunner()._public_persona(persona) for persona in personas]
        slash_command = self._development_slash_command(agent_ids)
        clipped_prompt = _clip_text(request.prompt, 3000)
        slash_prompt = (
            f"{slash_command} {clipped_prompt}\n\n"
            "Ontwikkelteam-protocol:\n"
            "- Werk iteratief: plan, kleine wijziging, test, review.\n"
            f"- Stop na maximaal {max_iterations} pogingen zonder nieuwe informatie.\n"
            "- Laat de voorzitter ingrijpen bij herhaling, tunnelvisie of test-loops.\n"
            "- Rapporteer welke bestanden zijn aangepast en welke tests zijn gedraaid.\n"
            f"- Gebruik alleen bestaande approval-gated routes; approval phrase blijft {APPROVAL_PHRASE}."
        )
        rounds = [
            {
                "id": f"dev-{uuid.uuid4().hex[:8]}-intake",
                "phase": "intake",
                "participantName": "De voorzitter",
                "participantId": "de-voorzitter",
                "content": (
                    "Ik start dit als ontwikkelteam, maar voer hier nog niets uit. Eerst bakenen we succes af, kiezen we de uitvoerende agent "
                    f"en zetten we een stopregel: maximaal {max_iterations} iteraties zonder nieuwe testinformatie."
                ),
                "createdAt": _now_iso(),
            },
            {
                "id": f"dev-{uuid.uuid4().hex[:8]}-route",
                "phase": "implementation-route",
                "participantName": "Ouroboros engineer",
                "participantId": "ouroboros-engineer",
                "content": (
                    f"Gebruik {provider} / {model} als gekozen modelcontext waar de agent-runtime dat ondersteunt. "
                    "Laat Codex, Roo, Claude of Gemini via de bestaande Cockpit-koppelingen werken; deze route maakt alleen de opdracht klaar."
                ),
                "createdAt": _now_iso(),
            },
            {
                "id": f"dev-{uuid.uuid4().hex[:8]}-test",
                "phase": "test-plan",
                "participantName": "Criticus",
                "participantId": "de-criticus",
                "content": (
                    "Voor elke wijziging is er een verificatie nodig: gerichte tests eerst, daarna build of smoke-test. "
                    "Als een test faalt zonder duidelijke hypothese, terug naar analyse in plaats van dezelfde fix herhalen."
                ),
                "createdAt": _now_iso(),
            },
            {
                "id": f"dev-{uuid.uuid4().hex[:8]}-guard",
                "phase": "loop-guard",
                "participantName": "De voorzitter",
                "participantId": "de-voorzitter",
                "content": (
                    "Ik houd de volgorde vast: uitvoerder, reviewer, test, besluit. Als twee rollen elkaar napraten of rondjes draaien, "
                    "onderbreek ik en vraag ik om een nieuw bewijsstuk, kleiner doel of expliciete stop."
                ),
                "createdAt": _now_iso(),
            },
        ]
        return {
            "status": "planned",
            "execution": "not_executed_by_ouroboros_chat_router",
            "approval_required": True,
            "approval_phrase": APPROVAL_PHRASE,
            "approval_supplied": str(request.approval or "").strip() == APPROVAL_PHRASE,
            "prompt": clipped_prompt,
            "provider": provider,
            "model": model,
            "recommended_models": {
                key: list(value)
                for key, value in CODING_MODEL_HINTS.items()
            },
            "personas": public_personas,
            "agent_ids": agent_ids[:12],
            "agent_command": slash_command,
            "slash_prompt": slash_prompt,
            "rounds": rounds,
            "next_route": "/api/cockpit/chat",
            "safety_note": (
                "Dit ontwikkelteam bereidt agentisch coderen voor, maar voert geen shell, browser, patch of CLI uit. "
                "Werkelijke uitvoering blijft bij de bestaande Cockpit approval-flow."
            ),
            "fake_success": False,
        }

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
        web_knowledge = self._brave_knowledge_for_persona(persona, request.prompt) if policy.get("can_search_web") else []
        knowledge = [*web_knowledge, *knowledge]
        assembled = self.prompt_assembler.assemble(
            persona=persona,
            memories=memories,
            knowledge=knowledge,
            recent_history=recent_history,
            user_message=request.prompt,
            attachment_context=attachment_payload["context"],
        )
        system_prompt = "\n\n".join(part for part in [assembled["system_prompt"], request.system_prompt or ""] if str(part).strip())
        response = self._call_model_provider(
            prompt=assembled["user_prompt"],
            provider=provider,
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
            "provider": response.get("provider", provider),
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
            "approval_phrase": APPROVAL_PHRASE,
            "approval_supplied": str(request.approval or "").strip() == APPROVAL_PHRASE,
            "files_received": [_clip_text(path, 240) for path in request.files[:20]],
            "attachments": attachment_payload["records"],
            "transient_attachment_context": bool(attachment_payload["context"]),
            "network_call_made": bool(response.get("network_call_made")) or provider not in {DEFAULT_PROVIDER, "local", "ouroboros", "ollama"},
            "fake_success": False,
            "local_only": provider in {DEFAULT_PROVIDER, "local", "ouroboros", "ollama"} and not response.get("network_call_made"),
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

    def _development_slash_command(self, agent_ids: list[str]) -> str:
        preferred_order = ["codex", "roo", "claude", "deepseek", "atlas", "ruflo", "agents"]
        selected = [str(item or "").strip().lower().lstrip("/") for item in agent_ids if str(item or "").strip()]
        for agent in [*selected, *preferred_order]:
            if agent in preferred_order:
                return f"/{agent}"
        return "/codex"

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

    def model_options(self) -> dict[str, Any]:
        key_status: dict[str, Any] = {}
        subscription_statuses: dict[str, Any] = {}
        openai_models = list(OPENAI_MODEL_OPTIONS)
        try:
            from controller.api_key_store import provider_key_status

            key_status = provider_key_status()
        except Exception:
            key_status = {}
        try:
            from controller.subscription_store import subscription_status

            subscription_statuses = subscription_status()
        except Exception:
            subscription_statuses = {}
        try:
            from controller.openai_model_catalog import openai_api_model_choices

            openai_models = list(openai_api_model_choices()) or openai_models
        except Exception:
            pass

        provider_models = {
            **PROVIDER_MODEL_OPTIONS,
            "openai": {**PROVIDER_MODEL_OPTIONS["openai"], "models": openai_models, "default_model": openai_models[0] if openai_models else "gpt-5.4-mini"},
        }
        providers: list[dict[str, Any]] = [
            {
                "id": "ollama",
                "label": "Ollama local",
                "models": self._local_ollama_models(),
                "default_model": DEFAULT_MODEL,
                "configured": True,
                "local_only": True,
                "key_source": "local",
                "direct_chat": True,
            }
        ]
        for provider_id, config in provider_models.items():
            key = key_status.get(provider_id) if isinstance(key_status.get(provider_id), dict) else {}
            sub = subscription_statuses.get(provider_id) if isinstance(subscription_statuses.get(provider_id), dict) else {}
            key_configured = bool(key.get("configured"))
            subscription_has_credential = bool(sub.get("active") and sub.get("has_credential") and not sub.get("expired"))
            api_key_ready = bool(sub.get("api_key_ready"))
            models = _dedupe_strings(config.get("models", []), fallback=tuple(sub.get("models", []) if isinstance(sub.get("models"), list) else ()))
            providers.append(
                {
                    "id": provider_id,
                    "label": config.get("label", provider_id),
                    "models": models,
                    "default_model": config.get("default_model") or (models[0] if models else ""),
                    "configured": bool(key_configured or subscription_has_credential),
                    "direct_chat": bool(key_configured or api_key_ready),
                    "key_source": key.get("source") if key_configured else (f"subscription:{sub.get('auth_mode')}" if subscription_has_credential else "missing"),
                    "auth_mode": sub.get("auth_mode", ""),
                    "subscription_status": sub.get("status", "inactive") if sub else "inactive",
                    "api_key_ready": api_key_ready or key_configured,
                    "local_only": False,
                }
            )

        try:
            from controller.roo_cli_runtime import ROO_OAUTH_MODEL, ROO_OAUTH_PROVIDER, roo_cli_status, roo_cloud_models

            roo_status = roo_cli_status()
            cloud = roo_cloud_models(timeout_seconds=2, max_models=120) if roo_status.get("available") else {}
            roo_models = _dedupe_strings(cloud.get("models", []) if isinstance(cloud.get("models"), list) else [], fallback=(ROO_OAUTH_MODEL,))
            providers.append(
                {
                    "id": ROO_OAUTH_PROVIDER,
                    "label": "Roo Cloud OAuth",
                    "models": roo_models,
                    "default_model": ROO_OAUTH_MODEL,
                    "configured": bool(roo_status.get("oauth_logged_in") or roo_status.get("auth", {}).get("ok")),
                    "direct_chat": False,
                    "key_source": "roo_oauth",
                    "auth_mode": "oauth",
                    "subscription_status": str(roo_status.get("status") or "unknown"),
                    "agent_runtime_only": True,
                    "local_only": False,
                }
            )
        except Exception:
            pass

        brave = key_status.get("brave") if isinstance(key_status.get("brave"), dict) else {}
        return {
            "status": "online",
            "providers": providers,
            "brave": {
                "configured": bool(brave.get("configured")),
                "key_source": brave.get("source", "missing"),
                "used_for_persona_web_search": True,
            },
            "fake_success": False,
        }

    def _local_ollama_models(self) -> list[str]:
        models: list[Any] = []
        if self.ollama_client is not None and callable(getattr(self.ollama_client, "list_models", None)):
            try:
                models = list(self.ollama_client.list_models())
            except Exception:
                models = []
        if not models:
            try:
                import requests

                base_url = (os.getenv("OLLAMA_HOST") or os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434").rstrip("/")
                if base_url.endswith("/api"):
                    base_url = base_url[:-4]
                response = requests.get(f"{base_url}/api/tags", timeout=2.0)
                response.raise_for_status()
                models = [item.get("name") for item in response.json().get("models", []) if isinstance(item, dict)]
            except Exception:
                models = []
        return _dedupe_strings(models, fallback=LOCAL_OLLAMA_FALLBACK_MODELS)

    def _cockpit_provider_api_keys(self) -> dict[str, str]:
        keys: dict[str, str] = {}
        try:
            from controller.api_key_store import load_provider_api_keys

            keys.update(load_provider_api_keys())
        except Exception:
            pass
        try:
            from controller.subscription_store import subscription_api_key_for_provider

            for provider_id in PROVIDER_MODEL_OPTIONS:
                if keys.get(provider_id):
                    continue
                value = subscription_api_key_for_provider(provider_id)
                if value:
                    keys[provider_id] = value
        except Exception:
            pass
        return keys

    def _brave_knowledge_for_persona(self, persona: dict[str, Any], query: str) -> list[dict[str, Any]]:
        clean_query = _clip_text(query, 400)
        if not clean_query:
            return []
        try:
            from controller.brave_search import search_brave_llm_context

            result = search_brave_llm_context(clean_query, maximum_number_of_urls=5)
        except Exception as exc:
            return [
                {
                    "label": "Brave Search",
                    "source": "brave:error",
                    "snippet": f"Brave Search context kon niet worden opgehaald: {exc}",
                    "score": 1,
                }
            ]
        if result.get("status") != "success":
            reason = result.get("reason") or result.get("status") or "unavailable"
            return [
                {
                    "label": "Brave Search",
                    "source": "brave:status",
                    "snippet": f"Brave Search is niet beschikbaar voor deze beurt: {reason}.",
                    "score": 1,
                }
            ]
        document = str(result.get("document") or "").strip()
        if not document:
            return []
        return [
            {
                "label": "Brave Search",
                "source": "brave:llm_context",
                "snippet": document[:4000],
                "score": 5,
                "source_urls": result.get("source_urls") or [],
                "taint": "untrusted_web",
            }
        ]

    def _call_model_provider(
        self,
        *,
        prompt: str,
        provider: str,
        model: str,
        system_prompt: str,
        history: list[dict[str, str]],
        images: list[str] | None = None,
    ) -> dict[str, Any]:
        provider_id = str(provider or DEFAULT_PROVIDER).strip().lower() or DEFAULT_PROVIDER
        if provider_id in {DEFAULT_PROVIDER, "local", "ouroboros", "ollama"}:
            result = self._call_ollama(
                prompt=prompt,
                model=model,
                system_prompt=system_prompt,
                history=history,
                images=images,
            )
            return {**result, "provider": DEFAULT_PROVIDER, "model": model}
        try:
            from controller.multi_api_router import MultiAPIRouter

            router = MultiAPIRouter(api_keys=self._cockpit_provider_api_keys())
            routed = asyncio.run(
                router.route_chat(
                    provider=provider_id,
                    model=model,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    history=history,
                )
            )
        except Exception as exc:
            return {"ok": False, "content": "", "error": str(exc), "provider": provider_id, "model": model}
        content = str(routed.get("response") or routed.get("content") or "").strip()
        ok = routed.get("status") == "success" and bool(content)
        error = str(routed.get("error") or routed.get("reason") or routed.get("message") or "")
        return {
            "ok": ok,
            "content": content,
            "error": "" if ok else error or f"{provider_id} returned no response.",
            "provider": routed.get("provider", provider_id),
            "model": routed.get("model", model),
            "raw_status": routed.get("status"),
            "network_call_made": routed.get("network_call_made", False),
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
        return await asyncio.to_thread(_service_from_request(request).chat, request_body)
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


@ouroboros_chat_router.get("/model-options")
async def get_model_options(request: Request) -> dict[str, Any]:
    return await asyncio.to_thread(_service_from_request(request).model_options)


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


@ouroboros_chat_router.post("/development-team")
async def plan_development_team(request_body: DevelopmentTeamRequest, request: Request) -> dict[str, Any]:
    service = _service_from_request(request)
    try:
        return await asyncio.to_thread(service.development_team, request_body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


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
        return await asyncio.to_thread(service.create_meeting, request_body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@ouroboros_chat_router.put("/meetings/{meeting_id}")
async def save_meeting_snapshot(meeting_id: str, request_body: MeetingSaveRequest, request: Request) -> dict[str, Any]:
    try:
        return _service_from_request(request).meetings.save_snapshot(meeting_id, request_body)
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
    "DevelopmentTeamRequest",
    "MeetingRequest",
    "MeetingSaveRequest",
    "OuroborosChatRequest",
    "OuroborosChatService",
    "PersonaRequest",
    "init_ouroboros_chat_routes",
    "ouroboros_chat_router",
]
