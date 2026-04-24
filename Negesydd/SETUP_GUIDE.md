# Negesydd Setup & Quick Start Guide

## Pre-Requirements Check

Before you start building in Codex, verify your environment:

```bash
cd /home/pwintri2/Negesydd

# Full system check
python negesydd_app.py --check-system

# Should output: ✓ OK for dependencies, Ollama, agents discovered
```

## Installation Steps

### 1. Install Python Dependencies
```bash
cd /home/pwintri2/Negesydd
pip install -r requirements.txt
```

### 2. Install & Run Ollama
```bash
# Install Ollama (if not already installed)
curl -fsSL https://ollama.ai/install.sh | sh

# Start Ollama server (background)
ollama serve &

# Pull deepseek-coder (optimal for Negesydd)
ollama pull deepseek-coder:latest

# Verify it's ready
curl http://localhost:11434/api/tags
```

### 3. Verify Gemini CLI
```bash
which gemini
gemini --version
```

### 4. Check for Agent Availability
```bash
which goose
which gorilla
```

---

## Quick Start

### Option A: Using a Plan File
```bash
python negesydd_app.py --plan plans/example_workflow.yaml --verbose
```

### Option B: Using a Direct Prompt
```bash
python negesydd_app.py --prompt "Create a Python REST API with FastAPI" \
  --agents gorilla,goose,codex_vscode \
  --loglevel DEBUG
```

### Option C: Dry-Run (Parse Only)
```bash
python negesydd_app.py --plan plans/example_workflow.yaml --dry-run
```

### Option D: List Available LLMs
```bash
python negesydd_app.py --list-llms
```

---

## Using with Codex in VSCode

### Setup Instructions

1. **Open the Codex Prompt in VSCode:**
   - Open VSCode
   - Install Codex extension (if not already installed)
   - Create a new file or open an existing one
   - Open Command Palette: `Cmd+Shift+P` (Mac) or `Ctrl+Shift+P` (Windows/Linux)
   - Search for "Codex" and enable it

2. **Load the Build Prompt:**
   - Open `/home/pwintri2/Negesydd/CODEX_BUILD_PROMPT.md`
   - Copy the entire content
   - In your code editor, paste the prompt above a new Python file

3. **Start Implementation:**
   - Ask Codex: "Implement the messenger.py module according to this specification"
   - Codex will generate the MessengerCore class and related functions
   - Save to `/home/pwintri2/Negesydd/messenger.py`

4. **Iterative Development:**
   - Use Codex to implement each module: `agent_pool.py`, `lifecycle.py`, etc.
   - Reference the CODEX_BUILD_PROMPT.md specification for each module
   - Test implementations with: `python negesydd_app.py --check-system`

---

## Dashboard Access

Once running, access the dashboard at:
```
http://localhost:8765
```

Features:
- Real-time Gemini CLI output terminal
- Codex VSCode activity viewer
- Agent status monitor
- Execution timeline
- Message routing log
- Prompt input form

---

## LLM Selection Rationale

Your system has these options:

| Model | Size | Best For | Score |
|-------|------|----------|-------|
| **deepseek-coder** | 776 MB | Code understanding, routing | ⭐⭐⭐⭐⭐ |
| codellama:13b | 7.4 GB | Advanced reasoning | ⭐⭐⭐⭐ |
| llama3.2 | 2.0 GB | General purpose | ⭐⭐⭐ |
| devstral | 14 GB | Code-heavy tasks | ⭐⭐⭐ |
| llama3 | 4.7 GB | Solid all-around | ⭐⭐⭐⭐ |

**Why deepseek-coder for Negesydd:**
1. **Fast inference** - sub-1-second routing decisions
2. **Code semantic understanding** - parses prompts into structured tasks
3. **Lightweight** - 776 MB fits comfortably in memory
4. **Specialized** - trained on code patterns and instruction-following
5. **Local execution** - no API calls, full privacy

---

## Project Structure After Implementation

