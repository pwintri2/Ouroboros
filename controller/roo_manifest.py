"""Roo capability inventory manifest for Ouroboros integration.

Provides read-only introspection of Roo Code's tool ecosystem, modes, and
task lifecycle patterns. This module documents capabilities without executing
them - the actual adapters live in controller/roo_tools.py.
"""

from __future__ import annotations

from typing import Any


# Roo tool names as implemented in controller/roo_tools.py
ROO_TOOLS: tuple[str, ...] = (
    "roo_read_file",
    "roo_list_files",
    "roo_search_files",
    "roo_write_file_preview",
    "roo_write_file",
    "roo_apply_patch_preview",
    "roo_apply_patch",
    "roo_execute_command",
    "roo_attempt_completion",
    "roo_ask_followup_question",
)

# Roo modes from Roo Code documentation
ROO_MODES: tuple[str, ...] = (
    "code",
    "architect",
    "ask",
    "debug",
    "custom",
)

# Task lifecycle states observed from Roo Code
ROO_TASK_STATES: tuple[str, ...] = (
    "idle",
    "planning",
    "executing",
    "blocked",
    "completed",
    "failed",
)


def get_roo_status() -> dict[str, Any]:
    """Get Roo adapter status and capability inventory."""
    return {
        "status": "online",
        "source": "/home/pwintri2/Roo-code",
        "available": True,
        "adapter_type": "local_python",
        "tools": {
            "file_operations": [
                {
                    "name": "roo_read_file",
                    "description": "Read file contents with optional offset/limit",
                    "approval_required": False,
                },
                {
                    "name": "roo_list_files",
                    "description": "List files in directory with recursive option",
                    "approval_required": False,
                },
                {
                    "name": "roo_search_files",
                    "description": "Search files by regex pattern",
                    "approval_required": False,
                },
            ],
            "write_operations": [
                {
                    "name": "roo_write_file_preview",
                    "description": "Preview file changes with unified diff",
                    "approval_required": False,
                },
                {
                    "name": "roo_write_file",
                    "description": "Write file content (requires Akkoord approval)",
                    "approval_required": True,
                },
                {
                    "name": "roo_apply_patch_preview",
                    "description": "Preview multi-file patch operations",
                    "approval_required": False,
                },
                {
                    "name": "roo_apply_patch",
                    "description": "Apply multi-file patch (requires Akkoord approval)",
                    "approval_required": True,
                },
            ],
            "execution": [
                {
                    "name": "roo_execute_command",
                    "description": "Execute shell command via safe_shell (requires Akkoord)",
                    "approval_required": True,
                },
            ],
            "completion": [
                {
                    "name": "roo_attempt_completion",
                    "description": "Mark task as completed with result",
                    "approval_required": False,
                },
                {
                    "name": "roo_ask_followup_question",
                    "description": "Ask user for clarification or input",
                    "approval_required": False,
                },
            ],
        },
        "modes": [
            {
                "name": "code",
                "description": "Everyday coding, edits, and file operations",
            },
            {
                "name": "architect",
                "description": "Plan systems, specs, and migrations",
            },
            {
                "name": "ask",
                "description": "Fast answers, explanations, and documentation",
            },
            {
                "name": "debug",
                "description": "Trace issues, add logs, isolate root causes",
            },
            {
                "name": "custom",
                "description": "Specialized modes for team workflows",
            },
        ],
        "task_lifecycle": [
            {"state": "idle", "description": "No active task"},
            {"state": "planning", "description": "Analyzing requirements and planning approach"},
            {"state": "executing", "description": "Running tool operations"},
            {"state": "blocked", "description": "Awaiting user approval or input"},
            {"state": "completed", "description": "Task finished successfully"},
            {"state": "failed", "description": "Task failed with error"},
        ],
        "approval_required_for": ["roo_write_file", "roo_apply_patch", "roo_execute_command"],
        "required_approval_phrase": "Akkoord",
        "workspace": "/workspace",
    }


