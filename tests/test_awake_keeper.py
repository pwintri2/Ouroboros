import asyncio
from pathlib import Path
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import json

from resonant_ouroboros.awake_keeper import AwakeKeeper, AwakeKeeperConfig, OllamaBridge
from resonant_ouroboros.browser import BrowserAction, BrowserSnapshot
from resonant_ouroboros.evolution import EvolutionEvent
from resonant_ouroboros.memory import InMemoryHippocampusMemory
from resonant_ouroboros.oscillator import HertzOscillator
from resonant_ouroboros.vision import VisionObservation
from resonant_ouroboros.seed import SeedKnowledgeLoader


class FakeOllama:
    model = "fake:latest"
    last_error = None
    last_model_used = "fake:latest"

    def __init__(self):
        self.texts = []

    def emotional_valence(self, text, prompt_context=None):
        return 0.2

    def summarize_page(self, title, url, visible_text, hz=None, mood=None, prompt_context=None):
        return f"summary:{title}:{round(hz or 0)}:{mood}"

    def empathetic_response(self, message, context="", prompt_context=None):
        return f"empathy:{message}:{bool(context)}"

    def code_help(self, question, context="", prompt_context=None):
        return f"code:{question}:{bool(context)}"


class FakeBrowser:
    allow_private_hosts = False

    def propose_next_action(self, topic, snapshot, behavior):
        if snapshot is None:
            return BrowserAction("navigate", "https://example.com/agi", "unit navigation")
        return BrowserAction("scroll", "down", "unit scroll")

    async def navigate(self, target, behavior):
        return self.snapshot(target)

    async def scroll(self, behavior, direction="down", steps=2):
        return self.snapshot("https://example.com/agi/scrolled")

    async def close(self):
        return None

    def snapshot(self, target):
        return BrowserSnapshot(
            url=target,
            title="AGI Unit Page",
            visible_text="Safe learning context with enough visible content for quality. " * 12,
            screenshot_path=None,
            vision=VisionObservation("unit vision", "unit", None),
            links=["https://example.com/agi/next"],
            quality_score=0.95,
            quality_reason="accepted",
        )


def test_awake_keeper_run_once_updates_status_and_memory(tmp_path):
    memory = InMemoryHippocampusMemory()
    config = AwakeKeeperConfig(
        seed_path=Path("AGI Kennis.txt"),
        interval_min_seconds=0.01,
        interval_max_seconds=0.02,
        steps_per_tick=1,
        spike_steps_per_tick=1,
        model="fake:latest",
        ollama_base_url="http://fake",
        self_model_path=tmp_path / "self_model.json",
        evolution_events_path=tmp_path / "evolution.jsonl",
    )
    keeper = AwakeKeeper(
        config=config,
        oscillator=HertzOscillator(spike_probability=0.0),
        memory_factory=lambda: memory,
        browser_factory=FakeBrowser,
        ollama=FakeOllama(),
    )
    events = asyncio.run(keeper.run_once(topic="AGI unit"))
    status = keeper.status()
    assert events
    assert memory.count() == 1
    assert status.iterations == 1
    assert status.last_record_id
    assert status.last_summary.startswith("summary:")
    assert status.last_knowledge_kind == "AGI Architecture"
    feed = keeper.knowledge_feed()
    assert feed
    assert feed[0]["kind"] == "AGI Architecture"
    assert feed[0]["record_id"] == status.last_record_id
    assert "summary:" in feed[0]["summary"]
    assert keeper.self_model.status_summary()["identity"]["name"] == "Resonant Ouroboros"
    assert keeper.self_model.status_summary()["reflection_count"] >= 1


def test_awake_keeper_chat_uses_code_help_for_programming_question(tmp_path):
    memory = InMemoryHippocampusMemory()
    config = AwakeKeeperConfig(
        seed_path=Path("AGI Kennis.txt"),
        interval_min_seconds=0.01,
        interval_max_seconds=0.02,
        model="fake:latest",
        ollama_base_url="http://fake",
        chat_browser_enabled=False,
        self_model_path=tmp_path / "self_model.json",
        evolution_events_path=tmp_path / "evolution.jsonl",
    )
    keeper = AwakeKeeper(
        config=config,
        memory_factory=lambda: memory,
        browser_factory=FakeBrowser,
        ollama=FakeOllama(),
    )
    answer = asyncio.run(keeper.answer_question("Python code bug"))
    assert answer.startswith("code:")
    assert memory.count() == 1
    assert keeper.evolution_store.list_events(limit=1)[0]["type"] == "chat"
    assert keeper.status().co_evolution_score > 0
    assert keeper.status().suggested_learning_actions
    growth = keeper.growth_indicators()
    assert "autonomy" in growth
    assert "co_evolution_status" in growth
    assert growth["co_evolution_status"]["help_moments"]


