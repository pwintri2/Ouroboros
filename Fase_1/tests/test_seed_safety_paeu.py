import unittest

from resonant_ouroboros.memory import InMemoryHippocampusMemory
from resonant_ouroboros.oscillator import HertzOscillator
from resonant_ouroboros.paeu_loop import PAEULoop
from resonant_ouroboros.safety import evaluate_url
from resonant_ouroboros.seed import SeedKnowledgeLoader, parse_seed_topics, queue_seed_topics_without_browser


class SeedSafetyPAEUTests(unittest.TestCase):
    def test_parse_seed_topics_from_agi_kennis(self):
        loader = SeedKnowledgeLoader("AGI Kennis.txt")
        topics = loader.load_topics()
        titles = [topic.title for topic in topics]
        self.assertIn("Wiskundige Basis", titles)
        self.assertIn("Cybersecurity", titles)
        self.assertGreaterEqual(len(topics), 15)

    def test_parse_seed_topics_handles_plain_bullets(self):
        topics = parse_seed_topics("### Test\n* Plain topic\n* **Named:** Details")
        self.assertEqual(topics[0].title, "Plain topic")
        self.assertEqual(topics[1].title, "Named")

    def test_url_safety_blocks_localhost_and_allows_https(self):
        self.assertFalse(evaluate_url("http://localhost:8000").allowed)
        self.assertFalse(evaluate_url("file:///etc/passwd").allowed)
        self.assertTrue(evaluate_url("https://example.com").allowed)

    def test_queue_seed_topics_without_browser_stores_11d_records(self):
        oscillator = HertzOscillator(spike_probability=0.0)
        memory = InMemoryHippocampusMemory()
        loop = PAEULoop(oscillator=oscillator, browser=None, memory=memory)  # type: ignore[arg-type]
        ids = queue_seed_topics_without_browser("AGI Kennis.txt", loop, max_topics=2)
        self.assertEqual(len(ids), 2)
        self.assertEqual(memory.count(), 2)
        for row in memory.rows:
            self.assertEqual(row["metadata"]["dimension_count"], 11)
            self.assertIn("current_hz", row["metadata"])


if __name__ == "__main__":
    unittest.main()
