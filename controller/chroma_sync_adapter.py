"""Approval-gated ChromaDB merge between the local and VPS Ouroboros brains.

This adapter intentionally does not rsync the Chroma sqlite/index files. It
exports collection records through Chroma's public collection API, imports only
missing records, and keeps all raw documents out of the returned tool payloads.
The document payloads travel only over the existing SSH connection.
"""

from __future__ import annotations

import hashlib
import json
import os
import posixpath
import re
import shlex
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from controller.chroma_runtime import (
    DEFAULT_KNOWLEDGE_COLLECTION,
    DEFAULT_OODA_DREAM_COLLECTION,
    DEFAULT_TRAINING_COLLECTION,
    DEFAULT_WORLD_COLLECTION,
    chroma_client,
    chroma_runtime_config,
    chroma_runtime_status,
    default_chroma_path,
)
from controller.safe_shell import workspace_root
from controller.vps_deploy_adapter import (
    APPROVAL_PHRASE,
    REMOTE_ROOT,
    VPSDeployAdapter,
    VPSProfile,
    _binary_exists,
    _bridge_request,
    _sanitize_payload,
    profile_from_env,
    redact_command,
    redact_sensitive_text,
)


DEFAULT_CHROMA_SYNC_COLLECTIONS: tuple[str, ...] = (
    DEFAULT_KNOWLEDGE_COLLECTION,
    DEFAULT_TRAINING_COLLECTION,
    DEFAULT_WORLD_COLLECTION,
    DEFAULT_OODA_DREAM_COLLECTION,
    "wintrip_trigger_actions_11d",
    "wintrip_agentic_sessions_11d",
)
DEFAULT_BATCH_SIZE = 250
DEFAULT_MAX_RECORDS_PER_COLLECTION = 20_000
REMOTE_SAFE_PATH_RE = re.compile(r"^[A-Za-z0-9_./-]{1,500}$")
JSON_MARKER = "WINTRIP_CHROMA_SYNC_JSON:"


@dataclass(frozen=True)
class ChromaSyncConfig:
    collections: tuple[str, ...]
    remote_workspace: str
    remote_chroma_path: str
    remote_chroma_http_url: str = ""
    max_records_per_collection: int = DEFAULT_MAX_RECORDS_PER_COLLECTION

    def sanitized(self) -> dict[str, Any]:
        return {
            "collections": list(self.collections),
            "remote_workspace": self.remote_workspace,
            "remote_chroma_path": self.remote_chroma_path,
            "remote_chroma_http_url": _safe_url(self.remote_chroma_http_url),
            "max_records_per_collection": self.max_records_per_collection,
            "secrets_returned": False,
        }


