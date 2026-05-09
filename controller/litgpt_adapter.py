"""LitGPT adapter for Ouroboros trainer pipeline.

Integrates LitGPT's fine-tuning capabilities (LoRA, full, adapter) with the
trainer job system. All commands run via safe_shell or Docker exec in /workspace.
Captures stdout/stderr/exit_code in trainer job records.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from controller.safe_shell import run_safe_shell, workspace_root
from controller.trainer_jobs import JobState, TrainerMethod, get_job, update_job_state


_LITGPT_DOCKER_PATH = Path("/workspace/litgpt")
_LITGPT_LOCAL_PATH = Path("/home/pwintri2/WintripAI/litgpt")

_VENV_DOCKER_PATH = Path("/workspace/.venv_litgpt")
_VENV_LOCAL_PATH = Path("/home/pwintri2/WintripAI/.venv_litgpt")


def _project_root() -> Path:
    configured = os.getenv("WINTRIP_WORKSPACE") or os.getenv("WINTRIP_PROJECT_ROOT")
    if configured:
        path = Path(configured).expanduser()
        if path.exists():
            return path.resolve()
    for candidate in (Path("/workspace"), Path("/home/pwintri2/WintripAI"), Path.cwd()):
        if candidate.exists():
            return candidate.resolve()
    return Path.cwd().resolve()


def _resolve_litgpt_source() -> Path:
    """Return the first existing LitGPT source directory."""
    candidates = [
        os.getenv("WINTRIP_LITGPT_PATH"),
        str(_project_root() / "litgpt"),
        str(_LITGPT_DOCKER_PATH),
        str(_LITGPT_LOCAL_PATH),
    ]
    for raw in candidates:
        if not raw:
            continue
        path = Path(raw).expanduser()
        if (path / "litgpt").is_dir() and (path / "pyproject.toml").exists():
            return path.resolve()
    return _LITGPT_DOCKER_PATH


def _resolve_litgpt_venv() -> Path:
    """Return the venv path that matches the resolved source location."""
    configured = os.getenv("WINTRIP_LITGPT_VENV")
    if configured:
        return Path(configured).expanduser().resolve()
    source = _resolve_litgpt_source()
    root = source.parent if source.exists() else _project_root()
    candidate = root / ".venv_litgpt"
    if candidate.exists() or root != Path("/workspace"):
        return candidate.resolve()
    if _VENV_LOCAL_PATH.exists():
        return _VENV_LOCAL_PATH
    return _VENV_DOCKER_PATH


LITGPT_SOURCE_PATH = _resolve_litgpt_source()
LITGPT_VENV_PATH = _resolve_litgpt_venv()


def litgpt_available() -> bool:
    """Check if LitGPT source is available."""
    return LITGPT_SOURCE_PATH.exists() and LITGPT_SOURCE_PATH.is_dir()


def _venv_python() -> Path:
    return LITGPT_VENV_PATH / "bin" / "python"


def _venv_script() -> Path:
    return LITGPT_VENV_PATH / "bin" / "litgpt"


def _is_runnable(path: Path) -> bool:
    return path.exists() and os.access(path, os.X_OK)


def _script_interpreter_exists(path: Path) -> bool:
    if not _is_runnable(path):
        return False
    try:
        first_line = path.read_text(encoding="utf-8", errors="replace").splitlines()[0]
    except Exception:
        return True
    if not first_line.startswith("#!"):
        return True
    interpreter = first_line[2:].strip().split(" ", 1)[0]
    return bool(interpreter) and Path(interpreter).exists()


def _current_python_can_import_litgpt() -> bool:
    source_parent = str(LITGPT_SOURCE_PATH)
    code = "import litgpt, lightning, torch; print('ok')"
    env = dict(os.environ)
    env["PYTHONPATH"] = source_parent + os.pathsep + env.get("PYTHONPATH", "")
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code],
            env=env,
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except Exception:
        return False
    return proc.returncode == 0


def _system_litgpt() -> str:
    return shutil.which("litgpt") or ""


def litgpt_runtime_ready() -> bool:
    return bool(get_litgpt_args(allow_unavailable=False))


def setup_litgpt_env() -> dict[str, Any]:
    """Set up LitGPT virtual environment if needed."""
    if not litgpt_available():
        return {
            "status": "error",
            "reason": f"LitGPT source not found at {LITGPT_SOURCE_PATH}",
        }
    
    workspace = workspace_root()
    
    # Check if venv exists
    if LITGPT_VENV_PATH.exists() and _is_runnable(_venv_python()):
        return {
            "status": "success",
            "venv_path": str(LITGPT_VENV_PATH),
            "message": "LitGPT venv already exists",
        }
    if LITGPT_VENV_PATH.exists():
        return {
            "status": "error",
            "venv_path": str(LITGPT_VENV_PATH),
            "reason": "LitGPT venv exists but its Python executable is not runnable; rebuild the venv before training.",
        }
    
    # Create venv and install LitGPT
    try:
        subprocess.run(
            ["python3", "-m", "venv", str(LITGPT_VENV_PATH)],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
        
        pip_path = LITGPT_VENV_PATH / "bin" / "pip"
        subprocess.run(
            [str(pip_path), "install", "-e", str(LITGPT_SOURCE_PATH)],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=300,
            check=True,
        )
        
        return {
            "status": "success",
            "venv_path": str(LITGPT_VENV_PATH),
            "message": "LitGPT venv created and installed",
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "reason": "LitGPT setup timeout",
        }
    except subprocess.CalledProcessError as exc:
        return {
            "status": "error",
            "reason": f"LitGPT setup failed: {exc.stderr}",
        }
    except Exception as exc:
        return {
            "status": "error",
            "reason": f"LitGPT setup error: {exc}",
        }


def get_litgpt_command() -> str:
    """Get the LitGPT command path."""
    args = get_litgpt_args(allow_unavailable=False)
    return " ".join(args) if args else "unavailable"


def get_litgpt_args(allow_unavailable: bool = True) -> list[str]:
    """Get LitGPT invocation args for the explicit trainer job runner."""
    main_path = LITGPT_SOURCE_PATH / "litgpt" / "__main__.py"

    if _is_runnable(_venv_python()) and main_path.exists():
        return [str(_venv_python()), "-m", "litgpt"]
    if _script_interpreter_exists(_venv_script()):
        return [str(_venv_script())]
    system = _system_litgpt()
    if system:
        return [system]
    if _current_python_can_import_litgpt() and main_path.exists():
        return [sys.executable, "-m", "litgpt"]
    return ["litgpt"] if allow_unavailable else []


def run_litgpt_lora_finetune(
    job_id: str,
    base_model: str,
    dataset_path: str,
    lora_r: int = 8,
    lora_alpha: int = 16,
    lora_dropout: float = 0.05,
    learning_rate: float = 2e-4,
    batch_size: int = 4,
    epochs: int = 3,
    out_dir: str | None = None,
    quantize: str | None = None,
) -> dict[str, Any]:
    """Run LitGPT LoRA fine-tuning via safe_shell.
    
    Args:
        job_id: Trainer job ID to update
        base_model: Base model name/path
        dataset_path: Path to training dataset (JSON)
        lora_r: LoRA rank
        lora_alpha: LoRA alpha
        lora_dropout: LoRA dropout rate
        learning_rate: Learning rate
        batch_size: Batch size
        epochs: Number of epochs
        out_dir: Output directory (defaults to out/lora)
        quantize: Quantization method (e.g., "bnb.nf4")
    
    Returns:
        Result dict with status and artifact paths
    """
    job = get_job(job_id)
    if not job:
        return {"status": "error", "reason": "Job not found"}
    
    # Set output directory
    workspace = workspace_root()
    if not out_dir:
        out_dir = str(workspace / "out" / "lora" / job_id)
    
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    
    # Build command for the explicit Docker-contained job runner.
    cmd_parts = [
        *get_litgpt_args(),
        "finetune_lora",
        base_model,
        "--data", "JSON",
        "--data.json_path", dataset_path,
        "--out_dir", out_dir,
        "--lora_r", str(lora_r),
        "--lora_alpha", str(lora_alpha),
        "--lora_dropout", str(lora_dropout),
        "--train.max_tokens", "100000",  # Default max tokens
        "--optimizer.lr", str(learning_rate),
        "--train.batch_size", str(batch_size),
        "--train.epochs", str(epochs),
    ]
    
    if quantize:
        cmd_parts.extend(["--quantize", quantize])
    
    # Update job state to training
    update_job_state(job_id, JobState.TRAINING, f"Starting LitGPT LoRA fine-tuning: {base_model}")

    try:
        proc = subprocess.run(
            cmd_parts,
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=3600,
        )
        result = {
            "status": "success" if proc.returncode == 0 else "error",
            "stdout": proc.stdout[-12000:],
            "stderr": proc.stderr[-12000:],
            "exit_code": proc.returncode,
        }
    except subprocess.TimeoutExpired as exc:
        result = {
            "status": "timeout",
            "stdout": (exc.stdout or "")[-12000:] if isinstance(exc.stdout, str) else "",
            "stderr": (exc.stderr or "")[-12000:] if isinstance(exc.stderr, str) else "",
            "exit_code": None,
            "reason": "LitGPT training timeout",
        }
    except Exception as exc:
        result = {"status": "error", "stdout": "", "stderr": str(exc), "exit_code": None, "reason": str(exc)}
    
    if result["status"] == "success":
        # Find the final checkpoint
        checkpoint_dir = out_path / "final"
        if checkpoint_dir.exists():
            lora_file = checkpoint_dir / "lit_model.pth.lora"
            if lora_file.exists():
                update_job_state(
                    job_id,
                    JobState.VALIDATING,
                    f"Training completed. LoRA checkpoint: {lora_file}",
                )
                return {
                    "status": "success",
                    "checkpoint_dir": str(checkpoint_dir),
                    "lora_file": str(lora_file),
                    "out_dir": out_dir,
                    "exit_code": result["exit_code"],
                }
        
        update_job_state(job_id, JobState.VALIDATING, "Training completed but checkpoint not found")
        return {
            "status": "warning",
            "reason": "Training completed but checkpoint not found",
            "out_dir": out_dir,
        }
    else:
        update_job_state(
            job_id,
            JobState.FAILED,
            f"Training failed: {result.get('reason', 'Unknown error')}",
            error=result.get("stderr", result.get("reason", "")),
        )
        return {
            "status": "error",
            "reason": result.get("reason", "Unknown error"),
            "stderr": result.get("stderr", ""),
            "exit_code": result.get("exit_code"),
        }


def merge_lora_weights(
    job_id: str,
    checkpoint_path: str,
) -> dict[str, Any]:
    """Merge LoRA weights into a full checkpoint.
    
    Args:
        job_id: Trainer job ID to update
        checkpoint_path: Path to LoRA checkpoint directory
    
    Returns:
        Result dict with merged checkpoint path
    """
    job = get_job(job_id)
    if not job:
        return {"status": "error", "reason": "Job not found"}
    
    litgpt_cmd = get_litgpt_command()
    command = f'{litgpt_cmd} merge_lora "{checkpoint_path}"'
    
    update_job_state(job_id, JobState.EXPORTING, f"Merging LoRA weights: {checkpoint_path}")
    
    result = run_safe_shell(command, approval="Akkoord", timeout=600)
    
    if result["status"] == "success":
        checkpoint_dir = Path(checkpoint_path)
        merged_file = checkpoint_dir / "lit_model.pth"
        if merged_file.exists():
            update_job_state(
                job_id,
                JobState.OLLAMA_CREATE,
                f"LoRA merged successfully: {merged_file}",
            )
            return {
                "status": "success",
                "merged_checkpoint": str(merged_file),
                "exit_code": result["exit_code"],
            }
        
        return {
            "status": "warning",
            "reason": "Merge completed but file not found",
        }
    else:
        update_job_state(
            job_id,
            JobState.FAILED,
            f"LoRA merge failed: {result.get('reason', 'Unknown error')}",
            error=result.get("stderr", ""),
        )
        return {
            "status": "error",
            "reason": result.get("reason", "Unknown error"),
            "stderr": result.get("stderr", ""),
        }


def validate_litgpt_model(job_id: str, checkpoint_path: str) -> dict[str, Any]:
    """Validate a LitGPT model checkpoint.
    
    Args:
        job_id: Trainer job ID to update
        checkpoint_path: Path to model checkpoint
    
    Returns:
        Validation result
    """
    job = get_job(job_id)
    if not job:
        return {"status": "error", "reason": "Job not found"}
    
    litgpt_cmd = get_litgpt_command()
    command = f'{litgpt_cmd} validate "{checkpoint_path}"'
    
    result = run_safe_shell(command, approval="Akkoord", timeout=300)
    
    if result["status"] == "success":
        update_job_state(job_id, JobState.EXPORTING, "Model validation passed")
        return {
            "status": "success",
            "validation_passed": True,
            "exit_code": result["exit_code"],
        }
    else:
        update_job_state(
            job_id,
            JobState.FAILED,
            f"Model validation failed: {result.get('reason', 'Unknown error')}",
        )
        return {
            "status": "error",
            "reason": result.get("reason", "Unknown error"),
            "validation_passed": False,
        }


def get_litgpt_status() -> dict[str, Any]:
    """Get LitGPT adapter status."""
    source_ready = litgpt_available()
    command_args = get_litgpt_args(allow_unavailable=False)
    runtime_ready = bool(command_args)
    if runtime_ready:
        status = "online"
        reason = "LitGPT source and executable runtime are available."
    elif source_ready:
        status = "configured"
        reason = "LitGPT source is present, but the venv/CLI runtime is not executable yet."
    else:
        status = "unavailable"
        reason = "LitGPT source directory is missing."
    return {
        "status": status,
        "reason": reason,
        "source_exists": source_ready,
        "source_path": str(LITGPT_SOURCE_PATH),
        "venv_path": str(LITGPT_VENV_PATH),
        "venv_exists": LITGPT_VENV_PATH.exists(),
        "venv_python_exists": _is_runnable(_venv_python()),
        "venv_script_exists": _venv_script().exists(),
        "venv_script_interpreter_ok": _script_interpreter_exists(_venv_script()),
        "runtime_ready": runtime_ready,
        "command_args": command_args,
        "command": get_litgpt_command(),
        "supported_commands": [
            "finetune_lora",
            "finetune_full",
            "finetune_adapter",
            "merge_lora",
            "validate",
            "generate",
            "chat",
            "serve",
        ],
    }