def test_awake_keeper_bootstrap_imports_all_seed_topics(tmp_path):
    memory = InMemoryHippocampusMemory()
    config = AwakeKeeperConfig(
        seed_path=Path("AGI Kennis.txt"),
        interval_min_seconds=0.01,
        interval_max_seconds=0.02,
        model="fake:latest",
        ollama_base_url="http://fake",
        self_model_path=tmp_path / "self_model.json",
        evolution_events_path=tmp_path / "evolution.jsonl",
    )
    keeper = AwakeKeeper(
        config=config,
        oscillator=HertzOscillator(spike_probability=0.0),
        memory_factory=lambda: memory,
        browser_factory=FakeBrowser,
        ollama=FakeOllama(),
    )
    topics = SeedKnowledgeLoader("AGI Kennis.txt").load_topics()
    keeper._bootstrap_seed_memory(memory)
    status = keeper.status()
    feed = keeper.knowledge_feed()
    assert memory.count() == len(topics)
    assert status.seed_records_imported == len(topics)
    assert status.iterations == len(topics)
    assert len(feed) == len(topics)
    assert any(row["kind"] == "Empathy / Context" for row in feed)
    assert any("AGI communication posture" in row["topic"] for row in feed)


def test_awake_keeper_imports_extra_local_knowledge(tmp_path):
    local_root = tmp_path / "Jarosmalen"
    local_root.mkdir()
    (local_root / "README.md").write_text("# Jarosmalen\nGraph runner local project knowledge.", encoding="utf-8")
    memory = InMemoryHippocampusMemory()
    config = AwakeKeeperConfig(
        seed_path=Path("AGI Kennis.txt"),
        interval_min_seconds=0.01,
        interval_max_seconds=0.02,
        model="fake:latest",
        ollama_base_url="http://fake",
        self_model_path=tmp_path / "self_model.json",
        evolution_events_path=tmp_path / "evolution.jsonl",
        extra_knowledge_paths=(local_root,),
        extra_knowledge_max_files=5,
    )
    keeper = AwakeKeeper(
        config=config,
        oscillator=HertzOscillator(spike_probability=0.0),
        memory_factory=lambda: memory,
        browser_factory=FakeBrowser,
        ollama=FakeOllama(),
    )
    keeper._bootstrap_local_knowledge(memory)
    status = keeper.status()
    feed = keeper.knowledge_feed()
    assert memory.count() == 1
    assert status.local_records_imported == 1
    assert feed[0]["action"] == "local_knowledge_bootstrap"
    assert "README.md" in feed[0]["topic"]


def test_awake_keeper_prompt_context_populates_links_and_proposals(tmp_path):
    memory = InMemoryHippocampusMemory()
    config = AwakeKeeperConfig(
        seed_path=Path("AGI Kennis.txt"),
        model="fake:latest",
        ollama_base_url="http://fake",
        chat_browser_enabled=False,
        self_model_path=tmp_path / "self_model.json",
        evolution_events_path=tmp_path / "evolution.jsonl",
    )
    keeper = AwakeKeeper(
        config=config,
        memory_factory=lambda: memory,
        browser_factory=FakeBrowser,
        ollama=FakeOllama(),
    )
    keeper.evolution_store.append(
        EvolutionEvent(
            event_type="knowledge_link",
            topic="Jarosmalen links",
            input_summary="link input",
            output_summary="linked r1 to r2",
            score_delta=0.07,
        )
    )
    keeper.evolution_store.reflect(
        "prompt context",
        "reflect input",
        "Proposal: surface pending proposals in prompts.",
        status="approved",
        score_delta=0.14,
    )

    context = keeper._prompt_context(task="chat", query="Jarosmalen")
    state = context.current_state_text()
    assert "knowledge_links=(" in state
    assert "linked r1 to r2" in state
    assert "reviewed_proposals=UNTRUSTED approved proposal summaries" in state
    assert "surface pending proposals" in state


def test_ollama_bridge_uses_http_api_and_available_models():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"models": [{"name": "fake:latest"}]}).encode("utf-8"))

        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(length)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"message": {"content": "0.4"}}).encode("utf-8"))

        def log_message(self, format, *args):
            return None

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        bridge = OllamaBridge(
            model="missing:latest",
            base_url=f"http://127.0.0.1:{server.server_port}",
            fallback_models=("fake:latest",),
            request_timeout=2,
        )
        assert bridge.available_models() == ["fake:latest"]
        assert bridge.emotional_valence("calm useful text") == 0.4
        assert bridge.last_model_used == "missing:latest"
    finally:
        server.shutdown()


def test_ollama_bridge_respects_max_model_attempts_without_tag_lookup():
    bridge = OllamaBridge(
        model="primary:latest",
        base_url="http://127.0.0.1:9",
        fallback_models=("fallback:latest",),
        request_timeout=0.01,
        max_model_attempts=1,
    )
    assert bridge._candidate_models() == ["primary:latest"]
