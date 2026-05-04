"""Approval-gated tool bridge for agent-runtime calls.

The bridge is a narrow HTTP-callable surface for read_file, write_file,
apply_patch and run_command. It reuses the existing Roo/safe_shell adapters,
adds a 528Hz coherence check, and records rejected/blocked calls in the
QuantumCorruptionNexus.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from controller.safe_shell import run_safe_shell
from ouroboros_esoteric.light_language import LightLanguageCompiler
from ouroboros_esoteric.quantum_corruption_nexus import get_quantum_corruption_nexus


APPROVAL_PHRASE = "Akkoord"
TOOL_BRIDGE_TOOLS: tuple[str, ...] = ("read_file", "write_file", "apply_patch", "run_command")
WRITE_TOOLS: frozenset[str] = frozenset(("write_file", "apply_patch", "run_command"))


class ToolBridge:
    """Single guarded tool bridge instance."""

    def __init__(self) -> None:
        self.compiler = LightLanguageCompiler()
        self.last_result: dict[str, Any] | None = None

    def run(self, tool: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
        started = time.time()
        clean_tool = str(tool or "").strip()
        payload = dict(args or {})
        firewall = self._firewall(clean_tool, payload)
        if firewall["status"] != "accepted":
            result = {
                "status": firewall["status"],
                "tool": clean_tool or "unknown",
                "result": {},
                "stdout": "",
                "stderr": firewall["reason"],
                "reason": firewall["reason"],
                "firewall": firewall,
                "duration_seconds": round(time.time() - started, 3),
                "fake_success": False,
            }
            get_quantum_corruption_nexus().record_tool_firewall(
                tool=clean_tool or "unknown",
                status=firewall["status"],
                reason=firewall["reason"],
                args=payload,
            )
            self.last_result = result
            return result

        try:
            result = self._dispatch(clean_tool, payload)
        except Exception as exc:
            result = {"status": "error", "stdout": "", "stderr": str(exc), "reason": str(exc), "result": {}}

        status = str(result.get("status") or "unknown")
        wrapped = {
            "status": status,
            "tool": clean_tool,
            "result": result.get("result") if isinstance(result, dict) else result,
            "stdout": str(result.get("stdout", "")) if isinstance(result, dict) else "",
            "stderr": str(result.get("stderr", "")) if isinstance(result, dict) else "",
            "reason": str(result.get("reason") or result.get("stderr") or "") if isinstance(result, dict) else "",
            "firewall": firewall,
            "raw": result,
            "duration_seconds": round(time.time() - started, 3),
            "fake_success": False,
        }
        if status in {"blocked", "rejected", "error"}:
            get_quantum_corruption_nexus().record_tool_firewall(
                tool=clean_tool,
                status=status,
                reason=wrapped["reason"] or f"{clean_tool} returned {status}",
                args=payload,
            )
        self.last_result = wrapped
        return wrapped

    def status(self) -> dict[str, Any]:
        return {
            "status": "online",
            "tools": list(TOOL_BRIDGE_TOOLS),
            "write_tools_require_approval": list(WRITE_TOOLS),
            "firewall_frequency_hz": 528.0,
            "last_result": self.last_result,
            "fake_success": False,
        }

    def _firewall(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        if tool not in TOOL_BRIDGE_TOOLS:
            return {"status": "rejected", "reason": f"Tool not allowed by bridge: {tool}", "resonant": False}

        frequency = _float(args.get("frequency"), default=528.0)
        check = self.compiler.coherence_check(
            _firewall_payload(tool, args),
            input_frequency=frequency,
            entropy_level=0.0,
            entropy_threshold=0.7,
        )
        if check.get("status") == "rejected":
            return {
                "status": "rejected",
                "reason": str(check.get("reason") or "528.0 Hz resonance required."),
                "resonant": False,
                "frequency": frequency,
            }

        if tool in WRITE_TOOLS and str(args.get("approval") or "").strip() != APPROVAL_PHRASE:
            return {
                "status": "blocked",
                "reason": "Tool bridge write/command calls require exact approval phrase: Akkoord.",
                "resonant": True,
                "frequency": frequency,
                "approval_required": True,
            }
        return {"status": "accepted", "reason": "528Hz firewall accepted.", "resonant": True, "frequency": frequency}

    def _dispatch(self, tool: str, args: dict[str, Any]) -> dict[str, Any]:
        from controller import roo_tools

        if tool == "read_file":
            return roo_tools.read_file(
                path=str(args.get("path") or ""),
                offset=_int_or_none(args.get("offset")),
                limit=_int_or_none(args.get("limit")),
            )
        if tool == "write_file":
            return roo_tools.write_file(
                path=str(args.get("path") or ""),
                content=str(args.get("content") or ""),
                approval=str(args.get("approval") or ""),
            )
        if tool == "apply_patch":
            return roo_tools.apply_patch(
                patch=str(args.get("patch") or ""),
                approval=str(args.get("approval") or ""),
            )
        if tool == "run_command":
            return run_safe_shell(
                str(args.get("command") or ""),
                approval=str(args.get("approval") or ""),
                timeout=max(1, min(_int(args.get("timeout"), default=20), 30)),
            )
        return {"status": "rejected", "reason": f"Tool not allowed by bridge: {tool}", "fake_success": False}


_BRIDGE_LOCK = threading.Lock()
_BRIDGE: ToolBridge | None = None


def get_tool_bridge() -> ToolBridge:
    global _BRIDGE
    with _BRIDGE_LOCK:
        if _BRIDGE is None:
            _BRIDGE = ToolBridge()
        return _BRIDGE


def run_tool_bridge(tool: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    return get_tool_bridge().run(tool, args)


def tool_bridge_status() -> dict[str, Any]:
    return get_tool_bridge().status()


def _firewall_payload(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    scrubbed: dict[str, Any] = {"tool": tool}
    for key, value in args.items():
        lowered = str(key).lower()
        if any(marker in lowered for marker in ("key", "token", "secret", "password", "bearer")):
            scrubbed[key] = "[REDACTED]"
        elif isinstance(value, str):
            scrubbed[key] = value[:1000]
        else:
            scrubbed[key] = value
    return scrubbed


def _float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _int(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return _int(value, default=0)
