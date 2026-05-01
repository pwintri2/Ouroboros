"""LitGPT adapter for Ouroboros trainer pipeline.

Integrates LitGPT's fine-tuning capabilities (LoRA, full, adapter) with the
trainer job system. All commands run via safe_shell or Docker exec in /workspace.
Captures stdout/stderr/exit_code in trainer job records.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from controller.safe_shell import run_safe_shell, workspace_root
from controller.trainer_jobs import JobState, TrainerMethod, get_job, update_job_state


LITGPT_SOURCE_PATH = Path("/workspace/litgpt")
LITGPT_VENV_PATH = Path("/workspace/.venv_litgpt")


def litgpt_available() -> bool:
    """Check if LitGPT source is available."""
    return LITGPT_SOURCE_PATH.exists() and LITGPT_SOURCE_PATH.is_dir()


def setup_litgpt_env() -> dict[str, Any]:
    """Set up LitGPT virtual environment if needed."""
    if not litgpt_available():
        return {
            "status": "error",
            "reason": "LitGPT source not found at /home/pwintri2/litgpt",
        }
    
    workspace = workspace_root()
    
    # Check if venv exists
    if LITGPT_VENV_PATH.exists():
        return {
            "status": "success",
            "venv_path": str(LITGPT_VENV_PATH),
            "message": "LitGPT venv already exists",
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
    python_path = LITGPT_VENV_PATH / "bin" / "python"
    main_path = LITGPT_SOURCE_PATH / "litgpt" / "__main__.py"
    
    if python_path.exists() and main_path.exists():
        return f"{python_path} -m litgpt"
    
    # Fallback: try system litgpt
    return "litgpt"


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
    
    # Build command
    litgpt_cmd = get_litgpt_command()
    
    cmd_parts = [
        litgpt_cmd,
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
    
    command = " ".join(cmd_parts)
    
    # Update job state to training
    update_job_state(job_id, JobState.TRAINING, f"Starting LitGPT LoRA fine-tuning: {base_model}")
    
    # Run via safe_shell (requires approval)
    result = run_safe_shell(command, approval="Akkoord", timeout=3600)
    
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
    return {
        "status": "online" if litgpt_available() else "unavailable",
        "source_path": str(LITGPT_SOURCE_PATH),
        "venv_path": str(LITGPT_VENV_PATH),
        "venv_exists": LITGPT_VENV_PATH.exists(),
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
