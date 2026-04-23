# controller/stream/sources/rss.py
# Phase 7.X — Stream of Consciousness: RSS/Atom Feed Bron
# Wintrip AI | task_id: wintrip-soc-006
#
# Verantwoordelijkheid:
#   - Haalt een RSS of Atom feed op via HTTP(S).
#   - Parseert de XML en retourneert een list[dict] in het normalize()-contract.
#   - Behandelt ALLE web-content als UNTRUSTED (OWASP LLM01).
#   - Stdlib-only: urllib.request + xml.etree.ElementTree + html.parser.
#   - Nooit crashen: netwerk- en parsefouten geven lege lijst terug.
#   - Injecteerbare fetch-functie voor testbaarheid (geen netwerk in tests nodig).
#
# Contract (output per item):
#   {
#     "title"       : str,
#     "text"        : str,   (description of summary)
#     "url"         : str,   (link)
#     "published_at": str,   (pubDate of updated)
#     "tags"        : list[str],
#     "source_type" : "rss",
#   }
#
# Gebruik in daemon:
#   from controller.stream.sources.rss import RSSSource
#   bron = RSSSource("https://feeds.example.com/feed.xml")
#   daemon.add_source(bron)   # bron is callable

from __future__ import annotations

import html
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from typing import Callable, Dict, List, Optional

# ---------------------------------------------------------------------------
# Constanten
# ---------------------------------------------------------------------------
_DEFAULT_TIMEOUT: int = 10          # seconden
_MAX_ITEMS: int = 100               # max items per feed-aanroep
_MAX_TEXT_LEN: int = 4096           # max tekens voor description-veld
_MAX_TITLE_LEN: int = 512
_MAX_URL_LEN: int = 2048
_MAX_TAG_LEN: int = 64
_MAX_TAGS: int = 10

# Atom namespace
_ATOM_NS = "http://www.w3.org/2005/Atom"

# User-Agent: identificeerbaar maar niet misleidend
_USER_AGENT = "WintripAI-StreamDaemon/1.0 (Phase 7.X; RSS Ingest)"

# ---------------------------------------------------------------------------
# Interne sanitisatie-helpers
# ---------------------------------------------------------------------------

_TAG_RE = re.compile(r"<[^>]+>")          # HTML-tags verwijderen
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")  # control chars


def _strip_html(text: str) -> str:
    """Verwijdert HTML-tags en decodeert HTML entities. UNTRUSTED content."""
    if not text:
        return ""
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = _CTRL_RE.sub("", text)
    return " ".join(text.split())  # normaliseer whitespace


def _safe(value: Optional[str], max_len: int) -> str:
    """Sanitiseert en trunkert een veldwaarde."""
    if not value:
        return ""
    return _strip_html(str(value))[:max_len]


def _safe_tags(raw: List[str]) -> List[str]:
    """Sanitiseert een lijst van tags."""
    seen = set()
    result = []
    for tag in raw:
        clean = _safe(tag, _MAX_TAG_LEN).lower()
        if clean and clean not in seen:
            seen.add(clean)
            result.append(clean)
        if len(result) >= _MAX_TAGS:
            break
    return result


# ---------------------------------------------------------------------------
# XML-helpers
# ---------------------------------------------------------------------------

def _text(element: Optional[ET.Element]) -> str:
    """Haalt tekst op uit een XML-element of retourneert leeg string."""
    if element is None:
        return ""
    return (element.text or "").strip()


def _find(parent: ET.Element, *tags: str) -> Optional[ET.Element]:
    """Zoekt een sub-element via meerdere mogelijke tagnamen (RSS + Atom compat)."""
    for tag in tags:
        el = parent.find(tag)
        if el is not None:
            return el
    return None


def _find_ns(parent: ET.Element, local: str, ns: str = _ATOM_NS) -> Optional[ET.Element]:
    """Zoekt een sub-element met Atom-namespace."""
    return parent.find(f"{{{ns}}}{local}")


# ---------------------------------------------------------------------------
# RSS/Atom parsers
# ---------------------------------------------------------------------------

def _parse_rss_item(item: ET.Element) -> Dict[str, object]:
    """Parseert één <item> uit een RSS 2.0 feed."""
    title = _safe(_text(_find(item, "title")), _MAX_TITLE_LEN) or "[geen titel]"

    # Tekst: description heeft voorkeur, anders geen tekst
    desc = _text(_find(item, "description", "content:encoded", "summary"))
    text = _safe(desc, _MAX_TEXT_LEN)

    # URL
    link_el = _find(item, "link")
    link = _safe(_text(link_el), _MAX_URL_LEN)
    if not link:
        # Sommige feeds stoppen de URL als tekst-node NA <link/>
        guid = _find(item, "guid")
        if guid is not None and (guid.get("isPermaLink", "true") == "true"):
            link = _safe(_text(guid), _MAX_URL_LEN)

    # Datum
    pub = _text(_find(item, "pubDate", "dc:date", "published"))

    # Tags (category)
    tags = [_text(c) for c in item.findall("category") if _text(c)]

    return {
        "title": title,
        "text": text,
        "url": link,
        "published_at": pub,
        "tags": _safe_tags(tags),
        "source_type": "rss",
    }


