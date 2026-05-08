import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from controller.computer_actions import computer_actions_status, run_computer_action


class TestComputerActions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="computer-actions-")
        self.root = Path(self.tmp.name)
        self.old_workspace = os.environ.get("WINTRIP_WORKSPACE")
        self.old_bridge_url = os.environ.get("WINTRIP_RCLONE_BRIDGE_URL")
        self.old_bridge_token = os.environ.get("WINTRIP_RCLONE_BRIDGE_TOKEN_PATH")
        os.environ["WINTRIP_WORKSPACE"] = str(self.root)
        os.environ.pop("WINTRIP_RCLONE_BRIDGE_URL", None)
        os.environ.pop("WINTRIP_RCLONE_BRIDGE_TOKEN_PATH", None)

    def tearDown(self):
        self.tmp.cleanup()
        self._restore("WINTRIP_WORKSPACE", self.old_workspace)
        self._restore("WINTRIP_RCLONE_BRIDGE_URL", self.old_bridge_url)
        self._restore("WINTRIP_RCLONE_BRIDGE_TOKEN_PATH", self.old_bridge_token)

    def test_status_exposes_typed_actions_without_secrets(self):
        status = computer_actions_status()

        self.assertEqual(status["status"], "online")
        self.assertIn("read_file", status["canonical_tools"])
        self.assertIn("list_files", status["canonical_tools"])
        self.assertIn("search_files", status["canonical_tools"])
        self.assertIn("run_tests", status["canonical_tools"])
        self.assertIn("host_status", status["canonical_tools"])
        self.assertIn("write_file", status["approval_required_for"])
        self.assertFalse(status["secrets_returned"])

    def test_file_read_list_search_and_secret_redaction(self):
        Path(self.root, "alpha.txt").write_text("API_KEY=supersecret123456\nneedle here\n", encoding="utf-8")

        listed = run_computer_action("list_files", {"path": "."})
        searched = run_computer_action("search_files", {"path": ".", "regex": "needle"})
        read = run_computer_action("read_file", {"path": "alpha.txt"})

        self.assertEqual(listed["status"], "success")
        self.assertIn("alpha.txt", listed["stdout"])
        self.assertEqual(searched["status"], "success")
        self.assertEqual(searched["result"]["count"], 1)
        self.assertEqual(read["status"], "success")
        self.assertIn("API_KEY=[REDACTED]", read["stdout"])
        self.assertNotIn("supersecret123456", json.dumps(read))

    def test_write_and_safe_shell_require_exact_akkoord(self):
        blocked = run_computer_action("write_file", {"path": "x.txt", "content": "x"})
        shell_blocked = run_computer_action("safe_shell", {"command": "pwd"})
        approved = run_computer_action("write_file", {"path": "x.txt", "content": "x", "approval": "Akkoord"})

        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(shell_blocked["status"], "blocked")
        self.assertEqual(approved["status"], "success")
        self.assertEqual(Path(self.root, "x.txt").read_text(encoding="utf-8"), "x")

    def test_run_tests_wraps_unittest(self):
        Path(self.root, "test_sample.py").write_text(
            "import unittest\n\n"
            "class TestSample(unittest.TestCase):\n"
            "    def test_ok(self):\n"
            "        self.assertTrue(True)\n",
            encoding="utf-8",
        )

        result = run_computer_action("run_tests", {"selector": "test_sample", "approval": "Akkoord"})

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["result"]["test_command"], "python3 -m unittest test_sample")

    def test_host_status_reports_unavailable_without_bridge_config(self):
        result = run_computer_action("host_status", {})

        self.assertEqual(result["status"], "unavailable")
        self.assertFalse(result["fake_success"])

    def test_host_bridge_computer_endpoints(self):
        import scripts.rclone_host_bridge as bridge

        bridge.WORKSPACE = self.root
        bridge.TOKEN_PATH = self.root / ".secrets" / "rclone_bridge_token"
        token = bridge.ensure_bridge_token()
        server = bridge.FastThreadingHTTPServer(("127.0.0.1", 0), bridge.RcloneBridgeHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base_url = f"http://127.0.0.1:{server.server_port}"

        status = self._request_json(base_url + "/computer/status", token=token)
        listed = self._request_json(
            base_url + "/computer/action",
            token=token,
            body={"action": "list_files", "args": {"path": "."}},
        )
        blocked = self._request_json(
            base_url + "/computer/action",
            token=token,
            body={"action": "run_command", "args": {"command": "pwd"}},
            expect_http_error=403,
        )
        host_open_blocked = self._request_json(
            base_url + "/computer/action",
            token=token,
            body={"action": "host_open_url", "args": {"url": "https://example.com"}},
            expect_http_error=403,
        )

        self.assertEqual(status["status"], "online")
        self.assertEqual(status["host_bridge_runtime"]["status"], "online")
        self.assertEqual(listed["status"], "success")
        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(host_open_blocked["status"], "blocked")

    def _request_json(
        self,
        url: str,
        *,
        token: str,
        body: dict[str, object] | None = None,
        expect_http_error: int | None = None,
    ) -> dict[str, object]:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(
            url,
            data=data,
            method="POST" if body is not None else "GET",
            headers={"Content-Type": "application/json", "X-Ouroboros-Bridge-Token": token},
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if expect_http_error is None or exc.code != expect_http_error:
                raise
            return json.loads(exc.read().decode("utf-8"))

    @staticmethod
    def _restore(key: str, value: str | None) -> None:
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
