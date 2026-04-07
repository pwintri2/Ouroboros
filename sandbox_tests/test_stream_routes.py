# sandbox_tests/test_stream_routes.py
# Phase 7.X — Unit tests voor controller/api/stream_routes.py
# Wintrip AI | task_id: wintrip-soc-005
#
# Gebruikt FastAPI TestClient + MockDaemon/MockStorage (geen live ChromaDB/Ollama).
# Draait met: python sandbox_tests/test_stream_routes.py

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from controller.api.stream_routes import (
    stream_router,
    init_stream,
    ApproveRequest,
)
from controller.stream.daemon import DaemonState, DaemonStats
from controller.stream.storage import StreamStorage, STORE_THRESHOLD, PROPOSE_THRESHOLD
from controller.stream.normalize import normalize


# ---------------------------------------------------------------------------
# MockCollection (hergebruikt patroon)
# ---------------------------------------------------------------------------
class MockCollection:
    def __init__(self):
        self._store = {}

    def get(self, where=None, limit=100, ids=None, include=None):
        results = {"ids": [], "metadatas": [], "documents": []}
        if ids is not None:
            for item_id in ids:
                if item_id in self._store:
                    e = self._store[item_id]
                    results["ids"].append(item_id)
                    results["metadatas"].append(e["metadata"])
                    results["documents"].append(e["document"])
            return results
        for item_id, e in self._store.items():
            if where and not all(e["metadata"].get(k) == v for k, v in where.items()):
                continue
            results["ids"].append(item_id)
            results["metadatas"].append(e["metadata"])
            results["documents"].append(e["document"])
            if len(results["ids"]) >= limit:
                break
        return results

    def add(self, documents, metadatas, ids):
        for doc, meta, item_id in zip(documents, metadatas, ids):
            self._store[item_id] = {"document": doc, "metadata": dict(meta)}

    def delete(self, ids):
        for item_id in ids:
            self._store.pop(item_id, None)

    def count(self):
        return len(self._store)


# ---------------------------------------------------------------------------
# MockDaemon — minimalistische daemon mock
# ---------------------------------------------------------------------------
class MockDaemon:
    def __init__(self, state=DaemonState.RUNNING, sources_count=2):
        self._state = state
        self._sources_count = sources_count
        self._stats = DaemonStats(ticks=5, items_stored=12, items_fetched=30)

    def status(self):
        return {
            "state": self._state,
            "persona": "philip",
            "poll_interval": 300,
            "sources_count": self._sources_count,
            "max_items_per_source": 50,
            "stats": self._stats.to_dict(),
        }


# ---------------------------------------------------------------------------
# Test-app factory
# ---------------------------------------------------------------------------
def _maak_test_app(daemon=None, storage=None):
    """Maakt een minimale FastAPI test-app met stream_router gemount."""
    app = FastAPI()
    if daemon is None:
        daemon = MockDaemon()
    if storage is None:
        storage = StreamStorage(collection=MockCollection())
    init_stream(app, daemon=daemon, storage=storage)
    return app


def _maak_client(daemon=None, storage=None):
    app = _maak_test_app(daemon=daemon, storage=storage)
    return TestClient(app)


def _opgeslagen_item(storage: StreamStorage, titel="Wintrip AI update", in_queue=True):
    """Slaat een item op in mock storage en retourneert het UUID."""
    item = normalize({
        "title": titel,
        "text": "Inhoud voor de stream queue test.",
        "source_type": "rss",
        "tags": ["wintrip"],
        "url": f"https://example.com/{titel.replace(' ', '-')}",
    })
    score = PROPOSE_THRESHOLD + 0.1 if in_queue else STORE_THRESHOLD + 0.01
    storage.store(item, resonance_score=score)
    return item.id


