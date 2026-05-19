from __future__ import annotations

from typing import Any


DEFAULT_TOOLS: dict[str, bool] = {
    "web_search": False,
    "file_search": True,
    "code_execution": False,
    "calendar_email": False,
    "local_shell": False,
    "image_generation": False,
    "document_generation": False,
}

TOOL_LABELS: dict[str, str] = {
    "web_search": "Web search",
    "file_search": "File search",
    "code_execution": "Code execution",
    "calendar_email": "Calendar/email",
    "local_shell": "Local shell",
    "image_generation": "Image generation",
    "document_generation": "Document generation",
}

MUTATING_TOOLS = {"code_execution", "calendar_email", "local_shell", "image_generation", "document_generation"}


def normalized_tools(value: Any | None) -> dict[str, bool]:
    tools = dict(DEFAULT_TOOLS)
    if isinstance(value, dict):
        for key in tools:
            tools[key] = bool(value.get(key, tools[key]))
    return tools


def tool_catalog() -> dict[str, Any]:
    return {
        "status": "online",
        "tools": [
            {
                "id": tool_id,
                "label": TOOL_LABELS[tool_id],
                "default_enabled": enabled,
                "approval_required": tool_id in MUTATING_TOOLS,
                "available": tool_id in {"file_search", "web_search"},
            }
            for tool_id, enabled in DEFAULT_TOOLS.items()
        ],
        "permission_gated": sorted(MUTATING_TOOLS),
        "fake_success": False,
    }


def enforce_tool_policy(persona: dict[str, Any]) -> dict[str, Any]:
    tools = normalized_tools(persona.get("tools"))
    blocked = [tool_id for tool_id, enabled in tools.items() if enabled and tool_id in MUTATING_TOOLS]
    return {
        "tools": tools,
        "requires_approval": blocked,
        "can_search_files": bool(tools.get("file_search")),
        "can_search_web": bool(tools.get("web_search")),
    }
