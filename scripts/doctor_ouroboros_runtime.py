#!/usr/bin/env python3
"""CLI doctor for the Ouroboros runtime harness."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from controller.runtime_doctor import runtime_doctor_payload, save_smoke_result  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect the Ouroboros backend/preview/bridge runtime.")
    parser.add_argument("--backend-url", default="http://127.0.0.1:8010")
    parser.add_argument("--preview-url", default="")
    parser.add_argument("--bridge-url", default="")
    parser.add_argument("--smoke", action="store_true", help="Run a non-mutating cockpit chat smoke test.")
    parser.add_argument("--json", action="store_true", help="Print full JSON payload.")
    args = parser.parse_args()

    backend_url = args.backend_url.rstrip("/")
    payload = _remote_doctor(backend_url, preview_url=args.preview_url, bridge_url=args.bridge_url)
    if payload is None:
        payload = runtime_doctor_payload(
            backend_url=backend_url,
            preview_url=args.preview_url or None,
            bridge_url=args.bridge_url or None,
        )
    if args.smoke:
        smoke = _run_smoke(backend_url)
        save_smoke_result(smoke)
        payload = _remote_doctor(backend_url, preview_url=args.preview_url, bridge_url=args.bridge_url) or runtime_doctor_payload(
            backend_url=backend_url,
            preview_url=args.preview_url or None,
            bridge_url=args.bridge_url or None,
        )
        payload["smoke_run"] = smoke

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_summary(payload)
    return 0 if payload.get("status") == "ready" else 1


def _remote_doctor(backend_url: str, *, preview_url: str = "", bridge_url: str = "") -> dict[str, Any] | None:
    query = {
        key: value
        for key, value in {
            "backend_url": backend_url,
            "preview_url": _docker_reachable_url(preview_url),
            "bridge_url": _docker_reachable_url(bridge_url),
        }.items()
        if value
    }
    suffix = f"?{urllib.parse.urlencode(query)}" if query else ""
    try:
        return _request_json("GET", f"{backend_url}/api/ouroboros/runtime/doctor{suffix}", timeout=8)
    except Exception:
        return None


def _docker_reachable_url(value: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(str(value or ""))
    except Exception:
        return value
    if parsed.hostname not in {"127.0.0.1", "localhost"}:
        return value
    netloc = "host.docker.internal"
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    return urllib.parse.urlunsplit((parsed.scheme or "http", netloc, parsed.path, parsed.query, parsed.fragment))


def _run_smoke(backend_url: str) -> dict[str, Any]:
    started = time.time()
    payload = {
        "prompt": "toon bestanden in controller",
        "provider": "ollama",
        "model": "llama3.2:latest",
        "conversation_id": f"runtime-doctor-{int(started)}",
        "history": [],
    }
    try:
        result = _request_json("POST", f"{backend_url}/api/cockpit/chat", timeout=75, payload=payload)
    except Exception as exc:
        return {"status": "failed", "route": "cockpit_chat", "reason": str(exc), "duration_seconds": round(time.time() - started, 3), "fake_success": False}

    source_trace = result.get("source_trace") if isinstance(result.get("source_trace"), dict) else {}
    tools = [str(item) for item in (source_trace.get("tools_executed") or [])]
    route = str(result.get("route") or source_trace.get("route") or "")
    status = str(result.get("status") or "")
    ok = route == "agentic_processor" and "list_files" in tools and status not in {"error", "failed", "blocked", "rejected"}
    return {
        "status": "success" if ok else "failed",
        "route": route,
        "tool": "list_files" if "list_files" in tools else "",
        "response_status": status,
        "reason": "agentic list_files smoke passed" if ok else f"expected agentic_processor/list_files, got route={route!r}, tools={tools}",
        "duration_seconds": round(time.time() - started, 3),
        "fake_success": False,
    }


def _request_json(method: str, url: str, *, timeout: float, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read(2_000_000).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read(20_000).decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} returned HTTP {exc.code}: {detail[:500]}") from exc
    data = json.loads(text) if text else {}
    if not isinstance(data, dict):
        raise RuntimeError(f"{method} {url} returned non-object JSON")
    return data


def _print_summary(payload: Mapping[str, Any]) -> None:
    status = str(payload.get("status") or "unknown")
    print(f"Ouroboros runtime doctor: {status}")
    blockers = payload.get("blockers") if isinstance(payload.get("blockers"), list) else []
    if blockers:
        print("Blockers:")
        for blocker in blockers:
            print(f"- {blocker}")
    checks = payload.get("checks") if isinstance(payload.get("checks"), dict) else {}
    for name in sorted(checks):
        check = checks.get(name) if isinstance(checks.get(name), dict) else {}
        print(f"{name}: {check.get('status', 'unknown')} - {check.get('reason', '')}")


if __name__ == "__main__":
    raise SystemExit(main())
