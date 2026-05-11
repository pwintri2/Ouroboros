#!/usr/bin/env python3
"""Run one-shot or looping laptop<->VPS Ouroboros peer exchange."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["WINTRIP_WORKSPACE"] = str(ROOT)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from controller.ouroboros_peer_bridge import exchange_with_vps, peer_bridge_status  # noqa: E402


DEFAULT_BACKEND_URL = "http://127.0.0.1:8010"


def main() -> int:
    parser = argparse.ArgumentParser(description="Exchange sanitized Ouroboros core snapshots with the VPS.")
    parser.add_argument("--approval", default="", help="Exact Akkoord is required for exchange.")
    parser.add_argument("--message", default="", help="Optional short pulse message.")
    parser.add_argument("--interval", type=float, default=60.0, help="Loop interval in seconds.")
    parser.add_argument("--loop", action="store_true", help="Keep exchanging until interrupted.")
    parser.add_argument("--status", action="store_true", help="Print local peer status without mutating.")
    parser.add_argument("--direct", action="store_true", help="Skip the local backend and run exchange in this Python process.")
    args = parser.parse_args()

    if args.status:
        print(json.dumps(_backend_status() if not args.direct else peer_bridge_status(), ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    def run_once() -> dict:
        result = _backend_exchange(args.approval, args.message) if not args.direct else {}
        if not result:
            result = exchange_with_vps(approval=args.approval, message=args.message)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
        return result

    result = run_once()
    if not args.loop:
        return 0 if result.get("status") == "success" else 1
    while True:
        time.sleep(max(5.0, float(args.interval or 60.0)))
        result = run_once()
        if result.get("status") == "blocked":
            return 1


def _backend_url() -> str:
    return str(os.getenv("WINTRIP_LOCAL_BACKEND_URL") or os.getenv("WINTRIP_BACKEND_URL") or DEFAULT_BACKEND_URL).rstrip("/")


def _backend_status() -> dict:
    try:
        with urllib.request.urlopen(f"{_backend_url()}/api/ouroboros/peer/status", timeout=5) as response:
            value = json.loads(response.read().decode("utf-8"))
            return value if isinstance(value, dict) else peer_bridge_status()
    except Exception:
        return peer_bridge_status()


def _backend_exchange(approval: str, message: str) -> dict:
    body = json.dumps({"approval": approval, "message": message, "timeout_seconds": 45}).encode("utf-8")
    try:
        request = urllib.request.Request(
            f"{_backend_url()}/api/ouroboros/peer/exchange",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            value = json.loads(response.read().decode("utf-8"))
            return value if isinstance(value, dict) else {}
    except Exception:
        return {}


if __name__ == "__main__":
    raise SystemExit(main())
