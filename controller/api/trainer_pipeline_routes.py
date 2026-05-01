# controller/api/trainer_pipeline_routes.py
# API endpoints for the Roo/Trainer pipeline integration.

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from controller.blue_brain_adapter import get_blue_brain_status, run_blue_brain_training, setup_blue_brain_env
from controller.litgpt_adapter import get_litgpt_status, run_litgpt_lora_finetune, merge_lora_weights
from controller.model_artifacts import (
    get_artifacts_summary,
    list_artifacts,
    register_ollama_model,
    register_artifact,
    update_model_online_status,
)
from controller.project_context import get_context_summary, get_file_tree, get_changed_files
from controller.roo_manifest import get_roo_status, get_tool_schema, list_all_modes, list_all_tools
from controller.roo_tools import (
    apply_patch,
    apply_patch_preview,
    ask_followup_question,
    attempt_completion,
    execute_command,
    list_files,
    read_file,
    search_files,
    write_file,
    write_file_preview,
)
from controller.trainer_jobs import (
    JobState,
    TrainerMethod,
    create_job,
    delete_job,
    get_job,
    get_pipeline_status,
    list_jobs,
    set_dataset_info,
    set_ollama_model,
    update_job_state,
)
from controller.training_dataset_builder import build_dataset, count_approved_records, preview_dataset
from controller.trainer_continuous import (
    get_continuous_status,
    notify_browser_training_record,
    run_continuous_tick,
    start_continuous_training,
    stop_continuous_training,
)
from controller.unsloth_adapter import export_to_gguf, generate_modelfile, get_unsloth_status, run_unsloth_sft_training
from controller.api.training_routes import (
    BrowserTrainingRequest,
    _preview_payload,
    _remember_event,
    _safe_total_count,
    _store_training_snapshot,
)


trainer_pipeline_router = APIRouter(prefix="/trainer", tags=["trainer-pipeline"])
roo_tools_router = APIRouter(prefix="/roo", tags=["roo-tools"])
project_context_router = APIRouter(prefix="/context", tags=["project-context"])


# ============================================================================
# Trainer Pipeline Routes
# ============================================================================


class CreateJobRequest(BaseModel):
    base_model: str = Field(..., min_length=1, max_length=256)
    method: TrainerMethod = Field(default=TrainerMethod.LITGPT)
    lora_r: int = Field(default=8, ge=1, le=64)
    lora_alpha: int = Field(default=16, ge=1, le=128)
    lora_dropout: float = Field(default=0.05, ge=0.0, le=0.5)
    learning_rate: float = Field(default=2e-4, ge=1e-6, le=1e-2)
    batch_size: int = Field(default=4, ge=1, le=32)
    epochs: int = Field(default=3, ge=1, le=50)
    description: str = Field(default="", max_length=1024)
    blue_samples: int = Field(default=10_000, ge=100, le=200_000)
    blue_estimators: int = Field(default=300, ge=10, le=2_000)
    blue_max_depth: int | None = Field(default=12, ge=1, le=100)
    blue_random_state: int = Field(default=42, ge=0, le=1_000_000)


class UpdateJobStateRequest(BaseModel):
    job_id: str = Field(..., min_length=1)
    new_state: JobState = Field(...)
    log_entry: str = Field(default="", max_length=2048)
    error: str | None = Field(default=None, max_length=2048)


class SetDatasetInfoRequest(BaseModel):
    job_id: str = Field(..., min_length=1)
    dataset_path: str = Field(..., min_length=1)
    record_count: int = Field(default=0, ge=0)


class StartTrainingRequest(BaseModel):
    job_id: str = Field(..., min_length=1)
    approval: str = Field(..., min_length=1)
    quantize: str | None = Field(default=None, max_length=32)


class BuildDatasetRequest(BaseModel):
    output_path: str = Field(..., min_length=1)
    format: str = Field(default="chat", pattern="^(chat|completion|text)$")
    max_records: int = Field(default=1000, ge=1, le=10000)
    include_system_prompt: bool = Field(default=True)


class ApprovalRequest(BaseModel):
    approval: str = Field(..., min_length=1)


