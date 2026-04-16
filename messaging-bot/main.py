import yaml
from core.message_router import MessageRouter
from core.auth_manager import AuthManager
from core.logger import BotLogger
from adapters.ollama_adapter import OllamaAdapter
from adapters.gemini_cli_adapter import GeminiCLIAdapter

# Dummy adapters for demonstration
class DummyAdapter:
    def __init__(self, name, auth_manager):
        self.name = name
        self.auth_manager = auth_manager
    def send_message(self, message):
        key = self.auth_manager.get_api_key(self.name)
        return f"Response from {self.name} (using key: {key[:5]}...): Received '{message}'"

def load_config():
    with open("config.yaml", "r") as f:
        return yaml.safe_load(f)

def main():
    config = load_config()
    logger = BotLogger()
    auth_manager = AuthManager()
    
    # Initialize adapters
    adapters = {
        "ollama": OllamaAdapter(base_url=config["tools"]["ollama"]["base_url"], model=config["tools"]["ollama"]["model"]),
        "gemini_cli": GeminiCLIAdapter(cli_path=config["tools"]["gemini_cli"]["cli_path"]),
        "codex": DummyAdapter("Codex", auth_manager),
        "antigravity": DummyAdapter("Antigravity", auth_manager),
        "grok": DummyAdapter("Grok", auth_manager)
    }
    
    router = MessageRouter(adapters)
    
    logger.log("Messaging Bot initialized. Ready to route messages.")
    
    # Example test
    test_msg = "Hello, testing routing."
    print(router.route("ollama", test_msg))
    print(router.route("codex", test_msg))

if __name__ == "__main__":
    main()
