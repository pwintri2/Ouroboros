import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from controller import project_context


class TestProjectContext(unittest.TestCase):
    def test_project_root_falls_back_when_workspace_is_empty(self):
        with tempfile.TemporaryDirectory(prefix="project-context-empty-") as tmp:
            with patch("controller.project_context.workspace_root", return_value=Path(tmp)):
                root = project_context.get_project_root()

        self.assertEqual(root, Path(project_context.__file__).resolve().parents[1])


if __name__ == "__main__":
    unittest.main()
