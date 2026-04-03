import os
import ollama

OLLAMA_MODEL_MAP = {
    # Friendly names → exact ollama model names
    "llama3.1": "llama3.1:latest",
    "llama3": "llama3:latest",
    "llama-3.1": "llama3.1:latest",   # fix the broken variant
    "Llama-3.1": "llama3.1:latest",   # fix the broken variant
    "gemma2": "gemma2:latest",
    "gemma2:2b": "gemma2:2b",
    "phi3": "phi3:latest",
    "phi4": "phi4:latest",
    "qwen2.5": "qwen2.5:latest",
    "qwen2.5-coder:3b": "qwen2.5-coder:3b",
    "qwen2.5-coder:7b": "qwen2.5-coder:7b",
    "nomic-embed-text": "nomic-embed-text:latest",
}

DEFAULT_OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:latest")

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
    def __init__(self, model="llama3.1:latest", base_url="http://localhost:11434/api"):
        self.model = resolve_model_name(model)
        # base_url is ignored by the official package by default, but kept for signature compatibility
        self.base_url = base_url

    def list_models(self):
        try:
            response = ollama.list()
            return [m["name"] for m in response.get("models", [])]
        except Exception:
            return ["gemma2:latest", "llama3.1:latest"]

    def chat(self, user_input, history=None, model=None, system_prompt=None):
        if history is None: history = []
        target_model = resolve_model_name(model if model else self.model)
        
        # Bepaal de juiste system prompt (Persona)
        active_system_prompt = system_prompt if system_prompt else DEFAULT_SYSTEM_PROMPT
        
        # 1. Start met de System Prompt
        messages = [{"role": "system", "content": active_system_prompt}]
        
        # 2. Voeg de voorgaande chatgeschiedenis toe (Het Geheugen!)
        messages.extend(history)
        
        # 3. Voeg de nieuwe vraag van de gebruiker toe
        messages.append({"role": "user", "content": user_input})
        
        try:
            response = ollama.chat(
                model=target_model,
                messages=messages
            )
            return response['message']['content']
        except Exception as e:
            return f"LOKALE OLLAMA ERROR: {str(e)}"