#!/usr/bin/env python3
"""Validate Wintrip Hippocampus chunks for the 11D Ouroboros metadata contract."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable

from controller.stream.metadata_11d import REQUIRED_11D_KEYS, missing_11d_layers


DEFAULT_COLLECTION = "wintrip_knowledge"


def validate_records(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    total = 0
    for index, record in enumerate(records):
        total += 1
        metadata = _metadata_from_record(record)
        missing = missing_11d_layers(metadata)
        hz_issue = _frequency_issue(metadata)
        record_id = record.get("id") or record.get("ids") or metadata.get("stream_item_id") or f"record-{index}"
        if missing or hz_issue:
            issues.append(
                {
                    "index": index,
                    "id": record_id,
                    "missing_11d_layers": missing,
                    "frequency_issue": hz_issue,
                }
            )

    status = "PASS" if total > 0 and not issues else "FAIL"
    return {
        "protocol": "WINTRIP-AGENT/1.0",
        "script": "validation_script.py",
        "status": status,
        "total_chunks": total,
        "valid_chunks": total - len(issues),
        "invalid_chunks": len(issues),
        "required_11d_layers": list(REQUIRED_11D_KEYS),
        "issues": issues,
    }


def load_records_from_json(path: str | os.PathLike[str]) -> list[dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        if isinstance(data.get("records"), list):
            return [r for r in data["records"] if isinstance(r, dict)]
        if isinstance(data.get("metadatas"), list):
            return _records_from_chroma_get(data)
        return [data]
    return []


def load_records_from_chroma(persist_dir: str, collection_name: str = DEFAULT_COLLECTION) -> list[dict[str, Any]]:
    try:
        import chromadb
    except Exception as exc:  # pragma: no cover - depends on optional runtime
        raise RuntimeError(f"chromadb is niet beschikbaar in deze sandbox: {exc}") from exc

    client = chromadb.PersistentClient(path=persist_dir)
    collection = client.get_collection(name=collection_name)
    result = collection.get(include=["metadatas", "documents"])
    return _records_from_chroma_get(result)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate 11D Wintrip Hippocampus metadata.")
    parser.add_argument("--input-json", help="Path to exported records JSON. Avoids live ChromaDB.")
    parser.add_argument(
        "--persist-dir",
        default=os.getenv("WINTRIP_DB_PATH", os.path.join("wintrip_brain")),
        help="Relative or env-provided ChromaDB path.",
    )
    parser.add_argument(
        "--collection",
        default=os.getenv("WINTRIP_COLLECTION", DEFAULT_COLLECTION),
        help="ChromaDB collection name.",
    )
    args = parser.parse_args(argv)

    try:
        if args.input_json:
            records = load_records_from_json(args.input_json)
        else:
            records = load_records_from_chroma(args.persist_dir, args.collection)
        report = validate_records(records)
    except Exception as exc:
        report = {
            "protocol": "WINTRIP-AGENT/1.0",
            "script": "validation_script.py",
            "status": "ERROR",
            "error": str(exc),
        }

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report.get("status") == "PASS" else 1


def _metadata_from_record(record: dict[str, Any]) -> dict[str, Any]:
    metadata = record.get("metadata")
    if isinstance(metadata, dict):
        return metadata
    metadata = record.get("metadatas")
    if isinstance(metadata, dict):
        return metadata
    return record


def _records_from_chroma_get(result: dict[str, Any]) -> list[dict[str, Any]]:
    ids = result.get("ids") or []
    metadatas = result.get("metadatas") or []
    documents = result.get("documents") or []
    records = []
    for index, metadata in enumerate(metadatas):
        records.append(
            {
                "id": ids[index] if index < len(ids) else f"record-{index}",
                "metadata": metadata or {},
                "document": documents[index] if index < len(documents) else "",
            }
        )
    return records


def _frequency_issue(metadata: dict[str, Any]) -> str:
    raw = metadata.get("dream_hz")
    if raw is None:
        return "dream_hz ontbreekt"
    try:
        hz = float(str(raw).replace("Hz", ""))
    except ValueError:
        return f"dream_hz is niet numeriek: {raw!r}"
    if not 418.0 <= hz <= 432.0:
        return f"dream_hz buiten 418-432Hz: {hz}"
    return ""


if __name__ == "__main__":
    sys.exit(main())
