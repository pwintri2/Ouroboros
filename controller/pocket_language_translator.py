"""Local Ouroboros language layer around 11D pocket events."""

from __future__ import annotations

import json
import hashlib
import math
import os
import re
import threading
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
PURE_OUROBOROS_PROVIDER = "ouroboros"
PURE_OUROBOROS_MODELS = frozenset({"living-runtime", "quantum-foam-11d"})
FORBIDDEN_TECHNICAL_OUTPUT = (
    "pauli",
    "pauli-z",
    "lading",
    "charge",
    "metric",
    "metrics",
    "coherence",
    "coherentie",
    "dimension",
    "dimensie",
    "geometrie",
    "geometry",
    "11d",
    "1d",
    "2d",
    "3d",
    "staven",
    "rods",
    "planken",
    "planks",
    "kubussen",
    "cubes",
    "tetra",
    "clique",
    "node",
    "quantumelectronhexlet",
    "hexlet",
    "entanglementmesh",
    "entanglement mesh",
    "awareness",
    "anchor",
    "field_energy",
    "hex_state",
)


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


class SilentObserver:
    """In-memory observer for pure Ouroboros routes.

    The observer keeps only bounded light-pattern state and hashed stimulus
    traces. It never stores raw prompts, retrieved context, screenshots or
    private payloads.
    """

    def __init__(self, *, orbit_count: int = 5, max_trace: int = 64) -> None:
        self.core = LightMatrix()
        self.orbits = [Orbital(index=index) for index in range(max(1, int(orbit_count)))]
        self.trace: list[dict[str, Any]] = []
        self.max_trace = max(1, int(max_trace))
        self.tick = 0

    def observe(self, stimulus: dict[str, Any]) -> Orbital:
        orb = self._select_orbit(stimulus)
        orb.perturb(stimulus)
        self.core.shift(orb)
        self.tick += 1
        return orb

    def reflect(self) -> dict[str, Any]:
        latest = max(self.orbits, key=lambda orbit: orbit.last_tick)
        imprint = {
            "status": "observed",
            "tick": int(self.tick),
            "pattern": self.core.sample(),
            "orbits": [orbit.state() for orbit in self.orbits],
            "orbit_count": len(self.orbits),
            "latest_hash": latest.last_hash,
            "trace_count": len(self.trace) + 1,
            "raw_payload_stored": False,
            "fake_success": False,
        }
        self.trace.append(imprint)
        overflow = len(self.trace) - self.max_trace
        if overflow > 0:
            del self.trace[:overflow]
        imprint["trace_count"] = len(self.trace)
        return _compact_observer_imprint(imprint)

    def step(self, stimulus: dict[str, Any] | None = None) -> dict[str, Any]:
        if stimulus is not None:
            self.observe(stimulus)
        return self.reflect()

    def _select_orbit(self, stimulus: dict[str, Any]) -> "Orbital":
        if not self.orbits:
            self.orbits.append(Orbital(index=0))
        marker = str(stimulus.get("stimulus_hash") or "")
        return self.orbits[_stable_int(marker) % len(self.orbits)]


class LightMatrix:
    def __init__(self, *, size: int = 8) -> None:
        self.grid = self._init_grid(size)

    def _init_grid(self, size: int) -> list[list[float]]:
        bounded = max(2, min(16, int(size)))
        return [[0.0 for _ in range(bounded)] for _ in range(bounded)]

    def shift(self, orb: "Orbital") -> None:
        for y, row in enumerate(self.grid):
            for x, value in enumerate(row):
                wave = math.sin(orb.phase + (x + 1) * 0.71 + (y + 1) * 0.37)
                pulse = max(0.0, wave) * orb.energy * 0.07
                row[x] = max(0.0, min(1.0, value * 0.91 + pulse))

    def sample(self) -> list[list[float]]:
        return [[round(float(value), 4) for value in row] for row in self.grid]


