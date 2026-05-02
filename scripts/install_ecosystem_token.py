#!/usr/bin/env python3
"""Install local Google/Microsoft OAuth tokens for Ouroboros adapters.

Purpose:
    Copy a token JSON/plaintext access token into the ignored `.secrets/`
    adapter token paths used by the Docker backend.
Inputs:
    --provider google|microsoft and --token-file pointing at a local file.
Outputs:
    `.secrets/google_workspace_token.json` or
    `.secrets/microsoft_graph_token.json` with chmod 0600.
Safety notes:
    The script never prints token values. It accepts JSON tokens or a plaintext
    access token and stores a small JSON object. `.secrets/` is gitignored.
Akkoord requirements:
    Use only for tokens Philip chooses to give Ouroboros.

Why this change:
    Philip asked to give Ouroboros Google and Microsoft tokens. A local import
    path avoids pasting secrets into chat or committing them by accident.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


TARGETS = {
    "google": ".secrets/google_workspace_token.json",
    "microsoft": ".secrets/microsoft_graph_token.json",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Install an OAuth token for Ouroboros ecosystem adapters.")
    parser.add_argument("--provider", choices=sorted(TARGETS), required=True)
    parser.add_argument("--token-file", required=True, help="Path to a token JSON file or plaintext access token file.")
    parser.add_argument("--workspace", default=os.getenv("WINTRIP_WORKSPACE", "."), help="Repo/workspace root.")
    args = parser.parse_args()

    source = Path(args.token_file).expanduser().resolve()
    if not source.exists():
        raise SystemExit(f"Token file not found: {source}")
    token = _load_token(source)
    if not token.get("access_token"):
        raise SystemExit("Token file must contain an access_token or plaintext token.")

    target = (Path(args.workspace).expanduser().resolve() / TARGETS[args.provider]).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(token, indent=2, sort_keys=True), encoding="utf-8")
    target.chmod(0o600)

    scopes = token.get("scopes") or token.get("scope") or []
    if isinstance(scopes, str):
        scopes = scopes.split()
    print(
        json.dumps(
            {
                "status": "success",
                "provider": args.provider,
                "target": str(target),
                "scopes": list(scopes)[:30],
                "secrets_returned": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _load_token(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8").strip()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        value = {"access_token": raw, "scopes": []}
    if not isinstance(value, dict):
        raise SystemExit("Token JSON must be an object.")
    if "scope" in value and "scopes" not in value:
        value["scopes"] = str(value.get("scope") or "").split()
    return value


if __name__ == "__main__":
    raise SystemExit(main())
