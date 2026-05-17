"""OpenAI model choices exposed in Cockpit and Roo integration."""

from __future__ import annotations

import os


OPENAI_DEFAULT_MODEL = "gpt-5.4-mini"
OPENAI_API_MODELS: tuple[str, ...] = (
    "gpt-5.4-mini",
    "gpt-5.4-nano",
    "gpt-5.4",
    "gpt-5.5",
    "gpt-5-mini",
    "gpt-5-nano",
    "gpt-5",
    "gpt-4.1-mini",
    "gpt-4.1-nano",
    "gpt-4.1",
    "gpt-4o-mini",
    "gpt-4o",
    "o4-mini",
    "o3",
)


def openai_default_model() -> str:
    configured = os.getenv("WINTRIP_OPENAI_DEFAULT_MODEL", "").strip()
    return configured or OPENAI_DEFAULT_MODEL


def openai_roo_default_model() -> str:
    configured = os.getenv("WINTRIP_ROO_OPENAI_MODEL", "").strip()
    return configured or openai_default_model()


def openai_api_model_choices() -> list[str]:
    default = openai_default_model()
    choices = [default]
    for model in OPENAI_API_MODELS:
        if model not in choices:
            choices.append(model)
    return choices
