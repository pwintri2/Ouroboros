"""Read-only CodeNeuron/CoreNEURON indexer for the trainer pipeline."""

from __future__ import annotations

import json
import os
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from controller.codeneuron_ontology import get_pocket_map, infer_dimensions
from controller.safe_shell import workspace_root


TARGET_DIRS = ("docs", "coreneuron", "tests", "CMake")
SKIP_DIRS = {
    ".git",
    ".github",
    ".cache",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    ".venv",
    "venv",
    "external",
}
TEXT_SUFFIXES = {
    "",
    ".c",
    ".cc",
    ".cpp",
    ".cxx",
    ".h",
    ".hh",
    ".hpp",
    ".hxx",
    ".cmake",
    ".md",
    ".rst",
    ".txt",
    ".py",
    ".sh",
    ".yml",
    ".yaml",
    ".json",
}


def codeneuron_root() -> Path:
    configured = os.getenv("WINTRIP_CODENEURON_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    host_default = Path("/home/pwintri2/CodeNeuron")
    if host_default.exists():
        return host_default.resolve()
    docker_default = Path("/codeneuron")
    if docker_default.exists():
        return docker_default.resolve()
    return host_default.resolve()


def codeneuron_index_path() -> Path:
    return (workspace_root() / ".secrets" / "codeneuron_index.json").resolve()


def get_codeneuron_status() -> dict[str, Any]:
    root = codeneuron_root()
    index = load_codeneuron_index()
    root_exists = root.exists() and root.is_dir()
    indexed = bool(index.get("status") == "success")
    return {
        "status": "indexed" if indexed else "available" if root_exists else "missing",
        "source_root": str(root),
        "root_exists": root_exists,
        "read_only": True,
        "target_dirs": list(TARGET_DIRS),
        "index_path": str(codeneuron_index_path()),
        "indexed": indexed,
        "indexed_at": index.get("indexed_at"),
        "file_count": index.get("file_count", 0),
        "total_lines": index.get("total_lines", 0),
        "subsystems": index.get("subsystems", {}),
        "dimension_counts": index.get("dimension_counts", {}),
        "fake_success": False,
        "reason": "" if root_exists else "Set WINTRIP_CODENEURON_PATH or mount /home/pwintri2/CodeNeuron as /codeneuron:ro in Docker.",
    }


def index_codeneuron(max_files: int = 1500, max_bytes_per_file: int = 50000) -> dict[str, Any]:
    """Build a compact read-only source index from CodeNeuron."""
    started = time.time()
    root = codeneuron_root()
    if not root.exists() or not root.is_dir():
        return {
            "status": "error",
            "reason": f"CodeNeuron root not found: {root}",
            "source_root": str(root),
            "fake_success": False,
        }

    max_files = max(1, min(int(max_files), 10000))
    max_bytes_per_file = max(1024, min(int(max_bytes_per_file), 250000))
    files: list[dict[str, Any]] = []
    subsystem_counter: Counter[str] = Counter()
    extension_counter: Counter[str] = Counter()
    dimension_counter: Counter[str] = Counter()
    total_lines = 0

    for path in _iter_source_files(root, max_files=max_files):
        rel_path = path.relative_to(root).as_posix()
        text = _read_text_prefix(path, max_bytes_per_file=max_bytes_per_file)
        line_count = text.count("\n") + (1 if text else 0)
        total_lines += line_count
        subsystem = rel_path.split("/", 1)[0]
        dimensions = infer_dimensions(f"{rel_path}\n{text}", limit=5)
        for match in dimensions:
            dimension_counter[str(match["id"])] += 1
        subsystem_counter[subsystem] += 1
        extension_counter[path.suffix.lower()] += 1
        files.append(
            {
                "path": rel_path,
                "subsystem": subsystem,
                "suffix": path.suffix.lower(),
                "size_bytes": path.stat().st_size,
                "line_count": line_count,
                "summary": _summarize_file(rel_path, text),
                "dimensions": dimensions,
            }
        )

    subsystem_summaries = _summarize_subsystems(files)
    result = {
        "status": "success",
        "source_root": str(root),
        "read_only": True,
        "indexed_at": datetime.utcnow().isoformat(),
        "file_count": len(files),
        "total_lines": total_lines,
        "max_files": max_files,
        "truncated": len(files) >= max_files,
        "extensions": dict(sorted(extension_counter.items())),
        "subsystems": subsystem_summaries,
        "dimension_counts": dict(sorted(dimension_counter.items())),
        "files": files,
        "duration_seconds": round(time.time() - started, 3),
        "index_path": str(codeneuron_index_path()),
        "fake_success": False,
    }
    _save_index(result)
    return result


def load_codeneuron_index() -> dict[str, Any]:
    path = codeneuron_index_path()
    if not path.exists():
        return {"status": "missing", "files": [], "fake_success": False}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"status": "error", "reason": "Index is not a JSON object.", "files": []}
    except Exception as exc:
        return {"status": "error", "reason": f"Cannot read CodeNeuron index: {exc}", "files": [], "fake_success": False}


