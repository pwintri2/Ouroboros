#!/usr/bin/env python3
"""
WintripAI Launcher
Start: cd /home/pwintri2/WintripAI && python3 launcher.py
"""

import subprocess, sys, os, signal, time

WINTRIP_ROOT = os.path.dirname(os.path.abspath(__file__))
VENV_PYTHON = os.path.join(WINTRIP_ROOT, ".venv", "bin", "python")
if not os.path.exists(VENV_PYTHON):
    VENV_PYTHON = sys.executable
BACKEND_PORT = 8000
LAUNCHER_PORT = 9000

try:
    import uvicorn
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
except ImportError:
    print("Installeer: pip install fastapi uvicorn")
    sys.exit(1)

app = FastAPI()
server_process = None

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/server/start")
def start():
    global server_process
    if server_process and server_process.poll() is None:
        return {"status": "already_running", "pid": server_process.pid}
    server_process = subprocess.Popen(
        [
            VENV_PYTHON, "-m", "uvicorn",
            "controller.main:app",
            "--host", "0.0.0.0",
            "--port", str(BACKEND_PORT),
            "--reload"
        ],
        cwd=WINTRIP_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    time.sleep(1.5)  # even wachten tot de server echt luistert
    if server_process.poll() is not None:
        err = server_process.stderr.read().decode()
        return {"status": "crashed", "error": err}
    return {"status": "started", "pid": server_process.pid}

@app.post("/server/stop")
def stop():
    global server_process
    if server_process and server_process.poll() is None:
        os.kill(server_process.pid, signal.SIGTERM)
        server_process.wait()
        return {"status": "stopped"}
    return {"status": "not_running"}

@app.get("/server/status")
def status():
    running = server_process is not None and server_process.poll() is None
    return {"running": running, "pid": server_process.pid if running else None}

if __name__ == "__main__":
    print(f"WintripAI Launcher → http://localhost:{LAUNCHER_PORT}")
    print(f"Backend wordt gestart op    → http://localhost:{BACKEND_PORT}")
    uvicorn.run(app, host="127.0.0.1", port=LAUNCHER_PORT, log_level="warning")
