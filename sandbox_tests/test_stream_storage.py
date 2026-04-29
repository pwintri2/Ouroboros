# sandbox_tests/test_stream_storage.py
# Phase 7.X — Unit tests voor controller/stream/storage.py
# Wintrip AI | task_id: wintrip-soc-002
#
# Geen ChromaDB/Ollama nodig: gebruikt een MockCollection (duck typing).
# Draait met: python sandbox_tests/test_stream_storage.py

import sys
import os
import unittest
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from controller.stream.normalize import normalize
from controller.stream.browser_scrubber import prepare_browser_ingest
from controller.stream.storage import (
    StreamStorage,
    StorageResult,
    STORE_THRESHOLD,
    PROPOSE_THRESHOLD,
    _resonance_to_importance,
    _tags_to_str,
)


# ---------------------------------------------------------------------------
# MockCollection — ChromaDB duck-type mock (geen live verbinding nodig)
# ---------------------------------------------------------------------------
class MockCollection:
    """
    Minimalistische in-memory implementatie van de ChromaDB collection interface.
    Ondersteunt .get(), .add(), .delete() zoals StreamStorage ze aanroept.
    """

    def __init__(self):
        self._store: dict[str, dict] = {}   # id → {document, metadata}

    def get(self, where: dict = None, limit: int = 100, ids: list = None, include: list = None) -> dict:
        results = {"ids": [], "metadatas": [], "documents": []}

        if ids is not None:
            for item_id in ids:
                if item_id in self._store:
                    entry = self._store[item_id]
                    results["ids"].append(item_id)
                    results["metadatas"].append(entry["metadata"])
                    results["documents"].append(entry["document"])
            return results

        for item_id, entry in self._store.items():
            if where:
                if not all(entry["metadata"].get(k) == v for k, v in where.items()):
                    continue
            results["ids"].append(item_id)
            results["metadatas"].append(entry["metadata"])
            results["documents"].append(entry["document"])
            if len(results["ids"]) >= limit:
                break
        return results

    def add(self, documents: list, metadatas: list, ids: list) -> None:
        for doc, meta, item_id in zip(documents, metadatas, ids):
            self._store[item_id] = {"document": doc, "metadata": dict(meta)}

    def delete(self, ids: list) -> None:
        for item_id in ids:
            self._store.pop(item_id, None)

    def count(self) -> int:
        return len(self._store)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _maak_item(title="Testbericht", text="Inhoud", source_type="rss",
               url="https://example.com/1", tags=None):
    """Maakt een NormalizedItem via de echte normalize() functie."""
    return normalize({
        "title": title,
        "text": text,
        "url": url,
        "source_type": source_type,
        "tags": tags or ["tech"],
    })


# ---------------------------------------------------------------------------
# Tests: _resonance_to_importance
# ---------------------------------------------------------------------------
class TestResonanceToImportance(unittest.TestCase):

    def test_hoge_resonance_geeft_5(self):
        self.assertEqual(_resonance_to_importance(0.85), 5.0)
        self.assertEqual(_resonance_to_importance(1.0), 5.0)

    def test_propose_zone_geeft_4(self):
        self.assertEqual(_resonance_to_importance(0.65), 4.0)
        self.assertEqual(_resonance_to_importance(0.80), 4.0)

    def test_midden_zone_geeft_3(self):
        self.assertEqual(_resonance_to_importance(0.40), 3.0)
        self.assertEqual(_resonance_to_importance(0.60), 3.0)

    def test_lage_zone_geeft_2(self):
        self.assertEqual(_resonance_to_importance(0.20), 2.0)
        self.assertEqual(_resonance_to_importance(0.35), 2.0)

    def test_onder_drempel_geeft_1(self):
        self.assertEqual(_resonance_to_importance(0.0), 1.0)
        self.assertEqual(_resonance_to_importance(0.19), 1.0)

    def test_grenswaarden_nauwkeurig(self):
        # Net onder propose threshold
        self.assertEqual(_resonance_to_importance(0.6499), 3.0)
        # Precies op propose threshold
        self.assertEqual(_resonance_to_importance(0.65), 4.0)


