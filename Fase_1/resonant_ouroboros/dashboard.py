"""Gradio dashboard for the Fase 1 core."""

from __future__ import annotations

import os
from pathlib import Path

from .memory import create_memory_from_env
from .oscillator import HertzOscillator


def create_dashboard(
    oscillator: HertzOscillator | None = None,
    screenshot_path: str | Path = "/workspace/data/screenshots/current_browser_view.png",
):
    try:
        import gradio as gr  # type: ignore
    except ImportError as exc:
        raise RuntimeError("gradio is required for the dashboard; use Docker or install requirements.txt") from exc

    oscillator = oscillator or HertzOscillator()
    screenshot_path = Path(screenshot_path)

    def waveform_data():
        import pandas as pd  # type: ignore

        hz = oscillator.sample()
        behavior = oscillator.behavior_for_hz(hz)
        wave = oscillator.waveform(samples=96, step_seconds=0.35)
        data = pd.DataFrame({"sample": list(range(len(wave))), "hz": wave})
        return data, f"{hz:.3f} Hz | {behavior.mood} | curiosity {behavior.curiosity:.2f}"

    def browser_image():
        return str(screenshot_path) if screenshot_path.exists() else None

    def memory_rows(query: str):
        memory = create_memory_from_env(fallback_in_memory=True)
        if not query.strip():
            count = memory.count()
            return [[f"{count} records", "", "", "", ""]]
        results = memory.search(query, n_results=10)
        rows = []
        for row in results:
            metadata = row.get("metadata", {})
            rows.append(
                [
                    row.get("id", ""),
                    metadata.get("current_hz", ""),
                    metadata.get("vibration_mood", ""),
                    metadata.get("field_cluster_id", ""),
                    row.get("document", "")[:300],
                ]
            )
        return rows

    with gr.Blocks(title="Resonant Ouroboros Proto 1.1 Fase 1") as demo:
        gr.Markdown("# Resonant Ouroboros Proto 1.1 - Fase 1")
        with gr.Row():
            with gr.Column(scale=1):
                hz_plot = gr.LinePlot(x="sample", y="hz", label="Live Hz waveform")
                hz_label = gr.Textbox(label="Current vibration", interactive=False)
            with gr.Column(scale=1):
                browser = gr.Image(label="Current browser view", interactive=False)
        query = gr.Textbox(label="11D memory explorer query", value="AGI")
        memory = gr.Dataframe(
            headers=["id", "current_hz", "vibration_mood", "field_cluster_id", "document"],
            label="11D Hippocampus records",
        )
        refresh = gr.Button("Refresh")

        refresh.click(waveform_data, outputs=[hz_plot, hz_label])
        refresh.click(browser_image, outputs=[browser])
        refresh.click(memory_rows, inputs=[query], outputs=[memory])
        query.submit(memory_rows, inputs=[query], outputs=[memory])
        demo.load(waveform_data, outputs=[hz_plot, hz_label])
        demo.load(browser_image, outputs=[browser])
        demo.load(memory_rows, inputs=[query], outputs=[memory])

    return demo


def launch_dashboard() -> None:
    demo = create_dashboard()
    demo.launch(
        server_name=os.getenv("GRADIO_SERVER_NAME", "0.0.0.0"),
        server_port=int(os.getenv("GRADIO_SERVER_PORT", "7860")),
        show_api=False,
    )
