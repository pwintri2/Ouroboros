"""Seed knowledge parsing and browser-learning orchestration."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .paeu_loop import PAEULoop
from .safety import sanitize_query


@dataclass(frozen=True)
class SeedTopic:
    section: str
    title: str
    details: str

    @property
    def search_phrase(self) -> str:
        return sanitize_query(f"{self.title}: {self.details}")


class SeedKnowledgeLoader:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load_topics(self) -> list[SeedTopic]:
        if not self.path.exists():
            raise FileNotFoundError(f"seed knowledge file not found: {self.path}")
        text = self.path.read_text(encoding="utf-8-sig")
        return parse_seed_topics(text)


def parse_seed_topics(text: str) -> list[SeedTopic]:
    topics: list[SeedTopic] = []
    current_section = "Unsectioned"
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("###"):
            current_section = line.lstrip("#").strip()
            continue
        match = re.match(r"[*-]\s+\*\*(.+?):\*\*\s*(.+)", line)
        if match:
            topics.append(
                SeedTopic(
                    section=current_section,
                    title=match.group(1).strip(),
                    details=match.group(2).strip(),
                )
            )
            continue
        if line.startswith("*") or line.startswith("-"):
            cleaned = line.lstrip("*- ").strip()
            if cleaned:
                topics.append(SeedTopic(current_section, cleaned, ""))
    return topics


async def browse_and_learn_seed(
    seed_path: str | Path,
    loop: PAEULoop,
    max_topics: int | None = None,
    steps_per_topic: int = 3,
) -> list[dict[str, object]]:
    loader = SeedKnowledgeLoader(seed_path)
    topics = loader.load_topics()
    selected = topics[:max_topics] if max_topics else topics
    results = []
    for topic in selected:
        events = await loop.learn_topic(topic.search_phrase, steps=steps_per_topic)
        results.append({"topic": topic, "events": events})
    return results


def queue_seed_topics_without_browser(
    seed_path: str | Path,
    loop: PAEULoop,
    max_topics: int | None = None,
) -> list[str]:
    topics = SeedKnowledgeLoader(seed_path).load_topics()
    selected = topics[:max_topics] if max_topics else topics
    return [loop.store_seed_topic_without_browser(topic.search_phrase) for topic in selected]
