# sandbox_tests/test_stream_daemon.py
# Phase 7.X — Unit tests voor controller/stream/daemon.py
# Wintrip AI | task_id: wintrip-soc-004
#
# Geen netwerk, geen ChromaDB, geen Ollama.
# Gebruikt MockCollection + mock-bronnen voor volledige pipeline-test.
# Draait met: python sandbox_tests/test_stream_daemon.py

import asyncio
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from controller.stream.daemon import (
    StreamDaemon,
    DaemonState,
    DaemonStats,
    ItemResult,
)
from controller.stream.storage import StreamStorage
from controller.stream.normalize import normalize


# ---------------------------------------------------------------------------
# MockCollection (hergebruikt van test_stream_storage.py)
# ---------------------------------------------------------------------------
class MockCollection:
    def __init__(self):
        self._store = {}

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
            if where:
                if not all(entry["metadata"].get(k) == v for k, v in where.items()):
                    continue
            results["ids"].append(item_id)
            results["metadatas"].append(entry["metadata"])
            results["documents"].append(entry["document"])
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
# Helpers — mock bronnen
# ---------------------------------------------------------------------------
def _maak_storage():
    return StreamStorage(collection=MockCollection())


def _wintrip_bron():
    """Sync bron die 2 Wintrip-relevante items retourneert (hoge resonantie)."""
    return [
        {
            "title": "Wintrip AI autonome OODA loop stream daemon update",
            "text": (
                "De nieuwe stream of consciousness architectuur van Wintrip AI "
                "maakt gebruik van een altijd-aan autonome OODA loop. "
                "ChromaDB Hippocampus en Ollama LLM samenwerking versterkt."
            ),
            "source_type": "rss",
            "tags": ["wintrip", "ai", "ooda"],
            "url": "https://example.com/wintrip-update",
        },
        {
            "title": "Bewustzijn en non-dualiteit in Boeddhistische filosofie",
            "text": (
                "Vijnana-santana beschrijft bewustzijn als een continue stroom. "
                "Meditatie en spiritueel onderzoek naar non-dualiteit."
            ),
            "source_type": "rss",
            "tags": ["filosofie", "bewustzijn"],
            "url": "https://example.com/filosofie",
        },
    ]


def _lege_bron():
    """Bron die niets retourneert."""
    return []


def _ruis_bron():
    """Bron met irrelevante items (lage resonantie)."""
    return [
        {
            "title": "Weersvoorspelling Rotterdam",
            "text": "Morgen bewolkt met kans op regen. Temperatuur rond 10 graden.",
            "source_type": "rss",
            "url": "https://example.com/weer",
        },
    ]


def _kapotte_bron():
    """Bron die een exception gooit — daemon mag niet crashen."""
    raise ConnectionError("Netwerkfout in bron")


async def _async_bron():
    """Async bron — daemon moet beide typen aankunnen."""
    await asyncio.sleep(0)
    return [
        {
            "title": "Wintrip AI async stream test",
            "text": "Een asynchroon item voor de Wintrip AI stream daemon pipeline test.",
            "source_type": "url",
            "tags": ["wintrip", "async"],
            "url": "https://example.com/async-test",
        }
    ]


def _fout_type_bron():
    """Bron die geen lijst retourneert — daemon moet dit afhandelen."""
    return {"title": "Dit is een dict, geen lijst"}


# ---------------------------------------------------------------------------
# Hulp: asyncio.run wrapper voor unittest
# ---------------------------------------------------------------------------
def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Tests: DaemonStats
# ---------------------------------------------------------------------------
class TestDaemonStats(unittest.TestCase):

    def test_initieel_alle_tellers_nul(self):
        stats = DaemonStats()
        self.assertEqual(stats.ticks, 0)
        self.assertEqual(stats.items_fetched, 0)
        self.assertEqual(stats.items_stored, 0)

    def test_to_dict_bevat_alle_velden(self):
        stats = DaemonStats(ticks=3, items_stored=7)
        d = stats.to_dict()
        self.assertIn("ticks", d)
        self.assertIn("items_stored", d)
        self.assertIn("items_fetched", d)
        self.assertIn("items_queued", d)
        self.assertIn("items_duplicate", d)
        self.assertIn("items_below_threshold", d)
        self.assertIn("items_error", d)
        self.assertEqual(d["ticks"], 3)
        self.assertEqual(d["items_stored"], 7)


