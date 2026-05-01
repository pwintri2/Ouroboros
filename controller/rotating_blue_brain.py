"""Rotating 11D Blue Brain trainer.

This module explores the Blue Brain feature pocket by applying a fresh
orthogonal rotation to the 11 e-type feature space on every bounded tick.
It keeps persistent state in ``.secrets`` and writes the best observed model
under ``out/blue_brain_rotating``.
"""

from __future__ import annotations

import importlib.util
import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from controller.blue_brain_adapter import CLASS_NAMES, E_TYPES, generate_dataset


APPROVAL_PHRASE = "Akkoord"
REQUIRED_PACKAGES = ("numpy", "sklearn", "joblib")
_STATE_LOCK = threading.Lock()
_WORKER_THREAD: threading.Thread | None = None
_WORKER_STOP = threading.Event()


def _workspace_root() -> Path:
    configured = os.getenv("WINTRIP_WORKSPACE") or os.getenv("WORKSPACE_ROOT") or "/workspace"
    root = Path(configured)
    if not root.exists():
        root = Path(os.getenv("WINTRIP_PROJECT_ROOT") or Path.cwd())
    return root.resolve()


def rotating_state_path() -> Path:
    return (_workspace_root() / ".secrets" / "rotating_blue_brain.json").resolve()


def rotating_output_dir() -> Path:
    return (_workspace_root() / "out" / "blue_brain_rotating").resolve()


def _dependency_map() -> dict[str, bool]:
    return {name: importlib.util.find_spec(name) is not None for name in REQUIRED_PACKAGES}


def dependencies_ready() -> bool:
    return all(_dependency_map().values())


def detect_cpu_clock_hz() -> float:
    """Best-effort CPU clock probe used to drive virtual 11D rotation cadence."""
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.exists():
        try:
            for line in cpuinfo.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.lower().startswith("cpu mhz") and ":" in line:
                    mhz = float(line.split(":", 1)[1].strip())
                    if mhz > 0:
                        return mhz * 1_000_000.0
        except Exception:
            pass
    return 1_000_000_000.0


def generate_rotation_matrix(dim: int = 11, random_state: int | None = None) -> Any:
    """Generate a proper orthogonal rotation matrix using NumPy QR decomposition."""
    if dim < 2:
        raise ValueError("dim must be at least 2")

    import numpy as np

    rng = np.random.default_rng(random_state)
    raw = rng.normal(size=(dim, dim))
    q_matrix, r_matrix = np.linalg.qr(raw)
    signs = np.sign(np.diag(r_matrix))
    signs[signs == 0] = 1
    q_matrix = q_matrix * signs
    if np.linalg.det(q_matrix) < 0:
        q_matrix[:, 0] *= -1
    return q_matrix


def apply_rotation(X: Any, rotation_matrix: Any) -> Any:
    """Apply an orthogonal rotation to a feature matrix while preserving shape."""
    import numpy as np

    x_array = np.asarray(X)
    r_array = np.asarray(rotation_matrix)
    if x_array.ndim != 2:
        raise ValueError("X must be a 2D feature matrix")
    if r_array.shape != (x_array.shape[1], x_array.shape[1]):
        raise ValueError("rotation_matrix must be square and match X feature count")
    return x_array @ r_array


