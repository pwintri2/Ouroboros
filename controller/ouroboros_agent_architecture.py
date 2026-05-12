"""Canonical four-agent architecture surface for Ouroboros.

This module does not execute agent work. It composes the current local
capability inventory into the four roles from the 2026-05-12 build plan and
builds Criticus review bundles for private, mutating, network and
self-install/self-copy actions.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Mapping


APPROVAL_PHRASE = "Akkoord"
ARCHITECTURE_VERSION = "2026-05-12.agentic-architecture.v1"
AGENT_IDS: tuple[str, ...] = ("codex", "web_scout", "communicator", "criticus")

PRIVATE_READ_TOOLS = {
    "gmail_search",
    "google_drive_list",
    "mail_read_recent",
    "drive_upload_file",
    "drive_upload_text",
    "gmail_manage",
}
PUBLIC_READ_TOOLS = {
    "brave_search",
    "github_status",
    "github_repo",
    "github_search_repositories",
    "gmail_status",
    "google_drive_status",
    "vps_status",
    "vps_login_check",
    "vps_sync_preview",
    "vps_ui_sync_preview",
    "chroma_sync_status",
    "chroma_sync_preview",
    "voice_chat_status",
    "prompt_understanding",
    "memory_search",
    "agentic_ecosystem_context",
    "host_status",
    "read_file",
    "list_files",
    "search_files",
}
EXTERNAL_APPROVAL_TOOLS = {"browser_research"}
MUTATING_TOOLS = {
    "safe_shell",
    "run_command",
    "run_tests",
    "write_file",
    "apply_patch",
    "roo_write_file",
    "roo_apply_patch",
    "roo_execute_command",
    "browser_open_url",
    "host_open_url",
    "chatgpt_browser_ask",
    "world_grok_ask",
    "mail_send",
    "social_post_publish",
    "codex_job_start",
    "resolve_or_build_function",
    "training_ingest",
    "vps_sync_execute",
    "vps_ui_sync_execute",
    "chroma_sync_execute",
    "drive_upload_file",
    "drive_upload_text",
    "gmail_manage",
}
CONNECTOR_WRITE_TOOLS = {
    "mail_send",
    "social_post_publish",
    "drive_upload_file",
    "drive_upload_text",
    "gmail_manage",
    "vps_sync_execute",
    "vps_ui_sync_execute",
    "chroma_sync_execute",
}
SHELL_TOOLS = {"safe_shell", "run_command", "run_tests", "roo_execute_command"}
BROWSER_CONTROL_TOOLS = {"browser_open_url", "host_open_url", "chatgpt_browser_ask", "world_grok_ask"}
VPS_TOOLS = {"vps_login_check", "vps_sync_preview", "vps_sync_execute", "vps_ui_sync_preview", "vps_ui_sync_execute"}

SECRET_KEY_MARKERS = ("api_key", "apikey", "access_token", "refresh_token", "client_secret", "authorization", "bearer", "password", "passwd", "token", "secret", "cookie", "session")
SECRET_VALUE_RE = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|token|secret|password|passwd|bearer|authorization|cookie|session)\b\s*[:=]\s*['\"]?[^'\"\s,;}]+"
)
SELF_COPY_RE = re.compile(
    r"(?i)\b("
    r"zelf(?:\s|-)?kopi(?:e|eer|eren)|self(?:[\s_-])?copy|self(?:[\s_-])?install|"
    r"repliceer|replicate|verspreid|spread|install(?:eer|eren)?\s+(?:jezelf|ouroboros)|"
    r"kopieer\s+(?:jezelf|ouroboros)|installer|installatiepakket"
    r")\b"
)
PRIVATE_MARKER_RE = re.compile(r"(?i)\b(gmail|mailbox|inbox|google drive|gdrive|drive map|onedrive|sharepoint|teams|calendar|agenda|private|prive)\b")
NETWORK_MARKER_RE = re.compile(r"(?i)\b(vps|ssh|rsync|scp|deploy|sync|synchroniseer|server|network|netwerk|internet|remote)\b")
MUTATION_MARKER_RE = re.compile(r"(?i)\b(schrijf|write|save|sla\s+op|maak|create|upload|verwijder|delete|remove|wijzig|edit|patch|update|verstuur|send|reply|post|publish|deploy|sync|run|start|execute|voer\s+uit|install|de-?install)\b")


def get_agent_architecture_catalog(*, include_status: bool = True) -> dict[str, Any]:
    """Return the canonical four-agent catalog and current capability view."""

    observed = _observed_runtime(include_status=include_status)
    tools = set(observed["tool_names"])
    agents = [
        _codex_agent(tools, observed),
        _web_scout_agent(tools, observed),
        _communicator_agent(tools, observed),
        _criticus_agent(tools, observed),
    ]
    readiness_summary: dict[str, int] = {}
    for agent in agents:
        readiness_summary[str(agent["readiness"])] = readiness_summary.get(str(agent["readiness"]), 0) + 1
    blocked_gaps = [gap for agent in agents for gap in agent.get("blocked_gaps", [])]
    return {
        "status": "online",
        "version": ARCHITECTURE_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "Bouwplan agentische architectuur 12-05.docx",
        "agent_count": len(agents),
        "agents": agents,
        "readiness_summary": readiness_summary,
        "blocked_gaps": blocked_gaps,
        "approval_policy": _approval_policy(),
        "public_interfaces": _public_interfaces(),
        "observed_runtime": observed,
        "secrets_returned": False,
        "fake_success": False,
    }


def build_critic_review(request: Mapping[str, Any] | None = None, *, store_audit: bool = True) -> dict[str, Any]:
    """Build a Criticus review bundle without executing any requested action."""

    payload = _redact(dict(request or {}))
    prompt = _clean_text(payload.get("prompt") or payload.get("intent") or payload.get("task") or "", 4000)
    action = _clean_text(payload.get("action") or "", 240)
    tool = _clean_text(payload.get("tool") or payload.get("tool_name") or "", 120)
    agent_id = _canonical_agent_id(payload.get("agent_id") or payload.get("agent") or "")
    requested_mode = _requested_mode(payload.get("requested_mode") or payload.get("mode") or "preview")
    approval = _clean_text(payload.get("approval") or "", 80)
    args = payload.get("args") if isinstance(payload.get("args"), Mapping) else {}
    data_scope = _clean_text(payload.get("data_scope") or "", 300)
    target = _clean_text(payload.get("target") or payload.get("platform") or "", 200)
    command = _clean_text(payload.get("command") or payload.get("api_call") or "", 1000)
    rollback = _clean_text(payload.get("rollback") or "", 500)

    review_text = " ".join(
        [
            prompt,
            action,
            tool,
            data_scope,
            target,
            command,
            rollback,
            json.dumps(args, ensure_ascii=False, sort_keys=True, default=str),
        ]
    )
    approval_present = approval == APPROVAL_PHRASE
    self_copy_install = bool(SELF_COPY_RE.search(review_text))
    private_data = tool in PRIVATE_READ_TOOLS or bool(PRIVATE_MARKER_RE.search(review_text))
    mutating = tool in MUTATING_TOOLS or bool(MUTATION_MARKER_RE.search(review_text))
    connector_write = tool in CONNECTOR_WRITE_TOOLS or ("connector write" in review_text.lower())
    browser_control = tool in BROWSER_CONTROL_TOOLS or ("browser" in review_text.lower() and mutating)
    external_browser_read = tool in EXTERNAL_APPROVAL_TOOLS
    shell = tool in SHELL_TOOLS or bool(re.search(r"(?i)\b(shell|commando|command|terminal|pytest|unittest)\b", review_text))
    vps_network = tool in VPS_TOOLS or bool(NETWORK_MARKER_RE.search(review_text))
    public_read = tool in PUBLIC_READ_TOOLS and not private_data and not mutating

    categories = _risk_categories(
        private_data=private_data,
        mutating=mutating,
        connector_write=connector_write,
        browser_control=browser_control,
        external_browser_read=external_browser_read,
        shell=shell,
        vps_network=vps_network,
        self_copy_install=self_copy_install,
        public_read=public_read,
    )
    blocked_reasons: list[str] = []
    findings: list[str] = []
    approval_required = False
    execute_allowed = False
    decision = "preview_only"

    if self_copy_install:
        blocked_reasons.append("Zelf-kopieren/installeren is in v1 alleen toegestaan als dry-run manifest; automatische verspreiding blijft geblokkeerd.")
        findings.append("Maak platformvereisten, rollback en handmatige stappen zichtbaar voordat er ooit installatie-automatisering wordt gebouwd.")
        decision = "dry_run_manifest_only"
    if connector_write and requested_mode == "execute":
        blocked_reasons.append("Live connector/VPS mutaties zijn in deze architectuurfase niet uitvoerbaar via de reviewroute.")
        if not self_copy_install:
            decision = "blocked_by_phase_policy"
    if vps_network and mutating and requested_mode == "execute":
        blocked_reasons.append("VPS/netwerkmutatie vereist een aparte deploytaak na dry-run inspectie.")
        if not self_copy_install:
            decision = "blocked_by_phase_policy"
    if (private_data or mutating or browser_control or external_browser_read or shell or vps_network) and not approval_present and not blocked_reasons:
        approval_required = True
        findings.append("Deze actie raakt private data, lokale mutatie, shell, browserbesturing of netwerk en wacht op exact Akkoord.")
        decision = "approval_required"
    if public_read and not blocked_reasons:
        findings.append("Publieke read-only actie mag inhoudelijk worden gepland zonder Akkoord; de reviewroute voert niets uit.")
        decision = "public_read_review_passed"
        execute_allowed = requested_mode in {"execute", "run"} and not mutating
    elif approval_present and not blocked_reasons:
        findings.append("Akkoord is aanwezig; daadwerkelijke uitvoering moet alsnog via de bestaande ToolBridge/adapter gebeuren.")
        decision = "review_passed"
        execute_allowed = requested_mode in {"execute", "run"}

    if blocked_reasons:
        status = "blocked"
        execute_allowed = False
        approval_required = bool(not approval_present and not self_copy_install)
        approval_status = "blocked_by_policy"
    elif approval_required:
        status = "approval_required"
        execute_allowed = False
        approval_status = "pending_philip_akkoord"
    elif decision in {"public_read_review_passed", "review_passed"}:
        status = "review_passed"
        approval_status = "approved" if approval_present else "not_required_readonly"
    else:
        status = "preview"
        approval_status = "not_required_preview"

    risk_level = _risk_level(categories=categories, blocked=bool(blocked_reasons), approval_required=approval_required)
    dry_run_manifest = _dry_run_manifest(
        prompt=prompt,
        action=action,
        tool=tool,
        agent_id=agent_id,
        categories=categories,
        self_copy_install=self_copy_install,
    )
    review_id = _review_id(payload, categories, status)
    result = {
        "status": status,
        "route": "agent_architecture_critic_review",
        "review_id": review_id,
        "decision": decision,
        "agent_id": agent_id,
        "agent": "Criticus",
        "requested_mode": requested_mode,
        "execution_performed": False,
        "execute_allowed": execute_allowed,
        "approval_required": approval_required,
        "approval_status": approval_status,
        "approval_phrase": APPROVAL_PHRASE,
        "risk_level": risk_level,
        "risk_categories": categories,
        "public_read": public_read,
        "private_data": private_data,
        "mutating": mutating,
        "connector_write": connector_write,
        "browser_control": browser_control,
        "external_browser_read": external_browser_read,
        "shell": shell,
        "vps_network": vps_network,
        "self_copy_install": self_copy_install,
        "critic": {
            "findings": findings,
            "blocked_reasons": blocked_reasons,
            "loop_policy": {
                "max_similar_failures": 3,
                "on_repeated_failure": "stop current loop, re-orient, or ask Philip a concrete question",
            },
            "secrets_check": "payload_redacted",
        },
        "action": {
            "prompt": prompt[:1000],
            "action": action,
            "tool": tool,
            "target": target,
            "command": command,
            "rollback": rollback,
            "args": _redact(args),
            "data_scope": data_scope,
        },
        "dry_run_manifest": dry_run_manifest,
        "public_interfaces": _public_interfaces(),
        "secrets_returned": False,
        "fake_success": False,
    }
    if store_audit:
        result["audit"] = store_critic_review_audit(result)
    return result


def store_critic_review_audit(result: Mapping[str, Any]) -> dict[str, Any]:
    """Store a redacted Criticus review audit record.

    Kept separate from ``build_critic_review`` so HTTP routes can return the
    review immediately and persist audit data asynchronously.
    """

    return _store_review_audit(result)


def _codex_agent(tools: set[str], observed: Mapping[str, Any]) -> dict[str, Any]:
    required = ("gmail_status", "google_drive_status", "github_status", "vps_status", "safe_shell", "run_tests", "codex_job_start")
    missing = [tool for tool in required if tool not in tools]
    readiness = "klaar" if not missing else "preview-only"
    return _agent_payload(
        agent_id="codex",
        name="Codex",
        role="De Bouwer",
        mission="Programmeert backend-adapters, shell/systeembeheer en veilige zelf-aanpassing via bestaande ToolBridge/Codex/Roo routes.",
        readiness=readiness,
        allowed_tools=[
            "gmail_status",
            "gmail_search",
            "google_drive_status",
            "google_drive_list",
            "github_status",
            "github_repo",
            "github_search_repositories",
            "vps_status",
            "vps_sync_preview",
            "safe_shell",
            "run_tests",
            "roo_apply_patch_preview",
            "roo_apply_patch",
            "codex_job_start",
            "resolve_or_build_function",
        ],
        approval_required_for=["gmail_search", "google_drive_list", "safe_shell", "run_tests", "roo_apply_patch", "codex_job_start", "resolve_or_build_function"],
        phases=[
            "Connectoren consolideren rond Google Workspace/rclone/GitHub/Microsoft/SharePoint/VPS.",
            "Muterende connectoracties alleen preview-first modelleren.",
            "Bestandsbeheer, tests en diagnose via ToolBridge/Roo/safe_shell.",
            "Zelf-aanpassing via patch-preview, tests, Criticus-review en Akkoord.",
        ],
        blocked_gaps=[
            *[f"Ontbrekende bouwer-tool: {tool}" for tool in missing],
            "GitHub/Teams/SharePoint write-actions blijven preview-only in v1.",
        ],
        observed=observed,
    )


def _web_scout_agent(tools: set[str], observed: Mapping[str, Any]) -> dict[str, Any]:
    missing = [tool for tool in ("brave_search", "browser_research") if tool not in tools]
    brave_status = str(((observed.get("connector_status") or {}).get("brave") or {}).get("status") or "")
    gaps = [f"Ontbrekende web-tool: {tool}" for tool in missing]
    if brave_status in {"missing_api_key", "unavailable"}:
        gaps.append("Brave Search is niet volledig geconfigureerd; browser research blijft de fallback.")
    return _agent_payload(
        agent_id="web_scout",
        name="Web-Scout",
        role="Informatieverzamelaar",
        mission="Verzamelt actuele documentatie en platformeisen via veilige read-only web- en browserlagen.",
        readiness="klaar" if not missing else "preview-only",
        allowed_tools=["brave_search", "browser_research", "scrub_browser_content", "prompt_understanding", "training_ingest"],
        approval_required_for=["browser_research", "training_ingest"],
        phases=[
            "Brave/browser research als primaire weblaag; maximaal een pagina per browseractie.",
            "Actuele API-documentatie verzamelen voor Google, GitHub, Microsoft 365 en platformen.",
            "Install capability cards opbouwen als gestructureerde read-only kennis.",
            "Netwerkorientatie read-only houden tot Criticus en Akkoord.",
        ],
        blocked_gaps=gaps,
        observed=observed,
    )


def _communicator_agent(tools: set[str], observed: Mapping[str, Any]) -> dict[str, Any]:
    missing = [tool for tool in ("voice_chat_status", "browser_open_url", "host_status") if tool not in tools]
    return _agent_payload(
        agent_id="communicator",
        name="Communicator",
        role="Uitleggen en meekijken",
        mission="Zet complexe acties om naar rustige tekst-, spraak-, visuele- en overnameflows voor de gebruiker.",
        readiness="preview-only",
        allowed_tools=["voice_chat_status", "browser_open_url", "host_status", "host_open_url", "prompt_understanding"],
        approval_required_for=["browser_open_url", "host_open_url"],
        phases=[
            "Begeleidingslaag voor tekst, spraaktekst en visuele aanwijzingen.",
            "Platformprofielen voor Windows, macOS, Linux/Pop!_OS en iPhone.",
            "Cockpit actiekaarten met stap, risico, toestemming en fallback.",
            "Automatische taakovername uitsluitend via ToolBridge na preview en Akkoord.",
        ],
        blocked_gaps=[
            *[f"Ontbrekende communicator-tool: {tool}" for tool in missing],
            "Visuele pijltjes en echte spraakuitvoer zijn nog niet volledig first-class.",
        ],
        observed=observed,
    )


def _criticus_agent(tools: set[str], observed: Mapping[str, Any]) -> dict[str, Any]:
    return _agent_payload(
        agent_id="criticus",
        name="Criticus",
        role="Veiligheid en kwaliteitscontrole",
        mission="Bundelt risico's, approvals, rollback en no-secrets checks voordat private of muterende acties plaatsvinden.",
        readiness="klaar",
        allowed_tools=["architecture_critic_review", "tool_bridge_status", "runtime_doctor", "inspect_hippocampus"],
        approval_required_for=[],
        phases=[
            "Reviewbundel voor private/muterende acties.",
            "Risico's classificeren: private data, filesystem, shell, browser, connector, VPS/netwerk, self-copy/install.",
            "Self-copy/install en netwerkverspreiding standaard blokkeren; dry-run manifesten toestaan.",
            "Beslissingen redacted naar OODA/Hippocampus/Ziel auditlagen schrijven.",
        ],
        blocked_gaps=[],
        observed=observed,
    )


def _agent_payload(
    *,
    agent_id: str,
    name: str,
    role: str,
    mission: str,
    readiness: str,
    allowed_tools: list[str],
    approval_required_for: list[str],
    phases: list[str],
    blocked_gaps: list[str],
    observed: Mapping[str, Any],
) -> dict[str, Any]:
    available = set(observed.get("tool_names") or [])
    return {
        "id": agent_id,
        "name": name,
        "role": role,
        "mission": mission,
        "readiness": readiness,
        "allowed_tools": allowed_tools,
        "available_tools": [tool for tool in allowed_tools if tool in available or tool == "architecture_critic_review"],
        "missing_tools": [tool for tool in allowed_tools if tool not in available and tool != "architecture_critic_review"],
        "approval_required_for": approval_required_for,
        "approval_phrase": APPROVAL_PHRASE,
        "phases": [{"index": idx + 1, "description": description} for idx, description in enumerate(phases)],
        "blocked_gaps": blocked_gaps,
        "interfaces": _agent_interfaces(agent_id),
        "secrets_returned": False,
        "fake_success": False,
    }


def _observed_runtime(*, include_status: bool) -> dict[str, Any]:
    registered_tools: tuple[str, ...] = ()
    bridge_tools: tuple[str, ...] = ()
    tool_bridge: dict[str, Any] = {"status": "unknown", "fake_success": False}
    slash_agents: dict[str, Any] = {"status": "unknown", "commands": {}, "fake_success": False}
    connector_status: dict[str, Any] = {}

    try:
        from controller.agent_tools import REGISTERED_TOOLS

        registered_tools = tuple(str(item) for item in REGISTERED_TOOLS)
    except Exception:
        registered_tools = ()
    try:
        from controller.tool_bridge import TOOL_BRIDGE_TOOLS, tool_bridge_status

        bridge_tools = tuple(str(item) for item in TOOL_BRIDGE_TOOLS)
        if include_status:
            tool_bridge = _redact(tool_bridge_status())
    except Exception as exc:
        tool_bridge = {"status": "unavailable", "reason": str(exc), "fake_success": False}
    try:
        from controller.slash_agent_router import slash_command_catalog

        if include_status:
            slash_agents = _redact(slash_command_catalog())
    except Exception as exc:
        slash_agents = {"status": "unavailable", "reason": str(exc), "commands": {}, "fake_success": False}

    if include_status:
        connector_status = {
            "brave": _safe_status("controller.brave_search", "brave_search_status"),
            "google_workspace": _safe_status("controller.google_workspace_adapter", "get_google_workspace_status"),
            "rclone_drive": _safe_status("controller.rclone_drive_adapter", "get_rclone_drive_status"),
            "github": _safe_status("controller.github_adapter", "get_github_status"),
            "microsoft_graph": _safe_status("controller.microsoft_graph_adapter", "get_microsoft_graph_status"),
            "sharepoint": _safe_status("controller.sharepoint_pnp_adapter", "get_sharepoint_status"),
            "vps": _safe_status("controller.vps_deploy_adapter", "get_vps_deploy_status"),
            "ziel_policy": _safe_status("controller.ziel_policy", "ziel_policy_status"),
        }

    tool_names = tuple(dict.fromkeys((*registered_tools, *bridge_tools)))
    return {
        "status": "observed",
        "tool_names": list(tool_names),
        "registered_tool_count": len(registered_tools),
        "bridge_tool_count": len(bridge_tools),
        "tool_bridge": tool_bridge,
        "slash_agents": slash_agents,
        "connector_status": connector_status,
        "secrets_returned": False,
        "fake_success": False,
    }


def _safe_status(module_name: str, function_name: str) -> dict[str, Any]:
    try:
        module = __import__(module_name, fromlist=[function_name])
        fn = getattr(module, function_name)
        return _redact(fn())
    except Exception as exc:
        return {"status": "unavailable", "reason": str(exc), "fake_success": False}


def _approval_policy() -> dict[str, Any]:
    return {
        "approval_phrase": APPROVAL_PHRASE,
        "case_sensitive": True,
        "private_reads_require_approval": True,
        "mutations_require_approval": True,
        "connector_writes_preview_first": True,
        "self_copy_install_v1": "dry_run_manifest_only",
        "secrets_returned": False,
        "fake_success": False,
    }


def _public_interfaces() -> dict[str, dict[str, str]]:
    return {
        "agent_architecture": {"method": "GET", "path": "/api/ouroboros/agents/architecture"},
        "critic_review": {"method": "POST", "path": "/api/ouroboros/agents/architecture/review"},
        "agent_architecture_review": {"method": "POST", "path": "/api/ouroboros/agents/architecture/review"},
        "agent_runtime_jobs": {"method": "GET", "path": "/api/agent-runtime/jobs"},
        "tool_bridge_status": {"method": "GET", "path": "/api/agent-runtime/tools/status"},
        "runtime_doctor": {"method": "GET", "path": "/api/ouroboros/runtime/doctor"},
        "connector_status": {"method": "GET", "path": "/trainer/status"},
        "slash_agents": {"method": "POST", "path": "/api/cockpit/chat", "prefix": "/"},
    }


def _agent_interfaces(agent_id: str) -> list[dict[str, str]]:
    interfaces = _public_interfaces()
    if agent_id == "codex":
        return [interfaces["agent_runtime_jobs"], interfaces["tool_bridge_status"], {"method": "POST", "path": "/api/codex/run"}]
    if agent_id == "web_scout":
        return [{"method": "POST", "path": "/api/ouroboros/search/brave"}, {"method": "POST", "path": "/api/ouroboros/research/browser"}]
    if agent_id == "communicator":
        return [{"method": "POST", "path": "/api/cockpit/chat"}, {"method": "GET", "path": "/api/world-agent/status"}]
    return [interfaces["critic_review"], interfaces["runtime_doctor"], interfaces["tool_bridge_status"]]


def _risk_categories(
    *,
    private_data: bool,
    mutating: bool,
    connector_write: bool,
    browser_control: bool,
    external_browser_read: bool,
    shell: bool,
    vps_network: bool,
    self_copy_install: bool,
    public_read: bool,
) -> list[str]:
    categories: list[str] = []
    if public_read:
        categories.append("public_read")
    if private_data:
        categories.append("private_data")
    if mutating:
        categories.append("filesystem_or_state_write")
    if shell:
        categories.append("shell")
    if external_browser_read:
        categories.append("external_browser_read")
    if browser_control:
        categories.append("browser_control")
    if connector_write:
        categories.append("connector_write")
    if vps_network:
        categories.append("vps_or_network")
    if self_copy_install:
        categories.append("self_copy_install")
    return list(dict.fromkeys(categories or ["local_preview"]))


def _risk_level(*, categories: list[str], blocked: bool, approval_required: bool) -> str:
    if blocked or "self_copy_install" in categories or "connector_write" in categories or "vps_or_network" in categories:
        return "critical"
    if approval_required or "shell" in categories or "filesystem_or_state_write" in categories:
        return "high"
    if "private_data" in categories or "browser_control" in categories or "external_browser_read" in categories:
        return "medium"
    return "low"


def _dry_run_manifest(
    *,
    prompt: str,
    action: str,
    tool: str,
    agent_id: str,
    categories: list[str],
    self_copy_install: bool,
) -> dict[str, Any]:
    if self_copy_install:
        steps = [
            "Inventariseer doelplatform en privileges zonder bestanden te kopieren.",
            "Maak een platform-specifieke installer/checklist en rollbackplan.",
            "Toon alle netwerkdoelen, paden en te schrijven bestanden als preview.",
            "Vraag een aparte expliciete menselijke deploy/install-taak voordat uitvoering wordt gebouwd.",
        ]
        target_platforms = ["windows", "macos", "linux", "iphone"]
    else:
        steps = [
            "Vat intent, tool, data-scope en risico samen.",
            "Controleer of private data of mutatie exact Akkoord vereist.",
            "Routeer uitvoering, indien later toegestaan, via bestaande ToolBridge/adapter.",
        ]
        target_platforms = []
    return {
        "status": "preview",
        "execution_performed": False,
        "agent_id": agent_id,
        "tool": tool,
        "action": action,
        "prompt_hash": hashlib.sha256(prompt.encode("utf-8", errors="replace")).hexdigest()[:16],
        "risk_categories": categories,
        "target_platforms": target_platforms,
        "steps": steps,
        "rollback": "Geen rollback nodig: reviewroute voert niets uit.",
        "network": "Geen netwerkactie uitgevoerd.",
        "writes": "Geen bestand of remote state gewijzigd.",
    }


def _store_review_audit(result: Mapping[str, Any]) -> dict[str, Any]:
    payload = _redact(result)
    stored: dict[str, Any] = {"trigger_action": {"status": "skipped"}, "ooda": {"status": "skipped"}, "fake_success": False}
    try:
        from controller.memory_event_router import record_trigger_action

        stored["trigger_action"] = record_trigger_action(
            trigger="agent_architecture_review",
            action=str(payload.get("decision") or "critic_review"),
            route="agent_architecture",
            status=str(payload.get("status") or "unknown"),
            payload=payload.get("action") if isinstance(payload.get("action"), Mapping) else {},
            result={"risk_categories": payload.get("risk_categories"), "blocked": payload.get("critic", {}).get("blocked_reasons") if isinstance(payload.get("critic"), Mapping) else []},
            approval_required=bool(payload.get("approval_required")),
            approval_status=str(payload.get("approval_status") or ""),
            source_trace={"review_id": payload.get("review_id"), "agent": "criticus"},
        )
    except Exception as exc:
        stored["trigger_action"] = {"status": "error", "stored": False, "reason": str(exc), "fake_success": False}
    try:
        from controller.ooda_hippocampus import record_ooda_event

        stored["ooda"] = record_ooda_event(
            phase="decide",
            session_id=str(payload.get("review_id") or "agent_architecture_review"),
            event_kind="critic_review",
            route="agent_architecture",
            status=str(payload.get("status") or "unknown"),
            payload=payload,
            approval_required=bool(payload.get("approval_required")),
            approval_status=str(payload.get("approval_status") or ""),
            source="controller.ouroboros_agent_architecture",
            source_type="critic_review",
            taint="local_audit",
            learnable=False,
            audit_only=True,
        )
    except Exception as exc:
        stored["ooda"] = {"status": "error", "stored": False, "reason": str(exc), "fake_success": False}
    return stored


def _canonical_agent_id(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_")
    if text in AGENT_IDS:
        return text
    if text in {"critic", "criticus", "reviewer"}:
        return "criticus"
    if text in {"web", "scout", "webscout"}:
        return "web_scout"
    if text in {"comm", "uitlegger"}:
        return "communicator"
    return "criticus"


def _requested_mode(value: Any) -> str:
    text = str(value or "preview").strip().lower()
    if text in {"execute", "run", "apply"}:
        return "execute"
    if text in {"dry_run", "dry-run", "preview", "plan"}:
        return "preview"
    return "preview"


def _review_id(payload: Mapping[str, Any], categories: list[str], status: str) -> str:
    seed = json.dumps({"payload": _redact(payload), "categories": categories, "status": status}, ensure_ascii=False, sort_keys=True, default=str)
    return "critic_" + hashlib.sha256(seed.encode("utf-8", errors="replace")).hexdigest()[:24]


def _clean_text(value: Any, limit: int) -> str:
    return str(value or "").replace("\x00", " ").strip()[:limit]


def _redact(value: Any) -> Any:
    if isinstance(value, Mapping):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            text_key = str(key)
            if any(marker in text_key.lower() for marker in SECRET_KEY_MARKERS):
                clean[text_key] = "[REDACTED]"
            else:
                clean[text_key] = _redact(item)
        return clean
    if isinstance(value, list):
        return [_redact(item) for item in value[:100]]
    if isinstance(value, tuple):
        return [_redact(item) for item in value[:100]]
    if isinstance(value, str):
        return SECRET_VALUE_RE.sub(lambda match: f"{match.group(1)}=[REDACTED]", value)[:6000]
    return value
