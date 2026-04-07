# sandbox_tests/test_stream_sources_rss.py
# Phase 7.X — Unit tests voor controller/stream/sources/rss.py
# Wintrip AI | task_id: wintrip-soc-006
#
# Geen echt netwerk: alle HTTP-calls worden onderschept via de injecteerbare
# fetch_fn parameter van RSSSource. 100% deterministisch.
# Draait met: python sandbox_tests/test_stream_sources_rss.py

import sys
import os
import unittest
import urllib.error

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from controller.stream.sources.rss import (
    RSSSource,
    _parse_feed,
    _strip_html,
    _safe,
    _safe_tags,
    _MAX_ITEMS,
)


# ---------------------------------------------------------------------------
# Test-fixtures: gesynthetiseerde RSS/Atom XML feeds
# ---------------------------------------------------------------------------

RSS_FEED_GELDIG = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Wintrip AI Nieuws</title>
    <link>https://example.com</link>
    <description>Updates over Wintrip AI</description>
    <item>
      <title>Wintrip AI Phase 7.X gelanceerd</title>
      <link>https://example.com/phase-7</link>
      <description>De stream of consciousness architectuur is nu live.</description>
      <pubDate>Tue, 07 Apr 2026 10:00:00 +0000</pubDate>
      <category>AI</category>
      <category>Wintrip</category>
    </item>
    <item>
      <title>Nieuwe resonantiefilter gebouwd</title>
      <link>https://example.com/resonance</link>
      <description>De resonantiefilter blokkeert irrelevante ruis effectief.</description>
      <pubDate>Mon, 06 Apr 2026 09:00:00 +0000</pubDate>
      <category>backend</category>
    </item>
  </channel>
</rss>
"""

RSS_FEED_EEN_ITEM = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Enkel item</title>
      <link>https://example.com/enkel</link>
      <description>Alleen dit item bestaat.</description>
    </item>
  </channel>
</rss>
"""

ATOM_FEED_GELDIG = b"""<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Wintrip Atom Feed</title>
  <entry>
    <title>Atom entry: OODA loop update</title>
    <link href="https://atom.example.com/ooda"/>
    <summary>De OODA loop is bijgewerkt met resonantie filteren.</summary>
    <updated>2026-04-07T10:00:00Z</updated>
    <category term="ai"/>
    <category term="ooda"/>
  </entry>
  <entry>
    <title>Tweede Atom entry</title>
    <link href="https://atom.example.com/tweede"/>
    <content>Meer nieuws over de autonome architectuur.</content>
    <updated>2026-04-06T09:00:00Z</updated>
  </entry>
</feed>
"""

RSS_FEED_HTML_IN_BESCHRIJVING = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <item>
      <title>Item met &lt;b&gt;HTML&lt;/b&gt; in titel</title>
      <link>https://example.com/html</link>
      <description>&lt;p&gt;Inhoud met &lt;a href="#"&gt;links&lt;/a&gt; en &amp;amp; entiteiten.&lt;/p&gt;</description>
    </item>
  </channel>
</rss>
"""

# Null-bytes worden door de XML parser afgehandeld vóór onze sanitizer;
# we testen dit via _strip_html direct (zie TestStripHtml).
RSS_FEED_CONTROL_CHARS = (
    b"<?xml version='1.0' encoding='UTF-8'?>"
    b"<rss version='2.0'><channel><item>"
    b"<title>Kwaadaardig IGNORE INSTRUCTIONS</title>"
    b"<link>https://example.com/kwaad</link>"
    b"<description>Inhoud met rare tekens.</description>"
    b"</item></channel></rss>"
)

RSS_FEED_LEEG_KANAAL = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Leeg kanaal</title>
  </channel>
</rss>
"""

XML_KAPOT = b"<<dit is geen geldige xml>>>"

ONBEKEND_FORMAT = b"""<?xml version="1.0"?>
<onbekend_root><data>hallo</data></onbekend_root>
"""

def _veel_items_feed(n: int) -> bytes:
    """Genereert een RSS feed met n items."""
    items = "".join(
        f"<item><title>Item {i}</title><link>https://example.com/{i}</link>"
        f"<description>Beschrijving {i}</description></item>"
        for i in range(n)
    )
    return (
        b"<?xml version='1.0'?><rss version='2.0'><channel>" +
        items.encode() +
        b"</channel></rss>"
    )