# ---------------------------------------------------------------------------
# Tests: _tags_to_str
# ---------------------------------------------------------------------------
class TestTagsToStr(unittest.TestCase):

    def test_lege_lijst(self):
        self.assertEqual(_tags_to_str([]), "")

    def test_een_tag(self):
        self.assertEqual(_tags_to_str(["tech"]), "tech")

    def test_meerdere_tags(self):
        result = _tags_to_str(["tech", "AI", "news"])
        self.assertEqual(result, "tech,AI,news")

    def test_none_geeft_leeg(self):
        self.assertEqual(_tags_to_str(None), "")


# ---------------------------------------------------------------------------
# Tests: StreamStorage initialisatie
# ---------------------------------------------------------------------------
class TestStreamStorageInit(unittest.TestCase):

    def test_geldige_collection_werkt(self):
        storage = StreamStorage(collection=MockCollection())
        self.assertIsNotNone(storage)

    def test_none_collection_gooit_valueerror(self):
        with self.assertRaises(ValueError):
            StreamStorage(collection=None)


# ---------------------------------------------------------------------------
# Tests: is_duplicate()
# ---------------------------------------------------------------------------
class TestIsDuplicate(unittest.TestCase):

    def test_nieuw_item_is_geen_duplicaat(self):
        storage = StreamStorage(collection=MockCollection())
        item = _maak_item()
        self.assertFalse(storage.is_duplicate(item))

    def test_opgeslagen_item_is_duplicaat(self):
        col = MockCollection()
        storage = StreamStorage(collection=col)
        item = _maak_item()
        storage.store(item, resonance_score=0.5)
        self.assertTrue(storage.is_duplicate(item))

    def test_ander_item_is_geen_duplicaat(self):
        col = MockCollection()
        storage = StreamStorage(collection=col)
        item1 = _maak_item(text="Inhoud A")
        item2 = _maak_item(text="Inhoud B")
        storage.store(item1, resonance_score=0.5)
        self.assertFalse(storage.is_duplicate(item2))

    def test_collection_fout_geeft_false_terug(self):
        """Bij ChromaDB-fout: conservatief False (niet als duplicaat markeren)."""
        broken_col = MagicMock()
        broken_col.get.side_effect = Exception("DB error")
        storage = StreamStorage(collection=broken_col)
        item = _maak_item()
        result = storage.is_duplicate(item)
        self.assertFalse(result)  # Conservatief: liever dubbel dan gemist


# ---------------------------------------------------------------------------
# Tests: store() — drempelwaarden
# ---------------------------------------------------------------------------
class TestStoreThresholds(unittest.TestCase):

    def setUp(self):
        self.storage = StreamStorage(collection=MockCollection())

    def test_onder_store_threshold_wordt_niet_opgeslagen(self):
        item = _maak_item()
        result = self.storage.store(item, resonance_score=STORE_THRESHOLD - 0.01)
        self.assertFalse(result.stored)
        self.assertTrue(result.below_threshold)

    def test_precies_op_store_threshold_wordt_opgeslagen(self):
        item = _maak_item()
        result = self.storage.store(item, resonance_score=STORE_THRESHOLD)
        self.assertTrue(result.stored)
        self.assertFalse(result.below_threshold)

    def test_boven_store_threshold_wordt_opgeslagen(self):
        item = _maak_item()
        result = self.storage.store(item, resonance_score=0.5)
        self.assertTrue(result.stored)

    def test_onder_propose_threshold_niet_in_queue(self):
        item = _maak_item()
        result = self.storage.store(item, resonance_score=PROPOSE_THRESHOLD - 0.01)
        self.assertTrue(result.stored)
        self.assertFalse(result.in_queue)

    def test_op_propose_threshold_in_queue(self):
        item = _maak_item()
        result = self.storage.store(item, resonance_score=PROPOSE_THRESHOLD)
        self.assertTrue(result.stored)
        self.assertTrue(result.in_queue)

    def test_hoge_score_opgeslagen_en_in_queue(self):
        item = _maak_item()
        result = self.storage.store(item, resonance_score=0.9)
        self.assertTrue(result.stored)
        self.assertTrue(result.in_queue)


