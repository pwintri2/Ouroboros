from pathlib import Path


def test_desktop_launcher_files_exist_and_are_executable():
    root = Path(__file__).resolve().parents[1]
    launcher = root / "negesydd-desktop"
    desktop = root / "Negesydd.desktop"

    assert launcher.exists()
    assert launcher.stat().st_mode & 0o111
    assert desktop.exists()
    assert "Terminal=false" in desktop.read_text()

