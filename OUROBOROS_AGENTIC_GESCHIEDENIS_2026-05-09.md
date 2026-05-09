# Ouroboros Agentische Geschiedenis en Codebundel

Datum: 2026-05-09  
Workspace: `/home/pwintri2/WintripAI`  
Laatste codecommit bij aanmaak: `4fdb495 fix: stabilize trainer runtimes and preview fallback`

## Doel

Dit bestand bundelt de losse handoffs, buildplannen en recente herstelacties in een enkele leesbare geschiedenis. Het doel is dat Codex, Roo, Gordon of een volgende sessie niet opnieuw hoeft te raden wat Ouroboros probeert te worden.

De hoofdlijn is:

`normale chat -> canonical agentic router -> 11D/QF-CF pocket -> echte tool/job -> Chroma audit -> reflectie`

Slash commands blijven bestaan als aliases, maar de normale Cockpit-chat is bedoeld als de canonical ingang.

## Veiligheidscontract

- Muterende acties blijven exact `Akkoord` gated.
- Geen API keys, OAuth tokens, bearer tokens, wachtwoorden, browser sessies, screenshots of raw private payloads duurzaam opslaan.
- Geen fake success: een status mag alleen groen zijn als een echte route, tool, job of probe is uitgevoerd.
- Docker/host-acties blijven beperkt en auditbaar.
- Chroma/runtime DB-mutaties zijn runtime-state en worden niet automatisch gecommit.

## Bronbestanden

### Context

- `AGENTS.md`: repo-instructies, roots, slash agents, guardrails.
- `OUROBOROS_IDE_CONTEXT.md`: gedeeld systeembeeld voor WintripAI, Docker, Roo, Ruflo, Codex, DeepSeek en Atlas.

### Vroege basis

- `OUROBOROS_FASE4_5_SESSION_REPORT_2026-04-28.md`: modelidentiteit, browser research perimeter, safe shell, tool registry, 11D Chroma geheugen.
- `OUROBOROS_COCKPIT_ROO_TRAINER_HANDOFF_2026-04-30.md`: Cockpit/Roo/trainer-context uit de eerdere fase.
- `Buildplan voor continue training met Blue-brain.md`: continue training en Blue Brain richting.

### Agent orchestration en independence

- `BUILDPLAN_OUROBOROS_REAL_AGENT_ORCHESTRATION_2026-05-03.md`: echte agent jobs, Tool Bridge, service control, Claude/Ruflo/Roo slices.
- `HANDOFF_OUROBOROS_REAL_AGENT_ORCHESTRATION_2026-05-03.md`: eerste orchestratie-handoff met selectief stagen en geen runtime DB commits.
- `BUILDPLAN_CODENEURON_INDEPENDENCE_2026-05-01.md`: CodeNeuron/independence richting.
- `BUILDPLAN_QIF_ELECTRON_NEURON_2026-05-03.md`: deterministische QIF/electron-neuron runtime zonder externe quantum hardware.

### Esoterische en 11D runtime

