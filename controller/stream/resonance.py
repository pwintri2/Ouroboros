# controller/stream/resonance.py
# Phase 7.X — Stream of Consciousness: Resonantie Filter
# Wintrip AI | task_id: wintrip-soc-003
#
# Verantwoordelijkheid:
#   - Beoordeelt een NormalizedItem op culturele/persoonlijke relevantie voor Philip.
#   - Retourneert een ResonanceScore (0.0–1.0) met auditeerbare redenen.
#   - Volledig deterministisch en stdlib-only: geen LLM-call, geen ChromaDB bij scoring.
#   - Persona-systeem: "philip" (persoonlijk), "developer" (technisch), "general" (breed).
#
# Architectuurprincipe (uit Stream of Consciousness PDF):
#   De Resonantie Filter is het cognitieve poortwachter-mechanisme dat voorkomt
#   dat de vector database opbloat met irrelevante ruis. Alleen wat structureel
#   betekenis heeft voor Philip's actieve projecten of filosofische concepten
#   passeert naar de Hippocampus.
#
# Scoreopbouw (additief, geclamped naar 0.0–1.0):
#   1. Trefwoordmatch  (max 0.50) — directe match op Philip's kennisdomeinen
#   2. Tagboost        (max 0.20) — tags uit de NormalizedItem matchen op persona-trefwoorden
#   3. Brongewicht     (max 0.15) — RSS > URL > manual qua betrouwbaarheid voor SoC
#   4. Titelboost      (max 0.15) — trefwoord in titel weegt zwaarder dan in body

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from controller.stream.normalize import NormalizedItem
from controller.stream.storage import STORE_THRESHOLD, PROPOSE_THRESHOLD


# ---------------------------------------------------------------------------
# Persona-kennisdomeinen — uitbreidbaar zonder code-wijziging in storage/daemon
# ---------------------------------------------------------------------------
#
# Elke persona heeft een dict van domeinen → trefwoordenlijst.
# Trefwoorden zijn lowercase. Matching is case-insensitief via .lower().
# Voeg nieuwe trefwoorden toe zonder bestaande logica te wijzigen.

PERSONA_KEYWORDS: Dict[str, Dict[str, List[str]]] = {
    "philip": {
        # Wintrip AI en technologie
        "wintrip_ai": [
            "wintrip", "wintripai", "stream of consciousness", "hippocampus",
            "regiekamer", "vergadertafel", "ooda", "speeltuin", "sandbox",
            "waakbewustzijn", "onderbewustzijn", "chromadb", "ollama",
            "autonome ai", "local llm", "local model",
        ],
        # Filosofie en spiritualiteit (Philip's roman John May)
        "philosophy_spirit": [
            "bewustzijn", "consciousness", "spiritueel", "spiritual", "ziel",
            "akasha", "akashic", "vijnana", "santana", "non-dualiteit",
            "non-dual", "boeddhisme", "buddhism", "meditatie", "meditation",
            "john may", "filosofie", "philosophy", "esoterie", "esoteric",
            "kwantumbewustzijn", "quantum consciousness",
        ],
        # Muziek (kamerkoor, requiem)
        "music_composition": [
            "kamerkoor", "chamber choir", "requiem", "compositie", "composition",
            "muziek", "music", "harmonie", "harmony", "contrapunt", "counterpoint",
            "partituur", "score", "koor", "choir", "gregoriaans", "gregorian",
        ],
        # AI / LLM ecosysteem
        "ai_ecosystem": [
            "llm", "language model", "transformer", "attention", "embedding",
            "vector database", "rag", "retrieval", "agent", "multi-agent",
            "fastapi", "uvicorn", "python", "asyncio", "docker",
            "github actions", "ci/cd", "antigravity", "gemini", "claude",
            "openai", "anthropic", "groq", "phi", "qwen", "llama",
        ],
        # Autonomie en proactiviteit
        "autonomy": [
            "autonoom", "autonomous", "proactief", "proactive", "daemon",
            "achtergrond", "background", "always-on", "altijd aan",
            "zelf-lerend", "self-learning", "zelf-herstellend", "self-healing",
        ],
    },
    "developer": {
        "software_engineering": [
            "python", "fastapi", "docker", "git", "github", "ci/cd",
            "unit test", "pytest", "asyncio", "api", "endpoint", "rest",
            "websocket", "refactor", "architecture", "design pattern",
            "dependency injection", "interface", "contract", "mock",
        ],
        "security": [
            "security", "owasp", "prompt injection", "sanitize", "sanitisation",
            "allowlist", "blocklist", "sandbox", "isolation", "privilege",
            "least privilege", "cve", "vulnerability", "exploit",
        ],
    },
    "general": {
        "tech_news": [
            "artificial intelligence", "machine learning", "deep learning",
            "neural network", "open source", "open-source", "release",
            "update", "version", "launch", "announcement",
        ],
    },
}

