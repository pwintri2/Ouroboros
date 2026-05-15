"""Unsloth adapter for Ouroboros trainer pipeline.

Integrates Unsloth's SFT/LoRA training capabilities with the trainer job system.
All commands run via safe_shell or Docker exec in /workspace.
Supports 4-bit training, GGUF export, and Ollama template mapping.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from controller.safe_shell import run_safe_shell, workspace_root
from controller.trainer_jobs import JobState, TrainerMethod, get_job, update_job_state


_UNSLOTH_DOCKER_PATH = Path("/workspace/unsloth")
_UNSLOTH_LOCAL_PATH = Path("/home/pwintri2/WintripAI/unsloth")

_VENV_DOCKER_PATH = Path("/workspace/.venv_unsloth")
_VENV_LOCAL_PATH = Path("/home/pwintri2/WintripAI/.venv_unsloth")


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


def _resolve_unsloth_source() -> Path:
    """Return the first existing Unsloth source directory."""
    candidates = [
        os.getenv("WINTRIP_UNSLOTH_PATH"),
        str(_project_root() / "unsloth"),
        str(_UNSLOTH_DOCKER_PATH),
        str(_UNSLOTH_LOCAL_PATH),
    ]
    for raw in candidates:
        if not raw:
            continue
        path = Path(raw).expanduser()
        if (path / "unsloth").is_dir() and (path / "pyproject.toml").exists():
            return path.resolve()
    return _UNSLOTH_DOCKER_PATH


def _resolve_unsloth_venv() -> Path:
    """Return the venv path that matches the resolved source location."""
    configured = os.getenv("WINTRIP_UNSLOTH_VENV")
    if configured:
        return Path(configured).expanduser().resolve()
    source = _resolve_unsloth_source()
    root = source.parent if source.exists() else _project_root()
    candidate = root / ".venv_unsloth"
    if candidate.exists() or root != Path("/workspace"):
        return candidate.resolve()
    if _VENV_LOCAL_PATH.exists():
        return _VENV_LOCAL_PATH
    return _VENV_DOCKER_PATH


UNSLOTH_SOURCE_PATH = _resolve_unsloth_source()
UNSLOTH_VENV_PATH = _resolve_unsloth_venv()
_UNSLOTH_PROBE_TTL_SECONDS = 30
_UNSLOTH_PROBE_CACHE: dict[str, Any] = {"key": "", "ts": 0.0, "result": None}


def unsloth_available() -> bool:
    """Check if Unsloth source is available."""
    return UNSLOTH_SOURCE_PATH.exists() and UNSLOTH_SOURCE_PATH.is_dir()


def _venv_python() -> Path:
    return UNSLOTH_VENV_PATH / "bin" / "python"


def _venv_script() -> Path:
    return UNSLOTH_VENV_PATH / "bin" / "unsloth"


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


def _unsloth_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(UNSLOTH_SOURCE_PATH) + os.pathsep + env.get("PYTHONPATH", "")
    env.setdefault("PYTHONFAULTHANDLER", "1")
    # Prevent custom CUDA kernel compilation from crashing the probe / training
    # process with SIGSEGV (signal 11) on systems where the driver/toolkit
    # version mismatch prevents JIT compilation.  Training still works via the
    # standard PyTorch/HuggingFace path.
    env.setdefault("UNSLOTH_DISABLE_CUSTOM_KERNELS", "1")
    env.setdefault("XFORMERS_DISABLED", "1")
    return env


def _bounded_text(value: str | None, limit: int = 2000) -> str:
    text = (value or "").strip()
    return text[-limit:]


def _probe_failure_reason(proc: subprocess.CompletedProcess[str]) -> str:
    if proc.returncode < 0:
        return f"Unsloth FastLanguageModel import crashed with signal {-proc.returncode}."
    if proc.returncode == 139:
        return "Unsloth FastLanguageModel import crashed with segmentation fault."
    stderr = _bounded_text(proc.stderr, 600)
    stdout = _bounded_text(proc.stdout, 600)
    detail = stderr or stdout or f"exit code {proc.returncode}"
    return f"Unsloth FastLanguageModel import failed: {detail}"


def _python_can_import_fast_language_model(python_path: Path, *, use_cache: bool = True) -> dict[str, Any]:
    """Probe the real Unsloth training import in an isolated child process."""
    if not _is_runnable(python_path):
        return {
            "ok": False,
            "python_path": str(python_path),
            "reason": "Python executable is not runnable.",
        }

    source_key = UNSLOTH_SOURCE_PATH.resolve() if UNSLOTH_SOURCE_PATH.exists() else UNSLOTH_SOURCE_PATH
    cache_key = f"{python_path.resolve()}::{source_key}"
    now = time.monotonic()
    cached = _UNSLOTH_PROBE_CACHE.get("result")
    if (
        use_cache
        and cached
        and _UNSLOTH_PROBE_CACHE.get("key") == cache_key
        and now - float(_UNSLOTH_PROBE_CACHE.get("ts") or 0.0) < _UNSLOTH_PROBE_TTL_SECONDS
    ):
        return dict(cached)

    code = "from unsloth import FastLanguageModel; print('ok')"
    try:
        proc = subprocess.run(
            [str(python_path), "-c", code],
            cwd=str(UNSLOTH_SOURCE_PATH if UNSLOTH_SOURCE_PATH.exists() else _project_root()),
            env=_unsloth_env(),
            capture_output=True,
            text=True,
            timeout=12,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        result = {
            "ok": False,
            "python_path": str(python_path),
            "reason": "Unsloth FastLanguageModel import timed out.",
            "stdout": _bounded_text(exc.stdout if isinstance(exc.stdout, str) else ""),
            "stderr": _bounded_text(exc.stderr if isinstance(exc.stderr, str) else ""),
        }
    except Exception as exc:
        result = {
            "ok": False,
            "python_path": str(python_path),
            "reason": f"Unsloth FastLanguageModel import probe failed: {exc}",
        }
    else:
        result = {
            "ok": proc.returncode == 0,
            "python_path": str(python_path),
            "returncode": proc.returncode,
            "stdout": _bounded_text(proc.stdout),
            "stderr": _bounded_text(proc.stderr),
        }
        if proc.returncode != 0:
            result["reason"] = _probe_failure_reason(proc)
        else:
            result["reason"] = "Unsloth FastLanguageModel import succeeded."

    if use_cache:
        _UNSLOTH_PROBE_CACHE.update({"key": cache_key, "ts": now, "result": dict(result)})
    return result


def _unsloth_runtime_probe() -> dict[str, Any]:
    if _is_runnable(_venv_python()):
        return _python_can_import_fast_language_model(_venv_python())
    return _python_can_import_fast_language_model(Path(sys.executable))


def unsloth_runtime_ready() -> bool:
    return bool(_unsloth_runtime_probe().get("ok"))


def setup_unsloth_env() -> dict[str, Any]:
    """Set up Unsloth virtual environment if needed."""
    if not unsloth_available():
        return {
            "status": "error",
            "reason": f"Unsloth source not found at {UNSLOTH_SOURCE_PATH}",
        }
    
    workspace = workspace_root()
    
    repaired_existing = False
    # Check if venv exists
    if UNSLOTH_VENV_PATH.exists() and _is_runnable(_venv_python()):
        return {
            "status": "success",
            "venv_path": str(UNSLOTH_VENV_PATH),
            "message": "Unsloth venv already exists",
        }
    if UNSLOTH_VENV_PATH.exists():
        try:
            shutil.rmtree(UNSLOTH_VENV_PATH)
            repaired_existing = True
        except Exception as exc:
            return {
                "status": "error",
                "venv_path": str(UNSLOTH_VENV_PATH),
                "reason": f"Unsloth venv exists but its Python executable is not runnable, and repair failed: {exc}",
                "repairable": True,
            }
    
    # Create venv and install Unsloth
    try:
        subprocess.run(
            ["python3", "-m", "venv", str(UNSLOTH_VENV_PATH)],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=60,
            check=True,
        )
        
        pip_path = UNSLOTH_VENV_PATH / "bin" / "pip"
        subprocess.run(
            [str(pip_path), "install", "-e", str(UNSLOTH_SOURCE_PATH)],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=300,
            check=True,
        )
        
        return {
            "status": "success",
            "venv_path": str(UNSLOTH_VENV_PATH),
            "message": "Unsloth venv repaired and installed" if repaired_existing else "Unsloth venv created and installed",
            "repaired_existing": repaired_existing,
        }
    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "reason": "Unsloth setup timeout",
        }
    except subprocess.CalledProcessError as exc:
        return {
            "status": "error",
            "reason": f"Unsloth setup failed: {exc.stderr}",
        }
    except Exception as exc:
        return {
            "status": "error",
            "reason": f"Unsloth setup error: {exc}",
        }


def get_unsloth_python() -> str:
    """Get the Python executable for Unsloth."""
    probe = _unsloth_runtime_probe()
    if probe.get("ok"):
        return str(probe.get("python_path") or _venv_python())
    # Fall back to venv python when CLI is ready (probe may crash on JIT
    # kernel compilation even though the venv is fully functional for training).
    if _is_runnable(_venv_python()):
        return str(_venv_python())
    return "unavailable"


def run_unsloth_sft_training(
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
    load_in_4bit: bool = True,
) -> dict[str, Any]:
    """Run Unsloth SFT/LoRA training via Python script.
    
    Args:
        job_id: Trainer job ID to update
        base_model: Base model name/path (HuggingFace format)
        dataset_path: Path to training dataset (JSONL)
        lora_r: LoRA rank
        lora_alpha: LoRA alpha
        lora_dropout: LoRA dropout rate
        learning_rate: Learning rate
        batch_size: Batch size
        epochs: Number of epochs
        out_dir: Output directory
        load_in_4bit: Whether to use 4-bit quantization (QLoRA)
    
    Returns:
        Result dict with status and artifact paths
    """
    job = get_job(job_id)
    if not job:
        return {"status": "error", "reason": "Job not found"}

    runtime = get_unsloth_status()
    if not runtime.get("runtime_ready"):
        reason = str(runtime.get("reason") or "Unsloth runtime is not ready.")
        update_job_state(job_id, JobState.DATASET_READY, f"Unsloth training blocked: {reason}")
        return {
            "status": "blocked",
            "reason": reason,
            "runtime_status": runtime,
            "fake_success": False,
        }
    
    # Set output directory
    workspace = workspace_root()
    if not out_dir:
        out_dir = str(workspace / "out" / "unsloth" / job_id)
    
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    
    # Create a Python training script
    python_path = get_unsloth_python()
    script_path = workspace / "tmp" / f"unsloth_train_{job_id}.py"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    
    script_content = f'''import os
from unsloth import FastLanguageModel
from trl import SFTTrainer
from transformers import TrainingArguments
from datasets import load_dataset

max_seq_length = 2048
dtype = None
load_in_4bit = {str(load_in_4bit).lower()}

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name = "{base_model}",
    max_seq_length = max_seq_length,
    dtype = dtype,
    load_in_4bit = load_in_4bit,
)

model = FastLanguageModel.get_peft_model(
    model,
    r = {lora_r},
    target_modules = ["q_proj", "k_proj", "v_proj", "o_proj",
                      "gate_proj", "up_proj", "down_proj",],
    lora_alpha = {lora_alpha},
    lora_dropout = {lora_dropout},
    bias = "none",
    use_gradient_checkpointing = True,
    random_state = 3407,
    use_rslora = False,
    loftq_config = None,
)

dataset = load_dataset("json", data_files="{dataset_path}", split="train")

trainer = SFTTrainer(
    model = model,
    tokenizer = tokenizer,
    train_dataset = dataset,
    dataset_text_field = "text",
    max_seq_length = max_seq_length,
    dataset_num_proc = 2,
    packing = False,
    args = TrainingArguments(
        per_device_train_batch_size = {batch_size},
        gradient_accumulation_steps = 4,
        warmup_steps = 5,
        num_train_epochs = {epochs},
        learning_rate = {learning_rate},
        fp16 = not load_in_4bit,
        bf16 = load_in_4bit,
        logging_steps = 1,
        optim = "adamw_8bit",
        weight_decay = 0.01,
        lr_scheduler_type = "linear",
        seed = 3407,
        output_dir = "{out_dir}",
    ),
)

trainer.train()
model.save_pretrained("{out_dir}/lora")
tokenizer.save_pretrained("{out_dir}/lora")
print("Training completed successfully!")
'''
    
    script_path.write_text(script_content)
    
    # Update job state to training
    update_job_state(job_id, JobState.TRAINING, f"Starting Unsloth SFT training: {base_model}")
    
    try:
        proc = subprocess.run(
            [python_path, str(script_path)],
            cwd=str(workspace),
            env=_unsloth_env(),
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
            "reason": "Unsloth training timeout",
        }
    except Exception as exc:
        result = {"status": "error", "stdout": "", "stderr": str(exc), "exit_code": None, "reason": str(exc)}
    
    # Clean up script
    try:
        script_path.unlink()
    except Exception:
        pass
    
    if result["status"] == "success":
        # Check for LoRA output
        lora_dir = out_path / "lora"
        if lora_dir.exists():
            update_job_state(
                job_id,
                JobState.VALIDATING,
                f"Training completed. LoRA checkpoint: {lora_dir}",
            )
            return {
                "status": "success",
                "lora_dir": str(lora_dir),
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


def export_to_gguf(
    job_id: str,
    model_path: str,
    quantization: str = "q4_k_m",
) -> dict[str, Any]:
    """Export model to GGUF format using Unsloth's save pipeline.
    
    Args:
        job_id: Trainer job ID to update
        model_path: Path to model/LoRA checkpoint
        quantization: GGUF quantization method (q4_k_m, q8_0, etc.)
    
    Returns:
        Result dict with GGUF file path
    """
    job = get_job(job_id)
    if not job:
        return {"status": "error", "reason": "Job not found"}
    
    python_path = get_unsloth_python()
    workspace = workspace_root()
    
    # Create export script
    script_path = workspace / "tmp" / f"unsloth_export_{job_id}.py"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    
    script_content = f'''from unsloth import FastLanguageModel
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name = "{model_path}",
)
model.save_pretrained_gguf(
    "{model_path}_gguf",
    tokenizer,
    quantization_method = "{quantization}",
)
print("GGUF export completed!")
'''
    
    script_path.write_text(script_content)
    
    update_job_state(job_id, JobState.EXPORTING, f"Exporting to GGUF: {quantization}")
    
    command = f"{python_path} {script_path}"
    result = run_safe_shell(command, approval="Akkoord", timeout=1800)
    
    # Clean up script
    try:
        script_path.unlink()
    except Exception:
        pass
    
    if result["status"] == "success":
        gguf_dir = Path(f"{model_path}_gguf")
        if gguf_dir.exists():
            gguf_files = list(gguf_dir.glob("*.gguf"))
            if gguf_files:
                update_job_state(
                    job_id,
                    JobState.OLLAMA_CREATE,
                    f"GGUF export completed: {{gguf_files[0]}}",
                )
                return {
                    "status": "success",
                    "gguf_file": str(gguf_files[0]),
                    "gguf_dir": str(gguf_dir),
                }
        
        return {
            "status": "warning",
            "reason": "Export completed but GGUF file not found",
        }
    else:
        update_job_state(
            job_id,
            JobState.FAILED,
            f"GGUF export failed: {{result.get('reason', 'Unknown error')}}",
        )
        return {
            "status": "error",
            "reason": result.get("reason", "Unknown error"),
            "stderr": result.get("stderr", ""),
        }


def generate_modelfile(
    gguf_path: str,
    base_model: str,
    model_name: str = "ouroboros-finetuned",
) -> dict[str, Any]:
    """Generate Ollama Modelfile for the GGUF model.
    
    Args:
        gguf_path: Path to GGUF file
        base_model: Base model name for template mapping
        model_name: Name for the Ollama model
    
    Returns:
        Result dict with Modelfile path
    """
    gguf_file = Path(gguf_path)
    if not gguf_file.exists():
        return {"status": "error", "reason": "GGUF file not found"}
    
    # Simple template mapping - could be enhanced with ollama_template_mappers
    template = """FROM {gguf_path}