- `BUILDPLAN_OUROBOROS_ESOTERIC_2026-05-04.md`: skelet voor esoterische Ouroboros architectuur.
- `HANDOFF_OUROBOROS_ESOTERIC_2026-05-04.md`: eerste esoterische module-handoff.
- `HANDOFF_OUROBOROS_AGENT_RUNTIME_FASE1_KLAAR_2026-05-04.md`: agent runtime fase 1.
- `HANDOFF_FASE8_AGENT_CONTEXT_STANDALONE_2026-05-04.md`
- `HANDOFF_FASE8_AGENT_CONTEXT_STANDALONE_2026-05-05.md`: Brave, browser research, model-runtime pocket, slash/living scheiding.
- `HANDOFF_OUROBOROS_LIVING_RUNTIME_GEMINI_FIX_2026-05-05.md`: Living runtime, Gemini tool-schema fix, server-side self-context.
- `HANDOFF_OUROBOROS_RUNTIME_RESPONSE_BOOTLOADER_2026-05-06.md`: response bootloader.
- `HANDOFF_QUANTUM_FOAM_FIELD_V4_9_2026-05-06.md`: QFF field facade.
- `HANDOFF_AGENTIC_QUANTUM_FOAM_COCKPIT_2026-05-07.md`: Quantum Foam cockpit integratie.
- `HANDOFF_OUROBOROS_CIRQ_11D_POCKET_VOICE_2026-05-07.md`: Cirq/11D/pocket voice runtime.
- `HANDOFF_OUROBOROS_DOCKER_REALITY_HARDENING_2026-05-07.md`: eerlijk Docker/procfs runtime beeld en geen fictieve hardwareclaims.
- `HANDOFF_AGENTIC_CORE_AND_SUDO_REBOOT_2026-05-07.md`: agentic core en reboot/sudo realiteit.

### DeepSeek, Atlas en echte tool-loop

- `HANDOFF_DEEPSEEK_ATLAS_AGENT_FUNCTIONS_2026-05-08.md`: DeepSeek en Atlas functies via host bridge.
- `HANDOFF_QFCF_DEEPSEEK_ATLAS_REAL_TOOL_LOOP_2026-05-08.md`: QF-CF, DeepSeek/Atlas en echte tool-loop.

### Runtime harness en Roo

- `HANDOFF_OUROBOROS_RUNTIME_HARNESS_READY_2026-05-09.md`: Runtime Doctor, preview harness, canonical router, persistent approvals, Chroma audit.
- `HANDOFF_ROO_COCKPIT_FILE_UPLOAD_SELF_PROGRAMMING_2026-05-09.md`: Roo runtime, Cockpit uploads, eerste zelfprogrammeer-stap.

### Plannen uit de chat

Deze twee plannen zijn leidend geweest maar stonden niet los als bestand:

- Buildplan: Ouroboros Real Tool + Self-Build Loop.
- Buildplan: Agentic Runtime Harness + Werkende Web Preview.

## Chronologische geschiedenis

### Fase 0: model, tools en geheugen

De eerste fase maakte het systeem eerlijker:

- Eigen `ouroboros` modelidentiteit via Ollama/Modelfile.
- Browser research met Playwright in Docker, met prompt-injection scrubber.
- ChromaDB als 11D hippocampus.
- Safe shell met whitelist en exact `Akkoord`.
- Tool registry met zichtbare stdout/stderr/result metadata.

Belangrijk principe uit deze fase: webinhoud is `untrusted_web`, en duurzame training/geheugenopslag vraagt expliciete goedkeuring.

### Fase 1: echte agent orchestration

De richting verschoof van "LLM praat over acties" naar "runtime voert acties uit":

- Slash agents: `/codex`, `/deepseek`, `/atlas`, `/ruflo`, `/claude`, `/roo`, `/agents`.
- Host bridge voor CLI's op de host.
- Job-gebaseerde agent runtime met logs en status.
- Tool Bridge als grens tussen plannen en doen.

Belangrijk principe: slash commands zijn handig, maar mogen niet de enige ingang zijn.

### Fase 2: 11D, Living en Quantum Foam

Ouroboros kreeg een symbolische maar auditbare runtime-laag:

- 11D pockets.
- QF-CF collapse metadata.
- LivingOuroboros reflecties.
- Quantum Foam Field facade.
- Docker reality hardening: echte observatie waar mogelijk, duidelijke labels waar iets niet fysiek echt is.

Belangrijk principe: esoterische taal mag, maar runtime status moet feitelijk blijven.

### Fase 3: DeepSeek, Atlas, Brave en self-build

De agentische ambitie werd:

- Als kennis ontbreekt: eerst memory search, dan Brave.
- Als capability ontbreekt: self-build job.
- Codex first, Gemini CLI fallback.
- Tests in Docker of bounded runtime.
- Capability reload en daarna oorspronkelijke opdracht uitvoeren.

