"""Adapters die buur-repo's vertalen naar Ouroboros-capabilities.

De scanner leest alleen projectmetadata en bestandsnamen. Hij importeert geen
code uit de andere repo's, start geen services en vermijdt secret-achtige
bestanden zoals `.env`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ouroboros_esoteric.memory_lattice import MemoryKind, OuroborosMemoryLattice
from ouroboros_esoteric.social_memory import SocialMemoryComplex


DEFAULT_EXTERNAL_REPOS: dict[str, str] = {
    "guaardvark": "/home/pwintri2/guaardvark",
    "surfsense": "/home/pwintri2/SurfSense",
    "mengram": "/home/pwintri2/mengram",
    "memoryos": "/home/pwintri2/memoryos",
}

_SKIP_DIRS = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    ".next",
    ".turbo",
    ".pytest_cache",
}

_DOC_NAMES = {"README.md", "CAPABILITIES.md", "ARCHITECTURE.md", "INSTALL.md"}

_SIGNALS: dict[str, list[tuple[str, str, str, str, float]]] = {
    "guaardvark": [
        ("agent_brain.py", "tiered_agent_router", "Reflex/instinct/deliberation routing voor snelle escalatie.", "routing", 9.0),
        ("tool_execution_guard.py", "tool_execution_guard", "Circuit breaker en duplicate-detectie voor agent tools.", "safety", 8.6),
        ("swarm_api.py", "swarm_orchestration", "Swarm-runner met parallelle agenttaken en statuslogica.", "orchestration", 8.2),
        ("rag_autoresearch", "rag_autoresearch", "Automatische RAG-evaluatie en parameter-experimenten.", "retrieval", 7.8),
        ("screen_interface.py", "screen_agent_servo", "Visuele agentbesturing met observe-think-act feedback.", "perception", 7.5),
    ],
    "surfsense": [
        ("chunks_hybrid_search.py", "rrf_hybrid_search", "Vector + full-text retrieval met reciprocal rank fusion.", "retrieval", 9.0),
        ("memory_protocol_private.md", "memory_protocol", "Turn-by-turn geheugenupdate protocol voor duurzame feiten.", "memory", 8.5),
        ("dedup_tool_calls.py", "hitl_tool_dedup", "Deduplicatie van HITL-toolcalls voor idempotente acties.", "safety", 8.0),
        ("connectors", "connector_fabric", "Connectorlaag voor externe kennisbronnen en sync.", "connectors", 7.8),
        ("local_folder", "local_folder_sync", "Lokale map-sync als bron voor kennisopbouw.", "ingestion", 7.2),
    ],
    "mengram": [
        ("ARCHITECTURE.md", "tri_memory_architecture", "Entiteiten, episodes en procedures als mensachtige geheugenfamilies.", "memory", 9.2),
        ("evolution.py", "procedure_evolution", "Feedback uit episodes laat procedures evolueren.", "learning", 8.7),
        ("knowledge_graph", "knowledge_graph", "Relationele kennislaag naast vector recall.", "memory", 8.4),
        ("mcp_server.py", "mcp_memory_surface", "MCP-oppervlak voor geheugeninteractie.", "tooling", 7.2),
    ],
    "memoryos": [
        ("models.py", "ebbinghaus_memory_atoms", "Memory atoms met retentie, stabiliteit en reinforcement.", "memory", 9.0),
        ("retriever.py", "composite_memory_ranker", "Ranking combineert semantiek, retentie, belang en recency.", "retrieval", 8.8),
        ("store.py", "sqlite_memory_store", "Persistente SQLite-store voor agentgeheugen.", "persistence", 8.1),
        ("agent.py", "memory_agent_api", "Hoge-level remember/recall API voor agents.", "memory", 7.8),
    ],
}

_INTEGRATION_NOTES: dict[str, str] = {
    "guaardvark": "Gebruik tiered routing, tool guards en swarm telemetry als agent-runtime meta-laag.",
    "surfsense": "Gebruik hybrid retrieval, connectors en memory protocol voor cockpit-kennisflows.",
    "mengram": "Gebruik tri-memory en procedure-evolution om JobRecord events tot leerbare workflows te maken.",
    "memoryos": "Gebruik retentie, reinforcement en composite ranking als lokaal Ouroboros-geheugen.",
}


@dataclass
class RepoSignal:
    name: str
    family: str
    summary: str
    strength: float
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ExternalRepoProfile:
    origin: str
    path: str
    exists: bool
    summary: str = ""
    capabilities: list[str] = field(default_factory=list)
    signals: list[RepoSignal] = field(default_factory=list)
    files_scanned: int = 0
    language_counts: dict[str, int] = field(default_factory=dict)
    docs_seen: list[str] = field(default_factory=list)
    integration_note: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["signals"] = [signal.to_dict() for signal in self.signals]
        return payload


def scan_external_repositories(paths: dict[str, str] | None = None) -> list[ExternalRepoProfile]:
    """Scan alle bekende buur-repo's en retourneer capability-profielen."""

    configured = (
        {str(key).lower(): value for key, value in paths.items()}
        if paths is not None
        else dict(DEFAULT_EXTERNAL_REPOS)
    )
    return [scan_repository(origin, path) for origin, path in configured.items()]


