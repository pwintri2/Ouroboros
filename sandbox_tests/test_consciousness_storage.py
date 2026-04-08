import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from controller.consciousness.models import ConsciousnessChunk, ConsciousnessIngestEvent, ConsciousnessQuery
from controller.consciousness.storage import ConsciousnessMemory, DEFAULT_11D_COLLECTION


class MockCollection:
    def __init__(self):
        self._store = {}

    def add(self, documents, metadatas, ids):
        for document, metadata, item_id in zip(documents, metadatas, ids):
            self._store[item_id] = {"document": document, "metadata": dict(metadata)}

    def get(self, where=None, limit=100, ids=None, include=None):
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
            metadata = entry["metadata"]
            if where and not all(metadata.get(key) == value for key, value in where.items()):
                continue
            results["ids"].append(item_id)
            results["metadatas"].append(metadata)
            results["documents"].append(entry["document"])
            if len(results["ids"]) >= limit:
                break
        return results

    def query(self, query_texts, n_results, where=None):
        docs = []
        metas = []
        ids = []
        distances = []
        for item_id, entry in self._store.items():
            metadata = entry["metadata"]
            if where and not all(metadata.get(key) == value for key, value in where.items()):
                continue
            docs.append(entry["document"])
            metas.append(metadata)
            ids.append(item_id)
            distances.append(0.25 if query_texts[0].lower() in entry["document"].lower() else 0.9)
        ordered = sorted(zip(ids, docs, metas, distances), key=lambda row: row[3])[:n_results]
        return {
            "ids": [[row[0] for row in ordered]],
            "documents": [[row[1] for row in ordered]],
            "metadatas": [[row[2] for row in ordered]],
            "distances": [[row[3] for row in ordered]],
        }


class ConsciousnessMemoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.collection = MockCollection()
        self.memory = ConsciousnessMemory(collection=self.collection, collection_name=DEFAULT_11D_COLLECTION)

    async def test_ingest_assigns_all_11_layers(self):
        event = ConsciousnessIngestEvent(
            title="CPU spike",
            text="CPU load on the VPS increased while the Python FastAPI worker processed telemetry.",
            system="vps",
            source="telemetry",
            language="python",
        )

        response = await self.memory.ingest_event(event)

        self.assertTrue(response.accepted)
        self.assertEqual(response.collection, DEFAULT_11D_COLLECTION)
        stored = self.collection._store[response.stored_chunk_ids[0]]["metadata"]
        for key in (
            "layer_1_system", "layer_2_source", "layer_3_language", "layer_4_timestamp",
            "layer_5_persona", "layer_6_intent", "layer_7_project_context",
            "layer_8_theme_resonance", "layer_9_emotional_valence", "layer_10_karmic_weight",
            "layer_11_field_cluster",
        ):
            self.assertIn(key, stored)

    async def test_dedup_skips_duplicate_chunks(self):
        event = ConsciousnessIngestEvent(title="Same", text="repeat me", system="mac", source="api")
        first = await self.memory.ingest_event(event)
        second = await self.memory.ingest_event(event)

        self.assertEqual(len(first.stored_chunk_ids), 1)
        self.assertEqual(len(second.stored_chunk_ids), 0)
        self.assertEqual(len(second.duplicate_chunk_ids), 1)

    async def test_chunk_overrides_inherit_event_defaults(self):
        event = ConsciousnessIngestEvent(
            title="File watch",
            chunks=[ConsciousnessChunk(text="SwiftUI file changed", language="swift")],
            system="mac",
            source="file_watch",
            persona="developer",
        )

        response = await self.memory.ingest_event(event)
        stored = self.collection._store[response.stored_chunk_ids[0]]["metadata"]
        self.assertEqual(stored["layer_1_system"], "mac")
        self.assertEqual(stored["layer_2_source"], "file_watch")
        self.assertEqual(stored["layer_3_language"], "swift")
        self.assertEqual(stored["layer_5_persona"], "developer")

    async def test_developer_rerank_prefers_technical_layers(self):
        await self.memory.ingest_event(ConsciousnessIngestEvent(
            title="Tech",
            text="Python telemetry from the VPS.",
            system="vps",
            source="telemetry",
            language="python",
            persona="developer",
        ))
        await self.memory.ingest_event(ConsciousnessIngestEvent(
            title="Novel",
            text="John May resonance and karmic unfolding.",
            system="unknown",
            source="manual",
            language="unknown",
            theme_resonance=0.9,
            emotional_valence=0.9,
            karmic_weight=0.9,
            field_cluster="novel",
            persona="talle_wintrip",
        ))

        response = self.memory.query_with_persona(ConsciousnessQuery(query="python telemetry", persona="developer"))
        self.assertEqual(response.results[0].metadata["layer_3_language"], "python")

    async def test_talle_rerank_prefers_resonance_layers(self):
        await self.memory.ingest_event(ConsciousnessIngestEvent(
            title="Tech",
            text="Python telemetry from the VPS.",
            system="vps",
            source="telemetry",
            language="python",
            persona="developer",
        ))
        await self.memory.ingest_event(ConsciousnessIngestEvent(
            title="Novel",
            text="John May resonance and karmic unfolding.",
            theme_resonance=1.0,
            emotional_valence=1.0,
            karmic_weight=1.0,
            field_cluster="novel",
            persona="talle_wintrip",
        ))

        response = self.memory.query_with_persona(ConsciousnessQuery(query="john may", persona="talle_wintrip"))
        self.assertEqual(response.results[0].metadata["layer_5_persona"], "talle_wintrip")
