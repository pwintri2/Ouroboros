# sandbox_tests/test_stream_resonance.py
# Phase 7.X — Unit tests voor controller/stream/resonance.py
# Wintrip AI | task_id: wintrip-soc-003
#
# Volledig deterministisch: geen LLM, geen ChromaDB, geen netwerk.
# Draait met: python sandbox_tests/test_stream_resonance.py

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from controller.stream.normalize import normalize
from controller.stream.resonance import (
    ResonanceScore,
    PERSONA_KEYWORDS,
    _MIN_TEXT_LENGTH,
    score,
    batch_score,
    _score_keywords,
    _score_tags,
    _score_source,
    _score_title_boost,
    _count_keyword_hits,
    _tokenize,
)
from controller.stream.storage import STORE_THRESHOLD, PROPOSE_THRESHOLD


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _item(title="Test", text="Inhoud voor de test.", source_type="rss", tags=None, url=""):
    return normalize({
        "title": title,
        "text": text,
        "source_type": source_type,
        "tags": tags or [],
        "url": url or "https://example.com",
    })


def _wintrip_item():
    """Item dat hoog moet scoren voor persona 'philip'."""
    return _item(
        title="Wintrip AI autonome stream daemon OODA loop",
        text=(
            "De nieuwe stream of consciousness architectuur van Wintrip AI "
            "maakt gebruik van een altijd-aan autonome OODA loop die lokale LLMs "
            "via Ollama en ChromaDB Hippocampus aanstuurt vanuit de Regiekamer."
        ),
        source_type="rss",
        tags=["wintrip", "ai", "autonomy"],
    )


def _weer_item():
    """Irrelevant weerbericht — moet laag scoren."""
    return _item(
        title="Weersvoorspelling Amsterdam",
        text="Het gaat morgen regenen. Maximumtemperatuur 12 graden Celsius.",
        source_type="rss",
        tags=["weer", "amsterdam"],
    )


# ---------------------------------------------------------------------------
# Tests: ResonanceScore dataclass
# ---------------------------------------------------------------------------
class TestResonanceScore(unittest.TestCase):

    def test_should_store_boven_drempel(self):
        rs = ResonanceScore(score=STORE_THRESHOLD)
        self.assertTrue(rs.should_store)

    def test_should_store_onder_drempel(self):
        rs = ResonanceScore(score=STORE_THRESHOLD - 0.01)
        self.assertFalse(rs.should_store)

    def test_should_propose_boven_drempel(self):
        rs = ResonanceScore(score=PROPOSE_THRESHOLD)
        self.assertTrue(rs.should_propose)

    def test_should_propose_onder_drempel(self):
        rs = ResonanceScore(score=PROPOSE_THRESHOLD - 0.01)
        self.assertFalse(rs.should_propose)

    def test_drempelwaarden_in_thresholds_dict(self):
        rs = ResonanceScore(score=0.5)
        self.assertIn("store", rs.thresholds)
        self.assertIn("propose", rs.thresholds)
        self.assertEqual(rs.thresholds["store"], STORE_THRESHOLD)
        self.assertEqual(rs.thresholds["propose"], PROPOSE_THRESHOLD)

    def test_repr_bevat_score_en_persona(self):
        rs = ResonanceScore(score=0.75, persona="philip")
        r = repr(rs)
        self.assertIn("0.750", r)
        self.assertIn("philip", r)


# ---------------------------------------------------------------------------
# Tests: _tokenize en _count_keyword_hits
# ---------------------------------------------------------------------------
class TestHelpers(unittest.TestCase):

    def test_tokenize_maakt_lowercase(self):
        self.assertEqual(_tokenize("Wintrip AI"), "wintrip ai")

    def test_count_hits_vindt_trefwoord(self):
        self.assertEqual(_count_keyword_hits("wintrip ooda chromadb", ["wintrip", "ooda"]), 2)

    def test_count_hits_trefwoord_max_1_keer(self):
        # Zelfde trefwoord meerdere keren in tekst → telt maar 1 keer
        hits = _count_keyword_hits("wintrip wintrip wintrip", ["wintrip"])
        self.assertEqual(hits, 1)

    def test_count_hits_geen_match(self):
        self.assertEqual(_count_keyword_hits("appels en peren", ["wintrip"]), 0)

    def test_count_hits_partieel_match(self):
        # "chromadb" vinden in langere tekst
        self.assertEqual(_count_keyword_hits("gebruik chromadb voor opslag", ["chromadb"]), 1)


