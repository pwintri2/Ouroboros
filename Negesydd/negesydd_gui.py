#!/usr/bin/env python3
import sys
import subprocess
import threading
import queue
import json
import webbrowser
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import os
import pty
import select
import signal

PORT = 8765
PROC = None
MASTER_FD = None
CLIENTS = []

HTML_CONTENT = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Negesydd App</title>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&family=Fira+Code:wght@400;500&display=swap');
        
        :root {
            --bg: #0f172a;
            --glass-bg: rgba(30, 41, 59, 0.7);
            --border: rgba(255, 255, 255, 0.1);
            --accent1: #3b82f6;
            --accent2: #8b5cf6;
            --text: #f8fafc;
            --term-bg: #020617;
            --term-text: #a5b4fc;
            --user-text: #34d399;
        }

        body {
            margin: 0;
            padding: 0;
            font-family: 'Inter', sans-serif;
            background: linear-gradient(135deg, #020617 0%, #1e1b4b 100%);
            color: var(--text);
            height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
        }

        .app-container {
            width: 95%;
            max-width: 1200px;
            height: 90vh;
            background: var(--glass-bg);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border: 1px solid var(--border);
            border-radius: 24px;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5), 0 0 60px rgba(139, 92, 246, 0.15);
            display: flex;
            flex-direction: column;
            overflow: hidden;
            animation: fadeIn 0.6s cubic-bezier(0.16, 1, 0.3, 1);
        }

        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(30px) scale(0.97); }
            to { opacity: 1; transform: translateY(0) scale(1); }
        }

        .header {
            padding: 20px 30px;
            border-bottom: 1px solid var(--border);
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: rgba(15, 23, 42, 0.4);
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            z-index: 10;
        }

        .brand {
            display: flex;
            align-items: center;
            gap: 16px;
        }

        .brand-dot {
            width: 14px;
            height: 14px;
            background: linear-gradient(135deg, var(--accent1), var(--accent2));
            border-radius: 50%;
            box-shadow: 0 0 12px var(--accent1);
            animation: pulse 2s infinite alternate;
        }

        @keyframes pulse {
            from { box-shadow: 0 0 6px var(--accent1); }
            to { box-shadow: 0 0 18px var(--accent2); }
        }

        .brand h1 {
            margin: 0;
            font-size: 1.4rem;
            font-weight: 600;
            letter-spacing: 0.5px;
            background: linear-gradient(to right, #60a5fa, #c084fc);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .status {
            font-size: 0.9rem;
            font-weight: 600;
            color: #10b981;
            display: flex;
            align-items: center;
            gap: 8px;
            background: rgba(16, 185, 129, 0.1);
            padding: 6px 14px;
            border-radius: 20px;
            border: 1px solid rgba(16, 185, 129, 0.2);
        }

        .terminal-container {
            flex: 1;
            background: var(--term-bg);
            padding: 30px;
            overflow-y: auto;
            font-family: 'Fira Code', monospace;
            font-size: 0.95rem;
            line-height: 1.6;
            color: var(--term-text);
            white-space: pre-wrap;
            word-wrap: break-word;
        }

        .terminal-container::-webkit-scrollbar {
            width: 10px;
        }

        .terminal-container::-webkit-scrollbar-track {
            background: transparent;
        }

        .terminal-container::-webkit-scrollbar-thumb {
            background: rgba(255, 255, 255, 0.1);
            border-radius: 5px;
        }

        .terminal-container::-webkit-scrollbar-thumb:hover {
            background: rgba(255, 255, 255, 0.2);
        }

        .input-area {
            padding: 24px 30px;
            background: rgba(15, 23, 42, 0.7);
            border-top: 1px solid var(--border);
            z-index: 10;
        }

        .input-form {
            display: flex;
            gap: 16px;
            position: relative;
        }

        .input-field {
            flex: 1;
            background: rgba(2, 6, 23, 0.7);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 16px 24px;
            color: white;
            font-family: 'Inter', sans-serif;
            font-size: 1.05rem;
            outline: none;
            transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
            box-shadow: inset 0 2px 4px rgba(0,0,0,0.2);
        }

        .input-field:focus {
            border-color: var(--accent2);
            background: rgba(2, 6, 23, 0.9);
            box-shadow: 0 0 0 3px rgba(139, 92, 246, 0.25), inset 0 2px 4px rgba(0,0,0,0.2);
        }

        .input-field::placeholder {
            color: #64748b;
        }

        .submit-btn {
            background: linear-gradient(135deg, var(--accent1), var(--accent2));
            color: white;
            border: none;
            border-radius: 16px;
            padding: 0 32px;
            font-weight: 600;
            font-size: 1.05rem;
            cursor: pointer;
            transition: all 0.3s cubic-bezier(0.16, 1, 0.3, 1);
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 4px 15px rgba(139, 92, 246, 0.3);
        }

        .submit-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 25px rgba(139, 92, 246, 0.4);
            filter: brightness(1.1);
        }

        .submit-btn:active {
            transform: translateY(1px);
            box-shadow: 0 2px 10px rgba(139, 92, 246, 0.3);
        }
        
        .user-line {
            color: var(--user-text);
            font-weight: 500;
        }
    </style>
