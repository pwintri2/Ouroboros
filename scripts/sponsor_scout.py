#!/usr/bin/env python3
"""Find potential GitHub sponsors and generate a human-reviewed outreach report."""

from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable


DEFAULT_QUERIES = [
    "privacy first AI assistant stars:>20",
    "local AI agent macOS stars:>20",
    "ollama fastapi AI agent stars:>20",
    "open source AI privacy Netherlands stars:>10",
]

POSITIVE_TERMS = {
    "ai": 10,
    "agent": 8,
    "assistant": 6,
    "privacy": 12,
    "local-first": 12,
    "local": 5,
    "macos": 7,
    "ollama": 8,
    "rag": 6,
    "automation": 5,
    "open-source": 5,
    "security": 5,
    "netherlands": 7,
    "dutch": 5,
}

NEGATIVE_TERMS = {
    "crypto": -12,
    "casino": -20,
    "gambling": -20,
    "adult": -20,
    "nft": -10,
}

SPONSOR_ASK_NL = (
    "Zou {owner} WintripAI / Ouroboros willen steunen als vroege sponsor met "
    "een bescheiden bijdrage van €250 per maand of een eenmalige pilotbijdrage "
    "van €1.000? In ruil krijgt de sponsor zichtbaarheid in de projectupdates, "
    "vroege demo-toegang en directe invloed op de privacy-first AI roadmap. "
    "Als dit te vroeg is, is een korte kennismaking of introductie naar een "
    "passende innovation/AI lead ook al waardevol."
)


@dataclass(frozen=True)
class Candidate:
    owner: str
    name: str
    url: str
    description: str
    stars: int
    topics: tuple[str, ...]
    language: str
    score: int
    reasons: tuple[str, ...]

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"


def github_get_json(url: str, token: str | None = None, timeout: int = 20) -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "wintripai-sponsor-scout",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API gaf HTTP {exc.code}: {body[:300]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"GitHub API is niet bereikbaar: {exc.reason}") from exc


def build_search_url(query: str, per_page: int) -> str:
    params = urllib.parse.urlencode(
        {
            "q": query,
            "sort": "stars",
            "order": "desc",
            "per_page": max(1, min(per_page, 100)),
        }
    )
    return f"https://api.github.com/search/repositories?{params}"


def score_repository(repo: dict) -> tuple[int, tuple[str, ...]]:
    text_parts = [
        repo.get("name") or "",
        repo.get("description") or "",
        repo.get("language") or "",
        " ".join(repo.get("topics") or []),
    ]
    haystack = " ".join(text_parts).lower()
    score = 0
    reasons: list[str] = []

    stars = int(repo.get("stargazers_count") or 0)
    if stars >= 1000:
        score += 20
        reasons.append("veel GitHub-sterren")
    elif stars >= 250:
        score += 14
        reasons.append("sterke open-source tractie")
    elif stars >= 50:
        score += 8
        reasons.append("zichtbare niche-tractie")

    for term, value in POSITIVE_TERMS.items():
        if term in haystack:
            score += value
            reasons.append(f"match op '{term}'")

    for term, value in NEGATIVE_TERMS.items():
        if term in haystack:
            score += value
            reasons.append(f"negatieve match op '{term}'")

    if repo.get("has_sponsors_listing"):
        score += 10
        reasons.append("heeft al GitHub Sponsors-ervaring")

    if repo.get("archived"):
        score -= 25
        reasons.append("repository is gearchiveerd")

    if not reasons:
        reasons.append("algemene AI/open-source overlap")

    return score, tuple(dict.fromkeys(reasons))


def candidate_from_repo(repo: dict) -> Candidate:
    score, reasons = score_repository(repo)
    owner = (repo.get("owner") or {}).get("login") or "unknown"
    return Candidate(
        owner=owner,
        name=repo.get("name") or "unknown",
        url=repo.get("html_url") or "",
        description=repo.get("description") or "",
        stars=int(repo.get("stargazers_count") or 0),
        topics=tuple(repo.get("topics") or []),
        language=repo.get("language") or "unknown",
        score=score,
        reasons=reasons,
    )


