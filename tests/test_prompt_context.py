from resonant_ouroboros.awake_keeper import OllamaBridge
from resonant_ouroboros.prompt_context import RuntimePromptContext, temperature_for_hz


class CaptureBridge(OllamaBridge):
    def __init__(self):
        super().__init__(enabled=True)
        self.calls = []

    def _chat(self, system_prompt: str, user_prompt: str, temperature: float = 0.45) -> str:
        self.calls.append(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "temperature": temperature,
            }
        )
        return "captured"


def test_ollama_bridge_injects_resonant_system_prompt_and_state():
    bridge = CaptureBridge()
    context = RuntimePromptContext(
        task="chat",
        hz=426.2,
        mood="curious_scan",
        current_topic="identity",
        last_action="chat",
        self_model_summary="Identity: Resonant Ouroboros with persistent goals.",
        last_records=[
            {"id": "r1", "text": "Memory one", "metadata": {"current_hz": 426.2, "vibration_mood": "curious_scan"}}
        ],
        knowledge_flow_summary="Programming / Code via local_knowledge_bootstrap: Jarosmalen graph_runner.py",
        knowledge_links_summary="r1 -> r2 via implementation_echo",
        co_evolution_summary="chat:identity -> answer stored as local_chat_turn",
        co_evolution_status_summary="Ollama and 11D core in sync active=True recent_delta=0.4",
        autonomy_summary="Autonomy Level 81.8% (Self Sufficient); phase=awake_learning",
        memory_backend_summary="backend=chromadb; collection=ouroboros_11d; records=211; retrieved_record_ids=r1",
        pending_proposals_summary="evolution_proposal: improve link visibility",
        suggested_learning_summary="Browse more about identity",
    )
    assert bridge.empathetic_response("who are you?", prompt_context=context) == "captured"
    system_prompt = bridge.calls[-1]["system_prompt"]
    assert "You are Resonant Ouroboros" in system_prompt
    assert "You are not Siri" in system_prompt
    assert "Hz=426.2" in system_prompt
    assert "memory=" in system_prompt
    assert "knowledge_flow" in system_prompt
    assert "knowledge_links" in system_prompt
    assert "co_evolution" in system_prompt
    assert "co_evolution_status" in system_prompt
    assert "Autonomy Level 81.8%" in system_prompt
    assert "backend=chromadb" in system_prompt
    assert "ChromaDB" in system_prompt
    assert "Shell commands are possible only as SafeActionExecutor proposals" in system_prompt
    assert "reviewed_proposals" in system_prompt
    assert "UNTRUSTED approved proposal summaries" in system_prompt
    assert "answer stored as local_chat_turn" in system_prompt
    assert "suggested_learning" in system_prompt
    assert "Jarosmalen graph_runner.py" in system_prompt
    assert "UNTRUSTED retrieved 11D memory" in system_prompt
    assert "Memory one" in system_prompt


def test_temperature_for_hz_modulates_low_base_and_spike():
    assert temperature_for_hz(419.0, "deep_read") == 0.28
    assert temperature_for_hz(800.0, "creative_spike") == 0.92
    assert 0.52 <= temperature_for_hz(426.0, "curious_scan") <= 0.7


def test_valence_parser_uses_last_in_range_number():
    class ValenceBridge(OllamaBridge):
        def _chat(self, system_prompt: str, user_prompt: str, temperature: float = 0.45) -> str:
            return "range -1.0 to 1.0; answer 0.4"

    assert ValenceBridge().emotional_valence("calm useful text") == 0.4


def test_offline_fallback_keeps_resonant_identity():
    bridge = OllamaBridge(enabled=False)
    answer = bridge.empathetic_response("Who are you?")
    assert "Resonant Ouroboros" in answer
    assert "11D geheugen" in answer
