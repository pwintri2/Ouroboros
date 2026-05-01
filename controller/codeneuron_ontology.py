"""Ontology that ties CodeNeuron/CoreNEURON concepts to the 11D pocket."""

from __future__ import annotations

from typing import Any

from controller.blue_brain_adapter import E_TYPES


POCKET_DIMENSIONS: list[dict[str, Any]] = [
    {
        "id": "d01_neuron_etype_activation",
        "index": 1,
        "title": "Neuron/e-type activation",
        "e_type": E_TYPES[0],
        "keywords": ["etype", "neuron", "cell", "memb", "voltage", "activation"],
        "summary": "How e-type activity is represented as an 11D feature signal.",
    },
    {
        "id": "d02_mechanisms_ion_channels",
        "index": 2,
        "title": "Mechanisms / ion channels",
        "e_type": E_TYPES[1],
        "keywords": ["mechanism", "ion", "channel", "mod2c", "nrn_state", "current"],
        "summary": "NMODL mechanisms, ion currents and channel state transitions.",
    },
    {
        "id": "d03_network_events",
        "index": 3,
        "title": "Network events",
        "e_type": E_TYPES[2],
        "keywords": ["event", "netcon", "spike", "queue", "deliver", "net_receive"],
        "summary": "Spike/event routing and delivery through the simulated network.",
    },
    {
        "id": "d04_simulation_timestep",
        "index": 4,
        "title": "Simulation time step",
        "e_type": E_TYPES[3],
        "keywords": ["timestep", "dt", "advance", "solver", "integrate", "thread"],
        "summary": "Time stepping, solvers and per-thread simulation advancement.",
    },
    {
        "id": "d05_memory_layout_soa_padding",
        "index": 5,
        "title": "Memory layout / SoA padding",
        "e_type": E_TYPES[4],
        "keywords": ["soa", "padding", "alignment", "layout", "memory", "stride"],
        "summary": "Struct-of-arrays layout, padding, alignment and memory locality.",
    },
    {
        "id": "d06_parallelism_mpi",
        "index": 6,
        "title": "Parallelism / MPI",
        "e_type": E_TYPES[5],
        "keywords": ["mpi", "parallel", "rank", "thread", "openmp", "coreneuron"],
        "summary": "Distributed and shared-memory execution model.",
    },
    {
        "id": "d07_gpu_offload",
        "index": 7,
        "title": "GPU offload",
        "e_type": E_TYPES[6],
        "keywords": ["gpu", "cuda", "openacc", "device", "offload", "nvc"],
        "summary": "GPU execution, device transfers and accelerator constraints.",
    },
    {
        "id": "d08_binary_io_checkpointing",
        "index": 8,
        "title": "Binary IO / checkpointing",
        "e_type": E_TYPES[7],
        "keywords": ["checkpoint", "binary", "io", "read", "write", "report"],
        "summary": "Input/output, reports, checkpoint and restart behavior.",
    },
    {
        "id": "d09_model_parameters",
        "index": 9,
        "title": "Model parameters",
        "e_type": E_TYPES[8],
        "keywords": ["parameter", "param", "mapping", "data", "nmodl", "variable"],
        "summary": "Model variables, mechanism parameters and generated data mapping.",
    },
    {
        "id": "d10_hardware_runtime_constraints",
        "index": 10,
        "title": "Hardware/runtime constraints",
        "e_type": E_TYPES[9],
        "keywords": ["cmake", "compiler", "build", "runtime", "hardware", "platform"],
        "summary": "Build, compiler, hardware and runtime constraints.",
    },
    {
        "id": "d11_validation_tests",
        "index": 11,
        "title": "Validation / tests",
        "e_type": E_TYPES[10],
        "keywords": ["test", "validation", "unit", "assert", "baseline", "compare"],
        "summary": "Tests, validation harnesses and reproducibility checks.",
    },
]


def get_pocket_dimensions() -> list[dict[str, Any]]:
    """Return the canonical 11D pocket dimensions."""
    return [dict(item) for item in POCKET_DIMENSIONS]


def infer_dimensions(text: str, limit: int = 4) -> list[dict[str, Any]]:
    """Infer likely pocket dimensions from path/content text."""
    haystack = str(text or "").lower()
    matches: list[dict[str, Any]] = []
    for dimension in POCKET_DIMENSIONS:
        keywords = dimension.get("keywords") or []
        score = sum(1 for keyword in keywords if str(keyword).lower() in haystack)
        if score:
            matches.append(
                {
                    "id": dimension["id"],
                    "title": dimension["title"],
                    "score": score,
                    "matched_keywords": [keyword for keyword in keywords if str(keyword).lower() in haystack],
                }
            )
    matches.sort(key=lambda item: (-int(item["score"]), str(item["id"])))
    return matches[: max(1, int(limit))]


def get_pocket_map(index_summary: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the 11D pocket map, optionally enriched with indexed sources."""
    files = list((index_summary or {}).get("files") or [])
    dimensions = get_pocket_dimensions()
    for dimension in dimensions:
        source_matches = []
        for file_info in files:
            for match in file_info.get("dimensions") or []:
                if match.get("id") == dimension["id"]:
                    source_matches.append(
                        {
                            "path": file_info.get("path", ""),
                            "subsystem": file_info.get("subsystem", ""),
                            "score": match.get("score", 0),
                            "summary": file_info.get("summary", ""),
                        }
                    )
        source_matches.sort(key=lambda item: (-int(item.get("score") or 0), str(item.get("path") or "")))
        dimension["source_matches"] = source_matches[:8]
        dimension["source_count"] = len(source_matches)
    return {
        "status": "success",
        "dimension_count": len(dimensions),
        "dimensions": dimensions,
        "indexed_at": (index_summary or {}).get("indexed_at"),
        "source_root": (index_summary or {}).get("source_root"),
        "fake_success": False,
    }
