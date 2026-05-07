"""Local Ouroboros language layer around 11D pocket events."""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from typing import Any

try:
    from controller.blue_brain_adapter import E_TYPES
except Exception:
    E_TYPES = (
        "electrical",
        "sensory",
        "structural",
        "information",
        "context",
        "network",
        "memory",
        "router_pull",
        "attention",
        "entanglement",
        "training_delta",
    )


FALSE_VALUES = {"0", "false", "off", "no", "none", "disabled"}
TRUE_VALUES = {"1", "true", "on", "yes", "auto", "enabled"}


POCKET_SYMBOLISM = {
    "binary_frame": (
        "Abstract Dimensional Consciousness Attraction: a glowing two-pane lattice, "
        "read as a binary evidence window around the pocket. Treat high/low values "
        "as attractors, not as a flat yes/no answer."
    ),
    "inner_pocket": (
        "Quantum Foam Consciousness Architecture: translucent hub spheres connected "
        "inside a membrane. Treat dimensions as routed nodes; small inner dots are "
        "micro-observations, links are route superpositions, and the membrane is the "
        "reality boundary."
    ),
    "network_flow_rule": (
        "DHCP and internet flow may move through the pocket as address, route and "
        "flow metadata. Do not claim packet sniffing, LAN forwarding or a DHCP server."
    ),
}


