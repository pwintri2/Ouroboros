"""Automatic safe learning records for cockpit chat turns.

The server-side self-context keeps conversation continuity, but trainer
datasets read from the approved 11D training collection. This module bridges
that gap by storing compact, redacted learning packets for every cockpit turn
and action result without persisting secrets verbatim.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Mapping


MAX_PROMPT_CHARS = 1400
MAX_RESPONSE_CHARS = 2200
MAX_REASON_CHARS = 900
MAX_STEPS = 12
SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|bearer|token|password|passwd|secret|authorization)\s*[:=]\s*['\"]?[^'\"\s,}]+"
)


def store_cockpit_learning_turn(
    *,
    prompt: str,
    result: Mapping[str, Any],
    provider: str,
    model: str,
    conversation_id: str,
) -> dict[str, Any]:
    """Store one redacted cockpit turn as a trainable local 11D record."""

    if not _auto_learning_enabled():
        return {"status": "skipped", "stored": False, "reason": "WINTRIP_COCKPIT_AUTO_LEARNING=0", "fake_success": False}

    payload = _learning_payload(
        prompt=prompt,
        result=result,
        provider=provider,
        model=model,
        conversation_id=conversation_id,
    )
    if not payload["prompt"] and not payload["response"] and not payload["reason"]:
        return {"status": "skipped", "stored": False, "reason": "empty cockpit turn", "fake_success": False}

    document = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
    digest = hashlib.sha256(document.encode("utf-8", errors="replace")).hexdigest()
    metadata = _metadata(payload, digest)

    try:
        stored = _store_training_record(document, metadata)
    except Exception as exc:
        return {"status": "error", "stored": False, "reason": str(exc)[:500], "fake_success": False}

    if stored.get("stored"):
        _wake_continuous_trainer(stored.get("item_id"))
    return {
        **stored,
        "record_type": "cockpit_learning_turn",
        "route": payload["route"],
        "brave_search_used": payload["source_trace"].get("brave_search_used", False),
        "fake_success": False,
    }


def _learning_payload(
    *,
    prompt: str,
    result: Mapping[str, Any],
    provider: str,
    model: str,
    conversation_id: str,
) -> dict[str, Any]:
    source_trace = result.get("source_trace") if isinstance(result.get("source_trace"), Mapping) else {}
    provenance = result.get("provenance") if isinstance(result.get("provenance"), Mapping) else {}
    return {
        "kind": "cockpit_learning_turn",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "conversation_id": _clean(conversation_id, 160),
        "provider": _clean(str(result.get("provider") or provider), 120),
        "model": _clean(str(result.get("model") or model), 160),
        "route": _clean(str(result.get("route") or "unknown"), 120),
        "status": _clean(str(result.get("status") or "unknown"), 80),
        "prompt": _clean(prompt, MAX_PROMPT_CHARS),
        "response": _clean(_response_text(result), MAX_RESPONSE_CHARS),
        "reason": _clean(str(result.get("reason") or result.get("error") or result.get("stderr") or ""), MAX_REASON_CHARS),
        "source_trace": _compact_source_trace(source_trace),
        "provenance": _compact_provenance(provenance),
        "steps": _compact_steps(result.get("steps") or []),
        "learning_rule": (
            "Use this local cockpit outcome as behavioral training: preserve successful routes, "
            "respect approval blocks, use Brave/current context when trace says it was needed, and do not repeat failed tool paths blindly."
        ),
    }


def _metadata(payload: Mapping[str, Any], digest: str) -> dict[str, Any]:
    source_trace = payload.get("source_trace") if isinstance(payload.get("source_trace"), Mapping) else {}
    route = str(payload.get("route") or "unknown")
    dream_hz = _dream_hz(digest)
    return {
        "type": "cockpit_learning_turn",
        "source": "cockpit_chat",
        "source_type": "cockpit_chat",
        "approval_status": "approved",
        "approval_source": "auto_local_cockpit_learning",
        "learnable": True,
        "audit_only": False,
        "trust_level": "local_redacted_cockpit_trace",
        "taint": "local_redacted",
        "route": route,
        "status": str(payload.get("status") or "unknown")[:80],
        "provider": str(payload.get("provider") or "")[:120],
        "model": str(payload.get("model") or "")[:160],
        "conversation_id": str(payload.get("conversation_id") or "")[:160],
        "brave_search_used": bool(source_trace.get("brave_search_used")),
        "brave_search_success": bool(source_trace.get("brave_search_success")),
        "chromadb_search_used": bool(source_trace.get("chromadb_search_used")),
        "memory_status": str(source_trace.get("memory_status") or "not_applicable")[:120],
        "dimension_count": 11,
        "dream_hz": dream_hz,
        "resonance_score": 0.62,
        "content_hash": digest,
        "ingested_at": str(payload.get("created_at") or datetime.now(timezone.utc).isoformat()),
        "d1_physical_body": "cockpit_turn_learning_packet",
        "d2_physical_source": "cockpit_chat",
        "d3_physical_container": "wintrip_training_11d",
        "d4_chronology": str(payload.get("created_at") or ""),
        "d5_persona_actor": "philip",
        "d6_persona_intent": "observe_orient_decide_act_reflect",
        "d7_persona_relation": "wintrip_ouroboros_cockpit_learning",
        "d8_karmic_taint": "local_redacted:auto_learnable",
        "d9_resonance_frequency": f"{dream_hz:.6f}Hz",
        "d10_resonance_score": "0.620000:importance=3.0",
        "d11_field": f"ouroboros_field:cockpit_learning:{route}:{digest[:12]}",
        "fake_success": False,
    }


def _store_training_record(document: str, metadata: dict[str, Any]) -> dict[str, Any]:
    from controller.knowledge_acquisition import store_knowledge_record

    return store_knowledge_record(document, metadata)


def _wake_continuous_trainer(item_id: Any) -> None:
    try:
        from controller.trainer_continuous import notify_learning_record

        notify_learning_record(item_id=str(item_id or ""), source="cockpit_learning")
    except Exception:
        return


def _auto_learning_enabled() -> bool:
    return str(os.getenv("WINTRIP_COCKPIT_AUTO_LEARNING", "1")).strip().lower() not in {"0", "false", "no", "off"}


def _response_text(result: Mapping[str, Any]) -> str:
    for key in ("response", "message", "stdout", "learned", "next_action"):
        value = result.get(key)
        if value:
            return str(value)
    return ""


def _compact_source_trace(trace: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "route",
        "source_kind",
        "model_only",
        "brave_search_used",
        "brave_search_success",
        "subliminal_lookup_used",
        "subliminal_source",
        "chromadb_search_used",
        "chromadb_hit_count",
        "tools_used",
        "tools_executed",
        "tools_blocked",
        "approval_required",
        "action_status",
        "memory_status",
    )
    return {key: _compact_value(trace.get(key)) for key in keys if key in trace}


def _compact_provenance(provenance: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "planner_source",
        "tools_used",
        "planned_tools",
        "blocked_tools",
        "brave_search_used",
        "brave_search_success",
        "memory_status",
        "approval_required",
        "step_count",
    )
    return {key: _compact_value(provenance.get(key)) for key in keys if key in provenance}


def _compact_steps(steps: Any) -> list[dict[str, Any]]:
    if not isinstance(steps, list):
        return []
    compact: list[dict[str, Any]] = []
    for step in steps[:MAX_STEPS]:
        if not isinstance(step, Mapping):
            continue
        validation = step.get("validated") if isinstance(step.get("validated"), Mapping) else {}
        result = step.get("result") if isinstance(step.get("result"), Mapping) else {}
        compact.append(
            {
                "index": step.get("index"),
                "tool": _clean(str(step.get("tool") or "unknown"), 120),
                "status": _clean(str(step.get("status") or "unknown"), 80),
                "reason": _clean(str(step.get("reason") or validation.get("reason") or result.get("reason") or ""), 400),
                "approval_required": bool(validation.get("approval_required") or result.get("approval_required")),
            }
        )
    return compact


def _compact_value(value: Any) -> Any:
    if isinstance(value, bool) or isinstance(value, (int, float)):
        return value
    if isinstance(value, list):
        return [_clean(str(item), 160) for item in value[:12]]
    if isinstance(value, tuple):
        return [_clean(str(item), 160) for item in value[:12]]
    if isinstance(value, Mapping):
        return {str(key)[:80]: _compact_value(item) for key, item in list(value.items())[:16]}
    return _clean(str(value or ""), 300)


def _clean(value: Any, limit: int) -> str:
    text = str(value or "").replace("\x00", " ")
    text = SECRET_RE.sub(lambda match: f"{match.group(1)}=[REDACTED]", text)
    text = re.sub(r"(?i)authorization:\s*bearer\s+[A-Za-z0-9._\\-]+", "authorization: bearer [REDACTED]", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _dream_hz(digest: str) -> float:
    try:
        raw = int(str(digest)[:8], 16)
    except ValueError:
        raw = 0
    return round(418.0 + (raw / 0xFFFFFFFF) * 14.0, 6)
