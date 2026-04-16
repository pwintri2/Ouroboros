from flask import Flask, request, jsonify
import yaml
from core.message_router import MessageRouter
from core.auth_manager import AuthManager
from adapters.ollama_adapter import OllamaAdapter
from adapters.gemini_cli_adapter import GeminiCLIAdapter
from adapters.chatgpt_adapter import ChatGPTAdapter

# Dummy adapter for demonstration
class DummyAdapter:
    def __init__(self, name, auth_manager):
        self.name = name
        self.auth_manager = auth_manager
    def send_message(self, message):
        key = self.auth_manager.get_api_key(self.name)
        return f"Response from {self.name} (using key: {key[:5]}...): Received '{message}'"

app = Flask(__name__)

def load_config():
    with open("config.yaml", "r") as f:
        return yaml.safe_load(f)

config = load_config()
auth_manager = AuthManager()

# Initialize adapters
adapters = {
    "ollama": OllamaAdapter(base_url=config["tools"]["ollama"]["base_url"], model=config["tools"]["ollama"]["model"]),
    "gemini_cli": GeminiCLIAdapter(cli_path=config["tools"]["gemini_cli"]["cli_path"]),
    "chatgpt": ChatGPTAdapter(api_key=config["tools"].get("chatgpt", {}).get("api_key")),
    "codex": DummyAdapter("Codex", auth_manager),
    "antigravity": DummyAdapter("Antigravity", auth_manager),
    "grok": DummyAdapter("Grok", auth_manager)
}

router = MessageRouter(adapters)

@app.route('/send', methods=['POST'])
def send_message():
    print(f"Request received: {request.json}")
    data = request.json
    tool_name = data.get('tool')
    message = data.get('message')
    persona = data.get('persona')
    
    if not tool_name or not message:
        return jsonify({"error": "Missing tool or message"}), 400
        
    response = router.route(tool_name, message, persona=persona)
    return jsonify({"response": response})

if __name__ == '__main__':
    app.run(port=5005)
