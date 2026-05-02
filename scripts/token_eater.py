#!/usr/bin/env python3
"""Token Eater for Ouroboros ecosystem adapters.

Purpose:
    Let Philip drop Google/Microsoft token files into one local folder and have
    Ouroboros place them in the exact adapter paths with safe permissions.
Inputs:
    Files in `token_drop/` or paths passed with --file. Accepts JSON token
    objects or a plaintext access token. Provider is detected from filename or
    JSON fields, with --provider available as an override.
Outputs:
    `.secrets/google_workspace_token.json` and/or
    `.secrets/microsoft_graph_token.json`, chmod 0600. Imported originals are
    moved to `.secrets/token_eater_imported/` unless --keep-source is used.
Safety notes:
    Token values are never printed. `.secrets/` is gitignored. The importer
    stores local OAuth material only on this machine.
Akkoord requirements:
    This tool is for tokens Philip explicitly chooses to feed Ouroboros.

Why this change:
    Creating correct env/token files by hand is fiddly. This gives the project
    a forgiving local dropbox that "eats" tokens and places them correctly.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TARGETS = {
    "google": ".secrets/google_workspace_token.json",
    "microsoft": ".secrets/microsoft_graph_token.json",
}
DROP_DIR = "token_drop"
IMPORTED_DIR = ".secrets/token_eater_imported"
README = """# Ouroboros Token Drop

Gooi hier je tokenbestanden in en run:

```bash
./scripts/token_eater.py --scan
./start_ouroboros_sandbox_allow.sh
```

Bestandsnamen die automatisch herkend worden:
- Google: `google_token.json`, `gmail_token.json`, `drive_token.json`, `gcp_token.json`
- Microsoft: `microsoft_token.json`, `graph_token.json`, `azure_token.json`, `entra_token.json`

