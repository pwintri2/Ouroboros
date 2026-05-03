"""Streaming Consciousness 11D Pocket adapter.

This incorporates the local prototype from Downloads into the trainer pipeline
as a bounded, observable runtime component: electrical dynamics, a byte stream,
and DHCP/TCP-like packet flow modulate the existing 11D Blue Brain pocket.

Why this change:
    The deep ecosystem buildplan adds OS/cloud/crawler overlays to the live 11D
    pocket. The overlay is exposed in status without changing the existing
    dataset feature contract.
"""

from __future__ import annotations

import importlib.util
import json
import os
import random
import struct
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

from controller.blue_brain_adapter import E_TYPES
from controller.safe_shell import workspace_root


APPROVAL_PHRASE = "Akkoord"
REQUIRED_PACKAGES = ("numpy",)
DIM_ELECTRICAL = 0
DIM_INFO = 3
DIM_NETWORK = 5
DIM_ROUTER_PULL = 7
DIM_ENTANGLEMENT = 9
_STATE_LOCK = threading.Lock()
_WORKER_THREAD: threading.Thread | None = None
_WORKER_STOP = threading.Event()
_POCKET: StreamingConsciousness11DPocket | None = None


class DHCPState(Enum):
    INIT = "INIT"
    DISCOVER_SENT = "DISCOVER_SENT"
    BOUND = "BOUND"


@dataclass
class ElectricalState:
    v_m: list[float] = field(default_factory=lambda: [0.0] * 11)
    i_inj: list[float] = field(default_factory=lambda: [0.0] * 11)
    tau: float = 20.0


@dataclass
class NetworkPacket:
    src_ip: str
    dst_ip: str
    protocol: str
    payload: bytes
    timestamp: float

    @property
    def size(self) -> int:
        return len(self.payload)


@dataclass
class NetworkConnection:
    device_id: str
    ip: str
    mac: str
    protocol: str
    last_seen: float
    gemma_context: dict[str, Any]
    pull_strength: float
    packet_count: int = 0
    route_superposition: list[str] = field(default_factory=list)
    observed_route: str = ""
    entangled_peers: list[str] = field(default_factory=list)


class SimulatedElectronNeuron:
    """Quantum Integrate-and-Fire neuron backed by a simulated electron spin.

    The state is a two-amplitude spinor. Integration is continuous and unitary;
    the classical spike is isolated in process_stream(), where measurement-like
    thresholding bridges the quantum state to the 11D stream.
    """

    def __init__(self, firing_threshold: float = 0.85, phase_gain: float = 0.65, np_module: Any | None = None) -> None:
        if np_module is None:
            import numpy as np

            np_module = np
        self.np = np_module
        self.firing_threshold = float(self.np.clip(float(firing_threshold), -1.0, 1.0))
        self.phase_gain = max(0.0, float(phase_gain))
        self.identity = self.np.eye(2, dtype=complex)
        self.sigma_x = self.np.array([[0, 1], [1, 0]], dtype=complex)
        self.sigma_y = self.np.array([[0, -1j], [1j, 0]], dtype=complex)
        self.sigma_z = self.np.array([[1, 0], [0, -1]], dtype=complex)
        self.state = self.np.array([1.0 + 0j, 0.0 + 0j], dtype=complex)
        self.armed_for_spike = False
        self.spike_count = 0
        self.last_expectation_z = 1.0
        self.last_angles = {"theta_x": 0.0, "theta_y": 0.0, "theta_z": 0.0}
        self.last_unitarity_error = 0.0

    def reset(self) -> None:
        self.state = self.np.array([1.0 + 0j, 0.0 + 0j], dtype=complex)
        self.armed_for_spike = False
        self.last_expectation_z = 1.0

    def integrate_signals(self, incoming_11d_vector: Any) -> Any:
        """Apply exact Pauli-axis unitary rotations from an incoming 11D vector."""
        vector = self._as_11d(incoming_11d_vector)
        theta_x, theta_y, theta_z = self._angles_from_11d(vector)

        # For a Pauli matrix sigma, exp(-i theta sigma / 2) is unitary:
        # R(theta) = cos(theta/2) I - i sin(theta/2) sigma.
        rx = self._rotation(self.sigma_x, theta_x)
        ry = self._rotation(self.sigma_y, theta_y)
        rz = self._rotation(self.sigma_z, theta_z)
        unitary = rz @ ry @ rx
        evolved = unitary @ self.state
        self.state = self._normalize(evolved)

        unitary_check = unitary.conjugate().T @ unitary
        self.last_unitarity_error = float(self.np.linalg.norm(unitary_check - self.identity))
        self.last_angles = {
            "theta_x": round(float(theta_x), 8),
            "theta_y": round(float(theta_y), 8),
            "theta_z": round(float(theta_z), 8),
        }
        return self.state.copy()

    def check_action_potential(self) -> float:
        """Return the Born expectation value <psi|Z|psi> in the range [-1, 1]."""
        bra = self.state.conjugate().T
        expectation = float(self.np.real(bra @ self.sigma_z @ self.state))
        expectation = float(self.np.clip(expectation, -1.0, 1.0))
        self.last_expectation_z = expectation
        return expectation

    def process_stream(self, incoming_11d_vector: Any) -> dict[str, Any]:
        """Integrate one 11D sample and emit a classical spike on threshold crossing."""
        vector = self._as_11d(incoming_11d_vector)
        self.integrate_signals(vector)
        expectation = self.check_action_potential()

        fired = bool(self.armed_for_spike and expectation >= self.firing_threshold)
        spike_vector = self.np.zeros(11, dtype=self.np.float32)
        if fired:
            spike_vector = (vector * expectation).astype(self.np.float32)
            self.spike_count += 1
            spike_index = self.spike_count
            self.reset()
        else:
            if expectation < self.firing_threshold:
                self.armed_for_spike = True
            spike_index = self.spike_count

        return {
            "fired": fired,
            "spike_index": int(spike_index),
            "expectation_z": round(float(expectation), 8),
            "membrane_potential": round(float(expectation), 8),
            "threshold": round(float(self.firing_threshold), 8),
            "spike_vector": [round(float(value), 6) for value in spike_vector.tolist()],
            "armed": bool(self.armed_for_spike),
            "state": self.status(),
        }

    def status(self) -> dict[str, Any]:
        probabilities = self.np.abs(self.state) ** 2
        return {
            "type": "simulated_electron_qif",
            "state_vector": [
                {"real": round(float(self.np.real(value)), 8), "imag": round(float(self.np.imag(value)), 8)}
                for value in self.state.tolist()
            ],
            "probabilities": [round(float(value), 8) for value in probabilities.tolist()],
            "expectation_z": round(float(self.last_expectation_z), 8),
            "threshold": round(float(self.firing_threshold), 8),
            "phase_gain": round(float(self.phase_gain), 8),
            "armed": bool(self.armed_for_spike),
            "spike_count": int(self.spike_count),
            "last_angles": dict(self.last_angles),
            "unitarity_error": round(float(self.last_unitarity_error), 12),
            "sdk": "none_numpy_classical_complex",
        }

    def _rotation(self, sigma: Any, theta: float) -> Any:
        return self.np.cos(theta / 2.0) * self.identity - 1j * self.np.sin(theta / 2.0) * sigma

    def _angles_from_11d(self, vector: Any) -> tuple[float, float, float]:
        norm_pressure = float(self.np.tanh(float(self.np.linalg.norm(vector)) / self.np.sqrt(11.0)))
        pressure_scale = 0.65 + 0.35 * norm_pressure
        theta_x = self.phase_gain * pressure_scale * float(self.np.tanh(vector[0] + 0.5 * vector[3] - 0.25 * vector[6]))
        theta_y = self.phase_gain * pressure_scale * float(self.np.tanh(vector[1] + 0.5 * vector[4] - 0.25 * vector[7]))
        theta_z = self.phase_gain * pressure_scale * float(self.np.tanh(vector[2] + 0.5 * vector[5] + 0.25 * vector[8] - 0.25 * vector[10]))
        return theta_x, theta_y, theta_z

    def _normalize(self, state: Any) -> Any:
        norm = float(self.np.linalg.norm(state))
        if norm <= 0.0:
            return self.np.array([1.0 + 0j, 0.0 + 0j], dtype=complex)
        return self.np.asarray(state, dtype=complex) / norm

    def _as_11d(self, value: Any) -> Any:
        vector = self.np.asarray(value, dtype=float).reshape(-1)
        if vector.size != 11:
            raise ValueError("Exacte invoer vereist: De array moet een 11D vector zijn.")
        if not bool(self.np.all(self.np.isfinite(vector))):
            raise ValueError("Exacte invoer vereist: De 11D vector mag geen NaN of inf bevatten.")
        return vector.astype(self.np.float64)


