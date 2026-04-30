import os
import requests

try:
    from controller.ollama_router import (
        DEFAULT_OLLAMA_MODEL as _ROUTER_DEFAULT_OLLAMA_MODEL,
        MODEL_ALIASES,
        resolve_model_name as _resolve_router_model_name,
        select_ollama_model,
    )
except ImportError:
    from ollama_router import (
        DEFAULT_OLLAMA_MODEL as _ROUTER_DEFAULT_OLLAMA_MODEL,
        MODEL_ALIASES,
        resolve_model_name as _resolve_router_model_name,
        select_ollama_model,
    )

DEFAULT_OLLAMA_MODEL = _ROUTER_DEFAULT_OLLAMA_MODEL
OLLAMA_MODEL_MAP = dict(MODEL_ALIASES)

def resolve_model_name(model: str | None) -> str:
    """Always return the exact Ollama model string, never a friendly name."""
    return _resolve_router_model_name(model)


# Dit is de fallback als we geen specifieke persona meesturen
DEFAULT_SYSTEM_PROMPT = """
Je bent Wintrip, een onverbiddelijke, briljante lokale macOS Assistent.
Je spreekt uitsluitend Nederlands. Je bent GEEN ChatGPT.
Je draait 100% lokaal via Ollama op de machine van de gebruiker.
"""

class OllamaClient:
    def __init__(self, model=None, base_url="http://localhost:11434/api"):
        host = os.getenv("OLLAMA_HOST") or os.getenv("OLLAMA_BASE_URL") or base_url
        self.base_url = host.rstrip("/")
        if self.base_url.endswith("/api"):
            self.base_url = self.base_url[:-4]
        requested_model = model if model is not None else os.getenv("OLLAMA_MODEL", "")
        if requested_model:
            self.model = select_ollama_model(requested=requested_model)
        else:
            self.model = self._best_available_model()

    def list_models(self):
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            response.raise_for_status()
            return [m["name"] for m in response.json().get("models", [])]
        except Exception:
            return []

    def _best_available_model(self, role: str = "") -> str:
        return select_ollama_model(role=role, list_models=self.list_models)

    def select_model(self, requested: str = None, role: str = "") -> str:
        return select_ollama_model(requested=requested, role=role, list_models=self.list_models)

    def chat(self, user_input, history=None, model=None, system_prompt=None):
        if history is None: history = []
        requested_model = model if model else ""
        target_model = self.select_model(requested_model, role=system_prompt or "")
        
        # Bepaal de juiste system prompt (Persona)
        active_system_prompt = system_prompt if system_prompt else DEFAULT_SYSTEM_PROMPT
        
        # 1. Start met de System Prompt
        messages = [{"role": "system", "content": active_system_prompt}]
        
        # 2. Voeg de voorgaande chatgeschiedenis toe (Het Geheugen!)
        messages.extend(history)
        
        # 3. Voeg de nieuwe vraag van de gebruiker toe
        messages.append({"role": "user", "content": user_input})
        
        try:
            response = requests.post(
                f"{self.base_url}/api/chat",
                json={"model": target_model, "messages": messages, "stream": False, "options": {"temperature": 0.15}},
                timeout=120,
            )
            response.raise_for_status()
            return response.json().get("message", {}).get("content", "")
        except Exception as e:
            return f"LOKALE OLLAMA ERROR ({target_model}): {str(e)}"