class ChromaSyncAdapter:
    def __init__(
        self,
        *,
        profile: VPSProfile | None = None,
        workspace: str | Path | None = None,
        ssh_binary: str | None = None,
        runner: Any | None = None,
        config: ChromaSyncConfig | None = None,
    ) -> None:
        self.profile = profile or profile_from_env()
        self.workspace = Path(workspace).expanduser().resolve() if workspace else workspace_root().resolve()
        self.ssh_binary = ssh_binary or os.getenv("WINTRIP_SSH_BIN", "ssh").strip() or "ssh"
        self.runner = runner or subprocess.run
        self.config = config or chroma_sync_config_from_env()

    def status(self, *, timeout_seconds: int = 45, prefer_bridge: bool = True) -> dict[str, Any]:
        if prefer_bridge:
            bridge = _bridge_request("GET", "/chroma-sync/status", {})
            if bridge:
                bridge["via_bridge"] = True
                return _sanitize_payload(bridge)

        direct = self._direct_readiness()
        local = _local_chroma_status(self.config.collections)
        payload: dict[str, Any] = {
            "status": "ready" if direct["ready"] and local.get("status") == "online" else "degraded",
            "operation": "chroma_sync_status",
            "profile": self.profile.sanitized(),
            "workspace": str(self.workspace),
            "config": self.config.sanitized(),
            "local": _status_without_raw_records(local),
            "remote": {},
            "readiness": direct,
            "mutated": False,
            "tokens_returned": False,
            "secrets_returned": False,
            "fake_success": False,
        }
        if direct["ready"]:
            remote = self._remote_command(
                "status",
                {"collections": list(self.config.collections)},
                timeout_seconds=timeout_seconds,
            )
            payload["remote"] = _status_without_raw_records(remote)
            if remote.get("status") == "online" and local.get("status") == "online":
                payload["status"] = "ready"
            elif remote.get("status") == "error":
                payload["status"] = "error"
                payload["reason"] = remote.get("reason", "Remote Chroma status failed.")
        else:
            payload["reason"] = direct["reason"]
        return _sanitize_payload(payload)

    def preview(self, *, timeout_seconds: int = 120, prefer_bridge: bool = True) -> dict[str, Any]:
        if prefer_bridge:
            bridge = _bridge_request("POST", "/chroma-sync/preview", {"timeout_seconds": timeout_seconds})
            if bridge:
                bridge["via_bridge"] = True
                return _sanitize_payload(bridge)

        direct = self._direct_readiness()
        if not direct["ready"]:
            return self._blocked("chroma_sync_preview", direct["reason"])

        local = _export_local_payload(
            self.config.collections,
            include_documents=False,
            max_records_per_collection=self.config.max_records_per_collection,
        )
        if local.get("status") == "error":
            return _sanitize_payload({**local, "operation": "chroma_sync_preview", "mutated": False})

        remote = self._remote_command(
            "export",
            {
                "collections": list(self.config.collections),
                "include_documents": False,
                "max_records_per_collection": self.config.max_records_per_collection,
            },
            timeout_seconds=timeout_seconds,
        )
        if remote.get("status") == "error":
            return _sanitize_payload({**remote, "operation": "chroma_sync_preview", "mutated": False})

        diff = _diff_payloads(local, remote)
        return _sanitize_payload(
            {
                "status": "preview",
                "operation": "chroma_sync_preview",
                "profile": self.profile.sanitized(),
                "config": self.config.sanitized(),
                "local": _summarize_export(local),
                "remote": _summarize_export(remote),
                "diff": diff,
                "dry_run": True,
                "executed": False,
                "mutated": False,
                "approval_required": False,
                "raw_documents_returned": False,
                "tokens_returned": False,
                "secrets_returned": False,
                "fake_success": False,
            }
        )

    def execute(self, *, approval: str = "", timeout_seconds: int = 300, prefer_bridge: bool = True) -> dict[str, Any]:
        if str(approval or "").strip() != APPROVAL_PHRASE:
            return {
                "status": "blocked",
                "operation": "chroma_sync_execute",
                "reason": "Chroma merge execution requires exact Akkoord.",
                "approval_required": True,
                "approval_present": False,
                "executed": False,
                "mutated": False,
                "tokens_returned": False,
                "secrets_returned": False,
                "fake_success": False,
            }
        if prefer_bridge:
            bridge = _bridge_request(
                "POST",
                "/chroma-sync/execute",
                {"approval": approval, "timeout_seconds": timeout_seconds},
            )
            if bridge:
                bridge["via_bridge"] = True
                return _sanitize_payload(bridge)

        direct = self._direct_readiness()
        if not direct["ready"]:
            return self._blocked("chroma_sync_execute", direct["reason"])

        remote_export = self._remote_command(
            "export",
            {
                "collections": list(self.config.collections),
                "include_documents": True,
                "max_records_per_collection": self.config.max_records_per_collection,
            },
            timeout_seconds=timeout_seconds,
        )
        if remote_export.get("status") == "error":
            return _sanitize_payload({**remote_export, "operation": "chroma_sync_execute", "mutated": False})

        local_import = _import_local_payload(remote_export, source_label="vps")
        if local_import.get("status") == "error":
            return _sanitize_payload({**local_import, "operation": "chroma_sync_execute", "mutated": False})

        local_export = _export_local_payload(
            self.config.collections,
            include_documents=True,
            max_records_per_collection=self.config.max_records_per_collection,
        )
        if local_export.get("status") == "error":
            return _sanitize_payload({**local_export, "operation": "chroma_sync_execute", "mutated": False})

        remote_import = self._remote_command(
            "import",
            {
                "collections": list(self.config.collections),
                "source_label": "local",
                "max_records_per_collection": self.config.max_records_per_collection,
            },
            stdin_payload=json.dumps(local_export, ensure_ascii=False, default=str),
            timeout_seconds=timeout_seconds,
        )
        if remote_import.get("status") == "error":
            return _sanitize_payload({**remote_import, "operation": "chroma_sync_execute", "mutated": bool(_imported_count(local_import))})

        imported_local = _imported_count(local_import)
        imported_remote = _imported_count(remote_import)
        return _sanitize_payload(
            {
                "status": "success",
                "operation": "chroma_sync_execute",
                "profile": self.profile.sanitized(),
                "config": self.config.sanitized(),
                "local_import": _summarize_import(local_import),
                "remote_import": _summarize_import(remote_import),
                "executed": True,
                "mutated": bool(imported_local or imported_remote),
                "approval_required": True,
                "approval_present": True,
                "raw_documents_returned": False,
                "tokens_returned": False,
                "secrets_returned": False,
                "fake_success": False,
            }
        )

    def _direct_readiness(self) -> dict[str, Any]:
        config_error = _config_validation_error(self.config)
        if config_error:
            return {"ready": False, "reason": config_error}
        if not _binary_exists(self.ssh_binary):
            return {"ready": False, "reason": "ssh binary is not available on the host bridge/runtime."}
        deploy = VPSDeployAdapter(profile=self.profile, workspace=self.workspace, ssh_binary=self.ssh_binary)
        readiness = deploy._direct_readiness(require_rsync=False)
        if not readiness.get("ready"):
            return readiness
        return {"ready": True, "reason": "ready"}

    def _remote_command(
        self,
        mode: str,
        payload: dict[str, Any],
        *,
        stdin_payload: str | None = None,
        timeout_seconds: int,
    ) -> dict[str, Any]:
        payload = dict(payload)
        payload.setdefault("remote_config", self.config.sanitized())
        remote_command = self._remote_python_command(mode, payload)
        cmd = self._ssh_args(timeout_seconds=timeout_seconds) + [self.profile.remote_login(), remote_command]
        try:
            proc = self.runner(
                cmd,
                input=stdin_payload,
                text=True,
                capture_output=True,
                timeout=max(10, min(int(timeout_seconds or 120), 900)),
                check=False,
            )
        except Exception as exc:
            return self._command_error(mode, cmd, str(exc))
        stdout = str(proc.stdout or "")
        stderr = redact_sensitive_text(str(proc.stderr or ""))[-12000:]
        parsed = _extract_marked_json(stdout)
        if int(proc.returncode or 0) != 0:
            return {
                "status": "error",
                "operation": f"remote_{mode}",
                "reason": stderr or f"Remote Chroma command exited with {int(proc.returncode or 0)}.",
                "exit_code": int(proc.returncode or 0),
                "command_preview": redact_command(cmd),
                "raw_documents_returned": False,
                "mutated": False,
                "fake_success": False,
            }
        if not parsed:
            return {
                "status": "error",
                "operation": f"remote_{mode}",
                "reason": "Remote Chroma command did not return a parseable JSON result.",
                "stderr": stderr,
                "command_preview": redact_command(cmd),
                "raw_documents_returned": False,
                "mutated": False,
                "fake_success": False,
            }
        parsed["remote_stderr"] = stderr
        parsed["command_preview"] = redact_command(cmd)
        return parsed

    def _remote_python_command(self, mode: str, payload: dict[str, Any]) -> str:
        env_parts = []
        if self.config.remote_chroma_http_url:
            env_parts.append(f"WINTRIP_CHROMA_HTTP_URL={shlex.quote(self.config.remote_chroma_http_url)}")
        elif self.config.remote_chroma_path:
            env_parts.append(f"WINTRIP_DB_PATH={shlex.quote(self.config.remote_chroma_path)}")
        script = shlex.quote(REMOTE_CHROMA_SCRIPT)
        payload_json = shlex.quote(json.dumps(payload, ensure_ascii=False, default=str))
        prefix = " ".join(env_parts + ["python3", "-c", script, shlex.quote(mode), payload_json])
        return f"cd {shlex.quote(self.config.remote_workspace)} && {prefix}"

    def _ssh_args(self, *, timeout_seconds: int) -> list[str]:
        connect_timeout = max(3, min(int(timeout_seconds or 30), 30))
        args = [
            self.ssh_binary,
            "-o",
            "BatchMode=yes",
            "-o",
            "PasswordAuthentication=no",
            "-o",
            f"ConnectTimeout={connect_timeout}",
        ]
        if self.profile.port:
            args.extend(["-p", str(int(self.profile.port))])
        return args

    def _command_error(self, mode: str, cmd: list[str], reason: str) -> dict[str, Any]:
        return {
            "status": "error",
            "operation": f"remote_{mode}",
            "reason": redact_sensitive_text(reason),
            "command_preview": redact_command(cmd),
            "raw_documents_returned": False,
            "mutated": False,
            "fake_success": False,
        }

    def _blocked(self, operation: str, reason: str) -> dict[str, Any]:
        return {
            "status": "blocked",
            "operation": operation,
            "reason": reason,
            "profile": self.profile.sanitized(),
            "config": self.config.sanitized(),
            "executed": False,
            "mutated": False,
            "raw_documents_returned": False,
            "tokens_returned": False,
            "secrets_returned": False,
            "fake_success": False,
        }


