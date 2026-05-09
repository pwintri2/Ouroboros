"""Roo-inspired local tool adapters for Ouroboros.

These adapters intentionally live inside the Python backend instead of calling
the VS Code extension directly. They preserve the useful Roo tool semantics
while enforcing Ouroboros' Docker/workspace and approval gates.
"""

from __future__ import annotations

import difflib
import fnmatch
import os
import re
import time
from pathlib import Path
from typing import Any, Iterable

from controller.safe_shell import run_safe_shell, workspace_root

try:
    from controller.ouroboros_self_context import codex_path, roo_path, ruflo_path
except Exception:
    def ruflo_path() -> Path:
        return Path(os.getenv("WINTRIP_RUFLO_PATH") or "/home/pwintri2/ruflo").expanduser().resolve()

    def codex_path() -> Path:
        return Path(os.getenv("WINTRIP_CODEX_PATH") or "/home/pwintri2/Codex").expanduser().resolve()

    def roo_path() -> Path:
        return Path(os.getenv("WINTRIP_ROO_CODE_PATH") or os.getenv("WINTRIP_ROO_PATH") or "/home/pwintri2/Roo-code").expanduser().resolve()


ROO_TOOL_NAMES: tuple[str, ...] = (
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


def roo_tools_status() -> dict[str, Any]:
    roots = _allowed_roots()
    return {
        "status": "online",
        "available": True,
        "source": str(roo_path()),
        "local_python_adapters": list(ROO_TOOL_NAMES),
        "approval_required_for": ["roo_write_file", "roo_apply_patch", "roo_execute_command"],
        "workspace": str(workspace_root()),
        "allowed_roots": [str(root) for root in roots],
        "configured_agent_roots": {
            "wintripai": str(workspace_root()),
            "ruflo": str(ruflo_path()),
            "roo": str(roo_path()),
            "codex": str(codex_path()),
        },
        "path_aliases": ["workspace/...", "wintripai/...", "ruflo/...", "roo/...", "codex/..."],
        "fake_success": False,
    }


def attempt_completion(result: str, command: str | None = None) -> dict[str, Any]:
    started = time.time()
    return _result(
        "roo_attempt_completion",
        "success",
        stdout=f"Taak voltooid: {result}",
        result={"result": result, "final_command": command},
        started=started,
    )


def ask_followup_question(question: str) -> dict[str, Any]:
    started = time.time()
    return _result(
        "roo_ask_followup_question",
        "blocked",
        stdout=f"Vraag aan Philip: {question}",
        result={"question": question},
        approval_status="pending_philip_akkoord",
        started=started,
    )


def read_file(path: str, offset: int | None = None, limit: int | None = None) -> dict[str, Any]:
    started = time.time()
    try:
        target = _resolve_workspace_path(path)
        if not target.exists():
            return _result("roo_read_file", "error", stderr=f"Bestand bestaat niet: {path}", started=started)
        if target.is_dir():
            return _result("roo_read_file", "error", stderr=f"Pad is een map, gebruik roo_list_files: {path}", started=started)
        text = target.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        if offset is not None or limit is not None:
            start = max(1, int(offset or 1)) - 1
            end = start + max(1, int(limit or 200))
            selected = lines[start:end]
            text = "\n".join(selected)
            if selected and text:
                text += "\n"
        return _result(
            "roo_read_file",
            "success",
            stdout=text,
            result={"path": str(target), "line_count": len(lines)},
            started=started,
        )
    except Exception as exc:
        return _result("roo_read_file", "error", stderr=str(exc), started=started)


def list_files(path: str = ".", recursive: bool = False, limit: int = 200) -> dict[str, Any]:
    started = time.time()
    try:
        target = _resolve_workspace_path(path or ".")
        if not target.exists():
            return _result("roo_list_files", "error", stderr=f"Pad bestaat niet: {path}", started=started)
        max_items = max(1, min(int(limit or 200), 1000))
        items: list[str] = []
        if target.is_file():
            items.append(_display_path(target))
        elif recursive:
            for dirpath, dirnames, filenames in os.walk(target):
                dirnames[:] = sorted(_skip_hidden(dirnames))
                for name in sorted(_skip_hidden(filenames)):
                    items.append(_display_path((Path(dirpath) / name).resolve()))
                    if len(items) >= max_items:
                        break
                if len(items) >= max_items:
                    break
        else:
            for child in sorted(target.iterdir(), key=lambda item: item.name):
                if child.name.startswith("."):
                    continue
                suffix = "/" if child.is_dir() else ""
                items.append(f"{_display_path(child.resolve())}{suffix}")
                if len(items) >= max_items:
                    break
        stdout = "\n".join(items)
        if stdout:
            stdout += "\n"
        return _result(
            "roo_list_files",
            "success",
            stdout=stdout,
            result={"path": str(target), "items": items, "truncated": len(items) >= max_items},
            started=started,
        )
    except Exception as exc:
        return _result("roo_list_files", "error", stderr=str(exc), started=started)


def search_files(
    path: str,
    regex: str,
    file_pattern: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    started = time.time()
    try:
        target = _resolve_workspace_path(path or ".")
        pattern = re.compile(regex)
        max_matches = max(1, min(int(limit or 100), 500))
        matches: list[dict[str, Any]] = []
        files = [target] if target.is_file() else _iter_files(target)
        for file_path in files:
            rel = _display_path(file_path.resolve())
            if file_pattern and not fnmatch.fnmatch(rel, file_pattern):
                continue
            try:
                lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for line_no, line in enumerate(lines, start=1):
                if pattern.search(line):
                    matches.append({"path": rel, "line": line_no, "text": line[:500]})
                    if len(matches) >= max_matches:
                        break
            if len(matches) >= max_matches:
                break
        stdout = "\n".join(f"{m['path']}:{m['line']}:{m['text']}" for m in matches)
        if stdout:
            stdout += "\n"
        return _result(
            "roo_search_files",
            "success",
            stdout=stdout,
            result={"matches": matches, "count": len(matches), "truncated": len(matches) >= max_matches},
            started=started,
        )
    except Exception as exc:
        return _result("roo_search_files", "error", stderr=str(exc), started=started)


def write_file_preview(path: str, content: str) -> dict[str, Any]:
    started = time.time()
    try:
        target = _resolve_workspace_path(path)
        new_content = "" if content is None else str(content)
        previous = target.read_text(encoding="utf-8", errors="replace") if target.exists() else ""
        diff = _unified_diff(previous, new_content, path)
        return _result(
            "roo_write_file_preview",
            "success",
            stdout=diff,
            result={
                "path": str(target),
                "diff_view": diff,
                "bytes_after": len(new_content.encode("utf-8")),
                "would_create": not target.exists(),
            },
            started=started,
        )
    except Exception as exc:
        return _result("roo_write_file_preview", "error", stderr=str(exc), started=started)


def write_file(path: str, content: str, approval: str = "") -> dict[str, Any]:
    started = time.time()
    try:
        target = _resolve_workspace_path(path)
        if target.exists() and target.is_dir():
            raise ValueError(f"Pad is een map, geen bestand: {path}")
        if target.exists() and target.is_symlink():
            raise ValueError(f"Weigert te schrijven via symlink: {path}")
        new_content = "" if content is None else str(content)
        previous = target.read_text(encoding="utf-8", errors="replace") if target.exists() else ""
        diff = _unified_diff(previous, new_content, path)
        if not _approved(approval):
            return _result(
                "roo_write_file",
                "blocked",
                stdout=diff,
                result={"path": str(target), "diff_view": diff, "approval_required": True},
                approval_status="pending_philip_akkoord",
                started=started,
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(new_content, encoding="utf-8")
        written = target.read_text(encoding="utf-8")
        if written != new_content:
            raise RuntimeError("Write verification failed.")
        return _result(
            "roo_write_file",
            "success",
            stdout=diff,
            result={"path": str(target), "diff_view": diff, "bytes_written": len(new_content.encode("utf-8"))},
            approval_status="approved",
            started=started,
        )
    except Exception as exc:
        return _result(
            "roo_write_file",
            "error",
            stderr=str(exc),
            approval_status="approved" if _approved(approval) else "pending_philip_akkoord",
            started=started,
        )


def apply_patch_preview(patch: str) -> dict[str, Any]:
    started = time.time()
    try:
        operations = _parse_apply_patch(patch)
        _validate_operations(operations)
        previews: list[str] = []
        for operation in operations:
            previews.append(_preview_operation(operation))
        diff_view = "\n".join(previews)
        return _result(
            "roo_apply_patch_preview",
            "success",
            stdout=diff_view,
            result={"operations": [_public_operation(op) for op in operations], "operation_count": len(operations)},
            started=started,
        )
    except Exception as exc:
        return _result("roo_apply_patch_preview", "error", stderr=str(exc), started=started)


def apply_patch(patch: str, approval: str = "") -> dict[str, Any]:
    started = time.time()
    try:
        operations = _parse_apply_patch(patch)
        _validate_operations(operations)
        previews: list[str] = []
        for operation in operations:
            previews.append(_preview_operation(operation))
        diff_view = "\n".join(previews)
        if not _approved(approval):
            return _result(
                "roo_apply_patch",
                "blocked",
                stdout=diff_view,
                result={"operations": [_public_operation(op) for op in operations], "approval_required": True},
                approval_status="pending_philip_akkoord",
                started=started,
            )
        changed: list[str] = []
        for operation in operations:
            _apply_operation(operation)
            changed.append(str(operation["path"]))
        return _result(
            "roo_apply_patch",
            "success",
            stdout=diff_view,
            result={"changed_paths": changed, "operation_count": len(operations)},
            approval_status="approved",
            started=started,
        )
    except Exception as exc:
        return _result(
            "roo_apply_patch",
            "error",
            stderr=str(exc),
            approval_status="approved" if _approved(approval) else "pending_philip_akkoord",
            started=started,
        )


def execute_command(command: str, approval: str = "", timeout: int = 20) -> dict[str, Any]:
    shell = run_safe_shell(command, approval=approval, timeout=timeout)
    return _result(
        "roo_execute_command",
        shell.get("status", "error"),
        stdout=str(shell.get("stdout", "")),
        stderr=str(shell.get("stderr") or (shell.get("reason") if shell.get("status") != "success" else "") or ""),
        result={"command": command, "exit_code": shell.get("exit_code"), "workspace": shell.get("workspace")},
        approval_status="approved" if shell.get("approved") else "pending_philip_akkoord",
        started=time.time() - float(shell.get("duration_seconds", 0.0) or 0.0),
    )


def _resolve_workspace_path(path: str) -> Path:
    if not str(path or "").strip():
        raise ValueError("Pad is verplicht.")
    root = workspace_root()
    target = _resolve_alias_path(path)
    if target is None:
        candidate = Path(path)
        target = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    if _root_for_path(target) is None:
        raise ValueError(f"Pad valt buiten /workspace of bekende agent-roots: {path}")
    return target


def _allowed_roots() -> list[Path]:
    roots: list[Path] = [workspace_root()]
    for root in (ruflo_path(), roo_path(), codex_path()):
        if root.exists():
            roots.append(root.resolve())
    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root)
        if key not in seen:
            unique.append(root)
            seen.add(key)
    return unique


def _resolve_alias_path(path: str) -> Path | None:
    raw = str(path or "").strip()
    if not raw:
        return None
    normalized = raw.replace("\\", "/")
    first, _, rest = normalized.partition("/")
    aliases = {
        "workspace": workspace_root(),
        "wintripai": workspace_root(),
        "wintrip": workspace_root(),
        "ruflo": ruflo_path(),
        "roo": roo_path(),
        "codex": codex_path(),
    }
    base = aliases.get(first.lower())
    if base is None:
        return None
    return (base / rest).resolve()


def _root_for_path(path: Path) -> Path | None:
    for root in _allowed_roots():
        try:
            path.relative_to(root)
            return root
        except ValueError:
            continue
    return None


def _display_path(path: Path) -> str:
    root = _root_for_path(path)
    if root is None:
        return str(path)
    rel = path.relative_to(root)
    if root == workspace_root():
        return str(rel) if str(rel) != "." else "."
    labels = {ruflo_path(): "ruflo", roo_path(): "roo", codex_path(): "codex"}
    prefix = labels.get(root, root.name)
    return f"{prefix}/{rel}" if str(rel) != "." else f"{prefix}/"


def _iter_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    if root.is_file():
        return [root]
    paths: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(_skip_hidden(dirnames))
        for name in sorted(_skip_hidden(filenames)):
            paths.append(Path(dirpath) / name)
    return paths


def _skip_hidden(names: Iterable[str]) -> list[str]:
    return [name for name in names if not name.startswith(".") and name not in {"__pycache__", "node_modules"}]


def _approved(approval: str) -> bool:
    return str(approval or "").strip() == "Akkoord"


def _unified_diff(before: str, after: str, path: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )


def _parse_apply_patch(patch: str) -> list[dict[str, Any]]:
    lines = str(patch or "").splitlines()
    if not lines or lines[0].strip() != "*** Begin Patch" or lines[-1].strip() != "*** End Patch":
        raise ValueError("Patch moet starten met *** Begin Patch en eindigen met *** End Patch.")
    operations: list[dict[str, Any]] = []
    index = 1
    while index < len(lines) - 1:
        line = lines[index]
        if line.startswith("*** Add File: "):
            rel = line.removeprefix("*** Add File: ").strip()
            body: list[str] = []
            index += 1
            while index < len(lines) - 1 and not lines[index].startswith("*** "):
                if not lines[index].startswith("+"):
                    raise ValueError("Add File regels moeten met + starten.")
                body.append(lines[index][1:])
                index += 1
            operations.append({"type": "add", "path": _resolve_workspace_path(rel), "rel": rel, "content": "\n".join(body) + "\n"})
            continue
        if line.startswith("*** Delete File: "):
            rel = line.removeprefix("*** Delete File: ").strip()
            operations.append({"type": "delete", "path": _resolve_workspace_path(rel), "rel": rel})
            index += 1
            continue
        if line.startswith("*** Update File: "):
            rel = line.removeprefix("*** Update File: ").strip()
            hunk_lines: list[str] = []
            index += 1
            if index < len(lines) - 1 and lines[index].startswith("@@"):
                index += 1
            while index < len(lines) - 1 and not lines[index].startswith("*** "):
                hunk_lines.append(lines[index])
                index += 1
            operations.append({"type": "update", "path": _resolve_workspace_path(rel), "rel": rel, "hunk": hunk_lines})
            continue
        if not line.strip():
            index += 1
            continue
        raise ValueError(f"Onbekende patchregel: {line}")
    return operations


def _preview_operation(operation: dict[str, Any]) -> str:
    path = operation["path"]
    rel = operation["rel"]
    current = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    if operation["type"] == "add":
        return _unified_diff("", operation["content"], rel)
    if operation["type"] == "delete":
        return _unified_diff(current, "", rel)
    updated = _apply_update_to_text(current, operation["hunk"])
    return _unified_diff(current, updated, rel)


def _validate_operations(operations: list[dict[str, Any]]) -> None:
    for operation in operations:
        path = operation["path"]
        rel = operation["rel"]
        if path.exists() and path.is_symlink():
            raise ValueError(f"Weigert patch via symlink: {rel}")
        if operation["type"] == "add":
            if path.exists():
                raise ValueError(f"Bestand bestaat al: {rel}")
            continue
        if operation["type"] == "delete":
            if not path.exists():
                raise ValueError(f"Bestand bestaat niet: {rel}")
            if path.is_dir():
                raise ValueError(f"Pad is een map, geen bestand: {rel}")
            continue
        if operation["type"] == "update":
            if not path.exists():
                raise ValueError(f"Bestand bestaat niet: {rel}")
            if path.is_dir():
                raise ValueError(f"Pad is een map, geen bestand: {rel}")
            _preview_operation(operation)
            continue
        raise ValueError(f"Onbekende operatie: {operation['type']}")


def _apply_operation(operation: dict[str, Any]) -> None:
    path = operation["path"]
    if operation["type"] == "add":
        if path.exists():
            raise ValueError(f"Bestand bestaat al: {operation['rel']}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(operation["content"], encoding="utf-8")
        return
    if operation["type"] == "delete":
        if not path.exists():
            raise ValueError(f"Bestand bestaat niet: {operation['rel']}")
        path.unlink()
        return
    if operation["type"] == "update":
        if not path.exists():
            raise ValueError(f"Bestand bestaat niet: {operation['rel']}")
        current = path.read_text(encoding="utf-8", errors="replace")
        path.write_text(_apply_update_to_text(current, operation["hunk"]), encoding="utf-8")
        return
    raise ValueError(f"Onbekende operatie: {operation['type']}")


def _apply_update_to_text(current: str, hunk_lines: list[str]) -> str:
    old_lines: list[str] = []
    new_lines: list[str] = []
    for line in hunk_lines:
        if not line:
            old_lines.append("")
            new_lines.append("")
        elif line[0] == " ":
            old_lines.append(line[1:])
            new_lines.append(line[1:])
        elif line[0] == "-":
            old_lines.append(line[1:])
        elif line[0] == "+":
            new_lines.append(line[1:])
        else:
            raise ValueError(f"Ongeldige hunkregel: {line}")
    old = "\n".join(old_lines)
    new = "\n".join(new_lines)
    if current.endswith("\n"):
        old += "\n"
        new += "\n"
    if old not in current:
        raise ValueError("Update hunk kon niet worden gevonden in huidig bestand.")
    return current.replace(old, new, 1)


def _public_operation(operation: dict[str, Any]) -> dict[str, Any]:
    return {"type": operation["type"], "path": operation["rel"]}


def _result(
    tool_name: str,
    status: str,
    stdout: str = "",
    stderr: str = "",
    result: dict[str, Any] | None = None,
    approval_status: str = "not_required",
    started: float | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "tool_name": tool_name,
        "stdout": stdout,
        "stderr": stderr,
        "result": result or {},
        "source": "roo_tools.local_adapter",
        "approval_status": approval_status,
        "stored_to_memory": False,
        "metadata_11d": {},
        "next_action": "Review stdout/stderr; writes require Akkoord.",
        "duration_seconds": round(time.time() - (started or time.time()), 3),
    }
