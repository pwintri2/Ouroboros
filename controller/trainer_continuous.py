"""Continuous trainer coordinator for LitGPT and Unsloth.

The coordinator watches approved 11D browser-training records, builds fresh
datasets, and creates bounded LitGPT/Unsloth jobs. Actual training remains
approval-gated and can be disabled so the loop may run as a job/dataset queue.
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from controller.litgpt_adapter import get_litgpt_status, run_litgpt_lora_finetune
from controller.trainer_jobs import JobState, TrainerMethod, create_job, set_dataset_info, update_job_state
from controller.unsloth_adapter import get_unsloth_status, run_unsloth_sft_training

try:
    from controller.training_dataset_builder import build_dataset, count_approved_records
except Exception as exc:
    _DATASET_IMPORT_ERROR = str(exc)

    def count_approved_records() -> int:
        return 0

    def build_dataset(
        output_path: str,
        format: str = "chat",
        max_records: int = 1000,
        include_system_prompt: bool = True,
    ) -> dict[str, Any]:
        return {
            "status": "error",
            "reason": f"Training dataset builder unavailable: {_DATASET_IMPORT_ERROR}",
            "record_count": 0,
            "output_path": output_path,
            "format": format,
            "max_records": max_records,
            "include_system_prompt": include_system_prompt,
        }


SUPPORTED_CONTINUOUS_METHODS = (TrainerMethod.LITGPT.value, TrainerMethod.UNSLOOTH.value)
APPROVAL_PHRASE = "Akkoord"
_STATE_LOCK = threading.Lock()
_WORKER_THREAD: threading.Thread | None = None
_WORKER_STOP = threading.Event()
_WORKER_WAKE = threading.Event()


def _workspace_root() -> Path:
    configured = os.getenv("WINTRIP_WORKSPACE") or os.getenv("WORKSPACE_ROOT") or "/workspace"
    root = Path(configured)
    if not root.exists():
        root = Path(os.getenv("WINTRIP_PROJECT_ROOT") or Path.cwd())
    return root.resolve()


def continuous_state_path() -> Path:
    return (_workspace_root() / ".secrets" / "trainer_continuous.json").resolve()


def _default_state() -> dict[str, Any]:
    return {
        "enabled": False,
        "status": "idle",
        "methods": list(SUPPORTED_CONTINUOUS_METHODS),
        "interval_seconds": 300,
        "execute_training": False,
        "base_models": {
            TrainerMethod.LITGPT.value: "llama3.2:latest",
            TrainerMethod.UNSLOOTH.value: "unsloth/tinyllama-bnb-4bit",
        },
        "lora": {"r": 8, "alpha": 16, "dropout": 0.05},
        "training": {"learning_rate": 2e-4, "batch_size": 1, "epochs": 1},
        "max_records": 1000,
        "last_seen_approved_count": 0,
        "pending_browser_records": 0,
        "pending_learning_records": 0,
        "last_dataset_path": None,
        "last_tick_at": None,
        "last_error": "",
        "last_jobs": [],
        "events": [],
    }


def load_continuous_state() -> dict[str, Any]:
    path = continuous_state_path()
    state = _default_state()
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                state.update(loaded)
        except Exception:
            state["last_error"] = "Continuous trainer state could not be read."
    state["methods"] = _normalize_methods(state.get("methods"))
    return state


def save_continuous_state(state: dict[str, Any]) -> None:
    path = continuous_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.utcnow().isoformat()
    state["methods"] = _normalize_methods(state.get("methods"))
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def get_continuous_status() -> dict[str, Any]:
    state = load_continuous_state()
    if state.get("enabled") and not (_WORKER_THREAD and _WORKER_THREAD.is_alive()):
        _ensure_worker()
    approved_count = count_approved_records()
    state.update(
        {
            "approved_dataset_records": approved_count,
            "new_records_available": max(0, approved_count - int(state.get("last_seen_approved_count") or 0)),
            "worker_alive": bool(_WORKER_THREAD and _WORKER_THREAD.is_alive()),
            "litgpt": get_litgpt_status(),
            "unsloth": get_unsloth_status(),
        }
    )
    return state


def start_continuous_training(
    approval: str,
    methods: list[str] | None = None,
    interval_seconds: int = 300,
    execute_training: bool = False,
    base_models: dict[str, str] | None = None,
    max_records: int = 1000,
    run_immediately: bool = False,
) -> dict[str, Any]:
    if approval != APPROVAL_PHRASE:
        return {"status": "blocked", "reason": "Approval phrase must be 'Akkoord'"}

    with _STATE_LOCK:
        state = load_continuous_state()
        state["enabled"] = True
        state["status"] = "running"
        state["methods"] = _normalize_methods(methods or state.get("methods"))
        state["interval_seconds"] = max(30, min(int(interval_seconds or 300), 86_400))
        state["execute_training"] = bool(execute_training)
        state["max_records"] = max(1, min(int(max_records or 1000), 10_000))
        if base_models:
            current = dict(state.get("base_models") or {})
            current.update({key: value for key, value in base_models.items() if value})
            state["base_models"] = current
        _event(state, "continuous_start", f"Methods: {', '.join(state['methods'])}")
        save_continuous_state(state)

    _ensure_worker()
    result = get_continuous_status()
    if run_immediately:
        result["tick"] = run_continuous_tick(approval=approval, force=True)
    return result


def stop_continuous_training(approval: str) -> dict[str, Any]:
    if approval != APPROVAL_PHRASE:
        return {"status": "blocked", "reason": "Approval phrase must be 'Akkoord'"}

    with _STATE_LOCK:
        state = load_continuous_state()
        state["enabled"] = False
        state["status"] = "stopped"
        _event(state, "continuous_stop", "Continuous trainer stopped.")
        save_continuous_state(state)
    _WORKER_STOP.set()
    return get_continuous_status()


def notify_browser_training_record(item_id: str | None = None, source_url: str | None = None) -> dict[str, Any]:
    """Record that a browser call stored approved data for trainer consumption."""
    return _notify_training_record(
        kind="browser_record_received",
        counter_key="pending_browser_records",
        message=f"Approved browser record queued{f': {item_id}' if item_id else ''}.",
        data={"item_id": item_id, "source_url": source_url},
    )


def notify_learning_record(item_id: str | None = None, source: str | None = None) -> dict[str, Any]:
    """Record that a local learnable cockpit/action packet is ready for trainer consumption."""
    return _notify_training_record(
        kind="learning_record_received",
        counter_key="pending_learning_records",
        message=f"Approved cockpit learning record queued{f': {item_id}' if item_id else ''}.",
        data={"item_id": item_id, "source": source},
    )


def _notify_training_record(kind: str, counter_key: str, message: str, data: dict[str, Any]) -> dict[str, Any]:
    should_wake = False
    with _STATE_LOCK:
        state = load_continuous_state()
        state[counter_key] = int(state.get(counter_key) or 0) + 1
        should_wake = bool(state.get("enabled"))
        _event(state, kind, message, data)
        save_continuous_state(state)
    if should_wake:
        _WORKER_WAKE.set()
        _ensure_worker()
    return get_continuous_status()


def run_continuous_tick(
    approval: str = "",
    force: bool = False,
    execute_training: bool | None = None,
    methods: list[str] | None = None,
    max_records: int | None = None,
) -> dict[str, Any]:
    """Run one bounded continuous-training tick."""
    with _STATE_LOCK:
        state = load_continuous_state()
        approved_count = count_approved_records()
        enabled = bool(state.get("enabled"))
        selected_methods = _normalize_methods(methods or state.get("methods"))
        should_execute = bool(state.get("execute_training")) if execute_training is None else bool(execute_training)
        dataset_max_records = max(
            1,
            min(int(max_records if max_records is not None else (state.get("max_records") or 1000)), 10_000),
        )

        if should_execute and approval != APPROVAL_PHRASE:
            state["status"] = "blocked"
            state["last_error"] = "Actual LitGPT/Unsloth training requires Akkoord."
            _event(state, "tick_blocked", state["last_error"])
            save_continuous_state(state)
            return {"status": "blocked", "reason": state["last_error"], "state": state}

        last_seen = int(state.get("last_seen_approved_count") or 0)
        if approved_count < last_seen:
            _event(
                state,
                "approved_count_rebased",
                f"Approved trainable record count changed from {last_seen} to {approved_count}; rebuilding from current safe set.",
                {"previous_last_seen": last_seen, "approved_count": approved_count},
            )
            state["last_seen_approved_count"] = 0
            last_seen = 0

        new_count = approved_count - last_seen
        if not force and (not enabled or new_count <= 0):
            state["status"] = "idle" if enabled else "stopped"
            state["last_tick_at"] = datetime.utcnow().isoformat()
            save_continuous_state(state)
            return {
                "status": "idle",
                "reason": "No new approved browser training records.",
                "approved_dataset_records": approved_count,
                "new_records_available": max(0, new_count),
                "state": state,
            }

        dataset_path = _dataset_output_path()
        dataset = build_dataset(
            output_path=str(dataset_path),
            format="text",
            max_records=dataset_max_records,
            include_system_prompt=True,
        )
        if dataset.get("status") != "success":
            state["status"] = "error"
            state["last_error"] = str(dataset.get("reason") or "Dataset build failed")
            state["last_tick_at"] = datetime.utcnow().isoformat()
            _event(state, "dataset_error", state["last_error"], dataset)
            save_continuous_state(state)
            return {"status": "error", "dataset": dataset, "state": state}

        jobs = []
        for method in selected_methods:
            job_result = _create_or_run_job(state, method, str(dataset_path), int(dataset.get("included_count") or 0), should_execute)
            jobs.append(job_result)

        state["status"] = "training" if should_execute else "dataset_ready"
        state["last_seen_approved_count"] = approved_count
        state["pending_browser_records"] = 0
        state["pending_learning_records"] = 0
        state["last_dataset_path"] = str(dataset_path)
        state["last_tick_at"] = datetime.utcnow().isoformat()
        state["last_error"] = ""
        state["last_jobs"] = jobs
        _event(state, "tick_completed", f"Prepared {len(jobs)} trainer job(s).", {"dataset": dataset, "jobs": jobs})
        save_continuous_state(state)
        return {
            "status": "success",
            "dataset": dataset,
            "jobs": jobs,
            "execute_training": should_execute,
            "state": state,
        }


def _ensure_worker() -> None:
    global _WORKER_THREAD
    if _WORKER_THREAD and _WORKER_THREAD.is_alive():
        return
    _WORKER_STOP.clear()
    _WORKER_THREAD = threading.Thread(target=_worker_loop, name="wintrip-continuous-trainer", daemon=True)
    _WORKER_THREAD.start()


def _worker_loop() -> None:
    while not _WORKER_STOP.is_set():
        state = load_continuous_state()
        if not state.get("enabled"):
            _WORKER_WAKE.clear()
            _WORKER_STOP.wait(5)
            continue
        run_continuous_tick(approval=APPROVAL_PHRASE if state.get("execute_training") else "", force=False)
        wait_seconds = max(30, min(int(state.get("interval_seconds") or 300), 86_400))
        _wait_for_next_tick(wait_seconds)


def _wait_for_next_tick(wait_seconds: int) -> None:
    deadline = time.monotonic() + max(1, int(wait_seconds))
    while not _WORKER_STOP.is_set():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        if _WORKER_WAKE.wait(min(remaining, 1.0)):
            _WORKER_WAKE.clear()
            return


def _create_or_run_job(
    state: dict[str, Any],
    method: str,
    dataset_path: str,
    record_count: int,
    execute_training: bool,
) -> dict[str, Any]:
    base_model = str((state.get("base_models") or {}).get(method) or "llama3.2:latest")
    lora = state.get("lora") or {}
    training = state.get("training") or {}
    trainer_method = TrainerMethod(method)
    job = create_job(
        base_model=base_model,
        method=trainer_method,
        lora_r=int(lora.get("r", 8)),
        lora_alpha=int(lora.get("alpha", 16)),
        lora_dropout=float(lora.get("dropout", 0.05)),
        learning_rate=float(training.get("learning_rate", 2e-4)),
        batch_size=int(training.get("batch_size", 1)),
        epochs=int(training.get("epochs", 1)),
        description="Continuous trainer job from approved browser calls",
    )
    set_dataset_info(job["job_id"], dataset_path, record_count)
    update_job_state(job["job_id"], JobState.DATASET_READY, f"Continuous dataset ready: {dataset_path}")

    result: dict[str, Any] | None = None
    if execute_training:
        if method == TrainerMethod.LITGPT.value:
            runtime = get_litgpt_status()
            if not runtime.get("runtime_ready"):
                reason = str(runtime.get("reason") or "LitGPT runtime is not executable.")
                update_job_state(job["job_id"], JobState.DATASET_READY, f"LitGPT training blocked: {reason}")
                return {
                    "job_id": job["job_id"],
                    "method": method,
                    "base_model": base_model,
                    "dataset_path": dataset_path,
                    "record_count": record_count,
                    "state": JobState.DATASET_READY.value,
                    "training_result": {
                        "status": "blocked",
                        "reason": reason,
                        "runtime_status": runtime,
                        "fake_success": False,
                    },
                }
            result = run_litgpt_lora_finetune(
                job_id=job["job_id"],
                base_model=base_model,
                dataset_path=dataset_path,
                lora_r=int(lora.get("r", 8)),
                lora_alpha=int(lora.get("alpha", 16)),
                lora_dropout=float(lora.get("dropout", 0.05)),
                learning_rate=float(training.get("learning_rate", 2e-4)),
                batch_size=int(training.get("batch_size", 1)),
                epochs=int(training.get("epochs", 1)),
            )
        elif method == TrainerMethod.UNSLOOTH.value:
            runtime = get_unsloth_status()
            if not runtime.get("runtime_ready"):
                reason = str(runtime.get("reason") or "Unsloth runtime is not executable.")
                update_job_state(job["job_id"], JobState.DATASET_READY, f"Unsloth training blocked: {reason}")
                return {
                    "job_id": job["job_id"],
                    "method": method,
                    "base_model": base_model,
                    "dataset_path": dataset_path,
                    "record_count": record_count,
                    "state": JobState.DATASET_READY.value,
                    "training_result": {
                        "status": "blocked",
                        "reason": reason,
                        "runtime_status": runtime,
                        "fake_success": False,
                    },
                }
            result = run_unsloth_sft_training(
                job_id=job["job_id"],
                base_model=base_model,
                dataset_path=dataset_path,
                lora_r=int(lora.get("r", 8)),
                lora_alpha=int(lora.get("alpha", 16)),
                lora_dropout=float(lora.get("dropout", 0.05)),
                learning_rate=float(training.get("learning_rate", 2e-4)),
                batch_size=int(training.get("batch_size", 1)),
                epochs=int(training.get("epochs", 1)),
            )

    return {
        "job_id": job["job_id"],
        "method": method,
        "base_model": base_model,
        "dataset_path": dataset_path,
        "record_count": record_count,
        "state": "training_started" if execute_training else JobState.DATASET_READY.value,
        "training_result": result,
    }


def _dataset_output_path() -> Path:
    stamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    path = _workspace_root() / "out" / "continuous_datasets" / f"browser_training_{stamp}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _normalize_methods(methods: Any) -> list[str]:
    if isinstance(methods, str):
        values = [methods]
    else:
        values = list(methods or SUPPORTED_CONTINUOUS_METHODS)
    normalized = []
    for value in values:
        text = str(value or "").strip()
        if text in SUPPORTED_CONTINUOUS_METHODS and text not in normalized:
            normalized.append(text)
    return normalized or list(SUPPORTED_CONTINUOUS_METHODS)


def _event(state: dict[str, Any], kind: str, message: str, data: dict[str, Any] | None = None) -> None:
    events = list(state.get("events") or [])
    events.append(
        {
            "kind": kind,
            "message": message,
            "data": data or {},
            "at": datetime.utcnow().isoformat(),
        }
    )
    state["events"] = events[-30:]