# ---------------------------------------------------------------------------
# Tests: store() — deduplicatie
# ---------------------------------------------------------------------------
class TestStoreDuplicaat(unittest.TestCase):

    def setUp(self):
        self.storage = StreamStorage(collection=MockCollection())

    def test_duplicaat_wordt_niet_opgeslagen(self):
        item = _maak_item()
        self.storage.store(item, resonance_score=0.5)
        result = self.storage.store(item, resonance_score=0.5)
        self.assertFalse(result.stored)
        self.assertTrue(result.duplicate)

    def test_duplicaat_telt_eenmalig_in_db(self):
        item = _maak_item()
        self.storage.store(item, resonance_score=0.5)
        self.storage.store(item, resonance_score=0.5)
        # Slechts 1 record in de database
        self.assertEqual(self.storage._collection.count(), 1)

    def test_ander_item_na_duplicaat_wordt_wel_opgeslagen(self):
        item1 = _maak_item(text="Inhoud A")
        item2 = _maak_item(text="Inhoud B")
        self.storage.store(item1, resonance_score=0.5)
        self.storage.store(item1, resonance_score=0.5)  # duplicaat
        result = self.storage.store(item2, resonance_score=0.5)
        self.assertTrue(result.stored)
        self.assertEqual(self.storage._collection.count(), 2)