def advance_rotation_clock(
    rotation_matrix: Any | None,
    start_index: int,
    rotation_count: int,
    dim: int = 11,
) -> Any:
    """Advance an orthogonal matrix with fast deterministic Givens rotations."""
    import numpy as np

    if rotation_count < 1:
        return _matrix_from_state(rotation_matrix, dim)
    matrix = _matrix_from_state(rotation_matrix, dim)
    base_angle = (2 * np.pi) / 4096.0
    for offset in range(int(rotation_count)):
        tick = int(start_index) + offset
        axis_a = tick % dim
        axis_b = (tick * 7 + 3) % dim
        if axis_a == axis_b:
            axis_b = (axis_b + 1) % dim
        angle = base_angle * (1.0 + ((tick % 17) / 64.0))
        c_value = float(np.cos(angle))
        s_value = float(np.sin(angle))
        col_a = matrix[:, axis_a].copy()
        col_b = matrix[:, axis_b].copy()
        matrix[:, axis_a] = c_value * col_a - s_value * col_b
        matrix[:, axis_b] = s_value * col_a + c_value * col_b

    q_matrix, r_matrix = np.linalg.qr(matrix)
    signs = np.sign(np.diag(r_matrix))
    signs[signs == 0] = 1
    q_matrix = q_matrix * signs
    if np.linalg.det(q_matrix) < 0:
        q_matrix[:, 0] *= -1
    return q_matrix


class TrainingObserver:
    """Track rotating trainer metrics and adjust hyperparameters conservatively."""

    def __init__(
        self,
        history: list[dict[str, Any]] | None = None,
        target_accuracy: float = 0.9,
        target_f1: float = 0.9,
        low_window: int = 3,
    ) -> None:
        self.history = list(history or [])
        self.target_accuracy = float(target_accuracy)
        self.target_f1 = float(target_f1)
        self.low_window = max(1, int(low_window))

    def evaluate(self, metrics: dict[str, Any], hyperparams: dict[str, Any]) -> dict[str, Any]:
        """Store metrics and return updated hyperparameters plus adjustment notes."""
        updated = dict(hyperparams)
        accuracy = float(metrics.get("accuracy", 0.0))
        macro_f1 = float(metrics.get("macro_f1", 0.0))
        train_accuracy = float(metrics.get("train_accuracy", accuracy))
        event = {
            "timestamp": datetime.utcnow().isoformat(),
            "rotation_index": int(metrics.get("rotation_index", len(self.history) + 1)),
            "accuracy": accuracy,
            "macro_f1": macro_f1,
            "train_accuracy": train_accuracy,
            "adjustments": [],
        }
        self.history.append(event)

        recent = self.history[-self.low_window :]
        if len(recent) >= self.low_window and all(
            item.get("accuracy", 0.0) < self.target_accuracy or item.get("macro_f1", 0.0) < self.target_f1
            for item in recent
        ):
            current_estimators = int(updated.get("n_estimators", 120))
            next_estimators = min(current_estimators + 25, 1000)
            if next_estimators != current_estimators:
                updated["n_estimators"] = next_estimators
                event["adjustments"].append(
                    {
                        "field": "n_estimators",
                        "from": current_estimators,
                        "to": next_estimators,
                        "reason": "recent accuracy/F1 below target",
                    }
                )

        overfit_gap = train_accuracy - accuracy
        max_depth = updated.get("max_depth")
        if max_depth is not None and overfit_gap > 0.12 and int(max_depth) > 4:
            next_depth = max(4, int(max_depth) - 1)
            if next_depth != int(max_depth):
                updated["max_depth"] = next_depth
                event["adjustments"].append(
                    {
                        "field": "max_depth",
                        "from": int(max_depth),
                        "to": next_depth,
                        "reason": "train/test gap suggests overfit",
                    }
                )

        event["next_hyperparams"] = dict(updated)
        return {"hyperparams": updated, "event": event, "history": self.history[-50:]}


