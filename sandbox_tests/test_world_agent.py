import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from controller.browser_research import BrowserActionResult
from controller.world_agent import WorldActionLog, WorldAgent, WorldMemory, detect_world_intent, grok_frontend_url


class FakeCollection:
    def __init__(self):
        self.documents = []
        self.metadatas = []
        self.ids = []

    def count(self):
        return len(self.ids)

    def upsert(self, documents, metadatas, ids):
        self.documents.extend(documents)
        self.metadatas.extend(metadatas)
        self.ids.extend(ids)

    def query(self, query_texts, n_results):
        return {
            "documents": [self.documents[:n_results]],
            "metadatas": [self.metadatas[:n_results]],
            "ids": [self.ids[:n_results]],
            "distances": [[0.12 for _ in self.documents[:n_results]]],
        }


class TestWorldAgent(unittest.TestCase):
    def test_detects_grok_and_world_memory_intents(self):
        grok = detect_world_intent("open grok.com en vraag wat het verschil is tussen simulatie en bewustzijn")
        grok_colon = detect_world_intent("open grok.com en vraag: antwoord alleen met OK")
        grok_polite = detect_world_intent("Kun je aan grok vragen hoe je zelf verder moet ontwikkelen?")
        grok_polite_reverse = detect_world_intent("Kun je het vragen aan Grok: wat is morgen de weersvoorspelling?")
        memory = detect_world_intent("wat weet je nog over 1GB bewustzijn?")

        self.assertIsNotNone(grok)
        self.assertEqual(grok.action, "grok_ask")
        self.assertIn("simulatie", grok.query)
        self.assertIsNotNone(grok_colon)
        self.assertEqual(grok_colon.action, "grok_ask")
        self.assertEqual(grok_colon.query, "antwoord alleen met OK")
        self.assertIsNotNone(grok_polite)
        self.assertEqual(grok_polite.action, "grok_ask")
        self.assertEqual(grok_polite.query, "hoe je zelf verder moet ontwikkelen?")
        self.assertIsNotNone(grok_polite_reverse)
        self.assertEqual(grok_polite_reverse.action, "grok_ask")
        self.assertIn("weersvoorspelling", grok_polite_reverse.query)
        self.assertIsNotNone(memory)
        self.assertEqual(memory.action, "memory_search")
        self.assertIn("1gb", memory.query.lower())

    def test_grok_frontend_url_preloads_question(self):
        url = grok_frontend_url("antwoord alleen met OK")

        self.assertTrue(url.startswith("https://grok.com/?"))
        self.assertIn("q=antwoord+alleen+met+OK", url)

    def test_grok_ask_requires_approval_before_typing(self):
        calls = []
        agent = WorldAgent(
            memory=WorldMemory(collection=FakeCollection()),
            browser_runner=lambda question: calls.append(question),
            tab_opener=lambda url: True,
        )

        result = agent.ask_grok("Wat is bewustzijn?", approval="akkoord")

        self.assertEqual(result["status"], "approval_required")
        self.assertFalse(result["browser_action_performed"])
        self.assertEqual(calls, [])

    def test_approved_grok_answer_is_stored_and_searchable(self):
        collection = FakeCollection()

        def runner(question):
            return BrowserActionResult(
                status="success",
                url="https://grok.com/",
                title="Grok",
                visible_text=f"Vraag: {question}\nAntwoord: Simulatie modelleert processen; bewustzijn ervaart.",
                browser_action_performed=True,
            )

        with tempfile.TemporaryDirectory(prefix="world-agent-test-") as tmp:
            agent = WorldAgent(
                memory=WorldMemory(collection=collection),
                action_log=WorldActionLog(os.path.join(tmp, "actions.jsonl")),
                browser_runner=runner,
                tab_opener=lambda url: True,
            )

            result = agent.ask_grok("Wat is het verschil tussen simulatie en bewustzijn?", approval="Akkoord")
            search = agent.search("bewustzijn simulatie", limit=3)

        self.assertEqual(result["status"], "success")
        self.assertTrue(result["memory"]["stored"])
        self.assertEqual(search["status"], "success")
        self.assertEqual(search["count"], 1)
        self.assertIn("Simulatie", search["matches"][0]["text"])

    def test_grok_success_text_is_reclassified_when_rate_limited(self):
        def runner(_question):
            return BrowserActionResult(
                status="success",
                url="https://grok.com/",
                title="Grok",
                visible_text="Veel vraag\nProbeer het straks opnieuw voor hogere prioriteitstoegang.",
                browser_action_performed=True,
            )

        agent = WorldAgent(
            memory=WorldMemory(collection=FakeCollection()),
            browser_runner=runner,
            tab_opener=lambda url: False,
        )

        result = agent.ask_grok("antwoord alleen met OK", approval="Akkoord")

        self.assertEqual(result["status"], "rate_limited")
        self.assertIn("drukte", result["reason"])
        self.assertTrue(result["memory"]["stored"])


if __name__ == "__main__":
    unittest.main()