def chroma_sync_config_from_env() -> ChromaSyncConfig:
    collections = _collection_list(os.getenv("WINTRIP_CHROMA_SYNC_COLLECTIONS", ""))
    remote_workspace = str(os.getenv("WINTRIP_VPS_REMOTE_WORKSPACE") or REMOTE_ROOT.rstrip("/")).strip()
    remote_chroma_http_url = str(os.getenv("WINTRIP_VPS_REMOTE_CHROMA_HTTP_URL") or "").strip()
    remote_chroma_path = str(os.getenv("WINTRIP_VPS_REMOTE_CHROMA_PATH") or "").strip()
    if not remote_chroma_path:
        remote_chroma_path = posixpath.join(remote_workspace.rstrip("/"), "wintrip_brain")
    try:
        max_records = int(os.getenv("WINTRIP_CHROMA_SYNC_MAX_RECORDS", str(DEFAULT_MAX_RECORDS_PER_COLLECTION)))
    except ValueError:
        max_records = DEFAULT_MAX_RECORDS_PER_COLLECTION
    return ChromaSyncConfig(
        collections=collections,
        remote_workspace=remote_workspace,
        remote_chroma_path=remote_chroma_path,
        remote_chroma_http_url=remote_chroma_http_url,
        max_records_per_collection=max(1, min(max_records, 100_000)),
    )


