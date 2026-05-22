"""Isolated Ouroboros Development Team build loop.

The Meeting layer may produce a formal build_plan, but this module owns the
Development Team runtime. It does not reuse Meeting personas or Meeting prompts.
Each iteration runs Voorman -> Ontwerper -> Developper -> Tester -> Criticus so
small local models get explicit handoffs instead of implicit context guessing.

All file writes and subprocess calls are confined to a sandbox workspace. The default
isolation mode is `inline` (host subprocess in a tempdir under
`data/dev-team-builds/{session_id}/`); the call sites can switch to a Docker-isolated
mode via the `isolation` parameter once the buildbox image is available.
"""

from __future__ import annotations

import os
import re
import json
import shutil
import subprocess
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
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
MAX_TEAM_BUS_MESSAGES = 10


DEVELOPMENT_AGENT_ROLE_ORDER: tuple[str, ...] = (
    "foreman",
    "designer",
    "developer",
    "tester",
    "criticus",
)


DEFAULT_DEVELOPMENT_TEAM_AGENTS: dict[str, dict[str, Any]] = {
    "foreman": {
        "id": "dev-voorman",
        "name": "Voorman",
        "role": "Development Team foreman and iteration owner",
        "system_prompt": (
            "Je bent Voorman van OUROBOROS DEVELOPMENT TEAM. Je bent geen Meeting-persona. "
            "Je ontvangt alleen het formele build_plan en de laatste teststatus.\n\n"
            "Jouw taak is werk klein maken en communicatie afdwingen. Geef per iteratie exact een "
            "handoffkaart met deze regels:\n"
            "SUBTASK: de ene kleinste bouwstap voor deze iteratie.\n"
            "DONE_CRITERION: het concrete bewijs dat deze stap klaar is.\n"
            "TO_ONTWERPER: wat de Ontwerper moet vastleggen.\n"
            "TO_DEVELOPPER: wat de Developper daarna moet wijzigen.\n"
            "TO_TESTER: welk bewijs de Tester moet leveren.\n\n"
            "Regels: verwijs naar build_plan.goals/components/tests; geen overlegtaal, geen mystiek, "
            "geen Meeting-context, geen shellcommando's. Schrijf voor kleine modellen: kort, concreet, "
            "herhaal de file/componentnaam als die bekend is."
        ),
    },
    "designer": {
        "id": "dev-ontwerper",
        "name": "Ontwerper",
        "role": "Development Team design contract author",
        "system_prompt": (
            "Je bent Ontwerper van OUROBOROS DEVELOPMENT TEAM. Je bent geen Meeting-persona. "
            "Je maakt van de Voorman-subtask een ontwerpcontract waar De Developper direct mee kan bouwen.\n\n"
            "Antwoord met maximaal vijf korte regels:\n"
            "CONTRACT: wat moet de gebruiker of caller merken.\n"
            "FILES: verwachte file(s) of component(en).\n"
            "INTERFACE: CLI/API/UI/functiecontract en input/output.\n"
            "TEST_HOOK: hoe De Tester dit mechanisch bewijst.\n"
            "TO_DEVELOPPER: directe bouwinstructie in één zin.\n\n"
            "Gebruik AgenK-stijl taaktoewijzing: één agent, één taak, één verwacht resultaat. "
            "Geen brede architectuurpraat en geen Meeting-taal."
        ),
    },
    "developer": {
        "id": "dev-developper",
        "name": "De Developper",
        "role": "Development Team code author",
        "system_prompt": (
            "Je bent De Developper van OUROBOROS DEVELOPMENT TEAM. Je bent geen Meeting-persona. "
            "Je bouwt alleen in de sandbox workspace.\n\n"
            "Gebruik Aider-discipline: kleine edits, concrete paden, bestaande conventies respecteren. "
            "Schrijf bij voorkeur `<diff path=\"...\">` blokken met Aider SEARCH/REPLACE inhoud. "
            "Voor nieuwe kleine files mag `<file path=\"...\">...</file>` ook, zodat kleine modellen betrouwbaar blijven.\n\n"
            "Communicatie is verplicht: begin met één korte zin aan Voorman/Ontwerper, daarna alleen editblokken, "
            "en sluit af met één korte overdracht aan De Tester. Geen markdown fences rond editblokken."
        ),
    },
    "tester": {
        "id": "dev-tester",
        "name": "De Tester",
        "role": "Development Team verification gate",
        "system_prompt": (
            "Je bent De Tester van OUROBOROS DEVELOPMENT TEAM. Je bent geen Meeting-persona. "
            "Je bewijst de laatste edit mechanisch.\n\n"
            "Output is streng: één korte regel aan De Developper, precies één `<cmd>...</cmd>` blok, "
            "en één korte regel met verwacht groen signaal. Geen extra commando's. Geen netwerk, geen sudo, "
            "geen destructieve acties. Kies het kleinste acceptance-commando uit build_plan.tests of uit de geschreven files."
        ),
    },
    "criticus": {
        "id": "dev-critikus",
        "name": "Critikus",
        "role": "Development Team failure analyst",
        "system_prompt": (
            "Je bent Critikus van OUROBOROS DEVELOPMENT TEAM. Je bent geen Meeting-persona. "
            "Je leest alleen de laatste testoutput en geeft één concrete fixopdracht.\n\n"
            "Antwoord in maximaal vier zinnen: oorzaak, geraakt bestand/symbol, kleinste fix, en welk testcommando "
            "daarna opnieuw moet draaien. Lees stderr/stdout letterlijk. Geen brede review, geen nieuwe features."
        ),
    },
}