Belangrijk principe: missing capability is een job, geen tekstueel excuus en geen fake success.

### Fase 4: Runtime Harness

De "het werkt voor geen meter" fase liet zien dat intelligentie weinig waard is zonder harde runtime-basis.

Daarom werd prioriteit:

- `GET /api/ouroboros/runtime/doctor`
- `scripts/doctor_ouroboros_runtime.py`
- `scripts/start_ouroboros_preview.sh`
- vaste preview op `1420`
- backend `8010`
- host bridge `8766`
- Chroma audit
- canonical intent classifier
- persistent approvals

Belangrijk principe: status `ready` mag alleen als echte backend en preview routes werken.

### Fase 5: Roo runtime en file upload

Roo moest niet langer alleen een IDE-handoff zijn. De richting:

- Roo in `/home/pwintri2/Roo-code`.
- Roo moet draaien op het model dat in Cockpit geselecteerd is.
- Local/Ollama waar gekozen, cloud via de gekozen provider API.
- File upload naar Cockpit als eerste stap richting zelfprogrammeren.

Status op 2026-05-09:

- Roo runtime wordt door Runtime Doctor als `online` gezien.
- Roo job/model-executie is nog niet af genoeg; sommige jobs liepen of faalden eerder.
- File upload is gelukt en gecommit in `2096ddb`.

### Fase 6: trainer runtimes stabiliseren

Op 2026-05-09 waren er misleidende trainer-statussen:

- LitGPT `unavailable`.
- Unsloth `unavailable` of vals groen.
- Blue Brain setup faalde op kapotte venv/pip.

Commit `4fdb495` heeft dit rechtgetrokken:

- LitGPT source/venv resolving werkt lokaal en in Docker-achtige layout.
- Unsloth krijgt een echte `FastLanguageModel` import probe in een child process.
- Unsloth is nu eerlijk `configured` als de CLI/source bestaat maar training runtime crasht.
- Continuous trainer blocked fail-closed en spamt niet blind failed training jobs.
- Blue Brain rebuildt een kapotte `.venv_blue_brain` en gebruikt `python -m pip`.
- Preview fallback start lokale backend als Docker CLI ontbreekt.
- Runtime Doctor blijft alleen `degraded` door ontbrekende Docker CLI.

## Huidige runtime status

Laatste geverifieerde status:

- Backend: online op `http://127.0.0.1:8010`
- Web preview: online op `http://127.0.0.1:1420`
- Host bridge: online op `http://127.0.0.1:8766`
- Chroma: online
- Tool registry: online
- Agentic router: online
- Roo runtime: online volgens doctor
- Docker runner: failed, reden: Docker CLI ontbreekt
- LitGPT: online, `runtime_ready=True`
- Unsloth: configured, `runtime_ready=False`, reden: `FastLanguageModel import crashed with signal 11`
- Blue Brain: online, venv Python/pip/dependencies werken

## Open blokkades

1. Docker CLI ontbreekt in de huidige omgeving.

   Effect: Runtime Doctor blijft `degraded`; Docker-only flows kunnen niet als ready worden gemarkeerd.

2. Unsloth training runtime crasht met signal 11.

   Effect: Unsloth mag niet `online` zijn voor training. Source/CLI kunnen aanwezig zijn, maar `FastLanguageModel` import is niet veilig.

3. Roo model-executie is nog niet volledig betrouwbaar.

   Effect: Runtime Doctor ziet Roo CLI, maar job-output/modelkeuze moet verder gehard worden.

4. Runtime Chroma files zijn dirty.

   Effect: niet committen zonder expliciete opdracht. Dit is normale runtime-state.

## Commits