def _collection_list(raw: str) -> tuple[str, ...]:
    values = [item.strip() for item in str(raw or "").replace(";", ",").split(",") if item.strip()]
    return tuple(dict.fromkeys(values or list(DEFAULT_CHROMA_SYNC_COLLECTIONS)))


def _config_validation_error(config: ChromaSyncConfig) -> str:
    if not config.collections:
        return "No Chroma collections configured for sync."
    for name in config.collections:
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", name):
            return f"Unsafe Chroma collection name: {name}"
    for label, value in (("remote_workspace", config.remote_workspace), ("remote_chroma_path", config.remote_chroma_path)):
        if not value or "\x00" in value or not REMOTE_SAFE_PATH_RE.fullmatch(value):
            return f"Unsafe {label} metadata."
    if config.remote_chroma_http_url and _url_has_credentials(config.remote_chroma_http_url):
        return "Remote Chroma HTTP URL must not contain credentials."
    return ""


def _local_chroma_status(collections: tuple[str, ...]) -> dict[str, Any]:
    status = chroma_runtime_status(list(collections))
    status["config"] = chroma_runtime_config()
    return status


def _status_without_raw_records(payload: dict[str, Any]) -> dict[str, Any]:
    clean = dict(payload or {})
    clean.pop("records", None)
    clean.pop("raw", None)
    return clean


def _export_local_payload(
    collections: tuple[str, ...],
    *,
    include_documents: bool,
    max_records_per_collection: int,
) -> dict[str, Any]:
    try:
        client = chroma_client()
    except Exception as exc:
        return {"status": "error", "reason": f"Local Chroma unavailable: {exc}", "fake_success": False}
    return _export_from_client(
        client,
        collections,
        include_documents=include_documents,
        max_records_per_collection=max_records_per_collection,
        origin="local",
    )


def _export_from_client(
    client: Any,
    collections: tuple[str, ...] | list[str],
    *,
    include_documents: bool,
    max_records_per_collection: int,
    origin: str,
) -> dict[str, Any]:
    exported: dict[str, Any] = {}
    for name in collections:
        exported[str(name)] = _export_collection(
            client,
            str(name),
            include_documents=include_documents,
            max_records=max_records_per_collection,
        )
    return {
        "status": "success",
        "origin": origin,
        "collections": exported,
        "include_documents": include_documents,
        "raw_documents_in_payload": include_documents,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "fake_success": False,
    }


def _export_collection(client: Any, name: str, *, include_documents: bool, max_records: int) -> dict[str, Any]:
    try:
        collection = client.get_collection(name=name)
    except Exception as exc:
        return {"status": "missing", "count": 0, "records": [], "reason": str(exc)[:240]}
    try:
        count = int(collection.count()) if callable(getattr(collection, "count", None)) else 0
    except Exception:
        count = 0

    records: list[dict[str, Any]] = []
    offset = 0
    include = ["metadatas"]
    if include_documents:
        include = ["documents", "metadatas", "embeddings"]
    while offset < min(count or max_records, max_records):
        limit = min(DEFAULT_BATCH_SIZE, max_records - offset)
        if limit <= 0:
            break
        try:
            raw = collection.get(limit=limit, offset=offset, include=include)
        except TypeError:
            raw = collection.get(limit=limit, include=include)
            offset = max_records
        except Exception as exc:
            if include_documents and "embeddings" in include:
                include = ["documents", "metadatas"]
                continue
            return {"status": "error", "count": count, "records": records, "reason": str(exc)[:240]}
        ids = list(raw.get("ids") or [])
        if not ids:
            break
        documents = list(raw.get("documents") or [])
        metadatas = list(raw.get("metadatas") or [])
        embeddings = list(raw.get("embeddings") or [])
        for index, item_id in enumerate(ids):
            document = documents[index] if index < len(documents) else ""
            metadata = metadatas[index] if index < len(metadatas) and isinstance(metadatas[index], dict) else {}
            embedding = embeddings[index] if index < len(embeddings) else None
            record = {
                "id": str(item_id),
                "metadata": _sanitize_metadata(metadata),
                "fingerprint": _record_fingerprint({"id": item_id, "document": document, "metadata": metadata}),
            }
            if include_documents:
                record["document"] = str(document or "")
                if _is_embedding(embedding):
                    record["embedding"] = [float(value) for value in embedding]
            records.append(record)
        if len(ids) < limit:
            break
        offset += len(ids)
    return {
        "status": "online",
        "count": count,
        "exported": len(records),
        "truncated": bool(count > len(records)),
        "records": records,
    }


