from pathlib import Path

import awake_keeper_launcher as launcher


def test_compose_command_defaults_to_fase2_project_and_port(monkeypatch):
    monkeypatch.setattr(launcher.shutil, "which", lambda name: "/usr/bin/docker" if name == "docker" else None)
    command = launcher.compose_command("ps")
    assert command.args[:3] == ["docker", "compose", "-f"]
    assert command.args[3] == str(launcher.COMPOSE_FILE)
    assert command.args[4:6] == ["-p", "ouroboros-fase2"]
    assert command.args[-1] == "ps"
    assert command.env["OUROBOROS_GRADIO_PORT"] == "7861"


def test_compose_command_uses_flatpak_spawn_when_docker_hidden(monkeypatch):
    def fake_which(name):
        if name == "flatpak-spawn":
            return "/usr/bin/flatpak-spawn"
        return None

    monkeypatch.setattr(launcher.shutil, "which", fake_which)
    command = launcher.compose_command("up", "--build", "-d", port="7862")
    assert command.args[:2] == ["flatpak-spawn", "--host"]
    assert command.args[2:4] == ["docker", "compose"]
    assert command.env["OUROBOROS_GRADIO_PORT"] == "7862"


def test_launcher_paths_are_repo_local():
    assert launcher.PROJECT_DIR == Path(__file__).resolve().parents[1]
    assert launcher.COMPOSE_FILE.name == "docker-compose.ouroboros.yml"


def test_sanitize_dashboard_port_rejects_bad_values():
    assert launcher.sanitize_dashboard_port("7861") == "7861"
    assert launcher.sanitize_dashboard_port("not-a-port") == "7861"
    assert launcher.sanitize_dashboard_port("99999") == "7861"


def test_browser_fallback_page_has_controls():
    state = launcher.BrowserLauncherState(port="7862")
    page = launcher.render_browser_page(state)
    assert "Start Fase 2" in page
    assert "Open Dashboard" in page
    assert "name=\"port\" value=\"7862\"" in page
    assert 'content="0.333"' in page
