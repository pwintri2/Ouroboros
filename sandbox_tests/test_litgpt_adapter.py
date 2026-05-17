import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestLitGPTAdapter(unittest.TestCase):
    def test_lora_finetune_uses_current_batch_size_args(self):
        from controller import litgpt_adapter
        from controller.trainer_jobs import TrainerMethod, create_job

        previous_workspace = os.environ.get("WINTRIP_WORKSPACE")
        try:
            with tempfile.TemporaryDirectory(prefix="litgpt-adapter-") as tmp:
                os.environ["WINTRIP_WORKSPACE"] = tmp
                job = create_job(
                    base_model="checkpoints/test-model",
                    method=TrainerMethod.LITGPT,
                    batch_size=2,
                    epochs=1,
                )
                captured: dict[str, list[str]] = {}

                def fake_run(cmd_parts, **_kwargs):
                    captured["cmd"] = list(cmd_parts)
                    return SimpleNamespace(returncode=2, stdout="", stderr="intentional test failure")

                with (
                    patch.object(litgpt_adapter, "get_litgpt_args", return_value=["litgpt"]),
                    patch.object(litgpt_adapter.subprocess, "run", side_effect=fake_run),
                ):
                    result = litgpt_adapter.run_litgpt_lora_finetune(
                        job_id=job["job_id"],
                        base_model="checkpoints/test-model",
                        dataset_path="/workspace/out/continuous_datasets/test.jsonl",
                        batch_size=2,
                        epochs=1,
                    )

                self.assertEqual(result["status"], "error")
                cmd = captured["cmd"]
                self.assertNotIn("--train.batch_size", cmd)
                self.assertEqual(cmd[cmd.index("--train.micro_batch_size") + 1], "2")
                self.assertEqual(cmd[cmd.index("--train.global_batch_size") + 1], "2")
        finally:
            if previous_workspace is None:
                os.environ.pop("WINTRIP_WORKSPACE", None)
            else:
                os.environ["WINTRIP_WORKSPACE"] = previous_workspace


if __name__ == "__main__":
    unittest.main()
