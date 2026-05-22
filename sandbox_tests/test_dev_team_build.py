"""Sandbox tests for the dev-team Aider-modus build loop."""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestDevTeamBuildExtractors(unittest.TestCase):
    def setUp(self) -> None:
        from controller import dev_team_build

        self.mod = dev_team_build

    def test_extract_file_blocks_handles_double_quotes(self) -> None:
        content = (
            "Ik schrijf de skeleton.\n"
            "<file path=\"src/main.py\">\n"
            "def main():\n"
            "    print(\"hi\")\n"
            "</file>\n"
            "Vraag aan tester?\n"
        )
        blocks = self.mod.extract_file_blocks(content)
        self.assertEqual(len(blocks), 1)
        path, body = blocks[0]
        self.assertEqual(path, "src/main.py")
        self.assertIn('print("hi")', body)
        self.assertFalse(body.startswith("\n"))
        self.assertFalse(body.endswith("\n"))

    def test_extract_file_blocks_handles_multiple_files(self) -> None:
        content = (
            "<file path=\"a.py\">print(1)</file>\n"
            "<file path='b.py'>print(2)</file>\n"
            "<file path=\"sub/c.py\">print(3)</file>\n"
        )
        blocks = self.mod.extract_file_blocks(content)
        paths = [path for path, _ in blocks]
        self.assertEqual(paths, ["a.py", "b.py", "sub/c.py"])

    def test_extract_file_blocks_ignores_missing_path(self) -> None:
        content = "<file>just body, no path</file>"
        self.assertEqual(self.mod.extract_file_blocks(content), [])

    def test_extract_cmd_block_picks_first_one_liner(self) -> None:
        content = (
            "Testcommando:\n"
            "<cmd>python -m pytest tests/test_main.py -v</cmd>\n"
            "Verwacht: exit 0."
        )
        self.assertEqual(
            self.mod.extract_cmd_block(content),
            "python -m pytest tests/test_main.py -v",
        )

    def test_extract_cmd_block_collapses_to_first_nonempty_line(self) -> None:
        content = "<cmd>\n\npytest -v\n\nignored second line\n</cmd>"
        self.assertEqual(self.mod.extract_cmd_block(content), "pytest -v")

    def test_extract_cmd_block_returns_empty_when_absent(self) -> None:
        self.assertEqual(self.mod.extract_cmd_block("geen commando hier"), "")


class TestDevTeamBuildFileWrites(unittest.TestCase):
    def setUp(self) -> None:
        from controller import dev_team_build

        self.mod = dev_team_build
        self.tmp = tempfile.TemporaryDirectory(prefix="dev-team-build-tests-")
        self.workspace = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_write_files_creates_nested_paths_safely(self) -> None:
        writes = self.mod.write_files(
            self.workspace,
            [
                ("src/cli.py", "print('hi')\n"),
                ("tests/sub/test_cli.py", "def test_dummy(): pass\n"),
            ],
        )
        self.assertEqual(len(writes), 2)
        self.assertTrue((self.workspace / "src" / "cli.py").is_file())
        self.assertTrue((self.workspace / "tests" / "sub" / "test_cli.py").is_file())

    def test_write_files_refuses_path_escape(self) -> None:
        writes = self.mod.write_files(
            self.workspace,
            [
                ("../outside.txt", "bad"),
                ("/etc/passwd", "bad"),
                ("good.py", "print('hi')"),
            ],
        )
        self.assertEqual([w.path for w in writes], ["good.py"])
        self.assertFalse((self.workspace.parent / "outside.txt").exists())

    def test_write_files_truncates_oversized_content(self) -> None:
        oversized = "x" * (self.mod.MAX_FILE_BYTES + 5000)
        writes = self.mod.write_files(
            self.workspace,
            [("big.txt", oversized)],
            max_file_bytes=self.mod.MAX_FILE_BYTES,
        )
        self.assertEqual(len(writes), 1)
        self.assertTrue(writes[0].truncated)
        self.assertEqual(writes[0].bytes_written, self.mod.MAX_FILE_BYTES)


