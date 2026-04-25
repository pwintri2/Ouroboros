"""Progress handoff for Gordon AI running in Docker."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import os


@dataclass(frozen=True)
class GordonBridge:
    """Write progress messages where a Docker-side Gordon process can read them."""

    progress_file: Path = Path(os.getenv("GORDON_PROGRESS_FILE", "gordon_progress.log"))

    def report(self, role: str, status: str, detail: str) -> None:
        self.progress_file.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).isoformat()
        line = f"{timestamp}\t{role}\t{status}\t{detail}\n"
        with self.progress_file.open("a", encoding="utf-8") as handle:
            handle.write(line)
