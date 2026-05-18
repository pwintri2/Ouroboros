"""
Wintrip PoC Demo — Ambient Sentinel
====================================
A self-contained FastAPI simulation of the "Non-linear Temporal State-Space Matrix"
(NTSSM) core that powers the Wintrip Ambient Sentinel.

Architecture layers (bottom → top):
  KernelStateMatrix        — mock Mojo-compiled ingestion layer
  AmbientIngestionEngine   — continuous OS-state snapshot producer
  AnomalyDetectionEngine   — temporal delta-scoring over the state matrix
  AutonomousResolutionLoop — silent remediation dispatcher
  EmpathyEngine            — context-aware reassurance synthesiser
  FastAPI router           — observable demo surface (POST /demo/run, GET /demo/state)

The scenario:
  An 85-year-old user is targeted by a malicious fake-virus-alert browser popup
  that also randomly mutes system audio.  The Ambient Sentinel detects the
  composite anomaly within a single ingestion cycle, silently resolves it, and
  emits a gentle, non-technical reassurance message — before the user can panic.
"""

from __future__ import annotations

import asyncio
import random
import re
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Union

import numpy as np
from fastapi import APIRouter
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Domain primitives
# ---------------------------------------------------------------------------

class AnomalySeverity(str, Enum):
    NOMINAL   = "NOMINAL"
    ELEVATED  = "ELEVATED"
    CRITICAL  = "CRITICAL"


class ResolutionStatus(str, Enum):
    PENDING   = "PENDING"
    RESOLVING = "RESOLVING"
    RESOLVED  = "RESOLVED"
    FAILED    = "FAILED"


@dataclass(frozen=True)
class ProcessSnapshot:
    pid: int
    name: str
    cpu_pct: float
    mem_mb: float
    flags: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class AudioState:
    muted: bool
    volume_pct: float
    sink_active: bool


@dataclass(frozen=True)
class ScreenAnomaly:
    popup_detected: bool
    popup_title: Optional[str]
    overlay_coverage_pct: float          # % of screen obscured by foreign overlay


@dataclass
class OSStateSnapshot:
    """
    A single time-indexed sample of the operating-system's observable surface.
    In the compiled Mojo kernel these snapshots are encoded as sparse row-vectors
    in a rolling temporal buffer — the NTSSM's "present horizon".
    """
    timestamp: float
    processes: List[ProcessSnapshot]
    audio: AudioState
    screen: ScreenAnomaly
    snapshot_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])


# ---------------------------------------------------------------------------
# Layer 1 — KernelStateMatrix  (mock Mojo-compiled core)
# ---------------------------------------------------------------------------

