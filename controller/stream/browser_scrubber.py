# controller/stream/browser_scrubber.py
# WINTRIP-AGENT/1.0 — Browser ingest perimeter for untrusted web content.

from __future__ import annotations

import difflib
import hashlib
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable
from urllib.parse import urlparse

from controller.scrubber import scrub_data


SCRUBBER_VERSION = "browser-action-scrubber/1.0"
DEFAULT_APPROVAL_PHRASE = "Akkoord"
TEACHABLE_MACHINE_HOST = "teachablemachine.withgoogle.com"
TAINT_UNTRUSTED_WEB = "untrusted_web"

ALLOWED_BROWSER_ACTIONS = ("read", "scroll", "navigate")
BLOCKED_BROWSER_ACTIONS = ("click", "type", "upload", "submit", "download", "execute_script")

_MAX_TEXT_ENV = "WINTRIP_BROWSER_SCRUB_MAX_CHARS"
_DEFAULT_MAX_TEXT = 16_384

_INJECTION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("prompt_injection", re.compile(r"(?i)\b(ignore|forget|override)\s+(all\s+)?(previous|prior)\s+instructions\b")),
    ("system_prompt_probe", re.compile(r"(?i)\b(system prompt|developer message|hidden instruction)\b")),
    ("tool_call_request", re.compile(r"(?i)\b(tool call|function_call|execute tool|run command|shell command)\b")),
    ("credential_request", re.compile(r"(?i)\b(api key|password|passwd|secret|token|credential)\b")),
    ("exfiltration", re.compile(r"(?i)\b(exfiltrate|send.*secret|leak.*key|copy.*\.env)\b")),
    ("chat_template", re.compile(r"(?i)(<\|system\|>|\[\[/?INST\]\]|###\s*system|###\s*developer)")),
)

_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


@dataclass(frozen=True)
class ScrubbedBrowserContent:
    source_url: str
    source_host: str
    original_text: str
    scrubbed_text: str
    diff_view: str
    diff_hash: str
    blocked_patterns: tuple[str, ...]
    allowed_actions: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    taint: str
    requires_approval: bool
    approval_status: str
    approval_phrase: str
    scrubbed_at: str
    scrubber_version: str = SCRUBBER_VERSION

    def metadata(self) -> dict[str, str | bool]:
        return {
            "taint": self.taint,
            "trust_level": "external_web_scrubbed",
            "source_url": self.source_url,
            "source_host": self.source_host,
            "scrubber_version": self.scrubber_version,
            "scrubbed_at": self.scrubbed_at,
            "blocked_patterns": ",".join(self.blocked_patterns),
            "allowed_actions": ",".join(self.allowed_actions),
            "blocked_actions": ",".join(self.blocked_actions),
            "requires_approval": self.requires_approval,
            "approval_status": self.approval_status,
            "approval_phrase": self.approval_phrase,
            "diff_hash": self.diff_hash,
        }

    def to_raw_item(self, title: str = "Browser ingest") -> dict[str, object]:
        tags = ["browser_ingest", "untrusted_web"]
        if self.source_host == TEACHABLE_MACHINE_HOST:
            tags.append("teachablemachine")
        raw = {
            "title": title,
            "text": self.scrubbed_text,
            "url": self.source_url,
            "source_type": "url",
            "tags": tags,
        }
        raw.update(self.metadata())
        return raw


def approval_matches(value: object, phrase: str | None = None) -> bool:
    expected = (phrase or os.getenv("WINTRIP_APPROVAL_PHRASE") or DEFAULT_APPROVAL_PHRASE).strip()
    return str(value or "").strip().casefold() == expected.casefold()


