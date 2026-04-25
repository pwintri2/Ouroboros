"""Browser and PAEU safety gates."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import urlparse


BLOCKED_HOSTS = {"localhost", "0.0.0.0"}


@dataclass(frozen=True)
class SafetyDecision:
    allowed: bool
    reason: str


def evaluate_url(url: str, allow_private_hosts: bool = False) -> SafetyDecision:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return SafetyDecision(False, f"blocked unsupported URL scheme: {parsed.scheme or 'empty'}")
    if not parsed.netloc:
        return SafetyDecision(False, "blocked URL without host")

    host = parsed.hostname or ""
    if host.lower() in BLOCKED_HOSTS and not allow_private_hosts:
        return SafetyDecision(False, f"blocked private host: {host}")

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return SafetyDecision(True, "public DNS host")

    if not allow_private_hosts and (ip.is_private or ip.is_loopback or ip.is_link_local):
        return SafetyDecision(False, f"blocked non-public IP host: {host}")
    return SafetyDecision(True, "public IP host")


def sanitize_query(text: str, max_length: int = 180) -> str:
    compact = " ".join(text.replace("\x00", " ").split())
    return compact[:max_length]