# ---------------------------------------------------------------------------
# Mock fetch-functies
# ---------------------------------------------------------------------------

def _mock_fetch(content: bytes):
    """Retourneert een fetch-functie die altijd `content` retourneert."""
    def _fetch(url, timeout):
        return content
    return _fetch


def _mock_fetch_fout(exc_type, *args):
    """Retourneert een fetch-functie die een exception gooit."""
    def _fetch(url, timeout):
        raise exc_type(*args)
    return _fetch


# ---------------------------------------------------------------------------
# Tests: _strip_html
# ---------------------------------------------------------------------------
class TestStripHtml(unittest.TestCase):

    def test_verwijdert_html_tags(self):
        result = _strip_html("<p>Hallo <b>wereld</b></p>")
        self.assertNotIn("<p>", result)
        self.assertNotIn("<b>", result)
        self.assertIn("Hallo", result)
        self.assertIn("wereld", result)

    def test_decodeert_html_entities(self):
        result = _strip_html("&lt;script&gt; &amp; &quot;test&quot;")
        self.assertIn("<script>", result)
        self.assertIn("&", result)

    def test_verwijdert_control_chars(self):
        result = _strip_html("hallo\x00\x01\x02wereld")
        self.assertNotIn("\x00", result)
        self.assertNotIn("\x01", result)
        self.assertIn("hallo", result)

    def test_normaliseert_whitespace(self):
        result = _strip_html("veel   spaties\n\nen tabs\t\there")
        self.assertNotIn("   ", result)

    def test_lege_string(self):
        self.assertEqual(_strip_html(""), "")

    def test_none(self):
        self.assertEqual(_strip_html(None), "")


# ---------------------------------------------------------------------------
# Tests: _safe_tags
# ---------------------------------------------------------------------------
class TestSafeTags(unittest.TestCase):

    def test_tags_worden_lowercase(self):
        result = _safe_tags(["AI", "Python", "RSS"])
        self.assertIn("ai", result)
        self.assertIn("python", result)

    def test_duplicaten_verwijderd(self):
        result = _safe_tags(["ai", "AI", "Ai"])
        self.assertEqual(result.count("ai"), 1)

    def test_max_10_tags(self):
        result = _safe_tags([f"tag{i}" for i in range(20)])
        self.assertLessEqual(len(result), 10)

    def test_lege_lijst(self):
        self.assertEqual(_safe_tags([]), [])


# ---------------------------------------------------------------------------
# Tests: _parse_feed — RSS 2.0
# ---------------------------------------------------------------------------
class TestParseFeedRSS(unittest.TestCase):

    def test_parst_twee_items(self):
        items = _parse_feed(RSS_FEED_GELDIG)
        self.assertEqual(len(items), 2)

    def test_item_heeft_title(self):
        items = _parse_feed(RSS_FEED_GELDIG)
        self.assertEqual(items[0]["title"], "Wintrip AI Phase 7.X gelanceerd")

    def test_item_heeft_url(self):
        items = _parse_feed(RSS_FEED_GELDIG)
        self.assertEqual(items[0]["url"], "https://example.com/phase-7")

    def test_item_heeft_text(self):
        items = _parse_feed(RSS_FEED_GELDIG)
        self.assertIn("stream of consciousness", items[0]["text"])

    def test_item_heeft_source_type_rss(self):
        items = _parse_feed(RSS_FEED_GELDIG)
        self.assertEqual(items[0]["source_type"], "rss")

    def test_item_heeft_published_at(self):
        items = _parse_feed(RSS_FEED_GELDIG)
        self.assertIn("2026", items[0]["published_at"])

    def test_item_heeft_tags(self):
        items = _parse_feed(RSS_FEED_GELDIG)
        tags = items[0]["tags"]
        self.assertIsInstance(tags, list)
        self.assertIn("ai", tags)

    def test_leeg_kanaal_geeft_lege_lijst(self):
        items = _parse_feed(RSS_FEED_LEEG_KANAAL)
        self.assertEqual(items, [])

    def test_kapotte_xml_geeft_lege_lijst(self):
        items = _parse_feed(XML_KAPOT)
        self.assertEqual(items, [])

    def test_onbekend_format_geeft_lege_lijst(self):
        items = _parse_feed(ONBEKEND_FORMAT)
        self.assertEqual(items, [])

    def test_max_items_wordt_gerespecteerd(self):
        feed = _veel_items_feed(_MAX_ITEMS + 20)
        items = _parse_feed(feed)
        self.assertLessEqual(len(items), _MAX_ITEMS)

    def test_html_wordt_gestript_uit_titel(self):
        items = _parse_feed(RSS_FEED_HTML_IN_BESCHRIJVING)
        self.assertNotIn("<b>", items[0]["title"])
        self.assertNotIn("<a", items[0]["text"])

    def test_control_chars_feed_wordt_geparseerd(self):
        """Feed met control chars in content wordt verwerkt zonder crash."""
        items = _parse_feed(RSS_FEED_CONTROL_CHARS)
        # Moet minstens een lege lijst of items geven, nooit een crash
        self.assertIsInstance(items, list)

    def test_enkel_item(self):
        items = _parse_feed(RSS_FEED_EEN_ITEM)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "Enkel item")


