import os
import tempfile
import unittest
from pathlib import Path

from controller.agent_tools import AgentToolRegistry
from controller import roo_tools


class TestRooTools(unittest.TestCase):
    def setUp(self):
        self.old_workspace = os.environ.get("WINTRIP_WORKSPACE")
        self.old_ruflo = os.environ.get("WINTRIP_RUFLO_PATH")
        self.workspace = tempfile.mkdtemp(prefix="wintrip-roo-tools-")
        self.ruflo = tempfile.mkdtemp(prefix="wintrip-ruflo-tools-")
        os.environ["WINTRIP_WORKSPACE"] = self.workspace
        os.environ["WINTRIP_RUFLO_PATH"] = self.ruflo
        Path(self.workspace, "alpha.txt").write_text("first\nsecond needle\nthird\n", encoding="utf-8")
        Path(self.workspace, "nested").mkdir()
        Path(self.workspace, "nested", "beta.py").write_text("def beta():\n    return 'needle'\n", encoding="utf-8")
        Path(self.ruflo, "ruflo_note.md").write_text("Ruflo sees WintripAI needle\n", encoding="utf-8")

    def tearDown(self):
        if self.old_workspace is None:
            os.environ.pop("WINTRIP_WORKSPACE", None)
        else:
            os.environ["WINTRIP_WORKSPACE"] = self.old_workspace
        if self.old_ruflo is None:
            os.environ.pop("WINTRIP_RUFLO_PATH", None)
        else:
            os.environ["WINTRIP_RUFLO_PATH"] = self.old_ruflo

    def test_read_list_and_search_stay_inside_workspace(self):
        read = roo_tools.read_file("alpha.txt", offset=2, limit=1)
        self.assertEqual(read["status"], "success")
        self.assertEqual(read["stdout"], "second needle\n")

        listed = roo_tools.list_files(".", recursive=True)
        self.assertEqual(listed["status"], "success")
        self.assertIn("alpha.txt", listed["result"]["items"])
        self.assertIn("nested/beta.py", listed["result"]["items"])

        searched = roo_tools.search_files(".", "needle", file_pattern="*.py")
        self.assertEqual(searched["status"], "success")
        self.assertEqual(searched["result"]["count"], 1)
        self.assertEqual(searched["result"]["matches"][0]["path"], "nested/beta.py")

    def test_path_escape_is_blocked(self):
        result = roo_tools.read_file("/etc/passwd")
        self.assertEqual(result["status"], "error")
        self.assertIn("buiten /workspace", result["stderr"])

    def test_ruflo_alias_can_be_read_listed_and_searched(self):
        status = roo_tools.roo_tools_status()
        self.assertIn(self.ruflo, status["allowed_roots"])

        read = roo_tools.read_file("ruflo/ruflo_note.md")
        self.assertEqual(read["status"], "success")
        self.assertIn("Ruflo sees WintripAI", read["stdout"])

        listed = roo_tools.list_files("ruflo")
        self.assertEqual(listed["status"], "success")
        self.assertIn("ruflo/ruflo_note.md", listed["result"]["items"])

        searched = roo_tools.search_files("ruflo", "needle")
        self.assertEqual(searched["status"], "success")
        self.assertEqual(searched["result"]["matches"][0]["path"], "ruflo/ruflo_note.md")

    def test_write_file_preview_does_not_write(self):
        target = Path(self.workspace, "preview_only.txt")

        preview = roo_tools.write_file_preview("preview_only.txt", "preview\n")

        self.assertEqual(preview["status"], "success")
        self.assertIn("+preview", preview["stdout"])
        self.assertFalse(target.exists())

    def test_write_file_requires_approval_and_then_writes(self):
        blocked = roo_tools.write_file("new_tool.py", "print('ok')\n", approval="")
        self.assertEqual(blocked["status"], "blocked")
        self.assertFalse(Path(self.workspace, "new_tool.py").exists())
        self.assertIn("approval_required", blocked["result"])

        lowercase = roo_tools.write_file("new_tool.py", "print('ok')\n", approval="akkoord")
        self.assertEqual(lowercase["status"], "blocked")
        self.assertFalse(Path(self.workspace, "new_tool.py").exists())

        written = roo_tools.write_file("new_tool.py", "print('ok')\n", approval="Akkoord")
        self.assertEqual(written["status"], "success")
        self.assertEqual(Path(self.workspace, "new_tool.py").read_text(encoding="utf-8"), "print('ok')\n")

    def test_apply_patch_preview_does_not_write(self):
        patch = """*** Begin Patch
*** Update File: alpha.txt
@@
 first
-second needle
+second fixed
 third
*** End Patch
"""
        preview = roo_tools.apply_patch_preview(patch)
        self.assertEqual(preview["status"], "success")
        self.assertIn("-second needle", preview["stdout"])
        self.assertIn("second needle", Path(self.workspace, "alpha.txt").read_text(encoding="utf-8"))

    def test_apply_patch_requires_approval_and_then_applies(self):
        patch = """*** Begin Patch
*** Update File: alpha.txt
@@
 first
-second needle
+second fixed
 third
*** End Patch
"""
        blocked = roo_tools.apply_patch(patch, approval="")
        self.assertEqual(blocked["status"], "blocked")
        self.assertIn("second needle", Path(self.workspace, "alpha.txt").read_text(encoding="utf-8"))

        lowercase = roo_tools.apply_patch(patch, approval="akkoord")
        self.assertEqual(lowercase["status"], "blocked")
        self.assertIn("second needle", Path(self.workspace, "alpha.txt").read_text(encoding="utf-8"))

        applied = roo_tools.apply_patch(patch, approval="Akkoord")
        self.assertEqual(applied["status"], "success")
        self.assertIn("second fixed", Path(self.workspace, "alpha.txt").read_text(encoding="utf-8"))

    def test_apply_patch_validates_before_writing(self):
        patch = """*** Begin Patch
*** Update File: alpha.txt
@@
-first
+changed
*** Delete File: missing.txt
*** End Patch
"""
        result = roo_tools.apply_patch(patch, approval="Akkoord")

        self.assertEqual(result["status"], "error")
        self.assertIn("Bestand bestaat niet", result["stderr"])
        self.assertIn("first", Path(self.workspace, "alpha.txt").read_text(encoding="utf-8"))

    def test_execute_command_uses_safe_shell(self):
        blocked = roo_tools.execute_command("pwd", approval="")
        self.assertEqual(blocked["status"], "blocked")

        success = roo_tools.execute_command("pwd", approval="Akkoord")
        self.assertEqual(success["status"], "success")
        self.assertEqual(success["stdout"].strip(), self.workspace)

    def test_registry_exposes_and_dispatches_roo_tools(self):
        registry = AgentToolRegistry()
        status = registry.status()
        self.assertIn("roo_read_file", status["available_tools"])
        self.assertEqual(status["roo_adapter"]["status"], "online")

        result = registry.run_tool("roo_read_file", {"path": "alpha.txt", "offset": 1, "limit": 1})
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["tool_name"], "roo_read_file")
        self.assertEqual(result["stdout"], "first\n")


if __name__ == "__main__":
    unittest.main()
