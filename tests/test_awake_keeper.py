import asyncio
from pathlib import Path
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
import json

from resonant_ouroboros.awake_keeper import AwakeKeeper, AwakeKeeperConfig, OllamaBridge
from resonant_ouroboros.browser import BrowserAction, BrowserSnapshot
from resonant_ouroboros.memory import InMemoryHippocampusMemory
from resonant_ouroboros.oscillator import HertzOscillator
from resonant_ouroboros.vision import VisionObservation


class FakeOllama:
    model = "fake:latest"
    last_error = None
    last_model_used = "fake:latest"

    def __init__(self):
        self.texts = []

    def emotional_valence(self, text):
        return 0.2

    def summarize_page(self, title, url, visible_text, hz=None, mood=None):
        return f"summary:{title}:{round(hz or 0)}:{mood}"

    def empathetic_response(self, message, context=""):
        return f"empathy:{message}:{bool(context)}"

    def code_help(self, question, context=""):
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


def test_awake_keeper_run_once_updates_status_and_memory():
    memory = InMemoryHippocampusMemory()
    config = AwakeKeeperConfig(
        seed_path=Path("AGI Kennis.txt"),
        interval_min_seconds=0.01,
        interval_max_seconds=0.02,
        steps_per_tick=1,
        spike_steps_per_tick=1,
        model="fake:latest",
        ollama_base_url="http://fake",
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


def test_awake_keeper_chat_uses_code_help_for_programming_question():
    config = AwakeKeeperConfig(
        seed_path=Path("AGI Kennis.txt"),
        interval_min_seconds=0.01,
        interval_max_seconds=0.02,
        model="fake:latest",
        ollama_base_url="http://fake",
        chat_browser_enabled=False,
    )
    keeper = AwakeKeeper(config=config, browser_factory=FakeBrowser, ollama=FakeOllama())
    answer = asyncio.run(keeper.answer_question("Python code bug"))
    assert answer.startswith("code:")


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