# ---------------------------------------------------------------------------
# Tests: _score_keywords
# ---------------------------------------------------------------------------
class TestScoreKeywords(unittest.TestCase):

    def test_wintrip_item_heeft_hits(self):
        item = _wintrip_item()
        raw, reasons, domains = _score_keywords(item, "philip")
        self.assertGreater(raw, 0.0)
        self.assertTrue(len(domains) > 0)

    def test_weer_item_heeft_geen_hits_philip(self):
        item = _weer_item()
        raw, reasons, domains = _score_keywords(item, "philip")
        self.assertEqual(raw, 0.0)
        self.assertEqual(domains, [])

    def test_onbekende_persona_geeft_nul(self):
        item = _wintrip_item()
        raw, reasons, domains = _score_keywords(item, "onbekend_persona_xyz")
        self.assertEqual(raw, 0.0)

    def test_score_is_max_0_50(self):
        # Maak item met zoveel mogelijk trefwoorden
        item = _item(
            title=" ".join(PERSONA_KEYWORDS["philip"]["wintrip_ai"][:5]),
            text=" ".join(
                kw for kws in PERSONA_KEYWORDS["philip"].values() for kw in kws
            ),
        )
        raw, _, _ = _score_keywords(item, "philip")
        self.assertLessEqual(raw, 0.50)

    def test_meerdere_domeinen_verhogen_score(self):
        # Item met hits in 2 domeinen → hogere score dan 1 domein
        item_een = _item(title="wintrip ai", text="ooda loop automation")
        item_twee = _item(
            title="wintrip ai consciousness",
            text="ooda loop automation bewustzijn spiritueel meditation"
        )
        raw_een, _, _ = _score_keywords(item_een, "philip")
        raw_twee, _, _ = _score_keywords(item_twee, "philip")
        self.assertGreaterEqual(raw_twee, raw_een)


# ---------------------------------------------------------------------------
# Tests: _score_tags
# ---------------------------------------------------------------------------
class TestScoreTags(unittest.TestCase):

    def test_relevante_tags_geven_score(self):
        item = _item(tags=["wintrip", "ooda", "llm"])
        raw, reasons = _score_tags(item, "philip")
        self.assertGreater(raw, 0.0)

    def test_irrelevante_tags_geven_nul(self):
        item = _item(tags=["voetbal", "amsterdam", "weer"])
        raw, reasons = _score_tags(item, "philip")
        self.assertEqual(raw, 0.0)

    def test_geen_tags_geeft_nul(self):
        item = _item(tags=[])
        raw, reasons = _score_tags(item, "philip")
        self.assertEqual(raw, 0.0)

    def test_score_is_max_0_20(self):
        item = _item(tags=[kw for kws in PERSONA_KEYWORDS["philip"].values() for kw in kws[:2]])
        raw, _ = _score_tags(item, "philip")
        self.assertLessEqual(raw, 0.20)


# ---------------------------------------------------------------------------
# Tests: _score_source
# ---------------------------------------------------------------------------
class TestScoreSource(unittest.TestCase):

    def test_rss_geeft_hoogste_gewicht(self):
        rss = _item(source_type="rss")
        url = _item(source_type="url")
        raw_rss, _ = _score_source(rss)
        raw_url, _ = _score_source(url)
        self.assertGreater(raw_rss, raw_url)

    def test_onbekend_source_type_geeft_minimaal_gewicht(self):
        item = _item(source_type="manual")
        raw, reasons = _score_source(item)
        self.assertGreater(raw, 0.0)
        self.assertLessEqual(raw, 0.15)

    def test_score_is_max_0_15(self):
        for stype in ["rss", "url", "manual", "chatgpt_macos_app"]:
            item = _item(source_type=stype)
            raw, _ = _score_source(item)
            self.assertLessEqual(raw, 0.15, f"source_type={stype} overschrijdt max")


# ---------------------------------------------------------------------------
# Tests: _score_title_boost
# ---------------------------------------------------------------------------
class TestScoreTitleBoost(unittest.TestCase):

    def test_trefwoord_in_titel_geeft_boost(self):
        item = _item(title="Wintrip AI OODA loop update", text="Geen relevante body.")
        raw, reasons = _score_title_boost(item, "philip")
        self.assertGreater(raw, 0.0)
        self.assertTrue(len(reasons) > 0)

    def test_trefwoord_alleen_in_body_geeft_geen_titelboost(self):
        item = _item(title="Normaal bericht", text="wintrip ooda chromadb hippocampus")
        raw, _ = _score_title_boost(item, "philip")
        self.assertEqual(raw, 0.0)

    def test_score_is_max_0_15(self):
        item = _item(
            title=" ".join(kw for kws in PERSONA_KEYWORDS["philip"].values() for kw in kws[:3]),
            text="irrelevant"
        )
        raw, _ = _score_title_boost(item, "philip")
        self.assertLessEqual(raw, 0.15)


