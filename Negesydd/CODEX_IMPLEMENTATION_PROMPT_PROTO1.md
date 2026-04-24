# Negesydd Implementation Prompt for Codex
## Build & Test in Docker Sandbox (Proto1 Container)

---

## CONTEXT

You are implementing the complete Negesydd multi-agent messenger system. All code will be:
1. **Built** in a Docker sandbox environment
2. **Tested** with comprehensive unit and integration tests
3. **Verified** before deployment

The Docker sandbox provides isolated, reproducible builds and prevents system pollution.

---

## EXECUTION MODE: DOCKER SANDBOX BUILD & TEST

### Phase 1: Prepare Sandbox Environment

**Dockerfile for Negesydd Build & Test:**

```dockerfile
# Use Python 3.11 slim for lightweight sandbox
FROM python:3.11-slim

WORKDIR /negesydd

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy source files
COPY . .

# Set entrypoint for testing
ENTRYPOINT ["/bin/bash"]

LABEL description="Negesydd development & test sandbox"
```

**Build command:**
```bash
cd /home/pwintri2/Negesydd
docker build -f Dockerfile.sandbox -t negesydd:dev-sandbox .
```

**Run for development:**
```bash
docker run -it \
  -v /home/pwintri2/Negesydd:/negesydd \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e OLLAMA_BASE_URL=http://host.docker.internal:11434 \
  negesydd:dev-sandbox
```

---

## MODULE IMPLEMENTATION SEQUENCE (In Sandbox)

For each module below:
1. Codex generates the Python file
2. Save to `/negesydd/<filename>.py`
3. Run tests in container
4. Fix any issues
5. Commit and move to next module

---

## MODULE 1: LOGGER (`logger.py`)
**Start here. Foundation for all other modules.**

### Specification

```python
import logging
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

class StructuredLogger:
    """
    Structured logging system for Negesydd with JSON output support.
    
    Features:
    - Multiple log levels (DEBUG, INFO, WARNING, ERROR)
    - JSON-formatted logs for machine parsing
    - File and console output
    - Correlation IDs for request tracing
    - Colored console output for readability
    """
    
    def __init__(self, name: str, log_dir: str = "./logs", level: str = "INFO"):
        """Initialize logger with file and console handlers."""
        pass
    
    def debug(self, message: str, context: dict = None, correlation_id: str = None):
        """Log DEBUG level with optional context."""
        pass
    
    def info(self, message: str, context: dict = None, correlation_id: str = None):
        """Log INFO level with optional context."""
        pass
    
    def warning(self, message: str, context: dict = None, correlation_id: str = None):
        """Log WARNING level with optional context."""
        pass
    
    def error(self, message: str, exception: Exception = None, context: dict = None, correlation_id: str = None):
        """Log ERROR level with exception traceback."""
        pass
    
    def set_correlation_id(self, correlation_id: str):
        """Set correlation ID for all subsequent logs in this request."""
        pass

# Usage example:
# logger = StructuredLogger("negesydd.messenger")
# logger.info("Routing message", {"source": "gemini_cli", "dest": "agent_1"})
```

### Test File: `test_logger.py`

```python
import pytest
import json
from pathlib import Path
from logger import StructuredLogger

def test_logger_init():
    """Test logger initialization."""
    logger = StructuredLogger("test")
    assert logger is not None

def test_logger_info():
    """Test INFO level logging."""
    logger = StructuredLogger("test")
    logger.info("Test message", {"key": "value"})
    # Verify log file created and contains JSON

def test_correlation_id():
    """Test correlation ID tracking."""
    logger = StructuredLogger("test")
    logger.set_correlation_id("test-123")
    logger.info("Message with correlation")
    # Verify correlation ID in output

def test_error_with_exception():
    """Test error logging with exception."""
    logger = StructuredLogger("test")
    try:
        raise ValueError("Test error")
    except Exception as e:
        logger.error("Error occurred", exception=e)
    # Verify exception traceback in log
```

