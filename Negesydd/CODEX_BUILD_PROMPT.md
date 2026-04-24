# Negesydd Multi-Agent Messenger System
## Advanced Codex Prompt for VSCode

---

## PROJECT OVERVIEW

You are building **Negesydd**, an intelligent messaging orchestration system that bridges Gemini CLI, Codex in VSCode, and their agents into a unified collaborative workspace. This system detects available agents, manages lifecycle events, routes messages between components, and provides real-time monitoring through a modern dashboard.

**Core Intelligence:** `deepseek-coder:latest` (776 MB) is the optimal LLM for this project due to its exceptional code understanding, instruction-following capabilities, and lightweight footprint. Alternative: `codellama:13b` for enhanced reasoning.

---

## SYSTEM ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────────┐
│                    NEGESYDD CORE SYSTEM                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  Gemini CLI  │  │Codex VSCode  │  │   Agents     │          │
│  │   (Input)    │  │  (IDE Tool)  │  │ (Execution)  │          │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │
│         │                  │                  │                  │
│         └──────────────────┼──────────────────┘                  │
│                            │                                     │
│                    ┌───────▼────────┐                            │
│                    │   MESSENGER    │                            │
│                    │   (Router)     │                            │
│                    └───────┬────────┘                            │
│                            │                                     │
│         ┌──────────────────┼──────────────────┬─────────────┐   │
│         │                  │                  │             │   │
│    ┌────▼─────┐    ┌──────▼──────┐    ┌─────▼──────┐  ┌──▼──┐ │
│    │ Lifecycle│    │ Agent Pool  │    │  Message   │  │LLM  │ │
│    │ Manager  │    │ Management  │    │  Queue     │  │Core │ │
│    └──────────┘    └─────────────┘    └────────────┘  └─────┘ │
│         │                  │                  │             │   │
│         └──────────────────┼──────────────────┴─────────────┘   │
│                            │                                     │
│                    ┌───────▼────────┐                            │
│                    │   DASHBOARD    │                            │
│                    │  (Web UI)      │                            │
│                    └────────────────┘                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## DETAILED SPECIFICATIONS

### 1. **Messenger Core** (`messenger.py`)
Primary responsibility: Message routing, state management, inter-component communication

**Key Features:**
- **Agent Discovery:** Auto-detect agents in execution environment (process scanning, service discovery)
- **Message Queue System:** Thread-safe queue handling prompts, completions, lifecycle events
- **Routing Engine:** Direct message flow between Gemini CLI → Agents → Codex
- **State Manager:** Track agent status (idle, processing, error), execution history
- **Event Emitter:** Broadcast real-time updates to dashboard via WebSocket/SSE

**Core Methods:**
```python
class MessengerCore:
    def discover_agents() -> List[Agent]
    def route_message(source, destination, payload) -> Response
    def detect_codex_vscode() -> bool
    def sync_execution_timeline() -> None
    def queue_prompt(prompt_text) -> TaskID
    def get_agent_status(agent_id) -> AgentStatus
```

### 2. **Agent Pool Manager** (`agent_pool.py`)
Manages lifecycle, health checks, resource allocation

**Responsibilities:**
- Enumerate available agents (gorilla, goose, etc.)
- Monitor agent health (heartbeat, resource usage)
- Manage startup/shutdown sequences
- Route tasks to available agents based on capability matching
- Maintain agent registry with metadata (version, capabilities, status)

**Data Model:**
```json
{
  "agent_id": "gorilla_1",
  "name": "Gorilla",
  "status": "active|idle|processing|error",
  "uptime_seconds": 1234,
  "capability_tags": ["code_execution", "file_ops"],
  "last_heartbeat": "2024-01-15T10:30:45Z",
  "resource_usage": {"cpu": 12.5, "memory_mb": 256},
  "version": "1.0.0"
}
```

### 3. **Lifecycle Manager** (`lifecycle.py`)
Orchestrates startup sequence and graceful shutdown

**Startup Sequence:**
1. Load config (prompt file or plan file)
2. Discover available agents
3. Detect Codex in VSCode (check extension status)
4. Initialize LLM connection (deepseek-coder)
5. Launch agents in dependency order
6. Start dashboard server
7. Begin listening for Gemini CLI input
8. Emit `system_ready` event

**Execution Flow Control:**
- Parse prompt/plan file to extract task graph
- Resolve task dependencies
- Start tasks at correct time (sequential/parallel based on config)
- Emit lifecycle events: `starting`, `ready`, `executing`, `completed`, `error`

