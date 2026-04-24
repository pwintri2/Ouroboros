import json

import pytest

from codex_bridge import CodexBridge, CodexNotDetected


def test_codex_bridge_outbox_fallback(tmp_path):
    bridge = CodexBridge(socket_path=str(tmp_path / "missing.sock"), outbox_dir=str(tmp_path))
    request = bridge.send_request("Write code", {"task_id": "t1"})
    saved = json.loads((tmp_path / f"{request.request_id}.json").read_text())
    assert saved["prompt"] == "Write code"
    assert saved["metadata"]["task_id"] == "t1"


def test_require_available_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("VSCODE_PID", raising=False)
    monkeypatch.delenv("TERM_PROGRAM", raising=False)
    bridge = CodexBridge(socket_path=str(tmp_path / "missing.sock"), outbox_dir=str(tmp_path))
    with pytest.raises(CodexNotDetected):
        bridge.send_request("x", require_available=True)


def test_capture_output(tmp_path):
    bridge = CodexBridge(outbox_dir=str(tmp_path))
    response_path = tmp_path / "abc.response.json"
    response_path.write_text(json.dumps({"text": "done"}))
    assert bridge.capture_output("abc") == {"text": "done"}
