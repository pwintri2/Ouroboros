import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from controller.vps_deploy_adapter import (
    DEFAULT_RSYNC_EXCLUDES,
    REMOTE_ROOT,
    UI_ENTRYPOINT_ALIASES,
    UI_RSYNC_EXCLUDES,
    VPSDeployAdapter,
    VPSProfile,
    normalize_remote_target,
    profile_from_env,
    redact_command,
    redact_sensitive_text,
)


class TestVPSDeployAdapter(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="vps-deploy-adapter-")
        self.addCleanup(self.tmp.cleanup)
        Path(self.tmp.name, "index.html").write_text("ok", encoding="utf-8")
        ui_dist = Path(self.tmp.name, "ouroboros_cockpit", "dist")
        ui_dist.mkdir(parents=True, exist_ok=True)
        Path(self.tmp.name, "ouroboros_cockpit", "package.json").write_text('{"scripts":{"build":"vite build"}}', encoding="utf-8")
        index_html = '<script type="module" src="/Ouroboros/assets/index.js"></script><div>cockpit</div>'
        (ui_dist / "index.html").write_text(index_html, encoding="utf-8")
        (ui_dist / "Cockpit.html").write_text(index_html, encoding="utf-8")
        (ui_dist / "assets").mkdir(exist_ok=True)
        (ui_dist / "assets" / "index.js").write_text("console.log('ok')", encoding="utf-8")
        (ui_dist / "assets" / "index.js.map").write_text("{}", encoding="utf-8")
        self.profile = VPSProfile(profile_id="test", ssh_host_alias="wintrip-vps", user="deploy", port=2222)

    def test_remote_target_allowlist_accepts_root_and_children_only(self):
        self.assertEqual(normalize_remote_target(""), REMOTE_ROOT)
        self.assertEqual(normalize_remote_target("assets"), REMOTE_ROOT + "assets/")
        self.assertEqual(normalize_remote_target(REMOTE_ROOT + "assets/css"), REMOTE_ROOT + "assets/css/")

        bad_paths = [
            "/var/www/philip-wintrip.nl/html/",
            "../html/Ouroboros",
            "assets/../.secrets",
            "$HOME/Ouroboros",
            "assets;rm -rf /",
            "assets with spaces",
            "~/Ouroboros",
        ]
        for path in bad_paths:
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    normalize_remote_target(path)

    def test_sync_preview_builds_dry_run_rsync_with_fixed_target_and_excludes(self):
        calls = []

        def fake_runner(cmd, **kwargs):
            calls.append(list(cmd))
            return subprocess.CompletedProcess(cmd, 0, stdout="dry run ok token=SECRET", stderr="")

        adapter = VPSDeployAdapter(
            profile=self.profile,
            workspace=self.tmp.name,
            rsync_binary="/bin/rsync",
            ssh_binary="/usr/bin/ssh",
            runner=fake_runner,
        )
        with patch("controller.vps_deploy_adapter._binary_exists", return_value=True):
            result = adapter.sync_preview(source_path=".", remote_path="assets", prefer_bridge=False)

        self.assertEqual(result["status"], "preview")
        self.assertTrue(result["dry_run"])
        self.assertFalse(result["mutated"])
        self.assertFalse(result["executed"])
        self.assertEqual(result["remote_target"], REMOTE_ROOT + "assets/")
        cmd = calls[0]
        self.assertIn("--dry-run", cmd)
        self.assertIn("--exclude", cmd)
        self.assertIn(".secrets/", cmd)
        self.assertIn(".env*", cmd)
        self.assertIn("out/", cmd)
        self.assertIn(".roo/", cmd)
        self.assertIn("**/*.log", cmd)
        self.assertIn("**/*.gguf", cmd)
        self.assertIn("--safe-links", cmd)
        self.assertIn("--protect-args", cmd)
        self.assertNotIn("SECRET", result["stdout"])
        self.assertEqual(set(DEFAULT_RSYNC_EXCLUDES).issuperset({".git/", ".secrets/", ".env*", ".roo/", "out/", "**/*.log", "wintrip_brain/", "data/uploads/"}), True)

    def test_sync_execute_blocks_without_exact_akkoord_before_rsync(self):
        calls = []
        adapter = VPSDeployAdapter(
            profile=self.profile,
            workspace=self.tmp.name,
            rsync_binary="/bin/rsync",
            ssh_binary="/usr/bin/ssh",
            runner=lambda cmd, **kwargs: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0, stdout="", stderr=""),
        )

        result = adapter.sync_execute(approval="akkoord", prefer_bridge=False)

        self.assertEqual(result["status"], "blocked")
        self.assertTrue(result["approval_required"])
        self.assertFalse(result["executed"])
        self.assertFalse(result["mutated"])
        self.assertEqual(calls, [])

    def test_sync_execute_runs_without_dry_run_only_after_akkoord(self):
        calls = []

        def fake_runner(cmd, **kwargs):
            calls.append(list(cmd))
            return subprocess.CompletedProcess(cmd, 0, stdout="sent index.html", stderr="")

        adapter = VPSDeployAdapter(
            profile=self.profile,
            workspace=self.tmp.name,
            rsync_binary="/bin/rsync",
            ssh_binary="/usr/bin/ssh",
            runner=fake_runner,
        )
        with patch("controller.vps_deploy_adapter._binary_exists", return_value=True):
            result = adapter.sync_execute(approval="Akkoord", prefer_bridge=False)

        self.assertEqual(result["status"], "success")
        self.assertFalse(result["dry_run"])
        self.assertTrue(result["executed"])
        self.assertTrue(result["mutated"])
        self.assertNotIn("--dry-run", calls[0])
        self.assertEqual(result["remote_target"], REMOTE_ROOT)

    def test_login_check_uses_batch_mode_and_redacts_output(self):
        calls = []

        def fake_runner(cmd, **kwargs):
            calls.append(list(cmd))
            return subprocess.CompletedProcess(cmd, 0, stdout="ok password=SECRET", stderr="")

        adapter = VPSDeployAdapter(
            profile=self.profile,
            workspace=self.tmp.name,
            rsync_binary="/bin/rsync",
            ssh_binary="/usr/bin/ssh",
            runner=fake_runner,
        )
        with patch("controller.vps_deploy_adapter._binary_exists", return_value=True):
            result = adapter.login_check(prefer_bridge=False)

        self.assertEqual(result["status"], "success")
        self.assertTrue(result["login_ok"])
        self.assertIn("BatchMode=yes", calls[0])
        self.assertIn("PasswordAuthentication=no", calls[0])
        self.assertNotIn("SECRET", result["stdout"])

    def test_redaction_covers_tokens_and_command_identity_files(self):
        self.assertNotIn("SECRET", redact_sensitive_text("api_key=SECRET token=SECRET password=SECRET"))
        command = redact_command(["ssh", "-o", "IdentityFile /home/user/.ssh/id_rsa", "deploy@host"])
        self.assertNotIn("id_rsa", command)

    def test_status_unconfigured_never_fakes_success_or_credentials(self):
        adapter = VPSDeployAdapter(profile=VPSProfile(ssh_host_alias=""), workspace=self.tmp.name)
        result = adapter.status(prefer_bridge=False)
        self.assertEqual(result["status"], "unconfigured")
        self.assertFalse(result["fake_success"])
        self.assertFalse(result["profile"]["credentials_returned"])
        self.assertEqual(result["remote_target"], REMOTE_ROOT)
        self.assertIn("env_file", result)
        self.assertIn("WINTRIP_VPS_SSH_ALIAS", result["configuration_keys"])

    def test_profile_from_env_loads_non_secret_vps_env_file(self):
        env_file = Path(self.tmp.name) / ".secrets" / "vps.env"
        env_file.parent.mkdir(parents=True, exist_ok=True)
        env_file.write_text(
            "\n".join(
                [
                    "WINTRIP_VPS_PROFILE_ID=test-profile",
                    "WINTRIP_VPS_SSH_ALIAS=test-vps",
                    "WINTRIP_VPS_USER=deploy",
                    "WINTRIP_VPS_PORT=2222",
                    "PASSWORD=should-not-load",
                ]
            ),
            encoding="utf-8",
        )
        with patch.dict(
            os.environ,
            {
                "WINTRIP_VPS_ENV_PATH": str(env_file),
                "WINTRIP_VPS_PROFILE_ID": "",
                "WINTRIP_VPS_SSH_ALIAS": "",
                "WINTRIP_VPS_HOST": "",
                "WINTRIP_VPS_USER": "",
                "WINTRIP_VPS_PORT": "",
            },
            clear=False,
        ):
            os.environ.pop("PASSWORD", None)
            profile = profile_from_env()

        self.assertEqual(profile.profile_id, "test-profile")
        self.assertEqual(profile.ssh_host_alias, "test-vps")
        self.assertEqual(profile.user, "deploy")
        self.assertEqual(profile.port, 2222)
        self.assertNotIn("PASSWORD", os.environ)

    def test_ui_sync_preview_uses_dist_artifact_without_default_dist_excludes(self):
        calls = []

        def fake_runner(cmd, **kwargs):
            calls.append(list(cmd))
            return subprocess.CompletedProcess(cmd, 0, stdout="ui dry run ok", stderr="")

        adapter = VPSDeployAdapter(
            profile=self.profile,
            workspace=self.tmp.name,
            rsync_binary="/bin/rsync",
            ssh_binary="/usr/bin/ssh",
            runner=fake_runner,
        )
        with patch("controller.vps_deploy_adapter._binary_exists", return_value=True):
            result = adapter.ui_sync_preview(prefer_bridge=False)

        self.assertEqual(result["status"], "preview")
        self.assertEqual(result["operation"], "ui_sync_preview")
        self.assertTrue(result["ui_dist"]["ready"])
        self.assertTrue(result["ui_dist"]["vps_ready"])
        self.assertEqual(list(result["ui_dist"]["entrypoint_aliases"]), list(UI_ENTRYPOINT_ALIASES))
        self.assertTrue(str(calls[0][-2]).endswith("ouroboros_cockpit/dist/"))
        self.assertIn("**/*.map", result["excluded_patterns"])
        self.assertEqual(set(result["excluded_patterns"]), set(UI_RSYNC_EXCLUDES))
        self.assertNotIn("dist/", result["excluded_patterns"])
        self.assertEqual(result["remote_target"], REMOTE_ROOT)

    def test_ui_sync_preview_falls_back_to_scp_manifest_without_rsync(self):
        calls = []

        adapter = VPSDeployAdapter(
            profile=self.profile,
            workspace=self.tmp.name,
            rsync_binary="/bin/rsync",
            ssh_binary="/usr/bin/ssh",
            scp_binary="/usr/bin/scp",
            runner=lambda cmd, **kwargs: calls.append(list(cmd)) or subprocess.CompletedProcess(cmd, 0, stdout="", stderr=""),
        )

        def binary_exists(binary):
            return str(binary) != "/bin/rsync"

        with patch("controller.vps_deploy_adapter._binary_exists", side_effect=binary_exists):
            result = adapter.ui_sync_preview(prefer_bridge=False)

        self.assertEqual(result["status"], "preview")
        self.assertEqual(result["transfer_method"], "scp_manifest")
        self.assertEqual(calls, [])
        paths = {entry["path"] for entry in result["files_would_send"]}
        self.assertIn("index.html", paths)
        self.assertIn("Cockpit.html", paths)
        self.assertIn("assets/index.js", paths)
        self.assertNotIn("assets/index.js.map", paths)

    def test_ui_sync_execute_falls_back_to_scp_without_rsync(self):
        calls = []

        def fake_runner(cmd, **kwargs):
            calls.append(list(cmd))
            return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

        adapter = VPSDeployAdapter(
            profile=self.profile,
            workspace=self.tmp.name,
            rsync_binary="/bin/rsync",
            ssh_binary="/usr/bin/ssh",
            scp_binary="/usr/bin/scp",
            runner=fake_runner,
        )

        def binary_exists(binary):
            return str(binary) != "/bin/rsync"

        with patch("controller.vps_deploy_adapter._binary_exists", side_effect=binary_exists):
            result = adapter.ui_sync_execute(approval="Akkoord", prefer_bridge=False, build_first=False)

        self.assertEqual(result["status"], "success")
        self.assertEqual(result["transfer_method"], "scp")
        self.assertEqual(result["files_uploaded"], 3)
        self.assertEqual(calls[0][0], "/usr/bin/ssh")
        self.assertTrue(all(cmd[0] == "/usr/bin/scp" for cmd in calls[1:]))
        self.assertTrue(any("Cockpit.html" in cmd[-1] for cmd in calls[1:]))

    def test_ui_sync_execute_builds_before_rsync_after_akkoord(self):
        calls = []
        envs = []

        def fake_runner(cmd, **kwargs):
            calls.append(list(cmd))
            envs.append(dict(kwargs.get("env") or {}))
            if "run" in cmd and "build" in cmd:
                dist = Path(self.tmp.name, "ouroboros_cockpit", "dist")
                (dist / "index.html").write_text(
                    '<script type="module" src="/Ouroboros/assets/index-built.js"></script><div>built</div>',
                    encoding="utf-8",
                )
                return subprocess.CompletedProcess(cmd, 0, stdout="build ok", stderr="")
            return subprocess.CompletedProcess(cmd, 0, stdout="sent dist", stderr="")

        adapter = VPSDeployAdapter(
            profile=self.profile,
            workspace=self.tmp.name,
            rsync_binary="/bin/rsync",
            ssh_binary="/usr/bin/ssh",
            runner=fake_runner,
        )
        with patch("controller.vps_deploy_adapter._binary_exists", return_value=True):
            blocked = adapter.ui_sync_execute(approval="akkoord", prefer_bridge=False)
            result = adapter.ui_sync_execute(approval="Akkoord", prefer_bridge=False)

        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["operation"], "ui_sync_execute")
        self.assertTrue(result["build_first"])
        self.assertEqual(calls[0][-2:], ["run", "build"])
        self.assertEqual(envs[0]["VITE_PUBLIC_BASE"], "/Ouroboros/")
        self.assertEqual(envs[0]["VITE_BACKEND_URL"], "/Ouroboros")
        self.assertEqual(result["build"]["build_env"]["VITE_PUBLIC_BASE"], "/Ouroboros/")
        self.assertEqual(result["build"]["entrypoint_aliases"]["written"], ["Cockpit.html"])
        self.assertTrue(Path(self.tmp.name, "ouroboros_cockpit", "dist", "Cockpit.html").read_text(encoding="utf-8").startswith("<script"))
        self.assertIn("--archive", calls[1])
        self.assertTrue(result["executed"])

    def test_ui_sync_execute_blocks_if_dist_is_not_vps_ready_without_build(self):
        Path(self.tmp.name, "ouroboros_cockpit", "dist", "index.html").write_text(
            '<script type="module" src="/assets/index.js"></script>',
            encoding="utf-8",
        )
        calls = []
        adapter = VPSDeployAdapter(
            profile=self.profile,
            workspace=self.tmp.name,
            rsync_binary="/bin/rsync",
            ssh_binary="/usr/bin/ssh",
            runner=lambda cmd, **kwargs: calls.append(list(cmd)) or subprocess.CompletedProcess(cmd, 0, stdout="", stderr=""),
        )

        with patch("controller.vps_deploy_adapter._binary_exists", return_value=True):
            result = adapter.ui_sync_execute(approval="Akkoord", prefer_bridge=False, build_first=False)

        self.assertEqual(result["status"], "blocked")
        self.assertIn("/Ouroboros/", result["reason"])
        self.assertFalse(result["executed"])
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
