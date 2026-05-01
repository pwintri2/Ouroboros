"""Trainer job model and persistent registry for Ouroboros fine-tuning pipeline.

Jobs track the full lifecycle from draft through training to Ollama model creation.
Only real LitGPT/Unsloth jobs with artifact registration can set status=success.
No fake completion claims - model.online=true requires Ollama inventory confirmation.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class JobState(str, Enum):
    """Trainer job states following the approved pipeline."""

    DRAFT = "draft"
    APPROVED = "approved"
    DATASET_READY = "dataset_ready"
    TRAINING = "training"
    VALIDATING = "validating"
    EXPORTING = "exporting"
    OLLAMA_CREATE = "ollama_create"
    ONLINE = "online"
    FAILED = "failed"


class TrainerMethod(str, Enum):
    """Supported training backends."""

    LITGPT = "litgpt"
    UNSLOOTH = "unsloth"
    BLUE_BRAIN = "blue_brain"


def trainer_jobs_path() -> Path:
    """Path to the persistent trainer jobs registry."""
    workspace = Path(os.getenv("WINTRIP_WORKSPACE") or os.getenv("WORKSPACE_ROOT") or "/workspace")
    if not workspace.exists():
        workspace = Path(os.getenv("WINTRIP_PROJECT_ROOT") or Path.cwd())
    return (workspace / ".secrets" / "trainer_jobs.json").resolve()


def load_jobs() -> dict[str, dict[str, Any]]:
    """Load all trainer jobs from the registry."""
    path = trainer_jobs_path()
    if not path.exists():
        return {"jobs": {}, "last_updated": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"jobs": {}, "last_updated": None}
    if not isinstance(data, dict):
        return {"jobs": {}, "last_updated": None}
    if "jobs" not in data:
        data["jobs"] = {}
    return data


def save_jobs(data: dict[str, Any]) -> None:
    """Save trainer jobs to the registry."""
    path = trainer_jobs_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data["last_updated"] = datetime.utcnow().isoformat()
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def create_job(
    base_model: str,
    method: TrainerMethod = TrainerMethod.LITGPT,
    lora_r: int = 8,
    lora_alpha: int = 16,
    lora_dropout: float = 0.05,
    learning_rate: float = 2e-4,
    batch_size: int = 4,
    epochs: int = 3,
    description: str = "",
    extra_training_params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a new trainer job in draft state."""
    job_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    training_params = {
        "learning_rate": learning_rate,
        "batch_size": batch_size,
        "epochs": epochs,
    }
    if extra_training_params:
        training_params.update(extra_training_params)
    job: dict[str, Any] = {
        "job_id": job_id,
        "state": JobState.DRAFT.value,
        "method": method.value,
        "base_model": base_model,
        "lora_params": {
            "r": lora_r,
            "alpha": lora_alpha,
            "dropout": lora_dropout,
        },
        "training_params": training_params,
        "description": description,
        "created_at": now,
        "updated_at": now,
        "dataset_path": None,
        "dataset_record_count": 0,
        "training_started_at": None,
        "training_completed_at": None,
        "validation_passed": False,
        "exported_artifacts": {},
        "ollama_model_name": None,
        "ollama_created_at": None,
        "logs": [],
        "error": None,
    }
    data = load_jobs()
    data["jobs"][job_id] = job
    save_jobs(data)
    return job


def get_job(job_id: str) -> dict[str, Any] | None:
    """Get a specific job by ID."""
    data = load_jobs()
    return data["jobs"].get(job_id)


def list_jobs(state: JobState | None = None) -> list[dict[str, Any]]:
    """List all jobs, optionally filtered by state."""
    data = load_jobs()
    jobs = list(data["jobs"].values())
    if state:
        jobs = [j for j in jobs if j.get("state") == state.value]
    return sorted(jobs, key=lambda j: j.get("created_at", ""), reverse=True)


def update_job_state(job_id: str, new_state: JobState, log_entry: str = "", error: str | None = None) -> dict[str, Any] | None:
    """Update job state with optional log entry."""
    data = load_jobs()
    job = data["jobs"].get(job_id)
    if not job:
        return None
    
    job["state"] = new_state.value
    job["updated_at"] = datetime.utcnow().isoformat()
    
    if log_entry:
        job["logs"].append({
            "timestamp": datetime.utcnow().isoformat(),
            "state": new_state.value,
            "message": log_entry,
        })
    
    if error:
        job["error"] = error
    
    # Update timestamps based on state
    if new_state == JobState.TRAINING and not job.get("training_started_at"):
        job["training_started_at"] = datetime.utcnow().isoformat()
    elif new_state in (JobState.ONLINE, JobState.FAILED) and not job.get("training_completed_at"):
        job["training_completed_at"] = datetime.utcnow().isoformat()
    elif new_state == JobState.OLLAMA_CREATE and not job.get("ollama_created_at"):
        job["ollama_created_at"] = datetime.utcnow().isoformat()
    
    save_jobs(data)
    return job


def set_dataset_info(job_id: str, dataset_path: str, record_count: int) -> dict[str, Any] | None:
    """Set dataset information after successful dataset build."""
    data = load_jobs()
    job = data["jobs"].get(job_id)
    if not job:
        return None
    
    job["dataset_path"] = dataset_path
    job["dataset_record_count"] = record_count
    job["updated_at"] = datetime.utcnow().isoformat()
    save_jobs(data)
    return job


def register_artifact(job_id: str, artifact_type: str, path: str, metadata: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Register a training artifact (checkpoint, GGUF, Modelfile, etc.)."""
    data = load_jobs()
    job = data["jobs"].get(job_id)
    if not job:
        return None
    
    if not job.get("exported_artifacts"):
        job["exported_artifacts"] = {}
    
    job["exported_artifacts"][artifact_type] = {
        "path": path,
        "registered_at": datetime.utcnow().isoformat(),
        "metadata": metadata or {},
    }
    job["updated_at"] = datetime.utcnow().isoformat()
    save_jobs(data)
    return job


def set_ollama_model(job_id: str, model_name: str) -> dict[str, Any] | None:
    """Set the Ollama model name after successful creation."""
    data = load_jobs()
    job = data["jobs"].get(job_id)
    if not job:
        return None
    
    job["ollama_model_name"] = model_name
    job["ollama_created_at"] = datetime.utcnow().isoformat()
    job["updated_at"] = datetime.utcnow().isoformat()
    save_jobs(data)
    return job


def set_validation_passed(job_id: str, validation_passed: bool = True) -> dict[str, Any] | None:
    """Set the validation flag for a trainer job."""
    data = load_jobs()
    job = data["jobs"].get(job_id)
    if not job:
        return None

    job["validation_passed"] = bool(validation_passed)
    job["updated_at"] = datetime.utcnow().isoformat()
    save_jobs(data)
    return job


def delete_job(job_id: str) -> bool:
    """Delete a job from the registry."""
    data = load_jobs()
    if job_id in data["jobs"]:
        del data["jobs"][job_id]
        save_jobs(data)
        return True
    return False


def get_pipeline_status() -> dict[str, Any]:
    """Get overall trainer pipeline status."""
    data = load_jobs()
    jobs = list(data["jobs"].values())
    
    total = len(jobs)
    by_state: dict[str, int] = {}
    for state in JobState:
        by_state[state.value] = sum(1 for j in jobs if j.get("state") == state.value)
    
    recent = sorted(jobs, key=lambda j: j.get("created_at", ""), reverse=True)[:5]
    
    return {
        "status": "configured",
        "total_jobs": total,
        "by_state": by_state,
        "recent_jobs": recent,
        "last_updated": data.get("last_updated"),
    }
