import os
import sys
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from controller.api.consciousness_routes import init_consciousness
from controller.consciousness.storage import ConsciousnessMemory


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
            if where and not all(entry["metadata"].get(key) == value for key, value in where.items()):
                continue
            results["ids"].append(item_id)
            results["metadatas"].append(entry["metadata"])
            results["documents"].append(entry["document"])
            if len(results["ids"]) >= limit:
                break
        return results

    def query(self, query_texts, n_results, where=None):
        ordered = []
        for item_id, entry in self._store.items():
            if where and not all(entry["metadata"].get(key) == value for key, value in where.items()):
                continue
            distance = 0.2 if query_texts[0].lower() in entry["document"].lower() else 0.8
            ordered.append((item_id, entry["document"], entry["metadata"], distance))
        ordered.sort(key=lambda row: row[3])
        ordered = ordered[:n_results]
        return {
            "ids": [[row[0] for row in ordered]],
            "documents": [[row[1] for row in ordered]],
            "metadatas": [[row[2] for row in ordered]],
            "distances": [[row[3] for row in ordered]],
        }


class ConsciousnessRouteTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        init_consciousness(app, ConsciousnessMemory(collection=MockCollection()))
        self.client = TestClient(app)

    def test_post_stream_consciousness_ingests(self):
        response = self.client.post("/stream_consciousness", json={
            "title": "Telemetry",
            "text": "Telemetry from the mac python worker.",
            "system": "mac",
            "source": "telemetry",
            "language": "python",
        })

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["accepted"])
        self.assertEqual(body["chunk_count"], 1)

    def test_query_route_returns_reranked_results(self):
        self.client.post("/stream_consciousness", json={
            "title": "Telemetry",
            "text": "Telemetry from the mac python worker.",
            "system": "mac",
            "source": "telemetry",
            "language": "python",
        })
        response = self.client.post("/consciousness/query", json={
            "query": "python worker",
            "persona": "developer",
        })

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["result_count"], 1)
        self.assertIn("score_breakdown", body["results"][0])

    def test_websocket_acknowledges_and_handles_validation_error(self):
        with self.client.websocket_connect("/stream_consciousness/ws") as websocket:
            websocket.send_json({
                "title": "Telemetry",
                "text": "Telemetry from the mac python worker.",
                "system": "mac",
                "source": "telemetry",
            })
            success = websocket.receive_json()
            self.assertTrue(success["accepted"])

            websocket.send_json({"title": "Broken"})
            error = websocket.receive_json()
            self.assertFalse(error["accepted"])
            self.assertEqual(error["error"], "validation_error")


if __name__ == "__main__":
    unittest.main()
