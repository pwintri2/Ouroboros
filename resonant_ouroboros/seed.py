"""Seed knowledge parsing and browser-learning orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from .paeu_loop import PAEULoop
from .safety import sanitize_query


@dataclass(frozen=True)
class SeedTopic:
    section: str
    title: str
    details: str

    @property
    def search_phrase(self) -> str:
        combined = f"{self.title} {self.details}".strip()
        return sanitize_query(combined or self.title)


class SeedKnowledgeLoader:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def load_topics(self) -> list[SeedTopic]:
        if not self.path.exists():
            raise FileNotFoundError(f"seed knowledge file not found: {self.path}")
        return parse_seed_topics(self.path.read_text(encoding="utf-8-sig"))


def parse_seed_topics(text: str) -> list[SeedTopic]:
    topics: list[SeedTopic] = []
    current_section = "Unsectioned"
    named_pattern = re.compile(r"[*-]\s+\*\*(.+?):\*\*\s*(.+)")
    for raw_line in (text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            current_section = line.lstrip("#").strip() or current_section
            continue
        if line.startswith(("*", "-")):
            named = named_pattern.match(line)
            if named:
                topics.append(
                    SeedTopic(
                        section=current_section,
                        title=named.group(1).strip(),
                        details=named.group(2).strip(),
                    )
                )
            else:
                cleaned = line.lstrip("*-").strip()
                topics.append(SeedTopic(section=current_section, title=cleaned, details=""))
    return topics


async def browse_and_learn_seed(
    seed_path: str | Path,
    loop: PAEULoop,
    max_topics: int | None = None,
    steps_per_topic: int = 3,
) -> list[dict[str, object]]:
    loader = SeedKnowledgeLoader(seed_path)
    topics = loader.load_topics()
    selected = topics if max_topics is None else topics[: max(0, max_topics)]
    results: list[dict[str, object]] = []
    for topic in selected:
        events = await loop.learn_topic(topic.search_phrase, steps=steps_per_topic)
        results.append({"topic": topic.search_phrase, "events": events})
    return results


def queue_seed_topics_without_browser(
    seed_path: str | Path,
    loop: PAEULoop,
    max_topics: int | None = None,
) -> list[str]:
    loader = SeedKnowledgeLoader(seed_path)
    topics = loader.load_topics()
    selected = topics if max_topics is None else topics[: max(0, max_topics)]
    return [loop.store_seed_topic_without_browser(topic.search_phrase) for topic in selected]