### 4. **LLM Integration** (`llm_core.py`)
Deepseek-coder as the intelligent reasoning backbone

**Capabilities:**
- Parse user prompts into structured task definitions
- Generate optimal routing decisions
- Analyze agent capabilities for task matching
- Summarize execution results
- Detect context switching needs

**Integration Pattern:**
```python
def analyze_prompt(text: str) -> TaskDefinition
def route_to_best_agent(task: TaskDefinition) -> AgentID
def summarize_results(execution_log: List[Event]) -> str
```

### 5. **Dashboard Server** (`dashboard.py`)
Modern web UI for real-time monitoring (extend existing `negesydd_gui.py`)

**Features:**
- **Terminal Pane:** Live Gemini CLI output
- **Code Editor Pane:** VSCode Codex activity viewer (read-only connection)
- **Agent Monitor:** Real-time status panel for all detected agents
- **Prompt Input:** Accept new prompts with preview of parsed task tree
- **Execution Timeline:** Gantt-style visualization of task execution
- **Message Log:** All inter-component communication history
- **Statistics:** Execution time, token usage, success rate

**UI Sections:**
```
┌─────────────────────────────────────────────────────────┐
│ Header: Status | Agents Count | Uptime                  │
├──────────┬──────────────────────────────────────────────┤
│ Agents   │  Gemini CLI Terminal + Codex Activity       │
│ Panel    ├──────────────────────────────────────────────┤
│ (List)   │  Execution Timeline / Message Log             │
├──────────┼──────────────────────────────────────────────┤
│          │  [Prompt Input] [Send] [Load Plan]            │
└──────────┴──────────────────────────────────────────────┘
```

### 6. **Plan/Prompt File Parser** (`config_parser.py`)
Load structured task definitions from YAML/JSON

**Plan File Format (YAML):**
```yaml
version: "1.0"
name: "Data Processing Pipeline"
description: "Process data with multiple agents"

agents:
  required:
    - gorilla
    - goose
  optional:
    - codex_vscode

tasks:
  - id: task_1
    description: "Analyze requirements"
    agent: "gorilla"
    depends_on: []
    timeout_seconds: 300
    
  - id: task_2
    description: "Generate code"
    agent: "codex_vscode"
    depends_on: [task_1]
    context_from: task_1
    
  - id: task_3
    description: "Execute and validate"
    agent: "goose"
    depends_on: [task_2]
    context_from: task_2

execution:
  mode: "sequential"  # or "parallel_where_possible"
  timeout_total_seconds: 3600
  on_failure: "halt"  # or "continue" or "skip_dependent"
```

**Prompt Format (Extended):**
```
[NEGESYDD_PLAN]
agents_required: gorilla, goose
execution_mode: sequential
timeout_minutes: 60

[INITIAL_CONTEXT]
Your task is to build a React component for authentication.
Use the gorilla agent for analysis, goose for execution.

[STEPS]
1. Analyze requirements with gorilla
2. Generate component scaffold with codex
3. Integrate API with goose
4. Validate in dashboard

[END_NEGESYDD_PLAN]

Your actual prompt here...
```

### 7. **Codex Detection & Integration** (`codex_bridge.py`)
Communicate with Codex running in VSCode

**Methods:**
- Query VSCode extension API for Codex availability
- Send code generation requests to Codex
- Capture Codex output and stream to dashboard
- Detect when Codex is ready (via extension messaging)
- Monitor active document in VSCode

**Implementation:**
- Use VSCode extension messaging protocol
- Polling fallback: check `/tmp/.vscode_codex_socket`
- Register Negesydd as an external tool in Codex

### 8. **Message Format Specification**

**Standard Envelope:**
```json
{
  "message_id": "uuid-1234",
  "timestamp": "2024-01-15T10:30:45.123Z",
  "source": "gemini_cli|codex_vscode|agent_name|messenger",
  "destination": "agent_name|codex_vscode|gemini_cli|dashboard",
  "message_type": "prompt|response|status|error|lifecycle",
  "priority": "low|normal|high|critical",
  "content": {
    "text": "...",
    "metadata": {}
  },
  "context": {
    "task_id": "task_123",
    "session_id": "session_456",
    "parent_message_id": "msg_789"
  },
  "signature": "hash_for_verification"
}
```

### 9. **Error Handling & Recovery**