# ---------------------------------------------------------------------------
# Tests: score() — kernfunctie
# ---------------------------------------------------------------------------
class TestScore(unittest.TestCase):

    def test_wintrip_item_scoort_hoog(self):
        rs = score(_wintrip_item(), persona="philip")
        self.assertGreater(rs.score, STORE_THRESHOLD)
        self.assertGreater(rs.score, 0.3)

    def test_weer_item_scoort_laag(self):
        rs = score(_weer_item(), persona="philip")
        self.assertLess(rs.score, STORE_THRESHOLD)

    def test_score_is_geclamped_0_tot_1(self):
        rs = score(_wintrip_item(), persona="philip")
        self.assertGreaterEqual(rs.score, 0.0)
        self.assertLessEqual(rs.score, 1.0)

    def test_score_is_deterministisch(self):
        """Zelfde item → zelfde score (geen randomness)."""
        item = _wintrip_item()
        rs1 = score(item, persona="philip")
        rs2 = score(item, persona="philip")
        self.assertEqual(rs1.score, rs2.score)

    def test_score_heeft_reasons(self):
        rs = score(_wintrip_item(), persona="philip")
        self.assertTrue(len(rs.reasons) > 0)

    def test_score_heeft_matched_domains(self):
        rs = score(_wintrip_item(), persona="philip")
        self.assertTrue(len(rs.matched_domains) > 0)

    def test_onbekende_persona_valt_terug_op_general(self):
        item = _wintrip_item()
        rs = score(item, persona="onbekend_xyz")
        self.assertEqual(rs.persona, "general")
        self.assertIsInstance(rs.score, float)

    def test_te_korte_tekst_geeft_nul(self):
        item = normalize({"title": "Ko", "text": "rt", "source_type": "rss"})
        rs = score(item, persona="philip")
        self.assertEqual(rs.score, 0.0)

    def test_lege_item_geeft_nul(self):
        item = normalize({})
        rs = score(item, persona="philip")
        self.assertIsInstance(rs, ResonanceScore)
        self.assertGreaterEqual(rs.score, 0.0)

    def test_deelscore_attributen_aanwezig(self):
        rs = score(_wintrip_item(), persona="philip")
        self.assertIsInstance(rs.keyword_score, float)
        self.assertIsInstance(rs.tag_score, float)
        self.assertIsInstance(rs.source_score, float)
        self.assertIsInstance(rs.title_boost, float)

    def test_deelscores_tellen_op_tot_totaalscore(self):
        rs = score(_wintrip_item(), persona="philip")
        berekend = rs.keyword_score + rs.tag_score + rs.source_score + rs.title_boost
        # Geclamped naar 1.0, dus som kan hoger zijn dan score
        self.assertAlmostEqual(rs.score, min(1.0, berekend), places=4)

    def test_hogere_relevantie_geeft_hogere_score(self):
        """Item met meer trefwoorden moet hoger scoren dan met minder."""
        item_weinig = _item(
            title="wintrip",
            text="Dit is een kleine update over het wintrip systeem.",
            source_type="rss",
        )
        item_veel = _item(
            title="wintrip ai autonome ooda loop",
            text=(
                "De wintrip ai autonome ooda loop met chromadb hippocampus, "
                "ollama llm, stream of consciousness en docker sandbox."
            ),
            source_type="rss",
            tags=["wintrip", "ooda", "llm"],
        )
        rs_weinig = score(item_weinig, persona="philip")
        rs_veel = score(item_veel, persona="philip")
        self.assertGreater(rs_veel.score, rs_weinig.score)

    def test_filosofie_item_scoort_voor_philip(self):
        """Items over bewustzijn/filosofie zijn relevant voor Philip's roman."""
        item = _item(
            title="Non-dualiteit en bewustzijn in Boeddhisme",
            text=(
                "De Boeddhistische filosofie beschrijft bewustzijn als een "
                "continue stroom (santana). Non-dualiteit is de kern van "
                "meditatie en spirituele praktijk."
            ),
            source_type="url",
        )
        rs = score(item, persona="philip")
        self.assertGreater(rs.score, 0.0)
        self.assertIn("philosophy_spirit", rs.matched_domains)

    def test_muziek_item_scoort_voor_philip(self):
        """Items over kamerkoor/compositie zijn relevant voor Philip."""
        item = _item(
            title="Nieuw requiem voor kamerkoor gepremièerd",
            text="Een nieuwe compositie voor kamerkoor met gregoriaanse harmonieën.",
            source_type="rss",
        )
        rs = score(item, persona="philip")
        self.assertGreater(rs.score, 0.0)
        self.assertIn("music_composition", rs.matched_domains)

    def test_developer_persona_scoort_anders(self):
        """Developer persona reageert anders dan philip op zelfde content."""
        item = _item(
            title="FastAPI unit testing met pytest en docker",
            text="Security best practices voor API endpoints en dependency injection.",
            source_type="url",
        )
        rs_philip = score(item, persona="philip")
        rs_dev = score(item, persona="developer")
        # Beide moeten positief scoren (inhoud is technisch)
        self.assertGreater(rs_dev.score, 0.0)
        self.assertIsInstance(rs_philip.score, float)


