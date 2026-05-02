"""SharePoint Online/On-Prem deep adapter foundation.

Purpose:
    Model SharePoint sites, libraries, lists, content types, permissions and
    workflow trigger plans in a local-first, testable adapter.
Inputs:
    Offline SharePoint fixtures or Microsoft Graph-backed site data, plus exact
    Akkoord for any operation that would mutate or call a live service.
Outputs:
    Site/library inventories, permission analysis reports and SharePoint 11D
    records with permission metadata.
Safety notes:
    This foundation pass performs no PnP PowerShell execution. It analyzes
    provided data and delegates live site enumeration to microsoft_graph_adapter
    only when that adapter is explicitly approved/enabled.
Akkoord requirements:
    Required for live enumeration and workflow trigger execution.

Why this change:
    SharePoint is called out as a deep specialty in the buildplan. This adapter
    captures permissions and workflow semantics without pretending to have live
    tenant access.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from controller.ecosystem_11d import build_11d_record, redact_sensitive_text
from controller.microsoft_graph_adapter import MicrosoftGraphAdapter
from controller.safe_shell import workspace_root


APPROVAL_PHRASE = "Akkoord"


def sharepoint_state_path() -> Path:
    return (workspace_root() / ".secrets" / "sharepoint_pnp_adapter.json").resolve()


def get_sharepoint_status() -> dict[str, Any]:
    return SharePointPnPAdapter().status()


class SharePointPnPAdapter:
    def __init__(self, graph_adapter: MicrosoftGraphAdapter | None = None, fixtures: dict[str, Any] | None = None) -> None:
        self.graph_adapter = graph_adapter or MicrosoftGraphAdapter()
        self.fixtures = fixtures or {}

    def status(self) -> dict[str, Any]:
        graph_status = self.graph_adapter.status()
        return {
            "status": "ready" if graph_status.get("status") in {"connected", "token_missing"} else "degraded",
            "adapter": "sharepoint_pnp",
            "graph_status": graph_status.get("status"),
            "live_api_enabled": graph_status.get("live_api_enabled", False),
            "write_requires_approval": True,
            "supported_methods": [
                "list_site_collections",
                "list_libraries",
                "analyze_permissions",
                "map_sharepoint_object_to_11d",
                "workflow_trigger_example",
            ],
            "state_path": str(sharepoint_state_path()),
            "fake_success": False,
        }

    def list_site_collections(self, approval: str = "") -> dict[str, Any]:
        fixture = self.fixtures.get("sites")
        if fixture is not None:
            return self._fixture_result("site_collections", list(fixture))
        result = self.graph_adapter.get_sharepoint_sites(approval=approval)
        if result.get("status") == "success":
            _save_state({"last_operation": "site_collections", "last_status": "success", "updated_at": datetime.utcnow().isoformat()})
        return result

    def list_libraries(self, site: dict[str, Any] | str, approval: str = "") -> dict[str, Any]:
        fixture = self.fixtures.get("libraries")
        if fixture is not None:
            libraries = list(fixture)
            return self._fixture_result("libraries", libraries)
        if approval != APPROVAL_PHRASE:
            return {"status": "blocked", "reason": "Approval phrase must be 'Akkoord' for live SharePoint library enumeration.", "fake_success": False}
        return {
            "status": "disabled",
            "reason": "Live library enumeration needs tenant-specific Graph site/list IDs.",
            "site": site if isinstance(site, str) else site.get("webUrl") or site.get("id"),
            "fake_success": False,
        }

    def analyze_permissions(self, sites: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        sites = list(sites if sites is not None else self.fixtures.get("sites", []))
        findings: list[dict[str, Any]] = []
        for site in sites:
            permissions = site.get("permissions") or site.get("permissionLevels") or []
            sharing = str(site.get("externalSharing") or site.get("sharingCapability") or "").lower()
            unique = bool(site.get("uniquePermissions") or site.get("hasUniqueRoleAssignments"))
            high_risk = unique or "anyone" in sharing or "anonymous" in sharing
            findings.append(
                {
                    "site_url": site.get("webUrl") or site.get("url") or "",
                    "title": site.get("displayName") or site.get("name") or site.get("title") or "",
                    "unique_permissions": unique,
                    "external_sharing": site.get("externalSharing") or site.get("sharingCapability") or "",
                    "permission_count": len(permissions) if isinstance(permissions, list) else 0,
                    "risk": "review" if high_risk else "normal",
                    "recommendation": "Review inheritance and external sharing." if high_risk else "No immediate cleanup signal from fixture.",
                    "record_11d": self.map_sharepoint_object_to_11d(site),
                }
            )
        return {
            "status": "success",
            "source": "fixture_or_supplied",
            "site_count": len(sites),
            "review_count": sum(1 for item in findings if item["risk"] == "review"),
            "findings": findings,
            "fake_success": False,
        }

    def workflow_trigger_example(self, site_url: str, list_id: str, action: str = "notify_teams", approval: str = "") -> dict[str, Any]:
        plan = {
            "operation": "sharepoint_item_created_to_power_automate",
            "site_url": site_url,
            "list_id": list_id,
            "action": action,
            "preview": "SharePoint item created -> Power Automate trigger -> local/Teams notification.",
            "rollback_plan": "Disable the Power Automate flow or remove the trigger connection.",
            "approval_required": True,
        }
        if approval != APPROVAL_PHRASE:
            return {"status": "blocked", "reason": "Approval phrase must be 'Akkoord'", "plan": plan, "fake_success": False}
        return {"status": "approval_recorded", "executed": False, "reason": "Live workflow creation is not enabled in this foundation pass.", "plan": plan, "fake_success": False}

    def map_sharepoint_object_to_11d(self, item: dict[str, Any]) -> dict[str, Any]:
        permissions = item.get("permissions") or item.get("permissionLevels") or []
        unique = bool(item.get("uniquePermissions") or item.get("hasUniqueRoleAssignments"))
        sharing = str(item.get("externalSharing") or item.get("sharingCapability") or "").lower()
        return build_11d_record(
            source="sharepoint_pnp_adapter",
            record_type="sharepoint_object",
            title=str(item.get("displayName") or item.get("name") or item.get("title") or item.get("webUrl") or "sharepoint_object"),
            summary=redact_sensitive_text(json.dumps({key: item.get(key) for key in ("id", "webUrl", "name", "displayName", "externalSharing")}, sort_keys=True)),
            signals={
                "driver_or_api_health": 0.8,
                "network_pressure": 0.4,
                "identity_or_auth_state": 0.7,
                "permission_complexity": 0.85 if unique else 0.55,
                "freshness": 0.8 if item.get("lastModifiedDateTime") else 0.5,
                "importance": 0.85,
                "safety_risk": 0.65 if ("anyone" in sharing or unique) else 0.35,
            },
            metadata={
                "site_url": item.get("webUrl") or item.get("url") or "",
                "list_id": item.get("listId") or item.get("id") or "",
                "permission_level_count": len(permissions) if isinstance(permissions, list) else 0,
                "unique_permissions": unique,
            },
        )

    def _fixture_result(self, operation: str, items: list[Any]) -> dict[str, Any]:
        records = [self.map_sharepoint_object_to_11d(item if isinstance(item, dict) else {"value": item}) for item in items]
        _save_state({"last_operation": operation, "last_status": "success", "last_source": "fixture", "updated_at": datetime.utcnow().isoformat()})
        return {
            "status": "success",
            "source": "fixture",
            "operation": operation,
            "count": len(items),
            "items": items,
            "records_11d": records,
            "fake_success": False,
        }


def _save_state(state: dict[str, Any]) -> None:
    path = sharepoint_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
