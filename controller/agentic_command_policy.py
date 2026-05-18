"""Shell command permission policy inspired by Cline's CommandPermissionController.

Goal: give the cockpit a structured way to describe which shell commands the
agent can run, which require explicit `Akkoord`, and which are denied
outright. Unlike Cline's TypeScript controller we keep parsing intentionally
conservative and never strip operators silently — pipes, redirects and
backticks always escalate to the most restrictive verdict that applies.

The Ouroboros approval gate (`Akkoord` for `safe_shell` / `run_tests`) is the
authoritative line of defense; this policy adds an inspectable layer that the
UI can show before the run is attempted, so the user understands *why* a
command is allowed, queued for approval, or refused.
"""

from __future__ import annotations

import fnmatch
import re
import shlex
from typing import Any, Iterable, Mapping


VERDICT_ALLOW = "allow"
VERDICT_REQUIRES_APPROVAL = "requires_approval"
VERDICT_DENY = "deny"

DEFAULT_DENY_PATTERNS: tuple[str, ...] = (
    "rm -rf /*",
    "rm -rf /",
    "rm -rf ~/*",
    "rm -rf ~",
    "rm -rf $HOME*",
    "dd if=*",
    "mkfs*",
    ":(){ :|:& };:",
    "shutdown*",
    "reboot*",
    "halt*",
    "init 0",
    "init 6",
    "chmod -R 777 /*",
    "curl * | sh*",
    "curl * | bash*",
    "wget * | sh*",
    "wget * | bash*",
)

DEFAULT_ALLOW_PATTERNS: tuple[str, ...] = (
    "ls*",
    "pwd",
    "echo*",
    "cat *",
    "head *",
    "tail *",
    "git status*",
    "git diff*",
    "git log*",
    "git show*",
    "git branch*",
    "python3 -m unittest*",
    "npm run build*",
    "npm run lint*",
    "npm run test*",
)

DANGEROUS_OPERATOR_RE = re.compile(r"[`$]\(|>>?|<\(|>\(|\|\&|\&>|<&|>&")
NEWLINE_INSIDE_COMMAND_RE = re.compile(r"[\r\n]")


