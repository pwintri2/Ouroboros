import os
import requests


class GrokXAIClient:
    """Client voor xAI Grok API (OpenAI-compatibele interface op api.x.ai)."""

    def __init__(self, model="grok-3", base_url="https://api.x.ai/v1"):
        self.model = model
        self.base_url = base_url
        self.api_key = os.getenv("XAI_API_KEY")

    def chat(self, user_input, history=None, model=None, system_prompt=None):
        if not self.api_key:
            return "Fout: XAI_API_KEY environment variabele is niet geconfigureerd."

        if history is None:
            history = []
        target_model = model if model else self.model

        active_system_prompt = (
            system_prompt
            if system_prompt
            else "Je bent Grok, een behulpzame AI-assistent gemaakt door xAI."
        )

        messages = [{"role": "system", "content": active_system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_input})

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": target_model,
            "messages": messages,
            "temperature": 0.7,
        }

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=60,
            )
            if response.status_code != 200:
                print(f"🔥 [GROK XAI ERROR]: {response.text}")
            response.raise_for_status()
            return (
                response.json()
                .get("choices", [{}])[0]
                .get("message", {})
                .get("content", "Fout: Geen antwoord ontvangen.")
            )
        except requests.exceptions.RequestException as e:
            details = e.response.text if hasattr(e, "response") and e.response is not None else ""
            return f"GROK XAI ERROR: {str(e)} | Details: {details}"
        except Exception as e:
            return f"GROK XAI ERROR: {str(e)}"

    def list_models(self):
        """Haal beschikbare Grok-modellen op via de xAI API."""
        if not self.api_key:
            return []
        headers = {"Authorization": f"Bearer {self.api_key}"}
        try:
            response = requests.get(
                f"{self.base_url}/models", headers=headers, timeout=15
            )
            response.raise_for_status()
            return [m["id"] for m in response.json().get("data", [])]
        except Exception:
            return ["grok-3", "grok-3-mini", "grok-2"]
