# controller/stream/daemon.py
# Phase 7.X — Stream of Consciousness: Background Daemon
# Wintrip AI | task_id: wintrip-soc-004
#
# Verantwoordelijkheid:
#   - Altijd-aan background loop (asyncio) die bronnen pollt, items normaliseert,
#     scoort via resonantiefilter en opslaat in de Hippocampus.
#   - Volledig ontkoppeld van user prompts en de React UI.
#   - Pluggbaar bronsysteem: elke callable die list[dict] retourneert is een bron.
#   - Veilige stop/start lifecycle met anti-loop protectie.
#   - Geen netwerktoegang in de module zelf: netwerk zit in sources/*.py.
#   - Stdlib-only behalve controller/stream imports.
#
# Architectuurpatroon (uit Stream of Consciousness PDF):
#   Source → normalize() → resonance.score() → storage.store() → on_new_item hook
#
# Levenscyclus:
#   daemon = StreamDaemon(storage, sources, poll_interval=300)
#   await daemon.start()    # start background loop
#   await daemon.stop()     # graceful shutdown
#   count = await daemon.tick()  # één poll-cyclus (ook bruikbaar in tests)
#   info  = daemon.status() # huidige staat als dict

from __future__ import annotations

import asyncio
import sys
import time
import traceback
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from controller.stream.normalize import NormalizedItem, normalize
from controller.stream.resonance import score as resonance_score
from controller.stream.storage import StreamStorage, StorageResult


# ---------------------------------------------------------------------------
# Type alias voor een bronfunctie
# Een bron is een callable die een lijst van ruwe dicts retourneert.
# De callable mag sync of async zijn; de daemon handelt beide af.
# ---------------------------------------------------------------------------
SourceFn = Callable[[], List[Dict[str, Any]]]


# ---------------------------------------------------------------------------
# DaemonState — enum-achtige constanten (geen enum import nodig)
# ---------------------------------------------------------------------------
class DaemonState:
    IDLE = "idle"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


# ---------------------------------------------------------------------------
# DaemonStats — auditeerbare tellers
# ---------------------------------------------------------------------------
@dataclass
class DaemonStats:
    """Cumulatieve statistieken van de daemon-run."""
    ticks: int = 0                # aantal poll-cycli
    items_fetched: int = 0        # totaal opgehaalde ruwe items
    items_stored: int = 0         # nieuw opgeslagen items
    items_queued: int = 0         # items boven propose-drempel
    items_duplicate: int = 0      # geweigerd als duplicaat
    items_below_threshold: int = 0  # geweigerd wegens lage score
    items_error: int = 0          # verwerkingsfouten
    last_tick_at: Optional[float] = None   # epoch timestamp
    started_at: Optional[float] = None
    stopped_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticks": self.ticks,
            "items_fetched": self.items_fetched,
            "items_stored": self.items_stored,
            "items_queued": self.items_queued,
            "items_duplicate": self.items_duplicate,
            "items_below_threshold": self.items_below_threshold,
            "items_error": self.items_error,
            "last_tick_at": self.last_tick_at,
            "started_at": self.started_at,
            "stopped_at": self.stopped_at,
        }


# ---------------------------------------------------------------------------
# ItemResult — resultaat per verwerkt item
# ---------------------------------------------------------------------------
@dataclass
class ItemResult:
    """Audit-record voor één verwerkt stream-item."""
    item_id: str
    title: str
    resonance: float
    stored: bool
    in_queue: bool
    duplicate: bool
    below_threshold: bool
    reason: str
    source_index: int   # welke bron leverde dit item


