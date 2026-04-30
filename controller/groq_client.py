"""Compatibility shim for the removed Groq cloud escalator.

Ouroboros phase 1 is local-only. This class keeps legacy imports alive while
making it impossible for the backend-first agent loop to call Groq.
"""

from __future__ import annotations

import os
from typing import Any

try:
    from controller.provider_router import disabled_provider_status
except ImportError:
    from provider_router import disabled_provider_status


class GroqClient:
    def __init__(
        self,
        model: str = "llama-3.3-70b-versatile",
        base_url: str = "https://api.groq.com/openai/v1",
    ):
        self.model = model
        self.base_url = base_url
        self.api_key = os.getenv("GROQ_API_KEY")
        self.disabled = True

    def disabled_payload(self, model=None) -> dict[str, Any]:
        return disabled_provider_status("groq", model=model or self.model, transport="cloud_api")

    def status(self) -> dict[str, Any]:
        return self.disabled_payload()

    def chat(self, user_input, history=None, model=None, system_prompt=None):
        status = self.disabled_payload(model=model)
        return (
            f"CLOUD GROQ ERROR: [disabled_external_provider:groq] {status['message']} "
            "Geen cloud-escalatie uitgevoerd."
        )