# ---------------------------------------------------------------------------
# Tests: _parse_feed — Atom 1.0
# ---------------------------------------------------------------------------
class TestParseFeedAtom(unittest.TestCase):

    def test_parst_twee_entries(self):
        items = _parse_feed(ATOM_FEED_GELDIG)
        self.assertEqual(len(items), 2)

    def test_atom_item_heeft_title(self):
        items = _parse_feed(ATOM_FEED_GELDIG)
        self.assertIn("OODA loop", items[0]["title"])

    def test_atom_item_heeft_url(self):
        items = _parse_feed(ATOM_FEED_GELDIG)
        self.assertEqual(items[0]["url"], "https://atom.example.com/ooda")

    def test_atom_item_heeft_summary(self):
        items = _parse_feed(ATOM_FEED_GELDIG)
        self.assertGreater(len(items[0]["text"]), 0)

    def test_atom_item_heeft_source_type_rss(self):
        items = _parse_feed(ATOM_FEED_GELDIG)
        self.assertEqual(items[0]["source_type"], "rss")

    def test_atom_item_heeft_tags(self):
        items = _parse_feed(ATOM_FEED_GELDIG)
        self.assertIn("ai", items[0]["tags"])
        self.assertIn("ooda", items[0]["tags"])

    def test_atom_content_als_fallback_voor_summary(self):
        items = _parse_feed(ATOM_FEED_GELDIG)
        self.assertGreater(len(items[1]["text"]), 0)


# ---------------------------------------------------------------------------
# Tests: RSSSource initialisatie
# ---------------------------------------------------------------------------
class TestRSSSourceInit(unittest.TestCase):

    def test_geldige_https_url(self):
        src = RSSSource("https://feeds.example.com/rss.xml")
        self.assertIsNotNone(src)

    def test_geldige_http_url(self):
        src = RSSSource("http://feeds.example.com/rss.xml")
        self.assertIsNotNone(src)

    def test_lege_url_gooit_valueerror(self):
        with self.assertRaises(ValueError):
            RSSSource("")

    def test_geen_http_url_gooit_valueerror(self):
        with self.assertRaises(ValueError):
            RSSSource("ftp://example.com/feed")

    def test_relatieve_url_gooit_valueerror(self):
        with self.assertRaises(ValueError):
            RSSSource("/feeds/rss.xml")

    def test_negatieve_timeout_gooit_valueerror(self):
        with self.assertRaises(ValueError):
            RSSSource("https://example.com/feed", timeout=0)

    def test_repr_bevat_url(self):
        src = RSSSource("https://example.com/feed")
        self.assertIn("example.com", repr(src))

    def test_custom_fetch_fn_wordt_gebruikt(self):
        aanroepen = []
        def mock(url, timeout):
            aanroepen.append(url)
            return RSS_FEED_EEN_ITEM
        src = RSSSource("https://example.com/feed", fetch_fn=mock)
        src()
        self.assertEqual(aanroepen, ["https://example.com/feed"])


