import unittest

from resonant_ouroboros.memory import InMemoryHippocampusMemory
from resonant_ouroboros.schema import ELEVEN_DIMENSIONS, build_11d_record


class SchemaMemoryTests(unittest.TestCase):
    def test_record_has_exact_11d_vector_and_required_metadata(self):
        record = build_11d_record(
            physical_structure="webpage_screenshot_text",
            source_origin="https://example.com",
            path_or_proprioception="/app/data/screenshots/current_browser_view.png",
            relative_temporal_position="now",
            persona_actor="tester",
            intent_marker="learn:test",
            user_context_marker="unit_test",
            emotional_valence=0.1,
            importance_score=0.8,
            karmic_weight=0.2,
            field_cluster_id="field_test",
            current_hz=431.2,
            vibration_mood="curious_scan",
        )
        self.assertEqual(len(record.vector()), 11)
        metadata = record.metadata()
        for field in ELEVEN_DIMENSIONS:
            self.assertIn(field, metadata)
        self.assertEqual(metadata["current_hz"], 431.2)
        self.assertEqual(metadata["vibration_mood"], "curious_scan")

    def test_in_memory_store_and_search(self):
        memory = InMemoryHippocampusMemory()
        record = build_11d_record(
            physical_structure="seed_topic_text",
            source_origin="AGI Kennis.txt",
            path_or_proprioception="AGI Kennis.txt",
            relative_temporal_position="now",
            persona_actor="tester",
            intent_marker="seed",
            user_context_marker="unit_test",
            emotional_valence=0.0,
            importance_score=0.9,
            karmic_weight=0.1,
            field_cluster_id="field_linear_algebra",
            current_hz=420.0,
            vibration_mood="deep_read",
        )
        identifier = memory.store("linear algebra and calculus for AGI", record)
        self.assertTrue(identifier.startswith("memory_"))
        self.assertEqual(memory.count(), 1)
        self.assertEqual(memory.search("linear algebra")[0]["id"], identifier)


if __name__ == "__main__":
    unittest.main()
