import os

class MessageRouter:
    def __init__(self, adapters):
        self.adapters = adapters
        self.persona_dir = "personas"

    def _get_persona_prompt(self, persona_name):
        if not persona_name:
            return None
        persona_file = os.path.join(self.persona_dir, f"{persona_name.lower()}.txt")
        if os.path.exists(persona_file):
            with open(persona_file, "r") as f:
                return f.read()
        return None

    def route(self, tool_name, message, persona=None):
        if tool_name not in self.adapters:
            return f"Tool {tool_name} not supported."
        
        final_message = message
        persona_prompt = self._get_persona_prompt(persona)
        if persona_prompt:
            final_message = f"System Instruction: {persona_prompt}\n\nUser Message: {message}"
            
        return self.adapters[tool_name].send_message(final_message)