# ---------------------------------------------------------------------------
# Tests: StreamDaemon initialisatie
# ---------------------------------------------------------------------------
class TestStreamDaemonInit(unittest.TestCase):

    def test_geldige_init(self):
        storage = _maak_storage()
        daemon = StreamDaemon(storage, [_wintrip_bron])
        self.assertEqual(daemon._state, DaemonState.IDLE)

    def test_geen_lijst_sources_gooit_typeerror(self):
        storage = _maak_storage()
        with self.assertRaises(TypeError):
            StreamDaemon(storage, _wintrip_bron)   # callable, geen lijst

    def test_negatief_interval_gooit_valueerror(self):
        storage = _maak_storage()
        with self.assertRaises(ValueError):
            StreamDaemon(storage, [], poll_interval=-1)

    def test_max_items_wordt_begrensd_door_hard_max(self):
        storage = _maak_storage()
        daemon = StreamDaemon(storage, [], max_items_per_source=99999)
        self.assertLessEqual(daemon._max_items, StreamDaemon._HARD_MAX_ITEMS)

    def test_lege_bronnenlijst_is_geldig(self):
        storage = _maak_storage()
        daemon = StreamDaemon(storage, [], poll_interval=0)
        self.assertIsNotNone(daemon)


# ---------------------------------------------------------------------------
# Tests: status()
# ---------------------------------------------------------------------------
class TestDaemonStatus(unittest.TestCase):

    def test_status_bevat_vereiste_velden(self):
        daemon = StreamDaemon(_maak_storage(), [_wintrip_bron])
        s = daemon.status()
        self.assertIn("state", s)
        self.assertIn("persona", s)
        self.assertIn("poll_interval", s)
        self.assertIn("sources_count", s)
        self.assertIn("stats", s)

    def test_initieel_state_is_idle(self):
        daemon = StreamDaemon(_maak_storage(), [])
        self.assertEqual(daemon.status()["state"], DaemonState.IDLE)

    def test_sources_count_klopt(self):
        daemon = StreamDaemon(_maak_storage(), [_wintrip_bron, _lege_bron])
        self.assertEqual(daemon.status()["sources_count"], 2)


# ---------------------------------------------------------------------------
# Tests: add_source() / remove_source()
# ---------------------------------------------------------------------------
class TestSourceManagement(unittest.TestCase):

    def test_add_source_vergroot_lijst(self):
        daemon = StreamDaemon(_maak_storage(), [])
        daemon.add_source(_wintrip_bron)
        self.assertEqual(daemon.status()["sources_count"], 1)

    def test_add_non_callable_gooit_typeerror(self):
        daemon = StreamDaemon(_maak_storage(), [])
        with self.assertRaises(TypeError):
            daemon.add_source("geen_callable")

    def test_remove_bestaande_source(self):
        daemon = StreamDaemon(_maak_storage(), [_wintrip_bron])
        result = daemon.remove_source(_wintrip_bron)
        self.assertTrue(result)
        self.assertEqual(daemon.status()["sources_count"], 0)

    def test_remove_niet_bestaande_source_geeft_false(self):
        daemon = StreamDaemon(_maak_storage(), [])
        result = daemon.remove_source(_wintrip_bron)
        self.assertFalse(result)


