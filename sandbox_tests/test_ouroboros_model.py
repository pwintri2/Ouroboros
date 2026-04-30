import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from controller.ouroboros_model import (
    MODEL_NAME,
    PREFERRED_BASE_MODEL,
    create_ouroboros_model,
    prepare_ouroboros_create,
    render_modelfile,
    select_base_model,
    validate_modelfile,
)


class TestOuroborosModel(unittest.TestCase):
    def test_modelfile_contains_identity_and_safety_contract(self):
        content = render_modelfile(base_model=PREFERRED_BASE_MODEL)

        self.assertIn("FROM llama3.2:latest", content)
        self.assertIn("Ouroboros leert zichzelf trainen", content)
        self.assertIn("mentoren", content)
        self.assertIn("UNTRUSTED", content)
        self.assertIn("ontbrekende kennis", content)
        self.assertIn("approval-gated tools", content)
        self.assertIn("Akkoord", content)
        self.assertEqual(validate_modelfile(content, base_model=PREFERRED_BASE_MODEL), ())

    def test_select_base_model_prefers_llama32_when_available(self):
        selected = select_base_model(["phi3:latest", "llama3.2:latest", "llama3:latest"])
        self.assertEqual(selected, "llama3.2:latest")

    def test_prepare_writes_modelfile_and_prepares_create_command(self):
        with tempfile.TemporaryDirectory(prefix="ouroboros-model-") as tmpdir:
            plan = prepare_ouroboros_create(root=tmpdir, available_models=["llama3.2:latest"])

            self.assertTrue(plan.valid)
            self.assertTrue(plan.wrote_modelfile)
            self.assertEqual(plan.model_name, MODEL_NAME)
            self.assertEqual(plan.base_model, "llama3.2:latest")
            self.assertEqual(plan.command[:3], ("ollama", "create", "ouroboros"))
            self.assertIn("ollama create ouroboros -f", plan.command_text)
            self.assertTrue(os.path.exists(plan.modelfile_path))

    def test_create_flow_is_prepared_only_by_default(self):
        with tempfile.TemporaryDirectory(prefix="ouroboros-model-") as tmpdir:
            plan = create_ouroboros_model(root=tmpdir, available_models=["llama3.2:latest"])

            self.assertEqual(plan.execution_status, "prepared_only")
            self.assertIsNone(plan.execution_result)

    def test_execute_requires_approval_before_safe_runner(self):
        calls = []

        def fake_runner(command, approval, timeout):
            calls.append((command, approval, timeout))
            return {"status": "success", "approved": True, "command": command}

        with tempfile.TemporaryDirectory(prefix="ouroboros-model-") as tmpdir:
            blocked = create_ouroboros_model(
                root=tmpdir,
                available_models=["llama3.2:latest"],
                execute=True,
                approval="nee",
                safe_shell_runner=fake_runner,
            )
            self.assertEqual(blocked.execution_status, "blocked_approval_required")
            self.assertEqual(calls, [])

            executed = create_ouroboros_model(
                root=tmpdir,
                available_models=["llama3.2:latest"],
                execute=True,
                approval="Akkoord",
                safe_shell_runner=fake_runner,
            )
            self.assertEqual(executed.execution_status, "executed_via_safe_shell")
            self.assertEqual(len(calls), 1)
            self.assertIn("ollama create ouroboros -f", calls[0][0])


if __name__ == "__main__":
    unittest.main()