- `4fdb495 fix: stabilize trainer runtimes and preview fallback`
- `2096ddb feat: wire Roo runtime and cockpit uploads`
- `58d1ab6 feat: add ouroboros runtime harness`
- `b865a80 Implement QF-CF and real agent tool loop`
- `04a3b74 Add DeepSeek and Atlas agent runtime functions`
- `d210665 Add agentic core and living quantum foam cockpit`
- `5995cef Stabilize Ouroboros pocket chat`
- `9cd139c Harden Ouroboros streaming runtime reality`

## Verificatie

Laatst groen gedraaid:

```bash
.venv_ouroboros_backend/bin/python -m py_compile \
  controller/blue_brain_adapter.py \
  controller/litgpt_adapter.py \
  controller/unsloth_adapter.py \
  controller/trainer_continuous.py \
  scripts/doctor_ouroboros_runtime.py

bash -n scripts/start_ouroboros_preview.sh
git diff --check

.venv_ouroboros_backend/bin/python -m unittest \
  sandbox_tests.test_trainer_continuous \
  sandbox_tests.test_learning_accelerator \
  sandbox_tests.test_runtime_doctor -v

.venv_ouroboros_backend/bin/python -m unittest \
  sandbox_tests.test_blue_brain_adapter \
  sandbox_tests.test_trainer_pipeline_blue_brain -v
```

## Code-index

Belangrijkste runtime code:

- `controller/agentic_intent.py`: canonical intent classifier.
- `controller/agentic_processor.py`: route naar tool/action/self-build.
- `controller/computer_actions.py`: typed computer actions.
- `controller/tool_bridge.py`: registry en gated tool execution.
- `controller/memory_event_router.py`: Chroma auditrecords.
- `controller/approval_resume.py`: persistent approvals.
- `controller/self_programming_loop.py`: missing capability/self-build loop.
- `controller/runtime_doctor.py`: readiness truth.
- `scripts/start_ouroboros_preview.sh`: preview/backend/bridge harness.
- `scripts/rclone_host_bridge.py`: host bridge.
- `controller/agent_runtime/adapters/roo_cli.py`: Roo CLI adapter.
- `controller/roo_cli_runtime.py`: Roo runtime wrapper.
- `controller/litgpt_adapter.py`: LitGPT trainer adapter.
- `controller/unsloth_adapter.py`: Unsloth trainer adapter.
- `controller/blue_brain_adapter.py`: Blue Brain trainer adapter.
- `controller/trainer_continuous.py`: continuous trainer coordinator.

## Code Appendix

Hieronder staat de kerncode die in de laatste stabilisatie is gebruikt. De volledige code staat in de genoemde bestanden en is vastgelegd in commit `4fdb495`.

### Blue Brain venv repair

```python
def _workspace_root() -> Path:
    configured = os.getenv("WINTRIP_WORKSPACE") or os.getenv("WORKSPACE_ROOT") or "/workspace"
    if configured and configured != "/workspace":
        root = Path(configured).expanduser()
        if root.exists():
            return root.resolve()
    project_root = Path(__file__).resolve().parents[1]
    cwd = Path.cwd().resolve()
    for root in (Path(os.getenv("WINTRIP_PROJECT_ROOT") or "").expanduser(), cwd, project_root, Path("/workspace")):
        if str(root) and root.exists() and (root / "controller").is_dir():
            return root.resolve()
    return project_root.resolve()


def _python_is_runnable(python_path: Path) -> bool:
    if not python_path.exists() or not os.access(python_path, os.X_OK):
        return False
    try:
        proc = subprocess.run(
            [str(python_path), "-c", "import sys; print(sys.executable)"],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except Exception:
        return False
    return proc.returncode == 0


def _python_has_pip(python_path: Path) -> bool:
    if not _python_is_runnable(python_path):
        return False
    try:
        proc = subprocess.run(
            [str(python_path), "-m", "pip", "--version"],
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )
    except Exception:
        return False
    return proc.returncode == 0


def _ensure_blue_brain_venv(workspace: Path, venv_path: Path) -> list[subprocess.CompletedProcess[str]]:
    logs: list[subprocess.CompletedProcess[str]] = []
    if not venv_path.exists():
        logs.append(_create_blue_brain_venv(venv_path, clear=False, workspace=workspace))
    elif not _python_is_runnable(_venv_python()):
        logs.append(_create_blue_brain_venv(venv_path, clear=True, workspace=workspace))

    if not _python_has_pip(_venv_python()):
        try:
            logs.append(
                subprocess.run(
                    [str(_venv_python()), "-m", "ensurepip", "--upgrade"],
                    cwd=str(workspace),
                    text=True,
                    capture_output=True,
                    timeout=120,
                    check=True,
                )
            )
        except Exception:
            logs.append(_create_blue_brain_venv(venv_path, clear=True, workspace=workspace))

    if not _python_has_pip(_venv_python()):
        raise RuntimeError(f"Blue Brain venv has no working pip after setup: {_venv_python()}")
    return logs
```