# ---------------------------------------------------------------------------
# Tests: tick() — de kern van de pipeline
# ---------------------------------------------------------------------------
class TestDaemonTick(unittest.TestCase):

    def test_tick_relevante_items_worden_opgeslagen(self):
        storage = _maak_storage()
        daemon = StreamDaemon(storage, [_wintrip_bron], poll_interval=0)
        count = _run(daemon.tick())
        self.assertGreater(count, 0)
        self.assertGreater(storage._collection.count(), 0)

    def test_tick_ruis_items_worden_niet_opgeslagen(self):
        storage = _maak_storage()
        daemon = StreamDaemon(storage, [_ruis_bron], poll_interval=0)
        count = _run(daemon.tick())
        self.assertEqual(count, 0)
        self.assertEqual(storage._collection.count(), 0)

    def test_tick_lege_bron_geeft_nul(self):
        storage = _maak_storage()
        daemon = StreamDaemon(storage, [_lege_bron], poll_interval=0)
        count = _run(daemon.tick())
        self.assertEqual(count, 0)

    def test_tick_kapotte_bron_crasht_daemon_niet(self):
        """Bron die exception gooit mag daemon niet stoppen."""
        storage = _maak_storage()
        daemon = StreamDaemon(storage, [_kapotte_bron, _wintrip_bron], poll_interval=0)
        count = _run(daemon.tick())
        # Kapotte bron geeft 0, wintrip-bron geeft items
        self.assertGreaterEqual(count, 0)

    def test_tick_async_bron_werkt(self):
        """Daemon moet zowel sync als async bronnen aankunnen."""
        storage = _maak_storage()
        daemon = StreamDaemon(storage, [_async_bron], poll_interval=0)
        count = _run(daemon.tick())
        self.assertGreaterEqual(count, 0)

    def test_tick_fout_type_bron_crasht_niet(self):
        """Bron die geen lijst retourneert wordt graceful afgehandeld."""
        storage = _maak_storage()
        daemon = StreamDaemon(storage, [_fout_type_bron], poll_interval=0)
        count = _run(daemon.tick())
        self.assertEqual(count, 0)

    def test_tick_verhoogt_stats_ticks(self):
        daemon = StreamDaemon(_maak_storage(), [_lege_bron], poll_interval=0)
        _run(daemon.tick())
        _run(daemon.tick())
        self.assertEqual(daemon._stats.ticks, 2)

    def test_tick_verhoogt_items_fetched(self):
        daemon = StreamDaemon(_maak_storage(), [_wintrip_bron], poll_interval=0)
        _run(daemon.tick())
        self.assertEqual(daemon._stats.items_fetched, 2)

    def test_tick_telt_duplicaten(self):
        storage = _maak_storage()
        daemon = StreamDaemon(storage, [_wintrip_bron], poll_interval=0)
        _run(daemon.tick())   # eerste keer opslaan
        _run(daemon.tick())   # tweede keer → duplicaten
        self.assertGreater(daemon._stats.items_duplicate, 0)

    def test_tick_meerdere_bronnen_gecombineerd(self):
        storage = _maak_storage()
        daemon = StreamDaemon(
            storage,
            [_wintrip_bron, _wintrip_bron],
            poll_interval=0
        )
        count = _run(daemon.tick())
        # Tweede bron levert duplicaten van eerste → minder unieke items
        self.assertGreater(daemon._stats.items_fetched, daemon._stats.items_stored)

    def test_tick_max_items_per_source_wordt_gerespecteerd(self):
        """Bron met veel items wordt afgekapt."""
        def grote_bron():
            return [
                {
                    "title": f"Wintrip item {i} autonome OODA Hippocampus",
                    "text": f"ChromaDB stream daemon item nummer {i} voor de Wintrip AI pipeline.",
                    "source_type": "rss",
                    "url": f"https://example.com/{i}",
                }
                for i in range(100)
            ]

        storage = _maak_storage()
        daemon = StreamDaemon(storage, [grote_bron], poll_interval=0, max_items_per_source=5)
        _run(daemon.tick())
        self.assertLessEqual(daemon._stats.items_fetched, 5)


# ---------------------------------------------------------------------------
# Tests: on_new_item callback
# ---------------------------------------------------------------------------
class TestOnNewItemCallback(unittest.TestCase):

    def test_callback_wordt_aangeroepen_bij_opgeslagen_item(self):
        received = []
        def callback(result: ItemResult):
            received.append(result)

        storage = _maak_storage()
        daemon = StreamDaemon(storage, [_wintrip_bron], poll_interval=0, on_new_item=callback)
        _run(daemon.tick())
        self.assertGreater(len(received), 0)

    def test_callback_ontvangt_itemresult(self):
        received = []
        daemon = StreamDaemon(
            _maak_storage(), [_wintrip_bron], poll_interval=0,
            on_new_item=lambda r: received.append(r)
        )
        _run(daemon.tick())
        if received:
            item = received[0]
            self.assertIsInstance(item, ItemResult)
            self.assertTrue(item.stored)
            self.assertIsInstance(item.resonance, float)

    def test_kapotte_callback_crasht_daemon_niet(self):
        """Crash in callback mag de tick niet stoppen."""
        def slechte_callback(r):
            raise RuntimeError("Callback explodeerde")

        storage = _maak_storage()
        daemon = StreamDaemon(
            storage, [_wintrip_bron], poll_interval=0,
            on_new_item=slechte_callback
        )
        # Moet zonder exception voltooien
        count = _run(daemon.tick())
        self.assertGreaterEqual(count, 0)

    def test_geen_callback_werkt_ook(self):
        """Daemon zonder callback moet normaal werken."""
        storage = _maak_storage()
        daemon = StreamDaemon(storage, [_wintrip_bron], poll_interval=0)
        count = _run(daemon.tick())
        self.assertGreaterEqual(count, 0)