def deduplicate_candidates(candidates: Iterable[Candidate]) -> list[Candidate]:
    best_by_repo: dict[str, Candidate] = {}
    for candidate in candidates:
        current = best_by_repo.get(candidate.full_name)
        if current is None or candidate.score > current.score:
            best_by_repo[candidate.full_name] = candidate
    return sorted(best_by_repo.values(), key=lambda item: (-item.score, -item.stars, item.full_name))


def search_candidates(queries: list[str], limit: int, token: str | None = None) -> list[Candidate]:
    raw_candidates: list[Candidate] = []
    per_query = max(10, min(50, limit * 2))

    for index, query in enumerate(queries):
        if index:
            time.sleep(1)
        payload = github_get_json(build_search_url(query, per_query), token=token)
        raw_candidates.extend(candidate_from_repo(item) for item in payload.get("items", []))

    return deduplicate_candidates(raw_candidates)[:limit]


def render_markdown(candidates: list[Candidate], queries: list[str]) -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Sponsor Scout Rapport",
        "",
        f"Gegenereerd: {generated_at}",
        "",
        "Dit rapport zoekt alleen publieke GitHub-signalen en verstuurt niets automatisch.",
        "Gebruik de voorstellen als menselijke shortlist; personaliseer elke benadering.",
        "",
        "## Zoekqueries",
        "",
    ]
    lines.extend(f"- `{query}`" for query in queries)
    lines.extend(["", "## Redelijke sponsorvraag", "", SPONSOR_ASK_NL.format(owner="de organisatie"), ""])
    lines.extend(["## Kandidaten", ""])

    if not candidates:
        lines.append("Geen kandidaten gevonden.")
        return "\n".join(lines) + "\n"

    for idx, candidate in enumerate(candidates, start=1):
        topics = ", ".join(candidate.topics[:8]) if candidate.topics else "geen topics"
        reasons = "; ".join(candidate.reasons[:6])
        ask = SPONSOR_ASK_NL.format(owner=candidate.owner)
        lines.extend(
            [
                f"### {idx}. {candidate.full_name}",
                "",
                f"- Score: {candidate.score}",
                f"- URL: {candidate.url}",
                f"- Sterren: {candidate.stars}",
                f"- Taal: {candidate.language}",
                f"- Topics: {topics}",
                f"- Waarom logisch: {reasons}",
                f"- Beschrijving: {candidate.description or 'geen beschrijving'}",
                "",
                "**Voorstelbericht (niet automatisch versturen):**",
                "",
                textwrap.fill(ask, width=100),
                "",
            ]
        )

    return "\n".join(lines) + "\n"


def render_json(candidates: list[Candidate], queries: list[str]) -> str:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "queries": queries,
        "sponsor_ask_nl": SPONSOR_ASK_NL.format(owner="{owner}"),
        "candidates": [
            {
                "full_name": candidate.full_name,
                "owner": candidate.owner,
                "name": candidate.name,
                "url": candidate.url,
                "description": candidate.description,
                "stars": candidate.stars,
                "topics": list(candidate.topics),
                "language": candidate.language,
                "score": candidate.score,
                "reasons": list(candidate.reasons),
                "suggested_ask_nl": SPONSOR_ASK_NL.format(owner=candidate.owner),
            }
            for candidate in candidates
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Maak een sponsor-shortlist op basis van publieke GitHub-data.")
    parser.add_argument("--query", action="append", dest="queries", help="GitHub repository search query; herhaalbaar.")
    parser.add_argument("--limit", type=int, default=20, help="Maximum aantal kandidaten in het rapport.")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown", help="Outputformaat.")
    parser.add_argument("--output", help="Pad voor rapportoutput. Zonder pad wordt stdout gebruikt.")
    parser.add_argument("--token", default=os.getenv("GITHUB_TOKEN"), help="GitHub token; standaard uit GITHUB_TOKEN.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    queries = args.queries or DEFAULT_QUERIES
    try:
        candidates = search_candidates(queries=queries, limit=max(1, args.limit), token=args.token)
    except RuntimeError as exc:
        print(f"FOUT: {exc}", file=sys.stderr)
        print("Tip: zet GITHUB_TOKEN voor hogere rate limits en toegang tot GitHub Actions.", file=sys.stderr)
        return 1
    content = render_json(candidates, queries) if args.format == "json" else render_markdown(candidates, queries)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as output_file:
            output_file.write(content)
    else:
        print(content, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