**Resilience Strategies:**
- Dead letter queue for failed messages
- Automatic agent restart on crash (up to 3 retries)
- Graceful degradation if Codex unavailable
- Circuit breaker pattern for LLM calls
- Detailed error logging with correlation IDs

**Error Types:**
```python
AgentNotAvailable(Exception)
CodexNotDetected(Exception)
MessageRoutingError(Exception)
LLMConnectionError(Exception)
TaskDependencyError(Exception)
ExecutionTimeout(Exception)
```

### 10. **Logging & Observability**

**Multi-level logging:**
- `DEBUG`: Message routing details, discovery processes
- `INFO`: Agent startup, task execution, state changes
- `WARNING`: Timeouts, retries, degraded modes
- `ERROR`: Failures, exceptions with full traceback

**Log Format:**
```
[2024-01-15 10:30:45.123] [INFO] [messenger.py:45] [session_456] Agent 'gorilla' changed state: idle → processing
```

**Metrics to track:**
- Messages routed per minute
- Agent utilization percentage
- Task completion rate
- Average execution time per agent
- LLM token usage
- Error rate by type

---

## IMPLEMENTATION ROADMAP

### Phase 1: Core Foundation (Files 1-3)
1. `messenger.py` — Core router and message queue
2. `agent_pool.py` — Agent discovery and management
3. `lifecycle.py` — Startup orchestration and state machine

### Phase 2: Integration (Files 4-5)
4. `llm_core.py` — Deepseek-coder integration with Ollama
5. `codex_bridge.py` — VSCode Codex detection and messaging

### Phase 3: Config & Execution (Files 6-7)
6. `config_parser.py` — Plan/prompt file parsing
7. `task_executor.py` — Dependency resolution and parallel task execution

### Phase 4: Dashboard & UI (Files 8-9)
8. Extend `negesydd_gui.py` with agent monitor, timeline, message log
9. `dashboard_api.py` — REST endpoints for UI operations

### Phase 5: Resilience (Files 10-11)
10. `error_handler.py` — Comprehensive error recovery
11. `logger.py` — Structured logging with observability

### Phase 6: Testing & Polish (Files 12+)
12. `test_suite.py` — Unit and integration tests
13. `performance_monitor.py` — Resource tracking and optimization

---

## DEEPSEEK-CODER CONFIGURATION

**Why deepseek-coder:latest?**
- **Code understanding:** Exceptional at parsing prompts into executable tasks
- **Model size:** 776 MB fits comfortably in memory without sacrificing capability
- **Routing logic:** Produces structured JSON for agent assignment decisions
- **Speed:** Fast inference for real-time routing decisions
- **Cost:** Minimal latency in local Ollama setup

**Ollama Setup:**
```bash
ollama run deepseek-coder:latest
# Or in background: ollama serve &
```

**Prompt Template for Task Analysis:**
```
You are an intelligent task router. Analyze the user prompt and output a JSON task definition.

Available agents: gorilla (planning/analysis), goose (execution), codex_vscode (code generation)

User prompt:
{user_prompt}

Output strict JSON (no markdown):
{
  "task_name": "...",
  "subtasks": [
    {"agent": "gorilla", "instruction": "..."},
    {"agent": "codex_vscode", "instruction": "..."},
    {"agent": "goose", "instruction": "..."}
  ],
  "dependencies": {"task_2": ["task_1"], "task_3": ["task_2"]},
  "estimated_duration_seconds": 300,
  "critical_path": ["task_1", "task_3"]
}
```

---

## STARTUP COMMAND

**From Prompt/Plan File:**
```bash
python negesydd_app.py --plan plans/my_workflow.yaml --loglevel DEBUG
# Or with inline prompt:
python negesydd_app.py --prompt "Build authentication component" --agents gorilla,goose,codex
```

**Dashboard Access:**
```
http://localhost:8765
Gemini CLI output streams live
Codex VSCode activity synced
Real-time agent status updates
```

---

## KEY INTERACTION FLOWS

### Flow 1: User Submits Prompt via Dashboard
```
User types prompt in Dashboard
  → Messenger receives via /input
  → LLM (deepseek-coder) parses into task tree
  → Lifecycle Manager resolves dependencies
  → Agent Pool Manager assigns subtasks
  → Messages route to respective agents (Gemini CLI, Codex, Goose)
  → Results aggregate back to Messenger
  → Dashboard displays real-time progress
  → Final summary emitted to terminal
```

