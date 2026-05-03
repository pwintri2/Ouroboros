"""Composable ecosystem status for Ouroboros.

Purpose:
    Summarize Pop!_OS diagnostics, Google, Microsoft, SharePoint, crawler and
    ecosystem knowledge ingestion state for API/UI status payloads.
Inputs:
    Existing adapter status functions only; no live API calls are made here.
Outputs:
    A truthful ecosystem_adapters payload and crawl_stats summary.
Safety notes:
    This module performs no writes, no shell commands and no external calls.
Akkoord requirements:
    None; individual adapters require Akkoord for active diagnostics/crawls.

Why this change:
    Multiple routes need the same ecosystem-health contract without duplicating
    import/error handling.
"""

from __future__ import annotations

from typing import Any


def get_ecosystem_status() -> dict[str, Any]:
    """Return best-effort ecosystem status without inventing live connectivity."""
    adapters: dict[str, Any] = {}
    adapters["popos"] = _safe_status("controller.popos_diagnostics_adapter", "get_popos_diagnostics_status")
    adapters["google"] = _safe_status("controller.google_workspace_adapter", "get_google_workspace_status")
    adapters["rclone_drive"] = _safe_status("controller.rclone_drive_adapter", "get_rclone_drive_status")
    adapters["microsoft"] = _safe_status("controller.microsoft_graph_adapter", "get_microsoft_graph_status")
    adapters["sharepoint"] = _safe_status("controller.sharepoint_pnp_adapter", "get_sharepoint_status")
    crawler = _safe_status("controller.agentic_crawler", "get_agentic_crawler_status")
    programs = _safe_status("controller.host_program_inventory", "get_host_program_inventory_status")
    sensory = _safe_status("controller.host_sensory_adapter", "get_host_sensory_status")
    knowledge = _safe_status("controller.ecosystem_knowledge_ingest", "get_ecosystem_knowledge_status")
    health_values = [str(value.get("status", "unknown")) for value in adapters.values() if isinstance(value, dict)]
    return {
        "status": "ready" if health_values else "unavailable",
        "ecosystem_adapters": adapters,
        "crawl_stats": crawler,
        "program_inventory": programs,
        "host_sensory": sensory,
        "ecosystem_knowledge": knowledge,
        "healthy_adapter_count": sum(1 for value in adapters.values() if str(value.get("status")) in {"ready", "connected"}),
        "approval_required": True,
        "fake_success": False,
    }


def _safe_status(module_name: str, function_name: str) -> dict[str, Any]:
    try:
        module = __import__(module_name, fromlist=[function_name])
        fn = getattr(module, function_name)
        status = fn()
        return status if isinstance(status, dict) else {"status": "error", "reason": "Status function did not return an object.", "fake_success": False}
    except Exception as exc:
        return {"status": "unavailable", "reason": str(exc), "fake_success": False}