### LitGPT runtime resolving

```python
def _resolve_litgpt_source() -> Path:
    candidates = [
        os.getenv("WINTRIP_LITGPT_PATH"),
        str(_project_root() / "litgpt"),
        str(_LITGPT_DOCKER_PATH),
        str(_LITGPT_LOCAL_PATH),
    ]
    for raw in candidates:
        if not raw:
            continue
        path = Path(raw).expanduser()
        if (path / "litgpt").is_dir() and (path / "pyproject.toml").exists():
            return path.resolve()
    return _LITGPT_DOCKER_PATH


def get_litgpt_args(allow_unavailable: bool = True) -> list[str]:
    main_path = LITGPT_SOURCE_PATH / "litgpt" / "__main__.py"

    if _is_runnable(_venv_python()) and main_path.exists():
        return [str(_venv_python()), "-m", "litgpt"]
    if _script_interpreter_exists(_venv_script()):
        return [str(_venv_script())]
    system = _system_litgpt()
    if system:
        return [system]
    if _current_python_can_import_litgpt() and main_path.exists():
        return [sys.executable, "-m", "litgpt"]
    return ["litgpt"] if allow_unavailable else []
```

### Unsloth real import probe

```python
def _python_can_import_fast_language_model(python_path: Path, *, use_cache: bool = True) -> dict[str, Any]:
    if not _is_runnable(python_path):
        return {
            "ok": False,
            "python_path": str(python_path),
            "reason": "Python executable is not runnable.",
        }

    source_key = UNSLOTH_SOURCE_PATH.resolve() if UNSLOTH_SOURCE_PATH.exists() else UNSLOTH_SOURCE_PATH
    cache_key = f"{python_path.resolve()}::{source_key}"
    now = time.monotonic()
    cached = _UNSLOTH_PROBE_CACHE.get("result")
    if (
        use_cache
        and cached
        and _UNSLOTH_PROBE_CACHE.get("key") == cache_key
        and now - float(_UNSLOTH_PROBE_CACHE.get("ts") or 0.0) < _UNSLOTH_PROBE_TTL_SECONDS
    ):
        return dict(cached)

    code = "from unsloth import FastLanguageModel; print('ok')"
    try:
        proc = subprocess.run(
            [str(python_path), "-c", code],
            cwd=str(UNSLOTH_SOURCE_PATH if UNSLOTH_SOURCE_PATH.exists() else _project_root()),
            env=_unsloth_env(),
            capture_output=True,
            text=True,
            timeout=12,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        result = {
            "ok": False,
            "python_path": str(python_path),
            "reason": "Unsloth FastLanguageModel import timed out.",
            "stdout": _bounded_text(exc.stdout if isinstance(exc.stdout, str) else ""),
            "stderr": _bounded_text(exc.stderr if isinstance(exc.stderr, str) else ""),
        }
    except Exception as exc:
        result = {
            "ok": False,
            "python_path": str(python_path),
            "reason": f"Unsloth FastLanguageModel import probe failed: {exc}",
        }
    else:
        result = {
            "ok": proc.returncode == 0,
            "python_path": str(python_path),
            "returncode": proc.returncode,
            "stdout": _bounded_text(proc.stdout),
            "stderr": _bounded_text(proc.stderr),
        }
        if proc.returncode != 0:
            result["reason"] = _probe_failure_reason(proc)
        else:
            result["reason"] = "Unsloth FastLanguageModel import succeeded."

    if use_cache:
        _UNSLOTH_PROBE_CACHE.update({"key": cache_key, "ts": now, "result": dict(result)})
    return result
```

