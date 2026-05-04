"""Entropy/SNR monitor voor agent-runtime en de 11D-pocket."""

from __future__ import annotations

import math
from typing import Any

try:
    import numpy as np
except ModuleNotFoundError:
    np = None  # type: ignore[assignment]

from ouroboros_esoteric.light_language import LightLanguageCompiler


class EntropyMonitor:
    """Meet entropy, SNR en voert optionele 528Hz healing uit."""

    def __init__(self, *, entropy_threshold: float = 0.7):
        self.entropy_threshold = float(entropy_threshold)
        self.compiler = LightLanguageCompiler()

    def measure(self, job_data: Any, *, input_frequency: float = 528.0) -> dict[str, Any]:
        entropy = _std(job_data)
        snr = 1.0 / (entropy + 1e-8)
        result: dict[str, Any] = {
            "entropy_level": round(entropy, 6),
            "signal_noise_ratio": round(snr, 6),
            "threshold": self.entropy_threshold,
            "healed": False,
            "coherence": round(max(0.0, min(1.0, 1.0 - entropy * 0.1)), 6),
        }
        if entropy > self.entropy_threshold:
            check = self.compiler.coherence_check(
                job_data,
                input_frequency=input_frequency,
                entropy_level=entropy,
                entropy_threshold=self.entropy_threshold,
            )
            result["healed"] = bool(check.get("healed"))
            result["resonance_status"] = check.get("status")
            if "payload" in check:
                result["data"] = check["payload"]
        return result


def measure_entropy(job_data: Any, *, input_frequency: float = 528.0) -> dict[str, Any]:
    return EntropyMonitor().measure(job_data, input_frequency=input_frequency)


def _flatten(value: Any) -> list[float]:
    if np is not None and isinstance(value, np.ndarray):
        return [0.0 if math.isnan(float(item)) else float(item) for item in value.ravel()]
    if isinstance(value, (int, float)):
        number = float(value)
        return [0.0 if math.isnan(number) else number]
    if isinstance(value, dict):
        out: list[float] = []
        for item in value.values():
            out.extend(_flatten(item))
        return out
    if isinstance(value, (list, tuple)):
        out: list[float] = []
        for item in value:
            out.extend(_flatten(item))
        return out
    text = str(value or "")
    return [ord(char) / 255.0 for char in text[:2048]]


def _std(value: Any) -> float:
    if np is not None and isinstance(value, np.ndarray):
        return float(np.std(value))
    flat = _flatten(value)
    if not flat:
        return 0.0
    mean = sum(flat) / len(flat)
    return math.sqrt(sum((item - mean) ** 2 for item in flat) / len(flat))
