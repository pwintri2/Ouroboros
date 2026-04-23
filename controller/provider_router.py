"""WintripAI Provider Router — CLI-gebaseerde multi-AI routing (geen API-kosten)."""
import subprocess
from typing import Optional

GEMINI_MODELS = ["gemini-2.5-pro","gemini-2.0-flash","gemini-1.5-pro","gemini-1.5-flash"]
CLAUDE_MODELS = ["claude-opus-4-6","claude-sonnet-4-6","claude-haiku-4-5-20251001"]

_ALLOWED_GEMINI_MODELS = frozenset(GEMINI_MODELS)
_ALLOWED_CLAUDE_MODELS = frozenset(CLAUDE_MODELS)

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
    if model not in _ALLOWED_GEMINI_MODELS:
        model = "gemini-2.5-pro"
    full = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
    for cmd in [["gemini", "-m", model, full],
                ["gemini", "--model", model, "-p", full],
                ["gemini", full]]:
        r = _run(cmd)
        if not r.startswith("["):
            return r
    return r

def route_claude(prompt: str, model: str = "claude-opus-4-6",
                 system_prompt: Optional[str] = None) -> str:
    if model not in _ALLOWED_CLAUDE_MODELS:
        model = "claude-opus-4-6"
    cmd = ["claude", "-p", prompt, "--print", "--model", model]
    if system_prompt:
        cmd += ["--system", system_prompt]
    return _run(cmd, timeout=120)

def check_providers() -> dict:
    result = {}
    for name, vcmd in [("gemini",["gemini","--version"]),
                       ("claude",["claude","--version"])]:
        try:
            r = subprocess.run(vcmd, capture_output=True, text=True, timeout=5)
            result[name] = {"available": r.returncode==0,
                            "version": r.stdout.strip() or r.stderr.strip(),
                            "models": GEMINI_MODELS if name=="gemini" else CLAUDE_MODELS}
        except Exception as e:
            result[name] = {"available": False, "version": str(e), "models": []}
    return result