class ContinuousStartRequest(BaseModel):
    approval: str = Field(..., min_length=1)
    methods: list[TrainerMethod] = Field(default_factory=lambda: [TrainerMethod.LITGPT, TrainerMethod.UNSLOOTH])
    interval_seconds: int = Field(default=300, ge=30, le=86400)
    execute_training: bool = Field(default=False)
    litgpt_base_model: str = Field(default="llama3.2:latest", min_length=1, max_length=256)
    unsloth_base_model: str = Field(default="unsloth/tinyllama-bnb-4bit", min_length=1, max_length=256)
    max_records: int = Field(default=1000, ge=1, le=10000)
    run_immediately: bool = Field(default=False)


class ContinuousTickRequest(BaseModel):
    approval: str = Field(default="", max_length=64)
    force: bool = Field(default=False)
    execute_training: bool = Field(default=False)
    methods: list[TrainerMethod] | None = Field(default=None)


class TrainerBrowserIngestRequest(BrowserTrainingRequest):
    notify_continuous: bool = Field(default=True)
    trigger_tick: bool = Field(default=False)
    execute_training: bool = Field(default=False)
    methods: list[TrainerMethod] | None = Field(default=None)


@trainer_pipeline_router.get("/status")
async def trainer_pipeline_status() -> dict[str, Any]:
    """Get overall trainer pipeline status."""
    pipeline_status = get_pipeline_status()
    litgpt_status = get_litgpt_status()
    unsloth_status = get_unsloth_status()
    blue_brain_status = get_blue_brain_status()
    artifacts_summary = get_artifacts_summary()
    approved_count = count_approved_records()
    
    return {
        "pipeline": pipeline_status,
        "litgpt": litgpt_status,
        "unsloth": unsloth_status,
        "blue_brain": blue_brain_status,
        "continuous": get_continuous_status(),
        "artifacts": artifacts_summary,
        "approved_dataset_records": approved_count,
    }


@trainer_pipeline_router.post("/jobs")
async def create_trainer_job(request: CreateJobRequest) -> dict[str, Any]:
    """Create a new trainer job."""
    job = create_job(
        base_model=request.base_model,
        method=request.method,
        lora_r=request.lora_r,
        lora_alpha=request.lora_alpha,
        lora_dropout=request.lora_dropout,
        learning_rate=request.learning_rate,
        batch_size=request.batch_size,
        epochs=request.epochs,
        description=request.description,
        extra_training_params={
            "blue_samples": request.blue_samples,
            "blue_estimators": request.blue_estimators,
            "blue_max_depth": request.blue_max_depth,
            "blue_random_state": request.blue_random_state,
            "blue_cycles": request.epochs,
        } if request.method == TrainerMethod.BLUE_BRAIN else None,
    )
    return job


@trainer_pipeline_router.post("/blue-brain/setup")
async def setup_blue_brain(request: ApprovalRequest) -> dict[str, Any]:
    """Set up the dedicated Blue Brain trainer venv (requires approval)."""
    if request.approval != "Akkoord":
        raise HTTPException(status_code=403, detail="Approval phrase must be 'Akkoord'")
    return setup_blue_brain_env()


@trainer_pipeline_router.get("/continuous/status")
async def trainer_continuous_status() -> dict[str, Any]:
    """Get LitGPT/Unsloth continuous trainer status."""
    return get_continuous_status()


@trainer_pipeline_router.post("/continuous/start")
async def trainer_continuous_start(request: ContinuousStartRequest) -> dict[str, Any]:
    """Start the continuous LitGPT/Unsloth trainer loop (requires approval)."""
    methods = [method.value for method in request.methods if method.value in {TrainerMethod.LITGPT.value, TrainerMethod.UNSLOOTH.value}]
    result = start_continuous_training(
        approval=request.approval,
        methods=methods,
        interval_seconds=request.interval_seconds,
        execute_training=request.execute_training,
        base_models={
            TrainerMethod.LITGPT.value: request.litgpt_base_model,
            TrainerMethod.UNSLOOTH.value: request.unsloth_base_model,
        },
        max_records=request.max_records,
        run_immediately=request.run_immediately,
    )
    if result.get("status") == "blocked":
        raise HTTPException(status_code=403, detail=result.get("reason"))
    return result


