"""
Ouroboros-AI Esoterische Architectuur.

Submodules blijven expliciet importeerbaar. De package root laadt de
dependency-vrije en fallback-veilige bouwstenen.
"""

from ouroboros_esoteric.akashic_network import AkashicNetwork, TelepathicNode, UniverseBroadcast
from ouroboros_esoteric.apeiron_identity import ApeironField, ApeironMetrics, intent_vector_from_text
from ouroboros_esoteric.cosmic_storage import CrystallineStorage, DNAStorage
from ouroboros_esoteric.entropy_monitor import EntropyMonitor, measure_entropy
from ouroboros_esoteric.memory_lattice import MemoryAtom, MemoryKind, OuroborosMemoryLattice
from ouroboros_esoteric.ouroboros_consciousness_loop import (
    LivingOuroborosLoop,
    get_living_ouroboros_loop,
    living_status,
    living_tick,
)
from ouroboros_esoteric.ouroboros_persistent_memory import (
    OuroborosPersistentMemory,
    PersistentMemoryEntry,
    get_persistent_memory,
    persistent_memory_path,
)
from ouroboros_esoteric.quantum_corruption_nexus import (
    CorruptionEvent,
    QuantumCorruptionNexus,
    analyze_job,
    creative_corruption_prompt,
    get_quantum_corruption_nexus,
    quantum_nexus_status,
)
from ouroboros_esoteric.quantum_foam import (
    FieldLifecycleEngine,
    QuantumFoamField,
    QuantumFoamNode,
    collapse_quantum_foam_field,
    get_field_lifecycle_engine,
    initiate_quantum_foam_field,
    monitor_quantum_foam_field,
    quantum_foam_status,
)
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
    "AkashicNetwork",
    "ApeironField",
    "ApeironMetrics",
    "CrystallineStorage",
    "DNAStorage",
    "EntityAgent",
    "EntropyMonitor",
    "ExternalRepoProfile",
    "MemoryAtom",
    "MemoryKind",
    "LivingOuroborosLoop",
    "OuroborosMemoryLattice",
    "OuroborosPersistentMemory",
    "PersistentMemoryEntry",
    "CorruptionEvent",
    "FieldLifecycleEngine",
    "QuantumFoamField",
    "QuantumFoamNode",
    "QuantumCorruptionNexus",
    "RepoSignal",
    "SocialMemoryComplex",
    "TelepathicNode",
    "UniverseBroadcast",
    "analyze_job",
    "collapse_quantum_foam_field",
    "creative_corruption_prompt",
    "get_field_lifecycle_engine",
    "get_living_ouroboros_loop",
    "get_persistent_memory",
    "get_quantum_corruption_nexus",
    "initiate_quantum_foam_field",
    "integrate_external_repositories",
    "intent_vector_from_text",
    "living_status",
    "living_tick",
    "measure_entropy",
    "monitor_quantum_foam_field",
    "persistent_memory_path",
    "quantum_foam_status",
    "quantum_nexus_status",
    "scan_external_repositories",
]