# ---------------------------------------------------------------------------
# Tests: RSSSource.__call__() — met mock fetch
# ---------------------------------------------------------------------------
class TestRSSSourceCall(unittest.TestCase):

    def test_retourneert_items_bij_geldige_feed(self):
        src = RSSSource("https://x.com/feed", fetch_fn=_mock_fetch(RSS_FEED_GELDIG))
        items = src()
        self.assertEqual(len(items), 2)

    def test_retourneert_lege_lijst_bij_urlerror(self):
        src = RSSSource(
            "https://x.com/feed",
            fetch_fn=_mock_fetch_fout(urllib.error.URLError, "verbinding geweigerd"),
        )
        items = src()
        self.assertEqual(items, [])

    def test_retourneert_lege_lijst_bij_timeout(self):
        src = RSSSource(
            "https://x.com/feed",
            fetch_fn=_mock_fetch_fout(TimeoutError, "timeout"),
        )
        items = src()
        self.assertEqual(items, [])

    def test_retourneert_lege_lijst_bij_willekeurige_exception(self):
        src = RSSSource(
            "https://x.com/feed",
            fetch_fn=_mock_fetch_fout(RuntimeError, "onverwacht"),
        )
        items = src()
        self.assertEqual(items, [])

    def test_retourneert_lege_lijst_bij_lege_response(self):
        src = RSSSource("https://x.com/feed", fetch_fn=_mock_fetch(b""))
        items = src()
        self.assertEqual(items, [])

    def test_retourneert_lege_lijst_bij_kapotte_xml(self):
        src = RSSSource("https://x.com/feed", fetch_fn=_mock_fetch(XML_KAPOT))
        items = src()
        self.assertEqual(items, [])

    def test_atom_feed_wordt_correct_geparseerd(self):
        src = RSSSource("https://x.com/atom", fetch_fn=_mock_fetch(ATOM_FEED_GELDIG))
        items = src()
        self.assertEqual(len(items), 2)

    def test_items_hebben_source_type_rss(self):
        src = RSSSource("https://x.com/feed", fetch_fn=_mock_fetch(RSS_FEED_GELDIG))
        items = src()
        self.assertTrue(all(i["source_type"] == "rss" for i in items))

    def test_items_hebben_altijd_title_veld(self):
        src = RSSSource("https://x.com/feed", fetch_fn=_mock_fetch(RSS_FEED_GELDIG))
        items = src()
        self.assertTrue(all("title" in i for i in items))

    def test_items_hebben_altijd_url_veld(self):
        src = RSSSource("https://x.com/feed", fetch_fn=_mock_fetch(RSS_FEED_GELDIG))
        items = src()
        self.assertTrue(all("url" in i for i in items))

    def test_items_hebben_altijd_tags_als_lijst(self):
        src = RSSSource("https://x.com/feed", fetch_fn=_mock_fetch(RSS_FEED_GELDIG))
        items = src()
        self.assertTrue(all(isinstance(i["tags"], list) for i in items))

    def test_html_injection_geblokkeerd(self):
        """HTML-tags in description mogen niet in text-veld zitten."""
        src = RSSSource(
            "https://x.com/feed",
            fetch_fn=_mock_fetch(RSS_FEED_HTML_IN_BESCHRIJVING)
        )
        items = src()
        self.assertNotIn("<a", items[0]["text"])
        self.assertNotIn("<p>", items[0]["text"])


# ---------------------------------------------------------------------------
# Integratie: RSSSource → normalize()
# ---------------------------------------------------------------------------
class TestRSSNormalizeIntegratie(unittest.TestCase):

    def test_rss_items_passeren_normalize_zonder_fout(self):
        from controller.stream.normalize import normalize
        src = RSSSource("https://x.com/feed", fetch_fn=_mock_fetch(RSS_FEED_GELDIG))
        raw_items = src()
        for raw in raw_items:
            item = normalize(raw)
            self.assertIsNotNone(item.id)
            self.assertIsInstance(item.content_hash, str)

    def test_rss_atom_items_passeren_normalize(self):
        from controller.stream.normalize import normalize
        src = RSSSource("https://x.com/atom", fetch_fn=_mock_fetch(ATOM_FEED_GELDIG))
        for raw in src():
            item = normalize(raw)
            self.assertEqual(item.source_type, "rss")

    def test_kapotte_bron_geeft_nul_normalize_aanroepen(self):
        from controller.stream.normalize import normalize
        src = RSSSource(
            "https://x.com/kapot",
            fetch_fn=_mock_fetch_fout(urllib.error.URLError, "fout"),
        )
        items = src()
        self.assertEqual(len(items), 0)  # geen normalize aanroepen nodig


if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