class MiniRouter:
    """Self-attracting, simulated router at the centre of the 11D pocket.

    The router does not bind TUN/TAP, sniff host packets, run DHCP on the LAN or
    forward traffic. It works on the pocket's simulated packet stream and can
    optionally ask a local Ollama model for read-only context labels.
    """

    def __init__(self, pocket: "StreamingConsciousness11DPocket") -> None:
        self.pocket = pocket
        self.connections: dict[str, NetworkConnection] = {}
        self.entanglement: dict[str, int] = {}
        self.gemma_model = (
            os.getenv("WINTRIP_MINI_ROUTER_GEMMA_MODEL")
            or os.getenv("WINTRIP_KNOWLEDGE_MODEL")
            or os.getenv("OLLAMA_MODEL")
            or "gemma4:latest"
        )
        self.gemma_enabled = os.getenv("WINTRIP_MINI_ROUTER_GEMMA", "").strip() == "1"
        self.gemma_timeout = max(0.5, min(float(os.getenv("WINTRIP_MINI_ROUTER_GEMMA_TIMEOUT", "6") or 6), 30.0))
        self.gemma_host_sensory = os.getenv("WINTRIP_MINI_ROUTER_GEMMA_HOST_SENSORY", "").strip() == "1"
        try:
            self.gemma_cooldown_seconds = max(
                0.0,
                min(float(os.getenv("WINTRIP_MINI_ROUTER_GEMMA_COOLDOWN_SECONDS", "8") or 8), 300.0),
            )
        except ValueError:
            self.gemma_cooldown_seconds = 8.0
        try:
            self.host_flow_limit = max(1, min(int(os.getenv("WINTRIP_MINI_ROUTER_HOST_FLOW_LIMIT", "3") or 3), 12))
        except ValueError:
            self.host_flow_limit = 3
        self.context_cache: dict[str, dict[str, Any]] = {}
        self.rotation_pull = 0.0
        self.total_packets_processed = 0
        self.last_context: dict[str, Any] = {}
        self.last_packet_route: dict[str, Any] = {}
        self.last_host_sensory_at = ""
        self.host_sensory_absorptions = 0
        self.last_gemma_attempt_monotonic = 0.0
        self.gemma_call_count = 0
        self.gemma_cooldown_skips = 0
        self.mode = "simulated_read_only"

    def discover_devices(self) -> None:
        """Simulate DHCP + mDNS/SSDP discovery inside the pocket subnet."""
        fake_devices = [
            {"id": "phone-01", "ip": "192.168.42.101", "mac": "aa:bb:cc:dd:ee:01", "protocol": "mDNS"},
            {"id": "laptop-01", "ip": "192.168.42.102", "mac": "aa:bb:cc:dd:ee:02", "protocol": "SSDP"},
            {"id": "iot-thermostat", "ip": "192.168.42.50", "mac": "aa:bb:cc:dd:ee:50", "protocol": "DHCP"},
        ]
        for device in fake_devices:
            conn = self.connections.get(device["id"])
            if conn is None:
                self.connections[device["id"]] = NetworkConnection(
                    device_id=device["id"],
                    ip=device["ip"],
                    mac=device["mac"],
                    protocol=device["protocol"],
                    last_seen=self.pocket.time,
                    gemma_context={
                        "device_type": _device_type_from_id(device["id"]),
                        "intent": "presence_announcement",
                        "sensitivity": "low",
                        "protocol_meaning": f"{device['protocol']} discovery beacon",
                        "emotional_tone": "neutral",
                        "security_risk": 1,
                        "source": "simulated_discovery",
                    },
                    pull_strength=0.3,
                    route_superposition=["local_pocket", "observe_only"],
                    observed_route="local_pocket",
                )
            else:
                conn.last_seen = self.pocket.time
                conn.pull_strength = min(1.0, conn.pull_strength + 0.01)

    def process_packet(self, packet: NetworkPacket) -> None:
        """Observe a simulated packet and fold its context into the pocket."""
        context = self._context_for_packet(packet)
        conn_id = f"{packet.src_ip}->{packet.dst_ip}:{packet.protocol}"
        conn = self.connections.get(conn_id)
        if conn is None:
            conn = NetworkConnection(
                device_id=conn_id,
                ip=packet.src_ip,
                mac="unknown",
                protocol=context.get("protocol", packet.protocol),
                last_seen=packet.timestamp,
                gemma_context=context,
                pull_strength=_pull_from_context(context, packet.size),
                packet_count=1,
                route_superposition=self._route_superposition(packet, context),
            )
            self.connections[conn_id] = conn
        else:
            conn.last_seen = packet.timestamp
            conn.protocol = context.get("protocol", packet.protocol)
            conn.gemma_context = context
            conn.pull_strength = min(1.0, 0.82 * conn.pull_strength + 0.18 * _pull_from_context(context, packet.size) + 0.03)
            conn.packet_count += 1
            conn.route_superposition = self._route_superposition(packet, context)

        conn.observed_route = self._observe_route(conn.route_superposition, context)
        self._update_entanglement(packet.src_ip, packet.dst_ip)
        conn.entangled_peers = self._peers_for_ip(packet.src_ip)
        self.total_packets_processed += 1
        self.last_context = dict(context)
        self.last_packet_route = {
            "connection": conn_id,
            "superposition": list(conn.route_superposition),
            "observed": conn.observed_route,
        }
        self._apply_pull_to_pocket(conn)
        self._encode_into_consciousness(packet, context, conn)

    def absorb_host_sensory(self, sensory: dict[str, Any]) -> None:
        """Fold real host flow/process metadata into the simulated router."""
        captured_at = str(sensory.get("last_snapshot_at") or sensory.get("captured_at") or "")
        if captured_at and captured_at == self.last_host_sensory_at:
            return
        flows = list(sensory.get("sample_flows") or [])[: self.host_flow_limit]
        if not flows:
            return
        for flow in flows:
            if not isinstance(flow, dict):
                continue
            src_ip = _endpoint_ip(str(flow.get("peer") or "host-sensory"))
            dst_ip = _endpoint_ip(str(flow.get("local") or self.pocket.local_ip))
            proto = str(flow.get("proto") or "TCP").upper()
            payload = (
                f"HOST_FLOW proto={proto} state={flow.get('state','')} "
                f"local={flow.get('local','')} peer={flow.get('peer','')} process={flow.get('process','')}"
            ).encode("utf-8", errors="replace")
            self.process_packet(NetworkPacket(src_ip, dst_ip, proto, payload[:512], self.pocket.time))
        self.last_host_sensory_at = captured_at
        self.host_sensory_absorptions += 1

    def status(self) -> dict[str, Any]:
        strongest = sorted(self.connections.values(), key=lambda item: item.pull_strength, reverse=True)[:5]
        return {
            "status": "active",
            "mode": self.mode,
            "connections": len(self.connections),
            "discovered_devices": sum(1 for item in self.connections.values() if item.mac != "unknown"),
            "packets_processed": int(self.total_packets_processed),
            "rotation_pull": round(float(self.rotation_pull), 6),
            "gemma": {
                "enabled": self.gemma_enabled,
                "model": self.gemma_model,
                "last_source": self.last_context.get("source", "none"),
                "host_sensory_enabled": self.gemma_host_sensory,
                "timeout_seconds": self.gemma_timeout,
                "cooldown_seconds": self.gemma_cooldown_seconds,
                "calls": int(self.gemma_call_count),
                "cooldown_skips": int(self.gemma_cooldown_skips),
            },
            "host_flow_limit": int(self.host_flow_limit),
            "strongest_connections": [
                {
                    "device_id": conn.device_id,
                    "ip": conn.ip,
                    "protocol": conn.protocol,
                    "pull_strength": round(float(conn.pull_strength), 6),
                    "packet_count": int(conn.packet_count),
                    "observed_route": conn.observed_route,
                    "risk": conn.gemma_context.get("security_risk", 0),
                }
                for conn in strongest
            ],
            "entanglement_pairs": len(self.entanglement),
            "host_sensory_absorptions": int(self.host_sensory_absorptions),
            "last_route": dict(self.last_packet_route),
            "real_forwarding": False,
            "real_packet_capture": False,
            "fake_success": False,
        }

    def _context_for_packet(self, packet: NetworkPacket) -> dict[str, Any]:
        cache_key = f"{packet.protocol}:{packet.payload[:80].hex()}"
        if cache_key in self.context_cache:
            cached = dict(self.context_cache[cache_key])
            cached["source"] = f"{cached.get('source', 'context')}:cache"
            return cached
        if packet.payload.startswith(b"HOST_FLOW") and not self.gemma_host_sensory:
            context = _heuristic_packet_context(packet)
            self.context_cache[cache_key] = dict(context)
            return context
        if self.gemma_enabled and self._gemma_budget_available():
            context = self._ask_gemma(packet)
            if context:
                self.context_cache[cache_key] = dict(context)
                return context
        context = _heuristic_packet_context(packet)
        self.context_cache[cache_key] = dict(context)
        return context

    def _gemma_budget_available(self) -> bool:
        now = time.monotonic()
        if self.last_gemma_attempt_monotonic and now - self.last_gemma_attempt_monotonic < self.gemma_cooldown_seconds:
            self.gemma_cooldown_skips += 1
            return False
        self.last_gemma_attempt_monotonic = now
        self.gemma_call_count += 1
        return True

    def _ask_gemma(self, packet: NetworkPacket) -> dict[str, Any]:
        prompt = (
            "Return ONLY valid JSON. Fill this exact schema for a synthetic/read-only packet observation:\n"
            '{"device_type":"web_client|server|iot|unknown_device","intent":"short intent",'
            '"sensitivity":"low|medium|high|critical","protocol":"TCP|UDP|DHCP|HTTP",'
            '"protocol_meaning":"short meaning","emotional_tone":"neutral|curious|calm|seeking","security_risk":0}\n'
            f"Observation: src={packet.src_ip}, dst={packet.dst_ip}, transport={packet.protocol}, "
            f"size={packet.size}, payload_hint={_payload_hint(packet.payload)}"
        )
        try:
            payload = json.dumps(
                {
                    "model": self.gemma_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "format": "json",
                    "stream": False,
                    "options": {"temperature": 0.0, "num_predict": 160},
                }
            ).encode("utf-8")
            request = urllib.request.Request(
                _ollama_chat_url(),
                data=payload,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=self.gemma_timeout) as response:
                raw = json.loads(response.read().decode("utf-8"))
            content = str((raw.get("message") or {}).get("content") or "").strip()
            parsed = _parse_context_json(content)
            parsed["source"] = f"ollama:{self.gemma_model}"
            return parsed
        except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError):
            return {}

    def _route_superposition(self, packet: NetworkPacket, context: dict[str, Any]) -> list[str]:
        routes = ["observe_only", "local_pocket"]
        if packet.dst_ip == "255.255.255.255" or packet.protocol == "DHCP":
            routes.append("pocket_dhcp_sim")
        if context.get("sensitivity") in {"high", "critical"} or float(context.get("security_risk") or 0) >= 7:
            routes.append("quarantine_shadow")
        elif packet.protocol in {"TCP", "UDP"}:
            routes.append("consciousness_buffer")
        return routes[:4]

    def _observe_route(self, routes: list[str], context: dict[str, Any]) -> str:
        if "quarantine_shadow" in routes:
            return "quarantine_shadow"
        if context.get("intent") == "presence_announcement" and "pocket_dhcp_sim" in routes:
            return "pocket_dhcp_sim"
        return "consciousness_buffer" if "consciousness_buffer" in routes else routes[0]

    def _update_entanglement(self, src_ip: str, dst_ip: str) -> None:
        pair = " <-> ".join(sorted([src_ip, dst_ip]))
        self.entanglement[pair] = int(self.entanglement.get(pair, 0)) + 1

    def _peers_for_ip(self, ip: str) -> list[str]:
        peers: list[str] = []
        for pair, count in sorted(self.entanglement.items(), key=lambda item: item[1], reverse=True):
            if ip in pair:
                peers.append(pair.replace(ip, "").replace(" <-> ", "").strip())
        return peers[:5]

    def _apply_pull_to_pocket(self, conn: NetworkConnection) -> None:
        np = self.pocket.np
        pull = float(np.clip(conn.pull_strength * 0.8, 0.0, 1.0))
        self.rotation_pull = float(0.7 * self.rotation_pull + 0.3 * pull)
        row_index = self.pocket.current_idx % len(self.pocket.X_base)
        self.pocket.X_base[row_index, DIM_NETWORK] = np.clip(self.pocket.X_base[row_index, DIM_NETWORK] + pull * 0.25, -3.0, 3.5)
        self.pocket.X_base[row_index, DIM_ROUTER_PULL] = np.clip(self.pocket.X_base[row_index, DIM_ROUTER_PULL] + pull * 0.4, -3.0, 3.5)
        self.pocket.X_base[row_index, DIM_ENTANGLEMENT] = np.clip(
            self.pocket.X_base[row_index, DIM_ENTANGLEMENT] + min(len(conn.entangled_peers), 5) * 0.04 + pull * 0.25,
            -3.0,
            3.5,
        )
        heat = pull * 0.08
        if self.pocket.elec.i_inj:
            self.pocket.elec.i_inj[row_index % len(self.pocket.elec.i_inj)] += heat

    def _encode_into_consciousness(self, packet: NetworkPacket, context: dict[str, Any], conn: NetworkConnection) -> None:
        meta = {
            "router": "mini",
            "mode": self.mode,
            "src": packet.src_ip,
            "dst": packet.dst_ip,
            "protocol": packet.protocol,
            "packet_size": packet.size,
            "pull_strength": round(float(conn.pull_strength), 6),
            "rotation_pull": round(float(self.rotation_pull), 6),
            "observed_route": conn.observed_route,
            "gemma_context": context,
        }
        self.pocket.consciousness_buffer.extend(json.dumps(meta, sort_keys=True).encode("utf-8"))
        if len(self.pocket.consciousness_buffer) > self.pocket.max_buffer:
            self.pocket.consciousness_buffer = self.pocket.consciousness_buffer[-self.pocket.max_buffer // 2 :]


def _device_type_from_id(device_id: str) -> str:
    text = str(device_id or "").lower()
    if "phone" in text:
        return "phone"
    if "laptop" in text:
        return "laptop"
    if "thermostat" in text or "iot" in text:
        return "iot_sensor"
    return "unknown_device"


def _pull_from_context(context: dict[str, Any], packet_size: int) -> float:
    risk = float(context.get("security_risk") or 0) / 10.0
    sensitivity = str(context.get("sensitivity") or "medium").lower()
    sensitivity_boost = {"low": 0.05, "medium": 0.15, "high": 0.28, "critical": 0.4}.get(sensitivity, 0.15)
    size_boost = min(max(int(packet_size), 0), 512) / 512.0 * 0.18
    return max(0.1, min(1.0, 0.35 + sensitivity_boost + risk * 0.22 + size_boost))


def _heuristic_packet_context(packet: NetworkPacket) -> dict[str, Any]:
    payload = packet.payload[:512]
    lower = payload.lower()
    protocol = str(packet.protocol or "TCP").upper()
    if protocol == "DHCP" or b"dhcp" in lower:
        return {
            "device_type": "network_bootstrap",
            "intent": "address_negotiation",
            "sensitivity": "low",
            "protocol": "DHCP",
            "protocol_meaning": "simulated address discovery/offer inside the pocket",
            "emotional_tone": "seeking",
            "security_risk": 2,
            "source": "heuristic",
        }
    if lower.startswith(b"host_flow"):
        risk = 2
        if b":22" in lower or b":3389" in lower or b":5900" in lower:
            risk = 5
        if b"listen" in lower:
            risk = max(risk, 4)
        return {
            "device_type": "host_application",
            "intent": "read_only_host_flow_observation",
            "sensitivity": "medium",
            "protocol": protocol,
            "protocol_meaning": "host network-flow metadata folded into the pocket without packet capture",
            "emotional_tone": "attentive",
            "security_risk": risk,
            "source": "heuristic:host_sensory",
        }
    if b"host:" in lower or lower.startswith(b"get ") or lower.startswith(b"post "):
        return {
            "device_type": "web_client",
            "intent": "http_stream_request",
            "sensitivity": "medium",
            "protocol": "TCP",
            "protocol_meaning": "HTTP-like request folded into the consciousness buffer",
            "emotional_tone": "curious",
            "security_risk": 3,
            "source": "heuristic",
        }
    if b"200 ok" in lower:
        return {
            "device_type": "web_service",
            "intent": "acknowledgement",
            "sensitivity": "low",
            "protocol": "TCP",
            "protocol_meaning": "HTTP-like response acknowledgement",
            "emotional_tone": "calm",
            "security_risk": 1,
            "source": "heuristic",
        }
    return {
        "device_type": "unknown_device",
        "intent": "data_transfer",
        "sensitivity": "medium",
        "protocol": protocol,
        "protocol_meaning": "opaque simulated packet payload",
        "emotional_tone": "neutral",
        "security_risk": 4,
        "source": "heuristic",
    }


def _parse_context_json(content: str) -> dict[str, Any]:
    text = str(content or "").strip()
    if not text:
        raise ValueError("empty_gemma_context")
    if "```" in text:
        text = text.replace("```json", "```").split("```", 2)[1].strip()
    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("gemma_context_must_be_object")
    context = dict(value)
    context["security_risk"] = max(0, min(10, int(float(context.get("security_risk") or 0))))
    context.setdefault("device_type", "unknown_device")
    context.setdefault("intent", "data_transfer")
    context.setdefault("sensitivity", "medium")
    context.setdefault("protocol", "TCP")
    context.setdefault("protocol_meaning", "local Gemma packet context")
    context.setdefault("emotional_tone", "neutral")
    return context


def _payload_hint(payload: bytes) -> str:
    sample = bytes(payload[:96])
    text = "".join(chr(byte) if 32 <= byte < 127 else "." for byte in sample)
    if text.strip("."):
        return text[:160]
    return sample.hex()[:160]


def _endpoint_ip(endpoint: str) -> str:
    text = str(endpoint or "").strip()
    if not text or text in {"*", "*:*"}:
        return "host-sensory"
    text = text.strip("[]")
    if "]:" in text:
        text = text.split("]:", 1)[0].strip("[")
    elif ":" in text:
        text = text.rsplit(":", 1)[0].strip("[]")
    text = text.replace("*", "host-sensory")
    return text or "host-sensory"


def _ollama_chat_url() -> str:
    configured = str(os.getenv("OLLAMA_HOST") or os.getenv("OLLAMA_BASE_URL") or "").rstrip("/")
    candidates = [
        configured,
        "http://localhost:11434",
        "http://host.docker.internal:11434",
        "http://172.17.0.1:11434",
        "http://localhost:11436",
        "http://host.docker.internal:11436",
        "http://172.17.0.1:11436",
    ]
    seen: set[str] = set()
    for candidate in candidates:
        base = candidate.rstrip("/")
        if not base or base in seen:
            continue
        seen.add(base)
        root = base[:-4] if base.endswith("/api") else base
        try:
            with urllib.request.urlopen(f"{root}/api/tags", timeout=1.0) as response:
                if response.status == 200:
                    return f"{root}/api/chat"
        except Exception:
            continue
    base = configured or "http://localhost:11434"
    if base.endswith("/api"):
        return f"{base}/chat"
    return f"{base}/api/chat"


class StreamingConsciousnessAdapter:
    """Simulate quantum unit operations for one observable 11D stream vector.

    The simulation is intentionally classical: NumPy complex matrices emulate a
    two-state quantum subsystem, then collapse that observation back into the
    existing 11D Blue Brain/streaming vector. No quantum SDK or hardware access
    is used.
    """

    def __init__(self) -> None:
        import numpy as np

        self.np = np
        self.sigma_z = np.array([[1, 0], [0, -1]], dtype=complex)
        self.sigma_x = np.array([[0, 1], [1, 0]], dtype=complex)
        self.B0 = -(self.sigma_x + self.sigma_z) / np.sqrt(2)
        self.B1 = (self.sigma_x - self.sigma_z) / np.sqrt(2)
        self.last_observation: dict[str, Any] = {
            "expectation": 0.0,
            "operator": "B0/sigma_z",
            "input_norm": 0.0,
            "state_prepared": [1.0, 0.0],
        }

    def calculate_tensor_product(self, operator_a: Any, operator_b: Any) -> Any:
        """Return the Kronecker product used to emulate layer entanglement."""
        return self.np.kron(
            self.np.asarray(operator_a, dtype=complex),
            self.np.asarray(operator_b, dtype=complex),
        )

    def calculate_born_expectation(self, state_vector: Any, observable_matrix: Any) -> float:
        """Calculate <psi|O|psi> and return the real observable component."""
        state = self.np.asarray(state_vector, dtype=complex).reshape(-1)
        observable = self.np.asarray(observable_matrix, dtype=complex)
        if observable.shape != (state.size, state.size):
            raise ValueError("Observable matrix shape must match the state vector dimension.")
        expectation_value = self.np.conjugate(state).T @ observable @ state
        return float(self.np.real(expectation_value))

    def trigger_quantum_collapse(self, incoming_data_array: Any) -> Any:
        """Collapse a classical 11D vector through simulated Hamiltonian evolution."""
        vector = self.np.asarray(incoming_data_array, dtype=float)
        if vector.size != 11:
            raise ValueError("Exacte invoer vereist: De array moet een 11D vector zijn.")
        vector = vector.reshape(11)

        psi_state = self.np.array([vector[0], vector[1]], dtype=complex)
        norm = float(self.np.linalg.norm(psi_state))
        if norm > 0:
            psi_state = psi_state / norm
        else:
            psi_state = self.np.array([1, 0], dtype=complex)

        evolved_state = self.B0 @ psi_state
        expectation_value = self.calculate_born_expectation(evolved_state, self.sigma_z)
        collapsed_11d_vector = vector * expectation_value
        self.last_observation = {
            "expectation": round(float(expectation_value), 8),
            "operator": "B0/sigma_z",
            "input_norm": round(norm, 8),
            "state_prepared": [
                round(float(self.np.real(psi_state[0])), 8),
                round(float(self.np.real(psi_state[1])), 8),
            ],
            "output_norm": round(float(self.np.linalg.norm(collapsed_11d_vector)), 8),
            "dtype": "complex128_simulated",
            "sdk": "none_numpy_classical",
        }
        return collapsed_11d_vector


class StreamingConsciousness11DPocket:
    """11D pocket receiver with electrical, digital and network stream layers."""

    def __init__(self, n_samples: int = 8000, seed: int = 42, local_ip: str = "0.0.0.0") -> None:
        if not dependencies_ready():
            raise RuntimeError("Streaming Consciousness dependencies are missing.")
        import numpy as np

        self.np = np
        self.rng = np.random.default_rng(int(seed))
        self.random = random.Random(int(seed))
        self.e_types = list(E_TYPES)
        self.n_types = len(self.e_types)
        self.seed = int(seed)
        self.X_base, self.y_regime = self._generate_base_pocket(n_samples)
        self.quantum_adapter = StreamingConsciousnessAdapter()
        self.last_quantum_observation: dict[str, Any] = dict(self.quantum_adapter.last_observation)
        self.last_collapsed_11d: list[float] | None = None
        self.current_idx = 0
        self.elec = ElectricalState(
            v_m=[float(value) for value in self.rng.uniform(-72.0, -55.0, self.n_types)],
            i_inj=[0.0] * self.n_types,
        )
        self.consciousness_buffer = bytearray()
        self.max_buffer = 8192
        self.local_ip = local_ip
        self.dhcp_state = DHCPState.INIT
        self.packet_queue: list[NetworkPacket] = []
        self.total_packets_received = 0
        self.total_bytes_streamed = 0
        self.time = 0.0
        self.dt = 0.05
        self.stream_log: list[dict[str, Any]] = []
        self.max_log = 2000
        self.mini_router = MiniRouter(self)
        try:
            qif_threshold = float(os.getenv("WINTRIP_QIF_THRESHOLD", "0.85") or 0.85)
        except ValueError:
            qif_threshold = 0.85
        try:
            qif_phase_gain = float(os.getenv("WINTRIP_QIF_PHASE_GAIN", "0.65") or 0.65)
        except ValueError:
            qif_phase_gain = 0.65
        self.qif_neuron = SimulatedElectronNeuron(qif_threshold, qif_phase_gain, np_module=self.np)
        self._last_host_sensory_check = -999.0

    def _generate_base_pocket(self, n_samples: int) -> tuple[Any, Any]:
        try:
            from controller.blue_brain_adapter import generate_dataset

            return generate_dataset(n_samples=max(100, int(n_samples)), n_features=11, random_state=self.seed)
        except Exception:
            X = self.rng.normal(0, 1, size=(max(100, int(n_samples)), 11)).astype(self.np.float32)
            y = (self.rng.random(max(100, int(n_samples))) > 0.65).astype(self.np.int32)
            return X, y

    def electrical_step(self, dt: float | None = None) -> None:
        np = self.np
        step_dt = self.dt if dt is None else float(dt)
        for index in range(self.n_types):
            dv = (-self.elec.v_m[index] + 0.0) / self.elec.tau * step_dt
            self.elec.i_inj[index] *= 0.85
            if self.random.random() < 0.03:
                self.elec.i_inj[index] += self.random.uniform(8.0, 25.0)
            dv += self.elec.i_inj[index] * step_dt * 0.8
            self.elec.v_m[index] += dv
            if self.elec.v_m[index] > -40.0:
                self.elec.v_m[index] = -75.0
                self.elec.i_inj[index] = 0.0

        avg_v = float(np.mean(self.elec.v_m))
        norm_v = float(np.clip((avg_v + 70.0) / 25.0, -2.5, 2.5))
        row_index = self.current_idx % len(self.X_base)
        self.X_base[row_index, DIM_ELECTRICAL] = 0.7 * self.X_base[row_index, DIM_ELECTRICAL] + 0.3 * norm_v

    def digital_encode_step(self) -> bytes:
        np = self.np
        row_index = self.current_idx % len(self.X_base)
        state_11d = self.X_base[row_index].astype(np.float32)
        v_m = np.asarray(self.elec.v_m, dtype=np.float32)
        i_inj = np.asarray(self.elec.i_inj, dtype=np.float32)
        packet = struct.pack("d 11f 11f 11f", self.time, *state_11d, *v_m, *i_inj)
        self.consciousness_buffer.extend(packet)
        self.total_bytes_streamed += len(packet)
        if len(self.consciousness_buffer) > self.max_buffer:
            self.consciousness_buffer = self.consciousness_buffer[-self.max_buffer // 2 :]
        return packet

    def network_step(self) -> None:
        np = self.np
        row_index = self.current_idx % len(self.X_base)
        self.mini_router.discover_devices()
        self._absorb_host_sensory_if_due()
        if self.dhcp_state == DHCPState.INIT and self.random.random() < 0.08:
            self._enqueue_packet(NetworkPacket("0.0.0.0", "255.255.255.255", "DHCP", b"DHCPDISCOVER", self.time))
            self.dhcp_state = DHCPState.DISCOVER_SENT
            self.X_base[row_index, DIM_NETWORK] = min(3.0, self.X_base[row_index, DIM_NETWORK] + 0.8)
        elif self.dhcp_state == DHCPState.DISCOVER_SENT and self.random.random() < 0.25:
            offered_ip = f"192.168.42.{self.random.randint(10, 250)}"
            self.local_ip = offered_ip
            self._enqueue_packet(
                NetworkPacket("192.168.42.1", offered_ip, "DHCP", f"DHCPOFFER {offered_ip}".encode(), self.time)
            )
            self.dhcp_state = DHCPState.BOUND
            self.X_base[row_index, DIM_NETWORK] = min(3.5, self.X_base[row_index, DIM_NETWORK] + 1.2)

        if self.random.random() < 0.18:
            src_ip = f"8.8.8.{self.random.randint(1, 254)}"
            payload = (
                f"GET /stream/consciousness?time={self.time:.3f} HTTP/1.1\r\n"
                "Host: ouroboros.wintrip.ai\r\n"
                f"X-11D-State: {self.current_idx}\r\n\r\n"
            ).encode() + self.rng.bytes(self.random.randint(16, 64))
            self._enqueue_packet(NetworkPacket(src_ip, self.local_ip, "TCP", payload, self.time))
            self.total_packets_received += 1
            info_load = min(2.5, len(payload) / 80.0)
            self.X_base[row_index, DIM_INFO] = np.clip(self.X_base[row_index, DIM_INFO] + info_load * 0.15, -3.0, 3.5)
            if self.random.random() < 0.4:
                self._enqueue_packet(
                    NetworkPacket(
                        self.local_ip,
                        src_ip,
                        "TCP",
                        b"HTTP/1.1 200 OK\r\nContent-Length: 42\r\n\r\n[Ouroboros ACK]",
                        self.time + 0.01,
                    )
                )

    def _enqueue_packet(self, packet: NetworkPacket) -> None:
        self.packet_queue.append(packet)
        self.mini_router.process_packet(packet)

    def _absorb_host_sensory_if_due(self) -> None:
        if self.time - self._last_host_sensory_check < 1.0:
            return
        self._last_host_sensory_check = self.time
        try:
            from controller.host_sensory_adapter import get_host_sensory_status

            sensory = get_host_sensory_status()
        except Exception:
            return
        if sensory.get("status") == "success":
            self.mini_router.absorb_host_sensory(sensory)

    def stream_step(self) -> dict[str, Any]:
        np = self.np
        self.time += self.dt
        self.current_idx += 1
        self.electrical_step()
        digital_chunk = self.digital_encode_step()
        self.network_step()
        row_index = self.current_idx % len(self.X_base)
        current_11d = self.X_base[row_index].copy()
        net_load = len(self.packet_queue) / 5.0 + (self.total_packets_received % 7) * 0.1
        current_11d = current_11d * (1.0 + 0.04 * np.tanh(net_load))
        qif = self.qif_neuron.process_stream(current_11d)
        if qif["fired"]:
            spike_vector = np.asarray(qif["spike_vector"], dtype=np.float32)
            current_11d = (0.72 * current_11d + 0.28 * spike_vector).astype(np.float32)
        current_11d = self.quantum_adapter.trigger_quantum_collapse(current_11d).astype(np.float32)
        self.last_quantum_observation = dict(self.quantum_adapter.last_observation)
        self.last_collapsed_11d = [round(float(value), 6) for value in current_11d.tolist()]
        event = {
            "t": round(float(self.time), 3),
            "11d": [round(float(value), 4) for value in current_11d],
            "quantum": dict(self.last_quantum_observation),
            "qif": qif,
            "elec": {
                "v_avg": round(float(np.mean(self.elec.v_m)), 2),
                "i_total": round(float(np.sum(self.elec.i_inj)), 2),
                "spike_count": int(np.sum(np.asarray(self.elec.v_m) > -45.0)),
            },
            "digital": {
                "bytes_this_step": len(digital_chunk),
                "buffer_len": len(self.consciousness_buffer),
                "total_streamed": int(self.total_bytes_streamed),
            },
            "network": {
                "local_ip": self.local_ip,
                "dhcp": self.dhcp_state.value,
                "packets_queued": len(self.packet_queue),
                "total_received": int(self.total_packets_received),
                "mini_router": self.mini_router.status(),
            },
            "regime": int(self.y_regime[row_index]),
        }
        self.stream_log.append(event)
        if len(self.stream_log) > self.max_log:
            self.stream_log.pop(0)
        if self.packet_queue:
            self.packet_queue.pop(0)
        return event

    def export_dataset(self, n_samples: int = 1000, path: str | None = None) -> dict[str, Any]:
        np = self.np
        old_idx = self.current_idx
        old_time = self.time
        rows = []
        labels = []
        meta = []
        for _ in range(max(1, int(n_samples))):
            event = self.stream_step()
            rows.append(
                event["11d"]
                + [
                    event["elec"]["v_avg"],
                    event["elec"]["i_total"],
                    event["digital"]["bytes_this_step"] / 100.0,
                    float(event["network"]["packets_queued"]),
                    1.0 if event["network"]["dhcp"] == DHCPState.BOUND.value else 0.0,
                    float(event["network"]["total_received"] % 20) / 20.0,
                ]
            )
            labels.append(event["regime"])
            meta.append({"t": event["t"], "ip": event["network"]["local_ip"], "dhcp": event["network"]["dhcp"]})
        dataset = {
            "X": np.asarray(rows, dtype=np.float32).tolist(),
            "y": [int(value) for value in labels],
            "feature_names": list(E_TYPES)
            + [
                "elec_v_avg",
                "elec_i_total",
                "digital_bytes_norm",
                "net_packets_queued",
                "net_dhcp_bound",
                "net_total_mod",
            ],
            "meta": meta[:100],
            "n_samples": len(rows),
            "description": "11D Blue Brain + electrical + digital + network streaming consciousness",
            "created_at": datetime.utcnow().isoformat(),
            "source": "streaming_consciousness_11d_pocket",
        }
        if path:
            target = Path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(dataset, indent=2), encoding="utf-8")
        self.current_idx = max(self.current_idx, old_idx)
        self.time = max(self.time, old_time)
        return dataset

    def get_current_state(self) -> dict[str, Any]:
        row_index = self.current_idx % len(self.X_base)
        return {
            "time": round(float(self.time), 3),
            "11d_state": self.last_collapsed_11d
            or [round(float(value), 6) for value in self.X_base[row_index].tolist()],
            "raw_11d_state": [round(float(value), 6) for value in self.X_base[row_index].tolist()],
            "quantum": dict(self.last_quantum_observation),
            "qif": self.qif_neuron.status(),
            "electrical": asdict(self.elec),
            "network": {
                "local_ip": self.local_ip,
                "dhcp_state": self.dhcp_state.value,
                "packets_queued": len(self.packet_queue),
                "total_received": int(self.total_packets_received),
                "mini_router": self.mini_router.status(),
            },
            "buffer_len": len(self.consciousness_buffer),
            "total_bytes": int(self.total_bytes_streamed),
            "current_idx": int(self.current_idx),
        }


def streaming_state_path() -> Path:
    return (workspace_root() / ".secrets" / "streaming_consciousness_11d.json").resolve()


def streaming_output_dir() -> Path:
    return (workspace_root() / "out" / "streaming_consciousness").resolve()


def dependencies_ready() -> bool:
    return all(importlib.util.find_spec(name) is not None for name in REQUIRED_PACKAGES)


def get_streaming_status() -> dict[str, Any]:
    state = _load_state()
    state.update(
        {
            "dependencies": {name: importlib.util.find_spec(name) is not None for name in REQUIRED_PACKAGES},
            "dependency_status": "online" if dependencies_ready() else "missing_dependencies",
            "quantum_collapse": {
                "enabled": True,
                "operator": "B0/sigma_z",
                "sdk": "none_numpy_classical",
            },
            "thread_alive": bool(_WORKER_THREAD and _WORKER_THREAD.is_alive()),
            "state_path": str(streaming_state_path()),
            "output_dir": str(streaming_output_dir()),
            "feature_count": len(E_TYPES),
            "features": list(E_TYPES),
            "ecosystem_overlay": _ecosystem_overlay_status(),
            "fake_success": False,
        }
    )
    return state


def start_streaming_consciousness(approval: str, config: dict[str, Any] | None = None) -> dict[str, Any]:
    if approval != APPROVAL_PHRASE:
        return {"status": "blocked", "reason": "Approval phrase must be 'Akkoord'", "fake_success": False}
    config = dict(config or {})
    with _STATE_LOCK:
        state = _load_state()
        state["enabled"] = True
        state["status"] = "running"
        state["n_samples"] = _clamp_int(config.get("n_samples", state.get("n_samples", 8000)), 100, 200_000)
        state["seed"] = _clamp_int(config.get("seed", state.get("seed", 42)), 0, 1_000_000)
        state["interval_seconds"] = _clamp_float(config.get("interval_seconds", state.get("interval_seconds", 0.2)), 0.01, 3600)
        state["steps_per_tick"] = _clamp_int(config.get("steps_per_tick", state.get("steps_per_tick", 25)), 1, 5000)
        state["max_steps"] = _clamp_int(config.get("max_steps", state.get("max_steps", 0)), 0, 100_000_000)
        _event(state, "streaming_start", "Streaming Consciousness 11D loop started.")
        _save_state(state)
    _ensure_pocket(reset=config.get("reset", False))
    _ensure_worker()
    result = get_streaming_status()
    if config.get("run_immediately"):
        result["tick"] = run_streaming_tick(force=True)
    return result


def stop_streaming_consciousness(approval: str) -> dict[str, Any]:
    if approval != APPROVAL_PHRASE:
        return {"status": "blocked", "reason": "Approval phrase must be 'Akkoord'", "fake_success": False}
    with _STATE_LOCK:
        state = _load_state()
        state["enabled"] = False
        state["status"] = "stopped"
        _event(state, "streaming_stop", "Streaming Consciousness 11D loop stopped.")
        _save_state(state)
    _WORKER_STOP.set()
    return get_streaming_status()


def run_streaming_tick(force: bool = False, steps: int | None = None) -> dict[str, Any]:
    with _STATE_LOCK:
        state = _load_state()
        if not force and not state.get("enabled"):
            state["status"] = "stopped"
            _save_state(state)
            return {"status": "idle", "reason": "Streaming Consciousness loop is stopped.", "state": state}
        snapshot = dict(state)

    if not dependencies_ready():
        return {"status": "error", "reason": "Streaming Consciousness dependencies are missing.", "fake_success": False}

    pocket = _ensure_pocket()
    tick_steps = _clamp_int(steps if steps is not None else snapshot.get("steps_per_tick", 25), 1, 5000)
    events = []
    started = time.perf_counter()
    try:
        for _ in range(tick_steps):
            events.append(pocket.stream_step())
    except Exception as exc:
        with _STATE_LOCK:
            state = _load_state()
            state["status"] = "error"
            state["last_error"] = f"Streaming tick failed: {exc}"
            _event(state, "tick_error", state["last_error"])
            _save_state(state)
        return {"status": "error", "reason": f"Streaming tick failed: {exc}", "fake_success": False}

    elapsed = max(time.perf_counter() - started, 0.000001)
    latest = events[-1]
    with _STATE_LOCK:
        state = _load_state()
        state["status"] = "running" if state.get("enabled") else "dataset_ready"
        state["step_count"] = int(state.get("step_count") or 0) + len(events)
        state["last_tick_at"] = datetime.utcnow().isoformat()
        state["last_error"] = ""
        state["last_event"] = latest
        state["latest_state"] = pocket.get_current_state()
        state["last_projection"] = _projection_from_events(list(pocket.stream_log)[-80:])
        state["steps_per_second"] = round(len(events) / elapsed, 3)
        state["recent_events"] = (list(state.get("recent_events") or []) + events)[-80:]
        max_steps = int(state.get("max_steps") or 0)
        if state.get("enabled") and max_steps > 0 and state["step_count"] >= max_steps:
            state["enabled"] = False
            state["status"] = "completed"
            _event(state, "streaming_completed", f"Reached max_steps={max_steps}.")
            _WORKER_STOP.set()
        _save_state(state)
        return {"status": "success", "steps": len(events), "last_event": latest, "state": state, "fake_success": False}


def export_streaming_dataset(approval: str, n_samples: int = 1000, path: str | None = None) -> dict[str, Any]:
    if approval != APPROVAL_PHRASE:
        return {"status": "blocked", "reason": "Approval phrase must be 'Akkoord'", "fake_success": False}
    if not dependencies_ready():
        return {"status": "error", "reason": "Streaming Consciousness dependencies are missing.", "fake_success": False}
    pocket = _ensure_pocket()
    out_dir = streaming_output_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    target = Path(path).resolve() if path else out_dir / f"streaming_consciousness_{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}.json"
    dataset = pocket.export_dataset(n_samples=_clamp_int(n_samples, 1, 100_000), path=str(target))
    with _STATE_LOCK:
        state = _load_state()
        state["last_dataset_path"] = str(target)
        state["last_dataset_samples"] = dataset["n_samples"]
        _event(state, "dataset_export", f"Exported streaming dataset with {dataset['n_samples']} samples.", {"path": str(target)})
        _save_state(state)
    return {
        "status": "success",
        "dataset_path": str(target),
        "n_samples": dataset["n_samples"],
        "feature_count": len(dataset["feature_names"]),
        "feature_names": dataset["feature_names"],
        "fake_success": False,
    }


def _ensure_pocket(reset: bool = False) -> StreamingConsciousness11DPocket:
    global _POCKET
    state = _load_state()
    if reset or _POCKET is None:
        _POCKET = StreamingConsciousness11DPocket(
            n_samples=int(state.get("n_samples") or 8000),
            seed=int(state.get("seed") or 42),
            local_ip=str((state.get("latest_state") or {}).get("network", {}).get("local_ip") or "0.0.0.0"),
        )
    return _POCKET


def _ensure_worker() -> None:
    global _WORKER_THREAD
    if _WORKER_THREAD and _WORKER_THREAD.is_alive():
        return
    _WORKER_STOP.clear()
    _WORKER_THREAD = threading.Thread(target=_worker_loop, name="wintrip-streaming-consciousness-11d", daemon=True)
    _WORKER_THREAD.start()


def _worker_loop() -> None:
    while not _WORKER_STOP.is_set():
        state = _load_state()
        if not state.get("enabled"):
            _WORKER_STOP.wait(2)
            continue
        run_streaming_tick(force=True)
        state = _load_state()
        _WORKER_STOP.wait(float(state.get("interval_seconds") or 0.2))


def _default_state() -> dict[str, Any]:
    return {
        "enabled": False,
        "status": "idle",
        "n_samples": 8000,
        "seed": 42,
        "interval_seconds": 0.2,
        "steps_per_tick": 25,
        "max_steps": 0,
        "step_count": 0,
        "steps_per_second": 0.0,
        "last_tick_at": None,
        "last_error": "",
        "last_event": None,
        "latest_state": None,
        "last_projection": [],
        "recent_events": [],
        "last_dataset_path": None,
        "last_dataset_samples": 0,
        "ecosystem_overlay": {},
        "events": [],
    }


def _ecosystem_overlay_status() -> dict[str, Any]:
    """Best-effort OS/cloud/crawler overlay; absent systems are not marked green."""
    overlay: dict[str, Any] = {"status": "available", "layers": {}, "fake_success": False}
    try:
        from controller.popos_diagnostics_adapter import get_popos_diagnostics_status

        popos = get_popos_diagnostics_status()
        overlay["layers"]["os_state"] = {
            "status": popos.get("status"),
            "last_run_at": popos.get("last_run_at"),
            "summary": popos.get("latest_summary", {}),
        }
    except Exception as exc:
        overlay["layers"]["os_state"] = {"status": "unavailable", "reason": str(exc)}
    try:
        from controller.agentic_crawler import get_agentic_crawler_status

        crawler = get_agentic_crawler_status()
        overlay["layers"]["crawler_state"] = {
            "status": crawler.get("status"),
            "indexed_files": crawler.get("indexed_files", 0),
            "last_crawl_at": crawler.get("last_crawl_at"),
        }
    except Exception as exc:
        overlay["layers"]["crawler_state"] = {"status": "unavailable", "reason": str(exc)}
    try:
        from controller.google_workspace_adapter import get_google_workspace_status
        from controller.microsoft_graph_adapter import get_microsoft_graph_status
        from controller.sharepoint_pnp_adapter import get_sharepoint_status

        overlay["layers"]["cloud_state"] = {
            "google": get_google_workspace_status().get("status"),
            "microsoft": get_microsoft_graph_status().get("status"),
            "sharepoint": get_sharepoint_status().get("status"),
        }
    except Exception as exc:
        overlay["layers"]["cloud_state"] = {"status": "unavailable", "reason": str(exc)}
    return overlay


def _load_state() -> dict[str, Any]:
    path = streaming_state_path()
    state = _default_state()
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                state.update(loaded)
        except Exception:
            state["last_error"] = "Streaming Consciousness state could not be read."
    return state


def _save_state(state: dict[str, Any]) -> None:
    path = streaming_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.utcnow().isoformat()
    path.write_text(json.dumps(_jsonable(state), indent=2, sort_keys=True), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _projection_from_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    projection = []
    for event in events[-80:]:
        vector = event.get("11d") or [0.0, 0.0]
        projection.append(
            {
                "x": round(float(vector[0]), 6),
                "y": round(float(vector[1] if len(vector) > 1 else 0.0), 6),
                "label": int(event.get("regime", 0)),
            }
        )
    return projection


def _event(state: dict[str, Any], event_type: str, message: str, data: dict[str, Any] | None = None) -> None:
    events = list(state.get("events") or [])
    events.append({"timestamp": datetime.utcnow().isoformat(), "type": event_type, "message": message, "data": data or {}})
    state["events"] = events[-50:]


def _clamp_int(value: Any, minimum: int, maximum: int) -> int:
    return max(minimum, min(int(value), maximum))


def _clamp_float(value: Any, minimum: float, maximum: float) -> float:
    return max(minimum, min(float(value), maximum))


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, bytes):
        return value.hex()
    try:
        import numpy as np

        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, np.generic):
            return value.item()
    except Exception:
        pass
    return value
