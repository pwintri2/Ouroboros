from resonant_ouroboros.safe_executor import SAFE_EXEC_COMMANDS, SafeActionExecutor


def test_safe_executor_blocks_dangerous_command(tmp_path):
    executor = SafeActionExecutor(path=tmp_path / "actions.json")
    result = executor.propose(
        kind="safe_command",
        payload={"command": "rm -rf /workspace"},
        auto_execute=False,
    )
    assert result["proposal"]["status"] == "blocked"
    assert result["approval_token"] is None
    assert "rm" in " ".join(result["proposal"]["safety_reasons"])


def test_safe_executor_requires_approval_for_code_review(tmp_path):
    executor = SafeActionExecutor(path=tmp_path / "actions.json")
    result = executor.propose(
        kind="apply_code_review",
        label="Approve & Review Code",
        payload={"code": "print('hello')"},
    )
    assert result["proposal"]["status"] == "pending"
    assert result["proposal"]["classification"] == "approval_required"
    assert result["approval_token"].startswith("apr_")

    rejected = executor.approve(result["proposal"]["id"], approval_token="wrong")
    assert rejected["ok"] is False
    assert rejected["proposal"]["status"] == "pending"

    approved = executor.approve(result["proposal"]["id"], approval_token=result["approval_token"])
    assert approved["ok"] is True
    assert approved["proposal"]["status"] == "executed"
    assert approved["proposal"]["result"]["mode"] == "review_only"
    repeated = executor.approve(result["proposal"]["id"], approval_token=result["approval_token"])
    assert repeated["ok"] is False
    assert repeated["proposal"]["status"] == "executed"


def test_safe_executor_safe_command_requires_approval_and_uses_docker_exec_vector(tmp_path):
    executor = SafeActionExecutor(path=tmp_path / "actions.json", docker_bin="true", enable_sandbox_exec=False)
    result = executor.propose(kind="safe_command", payload={"argv": ["ls", "/workspace"]})
    assert result["proposal"]["classification"] == "approval_required"
    assert result["proposal"]["status"] == "pending"
    approved = executor.approve(result["proposal"]["id"], approval_token=result["approval_token"])
    assert approved["proposal"]["status"] == "approved"
    assert approved["proposal"]["result"]["mode"] == "sandbox_exec_disabled"
    assert "feedback" in approved["proposal"]["result"]
    assert approved["proposal"]["result"]["prepared_command"][:3] == [
        "true",
        "exec",
        "ouroboros-fase2-ouroboros-1",
    ]


def test_safe_executor_can_execute_in_current_sandbox_when_enabled(tmp_path):
    executor = SafeActionExecutor(
        path=tmp_path / "actions.json",
        enable_sandbox_exec=True,
        sandbox_cwd=tmp_path,
    )
    result = executor.propose(kind="safe_command", payload={"argv": ["pwd"]})
    approved = executor.approve(result["proposal"]["id"], approval_token=result["approval_token"])
    assert approved["proposal"]["status"] == "executed"
    assert approved["proposal"]["result"]["mode"] == "sandbox_exec"
    assert approved["proposal"]["result"]["exit_code"] == 0
    assert approved["proposal"]["result"]["feedback"].startswith("Command completed successfully")
    assert str(tmp_path) in approved["proposal"]["result"]["stdout"]


def test_safe_executor_can_execute_when_explicitly_enabled(tmp_path):
    executor = SafeActionExecutor(
        path=tmp_path / "actions.json",
        docker_bin="true",
        enable_docker_exec=True,
        enable_sandbox_exec=False,
    )
    result = executor.propose(kind="safe_command", payload={"argv": ["ls", "/workspace"]})
    approved = executor.approve(result["proposal"]["id"], approval_token=result["approval_token"])
    assert approved["proposal"]["status"] == "executed"
    assert approved["proposal"]["result"]["mode"] == "docker_exec"
    assert approved["proposal"]["result"]["command"][:3] == [
        "true",
        "exec",
        "ouroboros-fase2-ouroboros-1",
    ]


def test_safe_executor_evolution_proposal_is_review_only_and_batch_approvable(tmp_path):
    executor = SafeActionExecutor(path=tmp_path / "actions.json")
    first = executor.propose(
        kind="evolution_proposal",
        label="Evolution Proposal",
        payload={
            "proposal": "Improve prompt context links.",
            "target_files": ["resonant_ouroboros/prompt_context.py"],
            "tests_to_run": ["pytest -q"],
            "risk": "low",
        },
    )
    second = executor.propose(
        kind="safe_evolution_proposal",
        label="Safe Evolution Proposal",
        payload={"proposal": "Clarify self-model goals."},
    )
    assert first["proposal"]["status"] == "pending"
    assert first["proposal"]["classification"] == "approval_required"
    assert executor.summary()["pending_evolution_proposals"] == 2

    batch = executor.approve_many(
        [
            {"action_id": first["proposal"]["id"], "approval_token": first["approval_token"]},
            {"action_id": second["proposal"]["id"], "approval_token": second["approval_token"]},
        ],
        approved_by="test",
    )
    assert batch["ok"] is True
    assert batch["summary"]["pending_evolution_proposals"] == 0
    assert batch["results"][0]["proposal"]["result"]["mode"] == "evolution_review_only"
    assert "No prompts, code, files" in batch["results"][0]["proposal"]["result"]["message"]


def test_safe_executor_blocks_secret_relative_paths_and_python_inline(tmp_path):
    executor = SafeActionExecutor(path=tmp_path / "actions.json")
    secret = executor.propose(
        kind="safe_command",
        payload={"argv": ["cat", ".env"]},
        auto_execute=False,
    )
    assert secret["proposal"]["status"] == "blocked"

    inline = executor.propose(
        kind="safe_command",
        payload={"argv": ["python3", "-c", "print('no')"]},
        auto_execute=False,
    )
    assert inline["proposal"]["status"] == "blocked"


def test_safe_executor_whitelist_is_explicit():
    assert "ls" in SAFE_EXEC_COMMANDS
    assert "cat" in SAFE_EXEC_COMMANDS
    assert "wc" in SAFE_EXEC_COMMANDS
    assert "date" in SAFE_EXEC_COMMANDS
    assert "du" in SAFE_EXEC_COMMANDS
    assert "pytest" in SAFE_EXEC_COMMANDS
    assert "python3" in SAFE_EXEC_COMMANDS
    assert "open" in SAFE_EXEC_COMMANDS
    assert "rm" not in SAFE_EXEC_COMMANDS


def test_safe_executor_pytest_is_workspace_bounded(tmp_path):
    executor = SafeActionExecutor(path=tmp_path / "actions.json")
    safe = executor.propose(
        kind="safe_command",
        payload={"argv": ["pytest", "-q", "tests"]},
        auto_execute=False,
    )
    assert safe["proposal"]["status"] == "pending"

    unsafe = executor.propose(
        kind="safe_command",
        payload={"argv": ["pytest", "--basetemp=/tmp/outside", "tests"]},
        auto_execute=False,
    )
    assert unsafe["proposal"]["status"] == "blocked"
