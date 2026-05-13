"""Curriculum labels for trainer data routing and coverage.

Why this change:
    The deep ecosystem buildplan adds explicit Pop!_OS mastery, cross-platform
    OS, Google ecosystem, SharePoint deep-dive and agentic crawling tracks. The
    previous track IDs remain in place so older training records keep their
    labels.
"""

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
        "id": "popos",
        "label": "Pop!_OS laptop",
        "keywords": ["pop!_os", "pop os", "system76", "cosmic", "wayland", "x11", "fwupd", "power profiles", "s2idle", "luks"],
        "embedding_schema": ["hardware", "kernel", "desktop", "power", "security", "troubleshooting"],
    },
    {
        "id": "popos_mastery",
        "label": "Pop!_OS mastery",
        "keywords": [
            "system76",
            "cosmic",
            "pop-upgrade",
            "recovery partition",
            "powerprofilesctl",
            "fwupdmgr",
            "hybrid graphics",
            "nvidia-smi",
            "s2idle",
            "thermald",
        ],
        "embedding_schema": ["thermal", "power", "memory", "drivers", "firmware", "desktop_session", "recovery"],
        "golden_prompts": [
            "What is my current thermal state and recommended Pop!_OS power profile?",
            "Diagnose a Pop!_OS NVIDIA hybrid graphics issue from journal errors.",
            "Explain whether COSMIC, firmware and recovery partition signals look healthy.",
        ],
    },
    {
        "id": "linux_internals",
        "label": "Linux internals",
        "keywords": ["systemd", "cgroups", "namespace", "seccomp", "ebpf", "oom killer", "kswapd", "vfs", "inode", "netfilter", "dkms"],
    },
    {
        "id": "operating_systems",
        "label": "Operating systems",
        "keywords": ["linux", "filesystem", "process", "memory", "kernel", "networking", "driver", "container", "sandbox"],
    },
    {
        "id": "os_cross_platform",
        "label": "Cross-platform OS",
        "keywords": [
            "windows 11",
            "wsl2",
            "registry",
            "event viewer",
            "macos",
            "darwin",
            "launchd",
            "kvm",
            "qemu",
            "hyper-v",
            "virtualbox",
            "terraform",
            "ansible",
        ],
        "embedding_schema": ["linux", "windows", "macos", "virtualization", "containers", "logs", "settings"],
        "golden_prompts": [
            "Compare how to inspect service failures on Pop!_OS, Windows 11 and macOS.",
            "Explain how WSL2 filesystem and networking behavior differs from native Linux.",
        ],
    },
    {
        "id": "google_workspace",
        "label": "Google Workspace",
        "keywords": ["google", "gmail", "google drive", "shared drives", "docs", "sheets", "calendar", "workspace", "gcp", "apps script"],
    },
    {
        "id": "google_ecosystem",
        "label": "Google ecosystem",
        "keywords": [
            "google account",
            "oauth2",
            "openid connect",
            "service accounts",
            "domain-wide delegation",
            "gmail api",
            "drive api",
            "calendar api",
            "google cloud",
            "gcp",
            "bigquery",
            "cloud run",
            "apps script",
        ],
        "embedding_schema": ["identity", "drive_tree", "mail", "calendar", "gcp_project", "oauth_scope", "last_modified"],
        "golden_prompts": [
            "Find my most recent Google Doc about Ouroboros and explain the approval steps.",
            "Map a Google Drive folder into an 11D record with importance and freshness.",
        ],
    },
    {
        "id": "microsoft_365",
        "label": "Microsoft 365",
        "keywords": ["microsoft", "microsoft 365", "office 365", "entra", "azure", "teams", "onedrive", "graph", "power platform", "windows"],
        "embedding_schema": ["identity", "graph_endpoint", "onedrive", "teams", "calendar", "azure", "power_platform", "permissions"],
        "golden_prompts": [
            "Copy a file from OneDrive to SharePoint and notify Teams with approval gates.",
            "Explain delegated versus application Graph permissions for a local adapter.",
            "Troubleshoot an Entra conditional access block without exposing secrets.",
        ],
    },
    {
        "id": "sharepoint",
        "label": "SharePoint",
        "keywords": ["sharepoint", "site collection", "document library", "list", "content type", "permission", "spfx", "pnp", "purview"],
    },
    {
        "id": "sharepoint_deep",
        "label": "SharePoint deep",
        "keywords": [
            "sharepoint online",
            "sharepoint server",
            "site collections",
            "hub sites",
            "content types",
            "unique permissions",
            "external sharing",
            "retention policies",
            "power automate",
            "pnp powershell",
            "spfx",
            "json formatting",
            "migration",
        ],
        "embedding_schema": ["site_url", "list_id", "content_type", "permission_level", "sharing", "retention", "last_modified"],
        "golden_prompts": [
            "Show SharePoint sites with unique permissions and suggest cleanup.",
            "Explain a SharePoint item-created trigger into Power Automate and Teams.",
        ],
    },
    {
        "id": "agentic_tooling",
        "label": "Agentic tooling",
        "keywords": ["agentic", "tool use", "browser calls", "approval gates", "self-extension", "capability gap", "long-term memory", "frontend_open_browser"],
    },
    {
        "id": "agentic_crawling",
        "label": "Agentic crawling",
        "keywords": [
            "crawl",
            "crawler",
            "filesystem",
            "journalctl",
            "gsettings",
            "dconf",
            "windows registry",
            "privacy filters",
            "gitignore",
            "content hash",
            "cross-service",
            "rollback plan",
        ],
        "embedding_schema": ["source", "content_hash", "timestamp", "privacy_risk", "importance", "approval_state", "rollback"],
        "golden_prompts": [
            "Safely crawl a project folder and report what was indexed without reading secrets.",
            "Propose a cross-service action from local findings to SharePoint and Teams.",
        ],
    },
    {
        "id": "codeneuron",
        "label": "CodeNeuron / 11D",
        "keywords": ["codeneuron", "coreneuron", "neuron", "nmodl", "mechanism", "mpi", "soa", "11d", "e-type", "membrane"],
    },
    {
        "id": "ouroboros_self",
        "label": "Ouroboros self",
        "keywords": [
            "ouroboros",
            "wintrip",
            "trainer",
            "codex",
            "self-extension",
            "self training",
            "capability gap",
            "streaming consciousness",
            "dhcp",
            "tcp",
            "byte-stream",
        ],
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
            from controller.training_dataset_builder import get_curriculum_records

            records = get_curriculum_records(limit=5000)
        except Exception:
            records = []
    coverage = coverage_from_records(records)
    coverage["coverage_ratio"] = {
        curriculum["id"]: (coverage["label_counts"].get(curriculum["id"], 0) / max(1, coverage["record_count"]))
        for curriculum in CURRICULA
    }
    return coverage
