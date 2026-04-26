"""LangGraph wiring for the PAEU loop."""

from __future__ import annotations

from typing import Any, TypedDict


class PAEUState(TypedDict, total=False):
    topic: str
    current_hz: float
    curiosity_factor: float
    vibration_mood: str
    browser_event: str
    action: str
    safety: str
    signal_fidelity: float
    stored_record_id: str


def build_langgraph_paeu():
    """Build a minimal LangGraph StateGraph for PAEU orchestration."""

    try:
        from langgraph.graph import StateGraph  # type: ignore
    except ImportError as exc:
        raise RuntimeError("langgraph is required for the PAEU graph. Use the Docker environment or install requirements.txt.") from exc

    graph = StateGraph(PAEUState)

    def perceive(state: PAEUState) -> PAEUState:
        return {"browser_event": f"browser_event_for:{state.get('topic', '')}", **state}

    def act(state: PAEUState) -> PAEUState:
        curiosity = float(state.get("curiosity_factor", 1.0))
        action = "navigate_or_link_jump" if curiosity > 1.25 else "scroll_and_read"
        return {**state, "action": action}

    def evaluate(state: PAEUState) -> PAEUState:
        return {**state, "safety": "safety_gate_active", "signal_fidelity": min(1.0, float(state.get("signal_fidelity", 0.5)))}

    def update(state: PAEUState) -> PAEUState:
        return {**state, "stored_record_id": state.get("stored_record_id", "external_paeu_loop")}

    graph.add_node("perceive", perceive)
    graph.add_node("act", act)
    graph.add_node("evaluate", evaluate)
    graph.add_node("update", update)
    graph.set_entry_point("perceive")
    graph.add_edge("perceive", "act")
    graph.add_edge("act", "evaluate")
    graph.add_edge("evaluate", "update")
    return graph.compile()


def graph_available() -> bool:
    try:
        build_langgraph_paeu()
    except Exception:
        return False
    return True