```
/home/pwintri2/Negesydd/
├── CODEX_BUILD_PROMPT.md        ← Full specification (paste into Codex)
├── negesydd                       ← Original CLI wrapper
├── negesydd_gui.py               ← Existing web UI
├── negesydd_app.py               ← Main entry point (template)
├── messenger.py                  ← TO BUILD: Core routing
├── agent_pool.py                 ← TO BUILD: Agent management
├── lifecycle.py                  ← TO BUILD: Orchestration
├── llm_core.py                   ← TO BUILD: Deepseek integration
├── codex_bridge.py               ← TO BUILD: VSCode communication
├── config_parser.py              ← TO BUILD: Plan/prompt parsing
├── task_executor.py              ← TO BUILD: Task execution
├── dashboard.py                  ← TO BUILD: Enhanced UI
├── error_handler.py              ← TO BUILD: Error recovery
├── logger.py                     ← TO BUILD: Structured logging
├── requirements.txt              ← Python dependencies
├── plans/
│   └── example_workflow.yaml     ← Sample execution plan
├── tests/
│   ├── test_messenger.py
│   ├── test_agent_pool.py
│   └── test_integration.py
└── docs/
    └── IMPLEMENTATION_GUIDE.md
```

---

## Development Workflow with Codex

### Step 1: Core Foundation
Ask Codex to implement in this order:
1. `messenger.py` - Message router and queue
2. `agent_pool.py` - Agent discovery and health checks
3. `lifecycle.py` - Startup orchestration

Test after each:
```bash
python negesydd_app.py --check-system
python -m pytest tests/test_messenger.py -v
```

### Step 2: Intelligence Layer
4. `llm_core.py` - Deepseek-coder integration
5. `codex_bridge.py` - VSCode detection and messaging

Test:
```bash
python -c "from llm_core import test_connection; test_connection()"
```

### Step 3: Configuration & Execution
6. `config_parser.py` - YAML/prompt file parsing
7. `task_executor.py` - Dependency resolution

Test:
```bash
python negesydd_app.py --plan plans/example_workflow.yaml --dry-run
```

### Step 4: Dashboard & Observability
8. `dashboard.py` - Enhanced web UI
9. `error_handler.py` - Recovery logic
10. `logger.py` - Structured logging

Full test:
```bash
python negesydd_app.py --plan plans/example_workflow.yaml --verbose
```

---

## Example Prompt for Codex (Copy-Paste)

```
You are implementing a message routing system for multi-agent coordination.

Reference specification: /home/pwintri2/Negesydd/CODEX_BUILD_PROMPT.md

Implement the `messenger.py` module with:
1. MessengerCore class with methods: discover_agents(), route_message(), sync_execution_timeline()
2. Message envelope structure (JSON with metadata)
3. Thread-safe queue management for message routing
4. Event emission system for dashboard updates
5. Comprehensive error handling and logging

Use the Message class specification from the prompt.
Include docstrings for all methods.
Handle edge cases (missing agents, routing failures).
```

Then paste this followed by the "Messenger Core" section from CODEX_BUILD_PROMPT.md.

---

## Troubleshooting

### Issue: "Ollama not responding"
```bash
# Start Ollama in foreground
ollama serve

# Or check if it's running
ps aux | grep ollama
```

### Issue: "deepseek-coder not found"
```bash
ollama pull deepseek-coder:latest
ollama list
```

### Issue: Agents not discovered
```bash
# Check if agents are in PATH
which goose
which gorilla

# Add to PATH if needed
export PATH=$PATH:/path/to/agents
```

### Issue: Codex not detected
```bash
# Ensure VSCode is running with Codex extension active
# Check extension status: VSCode → Extensions → Search "Codex"
# Restart VSCode if needed
```

---

## Success Checklist

Before declaring Negesydd "ready":

- [ ] All dependencies installed (`pip install -r requirements.txt`)
- [ ] Ollama running with deepseek-coder available
- [ ] Gemini CLI functional (`gemini --version` works)
- [ ] At least 2 agents discoverable (goose, gorilla)
- [ ] System check passes (`python negesydd_app.py --check-system`)
- [ ] Can load plan file (`python negesydd_app.py --plan plans/example_workflow.yaml --dry-run`)
- [ ] Dashboard starts on http://localhost:8765
- [ ] Codex VSCode extension active and accessible
- [ ] All 13+ modules implemented with comprehensive tests
- [ ] End-to-end test succeeds (prompt → routing → execution → display)

---

## Next Steps

1. **Get Codex Prompt:** Open `CODEX_BUILD_PROMPT.md`
2. **Paste into Codex:** Copy content into VSCode with Codex enabled
3. **Request Implementation:** "Implement messenger.py according to this specification"
4. **Iterate:** Build one module at a time, testing after each
5. **Integrate:** Connect modules through `negesydd_app.py`
6. **Test:** Run full system with example plan file
7. **Monitor:** Watch dashboard in real-time during execution
8. **Deploy:** Use for actual multi-agent workflows

---

**Happy building! 🚀**