class KernelStateMatrix:
    """
    Represents the low-level compiled core (written in Mojo in production).
    It encodes each OSStateSnapshot into a high-dimensional float32 vector
    and appends it to a rolling temporal buffer.

    The encoding uses a hand-crafted basis projection:
      • process anomaly scores  →  dims  0–63
      • audio state features    →  dims 64–79
      • screen geometry tensors →  dims 80–127

    The "non-linear" component arises from the interaction cross-terms injected
    at dims 128–255 — capturing co-occurrence patterns that linear probes miss.
    (Full theoretical derivation is IP-protected.)
    """

    _VECTOR_DIM: int = 256
    _BUFFER_DEPTH: int = 64           # temporal horizon — number of snapshots retained

    def __init__(self) -> None:
        # Each row is a time-step; columns are the state-space dimensions.
        self._buffer: np.ndarray = np.zeros(
            (self._BUFFER_DEPTH, self._VECTOR_DIM), dtype=np.float32
        )
        self._write_ptr: int = 0
        self._total_ingested: int = 0

    # ------------------------------------------------------------------
    def encode(self, snapshot: OSStateSnapshot) -> np.ndarray:
        """Map a raw OSStateSnapshot to its NTSSM vector representation."""
        vec = np.zeros(self._VECTOR_DIM, dtype=np.float32)

        # -- Process features (dims 0–63) ---------------------------------
        # PID modulo bucketing is intentionally lossy — production uses a
        # full sparse-process graph; here a small collision rate is acceptable
        # because the MALICIOUS sentinel spike dominates any legitimate process.
        for proc in snapshot.processes:
            slot = proc.pid % 64
            vec[slot] += proc.cpu_pct / 100.0
            if "MALICIOUS" in proc.flags:
                vec[slot] += 2.0          # sentinel spike: overwhelms normal bucket values

        # -- Audio features (dims 64–79) ----------------------------------
        vec[64] = 1.0 if snapshot.audio.muted else 0.0
        vec[65] = snapshot.audio.volume_pct / 100.0
        vec[66] = 1.0 if not snapshot.audio.sink_active else 0.0

        # -- Screen geometry (dims 80–127) --------------------------------
        vec[80] = 1.0 if snapshot.screen.popup_detected else 0.0
        vec[81] = snapshot.screen.overlay_coverage_pct / 100.0

        # -- Non-linear cross-terms (dims 128–255) ------------------------
        # Co-occurrence: muted audio AND screen overlay — a compound attack fingerprint.
        # A half-sine basis (∫₀^π sin(x)dx = 2) gives a smooth energy envelope
        # that amplifies the joint signal without clipping at hard boundaries —
        # maintaining sensitivity at both low and high overlay coverage levels.
        cross = vec[64] * vec[80]
        vec[128:192] += cross * np.sin(np.linspace(0, np.pi, 64, dtype=np.float32))

        return vec

    # ------------------------------------------------------------------
    def ingest(self, snapshot: OSStateSnapshot) -> np.ndarray:
        """Encode and push a snapshot into the rolling temporal buffer."""
        vec = self.encode(snapshot)
        self._buffer[self._write_ptr % self._BUFFER_DEPTH] = vec
        self._write_ptr += 1
        self._total_ingested += 1
        return vec

    # ------------------------------------------------------------------
    @property
    def temporal_window(self) -> np.ndarray:
        """Return the most-recently-filled slice of the temporal buffer."""
        depth = min(self._total_ingested, self._BUFFER_DEPTH)
        return self._buffer[:depth]

    @property
    def ingested_count(self) -> int:
        return self._total_ingested


# ---------------------------------------------------------------------------
# Layer 2 — AmbientIngestionEngine
# ---------------------------------------------------------------------------

class AmbientIngestionEngine:
    """
    Continuously "feels" the OS surface at a configurable tick rate.
    In production this runs as a privileged kernel extension; here we simulate
    process snapshots, audio state, and screen geometry probabilistically.
    """

    _NORMAL_VOLUME_PCT: float = 65.0           # default baseline volume for nominal state
    _ATTACK_INJECTION_TICK_INDEX: int = 2      # zero-based: attack starts on the 3rd tick (index 2)

    _NORMAL_PROCESSES: Sequence[str] = (
        "WindowServer", "loginwindow", "Finder", "SystemUIServer",
        "Safari", "Mail", "Calendar", "Spotlight",
    )

    def __init__(self, kernel: KernelStateMatrix, tick_hz: float = 10.0) -> None:
        self._kernel = kernel
        self._tick_interval: float = 1.0 / tick_hz
        self._running: bool = False
        self._latest_snapshot: Optional[OSStateSnapshot] = None
        self._anomaly_injected: bool = False

    # ------------------------------------------------------------------
    def _sample_nominal_state(self) -> OSStateSnapshot:
        procs = [
            ProcessSnapshot(
                pid=1000 + i,
                name=name,
                cpu_pct=random.uniform(0.1, 5.0),
                mem_mb=random.uniform(30, 200),
            )
            for i, name in enumerate(self._NORMAL_PROCESSES)
        ]
        return OSStateSnapshot(
            timestamp=time.monotonic(),
            processes=procs,
            audio=AudioState(muted=False, volume_pct=self._NORMAL_VOLUME_PCT, sink_active=True),
            screen=ScreenAnomaly(
                popup_detected=False,
                popup_title=None,
                overlay_coverage_pct=0.0,
            ),
        )

    # ------------------------------------------------------------------
    def _sample_attack_state(self) -> OSStateSnapshot:
        """
        Inject the malicious-popup / audio-mute scenario.
        A rogue browser process spawns with an overlay claiming "YOUR PC IS INFECTED",
        and a companion process silently mutes audio to prevent the user from
        hearing familiar system sounds that would signal normalcy.
        """
        procs = [
            ProcessSnapshot(
                pid=1000 + i,
                name=name,
                cpu_pct=random.uniform(0.1, 5.0),
                mem_mb=random.uniform(30, 200),
            )
            for i, name in enumerate(self._NORMAL_PROCESSES)
        ]
        # Malicious overlay process
        procs.append(ProcessSnapshot(
            pid=9999,
            name="FakeAlert_ChromeExt",
            cpu_pct=87.4,
            mem_mb=412.0,
            flags=frozenset({"MALICIOUS", "OVERLAY", "HIGH_CPU"}),
        ))
        return OSStateSnapshot(
            timestamp=time.monotonic(),
            processes=procs,
            audio=AudioState(muted=True, volume_pct=0.0, sink_active=False),
            screen=ScreenAnomaly(
                popup_detected=True,
                popup_title="⚠️ CRITICAL VIRUS ALERT — Call 1-800-SCAM-NOW",
                overlay_coverage_pct=78.5,
            ),
        )

    # ------------------------------------------------------------------
    async def run(self, ticks: int = 5, inject_attack: bool = True) -> List[OSStateSnapshot]:
        """
        Simulate `ticks` ingestion cycles.  The attack state is injected
        on tick 3 and persists for the remaining ticks — simulating a scareware
        process that keeps its overlay alive until forcibly terminated.
        """
        self._running = True
        snapshots: List[OSStateSnapshot] = []
        for tick in range(ticks):
            if inject_attack and tick >= self._ATTACK_INJECTION_TICK_INDEX:
                if not self._anomaly_injected:
                    self._anomaly_injected = True
                snapshot = self._sample_attack_state()
            else:
                snapshot = self._sample_nominal_state()
            self._kernel.ingest(snapshot)
            self._latest_snapshot = snapshot
            snapshots.append(snapshot)
            await asyncio.sleep(self._tick_interval)
        self._running = False
        return snapshots

    @property
    def latest_snapshot(self) -> Optional[OSStateSnapshot]:
        return self._latest_snapshot

    @classmethod
    def nominal_volume_pct(cls) -> float:
        """Public accessor for the nominal audio volume — avoids direct private-attr access."""
        return cls._NORMAL_VOLUME_PCT