class TestDevTeamBuildRunCommand(unittest.TestCase):
    def setUp(self) -> None:
        from controller import dev_team_build

        self.mod = dev_team_build
        self.tmp = tempfile.TemporaryDirectory(prefix="dev-team-build-run-")
        self.workspace = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_run_command_captures_stdout_and_exit(self) -> None:
        result = self.mod.run_test_command(self.workspace, "echo 'hello world'", timeout=10)
        self.assertEqual(result.exit_code, 0)
        self.assertIn("hello world", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_run_command_captures_nonzero_exit(self) -> None:
        result = self.mod.run_test_command(self.workspace, "false", timeout=10)
        self.assertNotEqual(result.exit_code, 0)

    def test_run_command_rejects_dangerous_command(self) -> None:
        result = self.mod.run_test_command(self.workspace, "sudo rm -rf /", timeout=10)
        self.assertEqual(result.exit_code, -2)
        self.assertIn("safety", result.stderr.lower())

    def test_run_command_times_out_cleanly(self) -> None:
        result = self.mod.run_test_command(self.workspace, "sleep 5", timeout=0.5)
        self.assertEqual(result.exit_code, -3)
        self.assertTrue(result.timed_out)


class TestDevTeamBuildSession(unittest.TestCase):
    def setUp(self) -> None:
        from controller import dev_team_build

        self.mod = dev_team_build
        self.tmp = tempfile.TemporaryDirectory(prefix="dev-team-build-session-")
        self.workspace = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _personas(self) -> dict[str, dict[str, Any]]:
        return {
            "developer": {
                "id": "de-developer",
                "name": "De Developper",
                "system_prompt": "Je bent de Developper.",
            },
            "tester": {
                "id": "de-tester",
                "name": "De Tester",
                "system_prompt": "Je bent de Tester.",
            },
            "criticus": {
                "id": "de-criticus",
                "name": "Criticus",
                "system_prompt": "Je bent de Criticus.",
            },
            "chair": {
                "id": "de-voorzitter",
                "name": "De voorzitter",
                "system_prompt": "Je bent de Voorzitter.",
            },
        }

    def test_llm_timeout_returns_without_waiting_for_worker_completion(self) -> None:
        def slow_llm(**kwargs: Any) -> dict[str, Any]:
            time.sleep(1.0)
            return {"ok": True, "content": "late", "error": ""}

        session = self.mod.DevTeamBuildSession(
            session_id="llm-timeout",
            workspace=self.workspace,
            llm_call=slow_llm,
            max_iterations=1,
            test_timeout=20,
        )
        session.llm_timeout_seconds = 0.1

        started = time.monotonic()
        result = session._call_llm(
            user_prompt="bouw iets",
            system_prompt="Je bent de Developper.",
            provider="ollama",
            model="slow:latest",
            persona=self._personas()["developer"],
        )
        elapsed = time.monotonic() - started

        self.assertFalse(result["ok"])
        self.assertIn("timed out", result["error"])
        self.assertLess(elapsed, 0.75)

    def test_session_completes_in_one_iteration_when_first_test_is_green(self) -> None:
        """Developer writes a passing test, Tester runs it, build goes green immediately."""

        def fake_llm(**kwargs: Any) -> dict[str, Any]:
            system_prompt = str(kwargs.get("system_prompt") or "")
            if system_prompt.startswith("Je bent de Developper."):
                return {
                    "ok": True,
                    "content": (
                        "Ik schrijf de skeleton.\n"
                        "<file path=\"src/dummy.py\">\n"
                        "def value():\n"
                        "    return 4\n"
                        "</file>\n"
                        "Vraag aan De Tester: hoe verifieer je?"
                    ),
                    "error": "",
                }
            if system_prompt.startswith("Je bent de Tester."):
                # Use a shell test that doesn't depend on pytest being installed in the sandbox.
                return {
                    "ok": True,
                    "content": (
                        "Verifieer dat dummy.value() == 4.\n"
                        "<cmd>python3 -c \"import sys; sys.path.insert(0,'src'); from dummy import value; assert value() == 4; print('PASS')\"</cmd>\n"
                        "Verwacht: stdout bevat PASS."
                    ),
                    "error": "",
                }
            if system_prompt.startswith("Je bent de Voorzitter."):
                # Chair declares the build complete after the first green test.
                return {
                    "ok": True,
                    "content": '{"verdict": "DONE", "reason": "Eerste passing test bewijst dummy.value()."}',
                    "error": "",
                }
            return {"ok": True, "content": "leeg", "error": ""}

        session = self.mod.DevTeamBuildSession(
            session_id="green-on-first",
            workspace=self.workspace,
            llm_call=fake_llm,
            max_iterations=3,
            test_timeout=20,
        )
        events = list(
            session.iterate(
                build_prompt="Schrijf een passing dummy test",
                clarifications=[],
                provider="ollama",
                model="ouroboros:latest",
                personas=self._personas(),
            )
        )
        types = [event.type for event in events]
        self.assertIn("build_started", types)
        self.assertIn("developer_turn", types)
        self.assertIn("files_written", types)
        self.assertIn("tester_turn", types)
        self.assertIn("test_run", types)
        self.assertIn("build_complete", types)
        # Criticus should NOT have fired because the first iteration went green.
        self.assertNotIn("critic_turn", types)
        # File landed on disk.
        self.assertTrue((self.workspace / "src" / "dummy.py").is_file())
        # The test_run event reports green.
        test_run = next(event for event in events if event.type == "test_run")
        self.assertEqual(test_run.data["exit_code"], 0)
        self.assertTrue(test_run.data["green"])

    def test_session_iterates_on_red_then_passes(self) -> None:
        """First iteration writes a failing test; after critic feedback, second pass goes green."""

        developer_responses = iter(
            [
                # Iteration 1 — broken assertion (will fail when run via python3 -c)
                (
                    "Ik begin met een rode implementatie om te kalibreren.\n"
                    "<file path=\"src/calc.py\">\n"
                    "def add(a, b):\n"
                    "    return a + b + 1\n"
                    "</file>\n"
                ),
                # Iteration 2 — fix
                (
                    "Ik corrigeer de + 1 bug.\n"
                    "<file path=\"src/calc.py\">\n"
                    "def add(a, b):\n"
                    "    return a + b\n"
                    "</file>\n"
                ),
            ]
        )

        def fake_llm(**kwargs: Any) -> dict[str, Any]:
            system_prompt = str(kwargs.get("system_prompt") or "")
            if system_prompt.startswith("Je bent de Developper."):
                return {"ok": True, "content": next(developer_responses), "error": ""}
            if system_prompt.startswith("Je bent de Tester."):
                return {
                    "ok": True,
                    "content": (
                        "Verifieer add(2,2)==4.\n"
                        "<cmd>python3 -c \"import sys; sys.path.insert(0,'src'); from calc import add; assert add(2,2) == 4; print('GREEN')\"</cmd>"
                    ),
                    "error": "",
                }
            if system_prompt.startswith("Je bent de Criticus."):
                return {
                    "ok": True,
                    "content": "AssertionError op add(2,2). De functie telt er +1 bij. Vervang `return a + b + 1` door `return a + b`.",
                    "error": "",
                }
            if system_prompt.startswith("Je bent de Voorzitter."):
                return {
                    "ok": True,
                    "content": '{"verdict": "DONE", "reason": "calc.add(2,2)==4 bewijst het bouwdoel."}',
                    "error": "",
                }
            return {"ok": True, "content": "leeg", "error": ""}

        session = self.mod.DevTeamBuildSession(
            session_id="red-then-green",
            workspace=self.workspace,
            llm_call=fake_llm,
            max_iterations=3,
            test_timeout=20,
        )
        events = list(
            session.iterate(
                build_prompt="Schrijf een test die 2+2 verifieert",
                clarifications=[],
                provider="ollama",
                model="ouroboros:latest",
                personas=self._personas(),
            )
        )
        types = [event.type for event in events]
        # Two developer turns, two file writes, two test runs, one critic turn, one complete.
        self.assertEqual(types.count("developer_turn"), 2)
        self.assertEqual(types.count("test_run"), 2)
        self.assertEqual(types.count("critic_turn"), 1)
        self.assertEqual(types.count("build_complete"), 1)

        first_run = next(event for event in events if event.type == "test_run")
        last_run = [event for event in events if event.type == "test_run"][-1]
        self.assertNotEqual(first_run.data["exit_code"], 0)
        self.assertEqual(last_run.data["exit_code"], 0)

    def test_session_continues_after_first_green_when_chair_says_continue(self) -> None:
        """First green test should NOT end the build if the chair says CONTINUE."""

        developer_responses = iter(
            [
                # Iter 1: write minimal add() — passes basic test
                (
                    "Ik schrijf de eerste functie.\n"
                    "<file path=\"src/calc.py\">\n"
                    "def add(a, b):\n"
                    "    return a + b\n"
                    "</file>\n"
                ),
                # Iter 2: add subtract() per chair's directive
                (
                    "Ik voeg subtract toe.\n"
                    "<file path=\"src/calc.py\">\n"
                    "def add(a, b):\n"
                    "    return a + b\n"
                    "\n"
                    "def subtract(a, b):\n"
                    "    return a - b\n"
                    "</file>\n"
                ),
            ]
        )
        chair_responses = iter(
            [
                # After iter 1: still need subtract
                '{"verdict": "CONTINUE", "reason": "Alleen add() bestaat; subtract ontbreekt.", "next_subtask": "Voeg subtract(a,b) toe in src/calc.py."}',
                # After iter 2: done
                '{"verdict": "DONE", "reason": "Beide functies werken en zijn getest."}',
            ]
        )
        tester_responses = iter(
            [
                "<cmd>python3 -c \"import sys; sys.path.insert(0,'src'); from calc import add; assert add(2,2) == 4; print('OK')\"</cmd>",
                "<cmd>python3 -c \"import sys; sys.path.insert(0,'src'); from calc import add, subtract; assert add(2,2) == 4 and subtract(5,3) == 2; print('OK')\"</cmd>",
            ]
        )

        def fake_llm(**kwargs: Any) -> dict[str, Any]:
            system_prompt = str(kwargs.get("system_prompt") or "")
            if system_prompt.startswith("Je bent de Developper."):
                return {"ok": True, "content": next(developer_responses), "error": ""}
            if system_prompt.startswith("Je bent de Tester."):
                return {"ok": True, "content": next(tester_responses), "error": ""}
            if system_prompt.startswith("Je bent de Voorzitter."):
                return {"ok": True, "content": next(chair_responses), "error": ""}
            return {"ok": True, "content": "leeg", "error": ""}

        session = self.mod.DevTeamBuildSession(
            session_id="multi-step-add-subtract",
            workspace=self.workspace,
            llm_call=fake_llm,
            max_iterations=4,
            test_timeout=20,
        )
        events = list(
            session.iterate(
                build_prompt="Bouw een calc-module met add EN subtract functies.",
                clarifications=[],
                provider="ollama",
                model="ouroboros:latest",
                personas=self._personas(),
            )
        )
        types = [event.type for event in events]
        # Two iterations because chair said CONTINUE after the first.
        self.assertEqual(types.count("developer_turn"), 2)
        self.assertEqual(types.count("test_run"), 2)
        self.assertEqual(types.count("chair_review"), 2)
        self.assertEqual(types.count("build_complete"), 1)
        self.assertNotIn("critic_turn", types)  # both tests went green

        # The first chair_review was CONTINUE.
        chair_events = [event for event in events if event.type == "chair_review"]
        self.assertEqual(chair_events[0].data["verdict"], "CONTINUE")
        self.assertIn("subtract", chair_events[0].data["next_subtask"].lower())
        self.assertEqual(chair_events[1].data["verdict"], "DONE")

        # Final file has both functions.
        final = (self.workspace / "src" / "calc.py").read_text()
        self.assertIn("def add", final)
        self.assertIn("def subtract", final)

    def test_session_exhausts_after_max_iterations(self) -> None:
        """Tests stay red — we expect exactly `max_iterations` developer turns then build_exhausted."""

        def fake_llm(**kwargs: Any) -> dict[str, Any]:
            system_prompt = str(kwargs.get("system_prompt") or "")
            if system_prompt.startswith("Je bent de Developper."):
                return {
                    "ok": True,
                    "content": (
                        "<file path=\"src/wrong.py\">\n"
                        "def value():\n"
                        "    return 0\n"
                        "</file>\n"
                    ),
                    "error": "",
                }
            if system_prompt.startswith("Je bent de Tester."):
                return {
                    "ok": True,
                    "content": (
                        "<cmd>python3 -c \"import sys; sys.path.insert(0,'src'); from wrong import value; assert value() == 4\"</cmd>"
                    ),
                    "error": "",
                }
            if system_prompt.startswith("Je bent de Criticus."):
                return {"ok": True, "content": "Blijft rood.", "error": ""}
            if system_prompt.startswith("Je bent de Voorzitter."):
                return {"ok": True, "content": '{"verdict": "DONE"}', "error": ""}
            return {"ok": True, "content": "leeg", "error": ""}

        session = self.mod.DevTeamBuildSession(
            session_id="never-green",
            workspace=self.workspace,
            llm_call=fake_llm,
            max_iterations=2,
            test_timeout=20,
        )
        events = list(
            session.iterate(
                build_prompt="probeer iets",
                clarifications=[],
                provider="ollama",
                model="ouroboros:latest",
                personas=self._personas(),
            )
        )
        types = [event.type for event in events]
        self.assertEqual(types.count("developer_turn"), 2)
        self.assertEqual(types.count("test_run"), 2)
        self.assertEqual(types.count("critic_turn"), 2)
        self.assertNotIn("build_complete", types)
        self.assertIn("build_exhausted", types)


if __name__ == "__main__":
    unittest.main()