def _import_local_payload(payload: dict[str, Any], *, source_label: str) -> dict[str, Any]:
    try:
        client = chroma_client()
    except Exception as exc:
        return {"status": "error", "reason": f"Local Chroma unavailable: {exc}", "fake_success": False}
    return _import_into_client(client, payload, source_label=source_label)


def _import_into_client(client: Any, payload: dict[str, Any], *, source_label: str) -> dict[str, Any]:
    collections = payload.get("collections") if isinstance(payload, dict) else {}
    if not isinstance(collections, dict):
        return {"status": "error", "reason": "Invalid Chroma sync payload.", "fake_success": False}
    report: dict[str, Any] = {}
    for name, details in collections.items():
        if not isinstance(details, dict) or details.get("status") not in {"online", "success"}:
            report[str(name)] = {"status": "skipped", "reason": "source collection unavailable", "imported": 0}
            continue
        report[str(name)] = _import_collection(client, str(name), list(details.get("records") or []), source_label=source_label)
    return {
        "status": "success",
        "operation": "chroma_import",
        "source_label": source_label,
        "collections": report,
        "imported_total": _imported_count({"collections": report}),
        "mutated": bool(_imported_count({"collections": report})),
        "fake_success": False,
    }


def _import_collection(client: Any, name: str, records: list[dict[str, Any]], *, source_label: str) -> dict[str, Any]:
    try:
        collection = client.get_or_create_collection(name=name)
    except Exception as exc:
        return {"status": "error", "reason": str(exc)[:240], "imported": 0, "skipped": 0}
    existing = _collection_fingerprints(collection)
    imported = 0
    skipped = 0
    conflicts = 0
    errors: list[str] = []
    for record in records:
        if not isinstance(record, dict):
            skipped += 1
            continue
        fingerprint = _record_fingerprint(record)
        if fingerprint in existing["fingerprints"]:
            skipped += 1
            continue
        item_id = str(record.get("id") or f"chroma_sync_{fingerprint[:24]}")
        if item_id in existing["ids"]:
            conflicts += 1
            item_id = f"{item_id}__{source_label}_{fingerprint[:12]}"
        metadata = _sanitize_metadata(record.get("metadata") or {})
        metadata["chroma_sync_origin"] = source_label
        metadata["chroma_sync_source_id"] = str(record.get("id") or "")
        metadata["chroma_sync_fingerprint"] = fingerprint
        metadata["chroma_sync_merged_at"] = datetime.now(timezone.utc).isoformat()
        kwargs: dict[str, Any] = {
            "ids": [item_id],
            "documents": [str(record.get("document") or "")],
            "metadatas": [metadata],
        }
        embedding = record.get("embedding")
        if _is_embedding(embedding):
            kwargs["embeddings"] = [[float(value) for value in embedding]]
        try:
            collection.add(**kwargs)
        except Exception as exc:
            errors.append(str(exc)[:180])
            skipped += 1
            continue
        imported += 1
        existing["ids"].add(item_id)
        existing["fingerprints"].add(fingerprint)
    return {
        "status": "success" if not errors else "partial",
        "incoming": len(records),
        "imported": imported,
        "skipped": skipped,
        "conflicts_renamed": conflicts,
        "errors": errors[:5],
    }


def _collection_fingerprints(collection: Any) -> dict[str, set[str]]:
    ids: set[str] = set()
    fingerprints: set[str] = set()
    try:
        count = int(collection.count()) if callable(getattr(collection, "count", None)) else 0
    except Exception:
        count = 0
    offset = 0
    while offset < count:
        limit = min(DEFAULT_BATCH_SIZE, count - offset)
        try:
            raw = collection.get(limit=limit, offset=offset, include=["metadatas"])
        except TypeError:
            raw = collection.get(limit=limit, include=["metadatas"])
            offset = count
        except Exception:
            break
        batch_ids = list(raw.get("ids") or [])
        metas = list(raw.get("metadatas") or [])
        if not batch_ids:
            break
        for index, item_id in enumerate(batch_ids):
            ids.add(str(item_id))
            metadata = metas[index] if index < len(metas) and isinstance(metas[index], dict) else {}
            fingerprints.add(_record_fingerprint({"id": item_id, "metadata": metadata}))
        if len(batch_ids) < limit:
            break
        offset += len(batch_ids)
    return {"ids": ids, "fingerprints": fingerprints}


