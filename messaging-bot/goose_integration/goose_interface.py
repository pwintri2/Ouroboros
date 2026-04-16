import yaml
from core.message_router import MessageRouter
from adapters.ollama_adapter import OllamaAdapter
from adapters.gemini_cli_adapter import GeminiCLIAdapter

class GooseInterface:
    def __init__(self, config_path="config.yaml"):
        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)
        
        # In a production scenario, you would initialize these dynamically based on config
        self.router = MessageRouter({
            "ollama": OllamaAdapter(base_url=self.config["tools"]["ollama"]["base_url"], model=self.config["tools"]["ollama"]["model"]),
            "gemini_cli": GeminiCLIAdapter(cli_path=self.config["tools"]["gemini_cli"]["cli_path"]),
            # Add other adapters here
        })

    def send_to_tool(self, tool_name, message):
        return self.router.route(tool_name, message)
