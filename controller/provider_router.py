"""WintripAI Provider Router — CLI/API-gebaseerde multi-AI routing."""
import os
import subprocess
from typing import Optional

GEMINI_MODELS = ["gemini-2.5-pro", "gemini-2.0-flash", "gemini-1.5-pro", "gemini-1.5-flash"]
CLAUDE_MODELS = ["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"]
OPENAI_MODELS = ["gpt-5.4", "gpt-5", "gpt-4.1"]
OLLAMA_MODELS = ["gemma4:latest", "llama3.1:latest", "qwen2.5:latest", "phi4:latest"]


def _run(cmd: list, timeout: int = 90) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = r.stdout.strip()
        return out if out else f"[CLI fout] {r.stderr.strip()[:400]}"
    except subprocess.TimeoutExpired:
        return f"[Timeout >{timeout}s]"
    except FileNotFoundError:
        return f"[CLI niet gevonden: {cmd[0]}]"
    except Exception as e:
        return f"[Fout: {e}]"


def route_gemini(prompt: str, model: str = "gemini-2.5-pro",
                 system_prompt: Optional[str] = None) -> str:
    gemini_cmd = os.getenv("WINTRIP_GEMINI_CLI", "gemini")
    full = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
    for cmd in [[gemini_cmd, "-m", model, full],
                [gemini_cmd, "--model", model, "-p", full],
                [gemini_cmd, full]]:
        r = _run(cmd)
        if not r.startswith("["):
            return r
    return r


def route_openai(prompt: str, model: str = "gpt-5.4",
                 system_prompt: Optional[str] = None) -> str:
    openai_cmd = os.getenv("WINTRIP_OPENAI_CLI", "codex")
    full = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
    for cmd in [[openai_cmd, "exec", "--model", model, full],
                [openai_cmd, "-m", model, full],
                [openai_cmd, full]]:
        r = _run(cmd, timeout=120)
        if not r.startswith("["):
            return r
    return r


def route_codex(prompt: str, model: str = "gpt-5.4",
                system_prompt: Optional[str] = None) -> str:
    return route_openai(prompt, model=model, system_prompt=system_prompt)


def route_ollama(prompt: str, model: str = "gemma4:latest",
                 system_prompt: Optional[str] = None) -> str:
    try:
        from controller.ollama_client import OllamaClient
    except ImportError:
        from ollama_client import OllamaClient
    client = OllamaClient(model=model)
    return client.chat(prompt, system_prompt=system_prompt, model=model)


def route_antigravity(prompt: str, model: str = "",
                      system_prompt: Optional[str] = None) -> str:
    cmd = os.getenv("WINTRIP_ANTIGRAVITY_CMD", "").strip()
    if not cmd:
        return "[ANTIGRAVITY niet geconfigureerd]"
    full = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
    return _run([cmd, full], timeout=120)


def route_claude(prompt: str, model: str = "claude-opus-4-6",
                 system_prompt: Optional[str] = None) -> str:
    cmd = ["claude", "-p", prompt, "--print", "--model", model]
    if system_prompt:
        cmd += ["--system", system_prompt]
    return _run(cmd, timeout=120)


def route_provider(provider: str, prompt: str, model: str, system_prompt: Optional[str] = None) -> str:
    provider_name = (provider or "ollama").lower()
    if provider_name in {"openai", "codex", "chatgpt"}:
        return route_openai(prompt, model=model or "gpt-5.4", system_prompt=system_prompt)
    if provider_name == "gemini":
        return route_gemini(prompt, model=model or "gemini-2.5-pro", system_prompt=system_prompt)
    if provider_name == "claude":
        return route_claude(prompt, model=model or "claude-opus-4-6", system_prompt=system_prompt)
    if provider_name == "antigravity":
        return route_antigravity(prompt, model=model, system_prompt=system_prompt)
    return route_ollama(prompt, model=model or "gemma4:latest", system_prompt=system_prompt)


def check_providers() -> dict:
    result = {}
    checks = [
        ("gemini", [os.getenv("WINTRIP_GEMINI_CLI", "gemini"), "--version"], GEMINI_MODELS),
        ("claude", ["claude", "--version"], CLAUDE_MODELS),
        ("openai", [os.getenv("WINTRIP_OPENAI_CLI", "codex"), "--version"], OPENAI_MODELS),
    ]
    for name, vcmd, models in checks:
        try:
            r = subprocess.run(vcmd, capture_output=True, text=True, timeout=5)
            result[name] = {
                "available": r.returncode == 0,
                "version": r.stdout.strip() or r.stderr.strip(),
                "models": models,
            }
        except Exception as e:
            result[name] = {"available": False, "version": str(e), "models": []}

    result["codex"] = result.get("openai", {"available": False, "version": "", "models": OPENAI_MODELS})
    result["ollama"] = {"available": True, "models": OLLAMA_MODELS}
    result["antigravity"] = {
        "available": bool(os.getenv("WINTRIP_ANTIGRAVITY_CMD", "").strip()),
        "version": "env-configured",
        "models": [],
    }
    return result
