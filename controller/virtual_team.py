import re
import os
import json
import requests
from typing import Dict, Optional, List, Tuple

try:
    from controller.ollama_client import OllamaClient
    from controller.agent_protocol import make_envelope
    from controller.agent_runtime import get_agent_configs
except ImportError:
    from ollama_client import OllamaClient
    from agent_protocol import make_envelope
    from agent_runtime import get_agent_configs


def extract_python_code(text: str) -> List[Tuple[int, int]]:
    pattern = r'```python\n(.*?)\n```'
    matches = re.finditer(pattern, text, re.DOTALL)
    return [(m.start(1), m.end(1)) for m in matches]


class VirtualMeeting:
    def __init__(self, ollama_client: Optional[OllamaClient] = None):
        self.roles = [
            'Wintrip Developer (Backend)',
            'Wintrip UI (Frontend)',
            'Wintrip Voorzitter (QA & Tester)',
            'Wintrip Kritiek (Docs/Planning)',
        ]
        self.conversation_history = {}
        self.task = None
        self.ollama = ollama_client or OllamaClient(model=os.getenv("WINTRIP_SUBAGENT_MODEL", "gemma4:latest"))
        self.agent_configs = get_agent_configs(project_root=os.getenv("WINTRIP_PROJECT_ROOT", "/app"))
        self.review = []

    def run_meeting(self, task: str) -> Dict[str, dict]:
        self.task = task

        agent_order = [
            "wintrip-developer-backend",
            "wintrip-ui-frontend",
            "wintrip-voorzitter-qa-tester",
            "wintrip-kritiek-docs-planning",
        ]
        for agent_id in agent_order:
            envelope = self._query_agent(agent_id, task)
            self.conversation_history[envelope["agent"]] = envelope

        return self.conversation_history

    def _query_agent(self, agent_id: str, task: str) -> Dict[str, str]:
        cfg = self.agent_configs[agent_id]
        system_prompt = (
            f"Je bent {cfg.label} binnen WintripAI. "
            f"Werk alleen binnen jouw bestandsgrenzen. "
            f"Je draait lokaal via Ollama met model {cfg.model}. "
            f"Lever compact, feitelijk en uitvoerbaar advies. "
            f"Lever je antwoord in WINTRIP-AGENT/1.0 stijl."
        )
        response = self._query_ollama(task, role=cfg.label, model=cfg.model, system_prompt=system_prompt)
        return make_envelope(
            agent=cfg.label,
            task_id="VT-MEETING",
            type="result",
            summary=response[:800],
            owned_paths=cfg.owned_paths,
            outputs=[response],
            risks=[],
            needs_review=True,
            requires_human=False,
        )

    def run_code(self, code: str) -> Tuple[str, str]:
        from controller.sandbox import SandboxExecutor
        sandbox = SandboxExecutor()

        output = sandbox.run_python_code(code)

        if "[SANDBOX ERROR" in output or "[SANDBOX FATAL ERROR]" in output:
            return "", output

        return output, ""

    def _query_ollama(self, input_text: str, role: str, model: str = None, system_prompt: str = None) -> str:
        prompt = system_prompt or (
            f"Je bent een {role} in een software development team. "
            f"Ontwijk onnodige introducties. "
            f"Beantwoord professioneel, feitelijk en zo kort mogelijk in het Nederlands."
        )
        return self.ollama.chat(user_input=input_text, system_prompt=prompt, model=model)