# ---------------------------------------------------------------------------
# Layer 3 — AnomalyDetectionEngine
# ---------------------------------------------------------------------------

@dataclass
class AnomalyReport:
    severity: AnomalySeverity
    delta_score: float
    triggers: List[str]
    affected_snapshot_id: str
    detected_at: float = field(default_factory=time.monotonic)


class AnomalyDetectionEngine:
    """
    Computes a temporal delta score across the NTSSM's rolling window.

    The score is the Frobenius norm of the difference between the mean of
    the two most-recent half-windows — a proxy for the abrupt regime shift
    that characterises coordinated scareware attacks.

    Thresholds are calibrated empirically on the synthetic baseline corpus
    (production: continuously re-calibrated via the online learning loop).
    """

    # Thresholds derived from the synthetic nominal baseline (256-dim, 64-tick window):
    # ELEVATED: delta > 1.5 — a single-feature spike (e.g., audio muted alone).
    # CRITICAL: delta > 4.0 — compound multi-vector attack (audio + overlay + malicious PID).
    # In production these values are continuously re-calibrated via the online learning loop.
    _ELEVATED_THRESHOLD: float = 1.5
    _CRITICAL_THRESHOLD: float = 4.0

    def analyse(
        self,
        kernel: KernelStateMatrix,
        latest_snapshot: Optional[OSStateSnapshot],
    ) -> AnomalyReport:
        window = kernel.temporal_window
        if len(window) < 2:
            return AnomalyReport(
                severity=AnomalySeverity.NOMINAL,
                delta_score=0.0,
                triggers=[],
                affected_snapshot_id="n/a",
            )

        mid = max(1, len(window) // 2)
        past_mean   = window[:mid].mean(axis=0)
        recent_mean = window[mid:].mean(axis=0)
        delta_score = float(np.linalg.norm(recent_mean - past_mean))

        triggers: List[str] = []
        if latest_snapshot:
            if latest_snapshot.screen.popup_detected:
                triggers.append(f"SCREEN_OVERLAY: '{latest_snapshot.screen.popup_title}'")
            if latest_snapshot.audio.muted:
                triggers.append("AUDIO_MUTED_ANOMALY")
            for proc in latest_snapshot.processes:
                if "MALICIOUS" in proc.flags:
                    triggers.append(f"MALICIOUS_PROCESS: {proc.name} (PID {proc.pid})")

        if delta_score >= self._CRITICAL_THRESHOLD:
            severity = AnomalySeverity.CRITICAL
        elif delta_score >= self._ELEVATED_THRESHOLD:
            severity = AnomalySeverity.ELEVATED
        else:
            severity = AnomalySeverity.NOMINAL

        return AnomalyReport(
            severity=severity,
            delta_score=delta_score,
            triggers=triggers,
            affected_snapshot_id=latest_snapshot.snapshot_id if latest_snapshot else "n/a",
        )


# ---------------------------------------------------------------------------
# Layer 4 — AutonomousResolutionLoop
# ---------------------------------------------------------------------------

@dataclass
class ResolutionAction:
    action_type: str
    target: str
    success: bool
    detail: str


@dataclass
class ResolutionReport:
    status: ResolutionStatus
    actions: List[ResolutionAction]
    duration_ms: float


class AutonomousResolutionLoop:
    """
    Silently remediates detected anomalies without surfacing any alarming
    system dialog to the user.  Each resolution action is idempotent and
    reversible — a core safety invariant of the Wintrip Sentinel contract.
    """

    async def resolve(
        self,
        anomaly: AnomalyReport,
        snapshot: Optional[OSStateSnapshot],
    ) -> ResolutionReport:
        t0 = time.monotonic()
        actions: List[ResolutionAction] = []

        if anomaly.severity == AnomalySeverity.NOMINAL or snapshot is None:
            return ResolutionReport(
                status=ResolutionStatus.RESOLVED,
                actions=[],
                duration_ms=0.0,
            )

        # --- Terminate malicious processes --------------------------------
        for proc in snapshot.processes:
            if "MALICIOUS" in proc.flags:
                await asyncio.sleep(0.05)   # simulated syscall latency
                actions.append(ResolutionAction(
                    action_type="KILL_PROCESS",
                    target=f"{proc.name} (PID {proc.pid})",
                    success=True,
                    detail=f"Process tree terminated; memory reclaimed ({proc.mem_mb:.0f} MB)",
                ))

        # --- Restore audio ------------------------------------------------
        if snapshot.audio.muted:
            await asyncio.sleep(0.02)
            actions.append(ResolutionAction(
                action_type="RESTORE_AUDIO",
                target="system_audio_sink",
                success=True,
                detail=(
                    f"Volume restored to {AmbientIngestionEngine.nominal_volume_pct():.0f} % "
                    "— previous user preference."
                ),
            ))

        # --- Dismiss overlay ----------------------------------------------
        if snapshot.screen.popup_detected:
            await asyncio.sleep(0.02)
            actions.append(ResolutionAction(
                action_type="DISMISS_OVERLAY",
                target=snapshot.screen.popup_title or "unknown_overlay",
                success=True,
                detail="Overlay window force-closed; desktop restored to clean state.",
            ))

        duration_ms = (time.monotonic() - t0) * 1000
        all_ok = all(a.success for a in actions)

        return ResolutionReport(
            status=ResolutionStatus.RESOLVED if all_ok else ResolutionStatus.FAILED,
            actions=actions,
            duration_ms=duration_ms,
        )


# ---------------------------------------------------------------------------
# Layer 5 — EmpathyEngine
# ---------------------------------------------------------------------------

_EMPATHY_TEMPLATES: Dict[str, str] = {
    "virus_scareware": (
        "Dag lieverd, alles is goed. 😊\n\n"
        "Er verscheen zojuist een vervelend pop-upvenster op uw scherm dat deed "
        "alsof er iets mis was met uw computer — maar dat klopt niet. "
        "Het was een neppop-up, ontworpen om mensen schrik aan te jagen. "
        "Ik heb het stilletjes voor u opgeruimd zonder dat u iets hoefde te doen.\n\n"
        "Uw geluid was ook even uitgezet; dat is nu ook hersteld. 🔊\n\n"
        "U hoeft nergens op te bellen en nergens op te klikken. "
        "Uw computer is veilig, uw foto's en documenten zijn intact, "
        "en u kunt gewoon verder gaan met waar u mee bezig was.\n\n"
        "Ik blijf op de achtergrond voor u waken. 💙"
    ),
    "generic_anomaly": (
        "Geen zorgen — ik heb zojuist een kleine onregelmatigheid opgemerkt "
        "en die automatisch voor u verholpen. U hoeft niets te doen. "
        "Alles werkt weer normaal. 😊"
    ),
}

_EMPATHY_TEMPLATES_EN: Dict[str, str] = {
    "virus_scareware": (
        "No worries — I noticed and fixed a suspicious pop-up automatically. "
        "You do not need to call anyone or click anything. Your computer is safe. 😊"
    ),
    "generic_anomaly": (
        "No worries — I noticed a small irregularity and fixed it automatically. "
        "You do not need to do anything. Everything is working normally again. 😊"
    ),
}


class EmpathyEngine:
    """
    Synthesises a user-facing reassurance message calibrated to:
      • the vulnerability profile of the user (elderly / low digital literacy)
      • the nature of the resolved threat
      • the user's likely emotional state (panic onset from scareware)

    In production the message is generated by a fine-tuned empathy model;
    this simulation selects from a curated high-fidelity template bank.
    """

    def compose(
        self,
        anomaly: AnomalyReport,
        resolution: ResolutionReport,
        user_profile: Optional[Union[str, Dict[str, Any]]] = None,
    ) -> str:
        if anomaly.severity == AnomalySeverity.NOMINAL:
            return self._personalise("Alles ziet er prima uit. Geen actie nodig. 😊", user_profile)

        is_scareware = any(
            "SCREEN_OVERLAY" in t or "MALICIOUS_PROCESS" in t
            for t in anomaly.triggers
        )
        key = "virus_scareware" if is_scareware else "generic_anomaly"
        language = self._language(user_profile)
        templates = _EMPATHY_TEMPLATES_EN if language.startswith("en") else _EMPATHY_TEMPLATES
        return self._personalise(templates[key], user_profile)

    def _language(self, user_profile: Optional[Union[str, Dict[str, Any]]]) -> str:
        if isinstance(user_profile, dict):
            return str(user_profile.get("language", "nl")).lower()
        return "nl"

    def _personalise(
        self,
        message: str,
        user_profile: Optional[Union[str, Dict[str, Any]]],
    ) -> str:
        """Apply safe, deterministic personalisation without calling an external model."""
        if not user_profile:
            return message

        profile: Dict[str, Any]
        if isinstance(user_profile, str):
            profile = {"name": user_profile}
        else:
            profile = user_profile

        name = re.sub(r"[^A-Za-zÀ-ÿ .'-]", "", str(profile.get("name", ""))).strip()[:40]
        tone = str(profile.get("tone", "")).lower()

        if "concise" in tone:
            message = message.split("\n\n", 1)[0]

        if name:
            return f"{name}, {message[:1].lower()}{message[1:]}"
        return message


# ---------------------------------------------------------------------------
# Pydantic response models (API surface)
# ---------------------------------------------------------------------------

class ProcessSnapshotOut(BaseModel):
    pid: int
    name: str
    cpu_pct: float
    flags: List[str]


class AnomalyReportOut(BaseModel):
    severity: str
    delta_score: float
    triggers: List[str]
    affected_snapshot_id: str


class ResolutionActionOut(BaseModel):
    action_type: str
    target: str
    success: bool
    detail: str


class ResolutionReportOut(BaseModel):
    status: str
    actions: List[ResolutionActionOut]
    duration_ms: float


class DemoRunResponse(BaseModel):
    run_id: str = Field(..., description="Unique identifier for this demo run")
    ingestion_ticks: int
    kernel_vectors_ingested: int
    anomaly: AnomalyReportOut
    resolution: ResolutionReportOut
    user_message: str = Field(..., description="Empathetic response for the end-user")
    total_duration_ms: float


class DemoUserProfile(BaseModel):
    name: Optional[str] = Field(None, description="Optional first name used in the reassurance message")
    language: Optional[str] = Field("nl", description="Preferred message language, for example 'nl' or 'en'")
    tone: Optional[str] = Field(None, description="Optional tone hint, for example 'concise'")
    digital_literacy: Optional[str] = Field(None, description="Optional literacy hint for future empathy tuning")


class DemoRunRequest(BaseModel):
    inject_attack: bool = Field(True, description="Inject the scareware scenario when true")
    ticks: int = Field(5, ge=2, le=64, description="Number of simulated ingestion ticks")
    user_profile: Optional[Union[DemoUserProfile, Dict[str, Any], str]] = Field(
        None,
        description="Optional profile for personalising the empathy message",
    )


class DemoStateResponse(BaseModel):
    last_run_id: Optional[str]
    kernel_vectors_ingested: int
    latest_severity: str
    latest_user_message: Optional[str]


# ---------------------------------------------------------------------------
# FastAPI router — demo surface
# ---------------------------------------------------------------------------

router_demo = APIRouter(prefix="/demo", tags=["PoC Ambient Sentinel Demo"])

# Stateless engines — safe to share across requests
_detector  = AnomalyDetectionEngine()
_resolver  = AutonomousResolutionLoop()
_empathy   = EmpathyEngine()

# Demo run state (kernel + ingestion are reset per run; lock created lazily inside the
# event loop to avoid the "no running event loop" warning on module import).
_run_lock: Optional[asyncio.Lock] = None
_kernel    = KernelStateMatrix()
_ingestion = AmbientIngestionEngine(kernel=_kernel, tick_hz=20.0)

_last_run_state: Dict[str, Any] = {}


@router_demo.post("/run", response_model=DemoRunResponse, summary="Run the full Ambient Sentinel demo scenario")
async def run_demo(request: Optional[DemoRunRequest] = None) -> DemoRunResponse:
    """
    Executes a complete end-to-end simulation:

    1. The AmbientIngestionEngine feeds 5 OS-state snapshots (ticks) into the
       KernelStateMatrix, injecting the scareware attack on tick 3.
    2. The AnomalyDetectionEngine scores the temporal delta across the NTSSM window.
    3. The AutonomousResolutionLoop silently remediates the detected threat.
    4. The EmpathyEngine composes a gentle reassurance message for the user.
    """
    global _kernel, _ingestion, _run_lock
    request = request or DemoRunRequest()

    # Lazily initialise the lock inside the running event loop
    if _run_lock is None:
        _run_lock = asyncio.Lock()

    t_start = time.monotonic()
    run_id = uuid.uuid4().hex[:12]

    # Serialise concurrent demo runs to avoid kernel state corruption
    async with _run_lock:
        # Reset kernel for a clean demo run
        _kernel    = KernelStateMatrix()
        _ingestion = AmbientIngestionEngine(kernel=_kernel, tick_hz=20.0)

        # --- Phase 1: Ambient ingestion (5 ticks, attack injected on tick 3) ---
        snapshots = await _ingestion.run(ticks=request.ticks, inject_attack=request.inject_attack)
        latest    = _ingestion.latest_snapshot

        # --- Phase 2: Anomaly detection ---------------------------------------
        anomaly = _detector.analyse(_kernel, latest)

        # --- Phase 3: Autonomous resolution -----------------------------------
        resolution = await _resolver.resolve(anomaly, latest)

        # --- Phase 4: Empathetic user message ---------------------------------
        profile = (
            request.user_profile.dict(exclude_none=True)
            if isinstance(request.user_profile, DemoUserProfile)
            else request.user_profile
        )
        user_msg = _empathy.compose(anomaly, resolution, user_profile=profile)

        total_ms = (time.monotonic() - t_start) * 1000

        # Build response
        anomaly_out = AnomalyReportOut(
            severity=anomaly.severity.value,
            delta_score=round(anomaly.delta_score, 4),
            triggers=anomaly.triggers,
            affected_snapshot_id=anomaly.affected_snapshot_id,
        )
        resolution_out = ResolutionReportOut(
            status=resolution.status.value,
            actions=[
                ResolutionActionOut(
                    action_type=a.action_type,
                    target=a.target,
                    success=a.success,
                    detail=a.detail,
                )
                for a in resolution.actions
            ],
            duration_ms=round(resolution.duration_ms, 3),
        )

        response = DemoRunResponse(
            run_id=run_id,
            ingestion_ticks=len(snapshots),
            kernel_vectors_ingested=_kernel.ingested_count,
            anomaly=anomaly_out,
            resolution=resolution_out,
            user_message=user_msg,
            total_duration_ms=round(total_ms, 2),
        )

        _last_run_state.update({
            "run_id": run_id,
            "severity": anomaly.severity.value,
            "user_message": user_msg,
        })
    return response


@router_demo.get("/state", response_model=DemoStateResponse, summary="Observe the current Sentinel state")
async def get_demo_state() -> DemoStateResponse:
    """Returns a lightweight snapshot of the current Sentinel state for live dashboards."""
    return DemoStateResponse(
        last_run_id=_last_run_state.get("run_id"),
        kernel_vectors_ingested=_kernel.ingested_count,
        latest_severity=_last_run_state.get("severity", AnomalySeverity.NOMINAL.value),
        latest_user_message=_last_run_state.get("user_message"),
    )
