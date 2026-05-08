"""Canonical intent classification for cockpit-to-agentic routing."""

from __future__ import annotations

import re
from dataclasses import dataclass
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


@dataclass(frozen=True)
class AgenticIntent:
    route: str
    is_agentic: bool
    is_slash_alias: bool
    approval_present: bool
    reason: str
    normalized_prompt: str
    slash_agent: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "route": self.route,
            "is_agentic": self.is_agentic,
            "is_slash_alias": self.is_slash_alias,
            "approval_present": self.approval_present,
            "reason": self.reason,
            "normalized_prompt": self.normalized_prompt,
            "slash_agent": self.slash_agent,
            "fake_success": False,
        }


def classify_agentic_intent(prompt: object, *, role: object = "", approval: object = "") -> AgenticIntent:
    raw = str(prompt or "").strip()
    lowered = raw.lower()
    clean_role = str(role or "").strip().lower()
    approval_present = str(approval or "").strip() == APPROVAL_PHRASE or _has_inline_approval(raw)
    if not raw:
        return AgenticIntent("normal_chat", False, False, approval_present, "empty_prompt", raw)

    slash = SLASH_RE.match(raw)
    if slash:
        return AgenticIntent("slash_agent", False, True, approval_present, "slash_alias", raw, slash_agent=slash.group(1).lower())

    if clean_role in {"agentic", "agentic_core", "agent"}:
        return AgenticIntent("agentic_processor", True, False, approval_present, "role_forced_agentic", raw)

    without_approval = _strip_inline_approval(raw).lower()
    if without_approval.startswith(PLAIN_CODE_PREFIXES):
        return AgenticIntent("normal_chat", False, False, approval_present, "plain_code_generation", raw)

    if URL_OR_DOMAIN_RE.search(without_approval) and ACTION_VERB_RE.search(without_approval):
        return AgenticIntent("agentic_processor", True, False, approval_present, "url_action", raw)

    if any(marker in without_approval for marker in ("schrijf", "write", "save")) and re.search(r"\b[\w./-]+\.[a-z0-9]{1,8}\b", without_approval):
        return AgenticIntent("agentic_processor", True, False, approval_present, "file_mutation", raw)

    if "maak" in without_approval and any(marker in without_approval for marker in ("bestand", "file", "map", "directory")):
        return AgenticIntent("agentic_processor", True, False, approval_present, "file_creation", raw)

    if any(marker in without_approval for marker in ("draai test", "run test", "voer test", "pytest", "unittest")):
        return AgenticIntent("agentic_processor", True, False, approval_present, "test_execution", raw)

    if any(marker in without_approval for marker in AGENTIC_MARKERS):
        return AgenticIntent("agentic_processor", True, False, approval_present, "agentic_marker", raw)

    return AgenticIntent("normal_chat", False, False, approval_present, "no_agentic_intent", raw)


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