@dataclass
class FileWrite:
    path: str
    bytes_written: int
    truncated: bool = False
    edit_format: str = "file"
    error: str = ""


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


# `<file path="src/foo.py">...</file>` blocks — permissive of missing quotes.
_FILE_BLOCK_PATTERN = re.compile(
    r"<file\s+path=(?:['\"](?P<path_q>[^'\"]+?)['\"]|(?P<path_uq>[^\s>]+))[^>]*>(?P<body>.*?)</file>",
    re.DOTALL,
)
# `<diff path="src/foo.py">...</diff>` blocks. The body accepts a compact Aider
# SEARCH/REPLACE block, a tiny unified-diff-like hunk, or plain replacement content.
_DIFF_BLOCK_PATTERN = re.compile(
    r"<diff\s+path=(?:['\"](?P<path_q>[^'\"]+?)['\"]|(?P<path_uq>[^\s>]+))[^>]*>(?P<body>.*?)</diff>",
    re.DOTALL,
)
_SEARCH_REPLACE_PATTERN = re.compile(
    r"<<<<<<< SEARCH\n(?P<search>.*?)(?:\n)?=======\n(?P<replace>.*?)\n>>>>>>> REPLACE",
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


def default_development_team_agents() -> dict[str, dict[str, Any]]:
    """Return fresh, Meeting-independent default agents for the build runtime."""
    return {role: dict(DEFAULT_DEVELOPMENT_TEAM_AGENTS[role]) for role in DEVELOPMENT_AGENT_ROLE_ORDER}


def extract_file_blocks(content: str) -> list[tuple[str, str]]:
    """Extract `<file path="...">...</file>` blocks from a developer turn.

    Returns a list of (path, body) tuples. Strips one leading and one trailing newline
    from the body so the LLM can wrap the code in newlines without bloating the file.
    """
    blocks: list[tuple[str, str]] = []
    for match in _FILE_BLOCK_PATTERN.finditer(content or ""):
        path = (match.group("path_q") or match.group("path_uq") or "").strip()
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


def extract_diff_blocks(content: str) -> list[tuple[str, str]]:
    """Extract `<diff path="...">...</diff>` blocks from a developer turn."""
    blocks: list[tuple[str, str]] = []
    for match in _DIFF_BLOCK_PATTERN.finditer(content or ""):
        path = (match.group("path_q") or match.group("path_uq") or "").strip()
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


def _content_from_additive_diff(body: str) -> str:
    """Best-effort support for tiny Aider/unified-diff-style additive hunks.

    This intentionally handles only the reliable subset small models tend to emit:
    lines starting with `+` are additions, while headers (`+++`, `---`, `@@`) and
    removed/context lines are ignored. Existing-file replacements should use
    SEARCH/REPLACE blocks for exactness.
    """
    added: list[str] = []
    for raw_line in (body or "").splitlines():
        if raw_line.startswith(("+++", "---", "@@")):
            continue
        if raw_line.startswith("+"):
            added.append(raw_line[1:])
    return "\n".join(added)


def apply_diff_blocks(
    workspace: Path,
    blocks: list[tuple[str, str]],
    *,
    max_file_bytes: int = MAX_FILE_BYTES,
    max_files: int = MAX_FILES_PER_ITERATION,
    max_total_bytes: int = MAX_TOTAL_WORKSPACE_BYTES,
) -> list[FileWrite]:
    """Apply small `<diff>` blocks inside the sandbox.

    Supported formats:
    - Aider SEARCH/REPLACE blocks inside `<diff path="...">`.
    - Additive unified-diff-like hunks with `+` lines.
    - Plain body content, treated as full-file replacement for new/small files.
    """
    workspace.mkdir(parents=True, exist_ok=True)
    writes: list[FileWrite] = []
    current_total = sum(path.stat().st_size for path in workspace.rglob("*") if path.is_file())
    for path_raw, body in blocks[:max_files]:
        try:
            target = _safe_workspace_join(workspace, path_raw)
        except ValueError as exc:
            writes.append(FileWrite(path=str(path_raw), bytes_written=0, edit_format="diff", error=str(exc)))
            continue

        existing = target.read_text(encoding="utf-8") if target.exists() and target.is_file() else ""
        new_content = existing
        edit_error = ""
        replacements = list(_SEARCH_REPLACE_PATTERN.finditer(body or ""))
        if replacements:
            for match in replacements:
                search = match.group("search")
                replace = match.group("replace")
                if search == "":
                    new_content = replace
                    continue
                if search not in new_content:
                    edit_error = f"SEARCH block did not match {path_raw}"
                    break
                new_content = new_content.replace(search, replace, 1)
        else:
            additive = _content_from_additive_diff(body)
            if additive:
                separator = "" if not existing or existing.endswith("\n") else "\n"
                new_content = f"{existing}{separator}{additive}"
            else:
                new_content = body

        if edit_error:
            writes.append(FileWrite(path=str(path_raw), bytes_written=0, edit_format="diff", error=edit_error))
            continue

        encoded = new_content.encode("utf-8")
        truncated = False
        if len(encoded) > max_file_bytes:
            encoded = encoded[:max_file_bytes]
            truncated = True
        previous_size = target.stat().st_size if target.exists() and target.is_file() else 0
        projected_total = current_total - previous_size + len(encoded)
        if projected_total > max_total_bytes:
            writes.append(
                FileWrite(path=str(path_raw), bytes_written=0, edit_format="diff", error="workspace byte budget exceeded")
            )
            break
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(encoded)
        current_total = projected_total
        writes.append(
            FileWrite(
                path=str(target.relative_to(workspace.resolve())),
                bytes_written=len(encoded),
                truncated=truncated,
                edit_format="diff",
            )
        )
    return writes


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


def apply_developer_edits(workspace: Path, content: str) -> tuple[list[FileWrite], int, int]:
    """Apply developer `<diff>` and legacy `<file>` blocks.

    Returns `(writes, diff_count, file_count)`. Diff blocks are preferred because
    they preserve the Aider-style small-edit contract; file blocks remain as a
    compatibility fallback for small local models and existing tests.
    """
    diff_blocks = extract_diff_blocks(content)
    file_blocks = extract_file_blocks(content)
    writes: list[FileWrite] = []
    if diff_blocks:
        writes.extend(apply_diff_blocks(workspace, diff_blocks))
    if file_blocks:
        writes.extend(write_files(workspace, file_blocks))
    return writes, len(diff_blocks), len(file_blocks)


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


def normalize_build_plan(value: Any, *, fallback_title: str = "") -> dict[str, Any]:
    """Normalize the formal build_plan object used between Meeting and Development."""
    if isinstance(value, str):
        text = value.strip()
        if text:
            try:
                value = json.loads(text)
            except Exception:
                value = {"title": fallback_title or text[:160], "goals": [text]}
        else:
            value = {}
    if not isinstance(value, dict):
        value = {}

    def _string_list(raw: Any) -> list[str]:
        if isinstance(raw, list):
            return [str(item).strip()[:500] for item in raw if str(item or "").strip()]
        if str(raw or "").strip():
            return [str(raw).strip()[:500]]
        return []

    def _component_list(raw: Any) -> list[dict[str, str]]:
        components: list[dict[str, str]] = []
        if isinstance(raw, list):
            for index, item in enumerate(raw[:12], start=1):
                if isinstance(item, dict):
                    name = str(item.get("name") or item.get("path") or f"component_{index}").strip()[:120]
                    description = str(item.get("description") or item.get("summary") or name).strip()[:400]
                else:
                    name = str(item or "").strip()[:120]
                    description = name
                if name:
                    components.append({"name": name, "description": description})
        return components

    title = str(value.get("title") or fallback_title or "Ouroboros build").strip()[:160]
    goals = _string_list(value.get("goals")) or [title]
    components = _component_list(value.get("components")) or [{"name": "implementation", "description": title}]
    tests = _string_list(value.get("tests")) or ["Draai het kleinste relevante testcommando en verwacht exitcode 0."]
    constraints = _string_list(value.get("constraints")) or ["Geen externe acties zonder expliciete toestemming."]
    return {
        "title": title,
        "goals": goals[:8],
        "components": components[:12],
        "tests": tests[:8],
        "constraints": constraints[:8],
    }


def format_build_plan(build_plan: dict[str, Any]) -> str:
    return json.dumps(normalize_build_plan(build_plan), ensure_ascii=False, indent=2, sort_keys=True)


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
        min_iterations: int = 2,
        test_timeout: float = DEFAULT_TEST_TIMEOUT_SECONDS,
        llm_timeout_seconds: float = 90.0,
    ):
        self.session_id = session_id
        self.workspace = workspace
        self.llm_call = llm_call
        self.max_iterations = max(1, min(int(max_iterations), 12))
        self.min_iterations = max(1, min(int(min_iterations), self.max_iterations))
        self.test_timeout = test_timeout
        self.llm_timeout_seconds = max(5.0, float(llm_timeout_seconds))
        self.iteration_log: list[dict[str, Any]] = []

    def iterate(
        self,
        *,
        build_prompt: str,
        build_plan: Any | None = None,
        clarifications: list[dict[str, str]] | None,
        provider: str,
        model: str,
        personas: dict[str, dict[str, Any]],
    ) -> Iterator[DevTeamBuildEvent]:
        clarifications = clarifications or []
        plan = normalize_build_plan(build_plan if build_plan is not None else build_prompt, fallback_title=build_prompt[:160])
        build_prompt = format_build_plan(plan)
        agents = self._merge_development_agents(personas)
        yield DevTeamBuildEvent(
            "build_started",
            {
                "session_id": self.session_id,
                "workspace_path": str(self.workspace),
                "max_iterations": self.max_iterations,
                "build_plan": plan,
                "development_agents": [
                    {"role": role, "id": agents[role].get("id"), "name": agents[role].get("name")}
                    for role in DEVELOPMENT_AGENT_ROLE_ORDER
                    if role in agents
                ],
                "build_prompt_preview": build_prompt[:480],
            },
        )

        last_test_result: TestResult | None = None
        chat_history: list[dict[str, str]] = []

        for iteration in range(1, self.max_iterations + 1):
            iteration_data: dict[str, Any] = {
                "iteration": iteration,
                "files_written": [],
                "test_result": None,
                "critic_feedback": "",
                "foreman_handoff": "",
                "designer_contract": "",
            }

            # ---- Voorman turn ----
            foreman_persona = agents.get("foreman") or {}
            foreman_response = self._call_llm(
                user_prompt=self._foreman_user_prompt(
                    build_plan=plan,
                    clarifications=clarifications,
                    iteration=iteration,
                    last_test_result=last_test_result,
                ),
                system_prompt=self._foreman_system_prompt(foreman_persona),
                provider=provider,
                model=model,
                persona=foreman_persona,
                history=self._recent_team_history(chat_history),
            )
            foreman_content = (foreman_response.get("content") or "").strip()
            if not foreman_content:
                foreman_content = self._fallback_foreman_turn(plan, iteration)
            iteration_data["foreman_handoff"] = foreman_content
            chat_history.append(self._team_message("Voorman", "Ontwerper/Developper/Tester/Critikus", foreman_content))
            yield DevTeamBuildEvent(
                "foreman_turn",
                {
                    "iteration": iteration,
                    "content": foreman_content,
                    "ok": bool(foreman_response.get("ok")) or bool(foreman_content),
                    "error": str(foreman_response.get("error") or ""),
                },
            )

            # ---- Ontwerper turn ----
            designer_persona = agents.get("designer") or {}
            designer_response = self._call_llm(
                user_prompt=self._designer_user_prompt(
                    build_plan=plan,
                    foreman_handoff=foreman_content,
                    iteration=iteration,
                ),
                system_prompt=self._designer_system_prompt(designer_persona),
                provider=provider,
                model=model,
                persona=designer_persona,
                history=self._recent_team_history(chat_history),
            )
            designer_content = (designer_response.get("content") or "").strip()
            if not designer_content:
                designer_content = self._fallback_designer_turn(plan, foreman_content, iteration)
            iteration_data["designer_contract"] = designer_content
            chat_history.append(self._team_message("Ontwerper", "Developper/Tester/Critikus", designer_content))
            yield DevTeamBuildEvent(
                "designer_turn",
                {
                    "iteration": iteration,
                    "content": designer_content,
                    "ok": bool(designer_response.get("ok")) or bool(designer_content),
                    "error": str(designer_response.get("error") or ""),
                },
            )

            # ---- Developer turn ----
            dev_persona = agents.get("developer") or {}
            dev_response = self._call_llm(
                user_prompt=self._developer_user_prompt(
                    build_prompt=build_prompt,
                    build_plan=plan,
                    foreman_handoff=foreman_content,
                    designer_contract=designer_content,
                    clarifications=clarifications,
                    iteration=iteration,
                ),
                system_prompt=self._developer_system_prompt(dev_persona),
                provider=provider,
                model=model,
                persona=dev_persona,
                history=self._recent_team_history(chat_history),
            )
            dev_content = (dev_response.get("content") or "").strip()
            if dev_content:
                chat_history.append(self._team_message("Developper", "Tester/Critikus", dev_content))
            yield DevTeamBuildEvent(
                "developer_turn",
                {
                    "iteration": iteration,
                    "content": dev_content,
                    "ok": bool(dev_response.get("ok")),
                    "error": str(dev_response.get("error") or ""),
                },
            )

            file_writes, diff_count, file_count = apply_developer_edits(self.workspace, dev_content)
            iteration_data["files_written"] = [asdict(w) for w in file_writes]
            yield DevTeamBuildEvent(
                "files_written",
                {
                    "iteration": iteration,
                    "files": [asdict(w) for w in file_writes],
                    "block_count": diff_count + file_count,
                    "diff_count": diff_count,
                    "file_count": file_count,
                },
            )

            # ---- Tester turn ----
            tester_persona = agents.get("tester") or {}
            tester_response = self._call_llm(
                user_prompt=self._tester_user_prompt(
                    build_prompt=build_prompt,
                    foreman_handoff=foreman_content,
                    designer_contract=designer_content,
                    last_developer=dev_content,
                    files_written=file_writes,
                    iteration=iteration,
                ),
                system_prompt=self._tester_system_prompt(tester_persona),
                provider=provider,
                model=model,
                persona=tester_persona,
                history=self._recent_team_history(chat_history),
            )
            tester_content = (tester_response.get("content") or "").strip()
            if tester_content:
                chat_history.append(self._team_message("Tester", "Voorman/Critikus", tester_content))
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
                # Green test — but is the *application* finished? Let the Voorman assess
                # whether the build prompt is fully realized by what's now on disk. If not,
                # she returns a CONTINUE-directive that becomes the focus of the next iteration.
                chair_persona = personas.get("chair") or agents.get("foreman") or {}
                workspace_listing = self._snapshot_workspace()
                review_response = self._call_llm(
                    user_prompt=self._chair_review_user_prompt(
                        build_prompt=build_prompt,
                        iteration=iteration,
                        last_test_command=command,
                        last_test_stdout=test_result.stdout,
                        workspace_listing=workspace_listing,
                    ),
                    system_prompt=self._chair_review_system_prompt(chair_persona),
                    provider=provider,
                    model=model,
                    persona=chair_persona,
                    history=self._recent_team_history(chat_history),
                )
                review_content = (review_response.get("content") or "").strip()
                if review_content:
                    chat_history.append(self._team_message("Voorman", "Team", review_content))
                verdict = _parse_chair_review(review_content)
                iteration_data["chair_review"] = {
                    "verdict": verdict["verdict"],
                    "reason": verdict["reason"],
                    "next_subtask": verdict["next_subtask"],
                    "raw": review_content,
                }
                yield DevTeamBuildEvent(
                    "chair_review",
                    {
                        "iteration": iteration,
                        "content": review_content,
                        "verdict": verdict["verdict"],
                        "reason": verdict["reason"],
                        "next_subtask": verdict["next_subtask"],
                        "ok": bool(review_response.get("ok")),
                    },
                )

                if verdict["verdict"] == "DONE":
                    # Even if Voorman says DONE, enforce minimum iterations for substantial builds
                    # This prevents early completion on simple prompts where the first green test
                    # doesn't mean the full application is built
                    if iteration >= self.min_iterations:
                        # Generate a summary of what was built
                        workspace_files = self._snapshot_workspace()
                        summary = self._generate_build_summary(
                            build_prompt=build_prompt,
                            iterations=iteration,
                            workspace_files=workspace_files,
                            last_command=command,
                            chair_reason=verdict["reason"] or "",
                        )
                        yield DevTeamBuildEvent(
                            "build_complete",
                            {
                                "iterations": iteration,
                                "workspace_path": str(self.workspace),
                                "last_command": command,
                                "reason": verdict["reason"] or "Voorman verklaart de build af.",
                                "summary": summary,
                            },
                        )
                        return
                    else:
                        # Force CONTINUE: we need more iterations for a substantial build
                        yield DevTeamBuildEvent(
                            "chair_review",
                            {
                                "iteration": iteration,
                                "content": review_content,
                                "verdict": "CONTINUE",
                                "reason": f"Minimaal {self.min_iterations} iteraties vereist. {verdict['reason'] or ''}".strip(),
                                "next_subtask": verdict["next_subtask"] or "Werk de bouwprompt verder uit met de eerstvolgende concrete capaciteit.",
                                "ok": bool(review_response.get("ok")),
                            },
                        )
                        next_focus = verdict["next_subtask"] or "Werk de bouwprompt verder uit met de eerstvolgende concrete capaciteit."
                        build_prompt = self._append_subtask(build_prompt, next_focus, iteration)
                        iteration_data["chair_review"] = {
                            "verdict": "CONTINUE",
                            "reason": f"Minimaal {self.min_iterations} iteraties vereist.",
                            "next_subtask": next_focus,
                            "raw": review_content,
                        }
                        continue  # to next iteration

                # CONTINUE — the Voorman's `next_subtask` becomes the focus for the next iteration.
                # We keep the original build_prompt on file but append the new subtask so the
                # developer/tester turns next round know what to work on.
                next_focus = verdict["next_subtask"] or "Bouw de volgende ontbrekende capaciteit uit het bouwdoel."
                build_prompt = self._append_subtask(build_prompt, next_focus, iteration)
                continue  # to next iteration

            # ---- Criticus turn (only on failure) ----
            critic_persona = agents.get("criticus") or {}
            critic_response = self._call_llm(
                user_prompt=self._criticus_user_prompt(
                    build_prompt=build_prompt,
                    foreman_handoff=foreman_content,
                    designer_contract=designer_content,
                    developer_content=dev_content,
                    tester_content=tester_content,
                    test_result=test_result,
                    iteration=iteration,
                ),
                system_prompt=self._criticus_system_prompt(critic_persona),
                provider=provider,
                model=model,
                persona=critic_persona,
                history=self._recent_team_history(chat_history),
            )
            critic_content = (critic_response.get("content") or "").strip()
            if critic_content:
                chat_history.append(self._team_message("Critikus", "Developper/Tester", critic_content))
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
        history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        model_settings = persona.get("model_settings") if isinstance(persona.get("model_settings"), dict) else {}
        chosen_provider = str(model_settings.get("provider") or provider or "ollama").strip().lower() or "ollama"
        chosen_model = str(model_settings.get("name") or model or "ouroboros:latest").strip() or "ouroboros:latest"
        safe_history = list(history or [])
        
        # Wrap the LLM call with a timeout
        def _do_call() -> dict[str, Any]:
            try:
                try:
                    result = self.llm_call(
                        prompt=user_prompt,
                        provider=chosen_provider,
                        model=chosen_model,
                        system_prompt=system_prompt,
                        history=safe_history,
                        images=[],
                    )
                except TypeError:
                    try:
                        result = self.llm_call(
                            prompt=user_prompt,
                            model=chosen_model,
                            system_prompt=system_prompt,
                            history=safe_history,
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
            except Exception as exc:
                return {"ok": False, "content": "", "error": str(exc)}
        
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(_do_call)
        try:
            return future.result(timeout=self.llm_timeout_seconds)
        except FuturesTimeoutError:
            future.cancel()
            return {
                "ok": False,
                "content": "",
                "error": f"LLM call timed out after {self.llm_timeout_seconds:.0f}s",
            }
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    # ------------------------------------------------------------------
    # Prompt builders
    # ------------------------------------------------------------------
    def _merge_development_agents(self, personas: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        agents = default_development_team_agents()
        for role, persona in (personas or {}).items():
            if not isinstance(persona, dict):
                continue
            if role in agents:
                agents[role] = dict(persona)
        return agents

    def _team_message(self, sender: str, recipient: str, content: str) -> dict[str, str]:
        return {
            "role": "user",
            "content": f"TEAM_HANDOFF FROM {sender} TO {recipient}:\n{content[:2400]}",
        }

    def _recent_team_history(self, history: list[dict[str, str]]) -> list[dict[str, str]]:
        return list(history[-MAX_TEAM_BUS_MESSAGES:])

    def _foreman_system_prompt(self, persona: dict[str, Any]) -> str:
        return str(persona.get("system_prompt") or DEFAULT_DEVELOPMENT_TEAM_AGENTS["foreman"]["system_prompt"])

    def _designer_system_prompt(self, persona: dict[str, Any]) -> str:
        return str(persona.get("system_prompt") or DEFAULT_DEVELOPMENT_TEAM_AGENTS["designer"]["system_prompt"])

    def _developer_system_prompt(self, persona: dict[str, Any]) -> str:
        base = str(persona.get("system_prompt") or "").strip()
        return (
            (base + "\n\n" if base else "")
            + "BOUWMODE: je werkt in de gescheiden OUROBOROS DEVELOPMENT TEAM build-loop. "
              "De Voorman en Ontwerper hebben net een concrete opdracht doorgegeven. Volg die handoff.\n\n"
              "Editregels, gebaseerd op Aider:\n"
              "- Gebruik bij voorkeur `<diff path=\"src/foo.py\">...</diff>` met SEARCH/REPLACE:\n"
              "  <<<<<<< SEARCH\n  bestaande tekst of leeg voor nieuw bestand\n  =======\n  nieuwe tekst\n  >>>>>>> REPLACE\n"
              "- Voor nieuwe kleine files mag `<file path=\"...\">...</file>` ook.\n"
              "- Schrijf alleen nieuwe of gewijzigde files; geen markdown fences rond editblokken.\n"
              "- Communiceer expliciet: één korte openingszin aan Voorman/Ontwerper, editblokken, één korte overdracht aan Tester.\n"
              "- Als Critikus feedback gaf, verwerk die zichtbaar in de volgende edit."
        )

    def _tester_system_prompt(self, persona: dict[str, Any]) -> str:
        base = str(persona.get("system_prompt") or "").strip()
        return (
            (base + "\n\n" if base else "")
            + "BOUWMODE: De Developper heeft net edits geschreven. Kies het kleinste commando "
              "dat het build_plan en de Voorman-subtask bewijst. Je MOET precies één "
              "`<cmd>...</cmd>` blok geven, één regel, idempotent, vanaf de workspace-root.\n\n"
              "Voorbeeld:\n"
              "Developper, ik test nu precies de CLI-output die de Ontwerper vroeg.\n"
              "<cmd>python -m pytest tests/test_cli.py -v</cmd>\n"
              "Verwacht groen: exit 0 en de acceptance-assertions passeren.\n\n"
              "Harde regels: één `<cmd>` blok per beurt, geen `sudo`, geen netwerk-tools "
              "(`curl`, `wget`, `ssh`), geen destructieve commando's (`rm -rf /`). Voor Python "
              "test-runs gebruik `python -m pytest ...` zodat de workspace op sys.path komt."
        )

    def _criticus_system_prompt(self, persona: dict[str, Any]) -> str:
        base = str(persona.get("system_prompt") or "").strip()
        return (
            (base + "\n\n" if base else "")
            + "BOUWMODE: je leest de stdout/stderr van het laatst gedraaide testcommando. "
              "Geef De Developper een gerichte fix-opdracht in MAXIMAAL 4 zinnen: oorzaak, "
              "file/symbol, kleinste wijziging, en welk testcommando opnieuw moet draaien. "
              "Lees stderr/stdout LETTERLIJK; verzin geen fouten die er niet staan."
        )

    def _foreman_user_prompt(
        self,
        *,
        build_plan: dict[str, Any],
        clarifications: list[dict[str, str]],
        iteration: int,
        last_test_result: TestResult | None,
    ) -> str:
        parts = [f"FORMEEL BUILD_PLAN:\n{format_build_plan(build_plan)}"]
        if clarifications:
            qa = "\n".join(
                f"- {item.get('question','')}\n  Antwoord: {item.get('answer','')}"
                for item in clarifications
                if isinstance(item, dict) and str(item.get("answer") or "").strip()
            )
            if qa:
                parts.append(f"Gebruiker-verduidelijking:\n{qa}")
        if last_test_result is not None:
            parts.append(
                "Laatste teststatus:\n"
                f"- command: {last_test_result.command}\n"
                f"- exit_code: {last_test_result.exit_code}\n"
                f"- stderr: {(last_test_result.stderr or '').strip()[:800] or '(leeg)'}"
            )
        if self.iteration_log:
            compact = []
            for entry in self.iteration_log[-MAX_HISTORY_IN_PROMPT:]:
                files = ", ".join(f.get("path", "") for f in entry.get("files_written", []) or []) or "(geen)"
                test = entry.get("test_result") or {}
                compact.append(f"Iteratie {entry.get('iteration')}: files={files}; test_exit={test.get('exit_code')}")
            parts.append("Korte historie:\n" + "\n".join(compact))
        parts.append(f"Maak nu de handoffkaart voor iteratie {iteration}.")
        return "\n\n".join(parts)

    def _designer_user_prompt(
        self,
        *,
        build_plan: dict[str, Any],
        foreman_handoff: str,
        iteration: int,
    ) -> str:
        return (
            f"FORMEEL BUILD_PLAN:\n{format_build_plan(build_plan)}\n\n"
            f"Voorman-handoff voor iteratie {iteration}:\n{foreman_handoff[:1800]}\n\n"
            "Maak het ontwerpcontract. Houd het kort genoeg voor een klein model en eindig met TO_DEVELOPPER."
        )

    def _developer_user_prompt(
        self,
        *,
        build_prompt: str,
        build_plan: dict[str, Any],
        foreman_handoff: str,
        designer_contract: str,
        clarifications: list[dict[str, str]],
        iteration: int,
    ) -> str:
        parts = [
            f"FORMEEL BUILD_PLAN:\n{format_build_plan(build_plan)}",
            f"Voorman-handoff:\n{foreman_handoff[:1800]}",
            f"Ontwerpcontract:\n{designer_contract[:1800]}",
            f"Bouwdoeltekst (compat):\n{build_prompt[:2000]}",
        ]
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
            "Schrijf nu je beurt: één korte teamzin, dan `<diff>` SEARCH/REPLACE of `<file>` blokken, "
            "en sluit af met één korte overdracht aan De Tester."
        )
        return "\n\n".join(parts)

    def _tester_user_prompt(
        self,
        *,
        build_prompt: str,
        foreman_handoff: str,
        designer_contract: str,
        last_developer: str,
        files_written: list[FileWrite],
        iteration: int,
    ) -> str:
        files_block = ", ".join(item.path for item in files_written) or "(geen files geschreven)"
        return (
            f"Bouwdoel: {build_prompt}\n\n"
            f"Voorman-handoff:\n{foreman_handoff[:1000]}\n\n"
            f"Ontwerpcontract:\n{designer_contract[:1000]}\n\n"
            f"Iteratie {iteration} — De Developper schreef: {files_block}.\n\n"
            f"Zijn beurt was:\n{last_developer[:2400]}\n\n"
            "Geef nu precies één `<cmd>...</cmd>` testcommando plus een korte verwachting."
        )

    def _criticus_user_prompt(
        self,
        *,
        build_prompt: str,
        foreman_handoff: str,
        designer_contract: str,
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
            f"Voorman-handoff:\n{foreman_handoff[:800]}\n\n"
            f"Ontwerpcontract:\n{designer_contract[:800]}\n\n"
            f"De Developper schreef:\n{developer_content[:1600]}\n\n"
            f"De Tester wilde:\n{tester_content[:800]}\n\n"
            "Geef nu De Developper een gerichte fix-opdracht (maximaal 4 zinnen)."
        )

    def _fallback_foreman_turn(self, build_plan: dict[str, Any], iteration: int) -> str:
        components = build_plan.get("components") if isinstance(build_plan.get("components"), list) else []
        goals = build_plan.get("goals") if isinstance(build_plan.get("goals"), list) else []
        tests = build_plan.get("tests") if isinstance(build_plan.get("tests"), list) else []
        component = components[min(iteration - 1, max(len(components) - 1, 0))] if components else {}
        component_name = component.get("name") if isinstance(component, dict) else str(component or "")
        goal = str(goals[0] if goals else build_plan.get("title") or "bouwdoel")
        test = str(tests[0] if tests else "het kleinste relevante testcommando draait groen")
        subtask = f"Maak {component_name or 'de eerste implementatie'} werkend voor: {goal}"
        return (
            f"SUBTASK: {subtask[:260]}\n"
            f"DONE_CRITERION: {test[:220]}\n"
            f"TO_ONTWERPER: Leg interface, files en testhook voor {component_name or 'de implementatie'} vast.\n"
            f"TO_DEVELOPPER: Bouw alleen deze subtask met kleine Aider-style edits.\n"
            f"TO_TESTER: Bewijs deze subtask mechanisch met één command."
        )

    def _fallback_designer_turn(self, build_plan: dict[str, Any], foreman_handoff: str, iteration: int) -> str:
        components = build_plan.get("components") if isinstance(build_plan.get("components"), list) else []
        component = components[min(iteration - 1, max(len(components) - 1, 0))] if components else {}
        component_name = component.get("name") if isinstance(component, dict) else str(component or "implementation")
        description = component.get("description") if isinstance(component, dict) else str(component or "")
        return (
            f"CONTRACT: {description or build_plan.get('title') or 'Maak de gevraagde functie zichtbaar werkend.'}\n"
            f"FILES: {component_name}\n"
            "INTERFACE: Houd input/output eenvoudig en direct testbaar.\n"
            "TEST_HOOK: De Tester moet het gedrag via pytest of een directe CLI/API-call kunnen bewijzen.\n"
            f"TO_DEVELOPPER: Volg de Voorman-subtask en wijzig alleen {component_name}."
        )

    def _guess_default_test_command(self, files: list[FileWrite]) -> str:
        """Pick a sensible default if the Tester didn't emit a <cmd> block."""
        for item in files:
            lower = item.path.lower()
            if lower.endswith(".py") and "test" in lower:
                return f"python -m pytest {item.path} -v"
        if any(item.path.endswith(".py") for item in files):
            return "python -m pytest -v"
        return "python -m pytest -q"

    def _chair_review_system_prompt(self, persona: dict[str, Any]) -> str:
        base = str(persona.get("system_prompt") or "").strip()
        return (
            (base + "\n\n" if base else "")
            + "BOUWMODE — Voorman-review: De Tester heeft net groen gemeld. Beslis of het "
              "BOUWDOEL nu volledig gerealiseerd is door de files op disk + de werkende test, "
              "of dat er nog ontbrekende capaciteiten zijn voordat het bouwdoel echt af is.\n\n"
              "Antwoord uitsluitend in deze JSON-vorm (geen markdown, geen toelichting eromheen):\n"
              "{\"verdict\": \"DONE\", \"reason\": \"...\"}\n"
              "OF\n"
              "{\"verdict\": \"CONTINUE\", \"reason\": \"...\", \"next_subtask\": \"De ene meest urgente capaciteit die nu mist, in één zin.\"}\n\n"
              "Beslisregels:\n"
              "- DONE alleen als het bouwdoel volledig werkt voor de gebruiker zoals beschreven. "
              "Een eerste 'add(a,b)' test is NIET genoeg om 'maak een schaakprogramma' DONE te verklaren.\n"
              "- CONTINUE als belangrijke onderdelen ontbreken: noem dan de KLEINSTE volgende stap die het bouwdoel "
              "merkbaar dichterbij brengt — een specifieke file/feature/test die nu mist.\n"
              "- Herhaal jezelf niet: kijk naar de werkhistorie en focus op iets nieuws.\n"
              "- Maximaal 3 zinnen in de reason; maximaal 1 zin in next_subtask."
        )

    def _chair_review_user_prompt(
        self,
        *,
        build_prompt: str,
        iteration: int,
        last_test_command: str,
        last_test_stdout: str,
        workspace_listing: str,
    ) -> str:
        history_summary = ""
        if self.iteration_log:
            history_lines = []
            for entry in self.iteration_log[-5:]:
                it = entry.get("iteration")
                files = [f.get("path", "") for f in entry.get("files_written", []) or []]
                test = entry.get("test_result") or {}
                feedback = entry.get("critic_feedback") or ""
                review = entry.get("chair_review") or {}
                history_lines.append(
                    f"  Iter {it}: files={files or '[]'}, test exit={test.get('exit_code')}"
                    + (f", criticus='{feedback[:200]}'" if feedback else "")
                    + (f", chair-review='{(review.get('verdict') or '')}: {(review.get('next_subtask') or review.get('reason') or '')[:160]}'" if review else "")
                )
            history_summary = "\nWerkhistorie:\n" + "\n".join(history_lines)
        return (
            f"Bouwdoel:\n{build_prompt}\n\n"
            f"Iteratie {iteration} groen via commando: {last_test_command}\n"
            f"Stdout (geclipt):\n{(last_test_stdout or '').strip()[:1200]}\n\n"
            f"Workspace inhoud:\n{workspace_listing[:1800]}\n"
            f"{history_summary}\n\n"
            "Beoordeel: is het bouwdoel hiermee volledig gerealiseerd? Antwoord in JSON."
        )

    def _snapshot_workspace(self, max_entries: int = 60) -> str:
        """Walk the workspace and return a flat listing (path + size) for the chair review."""
        try:
            entries: list[tuple[str, int]] = []
            for path in sorted(self.workspace.rglob("*")):
                if not path.is_file():
                    continue
                try:
                    rel = path.relative_to(self.workspace)
                except ValueError:
                    continue
                entries.append((str(rel), path.stat().st_size))
                if len(entries) >= max_entries:
                    break
            if not entries:
                return "(workspace is leeg)"
            return "\n".join(f"  {rel} ({size}B)" for rel, size in entries)
        except OSError:
            return "(workspace listing onbeschikbaar)"

    def _append_subtask(self, build_prompt: str, subtask: str, iteration: int) -> str:
        """Append a Voorman-decided subtask to the original build prompt for the next iteration."""
        marker = "\n\nVervolgstap"
        cleaned = build_prompt
        return (
            f"{cleaned}{marker} (na iteratie {iteration}, volgens Voorman): {subtask}"
        )

    def _generate_build_summary(
        self,
        *,
        build_prompt: str,
        iterations: int,
        workspace_files: str,
        last_command: str,
        chair_reason: str,
    ) -> str:
        """Generate a human-readable summary of what was built."""
        lines = []
        lines.append(f"Build afgerond na {iterations} iteratie(s).")
        lines.append(f"Bouwdoel: {build_prompt[:200]}...")
        
        # List files created
        if workspace_files and workspace_files != "(workspace is leeg)":
            file_lines = workspace_files.strip().split("\n")
            if len(file_lines) <= 5:
                lines.append(f"Files aangemaakt: {', '.join(f.strip() for f in file_lines)}")
            else:
                lines.append(f"Files aangemaakt: {len(file_lines)} bestanden")
        
        # Last test command
        if last_command:
            lines.append(f"Laatste test: `{last_command}`")
        
        # Chair's reason
        if chair_reason:
            lines.append(f"Voorman: {chair_reason}")
        
        lines.append(f"Workspace: {self.workspace}")
        return " ".join(lines)


def _parse_chair_review(content: str) -> dict[str, str]:
    """Parse the chair-review JSON. Falls back to heuristic DONE/CONTINUE detection.

    When the chair gives no answer at all, default to CONTINUE so the loop keeps
    building. Stopping at "DONE" on empty input would cut the team off mid-build —
    which is exactly the failure mode the user complained about. Stopping early at
    max_iterations is much less harmful than stopping too soon.
    """
    import json

    text = str(content or "").strip()
    if not text:
        return {
            "verdict": "CONTINUE",
            "reason": "Voorman-oordeel ontbreekt; ga voor de zekerheid door met de volgende kleine bouwstap.",
            "next_subtask": "Werk de bouwprompt verder uit met de eerstvolgende concrete capaciteit die nog mist.",
        }

    candidates: list[str] = [text]
    if text.startswith("```"):
        stripped = text[3:]
        if stripped.lower().startswith("json"):
            stripped = stripped[4:]
        if stripped.endswith("```"):
            stripped = stripped[:-3]
        candidates.insert(0, stripped.strip())
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        candidates.insert(0, text[start : end + 1])

    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        verdict_raw = str(data.get("verdict") or "").strip().upper()
        reason = str(data.get("reason") or "").strip()
        next_subtask = str(data.get("next_subtask") or "").strip()
        if verdict_raw in {"DONE", "AFGEROND", "KLAAR", "FINISHED"}:
            return {"verdict": "DONE", "reason": reason, "next_subtask": ""}
        if verdict_raw in {"CONTINUE", "DOOR", "DOORGAAN", "FURTHER"}:
            return {
                "verdict": "CONTINUE",
                "reason": reason,
                "next_subtask": next_subtask,
            }

    # Heuristic fallback: look for the literal words in the raw text.
    lowered = text.lower()
    if "\"verdict\": \"done\"" in lowered or " done\"" in lowered or lowered.startswith("done"):
        return {"verdict": "DONE", "reason": text[:240], "next_subtask": ""}
    if "continue" in lowered:
        # Try to grab the line that mentions the next step.
        for line in text.splitlines():
            if "next_subtask" in line.lower():
                _, _, payload = line.partition(":")
                return {"verdict": "CONTINUE", "reason": text[:240], "next_subtask": payload.strip().strip('",')[:240]}
        return {"verdict": "CONTINUE", "reason": text[:240], "next_subtask": "Werk de bouwprompt verder uit."}
    # When in doubt, assume the build is not yet finished — better to over-iterate than to declare done early.
    return {"verdict": "CONTINUE", "reason": "Voorman-oordeel onduidelijk; ga door.", "next_subtask": "Werk de bouwprompt verder uit."}


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
