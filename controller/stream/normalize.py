# controller/stream/normalize.py
# Phase 7.X — Stream of Consciousness: Normalizer + Dedup Fingerprint
# Wintrip AI | task_id: wintrip-soc-001
#
# Verantwoordelijkheid:
#   - Zet ruwe stream-items (dict van elke bron) om naar een canoniek NormalizedItem.
#   - Levert een deterministisch content_hash voor deduplicatie.
#   - Geen externe dependencies: uitsluitend stdlib (hashlib, datetime, uuid, dataclasses).
#
# Contract:
#   NormalizedItem(id, title, text, url, published_at, tags, source_type,
#                  content_hash, source_hash)
#   normalize(raw: dict) -> NormalizedItem
#   fingerprint(item: NormalizedItem) -> str

from __future__ import annotations

import hashlib
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List


# ---------------------------------------------------------------------------
# Toegestane source_type waarden (uitbreidbaar, nooit willekeurige strings)
# ---------------------------------------------------------------------------
ALLOWED_SOURCE_TYPES = {"rss", "url", "manual", "chatgpt_macos_app"}

# Maximale veldlengtes om prompt-injection-payloads te begrenzen
_MAX_TITLE_LEN = 512
_MAX_TEXT_LEN = 16_384
_MAX_URL_LEN = 2_048
_MAX_TAG_LEN = 64
_MAX_TAGS = 20


# ---------------------------------------------------------------------------
# Datacontract
# ---------------------------------------------------------------------------
@dataclass
class NormalizedItem:
    """Canoniek stream-item. Alle velden zijn gegarandeerd aanwezig en veilig."""
    id: str               # deterministisch UUID5 op basis van content_hash
    title: str            # gesanitiseerde titel
    text: str             # gesanitiseerde inhoud (max _MAX_TEXT_LEN)
    url: str              # canonieke bron-URL of leeg
    published_at: str     # ISO 8601 UTC string
    tags: List[str]       # max _MAX_TAGS tags, elk max _MAX_TAG_LEN tekens
    source_type: str      # uit ALLOWED_SOURCE_TYPES
    content_hash: str     # sha256(title + text) — dedup sleutel
    source_hash: str      # sha256(url) — provenance sleutel


# ---------------------------------------------------------------------------
# Interne hulpfuncties
# ---------------------------------------------------------------------------
def _safe_str(value: object, max_len: int, fallback: str = "") -> str:
    """Converteert waarde naar string, trims whitespace, begrenst lengte."""
    if value is None:
        return fallback
    s = str(value).strip()
    # Verwijder ASCII control characters (prompt injection via null bytes e.d.)
    s = "".join(ch for ch in s if ord(ch) >= 32 or ch in ("\n", "\t"))
    return s[:max_len]


def _safe_tags(raw_tags: object) -> List[str]:
    """Normaliseert tags-veld naar een schone lijst."""
    if not isinstance(raw_tags, (list, tuple)):
        return []
    cleaned = []
    for t in raw_tags:
        tag = _safe_str(t, _MAX_TAG_LEN)
        if tag and tag not in cleaned:
            cleaned.append(tag)
        if len(cleaned) >= _MAX_TAGS:
            break
    return cleaned


def _safe_source_type(raw: object) -> str:
    """Valideert source_type tegen allowlist; valt terug op 'manual'."""
    candidate = _safe_str(raw, 64, "manual").lower()
    return candidate if candidate in ALLOWED_SOURCE_TYPES else "manual"


def _safe_published_at(raw: object) -> str:
    """Parseert datum of retourneert UTC-now als ISO 8601 string."""
    if isinstance(raw, datetime):
        dt = raw
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    if isinstance(raw, str) and raw.strip():
        try:
            # Probeer ISO-formaat direct
            dt = datetime.fromisoformat(raw.strip().rstrip("Z"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except ValueError:
            pass
    # Fallback: huidig UTC-moment
    return datetime.now(tz=timezone.utc).isoformat()


def _sha256(text: str) -> str:
    """Retourneert hex SHA-256 digest van een UTF-8 string."""
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def _deterministic_uuid(content_hash: str) -> str:
    """Maakt een reproduceerbaar UUID5 op basis van content_hash."""
    namespace = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # UUID namespace URL
    return str(uuid.uuid5(namespace, content_hash))


# ---------------------------------------------------------------------------
# Publieke interface
# ---------------------------------------------------------------------------
def normalize(raw: dict) -> NormalizedItem:
    """
    Zet een ruw stream-item (dict) om naar een NormalizedItem.

    Onbekende of ontbrekende velden worden afgehandeld met graceful fallbacks.
    Nooit een uitzondering gooien bij geldige (ook lege) input.

    Args:
        raw: dict met willekeurige velden van een streambron.

    Returns:
        NormalizedItem met alle velden gegarandeerd ingevuld.
    """
    if not isinstance(raw, dict):
        # Defensief: niet-dict input behandelen als leeg item
        raw = {}

    title = _safe_str(raw.get("title"), _MAX_TITLE_LEN, fallback="[geen titel]")
    text = _safe_str(raw.get("text") or raw.get("body") or raw.get("content"), _MAX_TEXT_LEN, fallback="")
    url = _safe_str(raw.get("url") or raw.get("link"), _MAX_URL_LEN, fallback="")
    published_at = _safe_published_at(raw.get("published_at") or raw.get("pubDate") or raw.get("date"))
    tags = _safe_tags(raw.get("tags") or raw.get("categories"))
    source_type = _safe_source_type(raw.get("source_type") or raw.get("type"))

    content_hash = _sha256(title + text)
    source_hash = _sha256(url) if url else _sha256("")
    item_id = _deterministic_uuid(content_hash)

    return NormalizedItem(
        id=item_id,
        title=title,
        text=text,
        url=url,
        published_at=published_at,
        tags=tags,
        source_type=source_type,
        content_hash=content_hash,
        source_hash=source_hash,
    )


def fingerprint(item: NormalizedItem) -> str:
    """
    Retourneert de deduplicatie-sleutel van een NormalizedItem.

    De fingerprint is gelijk aan content_hash: twee items met dezelfde
    titel+tekst krijgen altijd dezelfde fingerprint, ongeacht bron of datum.

    Args:
        item: een NormalizedItem.

    Returns:
        str: hex SHA-256 digest (64 tekens).
    """
    return item.content_hash


# ---------------------------------------------------------------------------
# CLI smoke-test (optioneel, voor handmatige verificatie)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    try:
        sample = {
            "title": "Testbericht van RSS feed",
            "text": "Dit is de inhoud van het artikel.",
            "url": "https://example.com/artikel/1",
            "published_at": "2026-04-07T10:00:00",
            "tags": ["tech", "AI"],
            "source_type": "rss",
        }
        item = normalize(sample)
        print(f"[SUCCESS] NormalizedItem aangemaakt")
        print(f"  id           : {item.id}")
        print(f"  title        : {item.title}")
        print(f"  content_hash : {item.content_hash}")
        print(f"  source_type  : {item.source_type}")
        print(f"  published_at : {item.published_at}")
        print(f"  fingerprint  : {fingerprint(item)}")
    except Exception as e:
        print(f"[ERROR] Onverwacht: {e}", file=sys.stderr)
        sys.exit(1)