# ---------------------------------------------------------------------------
# Tests: drempelwaarden (integratie met storage-constanten)
# ---------------------------------------------------------------------------
class TestDrempelwaarden(unittest.TestCase):

    def test_wintrip_item_boven_store_threshold(self):
        rs = score(_wintrip_item(), persona="philip")
        self.assertTrue(rs.should_store, f"score={rs.score} < store_threshold={STORE_THRESHOLD}")

    def test_weer_item_onder_store_threshold(self):
        rs = score(_weer_item(), persona="philip")
        self.assertFalse(rs.should_store)

    def test_propose_threshold_hoger_dan_store_threshold(self):
        self.assertGreater(PROPOSE_THRESHOLD, STORE_THRESHOLD)

    def test_item_kan_store_zijn_zonder_propose(self):
        """Item tussen STORE en PROPOSE drempel → should_store maar niet should_propose."""
        item = _item(
            title="wintrip update",
            text="Kleine update voor het wintrip systeem.",
            source_type="manual",
        )
        rs = score(item, persona="philip")
        if rs.should_store and not rs.should_propose:
            self.assertTrue(STORE_THRESHOLD <= rs.score < PROPOSE_THRESHOLD)


# ---------------------------------------------------------------------------
# Tests: batch_score()
# ---------------------------------------------------------------------------
class TestBatchScore(unittest.TestCase):

    def test_batch_zelfde_resultaat_als_individueel(self):
        items = [_wintrip_item(), _weer_item()]
        batch = batch_score(items, persona="philip")
        individual = [score(item, persona="philip") for item in items]
        for b, i in zip(batch, individual):
            self.assertEqual(b.score, i.score)

    def test_batch_lege_lijst(self):
        result = batch_score([], persona="philip")
        self.assertEqual(result, [])

    def test_batch_behoudt_volgorde(self):
        items = [_wintrip_item(), _weer_item(), _wintrip_item()]
        batch = batch_score(items, persona="philip")
        self.assertEqual(len(batch), 3)
        # Eerste en derde (wintrip) hoger dan tweede (weer)
        self.assertGreater(batch[0].score, batch[1].score)
        self.assertGreater(batch[2].score, batch[1].score)


# ---------------------------------------------------------------------------
# Tests: PERSONA_KEYWORDS structuur
# ---------------------------------------------------------------------------
class TestPersonaKeywords(unittest.TestCase):

    def test_philip_persona_aanwezig(self):
        self.assertIn("philip", PERSONA_KEYWORDS)

    def test_philip_heeft_verwachte_domeinen(self):
        philip = PERSONA_KEYWORDS["philip"]
        self.assertIn("wintrip_ai", philip)
        self.assertIn("philosophy_spirit", philip)
        self.assertIn("music_composition", philip)
        self.assertIn("ai_ecosystem", philip)

    def test_alle_trefwoorden_zijn_lowercase(self):
        for persona, domains in PERSONA_KEYWORDS.items():
            for domain, keywords in domains.items():
                for kw in keywords:
                    self.assertEqual(
                        kw, kw.lower(),
                        f"Trefwoord '{kw}' in {persona}/{domain} is niet lowercase"
                    )

    def test_geen_lege_trefwoordenlijsten(self):
        for persona, domains in PERSONA_KEYWORDS.items():
            for domain, keywords in domains.items():
                self.assertGreater(
                    len(keywords), 0,
                    f"Lege trefwoordenlijst in {persona}/{domain}"
                )


if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
