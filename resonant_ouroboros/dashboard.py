"""Gradio dashboard for the Fase 2 Awake Keeper."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path

from .awake_keeper import AwakeKeeper, AwakeKeeperConfig
from .memory import InMemoryHippocampusMemory, create_memory_from_env
from .oscillator import HertzOscillator


@dataclass(frozen=True)
class HzSample:
    sampled_at: datetime
    hz: float


class HzHistory:
    """Rolling 60-second Hertz history for the dashboard plot."""

    def __init__(self, window_seconds: float = 60.0):
        self.window_seconds = window_seconds
        self._samples: deque[HzSample] = deque()

    def add(self, hz: float, sampled_at: datetime | None = None) -> None:
        now = sampled_at or datetime.now(timezone.utc)
        self._samples.append(HzSample(now, hz))
        self._prune(now)

    def rows(self, now: datetime | None = None) -> list[dict[str, float]]:
        moment = now or datetime.now(timezone.utc)
        self._prune(moment)
        rows = []
        for sample in self._samples:
            seconds_ago = round((moment - sample.sampled_at).total_seconds(), 3)
            rows.append({"seconds_ago": seconds_ago, "hz": sample.hz})
        return rows

    def _prune(self, now: datetime) -> None:
        while self._samples and (now - self._samples[0].sampled_at).total_seconds() > self.window_seconds:
            self._samples.popleft()


def create_dashboard(
    oscillator: HertzOscillator | None = None,
    screenshot_path: str | Path = "/workspace/data/screenshots/current_browser_view.png",
):
    try:
        import gradio as gr  # type: ignore
    except ImportError as exc:
        raise RuntimeError("gradio is required for the dashboard; use Docker or install requirements.txt") from exc

    oscillator = oscillator or HertzOscillator()
    history = HzHistory()
    config = AwakeKeeperConfig.from_env()

    def dashboard_memory():
        try:
            return create_memory_from_env(fallback_in_memory=True)
        except Exception:
            return InMemoryHippocampusMemory()

    keeper = AwakeKeeper(config=config, oscillator=oscillator, memory_factory=dashboard_memory)

    def refresh_status():
        state = oscillator.modulation_state()
        history.add(state.current_hz)
        status = keeper.status().as_lines()
        hz_label = f"{state.current_hz:.2f} Hz | {state.mood} | curiosity {state.curiosity_factor:.2f}"
        image = str(screenshot_path) if Path(screenshot_path).exists() else None
        return status, history.rows(), hz_label, image

    def start_awake():
        message = keeper.start()
        status, rows, label, image = refresh_status()
        return f"{message}\n\n{status}", rows, label, image

    def stop_awake():
        message = keeper.stop()
        status, rows, label, image = refresh_status()
        return f"{message}\n\n{status}", rows, label, image

    def chat(message, chat_history):
        answer = keeper.answer_question_sync(message)
        chat_history = chat_history or []
        chat_history.append((message, answer))
        status, rows, label, image = refresh_status()
        return "", chat_history, status, rows, label, image

    with gr.Blocks(title="Resonant Ouroboros Awake Keeper") as demo:
        gr.Markdown("# Resonant Ouroboros Awake Keeper")
        with gr.Row():
            start_button = gr.Button("Start Awake Mode", variant="primary")
            stop_button = gr.Button("Stop Awake Mode")
            refresh_button = gr.Button("Refresh")
        hz_label = gr.Textbox(label="Hertz state", interactive=False)
        status_box = gr.Textbox(label="Background loop status", lines=12, interactive=False)
        hz_table = gr.Dataframe(headers=["seconds_ago", "hz"], label="Hz history", interactive=False)
        screenshot = gr.Image(label="Latest browser view", interactive=False)
        chatbot = gr.Chatbot(label="Live Ollama + Browser Chat")
        chat_input = gr.Textbox(label="Ask Awake Keeper")
        chat_button = gr.Button("Send")

        start_button.click(start_awake, outputs=[status_box, hz_table, hz_label, screenshot])
        stop_button.click(stop_awake, outputs=[status_box, hz_table, hz_label, screenshot])
        refresh_button.click(refresh_status, outputs=[status_box, hz_table, hz_label, screenshot])
        chat_button.click(
            chat,
            inputs=[chat_input, chatbot],
            outputs=[chat_input, chatbot, status_box, hz_table, hz_label, screenshot],
        )
        chat_input.submit(
            chat,
            inputs=[chat_input, chatbot],
            outputs=[chat_input, chatbot, status_box, hz_table, hz_label, screenshot],
        )
        demo.load(refresh_status, outputs=[status_box, hz_table, hz_label, screenshot])
    return demo


def launch_dashboard() -> None:
    demo = create_dashboard()
    demo.launch(
        server_name=os.getenv("GRADIO_SERVER_NAME", "0.0.0.0"),
        server_port=int(os.getenv("GRADIO_SERVER_PORT", "7860")),
        share=False,
    )
