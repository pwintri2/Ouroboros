"""Canonical intent classification for cockpit-to-agentic routing."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


APPROVAL_PHRASE = "Akkoord"
SLASH_RE = re.compile(r"^/(codex|deepseek|atlas|ruflo|roo|claude|agents)\b", re.IGNORECASE)
URL_OR_DOMAIN_RE = re.compile(
    r"(?i)\b(?:https?://|www\.)[^\s<>()]+|\b[a-z0-9][a-z0-9.-]*\.(?:nl|com|org|net|io|dev|app)(?::\d+)?(?:/[^\s<>()]*)?"
)
ACTION_VERB_RE = re.compile(
    r"(?i)\b(open|openen|start|lanceer|bezoek|ga\s+naar|navigeer|zoek|lees|download|haal|check|controleer)\b"
)
AGENTIC_MARKERS = (
    "zoek",
    "internet",
    "brave",
    "browser",
    "web preview",
    "preview",
    "bestand",
    "bestanden",
    "file",
    "files",
    "map",
    "folder",
    "directory",
    "lees",
    "lijst",
    "toon bestanden",
    "zoek in",
    "shell",
    "commando",
    "command",
    "voer uit",
    "uitvoeren",
    "draai",
    "run ",
    "test ",
    "run tests",
    "unittest",
    "pytest",
    "bouw",
    "build",
    "maak",
    "programmeer",
    "functie ontbreekt",
    "capability",
    "missing",
    "codex",
    "gemini",
    "grok",
    "agentisch",
    "agentic",
    "agents",
    "subagent",
    "sub-agent",
    "deepseek",
    "atlas",
    "workflow",
    "orchestratie",
    "delegatie",
    "handoff",
)
PLAIN_CODE_PREFIXES = ("schrijf python", "maak python", "genereer python", "write python")
AGENT_SELECTION_MARKERS = (
    "welke agent",
    "welke tool",
    "welke adapter",
    "kies agent",
    "selecteer agent",
    "agent kiezen",
    "which agent",
    "which tool",
    "choose an agent",
    "select an agent",
    "agent action",
    "agent nodig",
    "tool nodig",
)
WEB_SEARCH_MARKERS = (
    "internet",
    "web search",
    "search the web",
    "zoek online",
    "zoek op internet",
    "brave",
    "online zoeken",
    "actueel",
    "actuele",
    "laatste",
    "nieuws",
    "vandaag",
    "latest",
    "current",
    "recent",
)
NS_MARKERS = ("ns", "ns.nl", "trein", "sprinter", "intercity", "station", "perron")
OV9292_MARKERS = ("9292", "ov9292", "ov 9292", "bus", "tram", "metro", "ov-fiets")
TRAVEL_MARKERS = (
    "reisplanner",
    "routeplanner",
    "reisadvies",
    "ov ",
    "openbaar vervoer",
    "travel planner",
    "transit",
    "vertrek",
    "aankomst",
    "vertrektijd",
    "aankomsttijd",
)
GMAIL_MARKERS = ("gmail", "google mail", "mailbox", "inbox", "e-mail", "email")
DRIVE_MARKERS = ("google drive", "gdrive", "g-drive", "drive map", "drive folder")
GITHUB_MARKERS = ("github", "git hub")
VPS_MARKERS = ("vps", "ssh", "server login", "server deploy", "rsync", "scp", "remote server")
MUTATING_VERB_RE = re.compile(
    r"(?i)\b("
    r"schrijf|write|save|sla\s+op|maak|create|upload|verwijder|delete|remove|"
    r"wijzig|edit|patch|update|aanpassen|pas\s+aan|verstuur|send|reply|antwoord|post|publish|plaats|archive|label|"
    r"deploy|sync|synchroniseer|login|log\s+in|push|merge|commit|run|start|execute|voer\s+uit"
    r")\b"
)
READ_ONLY_VERB_RE = re.compile(
    r"(?i)\b(lees|read|zoek|search|list|lijst|toon|show|check|controleer|summarize|vat\s+samen|inspecteer|inspect)\b"
)


@dataclass(frozen=True)
class AgenticIntent:
    route: str
    is_agentic: bool
    is_slash_alias: bool
    approval_present: bool
    reason: str
    normalized_prompt: str
    slash_agent: str = ""
    categories: tuple[str, ...] = field(default_factory=tuple)
    services: tuple[str, ...] = field(default_factory=tuple)
    target_tool: str = ""
    action_type: str = "none"
    read_only: bool = False
    private: bool = False
    mutating: bool = False
    approval_required: bool = False
    routing_hint: str = ""
    plan_hints: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, Any]:
        return {
            "route": self.route,
            "is_agentic": self.is_agentic,
            "is_slash_alias": self.is_slash_alias,
            "approval_present": self.approval_present,
            "reason": self.reason,
            "normalized_prompt": self.normalized_prompt,
            "slash_agent": self.slash_agent,
            "categories": list(self.categories),
            "services": list(self.services),
            "target_tool": self.target_tool,
            "action_type": self.action_type,
            "read_only": self.read_only,
            "private": self.private,
            "mutating": self.mutating,
            "approval_required": self.approval_required,
            "routing_hint": self.routing_hint,
            "plan_hints": [dict(item) for item in self.plan_hints],
            "metadata": {
                "categories": list(self.categories),
                "services": list(self.services),
                "target_tool": self.target_tool,
                "action_type": self.action_type,
                "read_only": self.read_only,
                "private": self.private,
                "mutating": self.mutating,
                "approval_required": self.approval_required,
                "routing_hint": self.routing_hint,
            },
            "fake_success": False,
        }


def classify_agentic_intent(prompt: object, *, role: object = "", approval: object = "") -> AgenticIntent:
    raw = str(prompt or "").strip()
    lowered = raw.lower()
    clean_role = str(role or "").strip().lower()
    approval_present = str(approval or "").strip() == APPROVAL_PHRASE or _has_inline_approval(raw)
    without_approval_raw = _strip_inline_approval(raw)
    without_approval = without_approval_raw.lower()
    metadata = _prompt_metadata(without_approval_raw, approval_present=approval_present)
    if not raw:
        return _intent("normal_chat", False, False, approval_present, "empty_prompt", raw, metadata)

    slash = SLASH_RE.match(raw)
    if slash:
        return _intent(
            "slash_agent",
            False,
            True,
            approval_present,
            "slash_alias",
            raw,
            metadata,
            slash_agent=slash.group(1).lower(),
        )

    if clean_role in {"agentic", "agentic_core", "agent"}:
        return _intent("agentic_processor", True, False, approval_present, "role_forced_agentic", raw, metadata)

    if without_approval.startswith(PLAIN_CODE_PREFIXES):
        return _intent("normal_chat", False, False, approval_present, "plain_code_generation", raw, metadata)

    connector_target_tools = {
        "connector_intent_preview",
        "gmail_status",
        "gmail_search",
        "google_drive_status",
        "google_drive_list",
        "github_status",
        "github_repo",
        "github_search_repositories",
        "vps_status",
        "vps_login_check",
        "vps_sync_preview",
        "vps_sync_execute",
    }
    if metadata["target_tool"] in connector_target_tools:
        return _intent("agentic_processor", True, False, approval_present, "connector_boundary_intent", raw, metadata)

    if metadata["target_tool"] in {"brave_search", "ns_travel_advice", "ov9292_travel_advice", "agentic_ecosystem_context"}:
        return _intent("agentic_processor", True, False, approval_present, str(metadata["routing_hint"]), raw, metadata)

    if URL_OR_DOMAIN_RE.search(without_approval) and ACTION_VERB_RE.search(without_approval):
        return _intent("agentic_processor", True, False, approval_present, "url_action", raw, metadata)

    if any(marker in without_approval for marker in ("schrijf", "write", "save")) and re.search(r"\b[\w./-]+\.[a-z0-9]{1,8}\b", without_approval):
        return _intent("agentic_processor", True, False, approval_present, "file_mutation", raw, metadata)

    if "maak" in without_approval and any(marker in without_approval for marker in ("bestand", "file", "map", "directory")):
        return _intent("agentic_processor", True, False, approval_present, "file_creation", raw, metadata)

    if any(marker in without_approval for marker in ("draai test", "run test", "voer test", "pytest", "unittest")):
        return _intent("agentic_processor", True, False, approval_present, "test_execution", raw, metadata)

    if any(marker in without_approval for marker in AGENTIC_MARKERS):
        return _intent("agentic_processor", True, False, approval_present, "agentic_marker", raw, metadata)

    return _intent("normal_chat", False, False, approval_present, "no_agentic_intent", raw, metadata)


def should_use_agentic_processor(prompt: object, *, role: object = "", approval: object = "") -> bool:
    return classify_agentic_intent(prompt, role=role, approval=approval).is_agentic


def _has_inline_approval(prompt: str) -> bool:
    if prompt == APPROVAL_PHRASE:
        return True
    return prompt.startswith(APPROVAL_PHRASE) and len(prompt) > len(APPROVAL_PHRASE) and prompt[len(APPROVAL_PHRASE)] in {" ", "\t", ":", "-", ","}


def _strip_inline_approval(prompt: str) -> str:
    if _has_inline_approval(prompt):
        return prompt[len(APPROVAL_PHRASE) :].strip(" \t:,-")
    return prompt


def _intent(
    route: str,
    is_agentic: bool,
    is_slash_alias: bool,
    approval_present: bool,
    reason: str,
    raw: str,
    metadata: dict[str, Any],
    *,
    slash_agent: str = "",
) -> AgenticIntent:
    return AgenticIntent(
        route=route,
        is_agentic=is_agentic,
        is_slash_alias=is_slash_alias,
        approval_present=approval_present,
        reason=reason,
        normalized_prompt=raw,
        slash_agent=slash_agent,
        categories=tuple(metadata.get("categories") or ()),
        services=tuple(metadata.get("services") or ()),
        target_tool=str(metadata.get("target_tool") or ""),
        action_type=str(metadata.get("action_type") or "none"),
        read_only=bool(metadata.get("read_only")),
        private=bool(metadata.get("private")),
        mutating=bool(metadata.get("mutating")),
        approval_required=bool(metadata.get("approval_required")),
        routing_hint=str(metadata.get("routing_hint") or ""),
        plan_hints=tuple(dict(item) for item in (metadata.get("plan_hints") or ())),
    )


def _prompt_metadata(prompt: str, *, approval_present: bool = False) -> dict[str, Any]:
    text = str(prompt or "").strip()
    lowered = text.lower()
    categories: list[str] = []
    services: list[str] = []

    agent_selection = _wants_agent_selection(lowered)
    web_search = _wants_web_search(lowered)
    ns = _wants_ns(lowered)
    ov9292 = _wants_9292(lowered)
    travel = ov9292 or _wants_travel(lowered)
    gmail = _wants_gmail(lowered)
    drive = _wants_drive(lowered)
    github = _wants_github(lowered)
    vps = _wants_vps(lowered)
    connector_status = _wants_connector_status(lowered)
    browser_action = bool(URL_OR_DOMAIN_RE.search(text) and ACTION_VERB_RE.search(lowered))
    file_mutation = bool(
        any(marker in lowered for marker in ("schrijf", "write", "save"))
        and re.search(r"\b[\w./-]+\.[a-z0-9]{1,8}\b", lowered)
    )
    local_file_action = file_mutation or any(marker in lowered for marker in ("toon bestanden", "lijst bestanden", "list files", "zoek in bestanden", "search files"))

    if agent_selection:
        categories.append("agent_selection")
        services.append("agent_runtime")
    if web_search:
        categories.append("web_search")
        services.append("brave")
    if travel:
        categories.append("travel")
        services.append("travel")
    if ns:
        services.append("ns")
    if ov9292:
        services.append("9292")
    if gmail:
        categories.append("connector")
        services.append("gmail")
    if drive:
        categories.append("connector")
        services.append("google_drive")
    if github:
        categories.append("connector")
        services.append("github")
    if vps:
        categories.append("vps")
        services.append("vps")
    if browser_action:
        categories.append("browser_action")
        services.append("browser")
    if local_file_action:
        categories.append("local_files")

    mutating = bool(MUTATING_VERB_RE.search(lowered) or file_mutation)
    private = bool((gmail and not connector_status) or (drive and not connector_status) or vps or (github and not connector_status and (_github_private_context(lowered) or mutating)))
    connector_boundary = bool(gmail or drive or github or vps)
    if browser_action:
        mutating = True

    if private and mutating:
        action_type = "private_mutating"
    elif private:
        action_type = "private_read"
    elif mutating:
        action_type = "mutating"
    elif categories:
        action_type = "read_only"
    else:
        action_type = "none"
    read_only = action_type == "read_only"
    approval_required = bool(private or mutating or vps or (gmail and not connector_status) or (drive and not connector_status))

    target_tool = ""
    routing_hint = "no_agentic_intent"
    other_private_connector = bool(gmail or drive or (github and (_github_private_context(lowered) or mutating)))
    if vps and other_private_connector:
        target_tool = "connector_intent_preview"
        routing_hint = "connector_preview_required"
    elif vps:
        if connector_status:
            target_tool = "vps_status"
            routing_hint = "vps_status_readonly"
        elif _wants_vps_login_check(lowered):
            target_tool = "vps_login_check"
            routing_hint = "vps_login_check_readonly"
        elif _wants_vps_execute(lowered):
            target_tool = "vps_sync_execute"
            routing_hint = "vps_sync_execute_approval_required"
        else:
            target_tool = "vps_sync_preview"
            routing_hint = "vps_sync_preview_first"
    elif (connector_boundary and mutating) or (github and _github_private_context(lowered) and not connector_status):
        target_tool = "connector_intent_preview"
        routing_hint = "connector_preview_required"
    elif gmail:
        target_tool = "gmail_status" if connector_status else "gmail_search"
        routing_hint = "gmail_status_readonly" if connector_status else "gmail_private_read_approval_required"
    elif drive:
        target_tool = "google_drive_status" if connector_status else "google_drive_list"
        routing_hint = "google_drive_status_readonly" if connector_status else "google_drive_private_read_approval_required"
    elif github:
        target_tool = "github_status" if connector_status else ("github_repo" if _github_repo_mentioned(text) else "github_search_repositories")
        routing_hint = "github_status_readonly" if connector_status else "github_public_readonly"
    elif travel:
        target_tool = "ov9292_travel_advice" if _prefers_9292(lowered, ns=ns, ov9292=ov9292) else "ns_travel_advice"
        routing_hint = "travel_readonly"
    elif web_search:
        target_tool = "brave_search"
        routing_hint = "web_search_readonly"
    elif agent_selection:
        target_tool = "agentic_ecosystem_context"
        routing_hint = "agent_selection_readonly"
    elif browser_action:
        target_tool = "browser_open_url"
        routing_hint = "browser_action_approval_required"
    elif local_file_action:
        target_tool = "write_file" if file_mutation else "list_files"
        routing_hint = "local_file_action"

    categories = _unique(categories)
    services = _unique(services)
    plan_hints = _plan_hints(
        target_tool=target_tool,
        text=text,
        action_type=action_type,
        approval_required=approval_required,
        approval_present=approval_present,
        categories=categories,
        services=services,
    )
    return {
        "categories": categories,
        "services": services,
        "target_tool": target_tool,
        "action_type": action_type,
        "read_only": read_only,
        "private": private,
        "mutating": mutating,
        "approval_required": approval_required,
        "routing_hint": routing_hint,
        "plan_hints": plan_hints,
    }


def _plan_hints(
    *,
    target_tool: str,
    text: str,
    action_type: str,
    approval_required: bool,
    approval_present: bool,
    categories: list[str],
    services: list[str],
) -> tuple[dict[str, Any], ...]:
    if not target_tool:
        return ()
    hint: dict[str, Any] = {
        "tool": target_tool,
        "action_type": action_type,
        "approval_required": bool(approval_required),
        "approval_present": bool(approval_present),
        "categories": list(categories),
        "services": list(services),
        "prompt_preview": text[:240],
    }
    if target_tool == "brave_search":
        hint["args_hint"] = {"query": text[:400], "limit": 5, "llm_context": True}
    elif target_tool in {"ns_travel_advice", "ov9292_travel_advice"}:
        hint["args_hint"] = {"query": text[:1000]}
    elif target_tool == "connector_intent_preview":
        hint["args_hint"] = {"prompt": text[:1000], "services": list(services), "preview_only": True}
    elif target_tool in {"vps_status", "vps_login_check", "vps_sync_preview", "vps_sync_execute"}:
        hint["args_hint"] = {"remote_path": "", "preview_first": target_tool != "vps_sync_execute"}
    elif target_tool == "gmail_search":
        hint["args_hint"] = {"query": "in:inbox", "max_results": 5}
    elif target_tool == "google_drive_list":
        hint["args_hint"] = {"path": "", "max_items": 25, "adapter": "auto"}
    elif target_tool == "github_repo":
        hint["args_hint"] = {"repo": _github_repo_mentioned(text) or text[:200]}
    elif target_tool == "github_search_repositories":
        hint["args_hint"] = {"query": text[:400], "limit": 5}
    elif target_tool == "agentic_ecosystem_context":
        hint["args_hint"] = {"goal": text[:1000], "prefer_bridge": True}
    return (hint,)


def _wants_agent_selection(lowered: str) -> bool:
    if any(marker in lowered for marker in AGENT_SELECTION_MARKERS):
        return True
    return bool(re.search(r"\b(welke|which)\s+(agent|tool|tools|adapter|adapters)\b", lowered))


def _wants_web_search(lowered: str) -> bool:
    if any(marker in lowered for marker in WEB_SEARCH_MARKERS):
        return True
    return bool(re.search(r"\b(search|zoek)\b.*\b(web|internet|online)\b", lowered))


def _wants_ns(lowered: str) -> bool:
    return bool(re.search(r"\bns\b", lowered)) or any(marker in lowered for marker in NS_MARKERS if marker != "ns")


def _wants_9292(lowered: str) -> bool:
    return any(marker in lowered for marker in OV9292_MARKERS)


def _wants_travel(lowered: str) -> bool:
    return any(marker in f" {lowered} " for marker in TRAVEL_MARKERS) or bool(
        re.search(r"\b(train|transit|departure|arrival|platform|reis|route)\b", lowered)
    )


def _wants_gmail(lowered: str) -> bool:
    return any(marker in lowered for marker in GMAIL_MARKERS) or bool(re.search(r"\bmail(?:s|tje|bericht|berichten)?\b", lowered))


def _wants_drive(lowered: str) -> bool:
    return any(marker in lowered for marker in DRIVE_MARKERS)


def _wants_github(lowered: str) -> bool:
    return any(marker in lowered for marker in GITHUB_MARKERS)


def _wants_connector_status(lowered: str) -> bool:
    return any(marker in lowered for marker in ("status", "configured", "configuration", "connectie", "verbonden", "geconfigureerd", "beschikbaar", "available", "auth status", "token status"))


def _wants_vps(lowered: str) -> bool:
    if any(marker in lowered for marker in VPS_MARKERS):
        return True
    return "server" in lowered and any(marker in lowered for marker in ("login", "deploy", "sync", "ssh", "vps"))


def _wants_vps_login_check(lowered: str) -> bool:
    return any(marker in lowered for marker in ("login check", "check login", "ssh check", "ssh status", "kan ik inloggen", "login status")) or (
        "login" in lowered and any(marker in lowered for marker in ("check", "controleer", "status"))
    )


def _wants_vps_execute(lowered: str) -> bool:
    if any(marker in lowered for marker in ("dry-run", "dry run", "preview", "voorvertoning", "plan", "toon")):
        return False
    return any(marker in lowered for marker in ("execute", "voer uit", "echt sync", "werkelijk sync", "deploy now", "deploy nu", "publiceer", "sync execute"))


def _github_private_context(lowered: str) -> bool:
    return any(marker in lowered for marker in ("mijn github", "my github", "private repo", "prive repo", "token", "issue", "pull request", "secret"))


def _clean_github_repo_segment(value: str) -> str:
    return str(value or "").removesuffix(".git").strip(".,;:!?)]}'\"")


def _github_repo_mentioned(text: str) -> str:
    raw = str(text or "")
    url_match = re.search(r"github\.com[:/]+([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)", raw, re.IGNORECASE)
    if url_match:
        return f"{url_match.group(1)}/{_clean_github_repo_segment(url_match.group(2))}"
    match = re.search(r"\b([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)\b", raw)
    if match:
        return f"{match.group(1)}/{_clean_github_repo_segment(match.group(2))}"
    return ""


def _prefers_9292(lowered: str, *, ns: bool, ov9292: bool) -> bool:
    if ov9292:
        return True
    if ns:
        return False
    return any(marker in lowered for marker in ("openbaar vervoer", "ov ", "reisplanner", "routeplanner", "bus", "tram", "metro"))


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            output.append(text)
    return output
