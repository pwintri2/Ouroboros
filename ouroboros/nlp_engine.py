"""
nlp_engine.py – Intentieherkenning voor Ouroboros Proto 1.

Strategie:
  1. Probeer een lokaal zero-shot classificatiemodel (transformers).
  2. Als dat niet beschikbaar is, val terug op een regex/keyword matcher.

Ondersteunde intentes:
  - open_app    : gebruiker wil een applicatie openen
  - screenshot  : gebruiker wil een screenshot maken
  - info        : gebruiker stelt een informatievraag
  - stop        : gebruiker wil de demo stoppen
  - onbekend    : intentie niet herkend
"""

from __future__ import annotations

import re
from typing import Tuple

# Intentielabels en bijbehorende trefwoorden voor de keyword-fallback
_KEYWORD_MAP: dict[str, list[str]] = {
    "open_app": [
        "open", "start", "lanceer", "opstart", "opstarten",
        "kladblok", "verkenner", "rekenmachine", "browser",
        "instellingen", "taakbeheer", "taakmgr",
    ],
    "screenshot": ["screenshot", "schermafbeelding", "knipprogramma", "printscreen"],
    "stop": ["stop", "sluit", "afsluiten", "stoppen", "exit", "quit"],
    "info": ["hoe", "wat", "waarom", "wanneer", "welk", "waar", "uitleg", "help"],
}

_CANDIDATE_LABELS = list(_KEYWORD_MAP.keys()) + ["onbekend"]

# Probeer transformers te laden; gebruik anders keyword-fallback
_classifier = None

try:
    from transformers import pipeline as _hf_pipeline  # type: ignore

    _classifier = _hf_pipeline(
        "zero-shot-classification",
        model="typeform/distilbart-mnli-12-3",
        multi_label=False,
    )
except Exception:
    _classifier = None


def herken_intentie(tekst: str) -> Tuple[str, float]:
    """Geef ``(intentie, confidence)`` terug voor *tekst*.

    Bij gebruik van het HuggingFace-model is *confidence* de werkelijke score.
    Bij de keyword-fallback is *confidence* altijd 1.0 of 0.0.
    """
    if not tekst or not tekst.strip():
        return "onbekend", 0.0

    if _classifier is not None:
        return _herken_met_model(tekst)
    return _herken_met_keywords(tekst)


def _herken_met_model(tekst: str) -> Tuple[str, float]:
    result = _classifier(tekst, candidate_labels=_CANDIDATE_LABELS)  # type: ignore[misc]
    top_label: str = result["labels"][0]
    top_score: float = result["scores"][0]
    return top_label, round(top_score, 3)


def _herken_met_keywords(tekst: str) -> Tuple[str, float]:
    lower = tekst.lower()
    for intentie, keywords in _KEYWORD_MAP.items():
        for kw in keywords:
            if re.search(rf"\b{re.escape(kw)}\b", lower):
                return intentie, 1.0
    return "onbekend", 0.0


if __name__ == "__main__":
    testgevallen = [
        "Open Kladblok alsjeblieft",
        "Hoe maak ik een screenshot?",
        "Stop de demo",
        "Wat is de betekenis van leven?",
        "",
    ]
    for t in testgevallen:
        label, score = herken_intentie(t)
        print(f"  {t!r:45s} → {label} ({score:.2f})")
