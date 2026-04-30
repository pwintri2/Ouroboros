"""11D geometry helpers for the Ouroboros field."""

from __future__ import annotations

import math


DIMENSIONS = 11
UNIT_11D_BALL_VOLUME = 64.0 * (math.pi ** 5) / 10395.0
UNIT_11D_BALL_SURFACE = 64.0 * (math.pi ** 5) / 945.0
DEFAULT_MIN_HZ = 418.0
DEFAULT_MAX_HZ = 432.0
DEFAULT_MIN_RADIUS = 1.0
DEFAULT_MAX_RADIUS = 11.0


def bereken_11d_bol(radius: float) -> tuple[float, float]:
    """
    Berekent het volume en de oppervlakte van een 11-dimensionale bol
    op basis van Philip's exacte formule.
    """

    r = float(radius)
    if not math.isfinite(r):
        raise ValueError("radius moet eindig zijn.")
    if r < 0:
        raise ValueError("radius mag niet negatief zijn.")
    volume = UNIT_11D_BALL_VOLUME * (r ** DIMENSIONS)
    oppervlakte = UNIT_11D_BALL_SURFACE * (r ** (DIMENSIONS - 1))
    return volume, oppervlakte


def measure_geometry_11d(value: object) -> dict[str, float | int]:
    """Meet 11D volume/oppervlakte vanuit radius, frequentie of 11D positie."""

    radius = radius_from_value(value)
    volume, oppervlakte = bereken_11d_bol(radius)
    return {
        "dimension_count": DIMENSIONS,
        "radius": radius,
        "volume": volume,
        "oppervlakte": oppervlakte,
        "surface_area": oppervlakte,
    }


def geometry_11d(value: object) -> dict[str, float | int]:
    """Compatibele alias voor de tool-registry."""

    return measure_geometry_11d(value)


def compute_geometry_11d(value: object) -> dict[str, float | int]:
    """Compatibele alias voor de tool-registry."""

    return measure_geometry_11d(value)


def radius_from_value(value: object) -> float:
    """Map een input naar een stabiele 11D-radius."""

    if isinstance(value, (list, tuple)):
        if not value:
            return DEFAULT_MIN_RADIUS
        numbers = [float(item) for item in value]
        if not all(math.isfinite(item) for item in numbers):
            raise ValueError("11D positie bevat geen eindige waarden.")
        rms = math.sqrt(sum(item * item for item in numbers) / len(numbers))
        return _lerp_radius(rms, DEFAULT_MIN_RADIUS, DEFAULT_MAX_RADIUS)

    number = float(value)
    if not math.isfinite(number):
        raise ValueError("waarde moet eindig zijn.")
    if DEFAULT_MIN_HZ <= number <= DEFAULT_MAX_HZ:
        return radius_from_frequency(number)
    if 0.0 <= number <= 1.0:
        return radius_from_autonomy(number)
    if number < 0:
        raise ValueError("radius mag niet negatief zijn.")
    return number


def radius_from_frequency(
    frequency_hz: float,
    band_min_hz: float = DEFAULT_MIN_HZ,
    band_max_hz: float = DEFAULT_MAX_HZ,
    min_radius: float = DEFAULT_MIN_RADIUS,
    max_radius: float = DEFAULT_MAX_RADIUS,
) -> float:
    """Map DreamCycle frequency to a bounded 11D radius."""

    hz = float(frequency_hz)
    low = float(band_min_hz)
    high = float(band_max_hz)
    if high <= low:
        raise ValueError("band_max_hz moet groter zijn dan band_min_hz.")
    return _lerp_radius((hz - low) / (high - low), min_radius, max_radius)


def radius_from_autonomy(
    autonomy: float,
    min_radius: float = DEFAULT_MIN_RADIUS,
    max_radius: float = DEFAULT_MAX_RADIUS,
) -> float:
    """Map autonomy 0..1 to a bounded 11D radius."""

    return _lerp_radius(float(autonomy), min_radius, max_radius)


def _lerp_radius(value: float, min_radius: float, max_radius: float) -> float:
    low = float(min_radius)
    high = float(max_radius)
    if not math.isfinite(value):
        raise ValueError("waarde moet eindig zijn.")
    if high < low:
        raise ValueError("max_radius moet groter dan of gelijk aan min_radius zijn.")
    clamped = max(0.0, min(1.0, value))
    return low + clamped * (high - low)
