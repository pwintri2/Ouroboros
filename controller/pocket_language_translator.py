"""Local Ouroboros language layer around 11D pocket events."""

from __future__ import annotations

import json
import os
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
                "options": {"temperature": 0.1, "num_predict": 220},
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
        value = json.loads(text)
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
        }

    def _prompt(self, event: dict[str, Any], fallback: dict[str, Any], *, user_prompt: str = "") -> str:
        compact = {
            "t": event.get("t"),
            "11d": event.get("11d"),
            "user_prompt": str(user_prompt or "")[:800],
            "dominant_dimensions": fallback.get("dominant_dimensions", []),
            "quantum": _compact_quantum(event.get("quantum") or {}),
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
            "Behoud de reality-boundary: Cirq/noise is lokaal en meet-gebaseerd, niet fysiek quantum. "
            "Geef JSON met exact deze sleutels: summary, response, dominant_dimensions, confidence. "
            "Maak response concreet, prompt-specifiek en maximaal twee korte zinnen. "
            "Begin niet met 'Ik ben Ouroboros' en herhaal geen standaardtekst over wat je bent.\n\n"
            f"POCKET={json.dumps(compact, ensure_ascii=False, sort_keys=True)}"
        )

    def _local_summary(self, event: dict[str, Any], *, user_prompt: str = "") -> dict[str, Any]:
        vector = _float_list(event.get("11d") or [])
        dominant = _dominant_dimensions(vector)
        quantum = event.get("quantum") or {}
        qif = event.get("qif") or {}
        runtime = str(quantum.get("runtime") or quantum.get("sdk") or "none")
        expectation = quantum.get("expectation", qif.get("expectation_z", 0.0))
        summary = (
            f"11D pocket actief: {', '.join(dominant) if dominant else 'geen dominante dimensie'}. "
            f"Meetlaag={runtime}, verwachting={_round(expectation)}."
        )
        prompt_text = str(user_prompt or "").strip()
        if prompt_text:
            response = f"Op je vraag lees ik nu vooral {', '.join(dominant[:2]) if dominant else 'een vlak 11D signaal'}; mijn antwoord blijft gegrond in deze pocket."
        else:
            response = "Ik kan deze pocket lezen als een lokaal runtime-signaal en vertaal hem zonder de 11D structuur te vervangen."
        return {
            "summary": summary,
            "response": response,
            "dominant_dimensions": dominant,
            "confidence": 0.42,
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
        "dhcp": value.get("dhcp"),
        "total_received": value.get("total_received"),
        "mini_router_mode": mini.get("mode"),
        "rotation_pull": mini.get("rotation_pull"),
    }


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