**Sandbox test command:**
```bash
pytest tests/test_logger.py -v --tb=short
```

---

## MODULE 2: MESSAGE ENVELOPE (`message_types.py`)
**Define core data structures used throughout Negesydd.**

### Specification

```python
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum
import json
import uuid

class MessageType(Enum):
    PROMPT = "prompt"
    RESPONSE = "response"
    STATUS = "status"
    ERROR = "error"
    LIFECYCLE = "lifecycle"
    DISCOVERY = "discovery"
    HEARTBEAT = "heartbeat"

class Priority(Enum):
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4

class LifecycleEvent(Enum):
    STARTING = "starting"
    READY = "ready"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    SHUTTING_DOWN = "shutting_down"

@dataclass
class Message:
    """Standard message envelope for all inter-component communication."""
    message_id: str  # UUID
    timestamp: str  # ISO 8601
    source: str  # "gemini_cli", "codex_vscode", "agent_name", "messenger"
    destination: str  # Same options
    message_type: MessageType
    priority: Priority
    content: Dict[str, Any]
    
    # Optional fields
    context: Optional[Dict[str, str]] = None  # task_id, session_id, parent_message_id
    error: Optional[Dict[str, Any]] = None  # error_code, error_message, traceback
    metadata: Optional[Dict[str, Any]] = None  # Custom metadata
    
    @classmethod
    def create(cls, source: str, destination: str, message_type: MessageType,
               content: Dict[str, Any], priority: Priority = Priority.NORMAL,
               context: Dict = None, metadata: Dict = None) -> 'Message':
        """Factory method to create a message with auto-generated ID and timestamp."""
        pass
    
    def to_json(self) -> str:
        """Serialize to JSON string."""
        pass
    
    @classmethod
    def from_json(cls, json_str: str) -> 'Message':
        """Deserialize from JSON string."""
        pass
    
    def is_error(self) -> bool:
        """Check if message indicates an error state."""
        pass
    
    def get_correlation_id(self) -> str:
        """Extract correlation ID from context if present."""
        pass

# Usage example:
# msg = Message.create(
#     source="gemini_cli",
#     destination="agent_gorilla",
#     message_type=MessageType.PROMPT,
#     content={"text": "Analyze this code"},
#     context={"task_id": "task_123"}
# )
```

### Test File: `test_message_types.py`

```python
import pytest
import json
from message_types import Message, MessageType, Priority

def test_message_creation():
    """Test creating a message with factory method."""
    msg = Message.create(
        source="gemini_cli",
        destination="messenger",
        message_type=MessageType.PROMPT,
        content={"text": "test"}
    )
    assert msg.message_id is not None
    assert msg.timestamp is not None
    assert msg.source == "gemini_cli"

def test_message_json_serialization():
    """Test JSON round-trip."""
    msg = Message.create(
        source="agent_1",
        destination="agent_2",
        message_type=MessageType.RESPONSE,
        content={"result": "success"}
    )
    json_str = msg.to_json()
    msg2 = Message.from_json(json_str)
    assert msg.message_id == msg2.message_id
    assert msg.content == msg2.content

def test_error_message():
    """Test error message handling."""
    msg = Message.create(
        source="agent_1",
        destination="messenger",
        message_type=MessageType.ERROR,
        content={"text": "Failed"},
        error={"error_code": 500, "error_message": "Internal error"}
    )
    assert msg.is_error()
```

**Sandbox test command:**
```bash
pytest tests/test_message_types.py -v --tb=short
```

---

## MODULE 3: AGENT POOL (`agent_pool.py`)
**Discover and manage available agents.**

### Specification

