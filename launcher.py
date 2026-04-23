#!/usr/bin/env python3
"""
WintripAI Phase 11 Launcher

Starts the full local nervous system from one macOS entrypoint:
- Docker Desktop best-effort bootstrap for the quarantine sandbox.
- FastAPI backend with 11D Consciousness Memory and Entanglement Daemon.
- Local static Skull UI server, opened automatically in the default browser.
"""

from __future__ import annotations

import atexit
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional


PROJECT_ROOT = Path(__file__).resolve().parent
BACKEND_HOST = "127.0.0.1"
BACKEND_PORT = 8000
UI_HOST = "127.0.0.1"
UI_PORT = 8765
UI_FILE = "skull_ui.html"
LOG_DIR = PROJECT_ROOT / "logs"
BACKEND_LOG = LOG_DIR / "phase11_backend.log"
UI_LOG = LOG_DIR / "phase11_launcher.log"

backend_process: Optional[subprocess.Popen] = None
ui_server: Optional[ThreadingHTTPServer] = None


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:
        return


def _python_bin() -> str:
    candidates = [
        PROJECT_ROOT / ".venv" / "bin" / "python",
        PROJECT_ROOT.parent / ".venv" / "bin" / "python",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return sys.executable


def _append_log(message: str) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    with UI_LOG.open("a", encoding="utf-8") as handle:
        handle.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")


def _url_ok(url: str, timeout: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return 200 <= response.status < 500
    except Exception:
        return False


def wait_for_backend(timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    health_url = f"http://{BACKEND_HOST}:{BACKEND_PORT}/health"
    while time.time() < deadline:
        if _url_ok(health_url):
            return True
        time.sleep(0.35)
    return False


def ensure_docker_best_effort(timeout: float = 20.0) -> None:
    """Start Docker Desktop if available. Failure is non-fatal; backend reports sandbox state."""
    try:
        subprocess.run(["docker", "info"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
        _append_log("Docker daemon already reachable.")
        return
    except Exception:
        pass

    if sys.platform == "darwin":
        try:
            subprocess.Popen(["open", "-ga", "Docker"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            _append_log("Requested Docker Desktop startup.")
        except Exception as exc:
            _append_log(f"Docker Desktop startup skipped: {exc}")

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            result = subprocess.run(
                ["docker", "info"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2,
            )
            if result.returncode == 0:
                _append_log("Docker daemon reachable after startup.")
                return
        except Exception:
            pass
        time.sleep(1.0)
    _append_log("Docker daemon not reachable yet; continuing with graceful sandbox fallback.")


def start_backend() -> subprocess.Popen | None:
    global backend_process

    if _url_ok(f"http://{BACKEND_HOST}:{BACKEND_PORT}/health"):
        _append_log("Backend already running; launcher will reuse it.")
        return None

    LOG_DIR.mkdir(exist_ok=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT)
    env.setdefault("WINTRIP_11D_DB_PATH", str(PROJECT_ROOT / "controller" / "wintrip_brain"))

    log_handle = BACKEND_LOG.open("a", encoding="utf-8")
    backend_process = subprocess.Popen(
        [
            _python_bin(),
            "-m",
            "uvicorn",
            "controller.main:app",
            "--host",
            BACKEND_HOST,
            "--port",
            str(BACKEND_PORT),
            "--log-level",
            "warning",
        ],
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    _append_log(f"Backend spawned with PID {backend_process.pid}.")
    return backend_process


def start_ui_server() -> ThreadingHTTPServer:
    global ui_server
    handler = partial(QuietHandler, directory=str(PROJECT_ROOT))
    ui_server = ThreadingHTTPServer((UI_HOST, UI_PORT), handler)
    return ui_server


def shutdown() -> None:
    if ui_server:
        ui_server.shutdown()
    if backend_process and backend_process.poll() is None:
        try:
            os.killpg(os.getpgid(backend_process.pid), signal.SIGTERM)
            backend_process.wait(timeout=5)
        except Exception:
            backend_process.kill()
    _append_log("Launcher shutdown complete.")


def main() -> int:
    atexit.register(shutdown)
    if not (PROJECT_ROOT / UI_FILE).exists():
        print(f"Missing UI file: {PROJECT_ROOT / UI_FILE}")
        return 1

    print("WintripAI Phase 11 launcher starting...")
    ensure_docker_best_effort()
    start_backend()
    backend_ready = wait_for_backend()

    server = start_ui_server()
    ui_url = f"http://{UI_HOST}:{UI_PORT}/{UI_FILE}"
    webbrowser.open(ui_url)

    print(f"Skull UI:  {ui_url}")
    print(f"Backend:   http://{BACKEND_HOST}:{BACKEND_PORT} ({'online' if backend_ready else 'starting'})")
    print(f"Logs:      {BACKEND_LOG}")
    print("Press Ctrl+C to stop WintripAI.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping WintripAI...")
    finally:
        shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