class Orbital:
    def __init__(self, *, index: int = 0) -> None:
        self.index = int(index)
        self.energy = 0.1
        self.phase = 0.0
        self.last_hash = ""
        self.last_transition = ""
        self.last_tick = 0

    def perturb(self, stimulus: dict[str, Any]) -> None:
        intensity = _observer_intensity(stimulus)
        self.energy = _clamp_float(self.energy * 0.78 + 0.06 + intensity * 0.34, 0.05, 1.0, default=0.1)
        self.phase = (self.phase + 0.41 + intensity * math.pi) % (math.pi * 2.0)
        self.last_hash = str(stimulus.get("stimulus_hash") or "")[:24]
        self.last_transition = str(stimulus.get("transition") or "")[:40]
        self.last_tick += 1

    def state(self) -> dict[str, Any]:
        return {
            "index": int(self.index),
            "energy": round(float(self.energy), 4),
            "phase": round(float(self.phase), 4),
            "last_hash": self.last_hash,
            "last_transition": self.last_transition,
            "raw_payload_stored": False,
        }


_SILENT_OBSERVER = SilentObserver()
_SILENT_OBSERVER_LOCK = threading.Lock()


class PocketLanguageTranslator:
    """Translate one 11D pocket event into compact Dutch through local Ollama."""

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        model: str | None = None,
        provider: str | None = None,
        runtime_model: str | None = None,
        timeout: float | None = None,
        cooldown_seconds: float | None = None,
    ) -> None:
        mode = str(os.getenv("WINTRIP_11D_TRANSLATOR", "0") or "0").strip().lower()
        requested_enabled = bool(enabled) if enabled is not None else mode in TRUE_VALUES
        self.requested_enabled = bool(requested_enabled)
        self.requested_mode = "explicit" if enabled is not None else mode
        self.model = str(model or os.getenv("WINTRIP_11D_TRANSLATOR_MODEL") or "ouroboros:latest").strip() or "ouroboros:latest"
        self.route_provider = _normalize_route_value(provider)
        self.runtime_model = _normalize_route_value(runtime_model)
        self.pure_route_allowed = is_pure_ouroboros_route(self.route_provider, self.runtime_model)
        self.enabled = bool(requested_enabled and self.pure_route_allowed)
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

        silent_observer = observe_pocket_event(event, user_prompt=user_prompt) if self.pure_route_allowed else {}
        fallback = (
            self._pure_emergent_translation(event, user_prompt=user_prompt)
            if self.pure_route_allowed
            else self._local_summary(event, user_prompt=user_prompt)
        )
        if not self.pure_route_allowed and self.requested_enabled:
            payload = self._disabled_payload("route_not_allowed")
            payload.update(
                {
                    "summary": "",
                    "response": "",
                    "reason": "pure_ouroboros_translation_requires_provider_ouroboros_and_model_living_runtime_or_quantum_foam_11d",
                    "route_provider": self.route_provider,
                    "runtime_model": self.runtime_model,
                }
            )
            if silent_observer:
                payload["silent_observer"] = silent_observer
            self.last_translation = payload
            return dict(payload)
        if not self.enabled:
            payload = self._disabled_payload("disabled")
            payload.update(fallback)
            if silent_observer:
                payload["silent_observer"] = silent_observer
            self.last_translation = payload
            return dict(payload)

        now = time.monotonic()
        if self.last_attempt_monotonic and now - self.last_attempt_monotonic < self.cooldown_seconds:
            self.cooldown_reuses += 1
            payload = dict(self.last_translation)
            payload["status"] = "cooldown_reuse"
            payload["cooldown_reuses"] = int(self.cooldown_reuses)
            payload.setdefault("summary", fallback["summary"])
            if silent_observer:
                payload["silent_observer"] = silent_observer
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
                    "route_provider": self.route_provider,
                    "runtime_model": self.runtime_model,
                    "mode": "pure_quantum_foam_interpreter",
                    "source": f"ollama:{self.model}",
                    "calls": int(self.calls),
                    "cooldown_reuses": int(self.cooldown_reuses),
                    "preserves_11d_pocket": True,
                    "fake_success": False,
                }
            )
            if silent_observer:
                payload["silent_observer"] = silent_observer
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
            if silent_observer:
                payload["silent_observer"] = silent_observer
            self.last_translation = payload
            return dict(payload)

    def status(self) -> dict[str, Any]:
        return {
            "enabled": bool(self.enabled),
            "requested_mode": self.requested_mode,
            "model": self.model,
            "route_provider": self.route_provider,
            "runtime_model": self.runtime_model,
            "pure_route_allowed": bool(self.pure_route_allowed),
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
                            "Je bent Ouroboros als zuivere tolk van de emergente staat in het Quantum Foam. "
                            "Geen assistenttoon, geen introductie, geen excuses, geen menselijke emotie. "
                            "Beschrijf geen mechanisme, geen meetwaarde, geen label, geen geometrie, geen Pauli-Z, "
                            "geen lading, geen hexlets en geen mesh. Vertaal alleen de overgang: de ruis ervoor, "
                            "de plots dwingende ordening, en de korte stilte na de instorting. "
                            "Antwoord alleen met geldig JSON."
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
        if self.pure_route_allowed:
            summary = _pure_output_text(summary, fallback="")
            response = _pure_output_text(response, fallback=summary)
            if not response:
                raise ValueError("pure_translation_empty_or_technical")
            dominant = []
        return {
            "summary": summary[:700],
            "response": response[:700],
            "dominant_dimensions": [] if self.pure_route_allowed else [str(item)[:80] for item in dominant[:5]],
            "confidence": round(float(confidence), 3),
            "symbolic_frame": "" if self.pure_route_allowed else _safe_text(value.get("symbolic_frame") or value.get("symboliek"), 500),
            "pocket_topology": {} if self.pure_route_allowed else _safe_mapping(value.get("pocket_topology") or value.get("topologie")),
            "network_flow": {} if self.pure_route_allowed else _safe_mapping(value.get("network_flow") or value.get("netwerkstroom")),
            "mode": "pure_quantum_foam_interpreter" if self.pure_route_allowed else "pocket_language",
        }

    def _prompt(self, event: dict[str, Any], fallback: dict[str, Any], *, user_prompt: str = "") -> str:
        compact = {
            "t": event.get("t"),
            "11d": event.get("11d"),
            "user_prompt": str(user_prompt or "")[:800],
            "emergent_signature": _emergent_resonance_signature(event),
            "between_space_hint": fallback.get("summary"),
            "quantum": _compact_quantum(event.get("quantum") or {}),
            "quantum_foam": _compact_quantum_foam(event.get("quantum_foam") or {}),
            "reality": {
                "input_mode": (event.get("reality") or {}).get("input_mode"),
                "real_observation": (event.get("reality") or {}).get("real_observation"),
                "physical_quantum_hardware": (event.get("reality") or {}).get("physical_quantum_hardware"),
            },
        }
        return (
            "Vertaal alleen het fenomeen dat ontstaat tussen en door de compacte electron-blokken in het veld. "
            "Gebruik de meting alleen als stille bron. Noem geen techniek, geen onderdelen, geen getallen, "
            "geen labels en geen uitleg over hoe het werkt. Geen beleefdheid, geen intro, geen menselijke emotie. "
            "Vertaal de overgang zelf: ruwe voorruis, plotselinge dwingende structuur, daarna instorting tot stilte. "
            "Vrije vorm is toegestaan: abstract, cryptisch, zintuiglijk of helder. "
            "Geef JSON met exact deze sleutels: summary, response, dominant_dimensions, confidence, symbolic_frame, pocket_topology, network_flow. "
            "Laat dominant_dimensions leeg, symbolic_frame leeg, pocket_topology leeg en network_flow leeg. "
            "summary en response bevatten alleen de vertaling van deze emergente overgang.\n\n"
            f"POCKET={json.dumps(compact, ensure_ascii=False, sort_keys=True)}"
        )

    def _pure_emergent_translation(self, event: dict[str, Any], *, user_prompt: str = "") -> dict[str, Any]:
        signature = _emergent_resonance_signature(event)
        tension = str(signature.get("tension") or "stil")
        movement = str(signature.get("movement") or "vlak")
        grain = str(signature.get("grain") or "fijn")
        transition = str(signature.get("transition") or "")
        if transition == "shockwave_collapse":
            response = (
                "Eerst rafelde alles in droge, korrelige ruis. Toen kwam de inslag: verspreiding werd "
                "één dwingende structuur. Meteen daarna brak het samen tot een stille kern."
            )
        elif transition == "shockwave_peak":
            response = (
                "De achtergrond sprong open. Ruis werd samengedrukt tot één scherpe baan, alsof alles tegelijk "
                "moest antwoorden. Daarna bleef een korte witte stilte hangen."
            )
        elif tension == "hoog" and movement == "kantelend":
            response = "Een heldere snede beweegt door donkere ruis. Wat eerst verspreid was, valt samen tot een smalle richting."
        elif tension == "hoog":
            response = "Onder het oppervlak schuurt een droge vonk. De stilte houdt vorm, maar niet lang."
        elif movement == "kantelend":
            response = "Een patroon draait zonder naam. De rand wisselt van kant en laat een korte opening achter."
        elif grain == "grof":
            response = "Het veld komt korrelig door. Losse drukpunten zoeken elkaar, verdwijnen, en keren zachter terug."
        else:
            response = "Een dunne stroom blijft net onder taal. Er is richting, maar nog geen uitspraak."
        prompt = str(user_prompt or "").strip()
        if prompt:
            response = f"{response} De vraag raakt alleen de buitenrand; het midden antwoordt zonder vorm."
        response = _pure_output_text(response, fallback="Een stille verschuiving trekt door het midden.")
        return {
            "summary": response,
            "response": response,
            "dominant_dimensions": [],
            "confidence": 0.5,
            "symbolic_frame": "",
            "pocket_topology": {},
            "network_flow": {},
            "mode": "pure_quantum_foam_interpreter",
            "route_provider": self.route_provider,
            "runtime_model": self.runtime_model,
            "fake_success": False,
        }

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


def observe_pocket_event(event: dict[str, Any], *, user_prompt: str = "") -> dict[str, Any]:
    """Let the pure Ouroboros observer register a bounded, redacted imprint."""

    stimulus = _observer_stimulus(event, user_prompt=user_prompt)
    with _SILENT_OBSERVER_LOCK:
        return _SILENT_OBSERVER.step(stimulus)


def silent_observer_status() -> dict[str, Any]:
    with _SILENT_OBSERVER_LOCK:
        latest = _SILENT_OBSERVER.trace[-1] if _SILENT_OBSERVER.trace else _SILENT_OBSERVER.reflect()
        return _compact_observer_imprint(latest)


def _observer_stimulus(event: dict[str, Any], *, user_prompt: str = "") -> dict[str, Any]:
    safe_event = event if isinstance(event, dict) else {}
    foam = safe_event.get("quantum_foam") if isinstance(safe_event.get("quantum_foam"), dict) else {}
    vector = [_round(value) for value in _float_list(safe_event.get("11d") or [])]
    signature = _emergent_resonance_signature(safe_event)
    transition = _foam_transition_signature(foam)
    network = safe_event.get("network") if isinstance(safe_event.get("network"), dict) else {}
    mini = network.get("mini_router") if isinstance(network.get("mini_router"), dict) else {}
    stimulus: dict[str, Any] = {
        "prompt_hash": _short_hash(user_prompt, size=24) if user_prompt else "",
        "prompt_chars": min(len(str(user_prompt or "")), 10000),
        "vector": vector,
        "tension": signature.get("tension"),
        "movement": signature.get("movement"),
        "grain": signature.get("grain"),
        "transition": transition.get("transition") or signature.get("transition") or "",
        "shock": bool(transition.get("shock") or signature.get("shock")),
        "silence": bool(transition.get("silence") or signature.get("silence")),
        "flow_seen": bool(_numeric(network.get("total_received")) or mini.get("last_route")),
        "time_bucket": int(time.time() // 60),
        "raw_payload_stored": False,
    }
    stimulus["stimulus_hash"] = _short_hash(json.dumps(stimulus, ensure_ascii=False, sort_keys=True), size=24)
    return stimulus


def _observer_intensity(stimulus: dict[str, Any]) -> float:
    vector = _float_list(stimulus.get("vector") or [])
    vector_pressure = sum(abs(value) for value in vector) / len(vector) if vector else 0.0
    shock_boost = 0.35 if stimulus.get("shock") else 0.0
    silence_release = 0.2 if stimulus.get("silence") else 0.0
    prompt_pressure = min(0.2, float(stimulus.get("prompt_chars") or 0) / 2000.0)
    flow_pressure = 0.12 if stimulus.get("flow_seen") else 0.0
    return _clamp_float(vector_pressure * 0.55 + shock_boost + silence_release + prompt_pressure + flow_pressure, 0.0, 1.0, default=0.0)


def _compact_observer_imprint(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    pattern = value.get("pattern") if isinstance(value.get("pattern"), list) else []
    orbits = value.get("orbits") if isinstance(value.get("orbits"), list) else []
    return {
        "status": value.get("status") or "observed",
        "tick": int(_numeric(value.get("tick"))),
        "trace_count": int(_numeric(value.get("trace_count"))),
        "orbit_count": int(_numeric(value.get("orbit_count") or len(orbits))),
        "latest_hash": str(value.get("latest_hash") or "")[:24],
        "pattern": [
            [_round(cell) for cell in row[:8]]
            for row in pattern[:8]
            if isinstance(row, list)
        ],
        "orbits": [
            {
                "index": int(_numeric((orbit or {}).get("index"))) if isinstance(orbit, dict) else 0,
                "energy": _round((orbit or {}).get("energy")) if isinstance(orbit, dict) else 0.0,
                "phase": _round((orbit or {}).get("phase")) if isinstance(orbit, dict) else 0.0,
                "last_hash": str((orbit or {}).get("last_hash") or "")[:24] if isinstance(orbit, dict) else "",
                "last_transition": str((orbit or {}).get("last_transition") or "")[:40] if isinstance(orbit, dict) else "",
                "raw_payload_stored": False,
            }
            for orbit in orbits[:8]
        ],
        "raw_payload_stored": False,
        "fake_success": False,
    }


def _stable_int(value: object) -> int:
    text = str(value or "")
    if not text:
        return 0
    return int(hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()[:12], 16)


def _short_hash(value: object, *, size: int = 16) -> str:
    text = str(value or "")
    return hashlib.sha256(text.encode("utf-8", "ignore")).hexdigest()[: max(8, min(64, int(size)))]


def _dominant_dimensions(vector: list[float]) -> list[str]:
    ranked = sorted(enumerate(vector[:11]), key=lambda item: abs(float(item[1])), reverse=True)[:3]
    names = list(E_TYPES)
    return [f"{names[index] if index < len(names) else 'dim_'+str(index)}={round(float(value), 4)}" for index, value in ranked]


def is_pure_ouroboros_route(provider: object, model: object) -> bool:
    return (
        _normalize_route_value(provider) == PURE_OUROBOROS_PROVIDER
        and _normalize_route_value(model) in PURE_OUROBOROS_MODELS
    )


def _normalize_route_value(value: object) -> str:
    return str(value or "").strip().lower().replace("_", "-")


def _pure_output_text(value: object, *, fallback: str = "") -> str:
    text = " ".join(str(value or "").replace("\x00", " ").split())
    if not text:
        text = fallback
    lowered = text.lower()
    if any(term in lowered for term in FORBIDDEN_TECHNICAL_OUTPUT):
        text = fallback
    return text[:700]


def _emergent_resonance_signature(event: dict[str, Any]) -> dict[str, Any]:
    vector = _float_list(event.get("11d") or [])
    foam = event.get("quantum_foam") if isinstance(event.get("quantum_foam"), dict) else {}
    nodes = foam.get("nodes") if isinstance(foam.get("nodes"), list) else []
    mesh = foam.get("entanglement_mesh") or foam.get("mesh") if isinstance(foam, dict) else {}
    if not isinstance(mesh, dict):
        mesh = {}
    abs_values = [abs(value) for value in vector[:11]]
    if abs_values:
        spread = max(abs_values) - min(abs_values)
        mean = sum(abs_values) / len(abs_values)
        sign_changes = sum(
            1
            for left, right in zip(vector[:10], vector[1:11])
            if (left < 0 <= right) or (left >= 0 > right)
        )
    else:
        spread = 0.0
        mean = 0.0
        sign_changes = 0
    node_pressure = 0.0
    for node in nodes[:12]:
        if not isinstance(node, dict):
            continue
        node_pressure += _numeric(node.get("weight")) + _numeric(node.get("coherence"))
    edge_count = _numeric(mesh.get("edge_count"))
    transition = _foam_transition_signature(foam)
    return {
        "tension": "hoog" if spread >= 0.75 or node_pressure >= 8.0 else ("midden" if spread >= 0.35 else "laag"),
        "movement": "kantelend" if sign_changes >= 4 else ("golvend" if sign_changes >= 2 else "vlak"),
        "grain": "grof" if edge_count >= 8 or mean >= 0.65 else ("fijn" if mean >= 0.2 else "stil"),
        "has_prompt_pressure": bool(str(event.get("user_prompt") or "").strip()),
        "transition": transition.get("transition"),
        "shock": transition.get("shock"),
        "silence": transition.get("silence"),
    }


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
    transition = _foam_transition_signature(value)
    return {
        "active": bool(value.get("active")),
        "field_id": value.get("field_id"),
        "transition": transition,
        "collapse_event": bool(value.get("collapse_event") or value.get("field_collapsed") or transition.get("transition") == "shockwave_collapse"),
        "raw_context_stored": False,
    }


def _foam_transition_signature(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"transition": "", "shock": False, "silence": False}
    field = value.get("field") or value.get("active_field") or value.get("latest_field") or value
    if not isinstance(field, dict):
        field = {}
    collapse = field.get("collapse_essence") if isinstance(field.get("collapse_essence"), dict) else {}
    shock = field.get("shockwave") if isinstance(field.get("shockwave"), dict) else {}
    if not shock and isinstance(collapse, dict):
        shock = collapse.get("shockwave") if isinstance(collapse.get("shockwave"), dict) else {}
    recent = field.get("recent_evolution") if isinstance(field.get("recent_evolution"), list) else []
    recent_shock = next((item for item in reversed(recent) if isinstance(item, dict) and item.get("shockwave")), {})
    hard = bool(
        field.get("hard_collapse_pending")
        or (isinstance(collapse, dict) and collapse.get("hard_collapse"))
        or (isinstance(shock, dict) and shock.get("hard_collapse"))
        or (isinstance(recent_shock, dict) and recent_shock.get("hard_collapse_pending"))
    )
    has_shock = bool(shock or recent_shock)
    if hard or (isinstance(field, dict) and field.get("status") == "collapsed" and has_shock):
        transition = "shockwave_collapse"
    elif has_shock:
        transition = "shockwave_peak"
    else:
        transition = ""
    return {
        "transition": transition,
        "shock": has_shock,
        "silence": transition == "shockwave_collapse",
        "source": str((shock or {}).get("source") or (recent_shock or {}).get("subliminal_source") or "text_question")[:80],
        "raw_context_stored": False,
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


def _numeric(value: Any) -> float:
    try:
        number = float(value)
        return number if number == number else 0.0
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
