# Codex Implementation Prompt for Negesydd
## Quick Reference (Sandbox Build & Test)

---

## 📋 WHAT TO DO

1. **Open Codex in VSCode**
2. **Copy the implementation prompt below**
3. **Paste into Codex** and follow the module sequence

---

## 🚀 QUICK START

### Step 1: Prepare Sandbox
```bash
cd /home/pwintri2/Negesydd
./sandbox-build.sh init     # Create directories and volumes
./sandbox-build.sh build    # Build Docker image
```

### Step 2: For Each Module (repeat 4 times)

1. **Ask Codex to implement Module 1: logger.py**
   ```
   Implement logger.py according to the specification in 
   CODEX_IMPLEMENTATION_PROMPT_PROTO1.md (MODULE 1: LOGGER section).
   Include all methods, docstrings, and error handling.
   ```

2. **Save to `/home/pwintri2/Negesydd/logger.py`**

3. **Test in Sandbox**
   ```bash
   ./sandbox-build.sh test logger
   ```

4. **Verify all tests pass** (green checkmarks)

5. **Commit changes**
   ```bash
   cd /home/pwintri2/Negesydd
   git add logger.py tests/test_logger.py
   git commit -m "Implement logger.py module"
   ```

6. **Repeat for Modules 2-4**:
   - message_types.py
   - agent_pool.py
   - message_queue.py

---

## 📝 IMPLEMENTATION SEQUENCE

### Module 1: `logger.py` (Foundation)
- Codex generates StructuredLogger class
- Copy to `/negesydd/logger.py`
- Test: `./sandbox-build.sh test logger`
- Estimated time: 15 min

### Module 2: `message_types.py` (Data Structures)
- Codex generates Message dataclass and enums
- Copy to `/negesydd/message_types.py`
- Test: `./sandbox-build.sh test message_types`
- Estimated time: 20 min

### Module 3: `agent_pool.py` (Agent Management)
- Codex generates AgentPool class with discovery
- Copy to `/negesydd/agent_pool.py`
- Test: `./sandbox-build.sh test agent_pool`
- Estimated time: 25 min

### Module 4: `message_queue.py` (Routing)
- Codex generates MessageQueue class
- Copy to `/negesydd/message_queue.py`
- Test: `./sandbox-build.sh test message_queue`
- Estimated time: 20 min

**Total for foundation: ~80 minutes**

---

## 🔧 SANDBOX WORKFLOW COMMANDS

```bash
# Initialize once
./sandbox-build.sh init

# Build Docker image once
./sandbox-build.sh build

# After implementing each module
./sandbox-build.sh test logger           # Test logger.py
./sandbox-build.sh test message_types    # Test message_types.py
./sandbox-build.sh test agent_pool       # Test agent_pool.py
./sandbox-build.sh test message_queue    # Test message_queue.py

# Run all tests
./sandbox-build.sh test-all

# Debug/troubleshoot in interactive shell
./sandbox-build.sh shell

# Cleanup when done
./sandbox-build.sh clean
```

---

## 💻 COPY THIS INTO CODEX

### When Codex Asks "What should I implement?"

Copy and paste this prompt section:

```
You are implementing the Negesydd multi-agent messenger system.

Read the full specification in:
/home/pwintri2/Negesydd/CODEX_IMPLEMENTATION_PROMPT_PROTO1.md

Implement MODULE 1: LOGGER (logger.py)

Requirements:
1. Create StructuredLogger class with JSON output support
2. Implement methods: __init__, debug, info, warning, error, set_correlation_id
3. Include docstrings for all methods
4. Handle file and console output
5. Support correlation IDs for request tracing
6. Add colored console output for readability

The class should satisfy all test cases in:
/home/pwintri2/Negesydd/tests/test_logger.py

Output ONLY the Python code, no explanations or markdown blocks.
```

---

After Module 1 is complete, repeat with:

```
Implement MODULE 2: MESSAGE TYPES (message_types.py)

Requirements:
1. Create Message dataclass with all required fields
2. Implement factory method: Message.create()
3. Implement serialization: to_json(), from_json()
4. Implement utility methods: is_error(), get_correlation_id()
5. Create enums: MessageType, Priority, LifecycleEvent

Satisfy all test cases in:
/home/pwintri2/Negesydd/tests/test_message_types.py

Output ONLY the Python code.
```

Repeat pattern for Module 3 (agent_pool.py) and Module 4 (message_queue.py).

---

## 📊 IMPLEMENTATION CHECKLIST