```python
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import subprocess
import json
from enum import Enum
import psutil
import threading
import time

class AgentStatus(Enum):
    IDLE = "idle"
    PROCESSING = "processing"
    ERROR = "error"
    OFFLINE = "offline"

@dataclass
class Agent:
    """Represents an available agent."""
    agent_id: str
    name: str
    status: AgentStatus
    last_heartbeat: datetime
    uptime_seconds: float
    capability_tags: List[str] = field(default_factory=list)
    version: str = "unknown"
    resource_usage: Dict[str, float] = field(default_factory=dict)  # cpu%, memory_mb
    
    def is_healthy(self, heartbeat_timeout_seconds: int = 30) -> bool:
        """Check if agent is responding."""
        pass
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        pass

class AgentPool:
    """
    Manages discovery, health monitoring, and lifecycle of all agents.
    
    Discovers: gorilla, goose, codex_vscode, and custom agents.
    Maintains agent registry with status tracking.
    """
    
    def __init__(self, logger=None):
        self.agents: Dict[str, Agent] = {}
        self.logger = logger
        self._heartbeat_thread = None
        self._running = False
    
    def discover_agents(self) -> List[Agent]:
        """
        Discover available agents by:
        1. Checking which <agent> in PATH
        2. Querying process names
        3. Checking VSCode extensions for Codex
        
        Returns: List of discovered Agent objects
        """
        pass
    
    def add_agent(self, agent: Agent) -> None:
        """Register an agent in the pool."""
        pass
    
    def get_agent(self, agent_id: str) -> Optional[Agent]:
        """Get agent by ID."""
        pass
    
    def get_agents_by_capability(self, capability: str) -> List[Agent]:
        """Filter agents by capability tag."""
        pass
    
    def get_agents_by_status(self, status: AgentStatus) -> List[Agent]:
        """Filter agents by status."""
        pass
    
    def update_agent_status(self, agent_id: str, status: AgentStatus) -> None:
        """Update agent status and refresh heartbeat time."""
        pass
    
    def start_health_monitoring(self) -> None:
        """Start background thread for agent health checks."""
        pass
    
    def stop_health_monitoring(self) -> None:
        """Stop background monitoring thread."""
        pass
    
    def get_resource_usage(self, agent_id: str) -> Dict[str, float]:
        """Get CPU and memory usage for an agent."""
        pass
    
    def list_all_agents(self) -> List[Agent]:
        """Return all registered agents."""
        pass

# Usage example:
# pool = AgentPool(logger)
# pool.discover_agents()
# healthy_agents = [a for a in pool.list_all_agents() if a.is_healthy()]
```

### Test File: `test_agent_pool.py`

```python
import pytest
from agent_pool import AgentPool, Agent, AgentStatus
from datetime import datetime

def test_agent_pool_init():
    """Test AgentPool initialization."""
    pool = AgentPool()
    assert pool.agents == {}

def test_discover_agents():
    """Test agent discovery."""
    pool = AgentPool()
    agents = pool.discover_agents()
    # Should find at least system agents (which, ps, etc.)

def test_add_agent():
    """Test adding agent to pool."""
    pool = AgentPool()
    agent = Agent(
        agent_id="test_1",
        name="Test Agent",
        status=AgentStatus.IDLE,
        last_heartbeat=datetime.now(),
        uptime_seconds=100,
        capability_tags=["test"]
    )
    pool.add_agent(agent)
    assert pool.get_agent("test_1") is not None

def test_agent_health_check():
    """Test agent health monitoring."""
    pool = AgentPool()
    agent = Agent(
        agent_id="test_1",
        name="Test",
        status=AgentStatus.IDLE,
        last_heartbeat=datetime.now(),
        uptime_seconds=100
    )
    pool.add_agent(agent)
    assert agent.is_healthy()
```

**Sandbox test command:**
```bash
pytest tests/test_agent_pool.py -v --tb=short
```

---

## MODULE 4: MESSAGE QUEUE (`message_queue.py`)
**Thread-safe message routing and queueing.**

### Specification