def get_tool_schema(tool_name: str) -> dict[str, Any] | None:
    """Get detailed schema for a specific Roo tool."""
    tool_schemas: dict[str, dict[str, Any]] = {
        "roo_read_file": {
            "name": "roo_read_file",
            "parameters": {
                "path": {"type": "string", "required": True, "description": "File path to read"},
                "offset": {"type": "integer", "required": False, "description": "Starting line number (1-indexed)"},
                "limit": {"type": "integer", "required": False, "description": "Number of lines to read"},
            },
            "returns": {
                "status": "string",
                "stdout": "string",
                "result": {"path": "string", "line_count": "integer"},
            },
        },
        "roo_list_files": {
            "name": "roo_list_files",
            "parameters": {
                "path": {"type": "string", "required": False, "default": ".", "description": "Directory path"},
                "recursive": {"type": "boolean", "required": False, "default": False},
                "limit": {"type": "integer", "required": False, "default": 200},
            },
            "returns": {
                "status": "string",
                "stdout": "string",
                "result": {"path": "string", "items": ["string"], "truncated": "boolean"},
            },
        },
        "roo_search_files": {
            "name": "roo_search_files",
            "parameters": {
                "path": {"type": "string", "required": False, "default": "."},
                "regex": {"type": "string", "required": True, "description": "Regex pattern to search"},
                "file_pattern": {"type": "string", "required": False, "description": "Glob pattern for files"},
                "limit": {"type": "integer", "required": False, "default": 100},
            },
            "returns": {
                "status": "string",
                "stdout": "string",
                "result": {"matches": [{"path": "string", "line": "integer", "text": "string"}], "count": "integer"},
            },
        },
        "roo_write_file_preview": {
            "name": "roo_write_file_preview",
            "parameters": {
                "path": {"type": "string", "required": True},
                "content": {"type": "string", "required": True},
            },
            "returns": {
                "status": "string",
                "stdout": "string",  # unified diff
                "result": {"path": "string", "diff_view": "string", "bytes_after": "integer"},
            },
        },
        "roo_write_file": {
            "name": "roo_write_file",
            "parameters": {
                "path": {"type": "string", "required": True},
                "content": {"type": "string", "required": True},
                "approval": {"type": "string", "required": True, "description": "Must be 'Akkoord'"},
            },
            "returns": {
                "status": "string",
                "stdout": "string",
                "approval_status": "string",
                "result": {"path": "string", "bytes_written": "integer"},
            },
        },
        "roo_apply_patch_preview": {
            "name": "roo_apply_patch_preview",
            "parameters": {
                "patch": {"type": "string", "required": True, "description": "Patch in Roo format"},
            },
            "returns": {
                "status": "string",
                "stdout": "string",
                "result": {"operations": [{"type": "string", "path": "string"}], "operation_count": "integer"},
            },
        },
        "roo_apply_patch": {
            "name": "roo_apply_patch",
            "parameters": {
                "patch": {"type": "string", "required": True},
                "approval": {"type": "string", "required": True, "description": "Must be 'Akkoord'"},
            },
            "returns": {
                "status": "string",
                "stdout": "string",
                "approval_status": "string",
                "result": {"changed_paths": ["string"], "operation_count": "integer"},
            },
        },
        "roo_execute_command": {
            "name": "roo_execute_command",
            "parameters": {
                "command": {"type": "string", "required": True},
                "approval": {"type": "string", "required": True, "description": "Must be 'Akkoord'"},
                "timeout": {"type": "integer", "required": False, "default": 20},
            },
            "returns": {
                "status": "string",
                "stdout": "string",
                "stderr": "string",
                "exit_code": "integer",
                "approval_status": "string",
            },
        },
        "roo_attempt_completion": {
            "name": "roo_attempt_completion",
            "parameters": {
                "result": {"type": "string", "required": True},
                "command": {"type": "string", "required": False},
            },
            "returns": {
                "status": "string",
                "stdout": "string",
                "result": {"result": "string", "final_command": "string"},
            },
        },
        "roo_ask_followup_question": {
            "name": "roo_ask_followup_question",
            "parameters": {
                "question": {"type": "string", "required": True},
            },
            "returns": {
                "status": "string",
                "stdout": "string",
                "approval_status": "string",
                "result": {"question": "string"},
            },
        },
    }
    return tool_schemas.get(tool_name)


def list_all_tools() -> list[str]:
    """List all available Roo tool names."""
    return list(ROO_TOOLS)


def list_all_modes() -> list[str]:
    """List all available Roo modes."""
    return list(ROO_MODES)


def list_task_states() -> list[str]:
    """List all Roo task lifecycle states."""
    return list(ROO_TASK_STATES)
