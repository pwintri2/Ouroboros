import os
import tempfile
import unittest

from controller.self_programming_loop import resolve_or_build_function


class FakeRegistry:
    def __init__(self, tools):
        self.tools = list(tools)
        self.calls = []

    def status(self):
        return {"available_tools": self.tools}

    def run_tool(self, tool_name, args=None):
        self.calls.append((tool_name, dict(args or {})))
        return {"status": "success", "tool_name": tool_name, "stdout": "executed", "stderr": "", "result": dict(args or {})}


class TestSelfProgrammingLoop(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="self-programming-loop-")
        self.addCleanup(self.tmp.cleanup)
        self.old_workspace = os.environ.get("WINTRIP_WORKSPACE")
        os.environ["WINTRIP_WORKSPACE"] = self.tmp.name

    def tearDown(self):
        if self.old_workspace is None:
            os.environ.pop("WINTRIP_WORKSPACE", None)
        else:
            os.environ["WINTRIP_WORKSPACE"] = self.old_workspace

    def test_resolves_existing_agent_tool_without_building(self):
        registry = FakeRegistry(["memory_search"])

        result = resolve_or_build_function(
            "memory_search",
            function_args={"query": "Ouroboros"},
            execute_after_build=True,
            agent_registry=registry,
            codex_lister=lambda: {"status": "success", "functions": []},
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["phase"], "executed_existing")
        self.assertEqual(result["discovery"]["source"], "agent_tool_registry")
        self.assertEqual(registry.calls, [("memory_search", {"query": "Ouroboros"})])
        self.assertNotIn("build", result)

    def test_missing_capability_blocks_build_without_exact_akkoord_after_brave_context(self):
        calls = []

        def brave(query, limit):
            calls.append(("brave", query, limit))
            return {"status": "success", "llm_context": "api_key=supersecret123456789"}

        def shell_runner(*_args, **_kwargs):
            raise AssertionError("safe shell should not run without exact Akkoord")

        result = resolve_or_build_function(
            "new_magic_tool",
            approval="akkoord",
            agent_registry=FakeRegistry([]),
            codex_lister=lambda: {"status": "success", "functions": []},
            brave_context_fetcher=brave,
            shell_runner=shell_runner,
            codex_available_checker=lambda: {"status": "available", "available": True},
            codex_job_starter=lambda *_args: {"status": "success"},
        )

        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["phase"], "approval_required_for_build")
        self.assertEqual(result["approval_status"], "pending_philip_akkoord")
        self.assertEqual(calls[0][0], "brave")
        self.assertNotIn("supersecret123456789", str(result))
        self.assertNotIn("build", result)

    def test_codex_build_runs_before_tests_then_rediscovery_and_execution(self):
        events = []
        lister_calls = {"count": 0}

        def lister():
            lister_calls["count"] += 1
            if lister_calls["count"] == 1:
                return {"status": "success", "functions": []}
            return {
                "status": "success",
                "functions": [
                    {
                        "name": "helpers.new_tool",
                        "function": "new_tool",
                        "module": "helpers",
                        "callable": True,
                    }
                ],
            }

        def brave(query, limit):
            events.append(("brave", query, limit))
            return {"status": "success", "document": "Implementation context"}

        def codex_start(task, approval, timeout_seconds):
            events.append(("codex", approval, timeout_seconds, task))
            return {"status": "success", "result": {"job": {"job_id": "codex_test_1", "status": "queued"}}}

        def shell_runner(command, approval="", timeout=20):
            events.append(("shell", command, approval, timeout))
            return {"status": "success", "approved": True, "stdout": "OK", "stderr": "", "exit_code": 0}

        def codex_call(name, args=None, kwargs=None):
            events.append(("execute", name, list(args or []), dict(kwargs or {})))
            return {"status": "success", "function": name, "result": {"ok": True, "kwargs": dict(kwargs or {})}}

        result = resolve_or_build_function(
            "new_tool",
            function_args={"kwargs": {"text": "hello"}},
            approval="Akkoord",
            execute_after_build=True,
            test_selector="sandbox_tests.test_self_programming_loop",
            agent_registry=FakeRegistry([]),
            codex_lister=lister,
            codex_caller=codex_call,
            codex_available_checker=lambda: {"status": "available", "available": True},
            codex_job_starter=codex_start,
            brave_context_fetcher=brave,
            shell_runner=shell_runner,
        )

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["phase"], "executed_after_build")
        self.assertEqual([event[0] for event in events], ["brave", "codex", "shell", "execute"])
        self.assertEqual(result["rediscovery"]["source"], "codex_registry")
        self.assertEqual(result["execution"]["result"]["kwargs"], {"text": "hello"})

    def test_gemini_fallback_is_used_only_when_codex_unavailable(self):
        commands = []

        def shell_runner(command, approval="", timeout=20):
            commands.append(command)
            return {"status": "success", "approved": True, "stdout": "ok", "stderr": "", "exit_code": 0}

        result = resolve_or_build_function(
            "missing_tool",
            approval="Akkoord",
            test_selector="sandbox_tests.test_self_programming_loop",
            agent_registry=FakeRegistry([]),
            codex_lister=lambda: {"status": "success", "functions": []},
            codex_available_checker=lambda: {"status": "missing", "available": False},
            brave_context_fetcher=lambda query, limit: {"status": "success", "document": "context"},
            shell_runner=shell_runner,
        )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["phase"], "unresolved_after_green_tests")
        self.assertTrue(result["build"]["gemini_fallback"])
        self.assertTrue(commands[0].startswith("gemini "))
        self.assertTrue(commands[1].startswith("python3 -m unittest "))

    def test_failed_tests_skip_rediscovery_execution(self):
        executed = []

        def shell_runner(command, approval="", timeout=20):
            return {"status": "error", "approved": True, "stdout": "", "stderr": "failed", "exit_code": 1}

        result = resolve_or_build_function(
            "new_tool",
            approval="Akkoord",
            execute_after_build=True,
            test_selector="sandbox_tests.test_self_programming_loop",
            agent_registry=FakeRegistry([]),
            codex_lister=lambda: {"status": "success", "functions": []},
            codex_caller=lambda *args, **kwargs: executed.append((args, kwargs)) or {"status": "success"},
            codex_available_checker=lambda: {"status": "available", "available": True},
            codex_job_starter=lambda *_args: {"status": "success", "result": {"job": {"job_id": "codex_test_2"}}},
            brave_context_fetcher=lambda query, limit: {"status": "success", "document": "context"},
            shell_runner=shell_runner,
        )

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["phase"], "validation_failed")
        self.assertTrue(result["execution_skipped"])
        self.assertEqual(executed, [])


if __name__ == "__main__":
    unittest.main()