def get_codeneuron_pocket_map() -> dict[str, Any]:
    return get_pocket_map(load_codeneuron_index())


def search_codeneuron(query: str, limit: int = 20) -> dict[str, Any]:
    index = load_codeneuron_index()
    if index.get("status") != "success":
        return {
            "status": "missing_index",
            "query": query,
            "results": [],
            "reason": "Run /trainer/codeneuron/index first.",
            "fake_success": False,
        }
    needle = str(query or "").strip().lower()
    if not needle:
        return {"status": "error", "query": query, "results": [], "reason": "Query is empty.", "fake_success": False}
    terms = [term for term in needle.replace("/", " ").replace("_", " ").split() if term]
    results = []
    for file_info in index.get("files") or []:
        haystack = " ".join(
            [
                str(file_info.get("path", "")),
                str(file_info.get("summary", "")),
                " ".join(str(match.get("title", "")) for match in file_info.get("dimensions") or []),
            ]
        ).lower()
        score = sum(haystack.count(term) for term in terms)
        if needle in haystack:
            score += 5
        if score:
            results.append(
                {
                    "path": file_info.get("path", ""),
                    "subsystem": file_info.get("subsystem", ""),
                    "summary": file_info.get("summary", ""),
                    "dimensions": file_info.get("dimensions", [])[:3],
                    "score": score,
                }
            )
    results.sort(key=lambda item: (-int(item["score"]), str(item["path"])))
    return {
        "status": "success",
        "query": query,
        "count": len(results),
        "results": results[: max(1, min(int(limit), 100))],
        "indexed_at": index.get("indexed_at"),
        "source_root": index.get("source_root"),
        "fake_success": False,
    }


def _iter_source_files(root: Path, max_files: int) -> list[Path]:
    found: list[Path] = []
    for dirname in TARGET_DIRS:
        base = root / dirname
        if not base.exists():
            continue
        if base.is_file():
            candidates = [base]
        else:
            candidates = []
            for current_root, dirnames, filenames in os.walk(base):
                dirnames[:] = [name for name in dirnames if name not in SKIP_DIRS and not name.startswith(".")]
                for filename in sorted(filenames):
                    candidates.append(Path(current_root) / filename)
        for path in sorted(candidates):
            if len(found) >= max_files:
                return found
            if _is_text_source(path):
                found.append(path)
    return found


def _is_text_source(path: Path) -> bool:
    if path.name.startswith(".") or not path.is_file():
        return False
    if path.name == "CMakeLists.txt":
        return True
    if path.suffix.lower() not in TEXT_SUFFIXES:
        return False
    try:
        return path.stat().st_size <= 2_000_000
    except OSError:
        return False


def _read_text_prefix(path: Path, max_bytes_per_file: int) -> str:
    try:
        data = path.read_bytes()[:max_bytes_per_file]
        return data.decode("utf-8", errors="replace")
    except Exception:
        return ""


def _summarize_file(rel_path: str, text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    selected = []
    for line in lines:
        if line.startswith(("#", "//", "/*", "*")) or any(token in line.lower() for token in ("test", "mechanism", "gpu", "mpi", "soa", "checkpoint")):
            selected.append(line[:180])
        if len(selected) >= 3:
            break
    if not selected:
        selected = lines[:2]
    summary = " ".join(selected)[:360]
    return summary or f"Indexed source file {rel_path}."


def _summarize_subsystems(files: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for file_info in files:
        grouped[str(file_info.get("subsystem") or "unknown")].append(file_info)
    summaries: dict[str, Any] = {}
    for subsystem, entries in sorted(grouped.items()):
        dimension_counts: Counter[str] = Counter()
        for entry in entries:
            for match in entry.get("dimensions") or []:
                dimension_counts[str(match.get("id"))] += 1
        summaries[subsystem] = {
            "file_count": len(entries),
            "line_count": sum(int(entry.get("line_count") or 0) for entry in entries),
            "top_dimensions": dict(dimension_counts.most_common(5)),
            "representative_files": [entry.get("path", "") for entry in entries[:8]],
        }
    return summaries


def _save_index(index: dict[str, Any]) -> None:
    path = codeneuron_index_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, indent=2, sort_keys=True), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
