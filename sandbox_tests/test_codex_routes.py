import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
except ModuleNotFoundError as exc:
    FastAPI = None
    TestClient = None
    MISSING_FASTAPI = f"fastapi test dependency ontbreekt: {exc}"
else:
    MISSING_FASTAPI = ""


@unittest.skipIf(FastAPI is None or TestClient is None, MISSING_FASTAPI)
class TestCodexRoutes(unittest.TestCase):
    def setUp(self) -> None:
        self.previous = {
            "WINTRIP_CODEX_PATH": os.environ.get("WINTRIP_CODEX_PATH"),
            "CODEX_HOME": os.environ.get("CODEX_HOME"),
            "WINTRIP_CODEX_BINARY": os.environ.get("WINTRIP_CODEX_BINARY"),
            "CODEX_BINARY": os.environ.get("CODEX_BINARY"),
            "WINTRIP_WORKSPACE": os.environ.get("WINTRIP_WORKSPACE"),
        }

    def tearDown(self) -> None:
        for key, value in self.previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _client_for_repo(self, repo: Path, workspace: Path) -> TestClient:
        os.environ["WINTRIP_CODEX_PATH"] = str(repo)
        os.environ["CODEX_HOME"] = str(repo / "_home")
        os.environ["WINTRIP_CODEX_BINARY"] = str(repo / "no-binary")
        os.environ["CODEX_BINARY"] = str(repo / "no-binary")
        os.environ["WINTRIP_WORKSPACE"] = str(workspace)

        from controller.api.codex_routes import init_codex_routes

        app = FastAPI()
        init_codex_routes(app)
        return TestClient(app)

    def test_status_endpoint_returns_truthful_payload(self):
        with tempfile.TemporaryDirectory(prefix="codex-routes-") as tmp:
            repo = Path(tmp) / "Codex"
            (repo / "codex-rs" / "cli").mkdir(parents=True)
            (repo / "codex-rs" / "mcp-server").mkdir(parents=True)
            (repo / "codex-rs" / "skills").mkdir(parents=True)
            workspace = Path(tmp) / "workspace"
            workspace.mkdir()

            client = self._client_for_repo(repo, workspace)
            response = client.get("/api/codex/status")
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertIn(payload["status"], {"missing", "discoverable", "binary_present_no_auth", "configured", "online"})
            self.assertEqual(payload["fake_success"], False)
            self.assertTrue(payload["repo_present"])

    def test_capabilities_endpoint_lists_subsystems(self):
        with tempfile.TemporaryDirectory(prefix="codex-routes-caps-") as tmp:
            repo = Path(tmp) / "Codex"
            (repo / "codex-rs" / "cli").mkdir(parents=True)
            (repo / "codex-rs" / "skills").mkdir(parents=True)
            workspace = Path(tmp) / "workspace"
            workspace.mkdir()

            client = self._client_for_repo(repo, workspace)
            response = client.get("/api/codex/capabilities")
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            keys = {item["key"]: item for item in payload["subsystems"]}
            self.assertIn("cli_exec", keys)
            self.assertTrue(keys["cli_exec"]["detected"])

    def test_run_endpoint_blocks_without_approval(self):
        with tempfile.TemporaryDirectory(prefix="codex-routes-run-") as tmp:
            repo = Path(tmp) / "Codex"
            (repo / "codex-rs" / "cli").mkdir(parents=True)
            workspace = Path(tmp) / "workspace"
            workspace.mkdir()

            client = self._client_for_repo(repo, workspace)
            response = client.post("/api/codex/run", json={"task": "doe iets"})
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["status"], "blocked")
            self.assertTrue(payload.get("approval_required"))
            self.assertEqual(payload["fake_success"], False)

    def test_run_endpoint_returns_503_when_binary_missing(self):
        with tempfile.TemporaryDirectory(prefix="codex-routes-no-bin-") as tmp:
            repo = Path(tmp) / "Codex"
            (repo / "codex-rs" / "cli").mkdir(parents=True)
            workspace = Path(tmp) / "workspace"
            workspace.mkdir()

            client = self._client_for_repo(repo, workspace)
            # Approval supplied but no binary present.
            response = client.post(
                "/api/codex/run",
                json={"task": "bouw iets", "approval": "Akkoord"},
            )
            self.assertEqual(response.status_code, 503)


if __name__ == "__main__":
    unittest.main()
