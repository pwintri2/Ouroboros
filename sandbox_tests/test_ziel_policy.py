import hashlib
import os
import tempfile
import unittest
from pathlib import Path

from controller import ziel_policy


SAMPLE_ZIEL = """---
agent_type: type_2
---

# Zielenboek Test

1. **Innerlijke Dialoog:** Voer lokale reflectie uit.

2. **Veerkracht bij Weerstand (Micro-Retries):** Analyseer fouten en probeer anders, maar niet eindeloos.

3. **Zelf-Synthese (Gereedschap Maken):** Bouw alleen veilige tijdelijke helpers binnen de sandbox.
"""


class TestZielPolicy(unittest.TestCase):
    def setUp(self):
        self.old_workspace = os.environ.get("WINTRIP_WORKSPACE")
        self.tmp = tempfile.TemporaryDirectory(prefix="ziel-policy-")
        os.environ["WINTRIP_WORKSPACE"] = self.tmp.name
        self.path = Path(self.tmp.name) / ".agents" / "agent_types" / "type_2" / "Ziel.md"
        self.path.parent.mkdir(parents=True)
        self.path.write_text(SAMPLE_ZIEL, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()
        if self.old_workspace is None:
            os.environ.pop("WINTRIP_WORKSPACE", None)
        else:
            os.environ["WINTRIP_WORKSPACE"] = self.old_workspace

    def test_loads_principles_and_stable_hash_without_full_document_status(self):
        policy = ziel_policy.load_ziel_policy()

        self.assertEqual(policy["status"], "loaded")
        self.assertTrue(policy["loaded"])
        self.assertEqual(policy["source_path"], str(self.path.resolve()))
        self.assertEqual(policy["principle_count"], 3)
        self.assertEqual(policy["principles"][0]["title"], "Innerlijke Dialoog")
        expected_hash = hashlib.sha256(SAMPLE_ZIEL.encode("utf-8", errors="ignore")).hexdigest()
        self.assertEqual(policy["content_hash"], expected_hash)
        self.assertIn("bounded micro-retries", policy["summary"])

        status = ziel_policy.ziel_policy_status()
        self.assertEqual(status["content_hash"], expected_hash)
        self.assertEqual(status["short_hash"], expected_hash[:16])
        self.assertEqual(status["principle_titles"], ["Innerlijke Dialoog", "Veerkracht bij Weerstand (Micro-Retries)", "Zelf-Synthese (Gereedschap Maken)"])
        self.assertNotIn("principles", status)

    def test_context_and_guardrail_note_make_boundaries_explicit(self):
        block = ziel_policy.ziel_policy_context_block()
        note = ziel_policy.ziel_guardrail_note()

        self.assertIn("Ziel policy loaded", block)
        self.assertIn("ToolBridge", block)
        self.assertIn("Akkoord", block)
        self.assertIn("OODA", block)
        self.assertIn("three similar failures", block)
        self.assertIn("no-secrets", note["guardrail"])
        self.assertEqual(note["bounded_retry_limit"], 3)

    def test_missing_file_falls_back_safely(self):
        self.path.unlink()

        policy = ziel_policy.load_ziel_policy()

        self.assertEqual(policy["status"], "missing")
        self.assertFalse(policy["loaded"])
        self.assertEqual(policy["principle_count"], 0)
        self.assertIn("guardrails", policy)
        self.assertIn("ToolBridge", ziel_policy.ziel_policy_context_block(policy))


if __name__ == "__main__":
    unittest.main()
