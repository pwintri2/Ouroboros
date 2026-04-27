"""Screenshot to vision-analysis adapter."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class VisionObservation:
    summary: str
    provider: str
    screenshot_path: str | None


class VisionAnalyzer:
    """Analyze browser screenshots through an explicitly configured provider."""

    def analyze(self, screenshot_path: str | None, visible_text: str) -> VisionObservation:
        provider = os.getenv("VISION_PROVIDER", "local_stub").strip().lower()
        if provider == "openai" and os.getenv("OPENAI_API_KEY"):
            return self._analyze_openai(screenshot_path, visible_text)
        return self._local_summary(screenshot_path, visible_text)

    def _analyze_openai(self, screenshot_path: str | None, visible_text: str) -> VisionObservation:
        try:
            from openai import OpenAI  # type: ignore
            import base64
        except ImportError:
            return VisionObservation(
                summary="Local vision placeholder: OpenAI client unavailable.",
                provider="local_stub_openai_missing",
                screenshot_path=screenshot_path,
            )

        if not screenshot_path or not Path(screenshot_path).exists():
            return self._local_summary(screenshot_path, visible_text)

        image_b64 = base64.b64encode(Path(screenshot_path).read_bytes()).decode("ascii")
        client = OpenAI()
        response = client.responses.create(
            model=os.getenv("VISION_MODEL", "gpt-4.1-mini"),
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": "Summarize the visible browser screenshot for a safe learning-memory record. Focus on page structure, topic, and useful knowledge signals.",
                        },
                        {
                            "type": "input_image",
                            "image_url": f"data:image/png;base64,{image_b64}",
                        },
                    ],
                }
            ],
        )
        return VisionObservation(
            summary=response.output_text,
            provider="openai",
            screenshot_path=screenshot_path,
        )

    def _local_summary(self, screenshot_path: str | None, visible_text: str) -> VisionObservation:
        words = " ".join((visible_text or "").split()).split()
        path_note = f"screenshot captured at {screenshot_path}" if screenshot_path else "no screenshot captured"
        if not words:
            summary = f"Local vision placeholder: blank or unreadable page; {path_note}."
        else:
            summary = f"Local vision placeholder from visible text: {' '.join(words[:40])}. {path_note}."
        return VisionObservation(summary=summary, provider="local_stub", screenshot_path=screenshot_path)
