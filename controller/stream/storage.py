# controller/stream/storage.py
# Phase 7.X — Stream of Consciousness: Storage Bridge naar Hippocampus (ChromaDB)
# Wintrip AI | task_id: wintrip-soc-002
#
# Verantwoordelijkheid:
#   - Slaat NormalizedItem op in de bestaande ChromaDB-collectie (wintrip_knowledge).
#   - Respecteert het metadata-contract van knowledge_base.py (type, source, importance, ...).
#   - Implementeert dedup-controle via content_hash VOOR embedding (goedkoop).
#   - Gebruikt dependency injection: accepteert een 'collection'-object (duck typing).
#     Dit maakt de module testbaar zonder live Ollama/ChromaDB verbinding.
#
# Metadata-contract voor stream_item (uitbreiding op bestaand schema):
#   type             : "stream_item"          — nieuw type naast user_memory/system_docs
#   source           : url of bron-identifier
#   source_type      : "rss" | "url" | "manual" | "chatgpt_macos_app"
#   persona          : "philip"               — altijd, stream is persoonlijk
#   importance       : float 1-5, afgeleid van resonance_score
#   resonance_score  : float 0-1             — auditeerbaar, apart veld
#   content_hash     : sha256(title+text)    — dedup sleutel
#   source_hash      : sha256(url)           — provenance
#   ingested_at      : ISO 8601 UTC
#   title            : gesanitiseerde titel
#   tags             : kommagescheiden string (ChromaDB accepteert geen lijsten)
#   language         : "unknown"             — toekomstige NLP-extensie
#   stream_item_id   : deterministisch UUID van NormalizedItem

from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import Any, Optional

from controller.stream.normalize import NormalizedItem, fingerprint
from controller.stream.browser_scrubber import TAINT_UNTRUSTED_WEB
from controller.stream.dreamcycle import DreamCycle
from controller.stream.geometry_11d import measure_geometry_11d
from controller.stream.metadata_11d import build_11d_metadata

# ---------------------------------------------------------------------------
# Drempelwaarden (uitbreidbaar via config in toekomstige iteratie)
# ---------------------------------------------------------------------------
STORE_THRESHOLD: float = 0.20    # items met resonance_score >= dit worden opgeslagen
PROPOSE_THRESHOLD: float = 0.65  # items met resonance_score >= dit komen in de queue


# ---------------------------------------------------------------------------
# Hulpfuncties
# ---------------------------------------------------------------------------
def _resonance_to_importance(resonance_score: float) -> float:
    """
    Mapt resonance_score (0.0–1.0) naar importance (1.0–5.0).

    Schaal:
        0.00–0.19  →  1.0  (onder store-drempel, wordt niet opgeslagen)
        0.20–0.39  →  2.0
        0.40–0.64  →  3.0
        0.65–0.84  →  4.0  (boven propose-drempel)
        0.85–1.00  →  5.0  (hoge resonantie = user_memory-niveau)
    """
    if resonance_score >= 0.85:
        return 5.0
    elif resonance_score >= 0.65:
        return 4.0
    elif resonance_score >= 0.40:
        return 3.0
    elif resonance_score >= 0.20:
        return 2.0
    else:
        return 1.0


def _tags_to_str(tags: list[str]) -> str:
    """
    Converteert tags-lijst naar kommagescheiden string.
    ChromaDB metadata accepteert alleen str/int/float/bool, geen lijst.
    """
    return ",".join(tags) if tags else ""


