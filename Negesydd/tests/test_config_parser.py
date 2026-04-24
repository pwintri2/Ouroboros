import json

import pytest

from config_parser import ConfigError, ConfigParser, ExecutionConfig, PlanConfig, TaskConfig, load_config


def test_parse_yaml_plan_file():
    config = ConfigParser.from_file("plans/example_workflow.yaml")

    assert isinstance(config, PlanConfig)
    assert config.name == "Multi-Agent Data Processing Pipeline"
    assert config.execution.mode == "sequential"
    assert "gorilla" in config.agents["required"]
    assert len(config.tasks) == 6
    assert config.tasks[0].id == "analyze_requirements"


def test_parse_json_plan():
    payload = {
        "version": "1.0",
        "name": "JSON Plan",
        "description": "Plan from JSON",
        "agents": {"required": ["codex_vscode"], "optional": []},
        "execution": {"mode": "sequential", "timeout_total_seconds": 600, "on_failure": "halt"},
        "tasks": [
            {
                "id": "task_1",
                "description": "Generate code",
                "agent": "codex_vscode",
                "depends_on": [],
            }
        ],
    }

    config = ConfigParser.from_json(json.dumps(payload))

    assert config.version == "1.0"
    assert isinstance(config.execution, ExecutionConfig)
    assert isinstance(config.tasks[0], TaskConfig)
    assert config.tasks[0].timeout_seconds == 300


def test_extended_prompt_parsing():
    prompt = """
[NEGESYDD_PLAN]
agents_required: gorilla, goose
execution_mode: sequential
timeout_minutes: 15

[INITIAL_CONTEXT]
Build a small service.

[STEPS]
1. Analyze requirements with gorilla
2. Implement with goose
3. Review with codex

[END_NEGESYDD_PLAN]

Use clean Python.
"""

    config = ConfigParser.from_prompt(prompt)

    assert config.agents["required"] == ["gorilla", "goose"]
    assert config.execution.timeout_total_seconds == 900
    assert [task.agent for task in config.tasks] == ["gorilla", "goose", "codex_vscode"]
    assert config.tasks[1].depends_on == ["task_1"]
    assert "Use clean Python." in config.description


def test_plain_prompt_fallback():
    config = ConfigParser.from_prompt("Create a CLI tool", agents=["goose"])

    assert config.name == "Direct Prompt"
    assert config.agents["required"] == ["goose"]
    assert len(config.tasks) == 1
    assert config.tasks[0].agent == "goose"


def test_invalid_dependency_raises_config_error():
    payload = {
        "version": "1.0",
        "name": "Bad Plan",
        "description": "Broken dependency",
        "tasks": [
            {
                "id": "task_1",
                "description": "Do work",
                "agent": "goose",
                "depends_on": ["missing_task"],
            }
        ],
    }

    with pytest.raises(ConfigError):
        PlanConfig.from_dict(payload)


def test_load_config_alias():
    config = load_config("plans/example_workflow.yaml")

    assert config.tasks[-1].id == "document_solution"
    assert "dashboard" in {channel["type"] for channel in config.notification["channels"]}