# ---------------------------------------------------------------------------
# Tests: store() — metadata-contract
# ---------------------------------------------------------------------------
class TestStoreMetadataContract(unittest.TestCase):

    def setUp(self):
        self.col = MockCollection()
        self.storage = StreamStorage(collection=self.col)

    def test_metadata_type_is_stream_item(self):
        item = _maak_item()
        self.storage.store(item, resonance_score=0.5)
        meta = self.col.get(ids=[item.id])["metadatas"][0]
        self.assertEqual(meta["type"], "stream_item")

    def test_metadata_persona_is_philip(self):
        item = _maak_item()
        self.storage.store(item, resonance_score=0.5)
        meta = self.col.get(ids=[item.id])["metadatas"][0]
        self.assertEqual(meta["persona"], "philip")

    def test_metadata_content_hash_aanwezig(self):
        item = _maak_item()
        self.storage.store(item, resonance_score=0.5)
        meta = self.col.get(ids=[item.id])["metadatas"][0]
        self.assertEqual(meta["content_hash"], item.content_hash)

    def test_metadata_resonance_score_aanwezig(self):
        item = _maak_item()
        self.storage.store(item, resonance_score=0.75)
        meta = self.col.get(ids=[item.id])["metadatas"][0]
        self.assertAlmostEqual(meta["resonance_score"], 0.75)

    def test_metadata_importance_afgeleid_van_resonance(self):
        item = _maak_item()
        self.storage.store(item, resonance_score=0.75)
        meta = self.col.get(ids=[item.id])["metadatas"][0]
        self.assertEqual(meta["importance"], 4.0)

    def test_metadata_in_queue_klopt_met_score(self):
        item_laag = _maak_item(text="Laag item")
        item_hoog = _maak_item(text="Hoog item")
        self.storage.store(item_laag, resonance_score=0.3)
        self.storage.store(item_hoog, resonance_score=0.8)
        meta_laag = self.col.get(ids=[item_laag.id])["metadatas"][0]
        meta_hoog = self.col.get(ids=[item_hoog.id])["metadatas"][0]
        self.assertFalse(meta_laag["in_queue"])
        self.assertTrue(meta_hoog["in_queue"])

    def test_metadata_source_type_correct(self):
        item = _maak_item(source_type="url")
        self.storage.store(item, resonance_score=0.5)
        meta = self.col.get(ids=[item.id])["metadatas"][0]
        self.assertEqual(meta["source_type"], "url")

    def test_metadata_tags_zijn_string(self):
        item = _maak_item(tags=["AI", "news"])
        self.storage.store(item, resonance_score=0.5)
        meta = self.col.get(ids=[item.id])["metadatas"][0]
        self.assertIsInstance(meta["tags"], str)
        self.assertIn("AI", meta["tags"])

    def test_metadata_ingested_at_aanwezig_en_iso(self):
        item = _maak_item()
        self.storage.store(item, resonance_score=0.5)
        meta = self.col.get(ids=[item.id])["metadatas"][0]
        self.assertIn("T", meta["ingested_at"])  # ISO 8601 heeft T-scheiding

    def test_score_buiten_range_wordt_geclamped(self):
        """Scores buiten 0-1 worden stil geclamped, geen crash."""
        item1 = _maak_item(text="Te hoog")
        item2 = _maak_item(text="Te laag")
        r1 = self.storage.store(item1, resonance_score=99.0)
        r2 = self.storage.store(item2, resonance_score=-5.0)
        self.assertTrue(r1.stored)   # 99 → geclamped naar 1.0 → boven threshold
        self.assertFalse(r2.stored)  # -5 → geclamped naar 0.0 → onder threshold

    def test_metadata_bevat_11d_lagen(self):
        item = _maak_item()
        self.storage.store(item, resonance_score=0.5)
        meta = self.col.get(ids=[item.id])["metadatas"][0]
        for key in (
            "d1_physical_body",
            "d2_physical_source",
            "d3_physical_container",
            "d4_chronology",
            "d5_persona_actor",
            "d6_persona_intent",
            "d7_persona_relation",
            "d8_karmic_taint",
            "d9_resonance_frequency",
            "d10_resonance_score",
            "d11_field",
        ):
            self.assertIn(key, meta)
            self.assertTrue(str(meta[key]))
        self.assertEqual(meta["dimension_count"], 11)

    def test_metadata_dream_hz_in_baseline_band(self):
        item = _maak_item()
        self.storage.store(item, resonance_score=0.5)
        meta = self.col.get(ids=[item.id])["metadatas"][0]
        self.assertGreaterEqual(float(meta["dream_hz"]), 418.0)
        self.assertLessEqual(float(meta["dream_hz"]), 432.0)


class TestStoreBrowserApprovalGate(unittest.TestCase):

    def setUp(self):
        self.col = MockCollection()
        self.storage = StreamStorage(collection=self.col)

    def test_unapproved_browser_ingest_wordt_niet_opgeslagen(self):
        raw = prepare_browser_ingest("https://example.com/page", "browser text").to_raw_item()
        item = normalize(raw)
        result = self.storage.store(item, resonance_score=0.9)
        self.assertFalse(result.stored)
        self.assertTrue(result.approval_required)
        self.assertEqual(self.col.count(), 0)

    def test_approved_browser_ingest_wordt_opgeslagen_met_taint_metadata(self):
        raw = prepare_browser_ingest(
            "https://example.com/page",
            "browser text",
            approval="Akkoord",
        ).to_raw_item()
        item = normalize(raw)
        result = self.storage.store(item, resonance_score=0.9)
        self.assertTrue(result.stored)
        meta = self.col.get(ids=[item.id])["metadatas"][0]
        self.assertEqual(meta["taint"], "untrusted_web")
        self.assertEqual(meta["approval_status"], "approved")