- [ ] **Setup Phase**
  - [ ] `./sandbox-build.sh init` executed
  - [ ] `./sandbox-build.sh build` completed
  - [ ] Docker image ready: `negesydd:dev-sandbox`

- [ ] **Module 1: logger.py**
  - [ ] Codex generates code
  - [ ] Saved to `/home/pwintri2/Negesydd/logger.py`
  - [ ] `./sandbox-build.sh test logger` passes (all green ✓)
  - [ ] Committed to git

- [ ] **Module 2: message_types.py**
  - [ ] Codex generates code
  - [ ] Saved to `/home/pwintri2/Negesydd/message_types.py`
  - [ ] `./sandbox-build.sh test message_types` passes ✓
  - [ ] Committed to git

- [ ] **Module 3: agent_pool.py**
  - [ ] Codex generates code
  - [ ] Saved to `/home/pwintri2/Negesydd/agent_pool.py`
  - [ ] `./sandbox-build.sh test agent_pool` passes ✓
  - [ ] Committed to git

- [ ] **Module 4: message_queue.py**
  - [ ] Codex generates code
  - [ ] Saved to `/home/pwintri2/Negesydd/message_queue.py`
  - [ ] `./sandbox-build.sh test message_queue` passes ✓
  - [ ] Committed to git

- [ ] **Verification**
  - [ ] `./sandbox-build.sh test-all` passes all 4 modules ✓
  - [ ] No import errors
  - [ ] No missing dependencies

---

## ✅ SUCCESS CRITERIA

After completing all 4 modules:

```bash
./sandbox-build.sh test-all
```

Should show:
```
tests/test_logger.py ............................ PASSED
tests/test_message_types.py ..................... PASSED
tests/test_agent_pool.py ........................ PASSED
tests/test_message_queue.py ..................... PASSED

============ 20 passed in 2.34s =============
```

---

## 🐛 TROUBLESHOOTING

### Docker image build fails
```bash
# Check Docker daemon is running
docker ps

# Rebuild with verbose output
docker build -f Dockerfile.sandbox -t negesydd:dev-sandbox . --progress=plain

# Check available disk space
df -h /var/lib/docker/
```

### Tests fail inside sandbox
```bash
# Launch interactive shell to debug
./sandbox-build.sh shell

# Inside shell, run tests manually
cd /negesydd
pytest tests/test_logger.py -v --tb=long

# Check imports
python -c "from logger import StructuredLogger; print('OK')"

# Exit sandbox
exit
```

### Volume permission issues
```bash
# Fix permissions on host
chmod -R 755 /home/pwintri2/Negesydd
chmod -R 755 /home/pwintri2/Negesydd/tests
```

### Module has syntax errors
```bash
# Check syntax in sandbox
./sandbox-build.sh shell
python -m py_compile logger.py  # Check for syntax errors
python -m pylint logger.py      # Check for style issues
```

---

## 📚 REFERENCE FILES

- **Full Implementation Spec:** `CODEX_IMPLEMENTATION_PROMPT_PROTO1.md`
- **Docker Config:** `Dockerfile.sandbox`
- **Build Script:** `sandbox-build.sh`
- **Requirements:** `requirements.txt`
- **Project Structure:**
  ```
  /home/pwintri2/Negesydd/
  ├── CODEX_IMPLEMENTATION_PROMPT_PROTO1.md  (← Full specification)
  ├── Dockerfile.sandbox                      (← Docker config)
  ├── sandbox-build.sh                        (← Build script)
  ├── requirements.txt
  ├── logger.py                               (← Implement here)
  ├── message_types.py                        (← Implement here)
  ├── agent_pool.py                           (← Implement here)
  ├── message_queue.py                        (← Implement here)
  └── tests/
      ├── test_logger.py                      (← Tests run here)
      ├── test_message_types.py
      ├── test_agent_pool.py
      └── test_message_queue.py
  ```

---

## 🎯 NEXT STEPS AFTER FOUNDATION MODULES

Once Modules 1-4 pass all tests, the remaining 8 modules follow the same pattern:

5. `config_parser.py` - Parse YAML plans
6. `error_handler.py` - Error recovery
7. `llm_core.py` - Deepseek-coder integration
8. `messenger.py` - Core routing (most complex)
9. `lifecycle.py` - Orchestration
10. `task_executor.py` - Task execution
11. `codex_bridge.py` - VSCode integration
12. `dashboard.py` - Web UI

Each uses the same sandbox test workflow.

---

**Ready to build? Start here:**

```bash
cd /home/pwintri2/Negesydd
./sandbox-build.sh init
./sandbox-build.sh build
```

Then open Codex and ask for Module 1: logger.py implementation! 🚀
