import json

import pytest

from llm_core import LLMCore, LLMError, OllamaClient, SubTask, TaskDefinition


class FakeClient:
    def __init__(self, response=None, exc=None):
        self.response = response
        self.exc = exc
        self.prompts = []

    def generate(self, prompt, model=None, options=None):
        self.prompts.append(prompt)
        if self.exc:
            raise self.exc
        return self.response

    def is_model_available(self, model=None):
        return True


def task_json():
    return json.dumps(
        {
            "task_name": "Build API",
            "subtasks": [
                {"agent": "gorilla", "instruction": "Analyze requirements", "task_id": "task_1"},
                {"agent": "codex_vscode", "instruction": "Implement code", "task_id": "task_2"},
            ],
            "dependencies": {"task_2": ["task_1"]},
            "estimated_duration_seconds": 600,
            "critical_path": ["task_1", "task_2"],
        }
    )


def test_parse_task_response():
    core = LLMCore(client=FakeClient(response=task_json()))

    definition = core.parse_task_response(f"```json\n{task_json()}\n```")

    assert isinstance(definition, TaskDefinition)
    assert definition.task_name == "Build API"
    assert definition.subtasks[1].agent == "codex_vscode"
    assert definition.dependencies == {"task_2": ["task_1"]}


def test_analyze_prompt_uses_client():
    fake = FakeClient(response=task_json())
    core = LLMCore(client=fake)

    definition = core.analyze_prompt("Build a REST API")

    assert definition.task_name == "Build API"
    assert fake.prompts
    assert "Build a REST API" in fake.prompts[0]


def test_analyze_prompt_fallback_on_llm_error():
    core = LLMCore(client=FakeClient(exc=LLMError("offline")))

    definition = core.analyze_prompt("Implement authentication code")

    assert definition.task_name == "Implement Authentication Code"
    assert definition.subtasks[0].agent == "codex_vscode"
    assert definition.critical_path == ["task_1"]


def test_invalid_llm_response_raises():
    core = LLMCore(client=FakeClient(response="not json"))

    with pytest.raises(LLMError):
        core.parse_task_response("not json")


def test_route_to_best_agent_heuristics():
    core = LLMCore(client=FakeClient(response=task_json()))

    assert core.route_to_best_agent("Analyze and design the plan") == "gorilla"
    assert core.route_to_best_agent("Run tests and validate output") == "goose"
    assert core.route_to_best_agent("Implement the code module") == "codex_vscode"


def test_summarize_results_without_llm():
    core = LLMCore(client=FakeClient(response=task_json()))

    summary = core.summarize_results(
        [
            {"task": "one", "status": "completed"},
            {"task": "two", "status": "failed"},
            {"task": "three", "status": "running"},
        ]
    )

    assert "3 event(s)" in summary
    assert "1 completed" in summary
    assert "1 failed" in summary


def test_count_tokens():
    core = LLMCore(client=FakeClient(response=task_json()))

    assert core.count_tokens("Build API, then test.") == 6


def test_validate_response():
    core = LLMCore(client=FakeClient(response=task_json()))

    assert core.validate_response(task_json())
    assert not core.validate_response("{}")


def test_subtask_from_dict_defaults():
    subtask = SubTask.from_dict({"description": "Do work"}, 2)

    assert subtask.agent == "codex_vscode"
    assert subtask.instruction == "Do work"
    assert subtask.task_id == "task_2"


def test_ollama_client_generate_with_fake_transport():
    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"response": "hello"}

    calls = []

    def transport(url, json=None, timeout=None):
        calls.append((url, json, timeout))
        return Response()

    client = OllamaClient(base_url="http://ollama", model="deepseek-coder:latest", transport=transport)

    assert client.generate("hi") == "hello"
    assert calls[0][0] == "http://ollama/api/generate"
    assert calls[0][1]["stream"] is False
