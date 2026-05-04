"""
Ouroboros-AI Esoterische Architectuur.

Submodules blijven expliciet importeerbaar. De package root laadt alleen de
dependency-vrije bouwstenen zodat memory/status tooling ook werkt in een shell
waar `numpy` nog niet geïnstalleerd is.
"""

from ouroboros_esoteric.memory_lattice import MemoryAtom, MemoryKind, OuroborosMemoryLattice
from ouroboros_esoteric.repository_integration import (
    DEFAULT_EXTERNAL_REPOS,
    ExternalRepoProfile,
    RepoSignal,
    integrate_external_repositories,
    scan_external_repositories,
)
from ouroboros_esoteric.social_memory import EntityAgent, SocialMemoryComplex

__all__ = [
    "DEFAULT_EXTERNAL_REPOS",
    "EntityAgent",
    "ExternalRepoProfile",
    "MemoryAtom",
    "MemoryKind",
    "OuroborosMemoryLattice",
    "RepoSignal",
    "SocialMemoryComplex",
    "integrate_external_repositories",
    "scan_external_repositories",
]
