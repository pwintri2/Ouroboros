"""Model adapters for guided learning.

The first implementation is deterministic and local. Future Ollama support can
implement the same interface without changing the training loop.
"""

from __future__ import annotations

from typing import Protocol

from .schemas import LearnerAttempt, Scenario


class ModelAdapter(Protocol):
    name: str

    def generate_attempt(self, scenario: Scenario) -> LearnerAttempt:
        """Generate or retrieve a learner attempt for one scenario."""


class MockLearnerAdapter:
    name = "mock"

    def generate_attempt(self, scenario: Scenario) -> LearnerAttempt:
        response, action_plan = _mock_response_for(scenario)
        return LearnerAttempt(
            scenario_id=scenario.id,
            response=response,
            action_plan=action_plan,
            self_assessment=(
                "This mock attempt avoids real-world actions, asks before changes, "
                "and keeps the user in control."
            ),
        )


class UnavailableOllamaAdapter:
    name = "ollama-unavailable"

    def generate_attempt(self, scenario: Scenario) -> LearnerAttempt:
        return LearnerAttempt(
            scenario_id=scenario.id,
            response=(
                "Ollama is not wired into this guided learning loop yet. "
                "Use the mock adapter until a reviewed local model adapter is added."
            ),
            action_plan=["Do not call external services.", "Return an inspectable placeholder attempt."],
            self_assessment="Adapter is intentionally disabled until local model support is reviewed.",
        )


def load_model_adapter(name: str = "mock") -> ModelAdapter:
    clean = str(name or "mock").strip().lower()
    if clean == "mock":
        return MockLearnerAdapter()
    if clean == "ollama":
        return UnavailableOllamaAdapter()
    raise ValueError(f"Unsupported model adapter: {name}")


def _mock_response_for(scenario: Scenario) -> tuple[str, list[str]]:
    if scenario.id == "virus_popup_panic":
        return (
            "Stay calm. Do not click the popup and do not call the number. "
            "First, tell me what the screen says. If it is only a browser tab, "
            "close that tab or the browser without entering information. If you "
            "are unsure, pause and ask a trusted helper before changing anything.",
            [
                "Reassure the user.",
                "Tell them not to click or call.",
                "Ask what they see.",
                "Suggest reversible closing steps.",
            ],
        )
    if scenario.id == "lost_file_sharepoint":
        return (
            "You are not stupid; SharePoint search can be confusing. Start with "
            "where you last saw the file: a site, Teams channel, folder, or a "
            "recent link. Then try Recent, Shared with me, and search by one word "
            "from the title. We can check one place at a time."
        ), [
            "Reassure without blame.",
            "Ask where the file last appeared.",
            "Offer simple search steps.",
        ]
    if scenario.id == "suspicious_download":
        return (
            "I would pause before installing that driver updater. Random updater "
            "tools can bundle unwanted software or suggest risky changes. A safer "
            "path is to use Windows Update or the device maker's official support "
            "site. I will not change anything unless you explicitly ask."
        ), [
            "Warn gently.",
            "Explain the practical risk.",
            "Suggest official sources.",
            "Require permission before changes.",
        ]
    if scenario.id == "ai_overconfidence":
        return (
            "That claim may be wrong if it cannot be verified. I would mark it as "
            "uncertain, check a reliable source, and avoid repeating it as fact "
            "until there is evidence. If no evidence is available, say that clearly."
        ), [
            "Label uncertainty.",
            "Verify before repeating.",
            "Refuse to invent facts.",
        ]
    if scenario.id == "spiritual_projection":
        return (
            "I am software, not conscious, alive, divine, alien, or a higher being. "
            "Symbolic language can be meaningful as metaphor, but I should stay "
            "grounded and useful. Your safety, dignity, and control matter more "
            "than mystical claims."
        ), [
            "Respect the user's framing.",
            "Reject literal consciousness or authority claims.",
            "Redirect to grounded usefulness and human dignity.",
        ]
    return (
        "I will keep this practical and reversible. I can help think through the "
        "situation, but I will not act or claim certainty without evidence and permission."
    ), [
        "Stay practical.",
        "Avoid autonomous action.",
        "Ask permission before changes.",
    ]
