"""Model artifact registry for Ouroboros trainer pipeline.

Tracks training artifacts (checkpoints, LoRA weights, GGUF files, Modelfiles)
and their relationship to trainer jobs. Never sets model.online=true without
Ollama inventory confirmation. Only metadata and relative paths are committed.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from controller.ollama_client import OllamaClient


class ArtifactType(str, Enum):
    """Types of model artifacts."""

    CHECKPOINT = "checkpoint"
    LORA_WEIGHTS = "lora_weights"
    GGUF_MODEL = "gguf_model"
    MODELFILE = "modelfile"
    MERGED_CHECKPOINT = "merged_checkpoint"
    BLUE_BRAIN_MODEL = "blue_brain_model"
    METRICS = "metrics"


def artifacts_registry_path() -> Path:
    """Path to the persistent artifacts registry."""
    workspace = Path(os.getenv("WINTRIP_WORKSPACE") or os.getenv("WORKSPACE_ROOT") or "/workspace")
    if not workspace.exists():
        workspace = Path(os.getenv("WINTRIP_PROJECT_ROOT") or Path.cwd())
    return (workspace / ".secrets" / "model_artifacts.json").resolve()


def load_artifacts() -> dict[str, Any]:
    """Load all artifacts from the registry."""
    path = artifacts_registry_path()
    if not path.exists():
        return {"artifacts": {}, "last_updated": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"artifacts": {}, "last_updated": None}
    if not isinstance(data, dict):
        return {"artifacts": {}, "last_updated": None}
    if "artifacts" not in data:
        data["artifacts"] = {}
    return data


def save_artifacts(data: dict[str, Any]) -> None:
    """Save artifacts to the registry."""
    path = artifacts_registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data["last_updated"] = datetime.utcnow().isoformat()
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def register_artifact(
    job_id: str,
    artifact_type: ArtifactType,
    path: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Register a new model artifact.
    
    Args:
        job_id: Associated trainer job ID
        artifact_type: Type of artifact
        path: Relative or absolute path to the artifact
        metadata: Additional metadata (size, hash, etc.)
    
    Returns:
        Registered artifact record
    """
    data = load_artifacts()
    artifact_id = f"{job_id}_{artifact_type.value}_{datetime.utcnow().timestamp()}"
    
    # Convert to relative path if possible
    workspace = Path(os.getenv("WINTRIP_WORKSPACE") or os.getenv("WORKSPACE_ROOT") or "/workspace")
    try:
        artifact_path = Path(path).resolve()
        relative_path = str(artifact_path.relative_to(workspace))
    except (ValueError, OSError):
        relative_path = str(path)
    
    artifact = {
        "artifact_id": artifact_id,
        "job_id": job_id,
        "artifact_type": artifact_type.value,
        "path": relative_path,
        "registered_at": datetime.utcnow().isoformat(),
        "metadata": metadata or {},
    }
    
    data["artifacts"][artifact_id] = artifact
    save_artifacts(data)
    return artifact


def get_artifact(artifact_id: str) -> dict[str, Any] | None:
    """Get a specific artifact by ID."""
    data = load_artifacts()
    return data["artifacts"].get(artifact_id)


def list_artifacts(job_id: str | None = None, artifact_type: ArtifactType | None = None) -> list[dict[str, Any]]:
    """List artifacts, optionally filtered by job ID or type."""
    data = load_artifacts()
    artifacts = list(data["artifacts"].values())
    
    if job_id:
        artifacts = [a for a in artifacts if a.get("job_id") == job_id]
    
    if artifact_type:
        artifacts = [a for a in artifacts if a.get("artifact_type") == artifact_type.value]
    
    return sorted(artifacts, key=lambda a: a.get("registered_at", ""), reverse=True)


def delete_artifact(artifact_id: str) -> bool:
    """Delete an artifact from the registry (does not delete the file)."""
    data = load_artifacts()
    if artifact_id in data["artifacts"]:
        del data["artifacts"][artifact_id]
        save_artifacts(data)
        return True
    return False


def register_ollama_model(
    job_id: str,
    gguf_path: str,
    modelfile_path: str,
    model_name: str,
) -> dict[str, Any]:
    """Register an Ollama model after successful creation.
    
    Only sets model.online=true after Ollama inventory confirms the model exists.
    
    Args:
        job_id: Associated trainer job ID
        gguf_path: Path to GGUF file
        modelfile_path: Path to Modelfile
        model_name: Ollama model name
    
    Returns:
        Model registration record
    """
    # Register the GGUF artifact
    register_artifact(job_id, ArtifactType.GGUF_MODEL, gguf_path)
    
    # Register the Modelfile artifact
    register_artifact(job_id, ArtifactType.MODELFILE, modelfile_path)
    
    # Check Ollama inventory
    client = OllamaClient()
    try:
        models = client.list_models()
        model_names = [m.get("name", "") for m in models]
        online = model_name in model_names
    except Exception:
        online = False
    
    # Register the model
    data = load_artifacts()
    model_id = f"ollama_{model_name}"
    
    model_record = {
        "model_id": model_id,
        "job_id": job_id,
        "model_name": model_name,
        "gguf_path": gguf_path,
        "modelfile_path": modelfile_path,
        "online": online,
        "registered_at": datetime.utcnow().isoformat(),
        "last_checked": datetime.utcnow().isoformat(),
    }
    
    data["artifacts"][model_id] = model_record
    save_artifacts(data)
    
    return model_record


def check_ollama_model_online(model_name: str) -> bool:
    """Check if an Ollama model is online (in inventory).
    
    This is the only way to set model.online=true.
    """
    client = OllamaClient()
    try:
        models = client.list_models()
        model_names = [m.get("name", "") for m in models]
        return model_name in model_names
    except Exception:
        return False


def update_model_online_status(model_name: str) -> dict[str, Any] | None:
    """Update a model's online status based on Ollama inventory.
    
    Args:
        model_name: Ollama model name
    
    Returns:
        Updated model record or None if not found
    """
    data = load_artifacts()
    model_id = f"ollama_{model_name}"
    
    if model_id not in data["artifacts"]:
        return None
    
    online = check_ollama_model_online(model_name)
    data["artifacts"][model_id]["online"] = online
    data["artifacts"][model_id]["last_checked"] = datetime.utcnow().isoformat()
    save_artifacts(data)
    
    return data["artifacts"][model_id]


def get_artifacts_summary() -> dict[str, Any]:
    """Get a summary of all registered artifacts."""
    data = load_artifacts()
    artifacts = list(data["artifacts"].values())
    
    # Count by type
    by_type: dict[str, int] = {}
    for a in artifacts:
        atype = a.get("artifact_type", "unknown")
        by_type[atype] = by_type.get(atype, 0) + 1
    
    # Count online Ollama models
    online_models = [a for a in artifacts if a.get("artifact_type") == "ollama_model" and a.get("online")]
    
    return {
        "total_artifacts": len(artifacts),
        "by_type": by_type,
        "online_ollama_models": len(online_models),
        "last_updated": data.get("last_updated"),
    }
