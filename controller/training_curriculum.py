"""Curriculum labels for trainer data routing and coverage."""

from __future__ import annotations

from collections import Counter
from typing import Any


CURRICULA: list[dict[str, Any]] = [
    {
        "id": "general",
        "label": "General knowledge",
        "keywords": ["summary", "article", "browser", "research", "knowledge", "concept", "explain"],
    },
    {
        "id": "programming",
        "label": "Programming",
        "keywords": ["python", "typescript", "javascript", "c++", "cmake", "shell", "sql", "bug", "test", "refactor", "function"],
    },
    {
        "id": "local_machine",
        "label": "This laptop",
        "keywords": ["pop!_os", "pop os", "docker", "ollama", "nvidia", "gpu", "cpu", "ram", "port", "service", "local machine"],
    },
    {
        "id": "operating_systems",
        "label": "Operating systems",
        "keywords": ["linux", "filesystem", "process", "memory", "kernel", "networking", "driver", "container", "sandbox"],
    },
    {
        "id": "codeneuron",
        "label": "CodeNeuron / 11D",
        "keywords": ["codeneuron", "coreneuron", "neuron", "nmodl", "mechanism", "mpi", "soa", "11d", "e-type"],
    },
    {
        "id": "ouroboros_self",
        "label": "Ouroboros self",
        "keywords": ["ouroboros", "wintrip", "trainer", "codex", "self-extension", "self training", "capability gap"],
    },
]


def list_curricula() -> dict[str, Any]:
    return {"status": "success", "curricula": [dict(item) for item in CURRICULA], "fake_success": False}


def classify_record(document: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """Classify one training record into curriculum labels with simple evidence."""
    metadata = metadata or {}
    text = " ".join(
        [
            str(document or ""),
            " ".join(f"{key}:{value}" for key, value in metadata.items() if value is not None),
        ]
    ).lower()
    scores: dict[str, int] = {}
    evidence: dict[str, list[str]] = {}
    for curriculum in CURRICULA:
        matches = [keyword for keyword in curriculum["keywords"] if keyword.lower() in text]
        score = len(matches)
        if score:
            scores[curriculum["id"]] = score
            evidence[curriculum["id"]] = matches[:8]

    if not scores:
        scores = {"general": 1}
        evidence = {"general": ["default"]}
    labels = sorted(scores, key=lambda item: (-scores[item], item))
    return {
        "primary": labels[0],
        "labels": labels,
        "scores": scores,
        "evidence": evidence,
        "fake_success": False,
    }


def coverage_from_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    counter: Counter[str] = Counter()
    primary_counter: Counter[str] = Counter()
    for record in records:
        classification = classify_record(str(record.get("document", "")), record.get("metadata") or {})
        primary_counter[classification["primary"]] += 1
        for label in classification["labels"]:
            counter[label] += 1
    return {
        "status": "success",
        "record_count": len(records),
        "primary_counts": dict(primary_counter),
        "label_counts": dict(counter),
        "curricula": [dict(item) for item in CURRICULA],
        "fake_success": False,
    }


def curriculum_status(records: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    if records is None:
        try:
            from controller.training_dataset_builder import get_approved_records

            records = get_approved_records(limit=5000)
        except Exception:
            records = []
    coverage = coverage_from_records(records)
    coverage["coverage_ratio"] = {
        curriculum["id"]: (coverage["label_counts"].get(curriculum["id"], 0) / max(1, coverage["record_count"]))
        for curriculum in CURRICULA
    }
    return coverage
