"""Dev-team build loop ("Aider-modus").

The dev-team meeting produces a build prompt; this module turns that build prompt into an
actual build cycle: each iteration runs De Developper → write files, De Tester → run a
test command, and (on failure) De Criticus → produce a directed fix instruction for the
next round. The loop stops on the first green test or after `max_iterations`.

All file writes and subprocess calls are confined to a sandbox workspace. The default
isolation mode is `inline` (host subprocess in a tempdir under
`data/dev-team-builds/{session_id}/`); the call sites can switch to a Docker-isolated
mode via the `isolation` parameter once the buildbox image is available.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Iterator


# Safety limits — kept conservative so a runaway LLM can't fill the disk or block the box.
MAX_FILE_BYTES = 250_000
MAX_FILES_PER_ITERATION = 16
MAX_TOTAL_WORKSPACE_BYTES = 6_000_000
DEFAULT_TEST_TIMEOUT_SECONDS = 120
MAX_TEST_OUTPUT_CHARS = 6_000
MAX_HISTORY_IN_PROMPT = 3


@dataclass
class FileWrite:
    path: str
    bytes_written: int
    truncated: bool = False


@dataclass
class TestResult:
    exit_code: int
    stdout: str
    stderr: str
    duration_s: float
    command: str
    timed_out: bool = False


@dataclass
class DevTeamBuildEvent:
    type: str
    data: dict[str, Any]


# `<file path="src/foo.py">...</file>` blocks — single or double quotes around path.
_FILE_BLOCK_PATTERN = re.compile(
    r"<file\s+path=(?P<q>['\"])(?P<path>[^'\"]+?)(?P=q)\s*>(?P<body>.*?)</file>",
    re.DOTALL,
)
# `<cmd>pytest ...</cmd>` — first match wins; one command per turn.
_CMD_BLOCK_PATTERN = re.compile(
    r"<cmd(?:\s+[^>]*)?>(?P<body>.*?)</cmd>",
    re.DOTALL,
)

_FORBIDDEN_COMMAND_FRAGMENTS = (
    "rm -rf /",
    "rm -rf ~",
    "rm -rf $home",
    "sudo ",
    " sudo\t",
    "curl ",
    "wget ",
    " nc ",
    " ssh ",
    " scp ",
    "/etc/passwd",
    "/etc/shadow",
    ">/dev/sda",
    ">/dev/null;",
    ":(){",
    "fork-bomb",
    "mkfs",
    "dd if=",
    "shutdown",
    "halt -",
    "reboot",
    "passwd ",
    "useradd",
    "usermod",
)


def extract_file_blocks(content: str) -> list[tuple[str, str]]:
    """Extract `<file path="...">...</file>` blocks from a developer turn.

    Returns a list of (path, body) tuples. Strips one leading and one trailing newline
    from the body so the LLM can wrap the code in newlines without bloating the file.
    """
    blocks: list[tuple[str, str]] = []
    for match in _FILE_BLOCK_PATTERN.finditer(content or ""):
        path = match.group("path").strip()
        body = match.group("body")
        if body.startswith("\r\n"):
            body = body[2:]
        elif body.startswith("\n"):
            body = body[1:]
        if body.endswith("\r\n"):
            body = body[:-2]
        elif body.endswith("\n"):
            body = body[:-1]
        if path:
            blocks.append((path, body))
    return blocks


def extract_cmd_block(content: str) -> str:
    """Extract the first `<cmd>...</cmd>` block (one command per tester turn)."""
    match = _CMD_BLOCK_PATTERN.search(content or "")
    if not match:
        return ""
    body = match.group("body").strip()
    # Reject multi-line commands — we run via `sh -c` and a stray newline can introduce
    # surprising behaviour. Pick the first non-empty line.
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    if not lines:
        return ""
    return lines[0]


def _safe_workspace_join(workspace: Path, target: str) -> Path:
    """Resolve `target` relative to `workspace`, refusing to escape with '..' or absolute paths."""
    raw = str(target or "").strip()
    if not raw:
        raise ValueError("Empty path")
    if "\x00" in raw or "\n" in raw or "\r" in raw:
        raise ValueError("Invalid path characters")
    # Refuse absolute paths outright — we never want a developer turn to be able to write
    # to /etc/passwd by accident, even with the workspace anchor.
    if raw.startswith("/") or raw.startswith("\\") or (len(raw) >= 2 and raw[1] == ":"):
        raise ValueError(f"Absolute path '{raw}' not allowed")
    candidate = (workspace / raw).resolve()
    workspace_resolved = workspace.resolve()
    try:
        candidate.relative_to(workspace_resolved)
    except ValueError as exc:
        raise ValueError(f"Path '{raw}' escapes the workspace.") from exc
    return candidate


def write_files(
    workspace: Path,
    blocks: list[tuple[str, str]],
    *,
    max_file_bytes: int = MAX_FILE_BYTES,
    max_files: int = MAX_FILES_PER_ITERATION,
    max_total_bytes: int = MAX_TOTAL_WORKSPACE_BYTES,
) -> list[FileWrite]:
    """Write `(path, content)` blocks to the workspace safely, returning what landed on disk."""
    workspace.mkdir(parents=True, exist_ok=True)
    writes: list[FileWrite] = []
    truncated_blocks = blocks[:max_files]
    current_total = sum(
        path.stat().st_size for path in workspace.rglob("*") if path.is_file()
    )
    for path_raw, body in truncated_blocks:
        try:
            target = _safe_workspace_join(workspace, path_raw)
        except ValueError:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        encoded = body.encode("utf-8")
        truncated = False
        if len(encoded) > max_file_bytes:
            encoded = encoded[:max_file_bytes]
            truncated = True
        # Honour the global workspace budget; stop adding files when exceeded.
        if current_total + len(encoded) > max_total_bytes:
            break
        target.write_bytes(encoded)
        current_total += len(encoded)
        rel = str(target.relative_to(workspace.resolve()))
        writes.append(FileWrite(path=rel, bytes_written=len(encoded), truncated=truncated))
    return writes


def _is_safe_command(cmd: str) -> bool:
    """Reject obviously dangerous shell snippets before subprocess.run."""
    if not cmd:
        return False
    lowered = " " + cmd.lower() + " "
    if any(fragment in lowered for fragment in _FORBIDDEN_COMMAND_FRAGMENTS):
        return False
    if "\x00" in cmd:
        return False
    return True


def run_test_command(
    workspace: Path,
    command: str,
    *,
    timeout: float = DEFAULT_TEST_TIMEOUT_SECONDS,
    extra_env: dict[str, str] | None = None,
) -> TestResult:
    """Run `command` in `workspace` and capture stdout/stderr.

    The command is executed via `sh -c` from within the workspace directory. Output is
    truncated to `MAX_TEST_OUTPUT_CHARS` per stream so a chatty test framework can't
    blow up the SSE event payload.
    """
    if not command or not command.strip():
        return TestResult(exit_code=-1, stdout="", stderr="(empty command)", duration_s=0.0, command="")
    if not _is_safe_command(command):
        return TestResult(
            exit_code=-2,
            stdout="",
            stderr=f"Command rejected for safety: {command!r}",
            duration_s=0.0,
            command=command,
        )
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if extra_env:
        env.update(extra_env)
    started = time.time()
    try:
        proc = subprocess.run(
            ["sh", "-c", command],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return TestResult(
            exit_code=-3,
            stdout="",
            stderr=f"Command timed out after {timeout:.0f}s",
            duration_s=time.time() - started,
            command=command,
            timed_out=True,
        )
    except Exception as exc:  # noqa: BLE001
        return TestResult(
            exit_code=-4,
            stdout="",
            stderr=f"Command failed to start: {exc}",
            duration_s=time.time() - started,
            command=command,
        )
    return TestResult(
        exit_code=proc.returncode,
        stdout=(proc.stdout or "")[:MAX_TEST_OUTPUT_CHARS],
        stderr=(proc.stderr or "")[:MAX_TEST_OUTPUT_CHARS],
        duration_s=time.time() - started,
        command=command,
    )


class DevTeamBuildSession:
    """Iterative dev-team build session.

    `iterate(...)` is a generator that yields `DevTeamBuildEvent` instances as the build
    progresses. The caller is expected to forward them as SSE chunks or persist them.
    """

    def __init__(
        self,
        *,
        session_id: str,
        workspace: Path,
        llm_call: Callable[..., Any],
        max_iterations: int = 4,
        test_timeout: float = DEFAULT_TEST_TIMEOUT_SECONDS,
    ):
        self.session_id = session_id
        self.workspace = workspace
        self.llm_call = llm_call
        self.max_iterations = max(1, min(int(max_iterations), 12))
        self.test_timeout = test_timeout
        self.iteration_log: list[dict[str, Any]] = []

    def iterate(
        self,
        *,
        build_prompt: str,
        clarifications: list[dict[str, str]] | None,
        provider: str,
        model: str,
        personas: dict[str, dict[str, Any]],
    ) -> Iterator[DevTeamBuildEvent]:
        clarifications = clarifications or []
        yield DevTeamBuildEvent(
            "build_started",
            {
                "session_id": self.session_id,
                "workspace_path": str(self.workspace),
                "max_iterations": self.max_iterations,
                "build_prompt_preview": build_prompt[:480],
            },
        )

        last_test_result: TestResult | None = None

        for iteration in range(1, self.max_iterations + 1):
            iteration_data: dict[str, Any] = {
                "iteration": iteration,
                "files_written": [],
                "test_result": None,
                "critic_feedback": "",
            }

            # ---- Developer turn ----
            dev_persona = personas.get("developer") or {}
            dev_response = self._call_llm(
                user_prompt=self._developer_user_prompt(
                    build_prompt=build_prompt,
                    clarifications=clarifications,
                    iteration=iteration,
                ),
                system_prompt=self._developer_system_prompt(dev_persona),
                provider=provider,
                model=model,
                persona=dev_persona,
            )
            dev_content = (dev_response.get("content") or "").strip()
            yield DevTeamBuildEvent(
                "developer_turn",
                {
                    "iteration": iteration,
                    "content": dev_content,
                    "ok": bool(dev_response.get("ok")),
                    "error": str(dev_response.get("error") or ""),
                },
            )

            file_blocks = extract_file_blocks(dev_content)
            file_writes = write_files(self.workspace, file_blocks)
            iteration_data["files_written"] = [asdict(w) for w in file_writes]
            yield DevTeamBuildEvent(
                "files_written",
                {
                    "iteration": iteration,
                    "files": [asdict(w) for w in file_writes],
                    "block_count": len(file_blocks),
                },
            )

            # ---- Tester turn ----
            tester_persona = personas.get("tester") or {}
            tester_response = self._call_llm(
                user_prompt=self._tester_user_prompt(
                    build_prompt=build_prompt,
                    last_developer=dev_content,
                    files_written=file_writes,
                    iteration=iteration,
                ),
                system_prompt=self._tester_system_prompt(tester_persona),
                provider=provider,
                model=model,
                persona=tester_persona,
            )
            tester_content = (tester_response.get("content") or "").strip()
            yield DevTeamBuildEvent(
                "tester_turn",
                {
                    "iteration": iteration,
                    "content": tester_content,
                    "ok": bool(tester_response.get("ok")),
                    "error": str(tester_response.get("error") or ""),
                },
            )

            command = extract_cmd_block(tester_content) or self._guess_default_test_command(file_writes)
            test_result = run_test_command(self.workspace, command, timeout=self.test_timeout)
            last_test_result = test_result
            iteration_data["test_result"] = asdict(test_result)
            yield DevTeamBuildEvent(
                "test_run",
                {
                    "iteration": iteration,
                    "command": command,
                    "exit_code": test_result.exit_code,
                    "stdout": test_result.stdout,
                    "stderr": test_result.stderr,
                    "duration_s": test_result.duration_s,
                    "timed_out": test_result.timed_out,
                    "green": test_result.exit_code == 0,
                },
            )

            self.iteration_log.append(iteration_data)

            if test_result.exit_code == 0:
                yield DevTeamBuildEvent(
                    "build_complete",
                    {
                        "iterations": iteration,
                        "workspace_path": str(self.workspace),
                        "last_command": command,
                    },
                )
                return

            # ---- Criticus turn (only on failure) ----
            critic_persona = personas.get("criticus") or {}
            critic_response = self._call_llm(
                user_prompt=self._criticus_user_prompt(
                    build_prompt=build_prompt,
                    developer_content=dev_content,
                    tester_content=tester_content,
                    test_result=test_result,
                    iteration=iteration,
                ),
                system_prompt=self._criticus_system_prompt(critic_persona),
                provider=provider,
                model=model,
                persona=critic_persona,
            )
            critic_content = (critic_response.get("content") or "").strip()
            iteration_data["critic_feedback"] = critic_content
            yield DevTeamBuildEvent(
                "critic_turn",
                {
                    "iteration": iteration,
                    "content": critic_content,
                    "ok": bool(critic_response.get("ok")),
                    "error": str(critic_response.get("error") or ""),
                },
            )

        yield DevTeamBuildEvent(
            "build_exhausted",
            {
                "iterations": self.max_iterations,
                "workspace_path": str(self.workspace),
                "last_test_result": asdict(last_test_result) if last_test_result else None,
            },
        )

    # ------------------------------------------------------------------
    # LLM glue
    # ------------------------------------------------------------------
    def _call_llm(
        self,
        *,
        user_prompt: str,
        system_prompt: str,
        provider: str,
        model: str,
        persona: dict[str, Any],
    ) -> dict[str, Any]:
        model_settings = persona.get("model_settings") if isinstance(persona.get("model_settings"), dict) else {}
        chosen_provider = str(model_settings.get("provider") or provider or "ollama").strip().lower() or "ollama"
        chosen_model = str(model_settings.get("name") or model or "ouroboros:latest").strip() or "ouroboros:latest"
        try:
            result = self.llm_call(
                prompt=user_prompt,
                provider=chosen_provider,
                model=chosen_model,
                system_prompt=system_prompt,
                history=[],
                images=[],
            )
        except TypeError:
            try:
                result = self.llm_call(
                    prompt=user_prompt,
                    model=chosen_model,
                    system_prompt=system_prompt,
                    history=[],
                )
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "content": "", "error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "content": "", "error": str(exc)}
        if isinstance(result, dict):
            content = str(result.get("content") or result.get("response") or "").strip()
            return {
                "ok": bool(result.get("ok", True)) and bool(content),
                "content": content,
                "error": str(result.get("error") or ""),
            }
        content = str(result or "").strip()
        return {"ok": bool(content), "content": content, "error": ""}

    # ------------------------------------------------------------------
    # Prompt builders
    # ------------------------------------------------------------------
    def _developer_system_prompt(self, persona: dict[str, Any]) -> str:
        base = str(persona.get("system_prompt") or "").strip()
        return (
            (base + "\n\n" if base else "")
            + "BOUWMODE: je werkt nu binnen een Aider-style build-loop. Bij elke beurt mag je "
              "code schrijven in een sandbox door je output op te splitsen in "
              "`<file path=\"...\">...</file>` blokken. ELK blok wordt LETTERLIJK naar disk "
              "geschreven; de inhoud van het blok VERVANGT de file volledig. Schrijf alleen "
              "nieuwe of gewijzigde files. Houd files compleet en self-contained.\n\n"
              "Vorm van je antwoord (vrij format buiten de blokken):\n"
              "1. 1-3 zinnen over wat je in deze iteratie bouwt.\n"
              "2. Een of meerdere `<file path=\"...\">...</file>` blokken met de werkelijke code.\n"
              "3. Een korte vraag aan De Tester over hoe te testen.\n\n"
              "Voorbeeld:\n"
              "Ik begin met de skeleton.\n"
              "<file path=\"src/cli.py\">\n"
              "#!/usr/bin/env python3\n"
              "def main():\n"
              "    print(\"hello\")\n"
              "</file>\n"
              "<file path=\"tests/test_cli.py\">\n"
              "from src.cli import main\n"
              "def test_main_prints_hello(capsys):\n"
              "    main()\n"
              "    assert \"hello\" in capsys.readouterr().out\n"
              "</file>\n"
              "Vraag aan De Tester: wil je ook stderr afdekken?\n\n"
              "Harde regels: geen markdown om de file-blokken (geen ```), geen tekst tussen "
              "`<file>` en `</file>` behalve de file-inhoud. Bij ontbrekende afhankelijkheden: "
              "voeg een `requirements.txt` blok toe en noem het in je context-zin. Begin niet "
              "met je eigen naam."
        )

    def _tester_system_prompt(self, persona: dict[str, Any]) -> str:
        base = str(persona.get("system_prompt") or "").strip()
        return (
            (base + "\n\n" if base else "")
            + "BOUWMODE: De Developper heeft net files geschreven. Bepaal het testcommando "
              "dat het bouwdoel bewijst en draai het mentaal door. Je MOET het commando in een "
              "`<cmd>...</cmd>` blok zetten — één regel, idempotent, draait vanaf de "
              "workspace-root.\n\n"
              "Voorbeeld antwoord:\n"
              "Test de hello-path met pytest.\n"
              "<cmd>python -m pytest tests/test_cli.py -v</cmd>\n"
              "Verwacht: exit 0 met `1 passed`.\n"
              "Faal: assertion of import error.\n\n"
              "Harde regels: één `<cmd>` blok per beurt, geen `sudo`, geen netwerk-tools "
              "(`curl`, `wget`, `ssh`), geen destructieve commando's (`rm -rf /`). Voor Python "
              "test-runs gebruik `python -m pytest ...` zodat de workspace op sys.path komt."
        )

    def _criticus_system_prompt(self, persona: dict[str, Any]) -> str:
        base = str(persona.get("system_prompt") or "").strip()
        return (
            (base + "\n\n" if base else "")
            + "BOUWMODE: je leest de stdout/stderr van het laatst gedraaide testcommando. "
              "Geef De Developper een gerichte fix-opdracht in MAXIMAAL 4 zinnen: (1) oorzaak "
              "van de fout, (2) welke file/symbol raakt het, (3) kleinste wijziging die het "
              "groen maakt, (4) optioneel: een edge case die nog mist. Lees de stderr "
              "LETTERLIJK; verzin geen fouten die er niet staan."
        )

    def _developer_user_prompt(
        self,
        *,
        build_prompt: str,
        clarifications: list[dict[str, str]],
        iteration: int,
    ) -> str:
        parts = [f"Bouwdoel (iteratie {iteration}):\n{build_prompt}"]
        if clarifications:
            qa = "\n".join(
                f"- {item.get('question','')}\n  Antwoord: {item.get('answer','')}"
                for item in clarifications
                if isinstance(item, dict) and str(item.get("answer") or "").strip()
            )
            if qa:
                parts.append(f"Verduidelijking van de gebruiker:\n{qa}")
        if self.iteration_log:
            log_lines = []
            for entry in self.iteration_log[-MAX_HISTORY_IN_PROMPT:]:
                it = entry.get("iteration")
                files = entry.get("files_written", []) or []
                test = entry.get("test_result") or {}
                feedback = entry.get("critic_feedback", "")
                log_lines.append(f"\nIteratie {it}:")
                log_lines.append(
                    "  Files geschreven: " + (", ".join(f.get("path", "") for f in files) or "(geen)")
                )
                log_lines.append(f"  Test exit: {test.get('exit_code')}")
                stderr = (test.get("stderr") or "").strip()
                if stderr:
                    log_lines.append("  Stderr:\n    " + stderr[:1200].replace("\n", "\n    "))
                stdout = (test.get("stdout") or "").strip()
                if stdout and not stderr:
                    log_lines.append("  Stdout:\n    " + stdout[:600].replace("\n", "\n    "))
                if feedback:
                    log_lines.append(f"  Criticus zei: {feedback[:600]}")
            parts.append("Werkhistorie:" + "".join(log_lines))
        parts.append(
            "Schrijf nu je beurt: 1-3 zinnen context, dan een of meer "
            "`<file path=\"...\">...</file>` blokken. Houd files compleet."
        )
        return "\n\n".join(parts)

    def _tester_user_prompt(
        self,
        *,
        build_prompt: str,
        last_developer: str,
        files_written: list[FileWrite],
        iteration: int,
    ) -> str:
        files_block = ", ".join(item.path for item in files_written) or "(geen files geschreven)"
        return (
            f"Bouwdoel: {build_prompt}\n\n"
            f"Iteratie {iteration} — De Developper schreef: {files_block}.\n\n"
            f"Zijn beurt was:\n{last_developer[:2400]}\n\n"
            "Geef nu in 2-3 zinnen het testcommando, met `<cmd>...</cmd>`. Eén regel, "
            "idempotent vanaf de workspace-root."
        )

    def _criticus_user_prompt(
        self,
        *,
        build_prompt: str,
        developer_content: str,
        tester_content: str,
        test_result: TestResult,
        iteration: int,
    ) -> str:
        return (
            f"Bouwdoel: {build_prompt}\n\n"
            f"Iteratie {iteration}: de test faalde.\n"
            f"Commando: {test_result.command}\n"
            f"Exit code: {test_result.exit_code}\n"
            f"Stdout (geclipt):\n{test_result.stdout[:1600] or '(leeg)'}\n\n"
            f"Stderr (geclipt):\n{test_result.stderr[:1600] or '(leeg)'}\n\n"
            f"De Developper schreef:\n{developer_content[:1600]}\n\n"
            f"De Tester wilde:\n{tester_content[:800]}\n\n"
            "Geef nu De Developper een gerichte fix-opdracht (maximaal 4 zinnen)."
        )

    def _guess_default_test_command(self, files: list[FileWrite]) -> str:
        """Pick a sensible default if the Tester didn't emit a <cmd> block."""
        for item in files:
            lower = item.path.lower()
            if lower.endswith(".py") and "test" in lower:
                return f"python -m pytest {item.path} -v"
        if any(item.path.endswith(".py") for item in files):
            return "python -m pytest -v"
        return "ls -la"


def new_build_session_id() -> str:
    return f"{int(time.time())}-{uuid.uuid4().hex[:10]}"


def workspace_for(session_id: str, root: Path) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", session_id).strip("-") or new_build_session_id()
    return (root / safe).resolve()


def cleanup_workspace(workspace: Path) -> None:
    """Best-effort cleanup of a build workspace."""
    try:
        shutil.rmtree(workspace)
    except FileNotFoundError:
        return
    except OSError:
        return