def evaluate_command(
    command: str,
    *,
    allow_patterns: Iterable[str] | None = None,
    deny_patterns: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Return a structured verdict for a shell command string."""

    raw = str(command or "")
    cleaned = raw.strip()
    if not cleaned:
        return {
            "verdict": VERDICT_DENY,
            "reason": "Lege command.",
            "command": "",
            "segments": [],
            "operators": [],
            "matched_rule": None,
            "approval_phrase_required": False,
            "fake_success": False,
        }
    if NEWLINE_INSIDE_COMMAND_RE.search(cleaned):
        return _verdict(
            VERDICT_DENY,
            cleaned,
            reason="Multiline commando's worden niet ge-evalueerd; splits ze en run ze los.",
        )
    if DANGEROUS_OPERATOR_RE.search(cleaned):
        return _verdict(
            VERDICT_REQUIRES_APPROVAL,
            cleaned,
            reason="Bevat redirect/pipe/subshell — vereist expliciete Akkoord.",
            matched_rule="dangerous_operator",
        )
    try:
        segments = list(_split_segments(cleaned))
    except ValueError as exc:
        return _verdict(VERDICT_DENY, cleaned, reason=f"Command kan niet veilig geparsed worden: {exc}")
    if not segments:
        return _verdict(VERDICT_DENY, cleaned, reason="Geen leesbare command-segmenten gevonden.")
    deny_rules = list(deny_patterns) if deny_patterns is not None else list(DEFAULT_DENY_PATTERNS)
    allow_rules = list(allow_patterns) if allow_patterns is not None else list(DEFAULT_ALLOW_PATTERNS)
    worst_verdict = VERDICT_ALLOW
    matched_rule: str | None = None
    reasons: list[str] = []
    for segment in segments:
        verdict, rule, reason = _classify_segment(segment, allow_rules, deny_rules)
        reasons.append(f"{segment!r} -> {verdict} ({reason})")
        if verdict == VERDICT_DENY:
            return _verdict(
                VERDICT_DENY,
                cleaned,
                reason=f"Segment '{segment}' valt onder deny-regel '{rule}'.",
                matched_rule=rule,
                segments=segments,
                operators=_extract_operators(cleaned),
                trace=reasons,
            )
        if verdict == VERDICT_REQUIRES_APPROVAL and worst_verdict == VERDICT_ALLOW:
            worst_verdict = VERDICT_REQUIRES_APPROVAL
            matched_rule = rule
        elif verdict == VERDICT_ALLOW and worst_verdict == VERDICT_ALLOW and matched_rule is None:
            matched_rule = rule
    return _verdict(
        worst_verdict,
        cleaned,
        reason=("Allow-listed." if worst_verdict == VERDICT_ALLOW else "Geen allow-match; vereist Akkoord."),
        matched_rule=matched_rule,
        segments=segments,
        operators=_extract_operators(cleaned),
        trace=reasons,
    )


def _verdict(
    verdict: str,
    command: str,
    *,
    reason: str,
    matched_rule: str | None = None,
    segments: list[str] | None = None,
    operators: list[str] | None = None,
    trace: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "verdict": verdict,
        "reason": reason,
        "command": command,
        "segments": list(segments or []),
        "operators": list(operators or []),
        "matched_rule": matched_rule,
        "trace": list(trace or []),
        "approval_phrase_required": verdict == VERDICT_REQUIRES_APPROVAL,
        "fake_success": False,
    }


def _split_segments(command: str) -> Iterable[str]:
    pieces: list[str] = []
    buffer: list[str] = []
    in_single = False
    in_double = False
    escape = False
    operators = ("&&", "||", ";", "|")
    index = 0
    while index < len(command):
        char = command[index]
        if escape:
            buffer.append(char)
            escape = False
            index += 1
            continue
        if char == "\\" and not in_single:
            buffer.append(char)
            escape = True
            index += 1
            continue
        if char == "'" and not in_double:
            in_single = not in_single
            buffer.append(char)
            index += 1
            continue
        if char == '"' and not in_single:
            in_double = not in_double
            buffer.append(char)
            index += 1
            continue
        if not in_single and not in_double:
            matched_operator = next((operator for operator in operators if command.startswith(operator, index)), None)
            if matched_operator is not None:
                pieces.append("".join(buffer).strip())
                buffer.clear()
                index += len(matched_operator)
                continue
        buffer.append(char)
        index += 1
    if in_single or in_double:
        raise ValueError("ongeslote quote in command")
    if buffer:
        pieces.append("".join(buffer).strip())
    return [piece for piece in pieces if piece]


def _extract_operators(command: str) -> list[str]:
    found: list[str] = []
    for operator in ("&&", "||", ";", "|"):
        if operator in command:
            found.append(operator)
    return found


def _classify_segment(
    segment: str,
    allow_rules: list[str],
    deny_rules: list[str],
) -> tuple[str, str | None, str]:
    try:
        tokens = shlex.split(segment, posix=True)
    except ValueError as exc:
        return VERDICT_DENY, None, f"Kan niet parsen: {exc}"
    if not tokens:
        return VERDICT_DENY, None, "Lege subcommand."
    canonical = _normalise_command(tokens)
    for rule in deny_rules:
        if fnmatch.fnmatchcase(canonical, rule):
            return VERDICT_DENY, rule, "Deny-regel matcht."
    for rule in allow_rules:
        if fnmatch.fnmatchcase(canonical, rule):
            return VERDICT_ALLOW, rule, "Allow-regel matcht."
    return VERDICT_REQUIRES_APPROVAL, None, "Geen allow-match."


def _normalise_command(tokens: list[str]) -> str:
    return " ".join(tokens)


def policy_snapshot(
    *,
    allow_patterns: Iterable[str] | None = None,
    deny_patterns: Iterable[str] | None = None,
) -> dict[str, Any]:
    return {
        "default_allow_patterns": list(DEFAULT_ALLOW_PATTERNS),
        "default_deny_patterns": list(DEFAULT_DENY_PATTERNS),
        "active_allow_patterns": list(allow_patterns or DEFAULT_ALLOW_PATTERNS),
        "active_deny_patterns": list(deny_patterns or DEFAULT_DENY_PATTERNS),
        "approval_phrase": "Akkoord",
        "fake_success": False,
    }


def merge_user_rules(
    *,
    allow_patterns: Iterable[str] | None,
    deny_patterns: Iterable[str] | None,
) -> tuple[list[str], list[str]]:
    """Combine defaults with user-supplied rules without duplicates."""

    def _merge(defaults: tuple[str, ...], extras: Iterable[str] | None) -> list[str]:
        seen: list[str] = list(defaults)
        for rule in extras or ():
            text = str(rule or "").strip()
            if text and text not in seen:
                seen.append(text)
        return seen

    return _merge(DEFAULT_ALLOW_PATTERNS, allow_patterns), _merge(DEFAULT_DENY_PATTERNS, deny_patterns)


def is_safe_for_auto_run(command: str, *, allow_patterns: Iterable[str] | None = None) -> bool:
    verdict = evaluate_command(command, allow_patterns=allow_patterns, deny_patterns=DEFAULT_DENY_PATTERNS)
    return bool(verdict.get("verdict") == VERDICT_ALLOW)


def explain_verdict(verdict: Mapping[str, Any]) -> str:
    verdict_text = str(verdict.get("verdict") or "")
    reason = str(verdict.get("reason") or "")
    rule = verdict.get("matched_rule")
    if verdict_text == VERDICT_ALLOW:
        return f"Allow: {reason}" + (f" (regel: {rule})" if rule else "")
    if verdict_text == VERDICT_REQUIRES_APPROVAL:
        return f"Vereist Akkoord: {reason}" + (f" (regel: {rule})" if rule else "")
    if verdict_text == VERDICT_DENY:
        return f"Deny: {reason}" + (f" (regel: {rule})" if rule else "")
    return reason or "Onbekende verdict."
