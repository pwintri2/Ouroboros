import asyncio

from resonant_ouroboros.browser import BrowserAction, BrowserSnapshot, HumanBrowserEngine
from resonant_ouroboros.memory import InMemoryHippocampusMemory
from resonant_ouroboros.oscillator import HertzOscillator
from resonant_ouroboros.paeu_loop import PAEULoop
from resonant_ouroboros.safety import evaluate_url
from resonant_ouroboros.seed import SeedKnowledgeLoader, parse_seed_topics, queue_seed_topics_without_browser
from resonant_ouroboros.vision import VisionObservation


def test_parse_seed_topics_from_agi_kennis():
    loader = SeedKnowledgeLoader("AGI Kennis.txt")
    topics = loader.load_topics()
    titles = [topic.title for topic in topics]
    assert "Linear algebra" in titles
    assert "Sandboxing" in titles
    assert len(topics) >= 4


def test_parse_seed_topics_handles_plain_bullets():
    topics = parse_seed_topics("### Test\n* Plain topic\n* **Named:** Details")
    assert [topic.title for topic in topics] == ["Plain topic", "Named"]


def test_url_safety_blocks_localhost_and_allows_https():
    assert not evaluate_url("http://localhost:8000").allowed
    assert not evaluate_url("file:///etc/passwd").allowed
    assert evaluate_url("https://example.com").allowed


def test_queue_seed_topics_without_browser_stores_11d_records():
    oscillator = HertzOscillator(spike_probability=0.0)
    browser = HumanBrowserEngine()
    memory = InMemoryHippocampusMemory()
    loop = PAEULoop(oscillator, browser, memory)
    rows = queue_seed_topics_without_browser("AGI Kennis.txt", loop, max_topics=2)
    assert len(rows) == 2
    assert memory.count() == 2
    metadata = memory.rows[0]["metadata"]
    assert metadata["dimension_count"] == 11
    assert "current_hz" in metadata


def test_zero_max_topics_queues_no_seed_topics():
    oscillator = HertzOscillator(spike_probability=0.0)
    browser = HumanBrowserEngine()
    memory = InMemoryHippocampusMemory()
    loop = PAEULoop(oscillator, browser, memory)
    assert queue_seed_topics_without_browser("AGI Kennis.txt", loop, max_topics=0) == []


def test_initial_browser_action_uses_wikipedia_search():
    async def run_check():
        engine = HumanBrowserEngine()
        behavior = HertzOscillator(spike_probability=0.0).behavior_for_hz(426.0)
        action = engine.propose_next_action("linear algebra", None, behavior)
        assert action.action_type == "navigate"
        assert action.target.startswith("https://en.wikipedia.org/w/index.php?search=")

    asyncio.run(run_check())


def test_paeu_loop_stores_browser_snapshot():
    class FakeBrowser:
        allow_private_hosts = False

        def propose_next_action(self, topic, snapshot, behavior):
            return BrowserAction("navigate", "https://example.com/agi", "unit navigation")

        async def navigate(self, target, behavior):
            return BrowserSnapshot(
                url=target,
                title="AGI Unit Page",
                visible_text="Safe learning context with enough visible content for quality. " * 12,
                screenshot_path=None,
                vision=VisionObservation("unit vision", "unit", None),
                links=["https://example.com/agi/next"],
                quality_score=0.9,
                quality_reason="accepted",
            )

    oscillator = HertzOscillator(spike_probability=0.0)
    memory = InMemoryHippocampusMemory()
    loop = PAEULoop(oscillator, FakeBrowser(), memory)
    events = asyncio.run(loop.learn_topic("AGI", steps=1))
    assert events[0].stored_record_id
    assert memory.count() == 1
