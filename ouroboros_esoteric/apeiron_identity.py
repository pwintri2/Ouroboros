"""11D intentieveld voor Ouroboros jobs.

De specificatie spreekt over zettabytes en een 11D-pocket. Technisch betekent
dat hier: een compacte tensor met 11 assen plus metadata die de virtuele schaal
beschrijft. We alloceren bewust geen 11^11 array.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Any

try:
    import numpy as np
except ModuleNotFoundError:
    np = None  # type: ignore[assignment]


DEFAULT_POCKET_SHAPE: tuple[int, ...] = (2,) * 11
DEFAULT_VIRTUAL_SHAPE: tuple[int, ...] = (11,) * 11


@dataclass
class ApeironMetrics:
    coherence: float
    flux: float
    entropy_level: float
    signal_noise_ratio: float
    virtual_zettabytes: float
    data_threshold: int
    dimension_count: int

    def to_dict(self) -> dict[str, float | int]:
        return {
            "coh": round(self.coherence * 100.0, 3),
            "flux": round(self.flux, 6),
            "entropy_level": round(self.entropy_level, 6),
            "signal_noise_ratio": round(self.signal_noise_ratio, 6),
            "virtual_zettabytes": round(self.virtual_zettabytes, 3),
            "data_threshold": self.data_threshold,
            "dimension_count": self.dimension_count,
        }


class ApeironField:
    """Compacte 11D tensor die job-intentie en coherentie meetbaar maakt."""

    def __init__(
        self,
        shape: tuple[int, ...] | None = None,
        *,
        virtual_shape: tuple[int, ...] = DEFAULT_VIRTUAL_SHAPE,
        virtual_size_zb: float = 82.0,
        data_threshold: int = 89,
    ):
        self.shape = tuple(shape or DEFAULT_POCKET_SHAPE)
        if len(self.shape) != 11:
            raise ValueError("ApeironField verwacht exact 11 dimensies.")
        self.virtual_shape = tuple(virtual_shape)
        self.virtual_size_zb = float(virtual_size_zb)
        self.data_threshold = int(data_threshold)
        self.coherence = 1.0
        self.flux = 0.0
        if np is None:
            self.field = _zeros(self.shape)
        else:
            self.field = np.zeros(self.shape, dtype=np.float64)

    def apply_consciousness(self, j_obs: Any, lambda_coupling: float = 0.618) -> None:
        """Pas een intentie-vector toe en herbereken coherentie."""

        if np is None:
            values = _flatten(j_obs)
            target_size = _size(self.shape)
            resized = _resize(values, target_size)
            current = _flatten(self.field)
            updated = [old + value * lambda_coupling for old, value in zip(current, resized)]
            self.field = _reshape(updated, self.shape)
        else:
            vector = np.asarray(j_obs, dtype=np.float64)
            if vector.shape != self.shape:
                vector = np.resize(vector, self.shape)
            self.field = self.field + vector * lambda_coupling
        self._refresh_metrics()

    def inject_text_intention(self, text: str, lambda_coupling: float = 0.618) -> None:
        """Maak deterministisch een 11D intentie-vector uit tekst."""

        self.apply_consciousness(intent_vector_from_text(text, self.shape), lambda_coupling=lambda_coupling)

    def project_to_11d_pocket(self) -> Any:
        """Projecteer het veld naar 11 waarden, een waarde per dimensie."""

        if np is None:
            flat = _flatten(self.field)
            chunk = max(1, len(flat) // 11)
            return [
                sum(flat[index:index + chunk]) / max(1, len(flat[index:index + chunk]))
                for index in range(0, min(len(flat), chunk * 11), chunk)
            ][:11]
        axes = tuple(range(1, self.field.ndim))
        base = np.mean(self.field, axis=axes)
        return np.resize(base, 11)

    def metrics(self) -> ApeironMetrics:
        self._refresh_metrics()
        entropy = _std(self.field)
        snr = 1.0 / (entropy + 1e-8)
        return ApeironMetrics(
            coherence=self.coherence,
            flux=self.flux,
            entropy_level=entropy,
            signal_noise_ratio=snr,
            virtual_zettabytes=self.virtual_size_zb,
            data_threshold=self.data_threshold,
            dimension_count=len(self.shape),
        )

    def _refresh_metrics(self) -> None:
        entropy = _std(self.field)
        mean_abs = _mean_abs(self.field)
        self.flux = mean_abs
        self.coherence = max(0.0, min(1.0, 1.0 - entropy * 0.1))


def intent_vector_from_text(text: str, shape: tuple[int, ...] = DEFAULT_POCKET_SHAPE) -> Any:
    """Deterministische compacte intentie-vector uit prompt/jobtekst."""

    digest = hashlib.sha256(str(text or "").encode("utf-8")).digest()
    total = _size(shape)
    values = [((digest[index % len(digest)] / 255.0) * 2.0) - 1.0 for index in range(total)]
    if np is None:
        return _reshape(values, shape)
    return np.asarray(values, dtype=np.float64).reshape(shape)


def _size(shape: tuple[int, ...]) -> int:
    total = 1
    for value in shape:
        total *= int(value)
    return total


def _zeros(shape: tuple[int, ...]) -> Any:
    return _reshape([0.0] * _size(shape), shape)


def _flatten(value: Any) -> list[float]:
    if np is not None and isinstance(value, np.ndarray):
        return [0.0 if math.isnan(float(item)) else float(item) for item in value.ravel()]
    if isinstance(value, (int, float)):
        number = float(value)
        return [0.0 if math.isnan(number) else number]
    if isinstance(value, list) or isinstance(value, tuple):
        out: list[float] = []
        for item in value:
            out.extend(_flatten(item))
        return out
    return [0.0]


def _reshape(values: list[float], shape: tuple[int, ...]) -> Any:
    if not shape:
        return values[0] if values else 0.0
    step = _size(shape[1:])
    return [_reshape(values[index:index + step], shape[1:]) for index in range(0, len(values), step)]


def _resize(values: list[float], total: int) -> list[float]:
    if not values:
        return [0.0] * total
    return [values[index % len(values)] for index in range(total)]


def _std(value: Any) -> float:
    if np is not None and isinstance(value, np.ndarray):
        return float(np.std(value))
    flat = _flatten(value)
    if not flat:
        return 0.0
    mean = sum(flat) / len(flat)
    return math.sqrt(sum((item - mean) ** 2 for item in flat) / len(flat))


def _mean_abs(value: Any) -> float:
    if np is not None and isinstance(value, np.ndarray):
        return float(np.mean(np.abs(value)))
    flat = _flatten(value)
    return sum(abs(item) for item in flat) / max(1, len(flat))
