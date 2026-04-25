import tempfile
import unittest
from pathlib import Path

from resonant_ouroboros.gordon_bridge import GordonBridge


class GordonBridgeTests(unittest.TestCase):
    def test_report_writes_progress_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "gordon_progress.log"
            GordonBridge(progress_file=path).report("Tester", "ok", "unit test")
            text = path.read_text(encoding="utf-8")
            self.assertIn("Tester\tok\tunit test", text)


if __name__ == "__main__":
    unittest.main()