# ---------------------------------------------------------------------------
# StreamDaemon — de hoofdklasse
# ---------------------------------------------------------------------------
class StreamDaemon:
    """
    Altijd-aan background daemon voor de Stream of Consciousness pipeline.

    Gebruik:
        # Productie (via main.py lifespan):
        storage = StreamStorage(collection=kb.collection)
        sources = [rss_source_fn, url_source_fn]
        daemon = StreamDaemon(storage, sources, poll_interval=300, persona="philip")
        await daemon.start()

        # Testen (geen netwerk):
        daemon = StreamDaemon(mock_storage, [mock_source], poll_interval=0)
        count = await daemon.tick()

    Args:
        storage       : StreamStorage instantie (met geïnjecteerde ChromaDB-collectie).
        sources       : lijst van callables die list[dict] retourneren.
        poll_interval : seconden tussen tick-cycli (default 300 = 5 min). 0 = no-sleep.
        persona       : resonantie-persona (default "philip").
        max_items_per_source : maximaal aantal items per bron per tick (DoS-bescherming).
        on_new_item   : optionele callback(ItemResult) voor elk nieuw opgeslagen item.
    """

    # Absolute maximumlimiet — ook bij misconfiguratie veilig
    _HARD_MAX_ITEMS: int = 500

    def __init__(
        self,
        storage: StreamStorage,
        sources: List[SourceFn],
        poll_interval: int = 300,
        persona: str = "philip",
        max_items_per_source: int = 50,
        on_new_item: Optional[Callable[[ItemResult], None]] = None,
    ):
        if not isinstance(sources, list):
            raise TypeError("sources moet een lijst zijn van callables.")
        if poll_interval < 0:
            raise ValueError("poll_interval mag niet negatief zijn.")
        max_items_per_source = min(max_items_per_source, self._HARD_MAX_ITEMS)

        self._storage = storage
        self._sources = sources
        self._poll_interval = poll_interval
        self._persona = persona
        self._max_items = max_items_per_source
        self._on_new_item = on_new_item

        self._state = DaemonState.IDLE
        self._stats = DaemonStats()
        self._loop_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    # ------------------------------------------------------------------
    # Publieke lifecycle-methoden
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """
        Start de background poll-loop als asyncio Task.

        Idempotent: meerdere aanroepen hebben geen effect als de daemon al loopt.
        """
        if self._state == DaemonState.RUNNING:
            print("[Daemon] Al actief — start() genegeerd.", file=sys.stderr)
            return

        self._stop_event.clear()
        self._state = DaemonState.RUNNING
        self._stats.started_at = time.time()
        self._loop_task = asyncio.create_task(self._loop(), name="stream-daemon")
        print(f"[Daemon] Gestart. Bronnen: {len(self._sources)}, interval: {self._poll_interval}s")

    async def stop(self) -> None:
        """
        Graceful shutdown: wacht op het einde van de huidige tick, dan stoppen.
        """
        if self._state not in (DaemonState.RUNNING,):
            return

        self._state = DaemonState.STOPPING
        self._stop_event.set()

        if self._loop_task and not self._loop_task.done():
            try:
                await asyncio.wait_for(self._loop_task, timeout=10.0)
            except asyncio.TimeoutError:
                self._loop_task.cancel()
                print("[Daemon] Timeout bij stoppen — task geannuleerd.", file=sys.stderr)

        self._state = DaemonState.STOPPED
        self._stats.stopped_at = time.time()
        print(f"[Daemon] Gestopt. Stats: {self._stats.to_dict()}")

    async def tick(self) -> int:
        """
        Voert één volledige poll-cyclus uit (fetch → normalize → score → store).

        Bruikbaar voor directe aanroep in tests en voor handmatige triggering.
        Retourneert het aantal nieuw opgeslagen items.
        """
        self._stats.ticks += 1
        self._stats.last_tick_at = time.time()

        newly_stored = 0

        for source_idx, source_fn in enumerate(self._sources):
            raw_items = await self._fetch_from_source(source_fn, source_idx)
            if not raw_items:
                continue

            # Begrenzing per bron (DoS-bescherming)
            raw_items = raw_items[: self._max_items]
            self._stats.items_fetched += len(raw_items)

            for raw in raw_items:
                result = await self._process_item(raw, source_idx)
                if result is None:
                    self._stats.items_error += 1
                    continue

                if result.stored:
                    self._stats.items_stored += 1
                    newly_stored += 1
                    if result.in_queue:
                        self._stats.items_queued += 1
                    if self._on_new_item:
                        try:
                            self._on_new_item(result)
                        except Exception as cb_exc:
                            print(f"[Daemon] on_new_item callback fout: {cb_exc}", file=sys.stderr)
                elif result.duplicate:
                    self._stats.items_duplicate += 1
                elif result.below_threshold:
                    self._stats.items_below_threshold += 1

        return newly_stored

    def status(self) -> Dict[str, Any]:
        """
        Retourneert de huidige daemon-status als serialiseerbaar dict.
        Gebruikt door /stream/status API endpoint.
        """
        return {
            "state": self._state,
            "persona": self._persona,
            "poll_interval": self._poll_interval,
            "sources_count": len(self._sources),
            "max_items_per_source": self._max_items,
            "stats": self._stats.to_dict(),
        }

    def add_source(self, source_fn: SourceFn) -> None:
        """
        Voegt een nieuwe bronfunctie toe aan een lopende daemon.
        Thread-veilig voor toevoeging (lijst-append is atomair in CPython).
        """
        if not callable(source_fn):
            raise TypeError("source_fn moet een callable zijn.")
        self._sources.append(source_fn)
        print(f"[Daemon] Nieuwe bron toegevoegd. Totaal: {len(self._sources)}")

    def remove_source(self, source_fn: SourceFn) -> bool:
        """
        Verwijdert een bronfunctie. Retourneert True als gevonden en verwijderd.
        """
        try:
            self._sources.remove(source_fn)
            return True
        except ValueError:
            return False

    # ------------------------------------------------------------------
    # Interne methoden
    # ------------------------------------------------------------------

    async def _loop(self) -> None:
        """Interne poll-loop. Draait tot _stop_event gezet wordt."""
        print("[Daemon] Poll-loop gestart.")
        try:
            while not self._stop_event.is_set():
                try:
                    count = await self.tick()
                    print(f"[Daemon] Tick #{self._stats.ticks} voltooid. "
                          f"Nieuw opgeslagen: {count}")
                except Exception as tick_exc:
                    print(f"[Daemon] Fout in tick: {tick_exc}", file=sys.stderr)
                    traceback.print_exc(file=sys.stderr)

                if self._poll_interval > 0:
                    try:
                        await asyncio.wait_for(
                            self._stop_event.wait(),
                            timeout=self._poll_interval,
                        )
                    except asyncio.TimeoutError:
                        pass  # Normale timeout → volgende tick starten
        finally:
            print("[Daemon] Poll-loop beëindigd.")

    async def _fetch_from_source(
        self,
        source_fn: SourceFn,
        source_idx: int,
    ) -> List[Dict[str, Any]]:
        """
        Roept een bronfunctie aan (sync of async) en retourneert ruwe items.
        Behandelt alle web/bronteksten als UNTRUSTED (OWASP LLM01).
        Fouten worden gelogd maar stoppen de daemon niet.
        """
        try:
            if asyncio.iscoroutinefunction(source_fn):
                raw = await source_fn()
            else:
                # Sync bron in executor zodat de event loop niet blokkeert
                loop = asyncio.get_event_loop()
                raw = await loop.run_in_executor(None, source_fn)

            if not isinstance(raw, list):
                print(
                    f"[Daemon] Bron {source_idx} retourneerde geen lijst "
                    f"(type={type(raw).__name__}) — overgeslagen.",
                    file=sys.stderr,
                )
                return []

            return raw

        except Exception as exc:
            print(f"[Daemon] Bron {source_idx} fout: {exc}", file=sys.stderr)
            return []

    async def _process_item(
        self,
        raw: Dict[str, Any],
        source_idx: int,
    ) -> Optional[ItemResult]:
        """
        Verwerkt één ruw item door de volledige pipeline:
        normalize → resonance.score → storage.store

        Retourneert ItemResult of None bij onherstelbare fout.
        Nooit een exception gooien — daemon moet altijd doordraaien.
        """
        try:
            # Stap 1: Normaliseer
            item: NormalizedItem = normalize(raw)

            # Stap 2: Resonantiescore
            rs = resonance_score(item, persona=self._persona)

            # Stap 3: Opslaan (dedup + drempel ingebakken in storage)
            store_result: StorageResult = self._storage.store(
                item, resonance_score=rs.score
            )

            return ItemResult(
                item_id=item.id,
                title=item.title[:80],
                resonance=rs.score,
                stored=store_result.stored,
                in_queue=store_result.in_queue,
                duplicate=store_result.duplicate,
                below_threshold=store_result.below_threshold,
                reason=store_result.reason,
                source_index=source_idx,
            )

        except Exception as exc:
            print(f"[Daemon] Verwerkingsfout: {exc}", file=sys.stderr)
            return None
