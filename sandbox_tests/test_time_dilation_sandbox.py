import asyncio
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from controller.sandbox import DreamCycle, TimeDilationSandbox


class FakeSandboxExecutor:
    def __init__(self):
        self.calls = []

    async def arun_python_code(self, code, timeout=15, return_dict=True, task_name="", allow_network=False):
        self.calls.append({
            "code": code,
            "timeout": timeout,
            "return_dict": return_dict,
            "task_name": task_name,
            "allow_network": allow_network,
        })
        await asyncio.sleep(0.01)
        return {
            "status": "error" if "FAIL" in code else "success",
            "logs": code,
            "exit_code": 1 if "FAIL" in code else 0,
            "error_type": "runtime_error" if "FAIL" in code else None,
        }


class TimeDilationSandboxTests(unittest.IsolatedAsyncioTestCase):
    async def test_runs_cycles_concurrently_with_virtual_time(self):
        executor = FakeSandboxExecutor()
        sandbox = TimeDilationSandbox(
            executor=executor,
            max_parallel=3,
            virtual_time_scale=1000,
            fail_fast=False,
        )

        started = time.perf_counter()
        result = await sandbox.run_dream([
            DreamCycle(name="Developer", code="print('dev')"),
            DreamCycle(name="Critic", code="print('critic')"),
            DreamCycle(name="Tester", code="print('tester')"),
        ])
        physical = time.perf_counter() - started

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["cycles_completed"], 3)
        self.assertLess(physical, 0.08)
        self.assertGreater(result["virtual_seconds"], result["physical_seconds"])
        self.assertTrue(result["sandbox_isolated"])
        self.assertTrue(all(item["sandbox_isolated"] for item in result["results"]))

    async def test_fail_fast_cancels_remaining_dream_cycles(self):
        executor = FakeSandboxExecutor()
        sandbox = TimeDilationSandbox(
            executor=executor,
            max_parallel=1,
            virtual_time_scale=1000,
            fail_fast=True,
        )

        result = await sandbox.run_dream([
            DreamCycle(name="Developer", code="FAIL"),
            DreamCycle(name="Critic", code="print('critic')"),
        ])

        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["cycles_completed"], 1)
        self.assertEqual(result["results"][0]["cycle"], "Developer")
        self.assertTrue(result["results"][0]["network_disabled"])


if __name__ == "__main__":
    unittest.main()
