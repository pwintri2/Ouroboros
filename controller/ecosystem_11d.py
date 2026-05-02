"""Shared 11D ecosystem helpers for Ouroboros adapters.

Purpose:
    Provide a small common schema for OS, crawler and cloud adapter records.
Inputs:
    Local metadata dictionaries, short summaries and numeric safety/health
    signals. No credentials or raw host secrets should be passed in.
Outputs:
    Deterministic 11D vectors, content hashes and redacted text snippets.
Safety notes:
    This module never calls external services and never executes commands. It
    only normalizes already-collected metadata.
Akkoord requirements:
    None here. Callers must enforce Akkoord before collecting or mutating data.

Why this change:
    The deep ecosystem plan needs Pop!_OS, Google, Microsoft, SharePoint and
    crawler records to share one auditable 11D shape instead of inventing a
    different vector per adapter.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any


ECOSYSTEM_11D_DIMENSIONS: tuple[str, ...] = (
    "thermal_load",
    "power_pressure",
    "memory_pressure",
    "storage_pressure",
    "driver_or_api_health",
    "network_pressure",
    "identity_or_auth_state",
    "permission_complexity",
    "freshness",
    "importance",
    "safety_risk",
)

SENSITIVE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)(access_token|refresh_token|id_token|api[_-]?key|secret|password|passwd|pwd)\s*[:=]\s*['\"]?[^'\"\s,;}]+"),
    re.compile(r"(?i)(authorization:\s*bearer\s+)[A-Za-z0-9._~+/\-=]+"),
    re.compile(r"(?i)(client_secret\s*[:=]\s*)['\"]?[^'\"\s,;}]+"),
    re.compile(r"(?i)(private_key\s*[:=]\s*)['\"]?[^'\"\n]+"),
)


def clamp01(value: Any, default: float = 0.0) -> float:
    """Return a finite float constrained to the 0..1 range."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(default)
    if number != number:
        number = float(default)
    return round(max(0.0, min(1.0, number)), 6)


def ecosystem_vector(signals: dict[str, Any] | None = None) -> list[float]:
    """Map named signals onto the canonical 11D ecosystem vector."""
    signals = signals or {}
    return [clamp01(signals.get(name, 0.0)) for name in ECOSYSTEM_11D_DIMENSIONS]


def content_hash(value: Any) -> str:
    """Hash a JSON-ish value without storing raw content in status payloads."""
    if isinstance(value, bytes):
        payload = value
    else:
        payload = json.dumps(value, sort_keys=True, default=str, ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def redact_sensitive_text(text: str, max_chars: int = 12000) -> str:
    """Redact common credential shapes and bound the returned text."""
    cleaned = str(text or "")
    for pattern in SENSITIVE_PATTERNS:
        cleaned = pattern.sub(lambda match: _redaction(match.group(0)), cleaned)
    if len(cleaned) > max_chars:
        return cleaned[: max_chars // 2] + "\n...[truncated]...\n" + cleaned[-max_chars // 2 :]
    return cleaned


def build_11d_record(
    *,
    source: str,
    record_type: str,
    title: str,
    summary: str,
    signals: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create one auditable 11D ecosystem record."""
    safe_summary = redact_sensitive_text(summary, max_chars=4000)
    safe_metadata = _redact_mapping(metadata or {})
    vector = ecosystem_vector(signals or {})
    return {
        "source": source,
        "record_type": record_type,
        "title": str(title)[:240],
        "summary": safe_summary,
        "metadata": safe_metadata,
        "11d": {
            "dimensions": list(ECOSYSTEM_11D_DIMENSIONS),
            "vector": vector,
            "dimension_count": len(vector),
        },
        "content_hash": content_hash({"source": source, "title": title, "summary": safe_summary, "metadata": safe_metadata}),
        "created_at": datetime.utcnow().isoformat(),
        "fake_success": False,
    }


def _redaction(value: str) -> str:
    prefix = value.split("=", 1)[0].split(":", 1)[0]
    return f"{prefix}=<redacted>"


def _redact_mapping(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if any(marker in str(key).lower() for marker in ("token", "secret", "password", "passwd", "api_key", "apikey", "private_key")):
                result[str(key)] = "<redacted>"
            else:
                result[str(key)] = _redact_mapping(item)
        return result
    if isinstance(value, list):
        return [_redact_mapping(item) for item in value[:200]]
    if isinstance(value, str):
        return redact_sensitive_text(value, max_chars=2000)
    return value
