"""Traceable ecosystem knowledge-list ingestion for Ouroboros.

Purpose:
    Parse OUROBOROS_KENNIS_LIJST.md into curriculum-aligned, 11D ecosystem
    records that can feed trainer/crawler status and later Chroma ingestion.
Inputs:
    A local Markdown path and exact Akkoord when writing state/artifacts.
Outputs:
    Parsed sections, topic records, curriculum labels, 11D vectors and JSONL
    artifacts under artifacts/ecosystem_knowledge/.
Safety notes:
    This module reads a local Markdown file only. It performs no browser calls,
    no model calls and no external API calls. It stores summaries, not secrets.
Akkoord requirements:
    ingest_ecosystem_knowledge() requires approval == "Akkoord" because it
    writes artifacts and state.

Why this change:
    The buildplan calls for a maintainable path from the knowledge list into
    visible ecosystem curricula and 11D records, without relying on ad hoc
    parsing in the UI or trainer loop.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from controller.ecosystem_11d import build_11d_record, clamp01
from controller.safe_shell import workspace_root
from controller.training_curriculum import classify_record


APPROVAL_PHRASE = "Akkoord"
DEFAULT_KNOWLEDGE_PATHS = (
    Path("/home/pwintri2/Downloads/OUROBOROS_KENNIS_LIJST.md"),
    workspace_root() / "OUROBOROS_KENNIS_LIJST.md",
    Path("/tmp/OUROBOROS_KENNIS_LIJST.md"),
)


def ecosystem_ingest_state_path() -> Path:
    return (workspace_root() / ".secrets" / "ecosystem_knowledge_ingest.json").resolve()


def ecosystem_ingest_output_dir() -> Path:
    return (workspace_root() / "artifacts" / "ecosystem_knowledge").resolve()


def get_ecosystem_knowledge_status() -> dict[str, Any]:
    """Return latest ecosystem knowledge ingestion state."""
    state = _load_state()
    path = _resolve_knowledge_path(None)
    return {
        "status": state.get("status", "ready"),
        "last_ingested_at": state.get("ingested_at"),
        "source_path": state.get("source_path") or (str(path) if path else ""),
        "section_count": state.get("section_count", 0),
        "topic_count": state.get("topic_count", 0),
        "track_counts": state.get("track_counts", {}),
        "artifact_path": state.get("artifact_path", ""),
        "state_path": str(ecosystem_ingest_state_path()),
        "fake_success": False,
    }


def ingest_ecosystem_knowledge(
    approval: str = "",
    path: str | None = None,
    max_topics: int = 500,
) -> dict[str, Any]:
    """Parse the local knowledge list and write bounded ecosystem records."""
    if approval != APPROVAL_PHRASE:
        return {"status": "blocked", "reason": "Approval phrase must be 'Akkoord'", "fake_success": False}
    source_path = _resolve_knowledge_path(path)
    if source_path is None or not source_path.exists():
        return {"status": "error", "reason": "OUROBOROS_KENNIS_LIJST.md not found.", "fake_success": False}

    text = source_path.read_text(encoding="utf-8", errors="replace")
    parsed = parse_knowledge_list(text, max_topics=max_topics)
    out_dir = ecosystem_ingest_output_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    artifact = out_dir / f"ecosystem_knowledge_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.jsonl"
    with artifact.open("w", encoding="utf-8") as handle:
        for record in parsed["records"]:
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=True) + "\n")

    state = {
        "status": "success",
        "ingested_at": datetime.utcnow().isoformat(),
        "source_path": str(source_path),
        "section_count": len(parsed["sections"]),
        "topic_count": len(parsed["records"]),
        "track_counts": parsed["track_counts"],
        "artifact_path": str(artifact),
        "sample_records": parsed["records"][:5],
        "fake_success": False,
    }
    _save_state(state)
    return state


def parse_knowledge_list(text: str, max_topics: int = 500) -> dict[str, Any]:
    """Parse headings and bullet topics from the knowledge list."""
    sections: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    current_section: dict[str, Any] | None = None
    current_subsection = ""
    section_index = 0
    bullet_index = 0

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        heading = re.match(r"^(#{2,4})\s+(.+)$", line)
        if heading:
            title = heading.group(2).strip()
            if heading.group(1) == "##":
                section_index += 1
                current_section = {
                    "id": f"section_{section_index}",
                    "title": title,
                    "track": _track_for_heading(title),
                    "subsections": [],
                }
                sections.append(current_section)
                current_subsection = ""
            elif current_section is not None:
                current_subsection = title
                current_section["subsections"].append(title)
            continue
        if line.startswith("- ") and current_section is not None and len(records) < max_topics:
            bullet_index += 1
            topic = line[2:].strip()
            track = current_section["track"]
            classification = classify_record(topic, {"section": current_section["title"], "preferred_track": track})
            if track not in classification["labels"]:
                labels = [track, *classification["labels"]]
            else:
                labels = classification["labels"]
            signals = _signals_for_track(track, topic)
            records.append(
                build_11d_record(
                    source="OUROBOROS_KENNIS_LIJST.md",
                    record_type="ecosystem_knowledge_topic",
                    title=topic[:180],
                    summary=f"{current_section['title']} / {current_subsection}: {topic}",
                    signals=signals,
                    metadata={
                        "topic_id": f"topic_{bullet_index:04d}",
                        "section": current_section["title"],
                        "subsection": current_subsection,
                        "curriculum_primary": track,
                        "curriculum_labels": labels,
                    },
                )
            )

    track_counts: dict[str, int] = {}
    for record in records:
        track = str(record.get("metadata", {}).get("curriculum_primary") or "general")
        track_counts[track] = track_counts.get(track, 0) + 1
    return {"sections": sections, "records": records, "track_counts": track_counts, "fake_success": False}


def _track_for_heading(title: str) -> str:
    lowered = title.lower()
    if lowered.startswith("1.") or "pop!_os" in lowered or "linux laptop" in lowered:
        return "popos_mastery"
    if lowered.startswith("2.") or "besturingssystemen" in lowered or "cross-platform" in lowered:
        return "os_cross_platform"
    if lowered.startswith("3.") or "google" in lowered:
        return "google_ecosystem"
    if lowered.startswith("4.") or "microsoft" in lowered:
        return "microsoft_365"
    if lowered.startswith("5.") or "sharepoint" in lowered:
        return "sharepoint_deep"
    if lowered.startswith("6.") or "kruipen" in lowered or "agentische" in lowered:
        return "agentic_crawling"
    if lowered.startswith("7.") or "implementatie" in lowered:
        return "ouroboros_self"
    return "general"


def _signals_for_track(track: str, topic: str) -> dict[str, float]:
    lowered = topic.lower()
    importance = 0.75
    safety = 0.15
    permission = 0.2
    auth = 0.1
    if track in {"google_ecosystem", "microsoft_365", "sharepoint_deep"}:
        auth = 0.55
        permission = 0.65 if any(word in lowered for word in ("permission", "sharing", "oauth", "entra", "admin", "consent")) else 0.45
        safety = 0.35
    if track in {"agentic_crawling", "popos_mastery"} and any(word in lowered for word in ("journal", "registry", "credentials", "privacy", "sudo", "shell")):
        safety = 0.55
    return {
        "thermal_load": 0.35 if track == "popos_mastery" else 0.05,
        "power_pressure": 0.35 if any(word in lowered for word in ("power", "battery", "tlp", "suspend")) else 0.1,
        "memory_pressure": 0.3 if any(word in lowered for word in ("memory", "ram", "oom", "cache")) else 0.1,
        "storage_pressure": 0.35 if any(word in lowered for word in ("drive", "filesystem", "storage", "onedrive", "document library")) else 0.1,
        "driver_or_api_health": 0.75 if track in {"google_ecosystem", "microsoft_365", "sharepoint_deep"} else 0.55,
        "network_pressure": 0.45 if any(word in lowered for word in ("api", "cloud", "graph", "drive", "gmail", "teams", "sharepoint")) else 0.15,
        "identity_or_auth_state": auth,
        "permission_complexity": permission,
        "freshness": 0.95,
        "importance": clamp01(importance),
        "safety_risk": clamp01(safety),
    }


def _resolve_knowledge_path(path: str | None) -> Path | None:
    if path:
        candidate = Path(path).expanduser()
        return candidate.resolve()
    for candidate in DEFAULT_KNOWLEDGE_PATHS:
        try:
            if candidate.exists():
                return candidate.resolve()
        except OSError:
            continue
    return None


def _load_state() -> dict[str, Any]:
    path = ecosystem_ingest_state_path()
    if not path.exists():
        return {"status": "ready", "fake_success": False}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {"status": "error", "reason": "State is not an object.", "fake_success": False}
    except Exception as exc:
        return {"status": "error", "reason": str(exc), "fake_success": False}


def _save_state(state: dict[str, Any]) -> None:
    path = ecosystem_ingest_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
