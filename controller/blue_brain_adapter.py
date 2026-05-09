"""Blue Brain inspired trainer adapter for the Ouroboros trainer pipeline.

This module turns the original ``Blue.py`` demo into reusable training
functions plus a job-runner adapter. Heavy ML dependencies are imported lazily
so the FastAPI backend can still boot before the Blue Brain environment exists.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence


E_TYPES = ["cAC", "bAC", "cNAC", "bNAC", "dNAC", "cSTUT", "bSTUT", "dSTUT", "cIR", "bIR", "cAD"]
CLASS_NAMES = ["Asynchronous low Ca2+", "Synchronous high Ca2+"]
REQUIRED_PACKAGES = ("numpy", "sklearn", "joblib")


def _workspace_root() -> Path:
    configured = os.getenv("WINTRIP_WORKSPACE") or os.getenv("WORKSPACE_ROOT") or "/workspace"
    if configured and configured != "/workspace":
        root = Path(configured).expanduser()
        if root.exists():
            return root.resolve()
    project_root = Path(__file__).resolve().parents[1]
    cwd = Path.cwd().resolve()
    for root in (Path(os.getenv("WINTRIP_PROJECT_ROOT") or "").expanduser(), cwd, project_root, Path("/workspace")):
        if str(root) and root.exists() and (root / "controller").is_dir():
            return root.resolve()
    return project_root.resolve()


def blue_brain_venv_path() -> Path:
    configured = os.getenv("BLUE_BRAIN_VENV_PATH")
    if configured:
        return Path(configured).resolve()
    return (_workspace_root() / ".venv_blue_brain").resolve()


def feature_names(n_features: int = 11) -> list[str]:
    """Return Blue Brain e-type feature names, padded for custom dimensions."""
    if n_features <= len(E_TYPES):
        return E_TYPES[:n_features]
    return E_TYPES + [f"feature_{index}" for index in range(len(E_TYPES) + 1, n_features + 1)]


def _dependency_map() -> dict[str, bool]:
    return {name: importlib.util.find_spec(name) is not None for name in REQUIRED_PACKAGES}


def _python_dependency_map(python_path: Path) -> dict[str, bool]:
    if not _python_is_runnable(python_path):
        return {name: False for name in REQUIRED_PACKAGES}
    code = (
        "import importlib.util, json; "
        f"names={list(REQUIRED_PACKAGES)!r}; "
        "print(json.dumps({name: importlib.util.find_spec(name) is not None for name in names}))"
    )
    try:
        proc = subprocess.run(
            [str(python_path), "-c", code],
            text=True,
            capture_output=True,
            timeout=15,
            check=True,
        )
        data = json.loads(proc.stdout.strip() or "{}")
        return {name: bool(data.get(name)) for name in REQUIRED_PACKAGES}
    except Exception:
        return {name: False for name in REQUIRED_PACKAGES}


def _venv_python() -> Path:
    return blue_brain_venv_path() / "bin" / "python"


def _python_is_runnable(python_path: Path) -> bool:
    if not python_path.exists() or not os.access(python_path, os.X_OK):
        return False
    try:
        proc = subprocess.run(
            [str(python_path), "-c", "import sys; print(sys.executable)"],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except Exception:
        return False
    return proc.returncode == 0


def _python_has_pip(python_path: Path) -> bool:
    if not _python_is_runnable(python_path):
        return False
    try:
        proc = subprocess.run(
            [str(python_path), "-m", "pip", "--version"],
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )
    except Exception:
        return False
    return proc.returncode == 0


def _bootstrap_python() -> str:
    candidates = [
        os.getenv("BLUE_BRAIN_BOOTSTRAP_PYTHON"),
        sys.executable,
        shutil.which("python3.11"),
        shutil.which("python3.10"),
        shutil.which("python3"),
    ]
    for raw in candidates:
        if not raw:
            continue
        path = Path(raw).expanduser()
        if _python_is_runnable(path):
            return str(path)
    return "python3"


def _create_blue_brain_venv(venv_path: Path, *, clear: bool, workspace: Path) -> subprocess.CompletedProcess[str]:
    args = [_bootstrap_python(), "-m", "venv"]
    if clear:
        args.append("--clear")
    args.append(str(venv_path))
    return subprocess.run(
        args,
        cwd=str(workspace),
        text=True,
        capture_output=True,
        timeout=120,
        check=True,
    )


def _ensure_blue_brain_venv(workspace: Path, venv_path: Path) -> list[subprocess.CompletedProcess[str]]:
    logs: list[subprocess.CompletedProcess[str]] = []
    if not venv_path.exists():
        logs.append(_create_blue_brain_venv(venv_path, clear=False, workspace=workspace))
    elif not _python_is_runnable(_venv_python()):
        logs.append(_create_blue_brain_venv(venv_path, clear=True, workspace=workspace))

    if not _python_has_pip(_venv_python()):
        try:
            logs.append(
                subprocess.run(
                    [str(_venv_python()), "-m", "ensurepip", "--upgrade"],
                    cwd=str(workspace),
                    text=True,
                    capture_output=True,
                    timeout=120,
                    check=True,
                )
            )
        except Exception:
            logs.append(_create_blue_brain_venv(venv_path, clear=True, workspace=workspace))

    if not _python_has_pip(_venv_python()):
        raise RuntimeError(f"Blue Brain venv has no working pip after setup: {_venv_python()}")
    return logs


def _current_dependencies_ready() -> bool:
    return all(_dependency_map().values())


def _venv_dependencies_ready() -> bool:
    return all(_python_dependency_map(_venv_python()).values())


def get_blue_brain_status() -> dict[str, Any]:
    """Return adapter status without importing sklearn."""
    venv_path = blue_brain_venv_path()
    current_deps = _dependency_map()
    venv_deps = _python_dependency_map(_venv_python()) if venv_path.exists() else {
        name: False for name in REQUIRED_PACKAGES
    }
    current_ready = all(current_deps.values())
    venv_ready = all(venv_deps.values())
    runtime = "current_python" if current_ready else "blue_brain_venv" if venv_ready else "unavailable"
    return {
        "status": "online" if current_ready or venv_ready else "missing_dependencies",
        "runtime": runtime,
        "venv_path": str(venv_path),
        "venv_exists": venv_path.exists(),
        "venv_python": str(_venv_python()),
        "venv_python_ready": _python_is_runnable(_venv_python()),
        "venv_pip_ready": _python_has_pip(_venv_python()),
        "current_python": sys.executable,
        "current_dependencies": current_deps,
        "venv_dependencies": venv_deps,
        "feature_count": len(E_TYPES),
        "features": list(E_TYPES),
        "model_type": "RandomForestClassifier",
        "supported_features": [
            "synthetic_11d_dataset",
            "random_forest_training",
            "joblib_export",
            "reload_validation",
            "bounded_continual_cycles",
        ],
    }


def setup_blue_brain_env() -> dict[str, Any]:
    """Create the dedicated Blue Brain virtual environment if needed."""
    workspace = _workspace_root()
    venv_path = blue_brain_venv_path()
    venv_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        setup_logs = _ensure_blue_brain_venv(workspace, venv_path)
        python_path = _venv_python()
        upgrade = subprocess.run(
            [str(python_path), "-m", "pip", "install", "--upgrade", "pip"],
            cwd=str(workspace),
            text=True,
            capture_output=True,
            timeout=300,
            check=True,
        )
        proc = subprocess.run(
            [str(python_path), "-m", "pip", "install", "numpy", "scikit-learn", "joblib"],
            cwd=str(workspace),
            text=True,
            capture_output=True,
            timeout=900,
            check=True,
        )
        return {
            "status": "success",
            "venv_path": str(venv_path),
            "dependencies": _python_dependency_map(_venv_python()),
            "venv_python_ready": _python_is_runnable(_venv_python()),
            "venv_pip_ready": _python_has_pip(_venv_python()),
            "stdout": "\n".join([item.stdout for item in setup_logs] + [upgrade.stdout, proc.stdout])[-4000:],
            "stderr": "\n".join([item.stderr for item in setup_logs] + [upgrade.stderr, proc.stderr])[-4000:],
        }
    except subprocess.CalledProcessError as exc:
        return {
            "status": "error",
            "reason": "Blue Brain setup failed",
            "stdout": exc.stdout[-4000:] if exc.stdout else "",
            "stderr": exc.stderr[-4000:] if exc.stderr else "",
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "timeout",
            "reason": "Blue Brain setup timed out",
            "stdout": exc.stdout[-4000:] if isinstance(exc.stdout, str) else "",
            "stderr": exc.stderr[-4000:] if isinstance(exc.stderr, str) else "",
        }
    except Exception as exc:
        return {"status": "error", "reason": f"Blue Brain setup error: {exc}"}


def generate_dataset(
    n_samples: int = 10_000,
    n_features: int = 11,
    random_state: int = 42,
) -> tuple[Any, Any]:
    """Generate an 11D synthetic state dataset inspired by the Blue Brain paper."""
    if n_samples < 10:
        raise ValueError("n_samples must be at least 10")
    if n_features < 2:
        raise ValueError("n_features must be at least 2")

    from sklearn.datasets import make_classification

    informative = min(n_features, max(2, min(n_features - 2, 9)))
    redundant = max(0, min(n_features - informative, 2))
    return make_classification(
        n_samples=n_samples,
        n_features=n_features,
        n_informative=informative,
        n_redundant=redundant,
        n_classes=2,
        weights=[0.65, 0.35],
        class_sep=1.8,
        random_state=random_state,
    )


def train_model(X: Any, y: Any, hyperparams: dict[str, Any] | None = None) -> tuple[Any, dict[str, Any]]:
    """Train and evaluate a RandomForestClassifier."""
    params = {
        "n_estimators": 300,
        "max_depth": 12,
        "random_state": 42,
        "test_size": 0.2,
        "n_jobs": -1,
        **(hyperparams or {}),
    }

    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import accuracy_score, classification_report
    from sklearn.model_selection import train_test_split

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=float(params["test_size"]),
        random_state=int(params["random_state"]),
        stratify=y,
    )
    model = RandomForestClassifier(
        n_estimators=int(params["n_estimators"]),
        max_depth=None if params.get("max_depth") is None else int(params["max_depth"]),
        random_state=int(params["random_state"]),
        n_jobs=int(params.get("n_jobs", -1)),
    )
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    accuracy = float(accuracy_score(y_test, y_pred))
    names = list(params.get("feature_names") or feature_names(getattr(X, "shape", [0, 11])[1]))
    importances = [
        {"feature": name, "importance": float(score)}
        for name, score in zip(names, getattr(model, "feature_importances_", []))
    ]
    importances.sort(key=lambda item: item["importance"], reverse=True)
    metrics = {
        "accuracy": accuracy,
        "classification_report": _jsonable(
            classification_report(y_test, y_pred, target_names=CLASS_NAMES, output_dict=True, zero_division=0)
        ),
        "train_samples": int(len(y_train)),
        "test_samples": int(len(y_test)),
        "feature_importances": importances,
        "hyperparams": {
            "n_estimators": int(params["n_estimators"]),
            "max_depth": params.get("max_depth"),
            "random_state": int(params["random_state"]),
            "test_size": float(params["test_size"]),
        },
    }
    return model, metrics


def predict(model: Any, X_new: Any) -> Any:
    """Predict synchronous/asynchronous state for new 11D points."""
    return model.predict(X_new)


def save_model(model: Any, path: str | Path, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Persist a model payload with joblib."""
    import joblib

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "model": model,
        "metadata": metadata or {},
        "feature_names": feature_names(int((metadata or {}).get("n_features", 11))),
        "class_names": list(CLASS_NAMES),
        "saved_at": datetime.utcnow().isoformat(),
    }
    joblib.dump(payload, output_path)
    return {
        "path": str(output_path),
        "size_bytes": output_path.stat().st_size,
        "saved_at": payload["saved_at"],
    }


