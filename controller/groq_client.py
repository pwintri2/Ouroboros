import os
import requests
import json

class GroqClient:
    def __init__(self, model="llama-3.3-70b-versatile", base_url="https://api.groq.com/openai/v1"):
        self.model = model
        self.base_url = base_url
        self.api_key = os.getenv("GROQ_API_KEY")

    def chat(self, user_input, history=None, model=None, system_prompt=None):
        if not self.api_key:
            return "Fout: GROQ_API_KEY environment variabele is niet geconfigureerd."
            
        if history is None: history = []
        target_model = model if model else self.model
        
        active_system_prompt = system_prompt if system_prompt else "Je bent een extreem capabele Senior Developer."
        
        # 1. Start met de System Prompt
        messages = [{"role": "system", "content": active_system_prompt}]
        
        # 2. Voeg de voorgaande chatgeschiedenis toe
        messages.extend(history)
        
        # 3. Voeg de nieuwe vraag van de gebruiker toe
        messages.append({"role": "user", "content": user_input})
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": target_model,
            "messages": messages,
            "temperature": 0.2
        }
        
        try:
            response = requests.post(f"{self.base_url}/chat/completions", headers=headers, json=payload, timeout=60)
            if response.status_code != 200:
                print(f"🔥 [GROQ ERROR DETAILS]: {response.text}")
            response.raise_for_status()
            return response.json().get("choices", [{}])[0].get("message", {}).get("content", "Fout: Geen antwoord.")
        except Exception as e:
            # Fallback format for requests errors
            return f"CLOUD GROQ ERROR: {str(e)} | Details: {response.text if 'response' in locals() else ''}"