```python
from queue import Queue, Empty
from threading import Lock, Event
from typing import Optional, Callable, List
import threading
from message_types import Message, MessageType
import time

class MessageQueue:
    """
    Thread-safe message queue for routing between components.
    
    Features:
    - FIFO queue with blocking put/get
    - Priority support (reorder by priority)
    - Callbacks for message delivery events
    - Dead letter queue for failed messages
    """
    
    def __init__(self, max_size: int = 10000, logger=None):
        self.queue: Queue = Queue(maxsize=max_size)
        self.dead_letter_queue: List[Message] = []
        self.logger = logger
        self._lock = Lock()
        self._callbacks: dict = {}  # message_type -> [callbacks]
    
    def put(self, message: Message, block: bool = True, timeout: Optional[float] = None) -> bool:
        """
        Put message on queue.
        Returns: True if successful, False if queue full and non-blocking
        """
        pass
    
    def get(self, block: bool = True, timeout: Optional[float] = None) -> Optional[Message]:
        """
        Get next message from queue.
        Returns: Message or None if empty and non-blocking
        """
        pass
    
    def put_dead_letter(self, message: Message, reason: str) -> None:
        """Move failed message to dead letter queue."""
        pass
    
    def get_dead_letters(self) -> List[Message]:
        """Retrieve all dead letter messages."""
        pass
    
    def register_callback(self, message_type: MessageType, callback: Callable) -> None:
        """Register callback for specific message type."""
        pass
    
    def trigger_callbacks(self, message: Message) -> None:
        """Trigger all callbacks for message type."""
        pass
    
    def size(self) -> int:
        """Current queue size."""
        pass
    
    def is_empty(self) -> bool:
        """Check if queue is empty."""
        pass
    
    def clear(self) -> None:
        """Clear all messages from queue."""
        pass

# Usage example:
# queue = MessageQueue(logger)
# queue.put(message)
# msg = queue.get(timeout=5)
```

### Test File: `test_message_queue.py`

```python
import pytest
import threading
from message_queue import MessageQueue
from message_types import Message, MessageType, Priority

def test_queue_put_get():
    """Test basic put and get."""
    queue = MessageQueue()
    msg = Message.create("source", "dest", MessageType.PROMPT, {"text": "test"})
    queue.put(msg)
    retrieved = queue.get(timeout=1)
    assert retrieved.message_id == msg.message_id

def test_queue_empty():
    """Test empty queue handling."""
    queue = MessageQueue()
    assert queue.is_empty()
    assert queue.size() == 0

def test_dead_letter_queue():
    """Test dead letter queue."""
    queue = MessageQueue()
    msg = Message.create("src", "dst", MessageType.ERROR, {"error": "test"})
    queue.put_dead_letter(msg, "Processing failed")
    dead_letters = queue.get_dead_letters()
    assert len(dead_letters) == 1

def test_callback_registration():
    """Test message callbacks."""
    queue = MessageQueue()
    callback_called = []
    
    def test_callback(msg):
        callback_called.append(msg)
    
    queue.register_callback(MessageType.PROMPT, test_callback)
    msg = Message.create("src", "dst", MessageType.PROMPT, {"text": "test"})
    queue.trigger_callbacks(msg)
    assert len(callback_called) == 1
```

**Sandbox test command:**
```bash
pytest tests/test_message_queue.py -v --tb=short
```

---

## SANDBOX BUILD & TEST WORKFLOW

### Build Docker Sandbox Image
```bash
cd /home/pwintri2/Negesydd

# Create Dockerfile.sandbox (use the one provided above)

# Build the image
docker build -f Dockerfile.sandbox -t negesydd:dev-sandbox .

# Verify
docker images | grep negesydd
```

### Run Tests in Sandbox

**For each module implementation:**

```bash
# Start sandbox container (interactive)
docker run -it \
  -v /home/pwintri2/Negesydd:/negesydd \
  negesydd:dev-sandbox

# Inside container:
cd /negesydd
pytest tests/test_<module>.py -v --tb=short

# If tests pass, exit container
exit
```

**Batch test all modules:**
```bash
docker run --rm \
  -v /home/pwintri2/Negesydd:/negesydd \
  negesydd:dev-sandbox \
  bash -c "cd /negesydd && pytest tests/ -v --tb=short"
```

### Sandbox Output Verification