def load_model_payload(path: str | Path) -> dict[str, Any]:
    """Load the full saved Blue Brain payload."""
    import joblib

    payload = joblib.load(Path(path))
    if isinstance(payload, dict) and "model" in payload:
        return payload
    return {"model": payload, "metadata": {}, "feature_names": list(E_TYPES), "class_names": list(CLASS_NAMES)}


def load_model(path: str | Path) -> Any:
    """Load a previously saved Blue Brain model."""
    return load_model_payload(path)["model"]


def train_blue_brain_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Run one bounded continual-training payload and write model artifacts."""
    job_id = str(payload["job_id"])
    out_dir = Path(payload["out_dir"])
    n_samples = int(payload.get("n_samples", 10_000))
    n_features = int(payload.get("n_features", 11))
    n_estimators = int(payload.get("n_estimators", 300))
    max_depth = payload.get("max_depth", 12)
    random_state = int(payload.get("random_state", 42))
    test_size = float(payload.get("test_size", 0.2))
    cycles = max(1, min(int(payload.get("cycles", 1)), 50))
    names = feature_names(n_features)

    out_dir.mkdir(parents=True, exist_ok=True)
    cycle_results: list[dict[str, Any]] = []
    last_model_path: Path | None = None
    last_metrics_path: Path | None = None
    last_metrics: dict[str, Any] | None = None

    for cycle in range(1, cycles + 1):
        cycle_seed = random_state + cycle - 1
        X, y = generate_dataset(n_samples=n_samples, n_features=n_features, random_state=cycle_seed)
        model, metrics = train_model(
            X,
            y,
            {
                "n_estimators": n_estimators,
                "max_depth": max_depth,
                "random_state": cycle_seed,
                "test_size": test_size,
                "feature_names": names,
            },
        )
        metadata = {
            "job_id": job_id,
            "cycle": cycle,
            "cycles": cycles,
            "n_samples": n_samples,
            "n_features": n_features,
            "feature_names": names,
            "class_names": list(CLASS_NAMES),
            "trained_at": datetime.utcnow().isoformat(),
            "accuracy": metrics["accuracy"],
        }
        model_path = out_dir / f"blue_brain_cycle_{cycle:03d}.joblib"
        metrics_path = out_dir / f"blue_brain_cycle_{cycle:03d}_metrics.json"
        saved = save_model(model, model_path, metadata=metadata)
        metrics_payload = {**metadata, "metrics": metrics, "model_path": str(model_path)}
        metrics_path.write_text(json.dumps(metrics_payload, indent=2, sort_keys=True), encoding="utf-8")
        cycle_results.append(
            {
                "cycle": cycle,
                "accuracy": metrics["accuracy"],
                "model_path": str(model_path),
                "metrics_path": str(metrics_path),
                "size_bytes": saved["size_bytes"],
            }
        )
        last_model_path = model_path
        last_metrics_path = metrics_path
        last_metrics = metrics

    if last_model_path is None or last_metrics_path is None or last_metrics is None:
        return {"status": "error", "reason": "No Blue Brain training cycles completed"}

    loaded = load_model(last_model_path)
    sample = _make_sample_point(n_features=n_features, random_state=random_state + cycles + 10_000)
    prediction = int(predict(loaded, sample)[0])
    probabilities = [float(value) for value in loaded.predict_proba(sample)[0]]

    summary_path = out_dir / "blue_brain_summary.json"
    result = {
        "status": "success",
        "job_id": job_id,
        "model_path": str(last_model_path),
        "metrics_path": str(last_metrics_path),
        "summary_path": str(summary_path),
        "out_dir": str(out_dir),
        "cycles": cycles,
        "cycle_results": cycle_results,
        "metrics": last_metrics,
        "reload_validation": {
            "passed": True,
            "sample_prediction": prediction,
            "sample_label": CLASS_NAMES[prediction],
            "probabilities": probabilities,
        },
    }
    summary_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return result


def run_blue_brain_training(
    job_id: str,
    n_samples: int = 10_000,
    n_features: int = 11,
    n_estimators: int = 300,
    max_depth: int | None = 12,
    random_state: int = 42,
    test_size: float = 0.2,
    cycles: int = 1,
    out_dir: str | None = None,
) -> dict[str, Any]:
    """Run Blue Brain training for an existing trainer job."""
    from controller.model_artifacts import ArtifactType, register_artifact as register_model_artifact
    from controller.trainer_jobs import (
        JobState,
        get_job,
        register_artifact as register_job_artifact,
        set_validation_passed,
        update_job_state,
    )

    job = get_job(job_id)
    if not job:
        return {"status": "error", "reason": "Job not found"}

    workspace = _workspace_root()
    output_dir = Path(out_dir) if out_dir else workspace / "out" / "blue_brain" / job_id
    payload = {
        "job_id": job_id,
        "out_dir": str(output_dir),
        "n_samples": n_samples,
        "n_features": n_features,
        "n_estimators": n_estimators,
        "max_depth": max_depth,
        "random_state": random_state,
        "test_size": test_size,
        "cycles": cycles,
    }

    update_job_state(job_id, JobState.TRAINING, f"Starting Blue Brain training: {cycles} cycle(s)")

    try:
        if _current_dependencies_ready():
            result = train_blue_brain_payload(payload)
            result["runtime"] = "current_python"
        elif _venv_dependencies_ready():
            result = _run_payload_in_venv(payload, workspace=workspace)
            result["runtime"] = "blue_brain_venv"
        else:
            result = {
                "status": "error",
                "reason": "Blue Brain dependencies missing. Run /trainer/blue-brain/setup first.",
                "dependencies": get_blue_brain_status(),
            }
    except Exception as exc:
        result = {"status": "error", "reason": f"Blue Brain training failed: {exc}"}

    if result.get("status") != "success":
        update_job_state(job_id, JobState.FAILED, result.get("reason", "Blue Brain training failed"), error=result.get("reason", ""))
        return result

    accuracy = float(result["metrics"]["accuracy"])
    artifact_metadata = {
        "accuracy": accuracy,
        "cycles": int(result["cycles"]),
        "n_samples": int(n_samples),
        "n_features": int(n_features),
        "n_estimators": int(n_estimators),
        "max_depth": max_depth,
        "runtime": result.get("runtime"),
        "reload_validation": result["reload_validation"],
    }
    register_model_artifact(job_id, ArtifactType.BLUE_BRAIN_MODEL, result["model_path"], artifact_metadata)
    register_model_artifact(job_id, ArtifactType.METRICS, result["metrics_path"], artifact_metadata)
    register_job_artifact(job_id, "blue_brain_model", result["model_path"], artifact_metadata)
    register_job_artifact(job_id, "blue_brain_metrics", result["metrics_path"], artifact_metadata)
    set_validation_passed(job_id, True)
    update_job_state(
        job_id,
        JobState.ONLINE,
        f"Blue Brain model saved and reload-validated at {result['model_path']}",
    )
    return result


class BlueBrainTrainer:
    """Small object wrapper matching the trainer-adapter style."""

    def status(self) -> dict[str, Any]:
        return get_blue_brain_status()

    def setup(self) -> dict[str, Any]:
        return setup_blue_brain_env()

    def train(self, job_id: str, **kwargs: Any) -> dict[str, Any]:
        return run_blue_brain_training(job_id=job_id, **kwargs)


def _make_sample_point(n_features: int, random_state: int) -> Any:
    import numpy as np

    rng = np.random.default_rng(random_state)
    return rng.uniform(-1.5, 1.5, size=(1, n_features))


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    try:
        import numpy as np

        if isinstance(value, np.generic):
            return value.item()
    except Exception:
        pass
    return value


def _run_payload_in_venv(payload: dict[str, Any], workspace: Path) -> dict[str, Any]:
    tmp_dir = workspace / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    payload_path = tmp_dir / f"blue_brain_payload_{payload['job_id']}.json"
    result_path = tmp_dir / f"blue_brain_result_{payload['job_id']}.json"
    payload_path.write_text(json.dumps(payload), encoding="utf-8")
    env = dict(os.environ)
    env["PYTHONPATH"] = f"{workspace}{os.pathsep}{env.get('PYTHONPATH', '')}".rstrip(os.pathsep)
    proc = subprocess.run(
        [
            str(_venv_python()),
            "-m",
            "controller.blue_brain_adapter",
            "--train-payload",
            str(payload_path),
            "--output-json",
            str(result_path),
        ],
        cwd=str(workspace),
        env=env,
        text=True,
        capture_output=True,
        timeout=1800,
    )
    if proc.returncode != 0:
        return {
            "status": "error",
            "reason": "Blue Brain venv training failed",
            "stdout": proc.stdout[-4000:],
            "stderr": proc.stderr[-4000:],
            "exit_code": proc.returncode,
        }
    if not result_path.exists():
        return {
            "status": "error",
            "reason": "Blue Brain venv training produced no result file",
            "stdout": proc.stdout[-4000:],
            "stderr": proc.stderr[-4000:],
            "exit_code": proc.returncode,
        }
    return json.loads(result_path.read_text(encoding="utf-8"))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a Blue Brain training payload.")
    parser.add_argument("--train-payload", required=True)
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args(argv)

    payload = json.loads(Path(args.train_payload).read_text(encoding="utf-8"))
    result = train_blue_brain_payload(payload)
    Path(args.output_json).write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return 0 if result.get("status") == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