### Flow 2: Codex Detects and Activates
```
Codex extension sends "I'm ready" message
  → Codex Bridge captures availability
  → Messenger updates agent registry
  → Dashboard shows "Codex VSCode" as active agent
  → Future prompts can now route to Codex for code generation
```

### Flow 3: Agent Failure & Recovery
```
Agent (e.g., goose) crashes or times out
  → Error Handler detects failure
  → Messenger moves message to Dead Letter Queue
  → Error recovery strategy executes (retry, skip, or halt)
  → Dashboard shows error with suggestion
  → User can retry or reassign to different agent
```

---

## TESTING & VALIDATION

**Before starting the app:**
1. Verify Ollama is running: `curl http://localhost:11434/api/tags`
2. Confirm deepseek-coder is available: `ollama list | grep deepseek-coder`
3. Check Gemini CLI is installed and functional
4. Ensure VSCode with Codex extension is running (optional but recommended)
5. Verify required Python dependencies: `requests`, `flask`, `ollama`, `pyyaml`

**Smoke Test Sequence:**
```bash
# 1. Test messenger core
python -m pytest tests/test_messenger.py -v

# 2. Test agent discovery
python negesydd_app.py --discover-agents --verbose

# 3. Test LLM integration
python -c "from llm_core import test_deepseek_connection; test_deepseek_connection()"

# 4. Test full system
python negesydd_app.py --plan examples/test_plan.yaml --dry-run

# 5. Start live dashboard
python negesydd_app.py --prompt "Hello, test the system" --verbose
```

---

## EXTENSIBILITY & FUTURE ENHANCEMENTS

- **Agent Plugins:** Support custom agents via plugin interface
- **Multi-LLM Routing:** Route complex tasks to llama3:latest, simpler tasks to phi3:latest
- **Persistence:** Save execution history to SQLite/PostgreSQL
- **Webhooks:** Trigger external systems on task completion
- **Slack Integration:** Send notifications and accept commands from Slack
- **Kubernetes Support:** Deploy agents as microservices in K8s
- **Model Fine-tuning:** Train deepseek-coder on your specific workflows

---

## PROJECT STRUCTURE

```
/home/pwintri2/Negesydd/
├── negesydd                      # Original CLI wrapper
├── negesydd_gui.py              # Existing web UI (extend this)
├── negesydd_app.py              # ← NEW: Main entry point
├── messenger.py                 # ← NEW: Core routing
├── agent_pool.py                # ← NEW: Agent management
├── lifecycle.py                 # ← NEW: Orchestration
├── llm_core.py                  # ← NEW: Deepseek integration
├── codex_bridge.py              # ← NEW: VSCode communication
├── config_parser.py             # ← NEW: YAML/prompt parsing
├── task_executor.py             # ← NEW: Task execution engine
├── dashboard.py                 # ← NEW: Enhanced UI server
├── error_handler.py             # ← NEW: Recovery logic
├── logger.py                    # ← NEW: Structured logging
├── plans/                       # ← NEW: Plan file examples
│   └── example_workflow.yaml
├── examples/                    # ← NEW: Example prompts
│   └── test_plan.yaml
├── tests/                       # ← NEW: Test suite
│   ├── test_messenger.py
│   ├── test_agent_pool.py
│   └── test_integration.py
└── requirements.txt             # ← NEW: Dependencies
```

---

## DEPENDENCIES

```
requests>=2.31.0
flask>=3.0.0
ollama>=0.0.11
pyyaml>=6.0
python-json-logger>=2.0.7
pytest>=7.4.0
pytest-asyncio>=0.21.0
```

---

## FINAL NOTES

This system transforms Negesydd from a basic CLI wrapper into an intelligent, multi-agent orchestration platform. The deepseek-coder LLM enables semantic understanding of tasks, intelligent routing, and adaptive execution strategies.

**Remember:** Start with Phase 1 (Messenger, Agent Pool, Lifecycle). Get the core message routing working first. Then add LLM intelligence. Finally, enhance the dashboard.

**Success criteria:**
- ✓ Detect Gemini CLI, Codex, and 2+ agents simultaneously
- ✓ Route a single prompt to correct agent based on task type
- ✓ Display real-time output from all components in unified dashboard
- ✓ Execute plan files with proper dependency ordering
- ✓ Handle agent failures gracefully with automatic recovery
- ✓ Provide clear audit trail of all message routing decisions

---

**Generated for:** PWintri2  
**Project:** Negesydd Multi-Agent Messenger  
**LLM Engine:** deepseek-coder:latest (776 MB)  
**Status:** Ready for Implementation
