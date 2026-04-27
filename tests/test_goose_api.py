from pathlib import Path

from fastapi.testclient import TestClient

from resonant_ouroboros.awake_keeper import AwakeKeeper, AwakeKeeperConfig
from resonant_ouroboros.browser import BrowserAction, BrowserSnapshot
from resonant_ouroboros.dashboard import DashboardRuntime, create_api_app
from resonant_ouroboros.memory import InMemoryHippocampusMemory
from resonant_ouroboros.oscillator import HertzOscillator
from resonant_ouroboros.safe_executor import SafeActionExecutor
from resonant_ouroboros.vision import VisionObservation


class FakeOllama:
    model = "fake:latest"
    last_error = None
    last_model_used = "fake:latest"

    def emotional_valence(self, text, prompt_context=None):
        return 0.1

    def summarize_page(self, title, url, visible_text, hz=None, mood=None, prompt_context=None):
        return f"summary:{title}:{mood}"

    def empathetic_response(self, message, context="", prompt_context=None):
        return f"empathy:{message}:{bool(context)}"

    def code_help(self, question, context="", prompt_context=None):
        return f"code:{question}:{bool(context)}"


class FakeBrowser:
    allow_private_hosts = False

    def propose_next_action(self, topic, snapshot, behavior):
        if snapshot is None:
            return BrowserAction("navigate", "https://example.com/goose", "unit navigation")
        return BrowserAction("scroll", "down", "unit scroll")

    async def navigate(self, target, behavior):
        return self.snapshot(target)

    async def scroll(self, behavior, direction="down", steps=2):
        return self.snapshot("https://example.com/goose/scrolled")

    async def close(self):
        return None

    def snapshot(self, target):
        return BrowserSnapshot(
            url=target,
            title="Goose API Unit Page",
            visible_text="Safe local API test content with enough visible text for storage. " * 12,
            screenshot_path=None,
            vision=VisionObservation("unit vision", "unit", None),
            links=["https://example.com/goose/next"],
            quality_score=0.95,
            quality_reason="accepted",
        )


def make_client(tmp_path):
    oscillator = HertzOscillator(spike_probability=0.0)
    memory = InMemoryHippocampusMemory()
    config = AwakeKeeperConfig(
        seed_path=Path("AGI Kennis.txt"),
        interval_min_seconds=0.01,
        interval_max_seconds=0.02,
        steps_per_tick=1,
        spike_steps_per_tick=1,
        model="fake:latest",
        ollama_base_url="http://fake",
        chat_browser_enabled=False,
        self_model_path=tmp_path / "self_model.json",
        evolution_events_path=tmp_path / "evolution.jsonl",
    )
    keeper = AwakeKeeper(
        config=config,
        oscillator=oscillator,
        memory_factory=lambda: memory,
        browser_factory=FakeBrowser,
        ollama=FakeOllama(),
    )
    runtime = DashboardRuntime(
        keeper=keeper,
        oscillator=oscillator,
        safe_executor=SafeActionExecutor(path=tmp_path / "actions.json", docker_bin="true"),
    )
    return TestClient(create_api_app(runtime=runtime)), memory


def test_status_endpoint_exposes_safe_mode_and_controls_contract(tmp_path):
    client, _memory = make_client(tmp_path)
    response = client.get("/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["safe_mode"] is True
    assert payload["api"]["chat"] == "/chat"
    assert payload["api"]["control"] == "/control"
    assert payload["api"]["self_model"] == "/self-model"
    assert payload["api"]["actions"] == "/actions"
    assert payload["api"]["evolution"] == "/evolution"
    assert "co_evolution" in payload
    assert payload["memory"]["backend"]["backend"] == "memory"
    assert payload["sandbox"]["status_label"]
    assert payload["self_model"]["identity"]["name"] == "Resonant Ouroboros"
    assert payload["poll_seconds"] == 1.5


def test_chat_endpoint_returns_answer_with_hz_and_mood(tmp_path):
    client, _memory = make_client(tmp_path)
    response = client.post("/chat", json={"message": "hello awake keeper"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["answer"].startswith("empathy:hello awake keeper")
    assert payload["safe_mode"] is True
    assert payload["hz"] >= 418.0
    assert payload["mood"] in {"deep_read", "curious_scan", "creative_spike"}
    assert payload["suggested_learning_actions"]

    evolution = client.get("/evolution", params={"limit": 5})
    assert evolution.status_code == 200
    assert evolution.json()["events"]


def test_control_endpoint_can_force_spike_and_clear_queue(tmp_path):
    client, _memory = make_client(tmp_path)
    spike = client.post("/control", json={"command": "creative_spike"})
    assert spike.status_code == 200
    spike_payload = spike.json()
    assert spike_payload["ok"] is True
    assert spike_payload["status"]["vibration_mood"] == "creative_spike"
    assert spike_payload["status"]["last_action"] == "creative_spike_forced"

    cleared = client.post("/control", json={"command": "clear_queue"})
    assert cleared.status_code == 200
    clear_payload = cleared.json()
    assert clear_payload["status"]["learning_queue_size"] == 0
    assert clear_payload["status"]["last_action"] == "queue_cleared"


def test_manual_paeu_control_stores_memory_and_memory_endpoint_reads_it(tmp_path):
    client, memory = make_client(tmp_path)
    manual = client.post("/control", json={"command": "manual_paeu_step", "topic": "goose ui"})
    assert manual.status_code == 200
    assert memory.count() == 1

    response = client.get("/memory", params={"query": "goose", "limit": 5})
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["count"] == 1
    assert payload["rows"]


def test_self_model_endpoint_and_action_approval_flow(tmp_path):
    client, memory = make_client(tmp_path)
    self_model = client.get("/self-model")
    assert self_model.status_code == 200
    assert self_model.json()["summary"]["identity"]["name"] == "Resonant Ouroboros"

    proposal = client.post(
        "/actions",
        json={
            "kind": "apply_code_review",
            "label": "Approve & Review Code",
            "summary": "Review code from chat",
            "payload": {"code": "print('safe')", "language": "python"},
        },
    )
    assert proposal.status_code == 200
    body = proposal.json()
    assert body["proposal"]["status"] == "pending"
    assert body["approval_token"].startswith("apr_")

    action_id = body["proposal"]["id"]
    approved = client.post(
        f"/actions/{action_id}/approve",
        json={"approval_token": body["approval_token"], "approved_by": "test"},
    )
    assert approved.status_code == 200
    assert approved.json()["proposal"]["status"] == "executed"
    assert approved.json()["proposal"]["result"]["mode"] == "review_only"
    assert memory.count() >= 2