def scan_repository(origin: str, path: str | Path, *, max_files: int = 6000) -> ExternalRepoProfile:
    """Maak een veilig profiel van één repo."""

    origin_key = str(origin).lower()
    root = Path(path).expanduser()
    profile = ExternalRepoProfile(
        origin=origin_key,
        path=str(root),
        exists=root.exists() and root.is_dir(),
        integration_note=_INTEGRATION_NOTES.get(origin_key, ""),
    )
    if not profile.exists:
        profile.summary = "Repository niet gevonden."
        profile.warnings.append("missing")
        return profile

    files = list(_iter_files(root, max_files=max_files))
    profile.files_scanned = len(files)
    profile.language_counts = _language_counts(files)
    profile.docs_seen = _docs_seen(root)
    profile.signals = _match_signals(origin_key, root, files)
    profile.capabilities = sorted({signal.name for signal in profile.signals})
    if profile.files_scanned >= max_files:
        profile.warnings.append(f"scan capped at {max_files} files")
    profile.summary = _build_summary(profile)
    return profile


def integrate_external_repositories(
    *,
    complex_network: SocialMemoryComplex | None = None,
    lattice: OuroborosMemoryLattice | None = None,
    paths: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Neem de vier repo's op in de Ouroboros-memory laag."""

    profiles = scan_external_repositories(paths)
    lattice = lattice or OuroborosMemoryLattice(agent_id="ouroboros-external")

    for profile in profiles:
        if complex_network is not None:
            complex_network.merge_memory(
                profile.origin,
                {
                    "capabilities": profile.capabilities,
                    "signals": [signal.to_dict() for signal in profile.signals],
                    "integration_note": profile.integration_note,
                },
            )
        if profile.exists:
            lattice.remember(
                profile.summary,
                MemoryKind.CAPABILITY,
                importance=_profile_importance(profile),
                tags=[profile.origin, "external-repo"],
                source=profile.origin,
                metadata={
                    "path": profile.path,
                    "capabilities": profile.capabilities,
                    "integration_note": profile.integration_note,
                },
            )
            for signal in profile.signals[:5]:
                lattice.remember(
                    f"{profile.origin} capability {signal.name}: {signal.summary}",
                    MemoryKind.CAPABILITY,
                    importance=signal.strength,
                    tags=[profile.origin, signal.family],
                    source=profile.origin,
                    metadata={"evidence": signal.evidence},
                )

    return {
        "status": "online",
        "fake_success": False,
        "profiles": [profile.to_dict() for profile in profiles],
        "capability_count": sum(len(profile.capabilities) for profile in profiles),
        "memory": lattice.stats(),
        "recommendations": build_integration_recommendations(profiles),
    }


def build_integration_recommendations(profiles: list[ExternalRepoProfile]) -> list[str]:
    available = {profile.origin for profile in profiles if profile.exists}
    notes: list[str] = []
    if "guaardvark" in available:
        notes.append("Laat agent-runtime taken een tier/risk/context label krijgen op basis van Guaardvark routing-signalen.")
    if "surfsense" in available:
        notes.append("Gebruik SurfSense RRF-hybrid-search en connector-denken voor research- en ingestion-taken.")
    if "mengram" in available and "memoryos" in available:
        notes.append("Promoveer afgeronde JobRecord events naar episodisch geheugen en succesvolle patronen naar procedures.")
    if "memoryos" in available:
        notes.append("Versterk vaak opgevraagde lessons via retentie/reinforcement in plaats van platte chatgeschiedenis.")
    return notes


def _iter_files(root: Path, *, max_files: int) -> list[Path]:
    out: list[Path] = []
    stack = [root]
    while stack and len(out) < max_files:
        current = stack.pop()
        try:
            children = sorted(current.iterdir(), key=lambda item: item.name)
        except OSError:
            continue
        for child in children:
            if child.name in _SKIP_DIRS:
                continue
            if child.is_dir():
                stack.append(child)
                continue
            if _looks_secret(child):
                continue
            out.append(child)
            if len(out) >= max_files:
                break
    return out


def _looks_secret(path: Path) -> bool:
    lowered = path.name.lower()
    if lowered == ".env" or lowered.startswith(".env."):
        return True
    return any(part in {"secrets", ".secrets"} for part in path.parts)


def _language_counts(files: list[Path]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in files:
        suffix = path.suffix.lower() or "(none)"
        counts[suffix] = counts.get(suffix, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:12])


def _docs_seen(root: Path) -> list[str]:
    docs: list[str] = []
    for name in _DOC_NAMES:
        path = root / name
        if path.exists() and path.is_file() and not _looks_secret(path):
            docs.append(name)
    return sorted(docs)


def _match_signals(origin: str, root: Path, files: list[Path]) -> list[RepoSignal]:
    relative_names = [str(path.relative_to(root)).replace("\\", "/").lower() for path in files]
    signals: list[RepoSignal] = []
    for pattern, name, summary, family, strength in _SIGNALS.get(origin, []):
        pattern_lower = pattern.lower()
        evidence = [rel for rel in relative_names if pattern_lower in rel][:5]
        if evidence:
            signals.append(
                RepoSignal(
                    name=name,
                    family=family,
                    summary=summary,
                    strength=strength,
                    evidence=evidence,
                )
            )
    return sorted(signals, key=lambda signal: signal.strength, reverse=True)


def _build_summary(profile: ExternalRepoProfile) -> str:
    if not profile.exists:
        return profile.summary
    capabilities = ", ".join(profile.capabilities[:6]) or "geen bekende signalen"
    langs = ", ".join(f"{suffix}:{count}" for suffix, count in list(profile.language_counts.items())[:4])
    return (
        f"{profile.origin} gescand: {profile.files_scanned} bestanden, "
        f"capabilities [{capabilities}], talen [{langs}]. {profile.integration_note}"
    )


def _profile_importance(profile: ExternalRepoProfile) -> float:
    if not profile.signals:
        return 4.0
    return min(10.0, sum(signal.strength for signal in profile.signals) / len(profile.signals))