# Brongewichten voor source_type
_SOURCE_WEIGHTS: Dict[str, float] = {
    "rss": 0.15,
    "url": 0.10,
    "manual": 0.08,
    "chatgpt_macos_app": 0.05,
}

# Minimum tekstlengte om een score te geven (te kort = ruis)
_MIN_TEXT_LENGTH = 20


# ---------------------------------------------------------------------------
# ResonanceScore — het publieke resultaat
# ---------------------------------------------------------------------------
@dataclass
class ResonanceScore:
    """
    Resultaat van een resonantie-scoring operatie.

    Attributen:
        score      : float 0.0–1.0 (geclamped). Vergelijk met STORE/PROPOSE drempels.
        reasons    : lijst van mensleesbare verklaringen per deelscore.
        persona    : de persona waarvoor gescoord is ("philip" | "developer" | "general").
        matched_domains : welke kennisdomeinen een hit genereerden.
        thresholds : dict met store- en propose-drempel voor referentie.
        keyword_score : ruwe trefwoordscore (voor debugging).
        tag_score     : ruwe tagscore.
        source_score  : ruwe bronscore.
        title_boost   : ruwe titelboost.
    """
    score: float
    reasons: List[str] = field(default_factory=list)
    persona: str = "philip"
    matched_domains: List[str] = field(default_factory=list)
    thresholds: Dict[str, float] = field(default_factory=lambda: {
        "store": STORE_THRESHOLD,
        "propose": PROPOSE_THRESHOLD,
    })
    keyword_score: float = 0.0
    tag_score: float = 0.0
    source_score: float = 0.0
    title_boost: float = 0.0

    @property
    def should_store(self) -> bool:
        return self.score >= STORE_THRESHOLD

    @property
    def should_propose(self) -> bool:
        return self.score >= PROPOSE_THRESHOLD

    def __repr__(self) -> str:
        return (
            f"ResonanceScore(score={self.score:.3f}, persona={self.persona!r}, "
            f"domains={self.matched_domains}, store={self.should_store}, "
            f"propose={self.should_propose})"
        )


# ---------------------------------------------------------------------------
# Interne helpers
# ---------------------------------------------------------------------------
def _tokenize(text: str) -> str:
    """Normaliseert tekst naar lowercase voor trefwoordmatching."""
    return text.lower()


def _count_keyword_hits(text_lower: str, keywords: List[str]) -> int:
    """Telt unieke trefwoordhits in text (elk trefwoord max 1 keer geteld)."""
    hits = 0
    for kw in keywords:
        if kw in text_lower:
            hits += 1
    return hits


def _score_keywords(
    item: NormalizedItem,
    persona: str,
) -> tuple[float, List[str], List[str]]:
    """
    Berekent de trefwoordscore (max 0.50) over alle domeinen van de persona.

    Returns:
        (raw_score, reasons, matched_domains)
    """
    domains = PERSONA_KEYWORDS.get(persona, {})
    if not domains:
        return 0.0, [], []

    corpus = _tokenize(item.title + " " + item.text)
    total_hits = 0
    reasons: List[str] = []
    matched_domains: List[str] = []

    for domain, keywords in domains.items():
        hits = _count_keyword_hits(corpus, keywords)
        if hits > 0:
            total_hits += hits
            matched_domains.append(domain)
            reasons.append(
                f"domein '{domain}': {hits} trefwoord(en) gevonden"
            )

    # Logaritmisch schalen: 1 hit → ~0.10, 5 hits → ~0.35, 10+ hits → ~0.50
    if total_hits == 0:
        return 0.0, reasons, matched_domains

    import math
    raw = min(0.50, math.log(1 + total_hits, 2) * 0.15)
    return raw, reasons, matched_domains


def _score_tags(item: NormalizedItem, persona: str) -> tuple[float, List[str]]:
    """
    Berekent de tagboost (max 0.20).

    Tags zijn al door de bron gelabeld — een directe match is sterker signaal
    dan toevallige trefwoordhit in de body.
    """
    if not item.tags:
        return 0.0, []

    domains = PERSONA_KEYWORDS.get(persona, {})
    all_keywords = [kw for kws in domains.values() for kw in kws]

    hits = 0
    matched_tags = []
    for tag in item.tags:
        tag_lower = tag.lower()
        if any(kw in tag_lower or tag_lower in kw for kw in all_keywords):
            hits += 1
            matched_tags.append(tag)

    if hits == 0:
        return 0.0, []

    raw = min(0.20, hits * 0.07)
    reasons = [f"tags gematcht: {matched_tags}"]
    return raw, reasons