def _parse_atom_entry(entry: ET.Element) -> Dict[str, object]:
    """Parseert één <entry> uit een Atom 1.0 feed."""
    ns = _ATOM_NS

    title_el = _find_ns(entry, "title")
    title = _safe(_text(title_el), _MAX_TITLE_LEN) or "[geen titel]"

    # Tekst: summary > content
    # Let op: ET.Element is falsy als het geen child-elementen heeft (ook al heeft
    # het wél tekst). Gebruik dus expliciete None-check, niet 'or'.
    summary = _find_ns(entry, "summary")
    if summary is None:
        summary = _find_ns(entry, "content")
    text = _safe(_text(summary), _MAX_TEXT_LEN)

    # URL: <link href="..."> of <link>tekst</link>
    link = ""
    link_el = _find_ns(entry, "link")
    if link_el is not None:
        link = _safe(link_el.get("href", "") or _text(link_el), _MAX_URL_LEN)

    # Datum
    pub = _text(_find_ns(entry, "updated") or _find_ns(entry, "published"))

    # Tags
    tags = []
    for cat in entry.findall(f"{{{ns}}}category"):
        term = cat.get("term", "") or cat.get("label", "")
        if term:
            tags.append(term)

    return {
        "title": title,
        "text": text,
        "url": link,
        "published_at": pub,
        "tags": _safe_tags(tags),
        "source_type": "rss",
    }


def _parse_feed(xml_bytes: bytes) -> List[Dict[str, object]]:
    """
    Parseert een RSS 2.0 of Atom 1.0 feed uit bytes.
    Retourneert lege lijst bij parse-fouten (UNTRUSTED content).
    """
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        print(f"[RSSSource] XML parse-fout: {e}", file=sys.stderr)
        return []

    items: List[Dict[str, object]] = []

    # RSS 2.0: <rss><channel><item>...
    tag = root.tag.lower().split("}")[-1]  # strip namespace
    if tag == "rss":
        channel = root.find("channel")
        if channel is not None:
            for item in channel.findall("item"):
                items.append(_parse_rss_item(item))
                if len(items) >= _MAX_ITEMS:
                    break
        return items

    # Atom 1.0: <feed xmlns="..."><entry>...
    if tag == "feed" or root.tag == f"{{{_ATOM_NS}}}feed":
        ns = _ATOM_NS
        for entry in root.findall(f"{{{ns}}}entry"):
            items.append(_parse_atom_entry(entry))
            if len(items) >= _MAX_ITEMS:
                break
        return items

    print(f"[RSSSource] Onbekend feed-formaat: root tag='{root.tag}'", file=sys.stderr)
    return []


# ---------------------------------------------------------------------------
# Fetch-functie (injectable voor tests)
# ---------------------------------------------------------------------------

def _default_fetch(url: str, timeout: int) -> bytes:
    """
    Haalt de URL op via urllib. Retourneert bytes of gooit een exception.
    Wordt vervangen door een mock in tests.
    """
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


# ---------------------------------------------------------------------------
# RSSSource — de publieke klasse
# ---------------------------------------------------------------------------

class RSSSource:
    """
    RSS/Atom feed bron voor de StreamDaemon.

    Callable interface: `source()` retourneert list[dict] klaar voor normalize().

    Veiligheidsgaranties:
    - Alle HTML-content wordt gestript en gesanitiseerd (OWASP LLM01).
    - Netwerk- en parsefouten geven altijd een lege lijst terug.
    - Maximaal _MAX_ITEMS (100) items per aanroep.
    - User-Agent identificeert Wintrip maar geeft geen gevoelige info vrij.

    Args:
        url         : de RSS/Atom feed URL.
        timeout     : HTTP timeout in seconden (default 10).
        fetch_fn    : optionele injecteerbare fetch-functie (voor tests).
                      Signatuur: (url: str, timeout: int) -> bytes
    """

    def __init__(
        self,
        url: str,
        timeout: int = _DEFAULT_TIMEOUT,
        fetch_fn: Optional[Callable[[str, int], bytes]] = None,
    ):
        if not url or not isinstance(url, str):
            raise ValueError("RSSSource vereist een niet-lege URL string.")
        if not (url.startswith("http://") or url.startswith("https://")):
            raise ValueError(
                f"RSSSource URL moet beginnen met http:// of https://. Ontvangen: {url!r}"
            )
        if timeout <= 0:
            raise ValueError("timeout moet groter dan 0 zijn.")

        self._url = url
        self._timeout = timeout
        self._fetch_fn = fetch_fn or _default_fetch

    def __call__(self) -> List[Dict[str, object]]:
        """
        Haalt de feed op en retourneert geparseerde items.
        Nooit een exception gooien — retourneert lege lijst bij elke fout.
        """
        try:
            raw_bytes = self._fetch_fn(self._url, self._timeout)
        except urllib.error.URLError as exc:
            print(f"[RSSSource] Netwerk-fout ({self._url}): {exc}", file=sys.stderr)
            return []
        except TimeoutError:
            print(f"[RSSSource] Timeout ({self._url})", file=sys.stderr)
            return []
        except Exception as exc:
            print(f"[RSSSource] Onverwachte fetch-fout ({self._url}): {exc}", file=sys.stderr)
            return []

        if not raw_bytes:
            print(f"[RSSSource] Lege response ({self._url})", file=sys.stderr)
            return []

        return _parse_feed(raw_bytes)

    def __repr__(self) -> str:
        return f"RSSSource(url={self._url!r}, timeout={self._timeout})"
