import os
import requests

OLLAMA_MODEL_MAP = {
    # Friendly names → exact ollama model names
    "llama3.1": "llama3.2:latest",
    "llama3": "llama3:latest",
    "llama-3.1": "llama3.2:latest",
    "Llama-3.1": "llama3.2:latest",
    "gemma2": "gemma2:latest",
    "gemma2:2b": "gemma2:2b",
    "phi3": "phi3:latest",
    "phi4": "phi4:latest",
    "qwen2.5": "qwen2.5:latest",
    "qwen2.5-coder:3b": "qwen2.5-coder:3b",
    "qwen2.5-coder:7b": "qwen2.5-coder:7b",
    "nomic-embed-text": "nomic-embed-text:latest",
}

DEFAULT_OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:latest")

def resolve_model_name(model: str) -> str:
    """Always return the exact Ollama model string, never a friendly name."""
    return OLLAMA_MODEL_MAP.get(model, model)


# Dit is de fallback als we geen specifieke persona meesturen
DEFAULT_SYSTEM_PROMPT = """
Je bent Wintrip, een onverbiddelijke, briljante lokale macOS Assistent.
Je spreekt uitsluitend Nederlands. Je bent GEEN ChatGPT.
Je draait 100% lokaal via Ollama op de machine van de gebruiker.
"""

class OllamaClient:
    def __init__(self, model=None, base_url="http://localhost:11434/api"):
        self.model = resolve_model_name(model)
        host = os.getenv("OLLAMA_HOST") or os.getenv("OLLAMA_BASE_URL") or base_url
        self.base_url = host.rstrip("/")
        if self.base_url.endswith("/api"):
            self.base_url = self.base_url[:-4]
        if not self.model:
            self.model = self._best_available_model()

    def list_models(self):
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            response.raise_for_status()
            return [m["name"] for m in response.json().get("models", [])]
        except Exception:
            return []

    def _best_available_model(self, role: str = "") -> str:
        available = self.list_models()
        if not available:
            return DEFAULT_OLLAMA_MODEL
        role_lower = role.lower()
        if "developer" in role_lower:
            preferences = ["deepseek-coder:latest", "devstral:latest", "codellama:13b", "llama3.2:latest", "llama3:latest"]
        elif "critic" in role_lower:
            preferences = ["mistral:latest", "phi3:latest", "llama3.2:latest", "llama3:latest"]
        elif "tester" in role_lower:
            preferences = ["phi3:latest", "mistral:latest", "llama3.2:latest", "deepseek-coder:latest"]
        else:
            preferences = ["llama3.2:latest", "llama3:latest", "mistral:latest", "phi3:latest", "deepseek-coder:latest"]
        for candidate in preferences:
            if candidate in available:
                return candidate
        return available[0]

    def select_model(self, requested: str = None, role: str = "") -> str:
        requested = resolve_model_name(requested) if requested else ""
        available = self.list_models()
        if requested and requested in available:
            return requested
        return self._best_available_model(role=role)

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