Het script print nooit tokenwaarden. Na import worden bronbestanden verplaatst naar
`.secrets/token_eater_imported/`.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Eat local Google/Microsoft tokens and install them for Ouroboros.")
    parser.add_argument("--workspace", default=os.getenv("WINTRIP_WORKSPACE", "."), help="Repo/workspace root.")
    parser.add_argument("--init", action="store_true", help="Create token_drop/ with a README.")
    parser.add_argument("--scan", action="store_true", help="Scan token_drop/ for token files.")
    parser.add_argument("--file", action="append", default=[], help="Import one token file. Can be used multiple times.")
    parser.add_argument("--provider", choices=sorted(TARGETS), default="", help="Override provider when using --file.")
    parser.add_argument("--keep-source", action="store_true", help="Keep source token files instead of moving them into .secrets.")
    parser.add_argument("--delete-source", action="store_true", help="Delete source token files after successful import.")
    args = parser.parse_args()

    workspace = Path(args.workspace).expanduser().resolve()
    if args.init:
        _init_drop_dir(workspace)

    files: list[Path] = []
    if args.scan:
        files.extend(_scan_drop_dir(workspace))
    files.extend(Path(item).expanduser().resolve() for item in args.file)

    if not files:
        _init_drop_dir(workspace)
        print(
            json.dumps(
                {
                    "status": "ready",
                    "message": "Drop token files into token_drop/ and run ./scripts/token_eater.py --scan",
                    "drop_dir": str(workspace / DROP_DIR),
                    "secrets_returned": False,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    results = []
    for path in files:
        result = _eat_file(
            workspace=workspace,
            path=path,
            provider_override=args.provider,
            keep_source=args.keep_source,
            delete_source=args.delete_source,
        )
        results.append(result)

    ok = sum(1 for item in results if item.get("status") == "success")
    print(json.dumps({"status": "success" if ok else "error", "imported_count": ok, "results": results, "secrets_returned": False}, indent=2, sort_keys=True))
    return 0 if ok else 1


def _init_drop_dir(workspace: Path) -> None:
    drop = workspace / DROP_DIR
    drop.mkdir(parents=True, exist_ok=True)
    readme = drop / "README.md"
    if not readme.exists():
        readme.write_text(README, encoding="utf-8")


def _scan_drop_dir(workspace: Path) -> list[Path]:
    drop = workspace / DROP_DIR
    _init_drop_dir(workspace)
    files = []
    for path in sorted(drop.iterdir()):
        if path.name.startswith(".") or path.name == "README.md" or not path.is_file():
            continue
        files.append(path.resolve())
    return files


def _eat_file(
    *,
    workspace: Path,
    path: Path,
    provider_override: str = "",
    keep_source: bool = False,
    delete_source: bool = False,
) -> dict[str, Any]:
    if not path.exists():
        return {"status": "error", "file": str(path), "reason": "file_not_found", "secrets_returned": False}

    try:
        token = _load_token(path)
        provider = provider_override or _detect_provider(path, token)
        if provider not in TARGETS:
            return {"status": "error", "file": str(path), "reason": "provider_not_detected", "hint": "Use --provider google or --provider microsoft.", "secrets_returned": False}
        normalized = _normalize_token(provider, token)
        target = (workspace / TARGETS[provider]).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(normalized, indent=2, sort_keys=True), encoding="utf-8")
        target.chmod(0o600)
        archived = ""
        if delete_source:
            path.unlink()
            archived = "<deleted>"
        elif not keep_source:
            imported_dir = (workspace / IMPORTED_DIR).resolve()
            imported_dir.mkdir(parents=True, exist_ok=True)
            imported_dir.chmod(0o700)
            destination = imported_dir / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{path.name}"
            shutil.move(str(path), str(destination))
            destination.chmod(0o600)
            archived = str(destination)
        scopes = normalized.get("scopes") or normalized.get("scope") or []
        if isinstance(scopes, str):
            scopes = scopes.split()
        return {
            "status": "success",
            "provider": provider,
            "source": str(path),
            "target": str(target),
            "archived_source": archived,
            "scopes": list(scopes)[:40],
            "expires_at": normalized.get("expiry") or normalized.get("expires_at") or normalized.get("expires_on") or "",
            "secrets_returned": False,
        }
    except Exception as exc:
        return {"status": "error", "file": str(path), "reason": str(exc), "secrets_returned": False}


def _load_token(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8", errors="replace").strip()
    if not raw:
        raise ValueError("empty_token_file")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = _parse_pasted_text(raw)
    if not isinstance(parsed, dict):
        raise ValueError("token_json_must_be_object")
    return parsed


def eat_pasted_text(
    *,
    workspace: str | Path,
    pasted_text: str,
    keep_source: bool = False,
) -> dict[str, Any]:
    """Import tokens from a notepad-style pasted text blob.

    Accepted shapes include:

    Google -->
    ya29...

    Microsoft
    eyJ...
    """
    root = Path(workspace).expanduser().resolve()
    sections = _split_pasted_sections(pasted_text)
    if not sections:
        return {"status": "error", "reason": "No Google or Microsoft token section found.", "imported_count": 0, "secrets_returned": False}

    sections = _merge_secret_sections(sections)

    results = []
    scratch = root / ".secrets" / "token_eater_paste"
    scratch.mkdir(parents=True, exist_ok=True)
    scratch.chmod(0o700)
    for index, (provider, raw_token) in enumerate(sections, start=1):
        source = scratch / f"paste_{index}_{provider}.txt"
        source.write_text(raw_token.strip(), encoding="utf-8")
        source.chmod(0o600)
        result = _eat_file(
            workspace=root,
            path=source,
            provider_override=provider,
            keep_source=keep_source,
            delete_source=not keep_source,
        )
        results.append(result)
    ok = sum(1 for item in results if item.get("status") == "success")
    return {"status": "success" if ok else "error", "imported_count": ok, "results": results, "secrets_returned": False}


def _split_pasted_sections(text: str) -> list[tuple[str, str]]:
    lines = str(text or "").splitlines()
    sections: list[tuple[str, list[str]]] = []
    current_provider = ""
    current_lines: list[str] = []

    for line in lines:
        provider, remainder = _provider_label_from_line(line)
        if provider:
            if current_provider and "".join(current_lines).strip():
                sections.append((current_provider, current_lines))
            current_provider = provider
            current_lines = [remainder] if remainder.strip() else []
            continue
        if current_provider:
            current_lines.append(line)

    if current_provider and "".join(current_lines).strip():
        sections.append((current_provider, current_lines))

    if not sections:
        raw = str(text or "").strip()
        if raw:
            provider = _detect_provider(Path("pasted_token.txt"), _parse_pasted_text(raw))
            if provider:
                sections.append((provider, [raw]))

    return [(provider, "\n".join(raw_lines).strip()) for provider, raw_lines in sections if "\n".join(raw_lines).strip()]


def _merge_secret_sections(sections: list[tuple[str, str]]) -> list[tuple[str, str]]:
    google_secret = ""
    merged: list[tuple[str, str]] = []
    for provider, raw in sections:
        if provider == "google_secret":
            google_secret = raw.strip()
            continue
        merged.append((provider, raw))
    if google_secret:
        for index, (provider, raw) in enumerate(merged):
            if provider == "google":
                merged[index] = ("google", _attach_google_secret(raw, google_secret))
                break
        else:
            merged.append(("google", json.dumps({"access_token": "", "client_secret": google_secret})))
    return merged


def _attach_google_secret(raw_token: str, secret: str) -> str:
    raw = raw_token.strip()
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            parsed.setdefault("client_secret", secret.strip())
            return json.dumps(parsed)
    except json.JSONDecodeError:
        pass
    return json.dumps({"access_token": raw, "client_secret": secret.strip()})


def _provider_label_from_line(line: str) -> tuple[str, str]:
    stripped = line.strip()
    lowered = stripped.lower()
    secret_match = re.match(r"^google\s+secret\b\s*(?:[-=]*>|:|-)?\s*(.*)$", stripped, flags=re.IGNORECASE)
    if secret_match:
        return "google_secret", stripped[secret_match.start(1) :].strip() if secret_match.lastindex else ""

    label_map = {
        "google": "google",
        "gmail": "google",
        "drive": "google",
        "gcp": "google",
        "microsoft": "microsoft",
        "ms": "microsoft",
        "graph": "microsoft",
        "azure": "microsoft",
        "entra": "microsoft",
        "office": "microsoft",
    }
    for label, provider in label_map.items():
        match = re.match(rf"^{label}\b\s*(?:[-=]*>|:|-)?\s*(.*)$", lowered, flags=re.IGNORECASE)
        if match:
            original_remainder = stripped[match.start(1) :].strip() if match.lastindex else ""
            return provider, original_remainder
    return "", ""


def _parse_pasted_text(raw: str) -> dict[str, Any]:
    token_match = re.search(r"(ya29\.[A-Za-z0-9._~+/\-=]+|eyJ[A-Za-z0-9._~+/\-=]+|Ew[A-Za-z0-9._~+/\-=]+)", raw)
    token = token_match.group(1) if token_match else raw.strip()
    return {"access_token": token, "scopes": []}


def _detect_provider(path: Path, token: dict[str, Any]) -> str:
    name = path.name.lower()
    blob = json.dumps({key: token.get(key) for key in ("client_id", "scope", "scopes", "tenant_id", "tid", "aud")}, default=str).lower()
    if any(marker in name for marker in ("google", "gmail", "drive", "gcp", "workspace")):
        return "google"
    if any(marker in name for marker in ("microsoft", "graph", "azure", "entra", "onedrive", "sharepoint", "office", "outlook")):
        return "microsoft"
    if "googleapis" in blob or "gmail" in blob or "drive" in blob:
        return "google"
    if "graph.microsoft" in blob or "microsoft" in blob or token.get("tenant_id") or token.get("tid"):
        return "microsoft"
    access = str(token.get("access_token") or "")
    if access.startswith("ya29."):
        return "google"
    return ""


def _normalize_token(provider: str, token: dict[str, Any]) -> dict[str, Any]:
    access_token = token.get("access_token") or token.get("token")
    if not access_token:
        if provider == "google" and (token.get("client_secret") or token.get("client_id")):
            access_token = ""
        elif provider == "microsoft" and token.get("client_id"):
            access_token = ""
        else:
            raise ValueError("missing_access_token")
    normalized = dict(token)
    raw_access = str(access_token).strip()
    if provider == "google" and _looks_like_google_client_id(raw_access):
        normalized.setdefault("client_id", raw_access)
        raw_access = ""
    if provider == "microsoft" and _looks_like_uuid(raw_access):
        normalized.setdefault("client_id", raw_access)
        raw_access = ""
    normalized["access_token"] = raw_access
    scopes = normalized.get("scopes") or normalized.get("scope") or []
    if isinstance(scopes, str):
        scopes = scopes.split()
    normalized["scopes"] = list(scopes)
    normalized["provider"] = provider
    normalized["installed_by"] = "scripts/token_eater.py"
    normalized["installed_at"] = datetime.now(timezone.utc).isoformat()
    return normalized


def _looks_like_google_client_id(value: str) -> bool:
    return value.strip().endswith(".apps.googleusercontent.com")


def _looks_like_uuid(value: str) -> bool:
    return bool(re.match(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", value.strip()))


if __name__ == "__main__":
    raise SystemExit(main())
