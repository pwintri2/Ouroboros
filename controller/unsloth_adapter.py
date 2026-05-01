"""Unsloth adapter for Ouroboros trainer pipeline.

Integrates Unsloth's SFT/LoRA training capabilities with the trainer job system.
All commands run via safe_shell or Docker exec in /workspace.
Supports 4-bit training, GGUF export, and Ollama template mapping.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from controller.safe_shell import run_safe_shell, workspace_root
from controller.trainer_jobs import JobState, TrainerMethod, get_job, update_job_state


UNSLOTH_SOURCE_PATH = Path("/workspace/unsloth")
UNSLOTH_VENV_PATH = Path("/workspace/.venv_unsloth")


def unsloth_available() -> bool:
    """Check if Unsloth source is available."""
    return UNSLOTH_SOURCE_PATH.exists() and UNSLOTH_SOURCE_PATH.is_dir()


def setup_unsloth_env() -> dict[str, Any]:
    """Set up Unsloth virtual environment if needed."""
    if not unsloth_available():
        return {
            "status": "error",
            "reason": "Unsloth source not found at /home/pwintri2/unsloth",
        }
    
    workspace = workspace_root()
    
    # Check if venv exists
    if UNSLOTH_VENV_PATH.exists():
        return {
            "status": "success",
            "venv_path": str(UNSLOTH_VENV_PATH),
            "message": "Unsloth venv already exists",
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
            "message": "Unsloth venv created and installed",
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
    python_path = UNSLOTH_VENV_PATH / "bin" / "python"
    if python_path.exists():
        return str(python_path)
    return "python3"


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
    return {
        "status": "online" if unsloth_available() else "unavailable",
        "source_path": str(UNSLOTH_SOURCE_PATH),
        "venv_path": str(UNSLOTH_VENV_PATH),
        "venv_exists": UNSLOTH_VENV_PATH.exists(),
        "python_path": get_unsloth_python(),
        "supported_features": [
            "sft_training",
            "lora_training",
            "4bit_quantization",
            "gguf_export",
            "ollama_template_mapping",
        ],
    }