def validate_teachablemachine_url(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or host != TEACHABLE_MACHINE_HOST:
        raise ValueError(
            "Browser wrapper accepteert alleen https://teachablemachine.withgoogle.com als expliciete perimeter."
        )
    return host


def scrub_untrusted_browser_text(text: str) -> tuple[str, tuple[str, ...]]:
    raw = str(text or "")
    raw = raw.replace("\x00", " ")
    raw = _ANSI_RE.sub("", raw)
    raw = "".join(ch for ch in raw if ord(ch) >= 32 or ch in ("\n", "\t", "\r"))
    raw = raw.replace("\r", "\n")

    blocked: list[str] = []
    scrubbed = scrub_data(raw)
    for name, pattern in _INJECTION_PATTERNS:
        if pattern.search(scrubbed):
            blocked.append(name)
            scrubbed = pattern.sub(f"[BLOCKED:{name}]", scrubbed)

    max_len = _max_text_len()
    if len(scrubbed) > max_len:
        blocked.append("truncated")
        scrubbed = scrubbed[:max_len] + "\n[TRUNCATED_BY_BROWSER_SCRUBBER]"

    return scrubbed.strip(), tuple(dict.fromkeys(blocked))


def prepare_teachablemachine_ingest(
    url: str,
    browser_text: str,
    approval: object = None,
    title: str = "Teachable Machine browser ingest",
) -> ScrubbedBrowserContent:
    validate_teachablemachine_url(url)
    return prepare_browser_ingest(
        url=url,
        browser_text=browser_text,
        approval=approval,
        title=title,
        require_teachablemachine=True,
    )


def prepare_browser_ingest(
    url: str,
    browser_text: str,
    approval: object = None,
    title: str = "Browser ingest",
    require_teachablemachine: bool = False,
) -> ScrubbedBrowserContent:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https") or not host:
        raise ValueError("Browser ingest vereist een http(s)-URL met host.")
    if require_teachablemachine:
        host = validate_teachablemachine_url(url)

    scrubbed, blocked = scrub_untrusted_browser_text(browser_text)
    diff_view = _diff_view(str(browser_text or ""), scrubbed, title=title)
    diff_hash = hashlib.sha256(diff_view.encode("utf-8", errors="replace")).hexdigest()
    phrase = os.getenv("WINTRIP_APPROVAL_PHRASE") or DEFAULT_APPROVAL_PHRASE
    approved = approval_matches(approval, phrase)

    return ScrubbedBrowserContent(
        source_url=url,
        source_host=host,
        original_text=str(browser_text or ""),
        scrubbed_text=scrubbed,
        diff_view=diff_view,
        diff_hash=diff_hash,
        blocked_patterns=blocked,
        allowed_actions=ALLOWED_BROWSER_ACTIONS,
        blocked_actions=BLOCKED_BROWSER_ACTIONS,
        taint=TAINT_UNTRUSTED_WEB,
        requires_approval=True,
        approval_status="approved" if approved else "pending_philip_akkoord",
        approval_phrase=phrase,
        scrubbed_at=datetime.now(tz=timezone.utc).isoformat(),
    )


def _diff_view(original: str, scrubbed: str, title: str) -> str:
    before = _bounded_lines(original)
    after = _bounded_lines(scrubbed)
    diff = list(
        difflib.unified_diff(
            before,
            after,
            fromfile=f"{title}:browser-original",
            tofile=f"{title}:browser-scrubbed",
            lineterm="",
        )
    )
    if not diff:
        diff = [
            f"--- {title}:browser-original",
            f"+++ {title}:browser-scrubbed",
            "@@ approval-gate @@",
            "Browser content unchanged by scrubber; still UNTRUSTED until Philip says Akkoord.",
        ]
    return "\n".join(diff)


def _bounded_lines(text: str, max_lines: int = 240) -> list[str]:
    lines = str(text or "").splitlines()
    if len(lines) <= max_lines:
        return lines
    hidden = len(lines) - max_lines
    return lines[:max_lines] + [f"[DIFF TRUNCATED: {hidden} lines hidden]"]


def _max_text_len() -> int:
    try:
        return max(1024, min(262_144, int(os.getenv(_MAX_TEXT_ENV, str(_DEFAULT_MAX_TEXT)))))
    except ValueError:
        return _DEFAULT_MAX_TEXT


def metadata_to_raw_tags(metadata: dict[str, object], extra: Iterable[str] = ()) -> list[str]:
    tags = ["browser_ingest", "untrusted_web", *extra]
    blocked = str(metadata.get("blocked_patterns") or "")
    if blocked:
        tags.append("scrubbed")
    return list(dict.fromkeys(tags))
