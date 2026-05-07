import json
import os
import struct
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
COCKPIT_DIR = REPO_ROOT / "ouroboros_cockpit"


def _first_existing(paths):
    for path in paths:
        if path.exists():
            return path
    return None


def _png_size(path):
    with path.open("rb") as handle:
        header = handle.read(24)
    if len(header) < 24 or not header.startswith(b"\x89PNG\r\n\x1a\n"):
        raise AssertionError(f"{path} is not a PNG file")
    return struct.unpack(">II", header[16:24])


class TestTauriCockpitFiles(unittest.TestCase):
    def test_ouroboros_cockpit_package_and_config_files_exist(self):
        expected_groups = {
            "cockpit root": [COCKPIT_DIR],
            "package manifest": [COCKPIT_DIR / "package.json"],
            "HTML entry": [COCKPIT_DIR / "index.html"],
            "React src directory": [COCKPIT_DIR / "src"],
            "React main entry": [
                COCKPIT_DIR / "src" / "main.tsx",
                COCKPIT_DIR / "src" / "main.jsx",
                COCKPIT_DIR / "src" / "main.ts",
                COCKPIT_DIR / "src" / "main.js",
            ],
            "React app component": [
                COCKPIT_DIR / "src" / "App.tsx",
                COCKPIT_DIR / "src" / "App.jsx",
            ],
            "Vite config": [
                COCKPIT_DIR / "vite.config.ts",
                COCKPIT_DIR / "vite.config.js",
                COCKPIT_DIR / "vite.config.mts",
            ],
            "TypeScript config": [COCKPIT_DIR / "tsconfig.json"],
            "Tauri Rust manifest": [COCKPIT_DIR / "src-tauri" / "Cargo.toml"],
            "Tauri config": [
                COCKPIT_DIR / "src-tauri" / "tauri.conf.json",
                COCKPIT_DIR / "src-tauri" / "tauri.conf.json5",
            ],
        }

        missing = [
            f"{label}: one of {', '.join(str(path.relative_to(REPO_ROOT)) for path in paths)}"
            for label, paths in expected_groups.items()
            if _first_existing(paths) is None
        ]

        self.assertEqual(
            [],
            missing,
            "Ouroboros Tauri cockpit scaffold is incomplete or missing.",
        )

    def test_package_declares_xterm_dependency(self):
        package_path = COCKPIT_DIR / "package.json"
        self.assertTrue(package_path.exists(), "Missing ouroboros_cockpit/package.json")

        package = json.loads(package_path.read_text(encoding="utf-8"))
        dependency_sections = (
            package.get("dependencies", {}),
            package.get("devDependencies", {}),
            package.get("optionalDependencies", {}),
        )
        dependencies = {
            name
            for section in dependency_sections
            if isinstance(section, dict)
            for name in section
        }

        self.assertTrue(
            {"@xterm/xterm", "xterm"} & dependencies,
            "package.json must include @xterm/xterm or xterm for the cockpit terminal.",
        )

    def test_tauri_config_points_to_vite_dev_and_dist_frontend(self):
        config_path = _first_existing(
            [
                COCKPIT_DIR / "src-tauri" / "tauri.conf.json",
                COCKPIT_DIR / "src-tauri" / "tauri.conf.json5",
            ]
        )
        self.assertIsNotNone(config_path, "Missing src-tauri/tauri.conf.json")

        config = json.loads(config_path.read_text(encoding="utf-8"))
        build = config.get("build", {})
        self.assertIsInstance(build, dict, "Tauri config must contain a build object.")

        before_dev = str(build.get("beforeDevCommand", ""))
        before_build = str(build.get("beforeBuildCommand", ""))
        dev_frontend = str(build.get("devUrl") or build.get("devPath") or "")
        dist_frontend = str(build.get("frontendDist") or build.get("distDir") or "")

        self.assertRegex(
            before_dev.lower(),
            r"(npm|pnpm|yarn|bun|vite).*(dev)|vite",
            "Tauri beforeDevCommand should start the Vite dev frontend.",
        )
        self.assertRegex(
            dev_frontend,
            r"^https?://(localhost|127\.0\.0\.1):\d+",
            "Tauri devUrl/devPath should point at the local Vite dev server.",
        )
        self.assertRegex(
            before_build.lower(),
            r"(npm|pnpm|yarn|bun|vite).*(build)|vite build",
            "Tauri beforeBuildCommand should build the frontend.",
        )
        self.assertIn(
            "dist",
            dist_frontend.replace(os.sep, "/"),
            "Tauri frontendDist/distDir should point at the built frontend dist directory.",
        )

    def test_react_source_mentions_backend_config_and_required_endpoints(self):
        src_dir = COCKPIT_DIR / "src"
        self.assertTrue(src_dir.exists(), "Missing ouroboros_cockpit/src")

        source_files = sorted(
            path
            for path in src_dir.rglob("*")
            if path.suffix in {".ts", ".tsx", ".js", ".jsx"}
        )
        self.assertTrue(source_files, "Cockpit src must contain React source files.")

        source_text = "\n".join(path.read_text(encoding="utf-8") for path in source_files)
        endpoint_groups = {
            "backend base config": [
                "VITE_BACKEND_URL",
                "TAURI_BACKEND_URL",
                "http://localhost:8000",
                "http://127.0.0.1:8000",
                "localhost:8000",
                "127.0.0.1:8000",
            ],
            "model status": ["/api/ouroboros/status", "/api/ouroboros/model/status"],
            "create flow": ["/api/ouroboros/model/create-flow"],
            "browser research": ["/api/ouroboros/research/browser"],
            "chatgpt browser": ["/api/ouroboros/chatgpt/browser"],
            "training ingest": ["/api/ouroboros/training/ingest"],
            "hippocampus inspect": ["/api/ouroboros/hippocampus/inspect"],
            "self training step": ["/api/ouroboros/self-training/step"],
            "approval gated shell": ["/sandbox/shell", "/agent/tool"],
            "safe shell tool name": ["safe_shell"],
            "approval phrase": ["Akkoord"],
        }

        missing = [
            f"{label}: one of {', '.join(options)}"
            for label, options in endpoint_groups.items()
            if not any(option in source_text for option in options)
        ]

        self.assertEqual(
            [],
            missing,
            "React cockpit source does not mention all backend contract strings.",
        )

    def test_tauri_native_external_url_opener_is_registered(self):
        main_rs = COCKPIT_DIR / "src-tauri" / "src" / "main.rs"
        app_tsx = COCKPIT_DIR / "src" / "App.tsx"

        self.assertTrue(main_rs.exists(), "Missing Tauri main.rs")
        rust_source = main_rs.read_text(encoding="utf-8")
        react_source = app_tsx.read_text(encoding="utf-8")

        self.assertIn("open_external_url", rust_source)
        self.assertIn("tauri::generate_handler![backend_config, open_external_url]", rust_source)
        self.assertIn('invoke<boolean>("open_external_url"', react_source)
        self.assertIn('window.open("about:blank"', react_source)
        self.assertIn("reserved-window", react_source)

    def test_cockpit_surfaces_ouroboros_pocket_voice_runtime_badges(self):
        app_tsx = COCKPIT_DIR / "src" / "App.tsx"
        react_source = app_tsx.read_text(encoding="utf-8")

        for expected in [
            "AgenticTraceReadout",
            "Bronpad",
            "Brave Search",
            "source_trace",
            "source_kind",
            "model_only",
            "planner_source",
            "selected_model_interprets_answer",
            "brave_search_used",
            "pocket_processed_steps",
            "tools_blocked",
            "planner_guardrails_applied",
            "Guardrails",
            "agentic-guardrail-chips",
            "PocketVoiceReadout",
            "Ouroboros voice",
            "Cirq local measurement",
            "NumPy fallback",
            "local_model_translation_used",
            "dominant_dimensions",
            "cirq_available",
            "Quantum Foam Field active",
            "Field Collapse",
            "field-state-badge",
            "weight {formatMetric(node.weight)}",
        ]:
            self.assertIn(expected, react_source)

    def test_cockpit_uses_ouroboros_logo_assets_for_native_and_in_app_branding(self):
        app_tsx = COCKPIT_DIR / "src" / "App.tsx"
        styles_css = COCKPIT_DIR / "src" / "styles.css"
        config_path = COCKPIT_DIR / "src-tauri" / "tauri.conf.json"
        logo = COCKPIT_DIR / "src" / "assets" / "ouroboros-logo.png"
        icon_dir = COCKPIT_DIR / "src-tauri" / "icons"

        self.assertEqual((256, 256), _png_size(logo))
        self.assertEqual((32, 32), _png_size(icon_dir / "32x32.png"))
        self.assertEqual((128, 128), _png_size(icon_dir / "128x128.png"))
        self.assertEqual((256, 256), _png_size(icon_dir / "128x128@2x.png"))
        self.assertEqual((512, 512), _png_size(icon_dir / "icon.png"))

        self.assertIn("ouroborosLogoUrl", app_tsx.read_text(encoding="utf-8"))
        self.assertIn("brand-logo", app_tsx.read_text(encoding="utf-8"))
        self.assertIn(".brand-logo", styles_css.read_text(encoding="utf-8"))
        self.assertIn("icons/icon.png", config_path.read_text(encoding="utf-8"))

    def test_standalone_applications_launcher_starts_native_tauri_not_browser(self):
        start_script = REPO_ROOT / "scripts" / "start_ouroboros_cockpit.sh"
        install_script = REPO_ROOT / "scripts" / "install_ouroboros_cockpit_desktop.sh"

        self.assertTrue(start_script.exists(), "Missing native cockpit start script")
        self.assertTrue(install_script.exists(), "Missing Applications desktop installer")
        start_text = start_script.read_text(encoding="utf-8")
        install_text = install_script.read_text(encoding="utf-8")

        for expected in [
            "target/release/ouroboros-cockpit",
            "target/debug/ouroboros-cockpit",
            "npm run tauri -- dev",
            "docker compose up -d ouroboros-backend",
            "TAURI_BACKEND_URL",
            "VITE_BACKEND_URL",
        ]:
            self.assertIn(expected, start_text)

        self.assertNotIn("xdg-open", start_text)
        self.assertNotIn("sensible-browser", start_text)
        self.assertNotIn("google-chrome", start_text)

        for expected in [
            "[Desktop Entry]",
            "Name=Ouroboros Cockpit",
            "Exec=$LAUNCHER",
            "Icon=$ICON",
            "Terminal=false",
            "Categories=Development;",
        ]:
            self.assertIn(expected, install_text)

    def test_docker_compose_mounts_codex_repo_home_and_binary(self):
        compose_path = REPO_ROOT / "docker-compose.yml"
        self.assertTrue(compose_path.exists(), "Missing docker-compose.yml")
        compose_text = compose_path.read_text(encoding="utf-8")

        for expected in [
            "/home/pwintri2/Codex:/codex:ro",
            "/home/pwintri2/.codex:/codex_home:ro",
            "/codex_native/bin/linux-x86_64/codex",
            "WINTRIP_CODEX_PATH: /codex",
            "CODEX_HOME: /codex_home",
            "WINTRIP_CODEX_BINARY: /codex_native/bin/linux-x86_64/codex",
            "WINTRIP_NS_API_KEY: ${WINTRIP_NS_API_KEY:-}",
            "NS_API_SUBSCRIPTION_KEY: ${NS_API_SUBSCRIPTION_KEY:-}",
        ]:
            self.assertIn(expected, compose_text)


if __name__ == "__main__":
    unittest.main()
