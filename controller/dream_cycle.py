"""
dream_cycle.py – Phase 12: Time-Dilation Sandbox (DreamCycle)

Wintrip's DreamCycle decouples "virtual experienced time" from physical clock
time by running many sandbox executions concurrently inside an asyncio event
loop.  While the host wall-clock may tick only a few seconds, the swarm can
complete an arbitrary number of parallel Python experiments – effectively
experiencing "hours" of virtual trial-and-error in a fraction of a second.

Public API
----------
run_time_dilated_dream(tasks, sandbox, max_concurrency, timeout_per_task)
    Entry point.  Pass a list of (task_name, python_code) tuples together with
    a SandboxExecutor instance; returns a list of result dicts sorted by
    wall-clock finish time.

DreamCycle
    Low-level asyncio orchestrator.  Useful when you need fine-grained control
    over the concurrency semaphore.
"""

import asyncio
import time
from typing import List, Tuple, Dict, Any

from controller.sandbox import SandboxExecutor


class DreamCycle:
    """
    Asyncio-gebaseerde orkestratie voor parallelle sandbox-executies.

    Parameters
    ----------
    sandbox : SandboxExecutor
        Een gedeeld SandboxExecutor-object (Docker-verbinding wordt hergebruikt).
    max_concurrency : int
        Maximaal aantal gelijktijdige container-runs (default: 4).
    """

    def __init__(self, sandbox: SandboxExecutor, max_concurrency: int = 4):
        self.sandbox = sandbox
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def _run_one(self, task_name: str, code: str, timeout: int) -> Dict[str, Any]:
        """Voert één codefragment uit in de sandbox, afgeschermd door de semaphore."""
        async with self._semaphore:
            start = time.monotonic()
            result = await self.sandbox.arun_python_code(code, timeout=timeout, task_name=task_name)
            result["wall_seconds"] = round(time.monotonic() - start, 3)
            result["task_name"] = task_name
            return result

    async def run(
        self,
        tasks: List[Tuple[str, str]],
        timeout_per_task: int = 15,
    ) -> List[Dict[str, Any]]:
        """
        Voer alle (task_name, code) paren parallel uit.

        Returns
        -------
        list[dict]
            Resultaten gesorteerd op wall-clock eindtijd (snelste eerst).
        """
        coroutines = [
            self._run_one(name, code, timeout_per_task)
            for name, code in tasks
        ]
        results = await asyncio.gather(*coroutines, return_exceptions=False)
        return sorted(results, key=lambda r: r.get("wall_seconds", 0))


def run_time_dilated_dream(
    tasks: List[Tuple[str, str]],
    sandbox: SandboxExecutor = None,
    max_concurrency: int = 4,
    timeout_per_task: int = 15,
) -> List[Dict[str, Any]]:
    """
    Synchrone entry point voor de DreamCycle.

    Hoe het werkt
    -------------
    1. Maak een nieuwe asyncio event loop aan (of hergebruik de huidige).
    2. Start alle taken gelijktijdig via asyncio.gather().
    3. Blokkeer de aanroepende thread totdat alle taken klaar zijn.
    4. Geef de gesorteerde resultatenlijst terug.

    Parameters
    ----------
    tasks : list[tuple[str, str]]
        Lijst van (task_name, python_code) paren.
    sandbox : SandboxExecutor, optional
        Wordt aangemaakt als niet meegegeven.
    max_concurrency : int
        Max gelijktijdige Docker-containers (default: 4).
    timeout_per_task : int
        Seconden per container-run (default: 15).

    Returns
    -------
    list[dict]
        Zie DreamCycle.run() voor de structuur per resultaat.
    """
    if sandbox is None:
        sandbox = SandboxExecutor()

    dream = DreamCycle(sandbox=sandbox, max_concurrency=max_concurrency)

    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError("closed")
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    return loop.run_until_complete(dream.run(tasks, timeout_per_task=timeout_per_task))
