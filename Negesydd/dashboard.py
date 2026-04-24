"""Dashboard server and UI for Negesydd."""

from __future__ import annotations

from typing import Any, Dict, Optional
import shutil
import time
from pathlib import Path

from flask import Flask, jsonify, request
from flask_cors import CORS

from messenger import MessengerCore


class DashboardServer:
    """Flask dashboard server exposing Negesydd state and controls."""

    def __init__(self, messenger: Optional[MessengerCore] = None, host: str = "127.0.0.1", port: int = 8765):
        """Initialize the dashboard server."""
        self.messenger = messenger or MessengerCore()
        self.host = host
        self.port = port
        self.started_at = time.time()
        self.app = Flask(__name__)
        CORS(self.app)
        self._configure_routes()

    def _configure_routes(self) -> None:
        @self.app.get("/")
        def index():
            return self.render_index()

        @self.app.get("/api/status")
        def status():
            return jsonify(self.get_status())

        @self.app.get("/api/options")
        def options():
            return jsonify(self.get_options())

        @self.app.get("/api/components")
        def components():
            return jsonify(self.get_components())

        @self.app.get("/api/agents")
        def agents():
            return jsonify([agent.to_dict() for agent in self.messenger.agent_pool.list_all_agents()])

        @self.app.get("/api/timeline")
        def timeline():
            return jsonify(self.messenger.sync_execution_timeline())

        @self.app.get("/api/messages")
        def messages():
            return jsonify([message.to_json() for message in self.messenger.get_message_history()])

        @self.app.post("/api/input")
        def input_prompt():
            payload: Dict[str, Any] = request.get_json(silent=True) or {}
            task_id = self.messenger.queue_prompt(str(payload.get("prompt", "")))
            return jsonify({"task_id": task_id})

        @self.app.post("/api/discover")
        def discover():
            agents = self.messenger.discover_agents()
            return jsonify({"agents": [agent.to_dict() for agent in agents]})

    def get_status(self) -> Dict[str, Any]:
        """Return dashboard status payload."""
        agents = self.messenger.agent_pool.list_all_agents()
        return {
            "status": "running",
            "uptime_seconds": time.time() - self.started_at,
            "agents_count": len(agents),
            "messages_count": len(self.messenger.get_message_history()),
            "queue_size": self.messenger.message_queue.size(),
            "timeline_count": len(self.messenger.execution_timeline),
        }

    def get_options(self) -> Dict[str, Any]:
        """Return CLI and dashboard options."""
        return {
            "commands": [
                {"name": "--dashboard", "value": "Start this dashboard"},
                {"name": "--plan", "value": "Run a YAML or JSON plan file"},
                {"name": "--prompt", "value": "Run an inline prompt"},
                {"name": "--agents", "value": "Select agents, comma-separated"},
                {"name": "--discover-agents", "value": "List detected agents"},
                {"name": "--check-system", "value": "Check dependencies and local services"},
                {"name": "--list-llms", "value": "List Ollama models"},
                {"name": "--dry-run", "value": "Validate without executing"},
                {"name": "--loglevel", "value": "DEBUG, INFO, WARNING, or ERROR"},
                {"name": "--port", "value": "Dashboard port"},
            ],
            "endpoints": [
                "/api/status",
                "/api/options",
                "/api/components",
                "/api/agents",
                "/api/timeline",
                "/api/messages",
                "/api/input",
                "/api/discover",
            ],
        }

    def get_components(self) -> Dict[str, Any]:
        """Return Gemini, Codex, and agent visibility."""
        agents = self.messenger.agent_pool.list_all_agents()
        gemini = self._detect_gemini_cli()
        return {
            "gemini_cli": gemini,
            "codex_vscode": {
                "name": "Codex in VSCode",
                "available": self.messenger.detect_codex_vscode(),
            },
            "agents": [agent.to_dict() for agent in agents],
        }

    def _detect_gemini_cli(self) -> Dict[str, Any]:
        """Detect Gemini CLI from PATH or common npm bundle locations."""
        path_gemini = shutil.which("gemini")
        if path_gemini:
            return {
                "name": "Gemini CLI",
                "available": True,
                "path": path_gemini,
                "command": path_gemini,
                "source": "PATH",
            }

        known_paths = [
            Path.home() / ".nvm/versions/node/v22.22.2/lib/node_modules/@google/gemini-cli/bundle/gemini.js",
        ]
        for candidate in known_paths:
            if candidate.exists():
                node = shutil.which("node") or "node"
                return {
                    "name": "Gemini CLI",
                    "available": True,
                    "path": str(candidate),
                    "command": f"{node} {candidate}",
                    "source": "npm bundle",
                }

        return {
            "name": "Gemini CLI",
            "available": False,
            "path": None,
            "command": "gemini",
            "source": "not found",
        }

    def render_index(self) -> str:
        """Return the dashboard HTML page."""
        return DASHBOARD_HTML

    def start(self, debug: bool = False) -> None:
        """Start the Flask development server."""
        self.app.run(host=self.host, port=self.port, debug=debug)

    def test_client(self):
        """Return a Flask test client."""
        return self.app.test_client()


