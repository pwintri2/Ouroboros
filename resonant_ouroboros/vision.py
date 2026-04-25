"""Screenshot to vision-analysis adapter."""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VisionObservation:
    summary: str
    provider: str
    screenshot_path: str | None


class VisionAnalyzer:
    """Analyze browser screenshots through a configured LLM vision endpoint.

    Fase 1 keeps this safe and explicit: no cloud call is made unless the user
    provides OPENAI_API_KEY and enables VISION_PROVIDER=openai. Without that,
    screenshot capture still occurs and the summary records a deterministic
    placeholder for memory provenance.
    """

    def analyze(self, screenshot_path: str | None, visible_text: str) -> VisionObservation:
        provider = os.getenv("VISION_PROVIDER", "local_stub").strip().lower()
        if provider == "openai" and os.getenv("OPENAI_API_KEY") and screenshot_path:
            return self._analyze_openai(Path(screenshot_path), visible_text)
        return VisionObservation(
            summary=_local_summary(visible_text, screenshot_path),
            provider="local_stub",
            screenshot_path=screenshot_path,
        )

    def _analyze_openai(self, screenshot_path: Path, visible_text: str) -> VisionObservation:
        try:
            from openai import OpenAI  # type: ignore
        except ImportError:
            return VisionObservation(
                summary=_local_summary(visible_text, str(screenshot_path)),
                provider="local_stub_openai_missing",
                screenshot_path=str(screenshot_path),
            )

        image_b64 = base64.b64encode(screenshot_path.read_bytes()).decode("ascii")
        client = OpenAI()
        response = client.responses.create(
            model=os.getenv("VISION_MODEL", "gpt-4.1-mini"),
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "Summarize the visible browser screenshot for a safe "
                                "learning-memory record. Focus on page structure, "
                                "topic, and useful knowledge signals."
                            ),
                        },
                        {
                            "type": "input_image",
                            "image_url": f"data:image/png;base64,{image_b64}",
                        },
                        {"type": "input_text", "text": visible_text[:2000]},
                    ],
                }
            ],
        )
        return VisionObservation(
            summary=response.output_text,
            provider="openai",
            screenshot_path=str(screenshot_path),
        )


def _local_summary(visible_text: str, screenshot_path: str | None) -> str:
    words = visible_text.split()
    head = " ".join(words[:48])
    path_note = f"screenshot captured at {screenshot_path}" if screenshot_path else "no screenshot captured"
    if not head:
        return f"Local vision placeholder: blank or unreadable page; {path_note}."
    return f"Local vision placeholder from visible text: {head}; {path_note}."