def _diff_payloads(local: dict[str, Any], remote: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {"collections": {}, "missing_on_local_total": 0, "missing_on_remote_total": 0}
    local_collections = local.get("collections") if isinstance(local, dict) else {}
    remote_collections = remote.get("collections") if isinstance(remote, dict) else {}
    names = sorted(set((local_collections or {}).keys()) | set((remote_collections or {}).keys()))
    for name in names:
        local_fps = _payload_fingerprints((local_collections or {}).get(name, {}))
        remote_fps = _payload_fingerprints((remote_collections or {}).get(name, {}))
        missing_local = len(remote_fps - local_fps)
        missing_remote = len(local_fps - remote_fps)
        output["collections"][name] = {
            "local_exported": len(local_fps),
            "remote_exported": len(remote_fps),
            "missing_on_local": missing_local,
            "missing_on_remote": missing_remote,
        }
        output["missing_on_local_total"] += missing_local
        output["missing_on_remote_total"] += missing_remote
    return output


def _payload_fingerprints(collection_payload: dict[str, Any]) -> set[str]:
    if not isinstance(collection_payload, dict):
        return set()
    return {_record_fingerprint(record) for record in list(collection_payload.get("records") or []) if isinstance(record, dict)}


def _record_fingerprint(record: dict[str, Any]) -> str:
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    for key in ("content_hash", "source_hash", "chroma_sync_fingerprint"):
        value = metadata.get(key)
        if value:
            return f"{key}:{value}"
    document = str(record.get("document") or "")
    if document:
        return "doc_sha256:" + hashlib.sha256(document.encode("utf-8", errors="replace")).hexdigest()
    return "id:" + str(record.get("id") or "")


def _sanitize_metadata(metadata: dict[str, Any]) -> dict[str, str | int | float | bool]:
    clean: dict[str, str | int | float | bool] = {}
    for key, value in dict(metadata or {}).items():
        lowered = str(key).lower()
        if any(marker in lowered for marker in ("token", "secret", "password", "passwd", "bearer", "authorization", "cookie")):
            clean[str(key)] = "[REDACTED]"
        elif isinstance(value, (str, int, float, bool)):
            clean[str(key)] = value
        elif value is None:
            clean[str(key)] = ""
        else:
            clean[str(key)] = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)[:900]
    return clean


def _summarize_export(payload: dict[str, Any]) -> dict[str, Any]:
    collections = payload.get("collections") if isinstance(payload, dict) else {}
    return {
        "status": payload.get("status"),
        "origin": payload.get("origin"),
        "collections": {
            str(name): {
                "status": details.get("status") if isinstance(details, dict) else "unknown",
                "count": details.get("count", 0) if isinstance(details, dict) else 0,
                "exported": len(details.get("records") or []) if isinstance(details, dict) else 0,
                "truncated": bool(details.get("truncated")) if isinstance(details, dict) else False,
            }
            for name, details in (collections or {}).items()
        },
        "raw_documents_returned": False,
    }


def _summarize_import(payload: dict[str, Any]) -> dict[str, Any]:
    collections = payload.get("collections") if isinstance(payload, dict) else {}
    return {
        "status": payload.get("status"),
        "imported_total": _imported_count(payload),
        "collections": {
            str(name): {
                "status": details.get("status") if isinstance(details, dict) else "unknown",
                "incoming": details.get("incoming", 0) if isinstance(details, dict) else 0,
                "imported": details.get("imported", 0) if isinstance(details, dict) else 0,
                "skipped": details.get("skipped", 0) if isinstance(details, dict) else 0,
                "conflicts_renamed": details.get("conflicts_renamed", 0) if isinstance(details, dict) else 0,
            }
            for name, details in (collections or {}).items()
        },
    }


def _imported_count(payload: dict[str, Any]) -> int:
    collections = payload.get("collections") if isinstance(payload, dict) else {}
    total = 0
    for details in (collections or {}).values():
        if isinstance(details, dict):
            try:
                total += int(details.get("imported") or 0)
            except (TypeError, ValueError):
                continue
    return total


def _is_embedding(value: Any) -> bool:
    if not isinstance(value, (list, tuple)) or not value:
        return False
    try:
        [float(item) for item in value[:3]]
    except Exception:
        return False
    return True


def _extract_marked_json(stdout: str) -> dict[str, Any]:
    for line in reversed(str(stdout or "").splitlines()):
        if line.startswith(JSON_MARKER):
            try:
                value = json.loads(line[len(JSON_MARKER) :])
            except json.JSONDecodeError:
                return {}
            return value if isinstance(value, dict) else {}
    return {}


