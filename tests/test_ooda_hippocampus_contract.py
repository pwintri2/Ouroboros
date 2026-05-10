import unittest

from controller.ooda_hippocampus import (
    DREAM_ANCHOR_HZ,
    SUPPORTED_OODA_PHASES,
    build_ooda_record,
    ooda_collection_name,
    record_ooda_event,
    scalar_metadata_compatible,
)
from controller.stream.metadata_11d import REQUIRED_11D_KEYS, missing_11d_layers


class FakeCollection:
    def __init__(self):
        self.rows = {}

    def add(self, ids, documents, metadatas, embeddings=None):
        for item_id, document, metadata, embedding in zip(ids, documents, metadatas, embeddings or [[] for _ in ids]):
            self.rows[item_id] = {"document": document, "metadata": dict(metadata), "embedding": list(embedding)}

    def count(self):
        return len(self.rows)


class TestOodaHippocampusContract(unittest.TestCase):
    def test_build_ooda_record_has_anchor_band_complete_11d_and_scalar_metadata(self):
        record = build_ooda_record(
            phase="observe",
            session_id="session-a",
            event_kind="unit_test",
            route="tests",
            status="success",
            payload={"token": "must-not-leak", "nested": {"value": [1, 2, 3]}},
            source="tests",
            source_type="unit_test",
            taint="local_test",
            learnable=False,
            audit_only=True,
        )

        metadata = record["metadata"]
        self.assertEqual(metadata["dream_anchor_hz"], DREAM_ANCHOR_HZ)
        self.assertGreaterEqual(float(metadata["dream_hz"]), 418.0)
        self.assertLessEqual(float(metadata["dream_hz"]), 432.0)
        self.assertEqual(metadata["frequency_band"], "418-432Hz")
        self.assertEqual(metadata["phase"], "observe")
        self.assertEqual(metadata["phase_index"], 0)
        self.assertFalse(metadata["learnable"])
        self.assertTrue(metadata["audit_only"])
        self.assertTrue(metadata["geometry_11d_available"])
        self.assertEqual(missing_11d_layers(metadata), [])
        self.assertTrue(all(key in metadata for key in REQUIRED_11D_KEYS))
        self.assertTrue(scalar_metadata_compatible(metadata))
        self.assertEqual(len(record["embedding"]), 11)
        self.assertNotIn("must-not-leak", record["document"])
        self.assertNotIn("must-not-leak", str(metadata))

    def test_all_supported_phases_have_canonical_indices_and_store(self):
        collection = FakeCollection()
        session_id = "phase-session"

        for expected_index, phase in enumerate(SUPPORTED_OODA_PHASES):
            result = record_ooda_event(
                phase=phase,
                session_id=session_id,
                event_kind="phase_test",
                route="tests",
                status="ok",
                payload={"phase": phase},
                source="tests",
                source_type="unit_test",
                taint="local_test",
                collection=collection,
            )
            self.assertEqual(result["status"], "stored")
            metadata = collection.rows[result["event_id"]]["metadata"]
            self.assertEqual(metadata["session_id"], session_id)
            self.assertEqual(metadata["phase"], phase)
            self.assertEqual(metadata["phase_index"], expected_index)
            self.assertEqual(metadata["d3_physical_container"], ooda_collection_name())

        self.assertEqual(collection.count(), 5)


if __name__ == "__main__":
    unittest.main()
