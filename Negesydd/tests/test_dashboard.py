from dashboard import DashboardServer


def test_dashboard_status_endpoint():
    dashboard = DashboardServer()
    client = dashboard.test_client()
    response = client.get("/api/status")
    assert response.status_code == 200
    assert response.get_json()["status"] == "running"
    assert "queue_size" in response.get_json()


def test_dashboard_timeline_endpoint():
    dashboard = DashboardServer()
    dashboard.messenger.emit_event("ready", {"ok": True})
    response = dashboard.test_client().get("/api/timeline")
    assert response.status_code == 200
    assert response.get_json()[0]["event_type"] == "ready"


def test_dashboard_index():
    dashboard = DashboardServer()
    response = dashboard.test_client().get("/")
    assert response.status_code == 200
    assert b"Negesydd Dashboard" in response.data
    assert b"Gemini CLI" in response.data
    assert b"Codex in VSCode" in response.data


def test_dashboard_options_endpoint():
    dashboard = DashboardServer()
    response = dashboard.test_client().get("/api/options")
    assert response.status_code == 200
    assert any(option["name"] == "--dashboard" for option in response.get_json()["commands"])


def test_dashboard_components_endpoint():
    dashboard = DashboardServer()
    response = dashboard.test_client().get("/api/components")
    assert response.status_code == 200
    payload = response.get_json()
    assert "gemini_cli" in payload
    assert "codex_vscode" in payload


def test_dashboard_discover_endpoint():
    dashboard = DashboardServer()
    response = dashboard.test_client().post("/api/discover")
    assert response.status_code == 200
    assert "agents" in response.get_json()