def _safe_url(value: str) -> str:
    if not value:
        return ""
    from urllib.parse import urlparse, urlunparse

    parsed = urlparse(value if "://" in value else f"http://{value}")
    if not parsed.netloc:
        return value
    hostname = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    return urlunparse((parsed.scheme or "http", f"{hostname}{port}", parsed.path, "", "", ""))


def _url_has_credentials(value: str) -> bool:
    from urllib.parse import urlparse

    parsed = urlparse(value if "://" in value else f"http://{value}")
    return bool(parsed.username or parsed.password)


REMOTE_CHROMA_SCRIPT = r'''
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse

MARKER = "WINTRIP_CHROMA_SYNC_JSON:"
BATCH = 250

def emit(payload):
    print(MARKER + json.dumps(payload, ensure_ascii=False, default=str), flush=True)

def client():
    import chromadb
    url = os.getenv("WINTRIP_CHROMA_HTTP_URL", "").strip()
    if url:
        parsed = urlparse(url if "://" in url else "http://" + url)
        return chromadb.HttpClient(host=parsed.hostname, port=parsed.port or (443 if parsed.scheme == "https" else 8000), ssl=parsed.scheme == "https")
    path = os.getenv("WINTRIP_DB_PATH", "wintrip_brain").strip() or "wintrip_brain"
    os.makedirs(path, exist_ok=True)
    return chromadb.PersistentClient(path=path)

def primitive_meta(meta):
    out = {}
    for key, value in dict(meta or {}).items():
        lower = str(key).lower()
        if any(marker in lower for marker in ("token", "secret", "password", "passwd", "bearer", "authorization", "cookie")):
            out[str(key)] = "[REDACTED]"
        elif isinstance(value, (str, int, float, bool)):
            out[str(key)] = value
        elif value is None:
            out[str(key)] = ""
        else:
            out[str(key)] = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)[:900]
    return out

def record_fingerprint(record):
    meta = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    for key in ("content_hash", "source_hash", "chroma_sync_fingerprint"):
        value = meta.get(key)
        if value:
            return f"{key}:{value}"
    doc = str(record.get("document") or "")
    if doc:
        return "doc_sha256:" + hashlib.sha256(doc.encode("utf-8", errors="replace")).hexdigest()
    return "id:" + str(record.get("id") or "")

def is_embedding(value):
    if not isinstance(value, (list, tuple)) or not value:
        return False
    try:
        [float(item) for item in value[:3]]
    except Exception:
        return False
    return True

def export_collection(chroma, name, include_documents, max_records):
    try:
        collection = chroma.get_collection(name=name)
    except Exception as exc:
        return {"status": "missing", "count": 0, "records": [], "reason": str(exc)[:240]}
    try:
        count = int(collection.count()) if callable(getattr(collection, "count", None)) else 0
    except Exception:
        count = 0
    records = []
    offset = 0
    include = ["metadatas"]
    if include_documents:
        include = ["documents", "metadatas", "embeddings"]
    while offset < min(count or max_records, max_records):
        limit = min(BATCH, max_records - offset)
        if limit <= 0:
            break
        try:
            raw = collection.get(limit=limit, offset=offset, include=include)
        except TypeError:
            raw = collection.get(limit=limit, include=include)
            offset = max_records
        except Exception as exc:
            if include_documents and "embeddings" in include:
                include = ["documents", "metadatas"]
                continue
            return {"status": "error", "count": count, "records": records, "reason": str(exc)[:240]}
        ids = list(raw.get("ids") or [])
        if not ids:
            break
        docs = list(raw.get("documents") or [])
        metas = list(raw.get("metadatas") or [])
        embeddings = list(raw.get("embeddings") or [])
        for index, item_id in enumerate(ids):
            doc = docs[index] if index < len(docs) else ""
            meta = metas[index] if index < len(metas) and isinstance(metas[index], dict) else {}
            embedding = embeddings[index] if index < len(embeddings) else None
            record = {"id": str(item_id), "metadata": primitive_meta(meta)}
            record["fingerprint"] = record_fingerprint({"id": item_id, "document": doc, "metadata": meta})
            if include_documents:
                record["document"] = str(doc or "")
                if is_embedding(embedding):
                    record["embedding"] = [float(value) for value in embedding]
            records.append(record)
        if len(ids) < limit:
            break
        offset += len(ids)
    return {"status": "online", "count": count, "exported": len(records), "truncated": bool(count > len(records)), "records": records}

def export_payload(config):
    chroma = client()
    names = list(config.get("collections") or [])
    include_documents = bool(config.get("include_documents"))
    max_records = max(1, min(int(config.get("max_records_per_collection") or 20000), 100000))
    return {
        "status": "success",
        "origin": "vps",
        "collections": {name: export_collection(chroma, str(name), include_documents, max_records) for name in names},
        "include_documents": include_documents,
        "raw_documents_in_payload": include_documents,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "fake_success": False,
    }

def fingerprints(collection):
    ids = set()
    fps = set()
    try:
        count = int(collection.count()) if callable(getattr(collection, "count", None)) else 0
    except Exception:
        count = 0
    offset = 0
    while offset < count:
        limit = min(BATCH, count - offset)
        try:
            raw = collection.get(limit=limit, offset=offset, include=["metadatas"])
        except TypeError:
            raw = collection.get(limit=limit, include=["metadatas"])
            offset = count
        except Exception:
            break
        batch_ids = list(raw.get("ids") or [])
        metas = list(raw.get("metadatas") or [])
        if not batch_ids:
            break
        for index, item_id in enumerate(batch_ids):
            ids.add(str(item_id))
            meta = metas[index] if index < len(metas) and isinstance(metas[index], dict) else {}
            fps.add(record_fingerprint({"id": item_id, "metadata": meta}))
        if len(batch_ids) < limit:
            break
        offset += len(batch_ids)
    return ids, fps

def import_payload(data, source_label):
    chroma = client()
    collections = data.get("collections") if isinstance(data, dict) else {}
    report = {}
    for name, details in dict(collections or {}).items():
        if not isinstance(details, dict) or details.get("status") not in ("online", "success"):
            report[str(name)] = {"status": "skipped", "reason": "source collection unavailable", "imported": 0, "skipped": 0}
            continue
        collection = chroma.get_or_create_collection(name=str(name))
        ids, fps = fingerprints(collection)
        imported = skipped = conflicts = 0
        errors = []
        for record in list(details.get("records") or []):
            if not isinstance(record, dict):
                skipped += 1
                continue
            fp = record_fingerprint(record)
            if fp in fps:
                skipped += 1
                continue
            item_id = str(record.get("id") or ("chroma_sync_" + fp[:24]))
            if item_id in ids:
                conflicts += 1
                item_id = f"{item_id}__{source_label}_{fp[:12]}"
            meta = primitive_meta(record.get("metadata") or {})
            meta["chroma_sync_origin"] = source_label
            meta["chroma_sync_source_id"] = str(record.get("id") or "")
            meta["chroma_sync_fingerprint"] = fp
            meta["chroma_sync_merged_at"] = datetime.now(timezone.utc).isoformat()
            kwargs = {"ids": [item_id], "documents": [str(record.get("document") or "")], "metadatas": [meta]}
            if is_embedding(record.get("embedding")):
                kwargs["embeddings"] = [[float(value) for value in record.get("embedding")]]
            try:
                collection.add(**kwargs)
            except Exception as exc:
                skipped += 1
                errors.append(str(exc)[:180])
                continue
            imported += 1
            ids.add(item_id)
            fps.add(fp)
        report[str(name)] = {"status": "success" if not errors else "partial", "incoming": len(details.get("records") or []), "imported": imported, "skipped": skipped, "conflicts_renamed": conflicts, "errors": errors[:5]}
    return {"status": "success", "operation": "chroma_import", "source_label": source_label, "collections": report, "imported_total": sum(int(item.get("imported") or 0) for item in report.values()), "fake_success": False}

def status_payload(config):
    chroma = client()
    names = list(config.get("collections") or [])
    collections = {}
    heartbeat = None
    try:
        hb = getattr(chroma, "heartbeat", None)
        heartbeat = hb() if callable(hb) else None
    except Exception as exc:
        heartbeat = "error:" + str(exc)[:120]
    for name in names:
        try:
            collection = chroma.get_collection(name=str(name))
            count = int(collection.count()) if callable(getattr(collection, "count", None)) else 0
            collections[str(name)] = {"status": "online", "count": count}
        except Exception as exc:
            collections[str(name)] = {"status": "missing_or_unavailable", "count": 0, "reason": str(exc)[:160]}
    return {"status": "online", "mode": "http" if os.getenv("WINTRIP_CHROMA_HTTP_URL") else "persistent", "heartbeat": heartbeat, "collections": collections, "fake_success": False}

try:
    mode = sys.argv[1]
    config = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    if mode == "status":
        emit(status_payload(config))
    elif mode == "export":
        emit(export_payload(config))
    elif mode == "import":
        data = json.loads(sys.stdin.read() or "{}")
        emit(import_payload(data, str(config.get("source_label") or "remote")))
    else:
        emit({"status": "error", "reason": "unknown mode", "fake_success": False})
except Exception as exc:
    emit({"status": "error", "reason": str(exc), "fake_success": False})
    raise
'''