def _utc_now() -> str:
    """Retourneert huidig UTC-moment als ISO 8601 string."""
    return datetime.now(tz=timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# StorageResult — gestructureerde return-waarde
# ---------------------------------------------------------------------------
class StorageResult:
    """
    Resultaat van een store()-operatie. Nooit een raw bool; altijd auditeerbaar.

    Attributen:
        stored     : True als item nieuw is opgeslagen, False bij skip/fout
        duplicate  : True als item al in de database stond (dedup hit)
        below_threshold : True als resonance_score onder STORE_THRESHOLD lag
        in_queue   : True als item boven PROPOSE_THRESHOLD uitkwam
        item_id    : UUID van het item (of None bij fout)
        reason     : leesbare reden voor de beslissing
        approval_required : True als browser-ingest nog op Philip's Akkoord wacht
    """
    __slots__ = (
        "stored",
        "duplicate",
        "below_threshold",
        "in_queue",
        "item_id",
        "reason",
        "approval_required",
    )

    def __init__(
        self,
        stored: bool,
        duplicate: bool = False,
        below_threshold: bool = False,
        in_queue: bool = False,
        item_id: Optional[str] = None,
        reason: str = "",
        approval_required: bool = False,
    ):
        self.stored = stored
        self.duplicate = duplicate
        self.below_threshold = below_threshold
        self.in_queue = in_queue
        self.item_id = item_id
        self.reason = reason
        self.approval_required = approval_required

    def __repr__(self) -> str:
        return (
            f"StorageResult(stored={self.stored}, duplicate={self.duplicate}, "
            f"below_threshold={self.below_threshold}, in_queue={self.in_queue}, "
            f"item_id={self.item_id!r}, reason={self.reason!r}, "
            f"approval_required={self.approval_required})"
        )


# ---------------------------------------------------------------------------
# StreamStorage — de publieke klasse
# ---------------------------------------------------------------------------
class StreamStorage:
    """
    Brug tussen de Stream of Consciousness pipeline en de ChromaDB Hippocampus.

    Gebruik dependency injection voor de ChromaDB-collectie zodat unit tests
    een mock kunnen injecteren zonder live Ollama-verbinding:

        # Productie:
        from controller.knowledge_base import KnowledgeBase
        kb = KnowledgeBase()
        storage = StreamStorage(collection=kb.collection)

        # Tests:
        storage = StreamStorage(collection=MockCollection())

    Args:
        collection: ChromaDB-collectie (of mock met .get() en .add() interface).
    """

    def __init__(self, collection: Any):
        if collection is None:
            raise ValueError("StreamStorage vereist een ChromaDB-collectie (geen None).")
        self._collection = collection

    # ------------------------------------------------------------------
    # Publieke interface
    # ------------------------------------------------------------------

    def is_duplicate(self, item: NormalizedItem) -> bool:
        """
        Controleert of een item al in de Hippocampus staat via content_hash.

        Goedkope metadata-only query — geen embedding berekening nodig.

        Args:
            item: het te controleren NormalizedItem.

        Returns:
            True als het item al bestaat, False als het nieuw is.
        """
        try:
            fp = fingerprint(item)
            existing = self._collection.get(
                where={"content_hash": fp},
                limit=1,
            )
            return bool(existing and existing.get("ids"))
        except Exception as exc:
            # Bij ChromaDB-fout: conservatief FALSE teruggeven zodat het item
            # opgeslagen kan worden (beter dubbel dan gemist).
            print(f"[WARN] is_duplicate check mislukt: {exc}", file=sys.stderr)
            return False

    def store(self, item: NormalizedItem, resonance_score: float = 0.0) -> StorageResult:
        """
        Slaat een NormalizedItem op in de Hippocampus als het de drempels haalt.

        Beslissingsvolgorde:
          1. resonance_score < STORE_THRESHOLD  →  niet opslaan (below_threshold)
          2. is_duplicate()                     →  niet opslaan (duplicate)
          3. collection.add()                   →  opslaan (stored=True)
          4. resonance_score >= PROPOSE_THRESHOLD → in_queue=True

        Args:
            item           : NormalizedItem van normalize.normalize().
            resonance_score: float 0.0–1.0 van resonance.score() (later).
                             Default 0.0 voor deze iteratie (resonance.py nog niet gebouwd).

        Returns:
            StorageResult met volledige audit trail.
        """
        # Valideer score-range
        resonance_score = max(0.0, min(1.0, float(resonance_score)))

        # Browser-ingest blijft buiten de Hippocampus totdat Philip de DiffView
        # expliciet goedkeurt met "Akkoord".
        if item.taint == TAINT_UNTRUSTED_WEB and item.approval_status != "approved":
            return StorageResult(
                stored=False,
                approval_required=True,
                item_id=item.id,
                reason="Browser ingest wacht op Philip Akkoord voordat opslag in Hippocampus mag.",
            )

        # --- Stap 1: drempelcheck ---
        if resonance_score < STORE_THRESHOLD:
            return StorageResult(
                stored=False,
                below_threshold=True,
                item_id=item.id,
                reason=f"resonance_score {resonance_score:.3f} < STORE_THRESHOLD {STORE_THRESHOLD}",
            )

        # --- Stap 2: dedup-check ---
        if self.is_duplicate(item):
            return StorageResult(
                stored=False,
                duplicate=True,
                item_id=item.id,
                reason=f"content_hash {item.content_hash[:16]}... al aanwezig in Hippocampus",
            )

        # --- Stap 3: opslaan ---
        importance = _resonance_to_importance(resonance_score)
        in_queue = resonance_score >= PROPOSE_THRESHOLD
        ingested_at = _utc_now()
        dream_sample = DreamCycle.from_env().sample(
            f"{item.published_at}|{item.content_hash}|{item.source_hash}"
        )

        metadata = {
            "type": "stream_item",
            "source": item.url or "unknown",
            "source_type": item.source_type,
            "persona": "philip",
            "importance": importance,
            "resonance_score": resonance_score,
            "content_hash": item.content_hash,
            "source_hash": item.source_hash,
            "ingested_at": ingested_at,
            "title": item.title[:256],          # ChromaDB metadata-waarden max ~512 bytes
            "tags": _tags_to_str(item.tags),
            "language": "unknown",
            "stream_item_id": item.id,
            "in_queue": in_queue,
            "published_at": item.published_at,
            "taint": item.taint,
            "approval_status": item.approval_status,
            "diff_hash": item.diff_hash,
            "source_host": item.source_host,
            "scrubber_version": item.scrubber_version,
            "blocked_patterns": item.blocked_patterns,
            "allowed_actions": item.allowed_actions,
            "dream_anchor_hz": 418.0,
            "learnable": bool(item.approval_status == "approved"),
            "audit_only": bool(item.approval_status != "approved"),
        }
        metadata.update(dream_sample.metadata())
        geometry_11d = measure_geometry_11d(dream_sample.hz)
        metadata.update(
            {
                "geometry_11d_available": True,
                "geometry_11d_radius": float(geometry_11d["radius"]),
                "geometry_11d_volume": float(geometry_11d["volume"]),
                "geometry_11d_oppervlakte": float(geometry_11d["oppervlakte"]),
                "geometry_11d_source": "controller.stream.geometry_11d.measure_geometry_11d",
            }
        )
        metadata.update(
            build_11d_metadata(
                item=item,
                resonance_score=resonance_score,
                importance=importance,
                ingested_at=ingested_at,
                dream_hz=dream_sample.hz,
                relative_temporal_position=dream_sample.relative_temporal_position,
            )
        )

        try:
            self._collection.add(
                documents=[item.text or item.title],
                metadatas=[metadata],
                ids=[item.id],
            )
        except Exception as exc:
            return StorageResult(
                stored=False,
                item_id=item.id,
                reason=f"ChromaDB add() mislukt: {exc}",
            )

        return StorageResult(
            stored=True,
            in_queue=in_queue,
            item_id=item.id,
            reason=(
                f"Opgeslagen | importance={importance} | "
                f"{'IN QUEUE (propose)' if in_queue else 'opgeslagen (geen queue)'}"
            ),
        )

    def get_queue(self, limit: int = 50) -> list[dict]:
        """
        Haalt items op uit de Hippocampus die in de propose-queue staan
        (in_queue=True, nog niet goedgekeurd door Philip).

        Args:
            limit: maximaal aantal items (default 50).

        Returns:
            Lijst van metadata-dicts, gesorteerd op resonance_score (hoog→laag).
        """
        try:
            results = self._collection.get(
                where={"in_queue": True},
                limit=limit,
            )
            if not results or not results.get("ids"):
                return []

            items = []
            for i, item_id in enumerate(results["ids"]):
                meta = results["metadatas"][i] if results.get("metadatas") else {}
                doc = results["documents"][i] if results.get("documents") else ""
                items.append({
                    "id": item_id,
                    "text": doc,
                    **meta,
                })

            # Sorteer op resonance_score hoog→laag
            items.sort(key=lambda x: float(x.get("resonance_score", 0.0)), reverse=True)
            return items

        except Exception as exc:
            print(f"[WARN] get_queue() mislukt: {exc}", file=sys.stderr)
            return []

    def mark_approved(self, item_id: str) -> bool:
        """
        Markeert een queued item als goedgekeurd door Philip.

        Dit verwijdert NIET het item — het zet in_queue=False en type="stream_item_approved".
        Geen gevaarlijke acties; alleen metadata-update via delete+re-add.

        Args:
            item_id: het UUID van het goed te keuren NormalizedItem.

        Returns:
            True bij succes, False bij fout.
        """
        try:
            existing = self._collection.get(ids=[item_id], include=["metadatas", "documents"])
            if not existing or not existing.get("ids"):
                print(f"[WARN] mark_approved: item {item_id!r} niet gevonden.", file=sys.stderr)
                return False

            meta = dict(existing["metadatas"][0])
            doc = existing["documents"][0] if existing.get("documents") else ""

            # Update metadata
            meta["in_queue"] = False
            meta["type"] = "stream_item_approved"
            meta["approved_at"] = _utc_now()

            # ChromaDB ondersteunt geen directe update → delete + re-add
            self._collection.delete(ids=[item_id])
            self._collection.add(
                documents=[doc],
                metadatas=[meta],
                ids=[item_id],
            )
            return True

        except Exception as exc:
            print(f"[ERROR] mark_approved() mislukt: {exc}", file=sys.stderr)
            return False
