"""Project context engine for Roo agent workspace awareness.

Builds file graph, symbol hints, test hints, and recent git diff context.
Uses rg, git diff, and git ls-files via safe_shell or read-only Python APIs.
Provides structured context for the Roo agent to make informed decisions.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from controller.safe_shell import workspace_root


def get_project_root() -> Path:
    """Get the project root directory."""
    return workspace_root()


def get_file_tree(max_depth: int = 3, limit: int = 500) -> dict[str, Any]:
    """Get a structured file tree of the project."""
    root = get_project_root()
    if not root.exists():
        return {"status": "error", "reason": "Project root not found", "tree": {}}
    
    tree: dict[str, Any] = {}
    items: list[dict[str, Any]] = []
    count = 0
    
    def build_tree(path: Path, depth: int) -> dict[str, Any]:
        nonlocal count
        if depth > max_depth or count >= limit:
            return {}
        
        node: dict[str, Any] = {"type": "directory" if path.is_dir() else "file", "name": path.name}
        
        if path.is_dir():
            if path.name.startswith(".") or path.name in {"__pycache__", "node_modules", ".git"}:
                return {}
            
            children: dict[str, Any] = {}
            try:
                for child in sorted(path.iterdir(), key=lambda p: p.name):
                    child_node = build_tree(child, depth + 1)
                    if child_node:
                        children[child.name] = child_node
                        count += 1
                        if count >= limit:
                            break
            except PermissionError:
                pass
            
            if children:
                node["children"] = children
        else:
            node["path"] = str(path.relative_to(root))
            node["size"] = path.stat().st_size if path.exists() else 0
            items.append(node)
            count += 1
        
        return node
    
    tree = build_tree(root, 0)
    
    return {
        "status": "success",
        "root": str(root),
        "max_depth": max_depth,
        "limit": limit,
        "actual_count": count,
        "tree": tree,
        "files": items,
    }


def get_changed_files(limit: int = 50) -> dict[str, Any]:
    """Get list of changed files from git diff."""
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
        
        # Get modified files
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        files = [f for f in result.stdout.strip().split("\n") if f]
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
    except Exception as exc:
        return {"status": "error", "reason": str(exc), "changed_files": []}


def get_test_files(limit: int = 100) -> dict[str, Any]:
    """Get list of test files in the project."""
    root = get_project_root()
    test_patterns = ["test_*.py", "*_test.py", "tests.py", "test_*.ts", "*.test.ts", "*.spec.ts"]
    
    test_files = []
    
    for pattern in test_patterns:
        try:
            result = subprocess.run(
                ["find", str(root), "-name", pattern, "-type", "f"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.stdout:
                files = [f for f in result.stdout.strip().split("\n") if f]
                for f in files:
                    rel_path = str(Path(f).relative_to(root))
                    if rel_path not in [tf["path"] for tf in test_files]:
                        test_files.append({"path": rel_path, "pattern": pattern})
        except Exception:
            continue
    
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


def get_project_structure_summary() -> dict[str, Any]:
    """Get a comprehensive summary of project structure."""
    root = get_project_root()
    
    # Count files by extension
    extension_counts: dict[str, int] = {}
    total_files = 0
    
    try:
        for item in root.rglob("*"):
            if item.is_file() and not item.name.startswith("."):
                if item.parent.name in {".git", "__pycache__", "node_modules"}:
                    continue
                ext = item.suffix.lstrip(".") or "no_ext"
                extension_counts[ext] = extension_counts.get(ext, 0) + 1
                total_files += 1
    except Exception:
        pass
    
    # Get directory structure
    directories = []
    try:
        for item in root.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                dir_info = {
                    "name": item.name,
                    "path": str(item.relative_to(root)),
                }
                try:
                    dir_info["file_count"] = sum(1 for _ in item.rglob("*") if _.is_file())
                except Exception:
                    dir_info["file_count"] = 0
                directories.append(dir_info)
    except Exception:
        pass
    
    return {
        "status": "success",
        "root": str(root),
        "total_files": total_files,
        "extensions": dict(sorted(extension_counts.items(), key=lambda x: x[1], reverse=True)[:20]),
        "directories": sorted(directories, key=lambda d: d["name"]),
    }


def get_context_summary() -> dict[str, Any]:
    """Get a combined context summary for the Roo agent."""
    file_tree = get_file_tree(max_depth=2, limit=100)
    changed = get_changed_files(limit=20)
    tests = get_test_files(limit=50)
    structure = get_project_structure_summary()
    
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