def train_rotated_model(
    X: Any,
    y: Any,
    hyperparams: dict[str, Any],
    rotation_index: int,
) -> tuple[Any, dict[str, Any]]:
    """Train a classifier on rotated features and return JSON-safe metrics."""
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import accuracy_score, classification_report, f1_score
    from sklearn.model_selection import train_test_split

    params = _normalize_hyperparams(hyperparams)
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
    train_pred = model.predict(X_train)
    accuracy = float(accuracy_score(y_test, y_pred))
    train_accuracy = float(accuracy_score(y_train, train_pred))
    macro_f1 = float(f1_score(y_test, y_pred, average="macro", zero_division=0))
    metrics = {
        "rotation_index": int(rotation_index),
        "timestamp": datetime.utcnow().isoformat(),
        "accuracy": accuracy,
        "macro_f1": macro_f1,
        "train_accuracy": train_accuracy,
        "classification_report": _jsonable(
            classification_report(y_test, y_pred, target_names=CLASS_NAMES, output_dict=True, zero_division=0)
        ),
        "train_samples": int(len(y_train)),
        "test_samples": int(len(y_test)),
        "hyperparams": params,
    }
    return model, metrics


def load_rotating_state() -> dict[str, Any]:
    path = rotating_state_path()
    state = _default_state()
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                state.update(loaded)
        except Exception:
            state["last_error"] = "Rotating Blue Brain state could not be read."
    state["hyperparams"] = _normalize_hyperparams(state.get("hyperparams"))
    return state


