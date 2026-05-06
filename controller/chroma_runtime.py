"""Shared ChromaDB runtime selection for Ouroboros.

Default mode keeps the existing local persistent brain. When
WINTRIP_CHROMA_HTTP_URL is set, callers use a Chroma HTTP server instead. This
keeps laptop/VPS sharing out of SQLite file-sharing territory.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse


DEFAULT_KNOWLEDGE_COLLECTION = "wintrip_knowledge"
DEFAULT_TRAINING_COLLECTION = "wintrip_training_11d"
DEFAULT_WORLD_COLLECTION = "wintrip_world_understanding"


def workspace_root() -> Path:
    configured = os.getenv("WINTRIP_WORKSPACE") or os.getenv("WORKSPACE_ROOT")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def default_chroma_path() -> Path:
    configured = os.getenv("WINTRIP_DB_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    return (workspace_root() / "wintrip_brain").resolve()


def chroma_http_url() -> str:
    return str(os.getenv("WINTRIP_CHROMA_HTTP_URL") or "").strip()


def chroma_runtime_mode() -> str:
    return "http" if chroma_http_url() else "persistent"


def chroma_client(*, persist_dir: str | os.PathLike[str] | None = None) -> Any:
    try:
        import chromadb
    except Exception as exc:
        raise RuntimeError(f"chromadb is not available: {exc}") from exc

    remote_url = chroma_http_url()
    if remote_url:
        parsed = _parse_remote_url(remote_url)
        if not hasattr(chromadb, "HttpClient"):
            raise RuntimeError("chromadb.HttpClient is not available in this ChromaDB install.")
        return chromadb.HttpClient(host=parsed["host"], port=parsed["port"], ssl=parsed["ssl"])

    path = Path(persist_dir).expanduser().resolve() if persist_dir else default_chroma_path()
    path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(path))


def get_or_create_collection(
    *,
    name: str,
    embedding_function: Any | None = None,
    metadata: dict[str, Any] | None = None,
    persist_dir: str | os.PathLike[str] | None = None,
) -> Any:
    client = chroma_client(persist_dir=persist_dir)
    kwargs: dict[str, Any] = {"name": name}
    if embedding_function is not None:
        kwargs["embedding_function"] = embedding_function
    if metadata is not None:
        kwargs["metadata"] = metadata
    return client.get_or_create_collection(**kwargs)


def chroma_runtime_config(*, persist_dir: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    remote_url = chroma_http_url()
    local_path = Path(persist_dir).expanduser().resolve() if persist_dir else default_chroma_path()
    return {
        "mode": "http" if remote_url else "persistent",
        "remote_url": _safe_url(remote_url) if remote_url else "",
        "persist_dir": "" if remote_url else str(local_path),
        "collection_names": {
            "knowledge": os.getenv("WINTRIP_KNOWLEDGE_COLLECTION", DEFAULT_KNOWLEDGE_COLLECTION),
            "training": os.getenv("WINTRIP_TRAINING_COLLECTION", DEFAULT_TRAINING_COLLECTION),
            "world": os.getenv("WINTRIP_WORLD_AGENT_COLLECTION", DEFAULT_WORLD_COLLECTION),
        },
        "fake_success": False,
    }


def chroma_runtime_status(collection_names: list[str] | tuple[str, ...] | None = None) -> dict[str, Any]:
    config = chroma_runtime_config()
    names = list(collection_names or config["collection_names"].values())
    status: dict[str, Any] = {
        "status": "unknown",
        "available": False,
        **config,
        "collections": {},
    }
    try:
        client = chroma_client()
        heartbeat = getattr(client, "heartbeat", None)
        if callable(heartbeat):
            try:
                status["heartbeat"] = heartbeat()
            except Exception as exc:
                status["heartbeat_error"] = str(exc)
        status["available"] = True
        status["status"] = "online"
        for name in names:
            status["collections"][name] = _collection_status(client, name)
    except Exception as exc:
        status["status"] = "error"
        status["reason"] = str(exc)
    return status


def _collection_status(client: Any, name: str) -> dict[str, Any]:
    try:
        getter = getattr(client, "get_collection", None)
        collection = getter(name=name) if callable(getter) else client.get_or_create_collection(name=name)
        count = int(collection.count()) if callable(getattr(collection, "count", None)) else 0
        return {"status": "online", "count": count}
    except Exception as exc:
        return {"status": "missing_or_unavailable", "count": 0, "reason": str(exc)}


def _parse_remote_url(value: str) -> dict[str, Any]:
    url = value if "://" in value else f"http://{value}"
    parsed = urlparse(url)
    if not parsed.hostname:
        raise RuntimeError(f"Invalid WINTRIP_CHROMA_HTTP_URL: {_safe_url(value)}")
    ssl = parsed.scheme == "https"
    port = parsed.port or (443 if ssl else 8000)
    return {"host": parsed.hostname, "port": int(port), "ssl": ssl}


def _safe_url(value: str) -> str:
    if not value:
        return ""
    parsed = urlparse(value if "://" in value else f"http://{value}")
    if not parsed.netloc:
        return value
    hostname = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    netloc = f"{hostname}{port}"
    return urlunparse((parsed.scheme or "http", netloc, parsed.path, "", "", ""))
