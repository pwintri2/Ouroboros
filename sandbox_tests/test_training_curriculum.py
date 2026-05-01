import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestTrainingCurriculum(unittest.TestCase):
    def test_classifies_programming_codeneuron_and_machine_records(self):
        from controller.training_curriculum import classify_record, coverage_from_records, list_curricula

        programming = classify_record("Fix a Python test failure in CMake and C++ code.", {"source": "WintripAI"})
        self.assertEqual(programming["primary"], "programming")
        self.assertIn("programming", programming["labels"])

        codeneuron = classify_record("CoreNEURON mechanism ion channel with MPI and SoA padding.", {})
        self.assertEqual(codeneuron["primary"], "codeneuron")

        machine = classify_record("Pop!_OS laptop has Docker, GPU, Ollama models and ports.", {})
        self.assertEqual(machine["primary"], "local_machine")

        coverage = coverage_from_records(
            [
                {"document": "Python bug test", "metadata": {}},
                {"document": "Linux process filesystem memory", "metadata": {}},
                {"document": "Ouroboros trainer self-extension", "metadata": {}},
            ]
        )
        self.assertEqual(coverage["record_count"], 3)
        self.assertGreaterEqual(len(list_curricula()["curricula"]), 6)


if __name__ == "__main__":
    unittest.main()
