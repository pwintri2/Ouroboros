"""Shared path discovery for neighbouring Ouroboros workspaces.

The laptop and the public VPS expose neighbouring agent repositories through
different mount points. These helpers prefer explicit environment variables,
then select the first existing well-known path.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable


VPS_WEBROOT = Path("/var/www/philip-wintrip.nl/html/Ouroboros")


def first_existing_path(env_names: Iterable[str], candidates: Iterable[str | Path], default: str | Path) -> Path:
    for name in env_names:
        configured = str(os.getenv(name) or "").strip()
        if configured:
            return Path(configured).expanduser().resolve()
    candidate_paths = [Path(item).expanduser() for item in candidates]
    for path in candidate_paths:
        if path.exists():
            return path.resolve()
    return Path(default).expanduser().resolve()


def roo_code_path() -> Path:
    return first_existing_path(
        ("WINTRIP_ROO_CODE_PATH", "WINTRIP_ROO_PATH"),
        (
            "/workspace/Roo",
            "/workspace/Roo-code",
            VPS_WEBROOT / "Roo",
            "/home/pwintri2/Roo-code",
            "/home/pwintri2/Roo",
        ),
        "/home/pwintri2/Roo-code",
    )


def deepseek_path() -> Path:
    return first_existing_path(
        ("WINTRIP_DEEPSEEK_PATH",),
        (
            "/workspace/deepseek",
            "/deepseek",
            VPS_WEBROOT / "deepseek",
            "/home/pwintri2/deepseek",
        ),
        "/home/pwintri2/deepseek",
    )


def atlas_path() -> Path:
    return first_existing_path(
        ("WINTRIP_ATLAS_PATH",),
        (
            "/workspace/atlas",
            "/atlas",
            VPS_WEBROOT / "atlas",
            "/home/pwintri2/atlas",
        ),
        "/home/pwintri2/atlas",
    )
