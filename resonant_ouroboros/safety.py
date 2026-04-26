"""Browser and PAEU safety gates."""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
from urllib.parse import urlparse


BLOCKED_HOSTS = {"localhost", "0.0.0.0"}


@dataclass(frozen=True)
class SafetyDecision:
    allowed: bool
    reason: str


def evaluate_url(url: str, allow_private_hosts: bool = False) -> SafetyDecision:
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in {"http", "https"}:
        return SafetyDecision(False, f"blocked unsupported URL scheme: {parsed.scheme or 'empty'}")

    host = (parsed.hostname or "").lower()
    if not host:
        return SafetyDecision(False, "blocked URL without host")

    if allow_private_hosts:
        return SafetyDecision(True, "private host override enabled")

    if host in BLOCKED_HOSTS or host.endswith(".local") or host.endswith(".internal"):
        return SafetyDecision(False, f"blocked private host: {host}")

    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return SafetyDecision(True, "public DNS host")

    if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
        return SafetyDecision(False, f"blocked non-public IP host: {host}")
    return SafetyDecision(True, "public IP host")


def sanitize_query(text: str, max_length: int = 180) -> str:
    compact = " ".join((text or "").replace("\x00", " ").split())
    compact = compact.replace("[", "").replace("]", "").replace("{", "").replace("}", "")
    compact = compact.replace("<", "").replace(">", "")
    return compact[:max_length].strip()