After each module implementation, verify:

```
✓ All unit tests pass (pytest output shows PASSED)
✓ No import errors
✓ No missing dependencies
✓ Type hints are correct (python -m mypy negesydd/<module>.py)
✓ Code style passes (python -m pylint negesydd/<module>.py)
```

---

## IMPLEMENTATION CHECKLIST

**Module 1 - Logger**
- [ ] Codex generates `logger.py`
- [ ] Copy to `/home/pwintri2/Negesydd/logger.py`
- [ ] Run sandbox tests: `pytest tests/test_logger.py -v`
- [ ] All tests pass ✓
- [ ] Commit changes

**Module 2 - Message Types**
- [ ] Codex generates `message_types.py`
- [ ] Copy to `/home/pwintri2/Negesydd/message_types.py`
- [ ] Run sandbox tests: `pytest tests/test_message_types.py -v`
- [ ] All tests pass ✓
- [ ] Commit changes

**Module 3 - Agent Pool**
- [ ] Codex generates `agent_pool.py`
- [ ] Copy to `/home/pwintri2/Negesydd/agent_pool.py`
- [ ] Run sandbox tests: `pytest tests/test_agent_pool.py -v`
- [ ] All tests pass ✓
- [ ] Commit changes

**Module 4 - Message Queue**
- [ ] Codex generates `message_queue.py`
- [ ] Copy to `/home/pwintri2/Negesydd/message_queue.py`
- [ ] Run sandbox tests: `pytest tests/test_message_queue.py -v`
- [ ] All tests pass ✓
- [ ] Commit changes

---

## CONTINUING MODULES (Same Pattern)

After these 4 foundation modules are complete, follow the same pattern for:

5. `config_parser.py` - Parse YAML plan files and prompts
6. `error_handler.py` - Error recovery and resilience
7. `llm_core.py` - Deepseek-coder integration (requires Ollama)
8. `messenger.py` - Core routing and orchestration
9. `lifecycle.py` - Startup and shutdown sequences
10. `task_executor.py` - Task execution with dependencies
11. `codex_bridge.py` - VSCode Codex detection
12. `dashboard.py` - Enhanced web UI server

---

## DOCKER SANDBOX BENEFITS

✓ **Isolation** - Experiments don't affect host system
✓ **Reproducibility** - Exact same environment every run
✓ **Cleanliness** - Easy cleanup: `docker rmi negesydd:dev-sandbox`
✓ **Testing** - Run tests in production-like environment
✓ **Documentation** - Dockerfile serves as build documentation
✓ **CI/CD Ready** - Same Dockerfile can be used in GitHub Actions

---

## SANDBOX CONTAINER PERSISTENCE

To keep built modules and test results:

```bash
# Create named volume for persistence
docker volume create negesydd-dev

# Run container with persistence
docker run -it \
  -v /home/pwintri2/Negesydd:/negesydd \
  -v negesydd-dev:/negesydd/.venv \
  negesydd:dev-sandbox
```

---

## TROUBLESHOOTING IN SANDBOX

### "pytest: command not found"
```bash
# Inside container
pip install pytest pytest-asyncio
```

### "Module not found" errors
```bash
# Inside container, ensure __init__.py exists
touch /negesydd/__init__.py
touch /negesydd/tests/__init__.py
```

### "Permission denied" on /negesydd
```bash
# Outside container, fix permissions
chmod -R 755 /home/pwintri2/Negesydd
```

### Tests timeout
```bash
# Increase timeout in pytest.ini
[pytest]
timeout = 10
```

---

## WHEN COMPLETE

Once all 12 modules are implemented, tested, and passing in sandbox:

1. Build final production image (without test deps)
2. Run full integration tests
3. Deploy to actual Gemini CLI environment
4. Monitor with structured logging
5. Use plan files to orchestrate agents

---

**Status: Ready for Codex Implementation**  
**Method: Docker Sandbox Build & Test**  
**LLM: deepseek-coder:latest**  
**Start with Module 1 (logger.py)**