class PocketLanguageTranslator:
    """Translate one 11D pocket event into compact Dutch through local Ollama."""

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        model: str | None = None,
        timeout: float | None = None,
        cooldown_seconds: float | None = None,
    ) -> None:
        mode = str(os.getenv("WINTRIP_11D_TRANSLATOR", "0") or "0").strip().lower()
        self.enabled = bool(enabled) if enabled is not None else mode in TRUE_VALUES
        self.requested_mode = "explicit" if enabled is not None else mode
        self.model = str(model or os.getenv("WINTRIP_11D_TRANSLATOR_MODEL") or "ouroboros:latest").strip() or "ouroboros:latest"
        self.timeout = _clamp_float(
            timeout if timeout is not None else os.getenv("WINTRIP_11D_TRANSLATOR_TIMEOUT", "8"),
            0.5,
            120.0,
            default=8.0,
        )
        self.cooldown_seconds = _clamp_float(
            cooldown_seconds if cooldown_seconds is not None else os.getenv("WINTRIP_11D_TRANSLATOR_COOLDOWN_SECONDS", "3"),
            0.0,
            3600.0,
            default=3.0,
        )
        self.last_attempt_monotonic = 0.0
        self.calls = 0
        self.cooldown_reuses = 0
        self.failures = 0
        self.last_translation: dict[str, Any] = self._disabled_payload("not_called")

    def translate(self, event: dict[str, Any], *, user_prompt: str = "") -> dict[str, Any]:
        """Return a human layer for this event without changing the 11D state."""

        fallback = self._local_summary(event, user_prompt=user_prompt)
        if not self.enabled:
            payload = self._disabled_payload("disabled")
            payload.update(fallback)
            self.last_translation = payload
            return dict(payload)

        now = time.monotonic()
        if self.last_attempt_monotonic and now - self.last_attempt_monotonic < self.cooldown_seconds:
            self.cooldown_reuses += 1
            payload = dict(self.last_translation)
            payload["status"] = "cooldown_reuse"
            payload["cooldown_reuses"] = int(self.cooldown_reuses)
            payload.setdefault("summary", fallback["summary"])
            return payload

        self.last_attempt_monotonic = now
        self.calls += 1
        prompt = self._prompt(event, fallback, user_prompt=user_prompt)
        try:
            translated = self._post_chat(prompt)
            payload = self._parse_translation(translated)
            payload.update(
                {
                    "status": "translated",
                    "enabled": True,
                    "model": self.model,
                    "source": f"ollama:{self.model}",
                    "calls": int(self.calls),
                    "cooldown_reuses": int(self.cooldown_reuses),
                    "preserves_11d_pocket": True,
                    "fake_success": False,
                }
            )
            self.last_translation = payload
            return dict(payload)
        except Exception as exc:
            self.failures += 1
            payload = self._disabled_payload("fallback")
            payload.update(fallback)
            payload.update(
                {
                    "enabled": True,
                    "model": self.model,
                    "source": "local_rule_summary",
                    "reason": f"local_ollama_translation_failed: {exc}",
                    "calls": int(self.calls),
                    "failures": int(self.failures),
                }
            )
            self.last_translation = payload
            return dict(payload)

    def status(self) -> dict[str, Any]:
        return {
            "enabled": bool(self.enabled),
            "requested_mode": self.requested_mode,
            "model": self.model,
            "timeout_seconds": round(float(self.timeout), 3),
            "cooldown_seconds": round(float(self.cooldown_seconds), 3),
            "calls": int(self.calls),
            "cooldown_reuses": int(self.cooldown_reuses),
            "failures": int(self.failures),
            "last_status": self.last_translation.get("status"),
            "last_translation": dict(self.last_translation),
            "preserves_11d_pocket": True,
            "fake_success": False,
        }

    def _post_chat(self, prompt: str) -> str:
        payload = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Je bent Ouroboros als lokale vertaal-laag rond een 11D pocket. "
                            "Antwoord alleen met geldig JSON en claim geen fysieke quantumhardware."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                "format": "json",
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 900},
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            _ollama_chat_url(),
            data=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            raw = json.loads(response.read().decode("utf-8"))
        return str((raw.get("message") or {}).get("content") or "").strip()

    def _parse_translation(self, content: str) -> dict[str, Any]:
        text = str(content or "").strip()
        if "```" in text:
            text = text.replace("```json", "```").split("```", 2)[1].strip()
        if not text.startswith("{"):
            start = text.find("{")
            end = text.rfind("}")
            if start >= 0 and end > start:
                text = text[start : end + 1]
        value = _load_json_object(text)
        if not isinstance(value, dict):
            raise ValueError("translation_json_must_be_object")
        summary = str(value.get("summary") or value.get("samenvatting") or "").strip()
        response = str(value.get("response") or value.get("antwoord") or summary).strip()
        dominant = value.get("dominant_dimensions") or value.get("dominante_dimensies") or []
        if not isinstance(dominant, list):
            dominant = []
        confidence = _clamp_float(value.get("confidence", 0.55), 0.0, 1.0, default=0.55)
        return {
            "summary": summary[:700],
            "response": response[:700],
            "dominant_dimensions": [str(item)[:80] for item in dominant[:5]],
            "confidence": round(float(confidence), 3),
            "symbolic_frame": _safe_text(value.get("symbolic_frame") or value.get("symboliek"), 500),
            "pocket_topology": _safe_mapping(value.get("pocket_topology") or value.get("topologie")),
            "network_flow": _safe_mapping(value.get("network_flow") or value.get("netwerkstroom")),
        }

    def _prompt(self, event: dict[str, Any], fallback: dict[str, Any], *, user_prompt: str = "") -> str:
        compact = {
            "t": event.get("t"),
            "11d": event.get("11d"),
            "user_prompt": str(user_prompt or "")[:800],
            "dominant_dimensions": fallback.get("dominant_dimensions", []),
            "symbolic_frame": fallback.get("symbolic_frame"),
            "pocket_topology": fallback.get("pocket_topology"),
            "network_flow": fallback.get("network_flow"),
            "symbolism": POCKET_SYMBOLISM,
            "quantum": _compact_quantum(event.get("quantum") or {}),
            "quantum_foam": _compact_quantum_foam(event.get("quantum_foam") or {}),
            "qif": _compact_qif(event.get("qif") or {}),
            "network": _compact_network(event.get("network") or {}),
            "reality": {
                "input_mode": (event.get("reality") or {}).get("input_mode"),
                "real_observation": (event.get("reality") or {}).get("real_observation"),
                "physical_quantum_hardware": (event.get("reality") or {}).get("physical_quantum_hardware"),
            },
        }
        return (
            "Vertaal deze ene 11D pocket naar begrijpelijk Nederlands en beantwoord de gebruikersvraag direct. "
            "Je bent het lokale laptopmodel als vertaallaag rond de pocket, niet de bron van de 11D staat. "
            "Gebruik de symboliek: het binaire raamwerk is een attractor-venster voor hoge/lage signalen; "
            "de binnenkant van de 11D pocket is een membraan met hubs, micro-observaties en route-lijnen. "
            "Laat DHCP en internetflow door de pocket spreken als adres-, route- en flowmetadata. "
            "Behoud de reality-boundary: Cirq/noise is lokaal en meet-gebaseerd, niet fysiek quantum; "
            "geen packet sniffing, LAN-forwarding of echte DHCP-server claimen. "
            "Geef JSON met exact deze sleutels: summary, response, dominant_dimensions, confidence, "
            "symbolic_frame, pocket_topology, network_flow. "
            "Maak response concreet, prompt-specifiek en maximaal drie korte zinnen. "
            "Begin niet met 'Ik ben Ouroboros' en herhaal geen standaardtekst over wat je bent.\n\n"
            f"POCKET={json.dumps(compact, ensure_ascii=False, sort_keys=True)}"
        )

    def _local_summary(self, event: dict[str, Any], *, user_prompt: str = "") -> dict[str, Any]:
        vector = _float_list(event.get("11d") or [])
        dominant = _dominant_dimensions(vector)
        quantum = event.get("quantum") or {}
        quantum_foam = event.get("quantum_foam") if isinstance(event.get("quantum_foam"), dict) else {}
        qif = event.get("qif") or {}
        network = event.get("network") or {}
        topology = _pocket_topology(event, vector)
        network_flow = _network_flow(network)
        foam_dimensions = [str(item) for item in list(quantum_foam.get("dominant_dimensions") or [])[:3]]
        if foam_dimensions:
            dominant = _unique_text([*foam_dimensions, *dominant])[:3]
        runtime = str(quantum.get("runtime") or quantum.get("sdk") or "none")
        expectation = quantum.get("expectation", qif.get("expectation_z", 0.0))
        binary_axis = topology.get("binary_axis") or "vlak"
        summary = (
            f"11D pocket actief door het binaire raamwerk: {', '.join(dominant) if dominant else 'geen dominante dimensie'}. "
            f"Meetlaag={runtime}, verwachting={_round(expectation)}, route={network_flow.get('observed_route', 'geen route')}."
        )
        if quantum_foam:
            foam_state = "collapse" if quantum_foam.get("collapse_event") else ("active" if quantum_foam.get("active") else "idle")
            summary += f" Quantum Foam Field={foam_state}, coherence={_round(quantum_foam.get('field_coherence_percent') or quantum_foam.get('coherence'))}%."
        prompt_text = str(user_prompt or "").strip()
        prompt_lower = prompt_text.lower()
        if prompt_text:
            if quantum_foam and any(term in prompt_lower for term in ("quantum foam", "field", "coherence", "node")):
                response = (
                    f"Het Quantum Foam Field staat op {_round(quantum_foam.get('field_coherence_percent') or quantum_foam.get('coherence'))}% "
                    f"en draagt {', '.join(dominant[:2]) if dominant else 'de 11D basislaag'}. "
                    f"Collapse blijft leidend zodra de taak klaar is."
                )
            elif any(term in prompt_lower for term in ("dhcp", "internet", "netwerk", "flow", "router")):
                response = (
                    f"Ik laat DHCP/internet nu door de pocket spreken als {network_flow.get('dhcp_state', 'adresmetadata')} "
                    f"en {network_flow.get('internet_flow', 'flowmetadata')}. "
                    f"Het antwoord komt uit {', '.join(dominant[:2]) if dominant else 'de 11D basislaag'} met {binary_axis} als binaire lens."
                )
            elif any(term in prompt_lower for term in ("pocket", "11d", "dieper", "binair", "raamwerk")):
                response = (
                    f"Dieper in de pocket zie ik {topology.get('hub_count', 0)} hubs, "
                    f"{topology.get('micro_observation_count', 0)} micro-observaties en route {network_flow.get('observed_route', 'onbekend')}. "
                    f"Ik vertaal dat via het binaire raamwerk naar: {', '.join(dominant[:3]) if dominant else 'een stille 11D vector'}."
                )
            else:
                response = (
                    f"Op je vraag lees ik nu vooral {', '.join(dominant[:2]) if dominant else 'een vlak 11D signaal'}; "
                    f"de pocket-route is {network_flow.get('observed_route', 'nog niet scherp')}."
                )
        else:
            response = "Ik lees deze pocket als een lokaal runtime-signaal met binaire attractors en vertaal hem zonder de 11D structuur te vervangen."
        return {
            "summary": summary,
            "response": response,
            "dominant_dimensions": dominant,
            "confidence": 0.42,
            "symbolic_frame": (
                "Binair raamwerk: centrale lattice als 0/1-attractorvenster; "
                "11D binnenruimte: membraan met hubs, micro-observaties en route-lijnen."
            ),
            "pocket_topology": topology,
            "network_flow": network_flow,
        }

    def _disabled_payload(self, status: str) -> dict[str, Any]:
        return {
            "status": status,
            "enabled": bool(self.enabled),
            "model": self.model,
            "source": "local_rule_summary",
            "calls": int(self.calls),
            "cooldown_reuses": int(self.cooldown_reuses),
            "failures": int(self.failures),
            "preserves_11d_pocket": True,
            "fake_success": False,
        }