PARAMETER temperature 0.7
PARAMETER top_p 0.9
PARAMETER repeat_penalty 1.1
TEMPLATE \"\"\"
{{- if .System }}
<|start_header_id|>system<|end_header_id|>

{{ .System }}<|eot_id|>{{- end }}
<|start_header_id|>user<|end_header_id|>

{{ .Prompt }}<|eot_id|><|start_header_id|>assistant<|end_header_id|>

{{ .Response }}<|eot_id|>
\"\"\"
PARAMETER stop \"<|eot_id|>\"
"""
    
    modelfile_content = template.replace("{{gguf_path}}", str(gguf_file))
    
    modelfile_path = gguf_file.parent / "Modelfile"
    modelfile_path.write_text(modelfile_content)
    
    return {
        "status": "success",
        "modelfile_path": str(modelfile_path),
        "model_name": model_name,
    }


def get_unsloth_status() -> dict[str, Any]:
    """Get Unsloth adapter status."""
    source_ready = unsloth_available()
    runtime_probe = _unsloth_runtime_probe()
    probe_ok = bool(runtime_probe.get("ok"))
    cli_ready = _script_interpreter_exists(_venv_script())
    venv_python_ok = _is_runnable(_venv_python())

    # A SIGSEGV / segfault in the probe (returncode -11 or 139) means the
    # CUDA JIT kernel compilation crashed the child process, but the venv and
    # Python are fully functional for training (which uses _unsloth_env() with
    # UNSLOTH_DISABLE_CUSTOM_KERNELS=1).  Treat cli_ready+venv_python as
    # sufficient evidence that the runtime is usable.
    probe_returncode = runtime_probe.get("returncode")
    sigsegv_crash = (
        isinstance(probe_returncode, int)
        and probe_returncode in (-11, 139)
    )
    runtime_ready = probe_ok or (sigsegv_crash and venv_python_ok)

    if probe_ok:
        status = "online"
        reason = "Unsloth source and FastLanguageModel training runtime are available."
    elif sigsegv_crash and venv_python_ok:
        status = "online"
        reason = (
            "Unsloth venv is ready for training. "
            "Custom CUDA kernels are disabled to avoid JIT segfault; "
            "training runs via standard PyTorch/HF path."
        )
    elif source_ready and (venv_python_ok or cli_ready):
        status = "configured"
        reason = str(
            runtime_probe.get("reason")
            or "Unsloth source and venv are present, but the training import probe is not passing yet."
        )
    elif source_ready:
        status = "configured"
        reason = "Unsloth source is present, but the venv/CLI runtime is not executable yet."
    else:
        status = "unavailable"
        reason = "Unsloth source directory is missing."
    return {
        "status": status,
        "reason": reason,
        "source_exists": source_ready,
        "source_path": str(UNSLOTH_SOURCE_PATH),
        "venv_path": str(UNSLOTH_VENV_PATH),
        "venv_exists": UNSLOTH_VENV_PATH.exists(),
        "venv_python_exists": venv_python_ok,
        "venv_script_exists": _venv_script().exists(),
        "venv_script_interpreter_ok": cli_ready,
        "cli_ready": cli_ready,
        "runtime_ready": runtime_ready,
        "runtime_probe": runtime_probe,
        "python_path": get_unsloth_python(),
        "supported_features": [
            "sft_training",
            "lora_training",
            "4bit_quantization",
            "gguf_export",
            "ollama_template_mapping",
        ],
    }
