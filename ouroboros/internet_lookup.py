"""
internet_lookup.py – Mock internet lookup via een lokale JSON-database.

Simuleert basale zoekopdrachten door trefwoorden te matchen tegen antwoorden.json.
"""

from __future__ import annotations

import json
import os
from difflib import get_close_matches
from typing import Optional

_DB_PATH = os.path.join(os.path.dirname(__file__), "antwoorden.json")


def _load_db() -> dict:
    with open(_DB_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def zoek(query: str) -> dict:
    """Zoek een antwoord op *query* in de lokale mock-database.

    Returns een dict met 'antwoord' en optioneel 'actie'/'app'.
    """
    if not query:
        return _fallback()

    db = _load_db()
    query_lower = query.lower()

    # 1. Directe sleutelwoordmatch
    for key, entry in db.items():
        if key == "standaard":
            continue
        if key in query_lower or any(
            word in query_lower for word in entry.get("vraag", "").lower().split()
        ):
            return entry

    # 2. Fuzzy match op sleutels
    matches = get_close_matches(query_lower, [k for k in db if k != "standaard"], n=1, cutoff=0.5)
    if matches:
        return db[matches[0]]

    # 3. Fallback
    return _fallback()


def _fallback() -> dict:
    db = _load_db()
    return db.get("standaard", {"antwoord": "Geen antwoord gevonden.", "actie": "info"})


if __name__ == "__main__":
    test_queries = ["Open Kladblok", "hoe maak ik een screenshot", "volume aanpassen", "xyz"]
    for q in test_queries:
        result = zoek(q)
        print(f"Query: {q!r}")
        print(f"  → {result['antwoord']}\n")