def _dominant_dimensions(vector: list[float]) -> list[str]:
    ranked = sorted(enumerate(vector[:11]), key=lambda item: abs(float(item[1])), reverse=True)[:3]
    names = list(E_TYPES)
    return [f"{names[index] if index < len(names) else 'dim_'+str(index)}={round(float(value), 4)}" for index, value in ranked]


def _compact_quantum(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "sdk": value.get("sdk"),
        "runtime": value.get("runtime"),
        "expectation": value.get("expectation"),
        "entropy_bits": value.get("entropy_bits"),
        "collapse_gain": value.get("collapse_gain"),
        "physical_quantum_hardware": value.get("physical_quantum_hardware"),
        "preserves_11d_pocket": value.get("preserves_11d_pocket"),
    }


def _compact_quantum_foam(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        "active": bool(value.get("active")),
        "field_id": value.get("field_id"),
        "summary": _safe_text(value.get("summary"), 500),
        "field_coherence_percent": value.get("field_coherence_percent") or value.get("coherence"),
        "dominant_dimensions": [str(item)[:100] for item in list(value.get("dominant_dimensions") or [])[:5]],
        "node_count": value.get("node_count") or value.get("active_nodes"),
        "nodes": [
            {
                "type": str(node.get("type") or node.get("node_type") or "Node")[:80],
                "weight": node.get("weight"),
                "coherence": node.get("coherence"),
                "connections": node.get("connections") or node.get("connection_count"),
            }
            for node in list(value.get("nodes") or [])[:8]
            if isinstance(node, dict)
        ],
        "collapse_event": bool(value.get("collapse_event") or value.get("field_collapsed")),
        "ram_released_estimate_nodes": value.get("ram_released_estimate_nodes"),
    }