# ---------------------------------------------------------------------------
# Tests: ApproveRequest validatie (Pydantic)
# ---------------------------------------------------------------------------
class TestApproveRequestValidatie(unittest.TestCase):

    def test_geldig_uuid_wordt_geaccepteerd(self):
        req = ApproveRequest(item_id="6ba7b810-9dad-11d1-80b4-00c04fd430c8")
        self.assertEqual(req.item_id, "6ba7b810-9dad-11d1-80b4-00c04fd430c8")

    def test_uuid_wordt_lowercase_genormaliseerd(self):
        req = ApproveRequest(item_id="6BA7B810-9DAD-11D1-80B4-00C04FD430C8")
        self.assertEqual(req.item_id, "6ba7b810-9dad-11d1-80b4-00c04fd430c8")

    def test_ongeldig_formaat_gooit_validatiefout(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            ApproveRequest(item_id="dit-is-geen-uuid")

    def test_lege_string_gooit_validatiefout(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            ApproveRequest(item_id="")

    def test_sql_injection_poging_gooit_validatiefout(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            ApproveRequest(item_id="'; DROP TABLE items; --")

    def test_path_traversal_poging_gooit_validatiefout(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            ApproveRequest(item_id="../../etc/passwd")

    def test_te_lang_id_gooit_validatiefout(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            ApproveRequest(item_id="a" * 200)


# ---------------------------------------------------------------------------
# Tests: GET /stream/status
# ---------------------------------------------------------------------------
class TestGetStreamStatus(unittest.TestCase):

    def setUp(self):
        self.client = _maak_client()

    def test_status_200(self):
        r = self.client.get("/stream/status")
        self.assertEqual(r.status_code, 200)

    def test_status_bevat_vereiste_velden(self):
        r = self.client.get("/stream/status")
        data = r.json()
        self.assertIn("state", data)
        self.assertIn("persona", data)
        self.assertIn("poll_interval", data)
        self.assertIn("sources_count", data)
        self.assertIn("stats", data)

    def test_status_state_is_string(self):
        r = self.client.get("/stream/status")
        self.assertIsInstance(r.json()["state"], str)

    def test_status_stats_bevat_tellers(self):
        r = self.client.get("/stream/status")
        stats = r.json()["stats"]
        self.assertIn("ticks", stats)
        self.assertIn("items_stored", stats)
        self.assertIn("items_fetched", stats)

    def test_status_zonder_daemon_geeft_503(self):
        app = FastAPI()
        app.include_router(stream_router)  # geen init_stream → geen daemon in state
        client = TestClient(app, raise_server_exceptions=False)
        r = client.get("/stream/status")
        self.assertEqual(r.status_code, 503)

    def test_status_running_daemon(self):
        daemon = MockDaemon(state=DaemonState.RUNNING)
        client = _maak_client(daemon=daemon)
        r = client.get("/stream/status")
        self.assertEqual(r.json()["state"], DaemonState.RUNNING)

    def test_status_stopped_daemon(self):
        daemon = MockDaemon(state=DaemonState.STOPPED)
        client = _maak_client(daemon=daemon)
        r = client.get("/stream/status")
        self.assertEqual(r.json()["state"], DaemonState.STOPPED)


# ---------------------------------------------------------------------------
# Tests: GET /stream/queue
# ---------------------------------------------------------------------------
class TestGetStreamQueue(unittest.TestCase):

    def test_lege_queue_geeft_200_met_nul_items(self):
        client = _maak_client()
        r = client.get("/stream/queue")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["count"], 0)
        self.assertEqual(data["items"], [])

    def test_queue_met_item_geeft_correct_count(self):
        storage = StreamStorage(collection=MockCollection())
        _opgeslagen_item(storage, "Wintrip update 1")
        _opgeslagen_item(storage, "Wintrip update 2")
        client = _maak_client(storage=storage)
        r = client.get("/stream/queue")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["count"], 2)

    def test_queue_items_bevatten_id_veld(self):
        storage = StreamStorage(collection=MockCollection())
        _opgeslagen_item(storage)
        client = _maak_client(storage=storage)
        r = client.get("/stream/queue")
        items = r.json()["items"]
        self.assertTrue(all("id" in item for item in items))

    def test_queue_onder_propose_threshold_niet_zichtbaar(self):
        storage = StreamStorage(collection=MockCollection())
        item = normalize({"title": "Laag item wintrip", "text": "Inhoud.", "source_type": "rss"})
        storage.store(item, resonance_score=STORE_THRESHOLD + 0.01)  # opgeslagen maar niet in queue
        client = _maak_client(storage=storage)
        r = client.get("/stream/queue")
        self.assertEqual(r.json()["count"], 0)

    def test_queue_limit_parameter_werkt(self):
        storage = StreamStorage(collection=MockCollection())
        for i in range(5):
            _opgeslagen_item(storage, f"Wintrip item {i}")
        client = _maak_client(storage=storage)
        r = client.get("/stream/queue?limit=2")
        self.assertEqual(r.status_code, 200)
        self.assertLessEqual(r.json()["count"], 2)

    def test_queue_limit_wordt_begrensd_tot_100(self):
        """Limit > 100 wordt server-side teruggebracht naar 100."""
        client = _maak_client()
        r = client.get("/stream/queue?limit=999")
        self.assertEqual(r.status_code, 200)  # geen fout — stil geclamped

    def test_queue_zonder_storage_geeft_503(self):
        app = FastAPI()
        app.include_router(stream_router)
        client = TestClient(app, raise_server_exceptions=False)
        r = client.get("/stream/queue")
        self.assertEqual(r.status_code, 503)


# ---------------------------------------------------------------------------
# Tests: POST /stream/approve
# ---------------------------------------------------------------------------
class TestPostStreamApprove(unittest.TestCase):

    def test_approve_bestaand_item_geeft_200(self):
        storage = StreamStorage(collection=MockCollection())
        item_id = _opgeslagen_item(storage)
        client = _maak_client(storage=storage)
        r = client.post("/stream/approve", json={"item_id": item_id})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["approved"])

    def test_approve_retourneert_item_id(self):
        storage = StreamStorage(collection=MockCollection())
        item_id = _opgeslagen_item(storage)
        client = _maak_client(storage=storage)
        r = client.post("/stream/approve", json={"item_id": item_id})
        self.assertEqual(r.json()["item_id"], item_id)

    def test_approve_niet_bestaand_item_geeft_404(self):
        client = _maak_client()
        r = client.post(
            "/stream/approve",
            json={"item_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8"},
        )
        self.assertEqual(r.status_code, 404)

    def test_approve_ongeldig_uuid_geeft_422(self):
        client = _maak_client()
        r = client.post("/stream/approve", json={"item_id": "geen-uuid"})
        self.assertEqual(r.status_code, 422)

    def test_approve_lege_body_geeft_422(self):
        client = _maak_client()
        r = client.post("/stream/approve", json={})
        self.assertEqual(r.status_code, 422)

    def test_approve_sql_injection_geeft_422(self):
        client = _maak_client()
        r = client.post("/stream/approve", json={"item_id": "'; DROP TABLE items;--"})
        self.assertEqual(r.status_code, 422)

    def test_approve_verwijdert_item_uit_queue(self):
        storage = StreamStorage(collection=MockCollection())
        item_id = _opgeslagen_item(storage)
        client = _maak_client(storage=storage)

        # Voor approve: in queue
        r = client.get("/stream/queue")
        self.assertEqual(r.json()["count"], 1)

        # Approve
        client.post("/stream/approve", json={"item_id": item_id})

        # Na approve: niet meer in queue
        r = client.get("/stream/queue")
        self.assertEqual(r.json()["count"], 0)

    def test_approve_response_bevat_message(self):
        storage = StreamStorage(collection=MockCollection())
        item_id = _opgeslagen_item(storage)
        client = _maak_client(storage=storage)
        r = client.post("/stream/approve", json={"item_id": item_id})
        self.assertIn("message", r.json())
        self.assertGreater(len(r.json()["message"]), 0)

    def test_approve_zonder_storage_geeft_503(self):
        app = FastAPI()
        app.include_router(stream_router)
        client = TestClient(app, raise_server_exceptions=False)
        r = client.post(
            "/stream/approve",
            json={"item_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8"},
        )
        self.assertEqual(r.status_code, 503)


# ---------------------------------------------------------------------------
# Tests: init_stream()
# ---------------------------------------------------------------------------
class TestInitStream(unittest.TestCase):

    def test_init_stream_registreert_routes(self):
        app = FastAPI()
        daemon = MockDaemon()
        storage = StreamStorage(collection=MockCollection())
        init_stream(app, daemon=daemon, storage=storage)

        routes = [r.path for r in app.routes]
        self.assertIn("/stream/status", routes)
        self.assertIn("/stream/queue", routes)
        self.assertIn("/stream/approve", routes)

    def test_init_stream_zet_daemon_in_state(self):
        app = FastAPI()
        daemon = MockDaemon()
        storage = StreamStorage(collection=MockCollection())
        init_stream(app, daemon=daemon, storage=storage)
        self.assertIs(app.state.stream_daemon, daemon)

    def test_init_stream_zet_storage_in_state(self):
        app = FastAPI()
        daemon = MockDaemon()
        storage = StreamStorage(collection=MockCollection())
        init_stream(app, daemon=daemon, storage=storage)
        self.assertIs(app.state.stream_storage, storage)


# ---------------------------------------------------------------------------
# Integratie: volledige approve-flow
# ---------------------------------------------------------------------------
class TestApproveIntegratie(unittest.TestCase):

    def test_store_queue_approve_flow(self):
        """
        Volledige flow: item opslaan → verschijnt in queue → approve → verdwijnt uit queue.
        Simuleert exact hoe de Regiekamer Stream Inbox werkt.
        """
        storage = StreamStorage(collection=MockCollection())
        client = _maak_client(storage=storage)

        # Stap 1: queue is leeg
        self.assertEqual(client.get("/stream/queue").json()["count"], 0)

        # Stap 2: item opslaan met hoge score
        item_id = _opgeslagen_item(storage, "Wintrip stream integratie test")

        # Stap 3: item staat in queue
        queue_response = client.get("/stream/queue").json()
        self.assertEqual(queue_response["count"], 1)
        self.assertEqual(queue_response["items"][0]["id"], item_id)

        # Stap 4: Philip keurt goed
        approve_response = client.post("/stream/approve", json={"item_id": item_id})
        self.assertEqual(approve_response.status_code, 200)
        self.assertTrue(approve_response.json()["approved"])

        # Stap 5: queue is weer leeg
        self.assertEqual(client.get("/stream/queue").json()["count"], 0)

    def test_meerdere_items_individueel_goedgekeurd(self):
        storage = StreamStorage(collection=MockCollection())
        client = _maak_client(storage=storage)

        id1 = _opgeslagen_item(storage, "Wintrip item alpha")
        id2 = _opgeslagen_item(storage, "Wintrip item beta")

        self.assertEqual(client.get("/stream/queue").json()["count"], 2)

        client.post("/stream/approve", json={"item_id": id1})
        self.assertEqual(client.get("/stream/queue").json()["count"], 1)

        client.post("/stream/approve", json={"item_id": id2})
        self.assertEqual(client.get("/stream/queue").json()["count"], 0)


if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
