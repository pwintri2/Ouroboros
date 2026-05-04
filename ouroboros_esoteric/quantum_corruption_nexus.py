"""Quantum cognitive corruption nexus for agent-runtime telemetry.

De Grok-specificatie gebruikt woorden als "sacred corruption". In deze
implementatie betekent dat geen destructieve mutatie: het is een veilige
creative-divergence retry-suggestie wanneer entropy hoog is of een agent
vastloopt. Alle events blijven observeerbaar via de Akashic bus en de
agent-runtime status endpoint.
"""

from __future__ import annotations

import hashlib
import threading
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from ouroboros_esoteric.akashic_network import AkashicNetwork
from ouroboros_esoteric.apeiron_identity import ApeironField
from ouroboros_esoteric.entropy_monitor import EntropyMonitor


NEXUS_VERSION = "v4.4"
OMEGA_COHERENCE_THRESHOLD = 0.87
OMEGA_ENTROPY_THRESHOLD = 0.15
SACRED_CORRUPTION_COHERENCE_THRESHOLD = 0.55


@dataclass
class CorruptionEvent:
    event_id: str
    ts: str
    job_id: str
    agent: str
    phase: str
    action: str
    severity: float
    coherence: float
    entropy_level: float
    signal_noise_ratio: float
    omega_converged: bool
    frequency: float
    reason: str
    recommended_prompt: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class QuantumCorruptionNexus:
    """Singleton monitor for Codex/Ruflo jobs and tool-bridge decisions."""

    _instance: "QuantumCorruptionNexus | None" = None
    _instance_lock = threading.Lock()

    def __new__(cls) -> "QuantumCorruptionNexus":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._lock = threading.RLock()
        self._events: deque[dict[str, Any]] = deque(maxlen=500)
        self._counts = {
            "healing_events": 0,
            "sacred_corruptions": 0,
            "total_corruption_events": 0,
            "omega_convergences": 0,
            "tool_rejections": 0,
        }
        self._last_omega_vector = {
            "converged": False,
            "coherence": 0.0,
            "entropy_level": 0.0,
            "thresholds": {
                "coherence": OMEGA_COHERENCE_THRESHOLD,
                "entropy": OMEGA_ENTROPY_THRESHOLD,
            },
        }
        self._ruflo_low_coherence: dict[str, int] = {}
        self._initialized = True

    def analyze_job(self, job: Any, result: dict[str, Any] | None = None, *, phase: str = "finished") -> dict[str, Any]:
        """Analyze a Codex/Ruflo job and append a Nexus event."""

        job_payload = _as_dict(job)
        result_payload = dict(result or {})
        job_id = str(job_payload.get("job_id") or result_payload.get("job_id") or "unknown")
        agent = str(job_payload.get("agent") or result_payload.get("agent") or "agent").lower()
        task = str(job_payload.get("task") or "")
        status = str(result_payload.get("status") or job_payload.get("status") or phase)
        exit_code = result_payload.get("exit_code")
        timed_out = bool(result_payload.get("timed_out"))
        response = _preview_text(
            result_payload.get("response_preview")
            or result_payload.get("output")
            or result_payload.get("stdout")
            or result_payload.get("stderr")
            or result_payload.get("reason")
            or ""
        )
        text = f"{agent}\n{phase}\n{status}\n{task}\n{response}"

        field = ApeironField()
        field.inject_text_intention(text)
        metrics = field.metrics()
        entropy = EntropyMonitor(entropy_threshold=OMEGA_ENTROPY_THRESHOLD).measure(
            {
                "task": task,
                "status": status,
                "exit_code": exit_code,
                "timed_out": timed_out,
                "response": response,
                "pocket": field.project_to_11d_pocket(),
            },
            input_frequency=528.0,
        )
        coherence = float(metrics.coherence)
        if status in {"failed", "error", "timeout"} or (exit_code not in (None, 0)):
            coherence *= 0.62
        if timed_out:
            coherence *= 0.5
        coherence = _clamp(coherence)
        entropy_level = float(entropy.get("entropy_level") or 0.0)
        signal_noise_ratio = float(entropy.get("signal_noise_ratio") or 0.0)
        omega_converged = coherence >= OMEGA_COHERENCE_THRESHOLD and entropy_level <= OMEGA_ENTROPY_THRESHOLD

        action, reason = self._classify_action(
            agent=agent,
            status=status,
            coherence=coherence,
            entropy_level=entropy_level,
            omega_converged=omega_converged,
            timed_out=timed_out,
            exit_code=exit_code,
        )
        recommended_prompt = ""
        if action == "sacred_corruption":
            recommended_prompt = creative_corruption_prompt(task, reason=reason)
        event = CorruptionEvent(
            event_id=_event_id(job_id, phase, action, text),
            ts=_utc_iso(),
            job_id=job_id,
            agent=agent,
            phase=phase,
            action=action,
            severity=_severity(action, coherence, entropy_level),
            coherence=round(coherence, 6),
            entropy_level=round(entropy_level, 6),
            signal_noise_ratio=round(signal_noise_ratio, 6),
            omega_converged=omega_converged,
            frequency=528.0 if action in {"healed", "converged"} else 432.0,
            reason=reason,
            recommended_prompt=recommended_prompt,
            metadata={
                "status": status,
                "exit_code": exit_code,
                "timed_out": timed_out,
                "healed": bool(entropy.get("healed")),
                "metrics": metrics.to_dict(),
                "entropy": entropy,
            },
        )
        return self._record_event(event)

    def record_tool_firewall(
        self,
        *,
        tool: str,
        status: str,
        reason: str,
        args: dict[str, Any] | None = None,
        frequency: float = 432.0,
    ) -> dict[str, Any]:
        """Record a tool-bridge decision as a Nexus event."""

        clean_args = _scrub_args(args or {})
        rejected = status in {"rejected", "blocked", "error"}
        action = "sacred_corruption" if rejected else "observed"
        event = CorruptionEvent(
            event_id=_event_id("tool_bridge", tool, status, reason),
            ts=_utc_iso(),
            job_id="tool_bridge",
            agent="tool_bridge",
            phase=tool,
            action=action,
            severity=0.72 if rejected else 0.0,
            coherence=0.432 if rejected else 0.96,
            entropy_level=0.528 if rejected else 0.04,
            signal_noise_ratio=1.894 if rejected else 25.0,
            omega_converged=False,
            frequency=frequency,
            reason=reason,
            recommended_prompt=creative_corruption_prompt(f"{tool}: {reason}", reason=reason) if rejected else "",
            metadata={"tool": tool, "status": status, "args": clean_args},
        )
        recorded = self._record_event(event)
        if rejected:
            with self._lock:
                self._counts["tool_rejections"] += 1
        return recorded

    def record_ruflo_coherence(
        self,
        *,
        task: str,
        coherence: float,
        agent_id: str = "ruflo",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Detect repeated Ruflo stalls and return the Nexus action."""

        clean_coherence = _clamp(float(coherence))
        key = f"{agent_id}:{hashlib.sha256(str(task or '').encode()).hexdigest()[:12]}"
        with self._lock:
            if clean_coherence < SACRED_CORRUPTION_COHERENCE_THRESHOLD:
                self._ruflo_low_coherence[key] = self._ruflo_low_coherence.get(key, 0) + 1
            else:
                self._ruflo_low_coherence.pop(key, None)
            stall_count = self._ruflo_low_coherence.get(key, 0)

        action = "sacred_corruption" if stall_count >= 2 else "observed"
        reason = (
            f"Ruflo coherence stayed below {SACRED_CORRUPTION_COHERENCE_THRESHOLD:.2f} for {stall_count} signals."
            if action == "sacred_corruption"
            else "Ruflo coherence signal observed."
        )
        event = CorruptionEvent(
            event_id=_event_id(agent_id, "ruflo_coherence", str(stall_count), task),
            ts=_utc_iso(),
            job_id=agent_id,
            agent="ruflo",
            phase="swarm_coherence",
            action=action,
            severity=_severity(action, clean_coherence, 1.0 - clean_coherence),
            coherence=round(clean_coherence, 6),
            entropy_level=round(1.0 - clean_coherence, 6),
            signal_noise_ratio=round(clean_coherence / max(1e-8, 1.0 - clean_coherence), 6),
            omega_converged=False,
            frequency=432.0,
            reason=reason,
            recommended_prompt=creative_corruption_prompt(task, reason=reason) if action == "sacred_corruption" else "",
            metadata={"stall_count": stall_count, **(metadata or {})},
        )
        return self._record_event(event)

    def status(self, *, limit: int = 20) -> dict[str, Any]:
        with self._lock:
            events = list(self._events)[-max(1, int(limit)):]
            counts = dict(self._counts)
            omega = dict(self._last_omega_vector)
        return {
            "status": "online",
            "version": NEXUS_VERSION,
            "healing_events": counts["healing_events"],
            "sacred_corruptions": counts["sacred_corruptions"],
            "total_corruption_events": counts["total_corruption_events"],
            "omega_convergences": counts["omega_convergences"],
            "tool_rejections": counts["tool_rejections"],
            "omega_vector": omega,
            "last_event": events[-1] if events else None,
            "recent_events": events,
            "thresholds": {
                "omega_coherence": OMEGA_COHERENCE_THRESHOLD,
                "omega_entropy": OMEGA_ENTROPY_THRESHOLD,
                "sacred_corruption_coherence": SACRED_CORRUPTION_COHERENCE_THRESHOLD,
            },
            "fake_success": False,
        }

    def reset(self) -> None:
        with self._lock:
            self._events.clear()
            for key in self._counts:
                self._counts[key] = 0
            self._last_omega_vector = {
                "converged": False,
                "coherence": 0.0,
                "entropy_level": 0.0,
                "thresholds": {
                    "coherence": OMEGA_COHERENCE_THRESHOLD,
                    "entropy": OMEGA_ENTROPY_THRESHOLD,
                },
            }
            self._ruflo_low_coherence.clear()

    def _classify_action(
        self,
        *,
        agent: str,
        status: str,
        coherence: float,
        entropy_level: float,
        omega_converged: bool,
        timed_out: bool,
        exit_code: Any,
    ) -> tuple[str, str]:
        if omega_converged:
            return "converged", "Ω-point convergence threshold reached."
        if coherence < SACRED_CORRUPTION_COHERENCE_THRESHOLD or timed_out or status in {"failed", "error", "timeout"}:
            return "sacred_corruption", "Agent stalled or diverged; issue a safe creative retry prompt."
        if entropy_level > OMEGA_ENTROPY_THRESHOLD:
            return "healed", "Entropy exceeded threshold; 528Hz healing path selected."
        if exit_code not in (None, 0):
            return "sacred_corruption", "Non-zero exit code; issue a safe creative retry prompt."
        if agent in {"ruflo", "swarm"} and coherence < 0.68:
            return "healed", "Ruflo swarm coherence is low; stabilize before retry."
        return "observed", "Job telemetry observed; no correction needed."

    def _record_event(self, event: CorruptionEvent) -> dict[str, Any]:
        payload = event.to_dict()
        with self._lock:
            self._events.append(payload)
            if event.action == "healed":
                self._counts["healing_events"] += 1
            elif event.action == "sacred_corruption":
                self._counts["sacred_corruptions"] += 1
            elif event.action == "converged":
                self._counts["omega_convergences"] += 1
            if event.action in {"healed", "sacred_corruption", "converged"}:
                self._counts["total_corruption_events"] += 1
            self._last_omega_vector = {
                "converged": event.omega_converged,
                "coherence": event.coherence,
                "entropy_level": event.entropy_level,
                "last_action": event.action,
                "last_event_id": event.event_id,
                "thresholds": {
                    "coherence": OMEGA_COHERENCE_THRESHOLD,
                    "entropy": OMEGA_ENTROPY_THRESHOLD,
                },
            }
        try:
            AkashicNetwork().broadcast(event.frequency, {"type": "quantum_corruption_nexus", "event": payload})
        except Exception:
            pass
        return payload


def get_quantum_corruption_nexus() -> QuantumCorruptionNexus:
    return QuantumCorruptionNexus()


def analyze_job(job: Any, result: dict[str, Any] | None = None, *, phase: str = "finished") -> dict[str, Any]:
    return get_quantum_corruption_nexus().analyze_job(job, result, phase=phase)


def quantum_nexus_status(limit: int = 20) -> dict[str, Any]:
    return get_quantum_corruption_nexus().status(limit=limit)


def creative_corruption_prompt(task: str, *, reason: str = "") -> str:
    """Return a safe divergent-thinking prompt, not a destructive mutation."""

    clean_task = _preview_text(task, limit=1200)
    clean_reason = _preview_text(reason, limit=300)
    return (
        "Retry this task with a divergent but safe strategy.\n"
        f"Reason: {clean_reason or 'low coherence / local minimum'}\n\n"
        "Constraints:\n"
        "- Preserve user files and do not revert unknown changes.\n"
        "- Do not expose secrets or session material.\n"
        "- Generate two alternative hypotheses, choose the smallest testable one, then verify.\n"
        "- Prefer read-only inspection before edits.\n\n"
        f"Original task:\n{clean_task}"
    )


def _as_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "to_dict"):
        try:
            return dict(value.to_dict())
        except Exception:
            pass
    out: dict[str, Any] = {}
    for name in ("job_id", "agent", "task", "status", "exit_code", "metadata"):
        if hasattr(value, name):
            out[name] = getattr(value, name)
    return out


def _preview_text(value: Any, *, limit: int = 2000) -> str:
    return str(value or "")[: max(1, int(limit))]


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _event_id(*parts: str) -> str:
    digest = hashlib.sha256("\n".join(str(part) for part in parts).encode("utf-8", errors="replace")).hexdigest()
    return f"qcn_{digest[:16]}"


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def _severity(action: str, coherence: float, entropy_level: float) -> float:
    if action == "converged":
        return 1.0
    if action == "healed":
        return round(_clamp(entropy_level / max(OMEGA_ENTROPY_THRESHOLD, 1e-8)), 6)
    if action == "sacred_corruption":
        return round(_clamp(max(1.0 - coherence, entropy_level)), 6)
    return 0.0


def _scrub_args(args: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in args.items():
        lowered = str(key).lower()
        if any(marker in lowered for marker in ("key", "token", "secret", "password", "bearer")):
            out[key] = "[REDACTED]"
        elif isinstance(value, str):
            out[key] = _preview_text(value, limit=500)
        else:
            out[key] = value
    return out
