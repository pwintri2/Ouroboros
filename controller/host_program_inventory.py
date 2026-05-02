"""Host program inventory for Ouroboros ecosystem awareness.

Purpose:
    Build a read-only inventory of installed desktop apps, package-manager
    packages, Flatpaks, Snaps and PATH binaries so Ouroboros can reason about
    what lives on the laptop.
Inputs:
    Exact Akkoord and optional scan limits. When run inside Docker, the scope is
    honestly reported as container. For a real host scan, run this module with
    WINTRIP_WORKSPACE pointing at the repo on the host.
Outputs:
    JSON inventory and compact status under artifacts/host_program_inventory/.
Safety notes:
    Only fixed read-only commands are used. No secrets are read intentionally,
    and command output is bounded/redacted.
Akkoord requirements:
    scan_host_program_inventory() requires approval == "Akkoord".

Why this change:
    Philip asked to see Ouroboros "snuffle" through the laptop and inspect
    programs. This gives that behavior an auditable, local-first inventory
    surface instead of ad hoc shell output.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from controller.ecosystem_11d import build_11d_record, content_hash, redact_sensitive_text
from controller.safe_shell import workspace_root


APPROVAL_PHRASE = "Akkoord"
DESKTOP_DIRS = (
    "/usr/share/applications",
    "/usr/local/share/applications",
    "~/.local/share/applications",
    "/var/lib/flatpak/exports/share/applications",
    "~/.local/share/flatpak/exports/share/applications",
    "~/Desktop",
    "~/Downloads",
)


def host_program_inventory_state_path() -> Path:
    return (workspace_root() / ".secrets" / "host_program_inventory.json").resolve()


def host_program_inventory_output_dir() -> Path:
    return (workspace_root() / "artifacts" / "host_program_inventory").resolve()


def get_host_program_inventory_status() -> dict[str, Any]:
    state = _load_state()
    return {
        "status": state.get("status", "ready"),
        "scope": state.get("scope", _scope()),
        "last_scan_at": state.get("scanned_at"),
        "desktop_app_count": state.get("desktop_app_count", 0),
        "package_count": state.get("package_count", 0),
        "flatpak_count": state.get("flatpak_count", 0),
        "snap_count": state.get("snap_count", 0),
        "path_binary_count": state.get("path_binary_count", 0),
        "artifact_path": state.get("artifact_path", ""),
        "top_categories": state.get("top_categories", {}),
        "sample_apps": state.get("sample_apps", []),
        "state_path": str(host_program_inventory_state_path()),
        "approval_required": True,
        "fake_success": False,
    }


def scan_host_program_inventory(
    approval: str = "",
    max_desktop_apps: int = 1000,
    max_packages: int = 8000,
    max_path_binaries: int = 3000,
) -> dict[str, Any]:
    """Run a bounded read-only program inventory."""
    if approval != APPROVAL_PHRASE:
        return {"status": "blocked", "reason": "Approval phrase must be 'Akkoord'", "fake_success": False}
    started = time.time()
    desktop_apps = _desktop_apps(max_desktop_apps=max_desktop_apps)
    packages = _dpkg_packages(max_packages=max_packages)
    flatpaks = _flatpak_apps()
    snaps = _snap_apps()
    path_binaries = _path_binaries(max_items=max_path_binaries)
    commands = {
        "dpkg-query": shutil.which("dpkg-query") or "",
        "flatpak": shutil.which("flatpak") or "",
        "snap": shutil.which("snap") or "",
    }
    categories = _category_counts(desktop_apps)
    summary = {
        "scope": _scope(),
        "desktop_app_count": len(desktop_apps),
        "package_count": len(packages),
        "flatpak_count": len(flatpaks),
        "snap_count": len(snaps),
        "path_binary_count": len(path_binaries),
        "top_categories": categories,
    }
    record = build_11d_record(
        source="host_program_inventory",
        record_type="program_inventory_summary",
        title="Host program inventory",
        summary=json.dumps(summary, sort_keys=True),
        signals={
            "storage_pressure": 0.35 if len(packages) > 2500 else 0.2,
            "driver_or_api_health": 0.65,
            "identity_or_auth_state": 0.15,
            "permission_complexity": 0.35,
            "freshness": 1.0,
            "importance": 0.75,
            "safety_risk": 0.2,
        },
        metadata={"commands": commands, "scope": _scope()},
    )
    payload = {
        "status": "success",
        "scanned_at": datetime.utcnow().isoformat(),
        "duration_seconds": round(time.time() - started, 3),
        "scope": _scope(),
        "commands": commands,
        "summary": summary,
        "desktop_apps": desktop_apps,
        "packages": packages,
        "flatpaks": flatpaks,
        "snaps": snaps,
        "path_binaries": path_binaries,
        "record": record,
        "fake_success": False,
    }
    artifact = _write_artifact(payload)
    state = {
        "status": "success",
        "scanned_at": payload["scanned_at"],
        "scope": payload["scope"],
        "desktop_app_count": len(desktop_apps),
        "package_count": len(packages),
        "flatpak_count": len(flatpaks),
        "snap_count": len(snaps),
        "path_binary_count": len(path_binaries),
        "top_categories": categories,
        "sample_apps": desktop_apps[:24],
        "artifact_path": str(artifact),
        "duration_seconds": payload["duration_seconds"],
        "fake_success": False,
    }
    _save_state(state)
    payload["artifact_path"] = str(artifact)
    return payload


def _desktop_apps(max_desktop_apps: int) -> list[dict[str, Any]]:
    apps: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw_dir in DESKTOP_DIRS:
        directory = Path(raw_dir).expanduser()
        if not directory.exists():
            continue
        for path in sorted(directory.glob("*.desktop")):
            if len(apps) >= max_desktop_apps:
                return apps
            parsed = _parse_desktop_file(path)
            key = parsed.get("id") or parsed.get("name") or str(path)
            if key in seen:
                continue
            seen.add(str(key))
            apps.append(parsed)
    return apps


def _parse_desktop_file(path: Path) -> dict[str, Any]:
    fields: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                if key in {"Name", "GenericName", "Comment", "Exec", "Icon", "Categories", "NoDisplay", "Hidden", "Type"}:
                    fields[key] = redact_sensitive_text(value, max_chars=500)
    except OSError as exc:
        fields["read_error"] = str(exc)
    name = fields.get("Name") or path.stem
    return {
        "id": path.stem,
        "name": name,
        "generic_name": fields.get("GenericName", ""),
        "comment": fields.get("Comment", ""),
        "exec": _sanitize_exec(fields.get("Exec", "")),
        "icon": fields.get("Icon", ""),
        "categories": [item for item in fields.get("Categories", "").split(";") if item],
        "no_display": fields.get("NoDisplay", "").lower() == "true",
        "hidden": fields.get("Hidden", "").lower() == "true",
        "path": str(path),
        "content_hash": _safe_file_hash(path),
    }


def _dpkg_packages(max_packages: int) -> list[dict[str, str]]:
    if shutil.which("dpkg-query") is None:
        return []
    result = _run(["dpkg-query", "-W", "-f=${Package}\t${Version}\t${Status}\n"], timeout=20, limit=2_000_000)
    packages = []
    for line in result.get("stdout", "").splitlines():
        if len(packages) >= max_packages:
            break
        parts = line.split("\t")
        if len(parts) >= 3 and "installed" in parts[2]:
            packages.append({"name": parts[0], "version": parts[1]})
    return packages


def _flatpak_apps() -> list[dict[str, str]]:
    if shutil.which("flatpak") is None:
        return []
    result = _run(["flatpak", "list", "--app", "--columns=application,name,version,branch,origin"], timeout=15, limit=200_000)
    apps = []
    for line in result.get("stdout", "").splitlines():
        parts = [part.strip() for part in line.split("\t")]
        if parts and parts[0]:
            apps.append(
                {
                    "application": parts[0],
                    "name": parts[1] if len(parts) > 1 else "",
                    "version": parts[2] if len(parts) > 2 else "",
                    "branch": parts[3] if len(parts) > 3 else "",
                    "origin": parts[4] if len(parts) > 4 else "",
                }
            )
    return apps


def _snap_apps() -> list[dict[str, str]]:
    if shutil.which("snap") is None:
        return []
    result = _run(["snap", "list"], timeout=15, limit=200_000)
    rows = []
    for index, line in enumerate(result.get("stdout", "").splitlines()):
        if index == 0:
            continue
        parts = line.split()
        if parts:
            rows.append({"name": parts[0], "version": parts[1] if len(parts) > 1 else "", "publisher": parts[4] if len(parts) > 4 else ""})
    return rows


def _path_binaries(max_items: int) -> list[dict[str, str]]:
    seen: set[str] = set()
    binaries: list[dict[str, str]] = []
    for raw_dir in os.getenv("PATH", "").split(os.pathsep):
        directory = Path(raw_dir)
        if not directory.exists() or not directory.is_dir():
            continue
        try:
            entries = sorted(directory.iterdir())
        except OSError:
            continue
        for path in entries:
            if len(binaries) >= max_items:
                return binaries
            try:
                if not path.is_file() or not os.access(path, os.X_OK):
                    continue
            except OSError:
                continue
            if path.name in seen:
                continue
            seen.add(path.name)
            binaries.append({"name": path.name, "path": str(path)})
    return binaries


def _category_counts(apps: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for app in apps:
        for category in app.get("categories", []):
            counts[category] = counts.get(category, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:20])


def _sanitize_exec(value: str) -> str:
    parts = []
    for token in str(value or "").split():
        if token.startswith("%"):
            continue
        parts.append(token)
    return " ".join(parts[:8])


def _scope() -> str:
    return "docker_container" if Path("/.dockerenv").exists() else "host"


def _safe_file_hash(path: Path) -> str:
    try:
        return content_hash(path.read_bytes())
    except OSError:
        return ""


def _run(command: list[str], timeout: int, limit: int) -> dict[str, Any]:
    try:
        proc = subprocess.run(command, text=True, capture_output=True, timeout=timeout)
        return {
            "status": "success" if proc.returncode == 0 else "error",
            "exit_code": proc.returncode,
            "stdout": redact_sensitive_text(proc.stdout or "", max_chars=limit),
            "stderr": redact_sensitive_text(proc.stderr or "", max_chars=8000),
        }
    except Exception as exc:
        return {"status": "error", "exit_code": None, "stdout": "", "stderr": redact_sensitive_text(str(exc))}


def _write_artifact(payload: dict[str, Any]) -> Path:
    out_dir = host_program_inventory_output_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"host_program_inventory_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.json"
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    latest = out_dir / "latest.json"
    latest.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return target


def _load_state() -> dict[str, Any]:
    path = host_program_inventory_state_path()
    if not path.exists():
        return {"status": "ready", "fake_success": False}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {"status": "error", "reason": "State is not an object.", "fake_success": False}
    except Exception as exc:
        return {"status": "error", "reason": str(exc), "fake_success": False}


def _save_state(state: dict[str, Any]) -> None:
    path = host_program_inventory_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a read-only host program inventory for Ouroboros.")
    parser.add_argument("--approval", default="", help="Must be Akkoord.")
    parser.add_argument("--max-desktop-apps", type=int, default=1000)
    parser.add_argument("--max-packages", type=int, default=8000)
    parser.add_argument("--max-path-binaries", type=int, default=3000)
    args = parser.parse_args()
    result = scan_host_program_inventory(
        approval=args.approval,
        max_desktop_apps=args.max_desktop_apps,
        max_packages=args.max_packages,
        max_path_binaries=args.max_path_binaries,
    )
    print(json.dumps({key: result.get(key) for key in ("status", "scope", "summary", "artifact_path", "duration_seconds", "reason")}, indent=2, sort_keys=True))
    return 0 if result.get("status") == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