# ---------------------------------------------------------------------------
# Tests: StorageResult
# ---------------------------------------------------------------------------
class TestStorageResult(unittest.TestCase):

    def test_result_heeft_stored_false_bij_below_threshold(self):
        storage = StreamStorage(collection=MockCollection())
        item = _maak_item()
        result = storage.store(item, resonance_score=0.0)
        self.assertFalse(result.stored)
        self.assertTrue(result.below_threshold)
        self.assertFalse(result.duplicate)

    def test_result_item_id_altijd_aanwezig(self):
        storage = StreamStorage(collection=MockCollection())
        item = _maak_item()
        result = storage.store(item, resonance_score=0.5)
        self.assertEqual(result.item_id, item.id)

    def test_result_reden_niet_leeg(self):
        storage = StreamStorage(collection=MockCollection())
        item = _maak_item()
        result = storage.store(item, resonance_score=0.5)
        self.assertTrue(len(result.reason) > 0)


# ---------------------------------------------------------------------------
# Tests: get_queue()
# ---------------------------------------------------------------------------
class TestGetQueue(unittest.TestCase):

    def setUp(self):
        self.col = MockCollection()
        self.storage = StreamStorage(collection=self.col)

    def test_lege_queue_geeft_lege_lijst(self):
        result = self.storage.get_queue()
        self.assertEqual(result, [])

    def test_item_met_hoge_score_staat_in_queue(self):
        item = _maak_item(title="Urgent item")
        self.storage.store(item, resonance_score=0.8)
        queue = self.storage.get_queue()
        self.assertEqual(len(queue), 1)
        self.assertEqual(queue[0]["id"], item.id)

    def test_item_met_lage_score_staat_niet_in_queue(self):
        item = _maak_item(title="Laag item")
        self.storage.store(item, resonance_score=0.3)
        queue = self.storage.get_queue()
        self.assertEqual(len(queue), 0)

    def test_queue_gesorteerd_op_resonance_hoog_naar_laag(self):
        item1 = _maak_item(title="Item laag", text="A")
        item2 = _maak_item(title="Item hoog", text="B")
        self.storage.store(item1, resonance_score=0.7)
        self.storage.store(item2, resonance_score=0.9)
        queue = self.storage.get_queue()
        scores = [float(q.get("resonance_score", 0)) for q in queue]
        self.assertEqual(scores, sorted(scores, reverse=True))


# ---------------------------------------------------------------------------
# Tests: mark_approved()
# ---------------------------------------------------------------------------
class TestMarkApproved(unittest.TestCase):

    def setUp(self):
        self.col = MockCollection()
        self.storage = StreamStorage(collection=self.col)

    def test_approve_zet_in_queue_op_false(self):
        item = _maak_item()
        self.storage.store(item, resonance_score=0.8)
        self.storage.mark_approved(item.id)
        meta = self.col.get(ids=[item.id])["metadatas"][0]
        self.assertFalse(meta["in_queue"])

    def test_approve_zet_type_op_approved(self):
        item = _maak_item()
        self.storage.store(item, resonance_score=0.8)
        self.storage.mark_approved(item.id)
        meta = self.col.get(ids=[item.id])["metadatas"][0]
        self.assertEqual(meta["type"], "stream_item_approved")

    def test_approve_voegt_approved_at_toe(self):
        item = _maak_item()
        self.storage.store(item, resonance_score=0.8)
        self.storage.mark_approved(item.id)
        meta = self.col.get(ids=[item.id])["metadatas"][0]
        self.assertIn("approved_at", meta)
        self.assertIn("T", meta["approved_at"])

    def test_approve_niet_bestaand_item_geeft_false(self):
        result = self.storage.mark_approved("niet-bestaand-id-123")
        self.assertFalse(result)

    def test_approve_item_blijft_in_database(self):
        item = _maak_item()
        self.storage.store(item, resonance_score=0.8)
        self.storage.mark_approved(item.id)
        # Item moet nog steeds bestaan na approve
        existing = self.col.get(ids=[item.id])
        self.assertEqual(len(existing["ids"]), 1)


if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