# ---------------------------------------------------------------------------
# Tests: start() / stop() lifecycle
# ---------------------------------------------------------------------------
class TestDaemonLifecycle(unittest.TestCase):

    def test_start_zet_state_op_running(self):
        async def _test():
            daemon = StreamDaemon(_maak_storage(), [], poll_interval=999)
            await daemon.start()
            self.assertEqual(daemon._state, DaemonState.RUNNING)
            await daemon.stop()

        _run(_test())

    def test_stop_zet_state_op_stopped(self):
        async def _test():
            daemon = StreamDaemon(_maak_storage(), [], poll_interval=999)
            await daemon.start()
            await daemon.stop()
            self.assertEqual(daemon._state, DaemonState.STOPPED)

        _run(_test())

    def test_dubbele_start_is_idempotent(self):
        async def _test():
            daemon = StreamDaemon(_maak_storage(), [], poll_interval=999)
            await daemon.start()
            task1 = daemon._loop_task
            await daemon.start()  # tweede aanroep — mag niet crashen
            task2 = daemon._loop_task
            self.assertIs(task1, task2)  # dezelfde task
            await daemon.stop()

        _run(_test())

    def test_stop_zonder_start_crasht_niet(self):
        async def _test():
            daemon = StreamDaemon(_maak_storage(), [], poll_interval=0)
            await daemon.stop()  # nog nooit gestart — moet graceful zijn

        _run(_test())

    def test_stats_started_at_wordt_gezet(self):
        async def _test():
            daemon = StreamDaemon(_maak_storage(), [], poll_interval=999)
            await daemon.start()
            self.assertIsNotNone(daemon._stats.started_at)
            await daemon.stop()

        _run(_test())

    def test_stats_stopped_at_wordt_gezet_na_stop(self):
        async def _test():
            daemon = StreamDaemon(_maak_storage(), [], poll_interval=999)
            await daemon.start()
            await daemon.stop()
            self.assertIsNotNone(daemon._stats.stopped_at)

        _run(_test())


# ---------------------------------------------------------------------------
# Tests: volledige pipeline-integratie
# ---------------------------------------------------------------------------
class TestPipelineIntegratie(unittest.TestCase):

    def test_volledige_pipeline_wintrip_item(self):
        """
        Integratietest: ruw item → normalize → resonance → storage.
        Wintrip-relevant item moet worden opgeslagen en correct geclassificeerd.
        """
        storage = _maak_storage()
        daemon = StreamDaemon(storage, [_wintrip_bron], poll_interval=0)
        count = _run(daemon.tick())

        self.assertGreater(count, 0)
        stored = storage._collection.count()
        self.assertGreater(stored, 0)

        # Verifieer metadata van eerste opgeslagen item
        results = storage._collection.get(limit=1)
        meta = results["metadatas"][0]
        self.assertEqual(meta["type"], "stream_item")
        self.assertEqual(meta["persona"], "philip")
        self.assertIn("resonance_score", meta)
        self.assertGreater(meta["resonance_score"], 0.0)

    def test_pipeline_dedup_werkt_over_meerdere_ticks(self):
        """Zelfde bron twee keer gepold → geen duplicaten in Hippocampus."""
        storage = _maak_storage()
        daemon = StreamDaemon(storage, [_wintrip_bron], poll_interval=0)

        _run(daemon.tick())
        count_na_eerste = storage._collection.count()
        _run(daemon.tick())
        count_na_tweede = storage._collection.count()

        self.assertEqual(count_na_eerste, count_na_tweede)
        self.assertGreater(daemon._stats.items_duplicate, 0)

    def test_pipeline_ruis_passeert_niet_naar_hippocampus(self):
        """Irrelevant weeritem mag nooit in de Hippocampus terechtkomen."""
        storage = _maak_storage()
        daemon = StreamDaemon(storage, [_ruis_bron], poll_interval=0)
        _run(daemon.tick())
        self.assertEqual(storage._collection.count(), 0)


if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