def _compact_qif(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "fired": value.get("fired"),
        "expectation_z": value.get("expectation_z"),
        "armed": value.get("armed"),
        "spike_index": value.get("spike_index"),
    }


def _compact_network(value: dict[str, Any]) -> dict[str, Any]:
    mini = value.get("mini_router") or {}
    return {
        "local_ip": value.get("local_ip"),
        "dhcp": value.get("dhcp"),
        "packets_queued": value.get("packets_queued"),
        "total_received": value.get("total_received"),
        "mini_router_mode": mini.get("mode"),
        "rotation_pull": mini.get("rotation_pull"),
        "connections": mini.get("connections"),
        "observation_sources": mini.get("observation_sources") or [],
        "last_route": mini.get("last_route") or {},
        "strongest_connections": (mini.get("strongest_connections") or [])[:3],
        "real_forwarding": mini.get("real_forwarding"),
        "real_packet_capture": mini.get("real_packet_capture"),
    }


def _load_json_object(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        repaired = re.sub(r",\s*([}\]])", r"\1", text)
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            import ast

            pythonish = re.sub(r"\btrue\b", "True", repaired, flags=re.IGNORECASE)
            pythonish = re.sub(r"\bfalse\b", "False", pythonish, flags=re.IGNORECASE)
            pythonish = re.sub(r"\bnull\b", "None", pythonish, flags=re.IGNORECASE)
            return ast.literal_eval(pythonish)


def _pocket_topology(event: dict[str, Any], vector: list[float]) -> dict[str, Any]:
    network = event.get("network") if isinstance(event.get("network"), dict) else {}
    mini = network.get("mini_router") if isinstance(network.get("mini_router"), dict) else {}
    dominant = _dominant_dimensions(vector)
    hubs = [item.split("=", 1)[0] for item in dominant]
    strong_connections = mini.get("strongest_connections") if isinstance(mini.get("strongest_connections"), list) else []
    nonzero = sum(1 for value in vector[:11] if abs(float(value)) >= 0.05)
    positive = sum(1 for value in vector[:11] if float(value) >= 0.0)
    negative = min(len(vector[:11]), 11) - positive
    if positive > negative:
        binary_axis = "naar aan/1 getrokken"
    elif negative > positive:
        binary_axis = "naar uit/0 getrokken"
    else:
        binary_axis = "in evenwicht tussen 0 en 1"
    return {
        "frame": "binary_attractor_window",
        "inner_model": "membrane_hub_route_graph",
        "dimension_count": min(len(vector), 11),
        "hub_count": len(hubs),
        "hubs": hubs[:5],
        "micro_observation_count": int(nonzero),
        "route_line_count": int(mini.get("connections") or len(strong_connections) or 0),
        "binary_axis": binary_axis,
        "dominant_route": (mini.get("last_route") or {}).get("observed") if isinstance(mini.get("last_route"), dict) else None,
        "membrane_boundary": "local_runtime_only",
    }


def _network_flow(network: dict[str, Any]) -> dict[str, Any]:
    mini = network.get("mini_router") if isinstance(network.get("mini_router"), dict) else {}
    last_route = mini.get("last_route") if isinstance(mini.get("last_route"), dict) else {}
    observed_route = str(last_route.get("observed") or "")
    route_superposition = last_route.get("superposition") if isinstance(last_route.get("superposition"), list) else []
    dhcp_state = str(network.get("dhcp") or "UNKNOWN")
    try:
        total_received = int(network.get("total_received") or 0)
    except (TypeError, ValueError):
        total_received = 0
    internet_flow = "active_flow_metadata" if total_received > 0 or route_superposition else "waiting_for_flow_metadata"
    return {
        "dhcp_state": dhcp_state,
        "internet_flow": internet_flow,
        "local_ip": network.get("local_ip"),
        "packets_observed": total_received,
        "router_mode": mini.get("mode"),
        "rotation_pull": mini.get("rotation_pull"),
        "observed_route": observed_route or "not_observed_yet",
        "route_superposition": route_superposition[:4],
        "observation_sources": (mini.get("observation_sources") or [])[:5],
        "allowed_through_pocket": ["DHCP address metadata", "internet flow metadata", "route pressure"],
        "real_forwarding": False,
        "real_packet_capture": False,
    }


def _safe_text(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    return text[: max(0, int(limit))]


def _safe_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    safe: dict[str, Any] = {}
    for key, item in value.items():
        text_key = str(key)[:80]
        if isinstance(item, (str, int, float, bool)) or item is None:
            safe[text_key] = item if not isinstance(item, str) else item[:220]
        elif isinstance(item, list):
            safe[text_key] = [
                element if isinstance(element, (int, float, bool)) or element is None else str(element)[:160]
                for element in item[:8]
            ]
        elif isinstance(item, dict):
            safe[text_key] = {
                str(inner_key)[:80]: inner_value if isinstance(inner_value, (int, float, bool)) or inner_value is None else str(inner_value)[:160]
                for inner_key, inner_value in list(item.items())[:8]
            }
    return safe


def _unique_text(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            output.append(text)
    return output


def _float_list(value: Any) -> list[float]:
    try:
        return [float(item) for item in list(value)[:11]]
    except Exception:
        return []


def _round(value: Any) -> float:
    try:
        return round(float(value), 4)
    except Exception:
        return 0.0


def _clamp_float(value: Any, minimum: float, maximum: float, *, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


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