def _score_source(item: NormalizedItem) -> tuple[float, List[str]]:
    """Retourneert brongewicht (max 0.15) op basis van source_type."""
    weight = _SOURCE_WEIGHTS.get(item.source_type, 0.05)
    reasons = [f"source_type '{item.source_type}' → gewicht {weight:.2f}"]
    return weight, reasons


def _score_title_boost(item: NormalizedItem, persona: str) -> tuple[float, List[str]]:
    """
    Titelboost (max 0.15): trefwoord in de titel is sterker signaal dan in body.
    """
    domains = PERSONA_KEYWORDS.get(persona, {})
    all_keywords = [kw for kws in domains.values() for kw in kws]
    title_lower = _tokenize(item.title)

    hits = _count_keyword_hits(title_lower, all_keywords)
    if hits == 0:
        return 0.0, []

    raw = min(0.15, hits * 0.05)
    reasons = [f"titel '{item.title[:60]}' bevat {hits} sleuteltrefwoord(en)"]
    return raw, reasons


# ---------------------------------------------------------------------------
# Publieke interface
# ---------------------------------------------------------------------------
def score(
    item: NormalizedItem,
    persona: str = "philip",
) -> ResonanceScore:
    """
    Berekent de resonantiescore van een NormalizedItem voor een gegeven persona.

    De score is volledig deterministisch (geen LLM, geen random). Dit maakt
    de resonantiefilter testbaar, auditeerbaar en reproduceerbaar.

    Scoreopbouw (additief, geclamped naar 0.0–1.0):
        1. Trefwoordmatch  (max 0.50) — domeinhits in titel+tekst
        2. Tagboost        (max 0.20) — tags matchen op domeintrefwoorden
        3. Brongewicht     (max 0.15) — source_type heuristiek
        4. Titelboost      (max 0.15) — trefwoord specifiek in de titel

    Args:
        item   : NormalizedItem van normalize.normalize().
        persona: "philip" (default) | "developer" | "general"

    Returns:
        ResonanceScore met score, reasons, matched_domains en drempels.
    """
    # Ongeldige persona → terugvallen op "general"
    if persona not in PERSONA_KEYWORDS:
        persona = "general"

    # Te korte tekst → directe afwijzing (ruis)
    combined_len = len(item.title) + len(item.text)
    if combined_len < _MIN_TEXT_LENGTH:
        return ResonanceScore(
            score=0.0,
            reasons=["tekst te kort voor zinvolle scoring (< 20 tekens)"],
            persona=persona,
        )

    # --- Deelscores berekenen ---
    kw_score, kw_reasons, matched_domains = _score_keywords(item, persona)
    tag_score, tag_reasons = _score_tags(item, persona)
    src_score, src_reasons = _score_source(item)
    title_boost, title_reasons = _score_title_boost(item, persona)

    raw_total = kw_score + tag_score + src_score + title_boost
    final_score = round(min(1.0, max(0.0, raw_total)), 4)

    all_reasons = kw_reasons + tag_reasons + src_reasons + title_reasons
    if not all_reasons:
        all_reasons = ["geen trefwoordhits gevonden"]

    return ResonanceScore(
        score=final_score,
        reasons=all_reasons,
        persona=persona,
        matched_domains=matched_domains,
        keyword_score=kw_score,
        tag_score=tag_score,
        source_score=src_score,
        title_boost=title_boost,
    )


def batch_score(
    items: List[NormalizedItem],
    persona: str = "philip",
) -> List[ResonanceScore]:
    """
    Scoort een lijst van NormalizedItems in één aanroep.

    Args:
        items  : lijst van NormalizedItems.
        persona: persona voor alle items (default "philip").

    Returns:
        Lijst van ResonanceScores, zelfde volgorde als input.
    """
    return [score(item, persona=persona) for item in items]


# ---------------------------------------------------------------------------
# CLI smoke-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    try:
        from controller.stream.normalize import normalize as norm

        hoog = norm({
            "title": "Wintrip AI autonome stream daemon gebouwd",
            "text": (
                "De nieuwe stream of consciousness architectuur van Wintrip AI "
                "maakt gebruik van een altijd-aan OODA loop die lokale LLMs via "
                "Ollama aanstuurt. ChromaDB Hippocampus slaat de resonerende items op."
            ),
            "source_type": "rss",
            "tags": ["wintrip", "ai", "autonomy"],
        })

        laag = norm({
            "title": "Weer in Amsterdam",
            "text": "Het gaat morgen regenen in Amsterdam. Temperatuur 12 graden.",
            "source_type": "rss",
            "tags": ["weer"],
        })

        for label, item in [("HOOG", hoog), ("LAAG", laag)]:
            rs = score(item)
            print(f"\n[{label}] {rs}")
            for r in rs.reasons:
                print(f"  → {r}")

    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
