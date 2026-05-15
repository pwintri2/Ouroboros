"""OpenClaw Voice adapter helpers for the Ouroboros cockpit.

The OpenClaw voice server speaks an OpenAI-compatible chat API when a gateway
URL is configured.  This module exposes sanitized status metadata and small
request/response shims so the cockpit can use Ouroboros as that gateway.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import requests


DEFAULT_OPENCLAW_ROOT = "/home/pwintri2/openclaw-voice"
DEFAULT_OPENCLAW_PORT = 8765
DEFAULT_GATEWAY_URL = "http://127.0.0.1:8010/api/openclaw-voice"


def _int_env(name: str, default: int) -> int:
    try:
        return int(str(os.getenv(name, str(default))).strip())
    except (TypeError, ValueError):
        return default


def _status_probe(url: str) -> dict[str, Any]:
    try:
        response = requests.get(url.rstrip("/") + "/", timeout=0.8)
        return {
            "status": "online" if response.status_code < 500 else "error",
            "http_status": response.status_code,
            "reachable": response.status_code < 500,
            "fake_success": False,
        }
    except Exception as exc:
        return {
            "status": "offline",
            "reachable": False,
            "reason": str(exc)[:300],
            "fake_success": False,
        }


def openclaw_voice_status_payload() -> dict[str, Any]:
    root = Path(os.getenv("OPENCLAW_VOICE_ROOT", DEFAULT_OPENCLAW_ROOT)).expanduser()
    browser_host = os.getenv("OPENCLAW_VOICE_BROWSER_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = _int_env("OPENCLAW_PORT", DEFAULT_OPENCLAW_PORT)
    server_url = os.getenv("OPENCLAW_VOICE_SERVER_URL", f"http://{browser_host}:{port}").strip()
    websocket_url = os.getenv("OPENCLAW_VOICE_WS_URL", f"ws://{browser_host}:{port}/ws").strip()
    gateway_url = (
        os.getenv("OPENCLAW_OUROBOROS_GATEWAY_URL")
        or os.getenv("OPENCLAW_GATEWAY_URL")
        or DEFAULT_GATEWAY_URL
    ).rstrip("/")

    root_visible = (root / "src" / "server" / "main.py").exists() and (root / "SKILL.md").exists()
    configured = root_visible or str(root) == DEFAULT_OPENCLAW_ROOT or bool(os.getenv("OPENCLAW_VOICE_ROOT"))
    probe = _status_probe(server_url) if os.getenv("OPENCLAW_VOICE_PROBE", "1") != "0" else {
        "status": "skipped",
        "reachable": False,
        "fake_success": False,
    }
    reachable = bool(probe.get("reachable"))
    status = "online" if reachable else ("configured" if configured else "missing")
    return {
        "status": status,
        "configured": configured,
        "available": reachable,
        "reachable_from_backend": reachable,
        "backend_probe": probe,
        "root": str(root),
        "root_visible_from_backend": root_visible,
        "server_url": server_url,
        "websocket_url": websocket_url,
        "gateway_url": gateway_url,
        "gateway_chat_completions": f"{gateway_url}/v1/chat/completions",
        "protocol": {
            "websocket_path": "/ws",
            "input_audio": "base64 float32 PCM mono 16kHz",
            "output_audio": "base64 PCM chunks, usually 24kHz",
            "events": ["transcript", "response_chunk", "audio_chunk", "response_complete"],
        },
        "start_script": "scripts/start_openclaw_ouroboros_voice.sh",
        "next_action": (
            "Start scripts/start_openclaw_ouroboros_voice.sh, then use the Cockpit voice buttons."
            if configured and not reachable
            else "Connect from the Cockpit voice buttons."
        ),
        "secrets_returned": False,
        "fake_success": False,
    }


def openai_content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                if isinstance(item.get("text"), str):
                    parts.append(item["text"])
                elif isinstance(item.get("content"), str):
                    parts.append(item["content"])
        return "\n".join(part for part in parts if part).strip()
    if isinstance(content, dict):
        if isinstance(content.get("text"), str):
            return content["text"]
        if isinstance(content.get("content"), str):
            return content["content"]
    return str(content)


def extract_openai_chat_request(body: dict[str, Any]) -> dict[str, Any]:
    messages = body.get("messages") if isinstance(body.get("messages"), list) else []
    system_parts: list[str] = []
    normalized: list[dict[str, str]] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "").strip().lower() or "user"
        text = openai_content_to_text(message.get("content")).strip()
        if not text:
            continue
        if role == "system":
            system_parts.append(text)
        elif role in {"user", "assistant", "tool"}:
            normalized.append({"role": role, "content": text})

    last_user_index = next(
        (idx for idx in range(len(normalized) - 1, -1, -1) if normalized[idx]["role"] == "user"),
        -1,
    )
    prompt = normalized[last_user_index]["content"] if last_user_index >= 0 else openai_content_to_text(body.get("prompt")).strip()
    history = normalized[:last_user_index] if last_user_index >= 0 else normalized
    return {
        "prompt": prompt,
        "history": history[-12:],
        "system_prompt": "\n\n".join(system_parts).strip() or None,
        "requested_model": str(body.get("model") or "openclaw:voice"),
        "stream": bool(body.get("stream")),
    }


def cockpit_response_text(payload: dict[str, Any]) -> str:
    for key in ("response", "message", "reason", "error"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "Ik kreeg geen bruikbaar antwoord terug van Ouroboros."


def openai_completion_payload(
    *,
    content: str,
    requested_model: str,
    cockpit_payload: dict[str, Any],
    completion_id: str | None = None,
) -> dict[str, Any]:
    return {
        "id": completion_id or f"chatcmpl-ouroboros-{int(time.time() * 1000)}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": requested_model or "openclaw:voice",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
        "ouroboros": {
            "status": cockpit_payload.get("status"),
            "route": cockpit_payload.get("route"),
            "provider": cockpit_payload.get("provider"),
            "model": cockpit_payload.get("model"),
            "local_only": cockpit_payload.get("local_only"),
            "fake_success": False,
        },
        "secrets_returned": False,
    }


def openai_stream_events(*, content: str, requested_model: str, completion_id: str) -> list[str]:
    created = int(time.time())
    role_chunk = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": requested_model or "openclaw:voice",
        "choices": [{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}],
    }
    content_chunk = {
        **role_chunk,
        "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": None}],
    }
    done_chunk = {
        **role_chunk,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    return [
        f"data: {json.dumps(role_chunk, ensure_ascii=False)}\n\n",
        f"data: {json.dumps(content_chunk, ensure_ascii=False)}\n\n",
        f"data: {json.dumps(done_chunk, ensure_ascii=False)}\n\n",
        "data: [DONE]\n\n",
    ]
