import os
import sys
import tempfile
import textwrap
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


class TestCodexRegistry(unittest.TestCase):
    def test_registry_discovers_and_calls_safe_public_functions(self):
        from controller.codex_registry import call_codex_function, list_codex_functions

        previous = {
            "WINTRIP_CODEX_PATH": os.environ.get("WINTRIP_CODEX_PATH"),
            "WINTRIP_CODEX_ALLOWED_SUBDIRS": os.environ.get("WINTRIP_CODEX_ALLOWED_SUBDIRS"),
            "WINTRIP_WORKSPACE": os.environ.get("WINTRIP_WORKSPACE"),
        }
        try:
            with tempfile.TemporaryDirectory(prefix="codex-registry-") as tmp:
                root = Path(tmp)
                workspace = root / "workspace"
                workspace.mkdir()
                (root / "safe_math.py").write_text(
                    textwrap.dedent(
                        """
                        from pathlib import Path

                        def add_values(left: int, right: int) -> int:
                            \"\"\"Add two JSON numbers.\"\"\"
                            return left + right

                        def _private_value() -> int:
                            return 99

                        def unsafe_write(path: str, text: str) -> str:
                            \"\"\"Write text to disk.\"\"\"
                            Path(path).write_text(text)
                            return path
                        """
                    ),
                    encoding="utf-8",
                )
                helpers = root / "helpers"
                helpers.mkdir()
                (helpers / "text_tools.py").write_text(
                    textwrap.dedent(
                        """
                        def shout(text: str) -> str:
                            \"\"\"Return uppercase text.\"\"\"
                            return text.upper()
                        """
                    ),
                    encoding="utf-8",
                )

                os.environ["WINTRIP_CODEX_PATH"] = str(root)
                os.environ["WINTRIP_CODEX_ALLOWED_SUBDIRS"] = "helpers"
                os.environ["WINTRIP_WORKSPACE"] = str(workspace)

                listing = list_codex_functions()
                names = {item["name"] for item in listing["functions"]}
                self.assertIn("safe_math.add_values", names)
                self.assertIn("helpers.text_tools.shout", names)
                self.assertNotIn("safe_math._private_value", names)
                self.assertNotIn("safe_math.unsafe_write", names)

                result = call_codex_function("safe_math.add_values", args=[2, 5])
                self.assertEqual(result["status"], "success")
                self.assertEqual(result["result"], 7)

                bare = call_codex_function("shout", args=["wintrip"])
                self.assertEqual(bare["status"], "success")
                self.assertEqual(bare["result"], "WINTRIP")

                invalid = call_codex_function("missing_function")
                self.assertEqual(invalid["status"], "error")
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


@unittest.skipIf(FastAPI is None or TestClient is None, MISSING_FASTAPI)
class TestCodexRegistryRoutes(unittest.TestCase):
    def test_codex_routes_list_functions_and_require_approval_for_calls(self):
        from controller.api.trainer_pipeline_routes import init_trainer_pipeline

        previous = {
            "WINTRIP_CODEX_PATH": os.environ.get("WINTRIP_CODEX_PATH"),
            "WINTRIP_CODEX_ALLOWED_SUBDIRS": os.environ.get("WINTRIP_CODEX_ALLOWED_SUBDIRS"),
            "WINTRIP_WORKSPACE": os.environ.get("WINTRIP_WORKSPACE"),
        }
        try:
            with tempfile.TemporaryDirectory(prefix="codex-registry-routes-") as tmp:
                root = Path(tmp)
                workspace = root / "workspace"
                workspace.mkdir()
                (root / "safe_text.py").write_text(
                    textwrap.dedent(
                        """
                        def echo(text: str) -> str:
                            \"\"\"Echo JSON text.\"\"\"
                            return text
                        """
                    ),
                    encoding="utf-8",
                )
                os.environ["WINTRIP_CODEX_PATH"] = str(root)
                os.environ["WINTRIP_CODEX_ALLOWED_SUBDIRS"] = ""
                os.environ["WINTRIP_WORKSPACE"] = str(workspace)

                app = FastAPI()
                init_trainer_pipeline(app)
                client = TestClient(app)

                listed = client.get("/trainer/codex/functions")
                self.assertEqual(listed.status_code, 200)
                self.assertEqual(listed.json()["count"], 1)

                blocked = client.post(
                    "/trainer/codex/call",
                    json={"approval": "nee", "function": "safe_text.echo", "args": ["x"]},
                )
                self.assertEqual(blocked.status_code, 403)

                called = client.post(
                    "/trainer/codex/call",
                    json={"approval": "Akkoord", "function": "safe_text.echo", "args": ["ok"]},
                )
                self.assertEqual(called.status_code, 200)
                self.assertEqual(called.json()["result"], "ok")
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
