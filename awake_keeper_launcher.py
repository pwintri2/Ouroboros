"""Small desktop launcher for Resonant Ouroboros Fase 2.

This file intentionally stays dependency-free. It starts the Docker Compose
stack from a button, including the Flatpak VS Code host-Docker bridge when
plain `docker` is not visible in the current environment.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import queue
import shutil
import subprocess
import threading
import time
import webbrowser


PROJECT_DIR = Path(__file__).resolve().parent
COMPOSE_FILE = PROJECT_DIR / "docker-compose.ouroboros.yml"
PROJECT_NAME = "ouroboros-fase2"
DEFAULT_PORT = "7861"
DEFAULT_DASHBOARD_URL = f"http://localhost:{DEFAULT_PORT}"


@dataclass(frozen=True)
class LauncherCommand:
    args: list[str]
    env: dict[str, str]


def docker_prefix() -> list[str]:
    """Return the command prefix needed to reach Docker from this desktop."""

    if shutil.which("docker"):
        return []
    if shutil.which("flatpak-spawn"):
        return ["flatpak-spawn", "--host"]
    return []


def compose_command(*compose_args: str, port: str = DEFAULT_PORT) -> LauncherCommand:
    docker_args = [
        "docker",
        "compose",
        "-f",
        str(COMPOSE_FILE),
        "-p",
        PROJECT_NAME,
        *compose_args,
    ]
    env = os.environ.copy()
    env["OUROBOROS_GRADIO_PORT"] = port
    return LauncherCommand(args=[*docker_prefix(), *docker_args], env=env)


def run_command(command: LauncherCommand) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            command.args,
            cwd=PROJECT_DIR,
            env=command.env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
    except FileNotFoundError as exc:
        return 127, f"Command not found: {exc.filename}"
    return completed.returncode, completed.stdout.strip()


class AwakeKeeperLauncher:
    def __init__(self, root):
        import tkinter as tk
        from tkinter import ttk

        self.root = root
        self.tk = tk
        self.ttk = ttk
        self.port_var = tk.StringVar(value=DEFAULT_PORT)
        self.status_var = tk.StringVar(value="Ready. Click Start Fase 2.")
        self.output_queue: queue.Queue[str] = queue.Queue()

        root.title("Awake Keeper Launcher")
        root.geometry("680x440")
        root.minsize(580, 360)

        frame = ttk.Frame(root, padding=16)
        frame.pack(fill="both", expand=True)

        title = ttk.Label(frame, text="Resonant Ouroboros Fase 2", font=("Sans", 16, "bold"))
        title.pack(anchor="w")

        subtitle = ttk.Label(
            frame,
            text="Start the Docker Awake Keeper dashboard without using the terminal.",
        )
        subtitle.pack(anchor="w", pady=(2, 14))

        controls = ttk.Frame(frame)
        controls.pack(fill="x", pady=(0, 12))

        ttk.Label(controls, text="Dashboard port").pack(side="left")
        port_entry = ttk.Entry(controls, textvariable=self.port_var, width=8)
        port_entry.pack(side="left", padx=(8, 16))

        ttk.Button(controls, text="Start Fase 2", command=self.start_stack).pack(side="left", padx=4)
        ttk.Button(controls, text="Open Dashboard", command=self.open_dashboard).pack(side="left", padx=4)
        ttk.Button(controls, text="Status", command=self.check_status).pack(side="left", padx=4)
        ttk.Button(controls, text="Stop", command=self.stop_stack).pack(side="left", padx=4)

        status = ttk.Label(frame, textvariable=self.status_var)
        status.pack(anchor="w", pady=(0, 8))

        self.log = tk.Text(frame, height=16, wrap="word")
        self.log.pack(fill="both", expand=True)
        self.log.insert("end", "Launcher ready.\n")
        self.log.configure(state="disabled")

        root.after(150, self.drain_output_queue)

    def append_log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", f"{message.rstrip()}\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def set_status(self, message: str) -> None:
        self.root.after(0, lambda: self.status_var.set(message))

    def drain_output_queue(self) -> None:
        while True:
            try:
                message = self.output_queue.get_nowait()
            except queue.Empty:
                break
            self.append_log(message)
        self.root.after(150, self.drain_output_queue)

    def run_background(self, label: str, command: LauncherCommand, open_after: bool = False) -> None:
        self.set_status(f"{label}...")
        self.output_queue.put(f"$ {' '.join(command.args)}")

        def worker() -> None:
            started = time.monotonic()
            code, output = run_command(command)
            elapsed = time.monotonic() - started
            if output:
                self.output_queue.put(output)
            if code == 0:
                self.output_queue.put(f"{label} finished in {elapsed:.1f}s.")
                self.set_status(f"{label} complete.")
                if open_after:
                    self.root.after(0, self.open_dashboard)
            else:
                self.output_queue.put(f"{label} failed with exit code {code}.")
                self.set_status(f"{label} failed.")

        threading.Thread(target=worker, daemon=True).start()

    def start_stack(self) -> None:
        command = compose_command("up", "--build", "-d", port=self.port_var.get().strip() or DEFAULT_PORT)
        self.run_background("Starting Fase 2", command, open_after=True)

    def stop_stack(self) -> None:
        command = compose_command("stop", port=self.port_var.get().strip() or DEFAULT_PORT)
        self.run_background("Stopping Fase 2", command)

    def check_status(self) -> None:
        command = compose_command("ps", port=self.port_var.get().strip() or DEFAULT_PORT)
        self.run_background("Checking status", command)

    def open_dashboard(self) -> None:
        port = self.port_var.get().strip() or DEFAULT_PORT
        url = f"http://localhost:{port}"
        self.output_queue.put(f"Opening {url}")
        webbrowser.open(url)


def main() -> None:
    try:
        import tkinter as tk
    except ImportError as exc:
        raise SystemExit("Tkinter is not available on this system.") from exc

    root = tk.Tk()
    AwakeKeeperLauncher(root)
    root.mainloop()


if __name__ == "__main__":
    main()