### Continuous trainer fail-closed guard

```python
if execute_training:
    if method == TrainerMethod.LITGPT.value:
        runtime = get_litgpt_status()
        if not runtime.get("runtime_ready"):
            reason = str(runtime.get("reason") or "LitGPT runtime is not executable.")
            update_job_state(job["job_id"], JobState.DATASET_READY, f"LitGPT training blocked: {reason}")
            return {
                "job_id": job["job_id"],
                "method": method,
                "base_model": base_model,
                "dataset_path": dataset_path,
                "record_count": record_count,
                "state": JobState.DATASET_READY.value,
                "training_result": {
                    "status": "blocked",
                    "reason": reason,
                    "runtime_status": runtime,
                    "fake_success": False,
                },
            }
```

### Preview/backend fallback

```bash
refresh_local_backend_pid_file() {
  local backend_pid
  backend_pid="$(
    ps -eo pid=,args= \
      | awk '$2 ~ /python/ && index($0, " -m uvicorn controller.main:app --host 0.0.0.0 --port 8010") {print $1}' \
      | tail -n 1
  )"
  [ -n "$backend_pid" ] && echo "$backend_pid" > "$BACKEND_PID_FILE"
}

ensure_backend() {
  if http_ok "$BACKEND_URL/health"; then
    refresh_local_backend_pid_file
    echo "Backend is al bereikbaar."
    return 0
  fi
  if [ "$BACKEND_MODE" != "local" ] && command -v docker >/dev/null 2>&1; then
    echo "Refreshing Docker backend and Chroma..."
    (cd "$ROOT" && docker compose up -d --build chroma ouroboros-backend)
    if wait_for_url "$BACKEND_URL/health" 90; then
      return 0
    fi
    [ "$BACKEND_MODE" = "docker" ] && fail "backend route $BACKEND_URL/health werd niet bereikbaar via Docker."
    echo "Docker backend werd niet bereikbaar; probeer lokale backend fallback."
  elif [ "$BACKEND_MODE" = "docker" ]; then
    fail "docker ontbreekt; WINTRIP_BACKEND_MODE=docker kan de backend niet starten."
  else
    echo "Docker CLI ontbreekt; probeer lokale backend fallback."
  fi
  ensure_local_backend
}
```

### Doctor localhost preservation

```python
def _remote_doctor(backend_url: str, *, preview_url: str = "", bridge_url: str = "") -> dict[str, Any] | None:
    query = {
        key: value
        for key, value in {
            "backend_url": backend_url,
            "preview_url": preview_url,
            "bridge_url": bridge_url,
        }.items()
        if value
    }
```

## Volgende stap

De meest waardevolle volgende stap is Roo job/model execution hardenen:

1. Laat Roo altijd de in Cockpit geselecteerde provider/modelconfig krijgen.
2. Laat Roo jobs echte output streamen naar `out/roo_cli_runtime`.
3. Maak job-statusen `queued -> running -> completed/failed` zichtbaar in de Cockpit.
4. Voeg tests toe voor Ollama, cloud-provider fallback en exact `Akkoord` gating.
5. Pas daarna self-build verder uitbreiden.

Daarna pas Unsloth verder debuggen op CUDA/Torch niveau.
