from pathlib import Path
import tempfile

from resonant_ouroboros.gordon_bridge import GordonBridge


def test_report_writes_progress_line():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "gordon_progress.log"
        bridge = GordonBridge(progress_file=path)
        bridge.report("Tester", "ok", "unit test")
        text = path.read_text(encoding="utf-8")
        assert "Tester\tok\tunit test" in text