DASHBOARD_HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Negesydd Dashboard</title>
  <style>
    :root {
      --page: #111111;
      --panel: #1b1b19;
      --panel-2: #242421;
      --line: #3a3933;
      --text: #f3f0e8;
      --muted: #afa99a;
      --teal: #3ec6b8;
      --amber: #d8a441;
      --red: #df6b5f;
      --green: #75c66a;
      --code: #080807;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--page);
      color: var(--text);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: 0;
    }
    button, input, textarea, select { font: inherit; }
    .shell {
      min-height: 100vh;
      display: grid;
      grid-template-rows: 58px 1fr;
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 0 18px;
      border-bottom: 1px solid var(--line);
      background: #171715;
    }
    h1 {
      margin: 0;
      font-size: 18px;
      font-weight: 700;
    }
    .meta {
      display: flex;
      gap: 8px;
      align-items: center;
      flex-wrap: wrap;
      justify-content: flex-end;
    }
    .badge {
      border: 1px solid var(--line);
      background: var(--panel-2);
      border-radius: 8px;
      padding: 5px 8px;
      color: var(--muted);
      font-size: 12px;
      white-space: nowrap;
    }
    .ok { color: var(--green); }
    .warn { color: var(--amber); }
    .bad { color: var(--red); }
    .layout {
      display: grid;
      grid-template-columns: 260px minmax(420px, 1fr) 340px;
      gap: 12px;
      padding: 12px;
      min-height: calc(100vh - 58px);
    }
    aside, main, section {
      min-width: 0;
    }
    .stack {
      display: grid;
      gap: 12px;
      align-content: start;
    }
    .panel {
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 8px;
      overflow: hidden;
    }
    .panel h2 {
      margin: 0;
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      font-size: 13px;
      text-transform: uppercase;
      color: var(--muted);
      font-weight: 700;
    }
    .panel-body {
      padding: 10px 12px;
    }
    .toolbar {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 8px;
      align-items: end;
    }
    textarea {
      min-height: 76px;
      resize: vertical;
      width: 100%;
      background: #10100f;
      color: var(--text);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
      outline: none;
    }
    textarea:focus, select:focus {
      border-color: var(--teal);
    }
    button {
      height: 38px;
      border: 1px solid #4a4942;
      color: var(--text);
      background: #2c2b27;
      border-radius: 8px;
      padding: 0 12px;
      cursor: pointer;
    }
    button:hover { border-color: var(--teal); }
    .primary {
      background: var(--teal);
      border-color: var(--teal);
      color: #07110f;
      font-weight: 700;
    }
    .row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      padding: 7px 0;
      border-bottom: 1px solid rgba(58, 57, 51, .65);
      font-size: 13px;
    }
    .row:last-child { border-bottom: 0; }
    .label { color: var(--muted); }
    .value { color: var(--text); text-align: right; overflow-wrap: anywhere; }
    .grid-2 {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
    }
    .terminal {
      min-height: 260px;
      max-height: 38vh;
      overflow: auto;
      background: var(--code);
      color: #d7f7ed;
      font-family: "Fira Code", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 12px;
      line-height: 1.45;
      padding: 12px;
      white-space: pre-wrap;
      border-top: 1px solid var(--line);
    }
    .list {
      display: grid;
      gap: 8px;
    }
    .item {
      border: 1px solid var(--line);
      background: var(--panel-2);
      border-radius: 8px;
      padding: 9px;
      display: grid;
      gap: 4px;
      font-size: 13px;
    }
    .item-title {
      display: flex;
      justify-content: space-between;
      gap: 8px;
      font-weight: 700;
    }
    .pill {
      display: inline-flex;
      align-items: center;
      border-radius: 8px;
      padding: 2px 7px;
      border: 1px solid var(--line);
      color: var(--muted);
      font-size: 11px;
      white-space: nowrap;
    }
    .tabs {
      display: flex;
      gap: 4px;
      padding: 8px;
      border-bottom: 1px solid var(--line);
      background: #171715;
    }
    .tab {
      height: 30px;
      padding: 0 10px;
      font-size: 12px;
    }
    .tab.active {
      background: var(--teal);
      color: #07110f;
      border-color: var(--teal);
      font-weight: 700;
    }
    .hidden { display: none; }
    @media (max-width: 1100px) {
      .layout { grid-template-columns: 220px 1fr; }
      .right { grid-column: 1 / -1; grid-template-columns: 1fr 1fr; }
    }
    @media (max-width: 760px) {
      header { align-items: flex-start; height: auto; padding: 12px; flex-direction: column; }
      .layout { grid-template-columns: 1fr; }
      .right { grid-template-columns: 1fr; }
      .grid-2 { grid-template-columns: 1fr; }
      .toolbar { grid-template-columns: 1fr; }
      button { width: 100%; }
    }
  </style>