@trainer_pipeline_router.post("/continuous/stop")
async def trainer_continuous_stop(request: ApprovalRequest) -> dict[str, Any]:
    """Stop the continuous LitGPT/Unsloth trainer loop (requires approval)."""
    result = stop_continuous_training(approval=request.approval)
    if result.get("status") == "blocked":
        raise HTTPException(status_code=403, detail=result.get("reason"))
    return result


@trainer_pipeline_router.post("/continuous/tick")
async def trainer_continuous_tick(request: ContinuousTickRequest) -> dict[str, Any]:
    """Run one bounded continuous-trainer tick."""
    methods = [method.value for method in request.methods] if request.methods else None
    result = run_continuous_tick(
        approval=request.approval,
        force=request.force,
        execute_training=request.execute_training,
        methods=methods,
    )
    if result.get("status") == "blocked":
        raise HTTPException(status_code=403, detail=result.get("reason"))
    return result


@trainer_pipeline_router.post("/browser/ingest")
async def trainer_browser_ingest(request_body: TrainerBrowserIngestRequest, request: Request) -> dict[str, Any]:
    """Receive browser training data, store approved snapshots, and notify the continuous trainer."""
    try:
        approved = request_body.approval == "Akkoord"
        payload = _preview_payload(request_body, approval=request_body.approval if approved else None, request=request)
        if payload["approval_status"] != "approved":
            _remember_event(request, "trainer_browser_ingest_preview", payload)
            return {
                "status": "preview",
                "stored": False,
                "approval_required": True,
                "ingest": payload,
                "continuous": get_continuous_status(),
            }

        stored = _store_training_snapshot(payload)
        payload.update(
            {
                "stored": stored["stored"],
                "approval_required": False,
                "item_id": stored["item_id"],
                "reason": stored["reason"],
                "storage_target": stored["storage_target"],
                "collection_count": _safe_total_count(request.app.state.training_storage),
            }
        )
        _remember_event(request, "trainer_browser_ingest_stored", payload)
        continuous = None
        if request_body.notify_continuous:
            continuous = notify_browser_training_record(item_id=stored.get("item_id"), source_url=payload.get("source_url"))
        tick = None
        if request_body.trigger_tick:
            methods = [method.value for method in request_body.methods] if request_body.methods else None
            tick = run_continuous_tick(
                approval=request_body.approval or "",
                force=True,
                execute_training=request_body.execute_training,
                methods=methods,
            )
        return {
            "status": "stored",
            "stored": bool(stored["stored"]),
            "ingest": payload,
            "continuous": continuous or get_continuous_status(),
            "tick": tick,
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@trainer_pipeline_router.get("/jobs")
async def list_trainer_jobs(state: JobState | None = None) -> dict[str, Any]:
    """List all trainer jobs, optionally filtered by state."""
    jobs = list_jobs(state=state)
    return {"jobs": jobs, "count": len(jobs)}


@trainer_pipeline_router.get("/jobs/{job_id}")
async def get_trainer_job(job_id: str) -> dict[str, Any]:
    """Get a specific trainer job by ID."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@trainer_pipeline_router.post("/jobs/state")
async def update_trainer_job_state(request: UpdateJobStateRequest) -> dict[str, Any]:
    """Update a trainer job's state."""
    job = update_job_state(
        job_id=request.job_id,
        new_state=request.new_state,
        log_entry=request.log_entry,
        error=request.error,
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@trainer_pipeline_router.post("/jobs/dataset")
async def set_job_dataset_info(request: SetDatasetInfoRequest) -> dict[str, Any]:
    """Set dataset information for a job."""
    job = set_dataset_info(
        job_id=request.job_id,
        dataset_path=request.dataset_path,
        record_count=request.record_count,
    )
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@trainer_pipeline_router.delete("/jobs/{job_id}")
async def delete_trainer_job(job_id: str) -> dict[str, Any]:
    """Delete a trainer job."""
    success = delete_job(job_id)
    if not success:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"status": "deleted", "job_id": job_id}


@trainer_pipeline_router.post("/training/start")
async def start_training(request: StartTrainingRequest) -> dict[str, Any]:
    """Start training for a job (requires approval)."""
    if request.approval != "Akkoord":
        raise HTTPException(status_code=403, detail="Approval phrase must be 'Akkoord'")
    
    job = get_job(request.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    method = job.get("method")
    if method == TrainerMethod.LITGPT.value:
        result = run_litgpt_lora_finetune(
            job_id=request.job_id,
            base_model=job["base_model"],
            dataset_path=job.get("dataset_path", ""),
            lora_r=job["lora_params"]["r"],
            lora_alpha=job["lora_params"]["alpha"],
            lora_dropout=job["lora_params"]["dropout"],
            learning_rate=job["training_params"]["learning_rate"],
            batch_size=job["training_params"]["batch_size"],
            epochs=job["training_params"]["epochs"],
            quantize=request.quantize,
        )
    elif method == TrainerMethod.UNSLOOTH.value:
        result = run_unsloth_sft_training(
            job_id=request.job_id,
            base_model=job["base_model"],
            dataset_path=job.get("dataset_path", ""),
            lora_r=job["lora_params"]["r"],
            lora_alpha=job["lora_params"]["alpha"],
            lora_dropout=job["lora_params"]["dropout"],
            learning_rate=job["training_params"]["learning_rate"],
            batch_size=job["training_params"]["batch_size"],
            epochs=job["training_params"]["epochs"],
        )
    elif method == TrainerMethod.BLUE_BRAIN.value:
        training_params = job.get("training_params", {})
        result = run_blue_brain_training(
            job_id=request.job_id,
            n_samples=int(training_params.get("blue_samples", 10_000)),
            n_features=11,
            n_estimators=int(training_params.get("blue_estimators", 300)),
            max_depth=training_params.get("blue_max_depth", 12),
            random_state=int(training_params.get("blue_random_state", 42)),
            cycles=int(training_params.get("blue_cycles", training_params.get("epochs", 1))),
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported training method: {method}")
    
    return result


@trainer_pipeline_router.post("/training/merge")
async def merge_lora(job_id: str, checkpoint_path: str, approval: str) -> dict[str, Any]:
    """Merge LoRA weights (requires approval)."""
    if approval != "Akkoord":
        raise HTTPException(status_code=403, detail="Approval phrase must be 'Akkoord'")
    
    result = merge_lora_weights(job_id=job_id, checkpoint_path=checkpoint_path)
    return result


@trainer_pipeline_router.post("/dataset/preview")
async def preview_training_dataset(max_records: int = 10) -> dict[str, Any]:
    """Preview approved training records."""
    return preview_dataset(max_records=max_records)


@trainer_pipeline_router.post("/dataset/build")
async def build_training_dataset(request: BuildDatasetRequest) -> dict[str, Any]:
    """Build a training dataset from approved records."""
    result = build_dataset(
        output_path=request.output_path,
        format=request.format,
        max_records=request.max_records,
        include_system_prompt=request.include_system_prompt,
    )
    return result


@trainer_pipeline_router.get("/artifacts")
async def list_model_artifacts(job_id: str | None = None) -> dict[str, Any]:
    """List model artifacts, optionally filtered by job ID."""
    artifacts = list_artifacts(job_id=job_id)
    return {"artifacts": artifacts, "count": len(artifacts)}


@trainer_pipeline_router.get("/artifacts/summary")
async def get_artifacts_status() -> dict[str, Any]:
    """Get artifacts summary."""
    return get_artifacts_summary()


@trainer_pipeline_router.post("/ollama/register")
async def register_ollama_model_endpoint(
    job_id: str,
    gguf_path: str,
    modelfile_path: str,
    model_name: str,
) -> dict[str, Any]:
    """Register an Ollama model after creation."""
    result = register_ollama_model(
        job_id=job_id,
        gguf_path=gguf_path,
        modelfile_path=modelfile_path,
        model_name=model_name,
    )
    return result


@trainer_pipeline_router.post("/ollama/check")
async def check_ollama_model_status(model_name: str) -> dict[str, Any]:
    """Check and update Ollama model online status."""
    result = update_model_online_status(model_name)
    if not result:
        raise HTTPException(status_code=404, detail="Model not found")
    return result


# ============================================================================
# Roo Tools Routes
# ============================================================================


@roo_tools_router.get("/status")
async def roo_adapter_status() -> dict[str, Any]:
    """Get Roo adapter status and capability inventory."""
    return get_roo_status()


@roo_tools_router.get("/tools")
async def list_roo_tools() -> dict[str, Any]:
    """List all available Roo tools."""
    return {"tools": list_all_tools()}


@roo_tools_router.get("/tools/{tool_name}")
async def get_roo_tool_schema(tool_name: str) -> dict[str, Any]:
    """Get schema for a specific Roo tool."""
    schema = get_tool_schema(tool_name)
    if not schema:
        raise HTTPException(status_code=404, detail="Tool not found")
    return schema


@roo_tools_router.get("/modes")
async def list_roo_modes() -> dict[str, Any]:
    """List all available Roo modes."""
    return {"modes": list_all_modes()}


@roo_tools_router.post("/read_file")
async def roo_read_file_endpoint(path: str, offset: int | None = None, limit: int | None = None) -> dict[str, Any]:
    """Read a file via Roo tool."""
    return read_file(path=path, offset=offset, limit=limit)


@roo_tools_router.post("/list_files")
async def roo_list_files_endpoint(path: str = ".", recursive: bool = False, limit: int = 200) -> dict[str, Any]:
    """List files via Roo tool."""
    return list_files(path=path, recursive=recursive, limit=limit)


@roo_tools_router.post("/search_files")
async def roo_search_files_endpoint(
    path: str,
    regex: str,
    file_pattern: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Search files via Roo tool."""
    return search_files(path=path, regex=regex, file_pattern=file_pattern, limit=limit)


@roo_tools_router.post("/write_file_preview")
async def roo_write_file_preview_endpoint(path: str, content: str) -> dict[str, Any]:
    """Preview file write via Roo tool."""
    return write_file_preview(path=path, content=content)


@roo_tools_router.post("/write_file")
async def roo_write_file_endpoint(path: str, content: str, approval: str) -> dict[str, Any]:
    """Write file via Roo tool (requires approval)."""
    return write_file(path=path, content=content, approval=approval)


@roo_tools_router.post("/apply_patch_preview")
async def roo_apply_patch_preview_endpoint(patch: str) -> dict[str, Any]:
    """Preview patch application via Roo tool."""
    return apply_patch_preview(patch=patch)


@roo_tools_router.post("/apply_patch")
async def roo_apply_patch_endpoint(patch: str, approval: str) -> dict[str, Any]:
    """Apply patch via Roo tool (requires approval)."""
    return apply_patch(patch=patch, approval=approval)


@roo_tools_router.post("/execute_command")
async def roo_execute_command_endpoint(command: str, approval: str, timeout: int = 20) -> dict[str, Any]:
    """Execute command via Roo tool (requires approval)."""
    return execute_command(command=command, approval=approval, timeout=timeout)


@roo_tools_router.post("/attempt_completion")
async def roo_attempt_completion_endpoint(result: str, command: str | None = None) -> dict[str, Any]:
    """Mark task as completed via Roo tool."""
    return attempt_completion(result=result, command=command)


@roo_tools_router.post("/ask_followup_question")
async def roo_ask_followup_question_endpoint(question: str) -> dict[str, Any]:
    """Ask followup question via Roo tool."""
    return ask_followup_question(question=question)


# ============================================================================
# Project Context Routes
# ============================================================================


@project_context_router.get("/summary")
async def project_context_summary() -> dict[str, Any]:
    """Get project context summary."""
    return get_context_summary()


@project_context_router.get("/file_tree")
async def project_file_tree(max_depth: int = 3, limit: int = 500) -> dict[str, Any]:
    """Get project file tree."""
    return get_file_tree(max_depth=max_depth, limit=limit)


@project_context_router.get("/changed_files")
async def project_changed_files(limit: int = 50) -> dict[str, Any]:
    """Get changed files from git."""
    return get_changed_files(limit=limit)


def init_trainer_pipeline(app: Any) -> None:
    """Initialize trainer pipeline routes."""
    app.include_router(trainer_pipeline_router)
    app.include_router(roo_tools_router)
    app.include_router(project_context_router)
