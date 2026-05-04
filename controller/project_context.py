"""Project context engine for Roo agent workspace awareness.

Builds file graph, symbol hints, test hints, and recent git diff context.
Uses rg, git diff, and git ls-files via safe_shell or read-only Python APIs.
Provides structured context for the Roo agent to make informed decisions.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from controller.safe_shell import workspace_root


IGNORED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "node_modules",
    "target",
    "dist",
    "build",
    ".venv",
    ".venv_litgpt",
    ".venv_unsloth",
    ".venv_world_agent",
    ".venv_blue_brain",
    "wintrip_brain",
    "out",
    "tmp",
}

SECRET_NAME_MARKERS = (
    ".env",
    "secret",
    "token",
    "apikey",
    "api_key",
    "oauth",
    "credential",
    "password",
)


def get_project_root() -> Path:
    """Get the project root directory."""
    return workspace_root()


def _bridge_get(path: str, query: dict[str, Any] | None = None) -> dict[str, Any] | None:
    bridge_url = os.getenv("WINTRIP_RCLONE_BRIDGE_URL", "").rstrip("/")
    token_path = os.getenv("WINTRIP_RCLONE_BRIDGE_TOKEN_PATH", "")
    if not bridge_url or not token_path:
        return None
    try:
        token = Path(token_path).read_text(encoding="utf-8").strip()
        suffix = f"?{urlencode(query or {})}" if query else ""
        req = Request(f"{bridge_url}{path}{suffix}", headers={"X-Ouroboros-Bridge-Token": token})
        with urlopen(req, timeout=8) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception:
        return None


def _should_skip(path: Path) -> bool:
    parts = set(path.parts)
    if parts.intersection(IGNORED_DIRS):
        return True
    lowered = path.name.lower()
    return any(marker in lowered for marker in SECRET_NAME_MARKERS)


def _git_file_list(root: Path, *, include_untracked: bool = True, limit: int = 5000) -> list[str] | None:
    args = ["git", "ls-files", "--cached"]
    if include_untracked:
        args.extend(["--others", "--exclude-standard"])
    try:
        result = subprocess.run(args, cwd=str(root), capture_output=True, text=True, timeout=8)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    files: list[str] = []
    for line in result.stdout.splitlines():
        path = line.strip()
        if not path or _should_skip(Path(path)):
            continue
        files.append(path)
        if len(files) >= limit:
            break
    return files


def _walk_file_list(root: Path, *, limit: int = 5000) -> list[str]:
    files: list[str] = []
    for current, dirnames, filenames in os.walk(root):
        current_path = Path(current)
        dirnames[:] = [name for name in dirnames if not _should_skip((current_path / name).relative_to(root))]
        for filename in sorted(filenames):
            rel = (current_path / filename).relative_to(root)
            if _should_skip(rel):
                continue
            files.append(str(rel))
            if len(files) >= limit:
                return files
    return files


def _project_files(root: Path, *, limit: int = 5000) -> list[str]:
    return _git_file_list(root, include_untracked=True, limit=limit) or _walk_file_list(root, limit=limit)


def _insert_tree_node(tree: dict[str, Any], parts: list[str], *, size: int) -> None:
    cursor = tree.setdefault("children", {})
    for index, part in enumerate(parts):
        is_leaf = index == len(parts) - 1
        if is_leaf:
            cursor[part] = {"type": "file", "name": part, "path": "/".join(parts), "size": size}
            return
        node = cursor.setdefault(part, {"type": "directory", "name": part, "children": {}})
        cursor = node.setdefault("children", {})


def get_file_tree(max_depth: int = 3, limit: int = 500, *, prefer_bridge: bool = True) -> dict[str, Any]:
    """Get a structured file tree of the project."""
    if prefer_bridge:
        bridged = _bridge_get("/context/file_tree", {"max_depth": max_depth, "limit": limit})
        if bridged:
            bridged["via_bridge"] = True
            return bridged

    root = get_project_root()
    if not root.exists():
        return {"status": "error", "reason": "Project root not found", "tree": {}}

    tree: dict[str, Any] = {"type": "directory", "name": root.name, "children": {}}
    items: list[dict[str, Any]] = []
    files = _project_files(root, limit=limit)
    for rel_path in files[:limit]:
        parts = Path(rel_path).parts
        if len(parts) > max_depth + 1:
            continue
        try:
            size = (root / rel_path).stat().st_size
        except OSError:
            size = 0
        node = {"type": "file", "name": parts[-1], "path": rel_path, "size": size}
        items.append(node)
        _insert_tree_node(tree, list(parts), size=size)

    return {
        "status": "success",
        "root": str(root),
        "max_depth": max_depth,
        "limit": limit,
        "actual_count": len(files[:limit]),
        "tree": tree,
        "files": items,
    }


def get_changed_files(limit: int = 50, *, prefer_bridge: bool = True) -> dict[str, Any]:
    """Get list of changed files from git diff."""
    if prefer_bridge:
        bridged = _bridge_get("/context/changed_files", {"limit": limit})
        if bridged:
            bridged["via_bridge"] = True
            return bridged

    root = get_project_root()
    
    try:
        # Check if we're in a git repo
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return {"status": "error", "reason": "Not a git repository", "changed_files": []}
        
        # Get modified and untracked files.
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=10,
        )
        files: list[str] = []
        for line in result.stdout.splitlines():
            path = line[3:].strip()
            if " -> " in path:
                path = path.split(" -> ", 1)[1].strip()
            if path and not _should_skip(Path(path)):
                files.append(path)
        files = files[:limit]
        
        # Get diff stats for each file
        file_details = []
        for file_path in files:
            try:
                diff_result = subprocess.run(
                    ["git", "diff", "--numstat", "HEAD", "--", file_path],
                    cwd=str(root),
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if diff_result.stdout:
                    parts = diff_result.stdout.strip().split()
                    if len(parts) >= 2:
                        additions = int(parts[0]) if parts[0].isdigit() else 0
                        deletions = int(parts[1]) if parts[1].isdigit() else 0
                        file_details.append({
                            "path": file_path,
                            "additions": additions,
                            "deletions": deletions,
                        })
            except Exception:
                file_details.append({"path": file_path, "additions": 0, "deletions": 0})
        
        return {
            "status": "success",
            "changed_files": files,
            "details": file_details,
            "count": len(files),
        }
    except subprocess.TimeoutExpired:
        return {"status": "error", "reason": "Git command timeout", "changed_files": []}
    except FileNotFoundError:
        return {"status": "error", "reason": "git not available", "changed_files": []}
    except Exception as exc:
        return {"status": "error", "reason": str(exc), "changed_files": []}


def get_test_files(limit: int = 100, *, prefer_bridge: bool = True) -> dict[str, Any]:
    """Get list of test files in the project."""
    if prefer_bridge:
        bridged = _bridge_get("/context/test_files", {"limit": limit})
        if bridged:
            bridged["via_bridge"] = True
            return bridged

    root = get_project_root()
    test_files = []
    for rel_path in _project_files(root, limit=5000):
        name = Path(rel_path).name
        if name.startswith("test_") or name.endswith(("_test.py", ".test.ts", ".spec.ts", ".test.tsx", ".spec.tsx")):
            test_files.append({"path": rel_path, "pattern": "project_files"})
        if len(test_files) >= limit:
            break
    test_files = test_files[:limit]
    
    return {
        "status": "success",
        "test_files": test_files,
        "count": len(test_files),
    }


def get_python_imports(file_path: str | None = None) -> dict[str, Any]:
    """Get Python import hints for a file or project-wide."""
    root = get_project_root()
    
    if file_path:
        # Get imports for specific file
        target = (root / file_path).resolve()
        if not target.exists() or not target.is_file():
            return {"status": "error", "reason": "File not found", "imports": []}
        
        try:
            content = target.read_text(encoding="utf-8")
            imports = []
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("import ") or line.startswith("from "):
                    imports.append(line)
            return {"status": "success", "file": file_path, "imports": imports}
        except Exception as exc:
            return {"status": "error", "reason": str(exc), "imports": []}
    
    # Get project-wide import hints using rg
    try:
        result = subprocess.run(
            ["rg", "^(import |from )", "--type", "py", "--no-heading", "-n"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=15,
        )
        
        if result.returncode == 0 and result.stdout:
            lines = result.stdout.strip().split("\n")
            import_hints = []
            for line in lines[:200]:  # Limit to 200 results
                if ":" in line:
                    parts = line.split(":", 1)
                    if len(parts) == 2:
                        file_path, import_stmt = parts
                        import_hints.append({
                            "file": file_path,
                            "import": import_stmt.strip(),
                        })
            
            return {
                "status": "success",
                "import_hints": import_hints,
                "count": len(import_hints),
            }
        
        return {"status": "success", "import_hints": [], "count": 0}
    except subprocess.TimeoutExpired:
        return {"status": "error", "reason": "ripgrep timeout", "import_hints": []}
    except FileNotFoundError:
        return {"status": "error", "reason": "ripgrep not available", "import_hints": []}
    except Exception as exc:
        return {"status": "error", "reason": str(exc), "import_hints": []}


def get_project_structure_summary(*, prefer_bridge: bool = True) -> dict[str, Any]:
    """Get a comprehensive summary of project structure."""
    if prefer_bridge:
        bridged = _bridge_get("/context/structure")
        if bridged:
            bridged["via_bridge"] = True
            return bridged

    root = get_project_root()
    
    # Count files by extension
    extension_counts: dict[str, int] = {}
    files = _project_files(root, limit=10000)
    for rel_path in files:
        ext = Path(rel_path).suffix.lstrip(".") or "no_ext"
        extension_counts[ext] = extension_counts.get(ext, 0) + 1
    
    # Get directory structure
    directory_counts: dict[str, int] = {}
    for rel_path in files:
        top = Path(rel_path).parts[0] if len(Path(rel_path).parts) > 1 else "."
        directory_counts[top] = directory_counts.get(top, 0) + 1
    directories = [{"name": name, "path": "" if name == "." else name, "file_count": count} for name, count in directory_counts.items()]
    
    return {
        "status": "success",
        "root": str(root),
        "total_files": len(files),
        "extensions": dict(sorted(extension_counts.items(), key=lambda x: x[1], reverse=True)[:20]),
        "directories": sorted(directories, key=lambda d: d["name"]),
    }


def get_context_summary(*, prefer_bridge: bool = True) -> dict[str, Any]:
    """Get a combined context summary for the Roo agent."""
    if prefer_bridge:
        bridged = _bridge_get("/context/summary")
        if bridged:
            bridged["via_bridge"] = True
            return bridged

    file_tree = get_file_tree(max_depth=2, limit=100, prefer_bridge=False)
    changed = get_changed_files(limit=20, prefer_bridge=False)
    tests = get_test_files(limit=50, prefer_bridge=False)
    structure = get_project_structure_summary(prefer_bridge=False)
    
    return {
        "status": "success",
        "project_root": str(get_project_root()),
        "file_tree_summary": {
            "file_count": file_tree.get("actual_count", 0),
            "limit_reached": file_tree.get("actual_count", 0) >= file_tree.get("limit", 0),
        },
        "changed_files": {
            "count": changed.get("count", 0),
            "files": changed.get("changed_files", [])[:10],
        },
        "test_files": {
            "count": tests.get("count", 0),
            "files": [tf["path"] for tf in tests.get("test_files", [])[:10]],
        },
        "structure": {
            "total_files": structure.get("total_files", 0),
            "top_extensions": list(structure.get("extensions", {}).items())[:10],
            "directory_count": len(structure.get("directories", [])),
        },
    }