def save_rotating_state(state: dict[str, Any]) -> None:
    path = rotating_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.utcnow().isoformat()
    state["hyperparams"] = _normalize_hyperparams(state.get("hyperparams"))
    path.write_text(json.dumps(_jsonable(state), indent=2, sort_keys=True), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def get_rotating_status() -> dict[str, Any]:
    state = load_rotating_state()
    cpu_clock_hz = detect_cpu_clock_hz()
    state.update(
        {
            "dependencies": _dependency_map(),
            "dependency_status": "online" if dependencies_ready() else "missing_dependencies",
            "thread_alive": bool(_WORKER_THREAD and _WORKER_THREAD.is_alive()),
            "state_path": str(rotating_state_path()),
            "output_dir": str(rotating_output_dir()),
            "feature_count": len(E_TYPES),
            "features": list(E_TYPES),
            "cpu_clock_hz": cpu_clock_hz,
            "cpu_clock_ghz": round(cpu_clock_hz / 1_000_000_000.0, 4),
            "target_rotation_hz": _target_rotation_hz(state, cpu_clock_hz),
        }
    )
    return state


def start_rotating_training(approval: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    if approval != APPROVAL_PHRASE:
        return {"status": "blocked", "reason": "Approval phrase must be 'Akkoord'"}

    config = dict(config or {})
    with _STATE_LOCK:
        state = load_rotating_state()
        state["enabled"] = True
        state["status"] = "running"
        state["n_samples"] = _clamp_int(config.get("n_samples", state.get("n_samples", 1000)), 100, 200_000)
        state["interval_seconds"] = _clamp_float(config.get("interval_seconds", state.get("interval_seconds", 120)), 0.0, 86_400.0)
        state["cpu_clock_mode"] = bool(config.get("cpu_clock_mode", state.get("cpu_clock_mode", False)))
        state["clock_divisor"] = _clamp_int(config.get("clock_divisor", state.get("clock_divisor", 100_000)), 1, 1_000_000_000)
        state["max_rotation_hz"] = _clamp_int(config.get("max_rotation_hz", state.get("max_rotation_hz", 20_000)), 1, 2_000_000)
        state["train_every_rotations"] = _clamp_int(
            config.get("train_every_rotations", state.get("train_every_rotations", 10_000)),
            1,
            10_000_000,
        )
        state["clock_burst_seconds"] = _clamp_float(
            config.get("clock_burst_seconds", state.get("clock_burst_seconds", 0.05)),
            0.001,
            1.0,
        )
        state["min_worker_sleep_seconds"] = _clamp_float(
            config.get("min_worker_sleep_seconds", state.get("min_worker_sleep_seconds", 0.005)),
            0.0,
            1.0,
        )
        state["max_rotations"] = _clamp_int(config.get("max_rotations", state.get("max_rotations", 0)), 0, 1_000_000_000)
        state["target_accuracy"] = _clamp_float(config.get("target_accuracy", state.get("target_accuracy", 0.9)), 0.0, 1.0)
        state["target_f1"] = _clamp_float(config.get("target_f1", state.get("target_f1", 0.9)), 0.0, 1.0)
        state["hyperparams"] = _normalize_hyperparams({**state.get("hyperparams", {}), **(config.get("hyperparams") or {})})
        _event(state, "rotating_start", "Rotating Blue Brain trainer started.")
        save_rotating_state(state)

    _ensure_worker()
    result = get_rotating_status()
    if config.get("run_immediately"):
        result["tick"] = run_rotation_tick(force=True)
    return result


def stop_rotating_training(approval: str) -> dict[str, Any]:
    if approval != APPROVAL_PHRASE:
        return {"status": "blocked", "reason": "Approval phrase must be 'Akkoord'"}

    with _STATE_LOCK:
        state = load_rotating_state()
        state["enabled"] = False
        state["status"] = "stopped"
        _event(state, "rotating_stop", "Rotating Blue Brain trainer stopped.")
        save_rotating_state(state)
    _WORKER_STOP.set()
    return get_rotating_status()


def run_rotation_tick(force: bool = False) -> dict[str, Any]:
    """Run one bounded rotation/training tick."""
    with _STATE_LOCK:
        state = load_rotating_state()
        if not force and not state.get("enabled"):
            state["status"] = "stopped"
            save_rotating_state(state)
            return {"status": "idle", "reason": "Rotating Blue Brain trainer is stopped.", "state": state}
        snapshot = dict(state)

    if not dependencies_ready():
        with _STATE_LOCK:
            state = load_rotating_state()
            state["status"] = "error"
            state["last_error"] = "Rotating Blue Brain dependencies are missing."
            _event(state, "dependency_error", state["last_error"], {"dependencies": _dependency_map()})
            save_rotating_state(state)
        return {"status": "error", "reason": "Rotating Blue Brain dependencies are missing.", "dependencies": _dependency_map()}

    try:
        rotation_index = int(snapshot.get("rotation_count") or 0) + 1
        random_state = int(snapshot.get("hyperparams", {}).get("random_state", 42)) + rotation_index
        n_samples = int(snapshot.get("n_samples") or 1000)
        X, y = generate_dataset(n_samples=n_samples, n_features=len(E_TYPES), random_state=random_state)
        if snapshot.get("cpu_clock_mode") and snapshot.get("last_rotation_matrix"):
            rotation_matrix = _matrix_from_state(snapshot.get("last_rotation_matrix"), len(E_TYPES))
        else:
            rotation_matrix = generate_rotation_matrix(dim=len(E_TYPES), random_state=random_state + 10_000)
        X_rotated = apply_rotation(X, rotation_matrix)
        model, metrics = train_rotated_model(
            X_rotated,
            y,
            snapshot.get("hyperparams", {}),
            rotation_index=rotation_index,
        )
        projection = project_to_2d(X_rotated, y, limit=80, random_state=random_state + 20_000)
        observer = TrainingObserver(
            history=snapshot.get("observer_history") or [],
            target_accuracy=float(snapshot.get("target_accuracy", 0.9)),
            target_f1=float(snapshot.get("target_f1", 0.9)),
        )
        observed = observer.evaluate(metrics, snapshot.get("hyperparams", {}))
        best_score = float(snapshot.get("best_score") or 0.0)
        score = (float(metrics["accuracy"]) + float(metrics["macro_f1"])) / 2
        saved = None
        if score >= best_score:
            saved = _save_best_artifacts(model, metrics, rotation_matrix, projection)
    except Exception as exc:
        with _STATE_LOCK:
            state = load_rotating_state()
            state["status"] = "error"
            state["last_error"] = f"Rotating Blue Brain tick failed: {exc}"
            _event(state, "tick_error", state["last_error"])
            save_rotating_state(state)
        return {"status": "error", "reason": f"Rotating Blue Brain tick failed: {exc}"}

    with _STATE_LOCK:
        state = load_rotating_state()
        state["status"] = "running" if state.get("enabled") else "dataset_ready"
        state["rotation_count"] = rotation_index
        state["training_rotation_count"] = int(state.get("training_rotation_count") or 0) + 1
        state["last_training_rotation_count"] = rotation_index
        state["last_tick_at"] = datetime.utcnow().isoformat()
        state["last_error"] = ""
        state["last_metrics"] = metrics
        state["last_projection"] = projection
        state["last_rotation_matrix"] = _rounded_matrix(rotation_matrix)
        state["hyperparams"] = observed["hyperparams"]
        state["observer_history"] = observed["history"]
        if saved:
            state["best_score"] = score
            state["best_accuracy"] = float(metrics["accuracy"])
            state["best_macro_f1"] = float(metrics["macro_f1"])
            state["best_model_path"] = saved["model_path"]
            state["best_metrics_path"] = saved["metrics_path"]
        _event(state, "rotation_tick", f"Rotation {rotation_index} accuracy={metrics['accuracy']:.4f}", {"metrics": metrics})
        max_rotations = int(state.get("max_rotations") or 0)
        if state.get("enabled") and max_rotations > 0 and rotation_index >= max_rotations:
            state["enabled"] = False
            state["status"] = "completed"
            _event(state, "rotating_completed", f"Reached max_rotations={max_rotations}.")
            _WORKER_STOP.set()
        save_rotating_state(state)
        return {
            "status": "success",
            "rotation_index": rotation_index,
            "metrics": metrics,
            "observer_event": observed["event"],
            "best_model_path": state.get("best_model_path"),
            "state": state,
        }


def run_clock_rotation_burst(force: bool = False) -> dict[str, Any]:
    """Run one lightweight CPU-clock-derived rotation burst without model training."""
    with _STATE_LOCK:
        state = load_rotating_state()
        if not force and not state.get("enabled"):
            state["status"] = "stopped"
            save_rotating_state(state)
            return {"status": "idle", "reason": "Rotating Blue Brain trainer is stopped.", "state": state}
        snapshot = dict(state)

    if not dependencies_ready():
        return {"status": "error", "reason": "Rotating Blue Brain dependencies are missing.", "dependencies": _dependency_map()}

    cpu_clock_hz = detect_cpu_clock_hz()
    target_hz = _target_rotation_hz(snapshot, cpu_clock_hz)
    burst_seconds = _clamp_float(snapshot.get("clock_burst_seconds", 0.05), 0.001, 1.0)
    burst_size = _clamp_int(round(target_hz * burst_seconds), 1, 100_000)
    start_index = int(snapshot.get("rotation_count") or 0)
    started = time.perf_counter()
    try:
        rotation_matrix = advance_rotation_clock(
            snapshot.get("last_rotation_matrix"),
            start_index=start_index,
            rotation_count=burst_size,
            dim=len(E_TYPES),
        )
    except Exception as exc:
        with _STATE_LOCK:
            state = load_rotating_state()
            state["status"] = "error"
            state["last_error"] = f"Clock rotation burst failed: {exc}"
            _event(state, "clock_burst_error", state["last_error"])
            save_rotating_state(state)
        return {"status": "error", "reason": f"Clock rotation burst failed: {exc}"}

    elapsed = max(time.perf_counter() - started, 0.000001)
    measured_hz = burst_size / elapsed
    with _STATE_LOCK:
        state = load_rotating_state()
        state["status"] = "running" if state.get("enabled") else "dataset_ready"
        state["rotation_count"] = int(state.get("rotation_count") or 0) + burst_size
        state["last_rotation_matrix"] = _rounded_matrix(rotation_matrix)
        state["last_clock_at"] = datetime.utcnow().isoformat()
        state["cpu_clock_hz"] = cpu_clock_hz
        state["target_rotation_hz"] = target_hz
        state["clock_rotation_hz"] = round(float(measured_hz), 3)
        state["clock_last_burst_size"] = burst_size
        state["last_error"] = ""
        max_rotations = int(state.get("max_rotations") or 0)
        if state.get("enabled") and max_rotations > 0 and state["rotation_count"] >= max_rotations:
            state["enabled"] = False
            state["status"] = "completed"
            _event(state, "rotating_completed", f"Reached max_rotations={max_rotations}.")
            _WORKER_STOP.set()
        save_rotating_state(state)
        return {
            "status": "success",
            "burst_size": burst_size,
            "rotation_count": state["rotation_count"],
            "cpu_clock_hz": cpu_clock_hz,
            "target_rotation_hz": target_hz,
            "clock_rotation_hz": state["clock_rotation_hz"],
            "state": state,
        }


def project_to_2d(X: Any, y: Any, limit: int = 80, random_state: int | None = None) -> list[dict[str, Any]]:
    """Return a compact PCA projection sample for UI visualization."""
    import numpy as np
    from sklearn.decomposition import PCA

    x_array = np.asarray(X)
    y_array = np.asarray(y)
    sample_count = min(int(limit), len(x_array))
    rng = np.random.default_rng(random_state)
    indexes = rng.choice(len(x_array), size=sample_count, replace=False) if sample_count < len(x_array) else np.arange(len(x_array))
    projected = PCA(n_components=2, random_state=random_state).fit_transform(x_array[indexes])
    return [
        {
            "x": round(float(point[0]), 6),
            "y": round(float(point[1]), 6),
            "label": int(label),
        }
        for point, label in zip(projected, y_array[indexes])
    ]


def _ensure_worker() -> None:
    global _WORKER_THREAD
    if _WORKER_THREAD and _WORKER_THREAD.is_alive():
        return
    _WORKER_STOP.clear()
    _WORKER_THREAD = threading.Thread(target=_worker_loop, name="wintrip-rotating-blue-brain", daemon=True)
    _WORKER_THREAD.start()


def _worker_loop() -> None:
    while not _WORKER_STOP.is_set():
        state = load_rotating_state()
        if not state.get("enabled"):
            _WORKER_STOP.wait(5)
            continue
        if state.get("cpu_clock_mode"):
            burst = run_clock_rotation_burst(force=True)
            state = load_rotating_state()
            rotations_since_training = int(state.get("rotation_count") or 0) - int(state.get("last_training_rotation_count") or 0)
            if burst.get("status") == "success" and rotations_since_training >= int(state.get("train_every_rotations") or 10_000):
                run_rotation_tick(force=True)
                state = load_rotating_state()
            target_hz = float(state.get("target_rotation_hz") or _target_rotation_hz(state, detect_cpu_clock_hz()))
            burst_size = int(state.get("clock_last_burst_size") or 1)
            target_sleep = max(0.0, (burst_size / max(target_hz, 1.0)) - 0.001)
            sleep_seconds = max(float(state.get("min_worker_sleep_seconds") or 0.0), target_sleep)
            _WORKER_STOP.wait(min(sleep_seconds, 1.0))
        else:
            run_rotation_tick(force=True)
            state = load_rotating_state()
            _WORKER_STOP.wait(float(state.get("interval_seconds") or 120.0))


def _default_state() -> dict[str, Any]:
    return {
        "enabled": False,
        "status": "idle",
        "n_samples": 1000,
        "interval_seconds": 120,
        "cpu_clock_mode": False,
        "clock_divisor": 100_000,
        "max_rotation_hz": 20_000,
        "target_rotation_hz": 0.0,
        "clock_rotation_hz": 0.0,
        "clock_last_burst_size": 0,
        "clock_burst_seconds": 0.05,
        "min_worker_sleep_seconds": 0.005,
        "train_every_rotations": 10_000,
        "max_rotations": 0,
        "target_accuracy": 0.9,
        "target_f1": 0.9,
        "rotation_count": 0,
        "training_rotation_count": 0,
        "last_training_rotation_count": 0,
        "hyperparams": _normalize_hyperparams({}),
        "best_score": 0.0,
        "best_accuracy": 0.0,
        "best_macro_f1": 0.0,
        "best_model_path": None,
        "best_metrics_path": None,
        "last_metrics": None,
        "last_projection": [],
        "last_rotation_matrix": [],
        "last_tick_at": None,
        "last_error": "",
        "observer_history": [],
        "events": [],
    }


def _normalize_hyperparams(value: dict[str, Any] | None) -> dict[str, Any]:
    params = {
        "n_estimators": 120,
        "max_depth": 12,
        "random_state": 42,
        "test_size": 0.2,
        "n_jobs": -1,
    }
    if value is not None:
        params.update(value)
    params["n_estimators"] = _clamp_int(params.get("n_estimators", 120), 10, 2000)
    max_depth = params.get("max_depth", 12)
    params["max_depth"] = None if max_depth in (None, "", "none") else _clamp_int(max_depth, 1, 100)
    params["random_state"] = _clamp_int(params.get("random_state", 42), 0, 1_000_000)
    params["test_size"] = _clamp_float(params.get("test_size", 0.2), 0.05, 0.5)
    params["n_jobs"] = _clamp_int(params.get("n_jobs", -1), -1, 64)
    return params


def _save_best_artifacts(model: Any, metrics: dict[str, Any], rotation_matrix: Any, projection: list[dict[str, Any]]) -> dict[str, str]:
    import joblib

    out_dir = rotating_output_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    model_path = out_dir / "rotating_blue_best.joblib"
    metrics_path = out_dir / "rotating_blue_best_metrics.json"
    payload = {
        "model": model,
        "metrics": metrics,
        "rotation_matrix": _rounded_matrix(rotation_matrix, digits=10),
        "projection": projection,
        "feature_names": list(E_TYPES),
        "class_names": list(CLASS_NAMES),
        "saved_at": datetime.utcnow().isoformat(),
    }
    joblib.dump(payload, model_path)
    metrics_path.write_text(json.dumps(_jsonable(payload | {"model": "<joblib-payload>"}), indent=2, sort_keys=True), encoding="utf-8")
    return {"model_path": str(model_path), "metrics_path": str(metrics_path)}


def _matrix_from_state(value: Any, dim: int) -> Any:
    import numpy as np

    if value:
        matrix = np.asarray(value, dtype=float)
        if matrix.shape == (dim, dim):
            return matrix
    return np.eye(dim)


def _target_rotation_hz(state: dict[str, Any], cpu_clock_hz: float | None = None) -> float:
    clock_hz = float(cpu_clock_hz if cpu_clock_hz is not None else detect_cpu_clock_hz())
    divisor = max(1, int(state.get("clock_divisor") or 100_000))
    cap = max(1, int(state.get("max_rotation_hz") or 20_000))
    return float(min(clock_hz / divisor, cap))


def _rounded_matrix(matrix: Any, digits: int = 6) -> list[list[float]]:
    return [[round(float(value), digits) for value in row] for row in matrix]


def _event(state: dict[str, Any], event_type: str, message: str, data: dict[str, Any] | None = None) -> None:
    events = list(state.get("events") or [])
    events.append(
        {
            "timestamp": datetime.utcnow().isoformat(),
            "type": event_type,
            "message": message,
            "data": data or {},
        }
    )
    state["events"] = events[-50:]


def _clamp_int(value: Any, minimum: int, maximum: int) -> int:
    return max(minimum, min(int(value), maximum))


def _clamp_float(value: Any, minimum: float, maximum: float) -> float:
    return max(minimum, min(float(value), maximum))


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    try:
        import numpy as np

        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, np.generic):
            return value.item()
    except Exception:
        pass
    return value
