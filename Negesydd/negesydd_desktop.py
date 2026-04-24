#!/usr/bin/env python3
"""Native desktop dashboard for Negesydd."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QAction, QFont, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from dashboard import DashboardServer


APP_DIR = Path(__file__).resolve().parent
LOGO_PATH = APP_DIR / "assets" / "ouroboros-logo.png"


class DesktopDashboard(QMainWindow):
    """Native Qt window for monitoring and controlling Negesydd."""

    def __init__(self) -> None:
        super().__init__()
        self.server = DashboardServer()
        self.setWindowTitle("Negesydd Dashboard")
        if LOGO_PATH.exists():
            self.setWindowIcon(QIcon(str(LOGO_PATH)))
        self.resize(1280, 820)
        self._build_ui()
        self._wire_actions()
        self.refresh()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(3000)

    def _build_ui(self) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        header = QHBoxLayout()
        self.logo = QLabel()
        if LOGO_PATH.exists():
            self.logo.setPixmap(QPixmap(str(LOGO_PATH)).scaled(38, 38, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.logo.setFixedSize(44, 44)
        self.title = QLabel("Negesydd Dashboard")
        self.title.setFont(QFont("Sans Serif", 17, QFont.Weight.Bold))
        self.status = QLabel("Starting")
        self.status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        header.addWidget(self.logo)
        header.addWidget(self.title, 1)
        header.addWidget(self.status, 1)
        layout.addLayout(header)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._left_panel())
        splitter.addWidget(self._center_panel())
        splitter.addWidget(self._right_panel())
        splitter.setSizes([260, 620, 360])
        layout.addWidget(splitter, 1)

        self.setCentralWidget(root)
        self.setStyleSheet(STYLESHEET)

        refresh_action = QAction("Refresh", self)
        refresh_action.triggered.connect(self.refresh)
        self.menuBar().addAction(refresh_action)

    def _left_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        self.components = QListWidget()
        self.options = QListWidget()
        layout.addWidget(section("Components", self.components), 2)
        layout.addWidget(section("Options", self.options), 3)
        return panel

    def _center_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        prompt_row = QHBoxLayout()
        self.prompt = QLineEdit()
        self.prompt.setPlaceholderText("Send a prompt to Negesydd")
        self.send = QPushButton("Send")
        prompt_row.addWidget(self.prompt, 1)
        prompt_row.addWidget(self.send)
        layout.addLayout(prompt_row)

        grid = QGridLayout()
        self.gemini = QTextEdit()
        self.codex = QTextEdit()
        self.messages = QTextEdit()
        for editor in (self.gemini, self.codex, self.messages):
            editor.setReadOnly(True)
            editor.setFont(QFont("Monospace", 10))
        grid.addWidget(section("Gemini CLI", self.gemini), 0, 0)
        grid.addWidget(section("Codex in VSCode", self.codex), 0, 1)
        grid.addWidget(section("Messages", self.messages), 1, 0, 1, 2)
        layout.addLayout(grid, 1)
        return panel

    def _right_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        row = QHBoxLayout()
        self.discover = QPushButton("Discover")
        self.refresh_button = QPushButton("Refresh")
        row.addWidget(self.discover)
        row.addWidget(self.refresh_button)
        layout.addLayout(row)
        self.agents = QListWidget()
        self.timeline = QListWidget()
        layout.addWidget(section("Agents", self.agents), 2)
        layout.addWidget(section("Timeline", self.timeline), 3)
        return panel

    def _wire_actions(self) -> None:
        self.refresh_button.clicked.connect(self.refresh)
        self.discover.clicked.connect(self.discover_agents)
        self.send.clicked.connect(self.send_prompt)
        self.prompt.returnPressed.connect(self.send_prompt)

    def refresh(self) -> None:
        try:
            status = self.server.get_status()
            components = self.server.get_components()
            options = self.server.get_options()
            agents = self.server.messenger.agent_pool.list_all_agents()
            timeline = self.server.messenger.sync_execution_timeline()
            messages = self.server.messenger.get_message_history()
        except Exception as exc:
            self.status.setText(f"Error: {exc}")
            return

        self.status.setText(
            f"Running | {status['agents_count']} agents | {status['messages_count']} messages | queue {status['queue_size']}"
        )

        self.components.clear()
        gemini = components["gemini_cli"]
        codex = components["codex_vscode"]
        add_item(self.components, "Gemini CLI", availability(gemini["available"]), gemini.get("command") or "-")
        add_item(self.components, "Codex in VSCode", availability(codex["available"]), "VSCode bridge" if codex["available"] else "fallback")

        self.options.clear()
        for option in options["commands"]:
            add_item(self.options, option["name"], option["value"])

        self.agents.clear()
        if agents:
            for agent in agents:
                add_item(self.agents, agent.name, agent.status.value, ", ".join(agent.capability_tags) or agent.agent_id)
        else:
            add_item(self.agents, "No agents discovered", "press Discover")

        self.timeline.clear()
        for event in reversed(timeline[-30:]):
            add_item(self.timeline, event["event_type"], event["timestamp"], json.dumps(event["payload"], default=str))

        self.gemini.setPlainText(
            f"Gemini CLI: {availability(gemini['available'])}\nSource: {gemini.get('source')}\nPath: {gemini.get('path')}\nCommand: {gemini.get('command')}"
        )
        self.codex.setPlainText(
            f"Codex in VSCode: {availability(codex['available'])}\nMode: {'VSCode detected' if codex['available'] else 'outbox fallback'}"
        )
        self.messages.setPlainText(
            "\n\n".join(message.to_json() for message in messages) or "No messages routed yet."
        )

    def discover_agents(self) -> None:
        self.server.messenger.discover_agents()
        self.refresh()

    def send_prompt(self) -> None:
        text = self.prompt.text().strip()
        if not text:
            return
        try:
            task_id = self.server.messenger.queue_prompt(text)
        except Exception as exc:
            QMessageBox.critical(self, "Negesydd", f"Prompt could not be queued:\n{exc}")
            return
        self.prompt.clear()
        self.status.setText(f"Queued {task_id}")
        self.refresh()


def section(title: str, child: QWidget) -> QFrame:
    frame = QFrame()
    frame.setObjectName("section")
    layout = QVBoxLayout(frame)
    label = QLabel(title)
    label.setObjectName("sectionTitle")
    layout.addWidget(label)
    layout.addWidget(child, 1)
    return frame


def add_item(widget: QListWidget, title: str, meta: str, detail: str = "") -> None:
    item = QListWidgetItem(f"{title}\n  {meta}{' | ' + detail if detail else ''}")
    widget.addItem(item)


def availability(value: bool) -> str:
    return "available" if value else "not detected"


STYLESHEET = """
QMainWindow, QWidget { background: #111111; color: #f3f0e8; }
QMenuBar { background: #171715; color: #f3f0e8; }
QLineEdit, QTextEdit, QListWidget {
    background: #080807;
    border: 1px solid #3a3933;
    border-radius: 8px;
    color: #f3f0e8;
    padding: 8px;
}
QPushButton {
    background: #2c2b27;
    border: 1px solid #4a4942;
    border-radius: 8px;
    color: #f3f0e8;
    padding: 8px 12px;
}
QPushButton:hover { border-color: #3ec6b8; }
QFrame#section {
    background: #1b1b19;
    border: 1px solid #3a3933;
    border-radius: 8px;
}
QLabel#sectionTitle {
    color: #afa99a;
    font-weight: 700;
    padding: 8px;
}
"""


def main() -> int:
    app = QApplication(sys.argv)
    window = DesktopDashboard()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
