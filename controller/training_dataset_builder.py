"""Dataset builder for trainer pipeline from approved 11D ChromaDB records.

Only records with approval_status='approved', learnable=True and audit_only=False
are used for training.
Browser data remains UNTRUSTED until scrubbed and approved.
Exports to JSONL with prompt/completion/chat format including 11D geometry metadata.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from controller.chroma_runtime import default_chroma_path, get_or_create_collection
from controller.training_curriculum import classify_record, coverage_from_records


def chroma_path() -> Path:
    """Path to the ChromaDB persistent storage."""
    return default_chroma_path()


def get_training_collection() -> Any | None:
    """Get the ChromaDB training collection."""
    try:
        collection_name = os.getenv("WINTRIP_TRAINING_COLLECTION", "wintrip_training_11d")
        return get_or_create_collection(name=collection_name)
    except Exception:
        return None


def get_approved_records(limit: int = 1000, *, require_learnable: bool = True) -> list[dict[str, Any]]:
    """Fetch approved 11D records from the training collection."""
    collection = get_training_collection()
    if not collection:
        return []
    
    try:
        # Get all records and filter by approval_status
        results = collection.get(
            limit=limit,
            include=["documents", "metadatas"]
        )
        
        approved = []
        if results and results["documents"]:
            for doc, meta in zip(results["documents"], results["metadatas"]):
                if _is_approved_record(meta, require_learnable=require_learnable):
                    approved.append(
                        {
                            "document": doc,
                            "metadata": meta,
                        }
                    )
        
        return approved
    except Exception:
        return []


def get_curriculum_records(limit: int = 5000) -> list[dict[str, Any]]:
    """Fetch approved records for curriculum coverage, including legacy records.

    Older approved records predate the learnable flag. They should still count
    toward knowledge coverage, while actual dataset building remains stricter.
    """
    return get_approved_records(limit=limit, require_learnable=False)


def _is_approved_record(meta: dict[str, Any] | None, *, require_learnable: bool) -> bool:
    if not meta or meta.get("approval_status") != "approved":
        return False
    if _truthy(meta.get("audit_only")):
        return False
    if require_learnable and not _truthy(meta.get("learnable")):
        return False
    if not require_learnable and _explicitly_false(meta.get("learnable")):
        return False
    return True


def _explicitly_false(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value is False
    if isinstance(value, (int, float)):
        return value == 0
    return str(value).strip().lower() in {"0", "false", "no", "n", "off", "not_learnable", "unlearnable"}


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on", "learnable"}


def count_approved_records() -> int:
    """Count total approved records in training collection."""
    return len(get_approved_records(limit=10000))


def build_dataset(
    output_path: str,
    format: str = "chat",
    max_records: int = 1000,
    include_system_prompt: bool = True,
) -> dict[str, Any]:
    """Build a training dataset from approved 11D records.
    
    Args:
        output_path: Path where JSONL dataset will be written
        format: 'chat' for OpenAI-style chat format, 'completion' for prompt/completion
        max_records: Maximum number of records to include
        include_system_prompt: Whether to include system prompts from metadata
    
    Returns:
        Dict with dataset statistics and path
    """
    records = get_approved_records(limit=max_records)
    if not records:
        return {
            "status": "error",
            "reason": "No approved records found in training collection",
            "record_count": 0,
            "output_path": output_path,
        }
    
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    dataset_entries = []
    included_count = 0
    
    for record in records:
        doc = record["document"]
        meta = record["metadata"]
        
        # Skip browser data unless explicitly approved and scrubbed
        source_type = meta.get("source_type", "")
        taint = meta.get("taint") or meta.get("d8_karmic_taint", "")
        if "browser" in source_type.lower() and "untrusted" in taint.lower():
            continue
        
        # Build entry based on format
        if format == "chat":
            entry = _build_chat_entry(doc, meta, include_system_prompt)
        elif format == "text":
            entry = _build_text_entry(doc, meta)
        else:
            entry = _build_completion_entry(doc, meta)
        
        if entry:
            dataset_entries.append(entry)
            included_count += 1
    
    # Write JSONL
    with open(output_file, "w", encoding="utf-8") as f:
        for entry in dataset_entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    
    return {
        "status": "success",
        "output_path": str(output_file),
        "format": format,
        "total_approved": len(records),
        "included_count": included_count,
        "skipped_untrusted": len(records) - included_count,
        "curriculum_coverage": coverage_from_records(records),
        "created_at": datetime.utcnow().isoformat(),
    }


def _build_chat_entry(document: str, metadata: dict[str, Any], include_system: bool) -> dict[str, Any] | None:
    """Build a chat-format entry with 11D metadata."""
    if not document or not document.strip():
        return None
    
    messages = []
    
    # Add system prompt if available and requested
    if include_system:
        system_prompt = metadata.get("system_prompt") or metadata.get("d5_persona_actor", "")
        if system_prompt:
            messages.append({
                "role": "system",
                "content": str(system_prompt),
            })
    
    # Extract user/assistant structure if present
    doc_type = metadata.get("type", "")
    source = metadata.get("source", "")
    
    # Simple heuristic: if document looks like a conversation, split it
    if "user:" in document.lower() or "assistant:" in document.lower():
        lines = document.split("\n")
        current_role = "user"
        current_content = []
        
        for line in lines:
            line_lower = line.lower().strip()
            if line_lower.startswith("user:") or line_lower.startswith("philip:"):
                if current_content:
                    messages.append({"role": current_role, "content": "\n".join(current_content).strip()})
                current_role = "user"
                current_content = [line.split(":", 1)[1].strip() if ":" in line else line]
            elif line_lower.startswith("assistant:") or line_lower.startswith("ai:"):
                if current_content:
                    messages.append({"role": current_role, "content": "\n".join(current_content).strip()})
                current_role = "assistant"
                current_content = [line.split(":", 1)[1].strip() if ":" in line else line]
            else:
                current_content.append(line)
        
        if current_content:
            messages.append({"role": current_role, "content": "\n".join(current_content).strip()})
    else:
        # Treat as single user message
        messages.append({
            "role": "user",
            "content": document.strip(),
        })
    
    # Add 11D geometry metadata
    entry = {
        "messages": messages,
        "curriculum": classify_record(document, metadata),
        "metadata_11d": {
            "dimension_count": metadata.get("dimension_count", 11),
            "dream_hz": metadata.get("dream_hz", 418.0),
            "radius": metadata.get("radius", 0.0),
            "volume": metadata.get("volume", 0.0),
            "surface_area": metadata.get("surface_area", metadata.get("oppervlakte", 0.0)),
            "resonance_score": metadata.get("resonance_score", 0.0),
            "source": source,
            "source_type": metadata.get("source_type", ""),
            "approval_status": metadata.get("approval_status", ""),
            "content_hash": metadata.get("content_hash", ""),
            "type": doc_type,
        },
    }
    
    return entry


def _build_completion_entry(document: str, metadata: dict[str, Any]) -> dict[str, Any] | None:
    """Build a prompt/completion-format entry with 11D metadata."""
    if not document or not document.strip():
        return None
    
    # Simple split: first paragraph as prompt, rest as completion
    paragraphs = [p.strip() for p in document.split("\n\n") if p.strip()]
    if len(paragraphs) < 1:
        return None
    
    prompt = paragraphs[0]
    completion = "\n\n".join(paragraphs[1:]) if len(paragraphs) > 1 else ""
    
    entry = {
        "prompt": prompt,
        "completion": completion,
        "curriculum": classify_record(document, metadata),
        "metadata_11d": {
            "dimension_count": metadata.get("dimension_count", 11),
            "dream_hz": metadata.get("dream_hz", 418.0),
            "radius": metadata.get("radius", 0.0),
            "volume": metadata.get("volume", 0.0),
            "surface_area": metadata.get("surface_area", metadata.get("oppervlakte", 0.0)),
            "resonance_score": metadata.get("resonance_score", 0.0),
            "source": metadata.get("source", ""),
            "source_type": metadata.get("source_type", ""),
            "approval_status": metadata.get("approval_status", ""),
            "content_hash": metadata.get("content_hash", ""),
            "type": metadata.get("type", ""),
        },
    }
    
    return entry


def _build_text_entry(document: str, metadata: dict[str, Any]) -> dict[str, Any] | None:
    """Build a plain SFT text entry for trainers that expect dataset_text_field='text'."""
    if not document or not document.strip():
        return None

    return {
        "text": document.strip(),
        "curriculum": classify_record(document, metadata),
        "metadata_11d": {
            "dimension_count": metadata.get("dimension_count", 11),
            "dream_hz": metadata.get("dream_hz", 418.0),
            "radius": metadata.get("radius", metadata.get("geometry_11d_radius", 0.0)),
            "volume": metadata.get("volume", metadata.get("geometry_11d_volume", 0.0)),
            "surface_area": metadata.get("surface_area", metadata.get("geometry_11d_oppervlakte", 0.0)),
            "resonance_score": metadata.get("resonance_score", 0.0),
            "source": metadata.get("source", ""),
            "source_type": metadata.get("source_type", ""),
            "approval_status": metadata.get("approval_status", ""),
            "content_hash": metadata.get("content_hash", ""),
            "type": metadata.get("type", ""),
        },
    }


def preview_dataset(max_records: int = 10) -> dict[str, Any]:
    """Preview approved records without building full dataset."""
    records = get_approved_records(limit=max_records)
    
    preview = {
        "total_approved_available": count_approved_records(),
        "preview_count": len(records),
        "curriculum_coverage": coverage_from_records(records),
        "records": [],
    }
    
    for record in records:
        meta = record["metadata"]
        preview["records"].append({
            "type": meta.get("type", ""),
            "source": meta.get("source", ""),
            "source_type": meta.get("source_type", ""),
            "approval_status": meta.get("approval_status", ""),
            "taint": meta.get("d8_karmic_taint", ""),
            "dream_hz": meta.get("dream_hz", 0.0),
            "resonance_score": meta.get("resonance_score", 0.0),
            "curriculum": classify_record(record["document"], meta),
            "document_preview": record["document"][:200] + "..." if len(record["document"]) > 200 else record["document"],
        })
    
    return preview
