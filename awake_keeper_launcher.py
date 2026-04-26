"""Small desktop launcher for Resonant Ouroboros Fase 2.

This file intentionally stays dependency-free. It starts the Docker Compose
stack from a button, including the Flatpak VS Code host-Docker bridge when
plain `docker` is not visible in the current environment.
"""

from __future__ import annotations

from dataclasses import dataclass
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import queue
import shutil
import subprocess
import threading
import time
from urllib.parse import parse_qs, urlparse
import webbrowser


PROJECT_DIR = Path(__file__).resolve().parent
COMPOSE_FILE = PROJECT_DIR / "docker-compose.ouroboros.yml"
PROJECT_NAME = "ouroboros-fase2"
DEFAULT_PORT = "7861"
DEFAULT_DASHBOARD_URL = f"http://localhost:{DEFAULT_PORT}"
LAUNCHER_HOST = "127.0.0.1"
LAUNCHER_PORT = 8791


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


def sanitize_dashboard_port(value: str) -> str:
    candidate = (value or "").strip()
    if candidate.isdigit() and 1 <= int(candidate) <= 65535:
        return candidate
    return DEFAULT_PORT


class BrowserLauncherState:
    def __init__(self, port: str = DEFAULT_PORT):
        self.dashboard_port = sanitize_dashboard_port(port)
        self.status = "Ready. Click Start Fase 2."
        self.logs: list[str] = ["Browser launcher ready."]
        self.command_running = False
        self.lock = threading.RLock()

    def add_log(self, message: str) -> None:
        with self.lock:
            self.logs.extend(line for line in message.rstrip().splitlines() if line.strip())
            self.logs = self.logs[-200:]

    def set_status(self, message: str) -> None:
        with self.lock:
            self.status = message

    def snapshot(self) -> tuple[str, str, list[str], bool]:
        with self.lock:
            return self.dashboard_port, self.status, list(self.logs), self.command_running

    def run_background(self, label: str, command: LauncherCommand, open_after: bool = False) -> None:
        with self.lock:
            if self.command_running:
                self.logs.append("Another Docker command is still running.")
                return
            self.command_running = True
            self.status = f"{label}..."
        self.add_log(f"$ {' '.join(command.args)}")

        def worker() -> None:
            started = time.monotonic()
            code, output = run_command(command)
            elapsed = time.monotonic() - started
            if output:
                self.add_log(output)
            with self.lock:
                self.command_running = False
                if code == 0:
                    self.status = f"{label} complete."
                    self.logs.append(f"{label} finished in {elapsed:.1f}s.")
                else:
                    self.status = f"{label} failed."
                    self.logs.append(f"{label} failed with exit code {code}.")
            if code == 0 and open_after:
                webbrowser.open(f"http://localhost:{self.dashboard_port}")

        threading.Thread(target=worker, daemon=True).start()


def render_browser_page(state: BrowserLauncherState) -> str:
    port, status, logs, command_running = state.snapshot()
    escaped_status = html.escape(status)
    escaped_port = html.escape(port)
    escaped_logs = html.escape("\n".join(logs[-80:]))
    busy = "Command running..." if command_running else "Idle"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="3">
  <title>Awake Keeper Launcher</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 860px; margin: 32px auto; padding: 0 18px; background: #f7f8fb; color: #172033; }}
    h1 {{ margin-bottom: 6px; }}
    .panel {{ background: white; border: 1px solid #d8deea; border-radius: 8px; padding: 16px; margin: 14px 0; }}
    label {{ font-weight: 600; margin-right: 8px; }}
    input {{ padding: 8px; border: 1px solid #b8c2d6; border-radius: 6px; width: 90px; }}
    button, a.button {{ display: inline-block; padding: 9px 12px; border: 1px solid #315b9f; border-radius: 6px; background: #315b9f; color: white; text-decoration: none; cursor: pointer; margin: 4px 4px 4px 0; font-size: 14px; }}
    button.secondary, a.secondary {{ background: white; color: #315b9f; }}
    pre {{ white-space: pre-wrap; background: #101827; color: #e8edf8; padding: 14px; border-radius: 8px; min-height: 180px; }}
    .status {{ font-weight: 700; }}
  </style>
</head>
<body>
  <h1>Resonant Ouroboros Fase 2</h1>
  <p>Start the Docker Awake Keeper dashboard without using the terminal.</p>
  <div class="panel">
    <p class="status">Status: {escaped_status}</p>
    <p>Launcher: {html.escape(busy)}</p>
    <form method="post" action="/start">
      <label for="port">Dashboard port</label>
      <input id="port" name="port" value="{escaped_port}">
      <button type="submit">Start Fase 2</button>
      <button class="secondary" formaction="/status">Status</button>
      <button class="secondary" formaction="/stop">Stop</button>
      <button class="secondary" formaction="/quit">Quit Launcher</button>
      <a class="button secondary" href="/dashboard">Open Dashboard</a>
    </form>
  </div>
  <div class="panel">
    <h2>Log</h2>
    <pre>{escaped_logs}</pre>
  </div>
</body>
</html>"""


class BrowserLauncherHandler(BaseHTTPRequestHandler):
    state: BrowserLauncherState

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/dashboard":
            port, _, _, _ = self.state.snapshot()
            self.send_response(303)
            self.send_header("Location", f"http://localhost:{port}")
            self.end_headers()
            return
        self.respond_html(render_browser_page(self.state))

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", "0") or "0")
        payload = self.rfile.read(length).decode("utf-8", errors="ignore")
        fields = parse_qs(payload)
        port = sanitize_dashboard_port(fields.get("port", [self.state.dashboard_port])[0])
        self.state.dashboard_port = port

        if parsed.path == "/start":
            command = compose_command("up", "--build", "-d", port=port)
            self.state.run_background("Starting Fase 2", command, open_after=True)
        elif parsed.path == "/stop":
            command = compose_command("stop", port=port)
            self.state.run_background("Stopping Fase 2", command)
        elif parsed.path == "/status":
            command = compose_command("ps", port=port)
            self.state.run_background("Checking status", command)
        elif parsed.path == "/quit":
            self.state.set_status("Launcher shutting down.")
            self.state.add_log("Launcher shutting down.")
            threading.Thread(target=self.server.shutdown, daemon=True).start()

        self.send_response(303)
        self.send_header("Location", "/")
        self.end_headers()

    def respond_html(self, body: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args) -> None:
        return


def launch_browser_ui() -> None:
    state = BrowserLauncherState()

    class Handler(BrowserLauncherHandler):
        pass

    Handler.state = state
    try:
        server = ThreadingHTTPServer((LAUNCHER_HOST, LAUNCHER_PORT), Handler)
    except OSError:
        server = ThreadingHTTPServer((LAUNCHER_HOST, 0), Handler)

    host, port = server.server_address
    url = f"http://{host}:{port}"
    state.add_log("Tkinter is not available; using browser launcher.")
    state.add_log(f"Launcher UI: {url}")
    webbrowser.open(url)
    try:
        server.serve_forever()
    finally:
        server.server_close()


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
    except ImportError:
        launch_browser_ui()
        return

    root = tk.Tk()
    AwakeKeeperLauncher(root)
    root.mainloop()


if __name__ == "__main__":
    main()
