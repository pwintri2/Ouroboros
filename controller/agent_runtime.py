import os
from dataclasses import dataclass
from typing import Dict, List


@dataclass
class AgentConfig:
    agent_id: str
    label: str
    provider: str
    model: str
    owned_paths: List[str]


WINTRIP_AGENT_NAMES = {
    "agent1": "Wintrip Developer (Backend)",
    "agent2": "Wintrip UI (Frontend)",
    "agent3": "Wintrip Voorzitter (QA & Tester)",
    "agent4": "Wintrip Kritiek (Docs/Planning)",
}


def _env(name: str, default: str) -> str:
    return os.getenv(name, default).strip()


def get_orchestrator_config() -> Dict[str, str]:
    return {
        "provider": _env("WINTRIP_ORCHESTRATOR_PROVIDER", "gemini"),
        "model": _env("WINTRIP_ORCHESTRATOR_MODEL", "gemini-2.5-pro"),
    }


def get_subagent_defaults() -> Dict[str, str]:
    return {
        "provider": _env("WINTRIP_SUBAGENT_PROVIDER", "ollama"),
        "model": _env("WINTRIP_SUBAGENT_MODEL", "gemma4:latest"),
    }


def get_agent_configs(project_root: str = "/app") -> Dict[str, AgentConfig]:
    defaults = get_subagent_defaults()

    return {
        "wintrip-developer-backend": AgentConfig(
            agent_id="wintrip-developer-backend",
            label=WINTRIP_AGENT_NAMES["agent1"],
            provider=_env("WINTRIP_AGENT1_PROVIDER", defaults["provider"]),
            model=_env("WINTRIP_AGENT1_MODEL", defaults["model"]),
            owned_paths=[
                f"{project_root}/controller",
                f"{project_root}/docker-image",
                f"{project_root}/Dockerfile",
                f"{project_root}/docker-compose.yml",
                f"{project_root}/data/main_sandbox.py",
                f"{project_root}/data/start_sandbox.sh",
            ],
        ),
        "wintrip-ui-frontend": AgentConfig(
            agent_id="wintrip-ui-frontend",
            label=WINTRIP_AGENT_NAMES["agent2"],
            provider=_env("WINTRIP_AGENT2_PROVIDER", defaults["provider"]),
            model=_env("WINTRIP_AGENT2_MODEL", defaults["model"]),
            owned_paths=[
                f"{project_root}/regiekamer",
                f"{project_root}/WintripAI_IDE.html",
                f"{project_root}/demo_stream_of_consciousness.html",
                f"{project_root}/demo_stream_of_consciousness_en.html",
            ],
        ),
        "wintrip-voorzitter-qa-tester": AgentConfig(
            agent_id="wintrip-voorzitter-qa-tester",
            label=WINTRIP_AGENT_NAMES["agent3"],
            provider=_env("WINTRIP_AGENT3_PROVIDER", defaults["provider"]),
            model=_env("WINTRIP_AGENT3_MODEL", defaults["model"]),
            owned_paths=[
                f"{project_root}/sandbox_tests",
                f"{project_root}/smoke_test.py",
                f"{project_root}/test_phase1.py",
                f"{project_root}/test_phase2.py",
                f"{project_root}/test_phase3.py",
                f"{project_root}/test_phase4.py",
                f"{project_root}/requirements-dev.txt",
                f"{project_root}/setup.cfg",
            ],
        ),
        "wintrip-kritiek-docs-planning": AgentConfig(
            agent_id="wintrip-kritiek-docs-planning",
            label=WINTRIP_AGENT_NAMES["agent4"],
            provider=_env("WINTRIP_AGENT4_PROVIDER", defaults["provider"]),
            model=_env("WINTRIP_AGENT4_MODEL", defaults["model"]),
            owned_paths=[
                f"{project_root}/ARCHITECTURE.md",
                f"{project_root}/PROJECT.md",
                f"{project_root}/SESSION.md",
                f"{project_root}/SESSIE_VERSLAG_2026-04-07.md",
                f"{project_root}/README_AI.md",
                f"{project_root}/GEMINI.md",
                f"{project_root}/docs",
            ],
        ),
    }
