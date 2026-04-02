import requests
import json

# Dit is de fallback als we geen specifieke persona meesturen
DEFAULT_SYSTEM_PROMPT = """
Je bent Wintrip, een onverbiddelijke, briljante lokale macOS Assistent.
Je spreekt uitsluitend Nederlands. Je bent GEEN ChatGPT.
Je draait 100% lokaal via Ollama op de machine van de gebruiker.
"""

class OllamaClient:
    def __init__(self, model="gemma2", base_url="http://localhost:11434/api"):
        self.model = model
        self.base_url = base_url

    def list_models(self):
        try:
            tags_url = self.base_url.replace("/api", "") + "/api/tags"
            response = requests.get(tags_url, timeout=5)
            response.raise_for_status()
            models_data = response.json().get("models", [])
            return [m["name"] for m in models_data]
        except Exception:
            return ["gemma2", "llama3"]

    def chat(self, user_input, history=None, model=None, system_prompt=None):
        if history is None: history = []
        target_model = model if model else self.model
        
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
                f"{self.base_url}/chat", 
                json={"model": target_model, "messages": messages, "stream": False}, # target_model bug is hier gefixt!
                timeout=120
            )
            response.raise_for_status()
            return response.json().get("message", {}).get("content", "Fout: Geen antwoord.")
        except Exception as e:
            return f"LOKALE OLLAMA ERROR: {str(e)}"