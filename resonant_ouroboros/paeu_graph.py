"""LangGraph wiring for the PAEU loop."""

from __future__ import annotations

from typing import Any, TypedDict


class PAEUState(TypedDict, total=False):
    topic: str
    current_hz: float
    vibration_mood: str
    perceived: str
    action: str
    safety: str
    stored_record_id: str


def build_langgraph_paeu():
    """Build a minimal LangGraph StateGraph for PAEU orchestration.

    The executable browser work lives in PAEULoop. This graph provides the
    explicit LangGraph toolkit layer requested for Fase 1 and can be extended
    with richer nodes without changing the core safety and memory contracts.
    """

    try:
        from langgraph.graph import END, StateGraph  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "langgraph is required for the PAEU graph. Use the Docker environment "
            "or install requirements.txt."
        ) from exc

    graph = StateGraph(PAEUState)

    def perceive(state: PAEUState) -> PAEUState:
        state["perceived"] = f"browser_event_for:{state.get('topic', '')}"
        return state

    def act(state: PAEUState) -> PAEUState:
        state["action"] = "frequency_driven_browser_action"
        return state

    def evaluate(state: PAEUState) -> PAEUState:
        state["safety"] = "safety_gate_active"
        return state

    def update(state: PAEUState) -> PAEUState:
        state["stored_record_id"] = state.get("stored_record_id", "external_paeu_loop")
        return state

    graph.add_node("perceive", perceive)
    graph.add_node("act", act)
    graph.add_node("evaluate", evaluate)
    graph.add_node("update", update)
    graph.set_entry_point("perceive")
    graph.add_edge("perceive", "act")
    graph.add_edge("act", "evaluate")
    graph.add_edge("evaluate", "update")
    graph.add_edge("update", END)
    return graph.compile()


def graph_available() -> bool:
    try:
        build_langgraph_paeu()
    except RuntimeError:
        return False
    return True