</head>
<body>
  <div class="shell">
    <header>
      <h1>Negesydd Dashboard</h1>
      <div class="meta">
        <span class="badge" id="statusBadge">status</span>
        <span class="badge" id="agentsBadge">agents</span>
        <span class="badge" id="messagesBadge">messages</span>
        <button id="refreshBtn">Refresh</button>
      </div>
    </header>
    <div class="layout">
      <aside class="stack">
        <div class="panel">
          <h2>Components</h2>
          <div class="panel-body list" id="components"></div>
        </div>
        <div class="panel">
          <h2>Options</h2>
          <div class="panel-body list" id="options"></div>
        </div>
      </aside>
      <main class="stack">
        <div class="panel">
          <h2>Prompt</h2>
          <div class="panel-body">
            <div class="toolbar">
              <textarea id="promptInput" placeholder="Send a prompt to Negesydd"></textarea>
              <button class="primary" id="sendBtn">Send</button>
            </div>
          </div>
        </div>
        <div class="grid-2">
          <div class="panel">
            <h2>Gemini CLI</h2>
            <div class="panel-body" id="geminiDetails"></div>
            <div class="terminal" id="geminiTerminal">// Gemini CLI stream</div>
          </div>
          <div class="panel">
            <h2>Codex in VSCode</h2>
            <div class="panel-body" id="codexDetails"></div>
            <div class="terminal" id="codexTerminal">// Codex activity stream</div>
          </div>
        </div>
        <div class="panel">
          <h2>Messages</h2>
          <div class="terminal" id="messages"></div>
        </div>
      </main>
      <section class="stack right">
        <div class="panel">
          <h2>Agents</h2>
          <div class="panel-body">
            <button id="discoverBtn">Discover</button>
          </div>
          <div class="panel-body list" id="agents"></div>
        </div>
        <div class="panel">
          <h2>Timeline</h2>
          <div class="tabs">
            <button class="tab active" data-tab="timeline">Events</button>
            <button class="tab" data-tab="stats">Stats</button>
          </div>
          <div class="panel-body list" id="timeline"></div>
          <div class="panel-body hidden" id="stats"></div>
        </div>
      </section>
    </div>
  </div>
  <script>
    const $ = (id) => document.getElementById(id);
    const state = { status: {}, components: {}, agents: [], timeline: [], messages: [], options: {} };

    function classFor(value) {
      return value ? 'ok' : 'warn';
    }
    function row(label, value, cls = '') {
      return `<div class="row"><span class="label">${label}</span><span class="value ${cls}">${value}</span></div>`;
    }
    function item(title, meta, body = '') {
      return `<div class="item"><div class="item-title"><span>${title}</span><span class="pill">${meta}</span></div>${body}</div>`;
    }
    async function getJSON(url, options) {
      const response = await fetch(url, options);
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
      return await response.json();
    }
    async function refresh() {
      const [status, components, agents, timeline, messages, options] = await Promise.all([
        getJSON('/api/status'),
        getJSON('/api/components'),
        getJSON('/api/agents'),
        getJSON('/api/timeline'),
        getJSON('/api/messages'),
        getJSON('/api/options'),
      ]);
      Object.assign(state, { status, components, agents, timeline, messages, options });
      render();
    }
    function render() {
      $('statusBadge').textContent = `running ${Math.round(state.status.uptime_seconds || 0)}s`;
      $('agentsBadge').textContent = `${state.status.agents_count || 0} agents`;
      $('messagesBadge').textContent = `${state.status.messages_count || 0} messages`;

      const gemini = state.components.gemini_cli || {};
      const codex = state.components.codex_vscode || {};
      $('components').innerHTML = [
        item('Gemini CLI', gemini.available ? 'available' : 'not found', row('Path', gemini.path || '-', classFor(gemini.available))),
        item('Codex in VSCode', codex.available ? 'visible' : 'not detected', row('Bridge', codex.available ? 'ready' : 'fallback', classFor(codex.available))),
      ].join('');
      $('geminiDetails').innerHTML = row('Available', gemini.available ? 'yes' : 'no', classFor(gemini.available)) + row('Source', gemini.source || '-') + row('Path', gemini.path || '-') + row('Command', gemini.command || '-');
      $('codexDetails').innerHTML = row('Detected', codex.available ? 'yes' : 'no', classFor(codex.available)) + row('Mode', codex.available ? 'VSCode' : 'outbox fallback');

      $('options').innerHTML = (state.options.commands || []).map(opt => item(opt.name, opt.value)).join('');
      $('agents').innerHTML = (state.agents || []).length
        ? state.agents.map(agent => item(agent.name || agent.agent_id, agent.status, row('ID', agent.agent_id) + row('Capabilities', (agent.capability_tags || []).join(', ') || '-'))).join('')
        : item('No agents discovered', 'idle', row('Action', 'press Discover'));
      $('timeline').innerHTML = (state.timeline || []).length
        ? state.timeline.slice().reverse().map(event => item(event.event_type, new Date(event.timestamp).toLocaleTimeString(), `<pre>${JSON.stringify(event.payload, null, 2)}</pre>`)).join('')
        : item('No events yet', 'waiting');
      $('messages').textContent = (state.messages || []).map(msg => {
        try { return JSON.stringify(JSON.parse(msg), null, 2); } catch { return msg; }
      }).join('\n\n') || '// No messages routed yet';
      $('geminiTerminal').textContent = gemini.available ? `// Gemini CLI detected via ${gemini.source}\n// ${gemini.command}\n// Awaiting routed prompts` : '// Gemini CLI not found';
      $('codexTerminal').textContent = codex.available ? '// Codex detected in VSCode\n// Awaiting bridge activity' : '// Codex not detected\n// Requests will use fallback outbox';
      $('stats').innerHTML = row('Queue', state.status.queue_size || 0) + row('Timeline', state.status.timeline_count || 0) + row('Messages', state.status.messages_count || 0);
    }
    async function sendPrompt() {
      const prompt = $('promptInput').value.trim();
      if (!prompt) return;
      const result = await getJSON('/api/input', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt })
      });
      $('promptInput').value = '';
      $('messages').textContent = `Queued ${result.task_id}\n` + $('messages').textContent;
      await refresh();
    }
    document.querySelectorAll('.tab').forEach(tab => {
      tab.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        $('timeline').classList.toggle('hidden', tab.dataset.tab !== 'timeline');
        $('stats').classList.toggle('hidden', tab.dataset.tab !== 'stats');
      });
    });
    $('refreshBtn').addEventListener('click', refresh);
    $('discoverBtn').addEventListener('click', async () => { await getJSON('/api/discover', { method: 'POST' }); await refresh(); });
    $('sendBtn').addEventListener('click', sendPrompt);
    $('promptInput').addEventListener('keydown', event => {
      if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') sendPrompt();
    });
    refresh().catch(error => {
      $('messages').textContent = `Dashboard error: ${error.message}`;
    });
    setInterval(() => refresh().catch(() => {}), 3000);
  </script>
</body>
</html>"""
