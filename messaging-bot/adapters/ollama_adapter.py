import requests

class OllamaAdapter:
    def __init__(self, base_url="http://localhost:11434", model="phi3"):
        self.base_url = base_url
        self.model = model

    def send_message(self, message):
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": message}]
        }
        try:
            response = requests.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
            return response.json()["message"]["content"]
        except Exception as e:
            return f"Error connecting to Ollama: {str(e)}"