</head>
<body>

    <div class="app-container">
        <div class="header">
            <div class="brand">
                <div class="brand-dot"></div>
                <h1>Negesydd GUI</h1>
            </div>
            <div class="status">● Linked to Goose</div>
        </div>
        
        <div class="terminal-container" id="terminal"><span style="color: #64748b;">// Negesydd Router + Goose Standalone UI
// Waiting for agent output...

</span></div>
        
        <div class="input-area">
            <form class="input-form" id="form">
                <input type="text" class="input-field" id="cmd-input" placeholder="Type a message to send to the agent..." autocomplete="off">
                <button type="submit" class="submit-btn">Send ➔</button>
            </form>
        </div>
    </div>

    <script>
        const terminal = document.getElementById('terminal');
        const form = document.getElementById('form');
        const input = document.getElementById('cmd-input');
        
        let textNode = document.createTextNode('');
        terminal.appendChild(textNode);
        
        const evtSource = new EventSource('/stream');
        
        const stripAnsi = (str) => {
            return str.replace(/[\\u001b\\u009b][[\\]()#;?]*(?:(?:(?:[a-zA-Z\\d]*(?:;[a-zA-Z\\d]*)*)?\\u0007)|(?:(?:\\d{1,4}(?:;\\d{0,4})*)?[\\dA-PRZcf-ntqry=><~]))/g, '');
        };
        
        evtSource.onmessage = function(event) {
            try {
                const data = JSON.parse(event.data);
                const cleanText = stripAnsi(data.text);
                textNode.nodeValue += cleanText;
                terminal.scrollTop = terminal.scrollHeight;
            } catch(e) {
                console.error(e);
            }
        };

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const msg = input.value;
            if(!msg) return;
            
            // Add user message to terminal
            const userSpan = document.createElement('span');
            userSpan.className = 'user-line';
            userSpan.textContent = "\n> " + msg + "\n";
            terminal.appendChild(userSpan);
            
            // Re-create text node for future system output
            textNode = document.createTextNode('');
            terminal.appendChild(textNode);
            terminal.scrollTop = terminal.scrollHeight;
            
            input.value = '';
            
            await fetch('/input', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: msg + '\n' })
            });
        });
        
        input.focus();
    </script>
</body>
</html>
"""

class RequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML_CONTENT.encode('utf-8'))
            
        elif self.path == '/stream':
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Connection', 'keep-alive')
            self.end_headers()
            
            q = queue.Queue()
            CLIENTS.append(q)
            try:
                while True:
                    chunk = q.get()
                    if chunk is None:
                        break
                    payload = json.dumps({"text": chunk}, ensure_ascii=False)
                    self.wfile.write(f"data: {payload}\n\n".encode('utf-8'))
                    self.wfile.flush()
            except Exception:
                pass
            finally:
                if q in CLIENTS:
                    CLIENTS.remove(q)
        else:
            # Silently ignore all other requests (favicon, extension probes, etc.)
            self.send_response(200)
            self.end_headers()

    def do_POST(self):
        if self.path == '/input':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            text = data.get('text', '')
            if MASTER_FD is not None:
                try:
                    os.write(MASTER_FD, text.encode('utf-8'))
                except OSError as e:
                    print("Error writing to PTY:", e)
            self.send_response(200)
            self.end_headers()

def broadcast(text):
    for q in CLIENTS:
        q.put(text)

def run_negesydd():
    global PROC, MASTER_FD

    # Open a PTY pair so Goose thinks it has a real terminal
    master_fd, slave_fd = pty.openpty()
    MASTER_FD = master_fd

    cmd = ["/home/pwintri2/Negesydd/negesydd", "goose"]
    PROC = subprocess.Popen(
        cmd,
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        close_fds=True,
        preexec_fn=os.setsid
    )
    os.close(slave_fd)  # slave end belongs to the child process now

    # Read from the master side of the PTY
    while True:
        try:
            r, _, _ = select.select([master_fd], [], [], 0.5)
            if r:
                try:
                    data = os.read(master_fd, 4096)
                except OSError:
                    break
                if not data:
                    break
                broadcast(data.decode('utf-8', errors='replace'))
            elif PROC.poll() is not None:
                # Process has exited and no more data
                break
        except (OSError, select.error):
            break

    broadcast("\n[Goose session ended]\n")

def main():
    t = threading.Thread(target=run_negesydd, daemon=True)
    t.start()
    
    server = ThreadingHTTPServer(('127.0.0.1', PORT), RequestHandler)
    url = f"http://127.0.0.1:{PORT}"
    print(f"Starting Negesydd UI server at {url}")
    print("Press Ctrl+C to stop the server.")
    
    # Automatically open the browser to act like a standalone app
    webbrowser.open(url)
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if PROC:
            PROC.terminate()

if __name__ == '__main__':
    main()
